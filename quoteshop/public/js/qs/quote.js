// /quote – quote list (localStorage via quote_store), paste/upload, details form, OTP, submit.
// Also exports the small helpers (call, money, esc, fillQuote, startChange) used by quote_view.js and account.js.
import { __ } from "./i18n.js";
import { getQuote, setQty, remove, clear, recolour } from "./quote_store.js";

const API = "/api/method/quoteshop.quoteshop_enquiry.";
const CHANGE_KEY = "qs-change";
const MOBILE = "(max-width: 767px)";

export async function call(method, args = {}) {
	const headers = { "Content-Type": "application/json", Accept: "application/json" };
	const csrf = (window.frappe && window.frappe.csrf_token) || document.querySelector('meta[name="csrf-token"]')?.content;
	if (csrf && csrf !== "None") headers["X-Frappe-CSRF-Token"] = csrf;
	let res, data = {};
	try {
		res = await fetch(method.startsWith("quoteshop.") ? `/api/method/${method}` : API + method, { method: "POST", headers, credentials: "same-origin", body: JSON.stringify(args) });
		data = await res.json();
	} catch (e) {
		throw new Error(res ? __("Something went wrong. Please try again.") : __("You seem to be offline. Please try again."));
	}
	if (!res.ok || data.exc_type) throw new Error(serverMessage(data) || __("Something went wrong. Please try again."));
	return data.message;
}

function serverMessage(data) {
	try {
		const msg = JSON.parse(JSON.parse(data._server_messages).pop()).message;
		return new DOMParser().parseFromString(msg, "text/html").body.textContent; // inert: no scripts, no image loads
	} catch (e) {
		return "";
	}
}

export function money(value, currency) {
	const v = Number(value) || 0;
	const digits = Math.abs(v - Math.round(v)) < 0.005 ? 0 : 2;
	try {
		return new Intl.NumberFormat("en-IN", { style: "currency", currency: currency || "INR", minimumFractionDigits: digits, maximumFractionDigits: digits }).format(v);
	} catch (e) {
		return `${currency || ""} ${v.toFixed(digits)}`.trim();
	}
}

export function esc(s) {
	return String(s ?? "").replace(/[&<>"']/g, (c) => ({ "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;", "'": "&#39;" })[c]);
}

// E.164: "+" and 8–15 digits; a bare 10-digit number gets +91 (CONTRACTS §7.2).
export function normaliseMobile(raw) {
	const digits = raw.replace(/\D/g, "");
	if (raw.trim().startsWith("+")) return digits.length >= 8 && digits.length <= 15 ? `+${digits}` : null;
	if (digits.length === 10) return `+91${digits}`;
	if (digits.length === 12 && digits.startsWith("91")) return `+${digits}`;
	return null;
}

// one / many are translated "{0} …" templates
const plural = (n, one, many) => (n === 1 ? one : many).replace("{0}", n.toLocaleString("en-IN"));

export function listItems() {
	const q = getQuote();
	return (Array.isArray(q) ? q : q?.items) || [];
}

export function fillQuote(items, { replace = false } = {}) {
	if (replace) clear();
	items.forEach((i) => i.qty > 0 && setQty(i.item_code, i.qty, i.colour || ""));
}

// Buyer "Change" on /q: park the current list, load the quote lines, edit them on /quote.
export function startChange(ctx, items) {
	localStorage.setItem(CHANGE_KEY, JSON.stringify({ ...ctx, back: location.href, prev: listItems() }));
	fillQuote(items, { replace: true });
	location.href = "/quote";
}

function readChange() {
	try {
		return JSON.parse(localStorage.getItem(CHANGE_KEY) || "null");
	} catch (e) {
		return null;
	}
}

function endChange(change) {
	fillQuote(change.prev || [], { replace: true });
	localStorage.removeItem(CHANGE_KEY);
}

// Small card cache so /quote can draw real rows at first paint (CONTRACTS §11 front end): {v: 1, cards: {code: card + t}}.
const CARDS_KEY = "qs-quote-cards";
const CARD_TTL = 24 * 3600 * 1000;
const CARD_MAX = 200;

function readCardCache() {
	try {
		const data = JSON.parse(localStorage.getItem(CARDS_KEY));
		if (data && data.v === 1 && data.cards && typeof data.cards === "object") return data.cards;
	} catch (e) {
		/* blocked or corrupt storage: no cache */
	}
	return {};
}

function saveCardCache(cards) {
	const keep = Object.entries(cards).sort((a, b) => (b[1].t || 0) - (a[1].t || 0)).slice(0, CARD_MAX);
	Object.keys(cards).forEach((code) => keep.some((k) => k[0] === code) || delete cards[code]);
	try {
		localStorage.setItem(CARDS_KEY, JSON.stringify({ v: 1, cards: Object.fromEntries(keep) }));
	} catch (e) {
		/* storage full or blocked: rows just load as before */
	}
}

export function init() {
	const root = document.querySelector("[data-qs-quote]");
	if (!root) return;
	const $ = (s) => root.querySelector(s);
	const linesEl = $("[data-qs-lines]");
	const findEl = $("[data-qs-find]");
	const errEl = $("[data-qs-error]");
	const sendBtn = $("[data-qs-send]");
	const otpBox = $("[data-qs-otp]");
	const showPrices = root.dataset.showPrices === "1";
	const otpRequired = root.dataset.otp === "1";
	const cards = new Map();
	const change = readChange();
	let rows = [];
	let refocus = null;
	let busy = false;
	let loading = false;
	let otpFor = null;
	let otpToken = null;

	// ---- lines ----
	// Real rows from the card cache at first paint, skeleton rows for the rest, then one parallel
	// revalidation (stale-while-revalidate); rows are updated in place, so the page below never jumps.
	const cache = readCardCache();
	const inflight = new Set();
	let revalidated = false;
	listItems().forEach((i) => {
		const hit = cache[i.item_code];
		if (hit && Date.now() - hit.t < CARD_TTL && !cards.has(i.item_code)) cards.set(i.item_code, hit);
	});

	async function fetchCards(codes) {
		codes.forEach((c) => inflight.add(c));
		try {
			// one round trip: cards and colour choices side by side (get_colours only names items that have colours)
			const [found, by] = await Promise.all([
				call("api.get_quote_items", { item_codes: codes }),
				call("quoteshop.quoteshop_catalog.catalog.get_colours", { item_codes: codes }).catch(() => null),
			]);
			const seen = new Set();
			(found || []).forEach((c) => {
				if (seen.has(c.item_code)) return;
				seen.add(c.item_code);
				const old = cards.get(c.item_code);
				if (by) c.colours = by[c.item_code] || [];
				else if (c.has_colours === false) c.colours = [];
				else if (old && Array.isArray(old.colours)) c.colours = old.colours; // colour call failed: keep what we knew
				c.fresh = true; // colours are current: the stale-colour check may trust them
				cards.set(c.item_code, c);
				cache[c.item_code] = { ...c, image: c.image ? { thumb: c.image.thumb } : null, fresh: undefined, t: Date.now() };
			});
			saveCardCache(cache);
			codes.filter((c) => !seen.has(c)).forEach((c) => {
				cards.set(c, null);
				delete cache[c];
				listItems().filter((i) => i.item_code === c).forEach((i) => remove(c, i.colour || "")); // no longer published
			});
		} catch (e) {
			// offline: cached rows stay as they are, the others show their code
			codes.forEach((c) => cards.has(c) || cards.set(c, { item_code: c, item_name: c, fallback: true }));
		}
		codes.forEach((c) => inflight.delete(c));
	}

	async function load() {
		const codes = [...new Set(listItems().map((i) => i.item_code))];
		const need = codes.filter((c) => !inflight.has(c) && (!revalidated || !cards.has(c)));
		revalidated = true;
		render();
		if (need.length) {
			await fetchCards(need);
		}
		// a stored colour the item no longer has (admin removed it) becomes "not chosen"
		const stale = listItems().find((i) => i.colour && cards.get(i.item_code)?.fresh && !cards.get(i.item_code).colours.some((x) => x.label === i.colour));
		if (stale) return recolour(stale.item_code, stale.colour, ""); // emits qs:quote-changed -> load() again
		render();
	}

	let rendering = false;
	let again = false;

	function render() {
		// replacing the focused row blurs it, which can commit a typed quantity and re-enter: run that render afterwards
		if (rendering) return void (again = true);
		rendering = true;
		try {
			draw();
		} finally {
			rendering = false;
		}
		if (again) {
			again = false;
			render();
		}
	}

	function draw() {
		const focus = document.activeElement?.closest?.("[data-code]") && document.activeElement;
		const focusKey = focus ? [focus.closest("[data-code]").dataset.code, focus.closest("[data-code]").dataset.colour, focus.dataset.act] : null;
		const typed = focus && focus.matches('input[data-act="qty"]') ? [focus.value, focus.selectionStart, focus.selectionEnd] : null; // not committed yet
		const lines = listItems().filter((i) => cards.get(i.item_code) !== null).map((i) => ({ ...i, colour: i.colour || "", card: cards.get(i.item_code) }));
		const pending = lines.filter((l) => !l.card);
		rows = lines.filter((l) => l.card);
		const grouped = rows.length > 20 && !pending.length;
		const ordered = grouped ? groupRows(rows) : lines;
		const parts = [];
		let lastGroup = null;
		ordered.forEach((r, idx) => {
			const group = r.card?.item_group || "";
			if (grouped && group !== lastGroup) {
				const n = ordered.filter((x) => (x.card.item_group || "") === group).length;
				parts.push({ key: `g|${group}`, html: `<h2 class="qs-q-group" data-group="${esc(group)}">${esc(group || __("Other"))} · ${n}</h2>` });
				lastGroup = group;
			}
			parts.push(r.card ? { key: `${r.item_code}|${r.colour}`, html: rowHtml(r, idx) } : { key: `sk|${r.item_code}|${r.colour}`, html: skeletonHtml(r) });
		});
		if (pending.length) parts.unshift({ key: "sr", html: `<span class="qs-p-sr">${esc(__("Loading your items"))}</span>` });
		reconcile(parts);
		linesEl.setAttribute("aria-busy", String(pending.length > 0));
		if (refocus) {
			linesEl.querySelector(`[data-code="${CSS.escape(refocus[0])}"][data-colour="${CSS.escape(refocus[1])}"] input[data-act="colour"]:checked`)?.focus();
			refocus = null;
		} else if (focusKey) {
			const el = linesEl.querySelector(`[data-code="${CSS.escape(focusKey[0])}"][data-colour="${CSS.escape(focusKey[1])}"] [data-act="${focusKey[2]}"]`) || linesEl.querySelector('[data-act="rm"]');
			if (el && el !== focus) el.focus();
			if (el && typed && el.matches('input[data-act="qty"]')) {
				el.value = typed[0];
				el.setSelectionRange?.(typed[1], typed[2]);
			}
		}

		const n = lines.length;
		const u = lines.reduce((s, r) => s + Number(r.qty || 0), 0);
		$("[data-qs-summary]").textContent = __("{0} · {1} pcs.", [plural(n, __("{0} product"), __("{0} products")), u.toLocaleString("en-IN")]);
		$("[data-qs-count-text]").textContent = plural(n, __("{0} item"), __("{0} items"));
		$("[data-qs-units-text]").textContent = __("{0} pcs total", [u.toLocaleString("en-IN")]);
		const sendCount = $("[data-qs-send-count]");
		if (sendCount) sendCount.textContent = n ? `\u00a0· ${plural(n, __("{0} item"), __("{0} items"))}` : "";
		$("[data-qs-empty]").hidden = n > 0;
		$("[data-qs-list-search]").hidden = n <= 10;
		syncSend(pending.length > 0);
		applyFind();
	}

	// Keyed update of #lines: rows whose markup did not change stay (focus, typed text, scroll), the rest are swapped.
	function reconcile(parts) {
		const old = new Map([...linesEl.children].map((el) => [el.dataset.key, el]));
		let prev = null;
		parts.forEach(({ key, html }) => {
			let el = old.get(key);
			if (!el || el._html !== html) {
				const t = document.createElement("template");
				t.innerHTML = html;
				const next = t.content.firstElementChild;
				next._html = html;
				next.dataset.key = key;
				if (el && el.parentNode) el.replaceWith(next);
				el = next;
			}
			old.delete(key);
			const want = prev ? prev.nextElementSibling : linesEl.firstElementChild;
			if (el !== want) linesEl.insertBefore(el, want);
			prev = el;
		});
		old.forEach((el) => el.remove());
	}

	function skeletonHtml(r) {
		// same classes as a real row (so the same sizes at every breakpoint); a known-coloured line also reserves the swatch row
		return `<div class="qs-q-row qs-q-skel" aria-hidden="true">
			<div class="qs-q-thumb qs-sk"></div>
			<div class="qs-q-info">
				<div class="qs-q-name"><span class="qs-sk" style="width:62%">&nbsp;</span><span class="qs-sk qs-sk-2" style="width:44%">&nbsp;</span></div>
				<div class="qs-q-note"><span class="qs-sk" style="width:36%">&nbsp;</span></div>
				${r.colour ? '<div class="qs-q-sws">' + '<span class="qs-q-sw"><i class="qs-sk qs-sk-dot"></i></span>'.repeat(3) + "</div>" : ""}
			</div>
			<div class="qs-q-step qs-sk"></div>
			<span class="qs-q-x"></span>
		</div>`;
	}

	// the Send button waits for the list: lines still loading would be missing from the request
	function syncSend(pending) {
		loading = pending;
		if (!sendBtn) return;
		sendBtn.disabled = busy || loading;
		sendBtn.setAttribute("aria-disabled", String(busy || loading));
	}

	function groupRows(list) {
		const order = [];
		list.forEach((r) => !order.includes(r.card.item_group || "") && order.push(r.card.item_group || ""));
		return order.flatMap((g) => list.filter((r) => (r.card.item_group || "") === g));
	}

	function rowHtml(r, idx) {
		const c = r.card;
		const name = c.item_name || c.item_code;
		const note = c.short_description || "";
		const price = showPrices && c.starting_price != null ? __("from {0} each", [money(c.starting_price, c.currency)]) : __("price on request");
		const img = c.image?.thumb
			? `<img class="qs-q-thumb" src="${esc(c.image.thumb)}" alt="" width="64" height="64" loading="lazy">`
			: `<div class="qs-q-thumb" aria-hidden="true"></div>`;
		const title = c.route ? `<a href="/p/${esc(c.route)}">${esc(name)}</a>` : esc(name);
		const colours = Array.isArray(c.colours) ? c.colours : [];
		const dot = colours.find((x) => x.label === r.colour)?.swatch;
		const safeDot = /^#[0-9a-f]{3,8}$/i.test(dot || "") ? ` style="background:${dot}"` : "";
		const colourText = r.colour ? `<span class="qs-q-col"> · ${dot ? `<i class="qs-q-dot"${safeDot}></i>` : ""}${esc(r.colour)}</span>` : "";
		// one radio group of swatches per row (names unique per row); the colour name stays in the title line only
		const select = colours.length
			? `<div class="qs-q-sws" role="radiogroup" aria-label="${esc(__("Colour for {0}", [name]))}">${colours.map((x, j) => `<span class="qs-q-sw"><input type="radio" name="qs-q-c-${idx}" id="qs-q-c-${idx}-${j}" value="${esc(x.label)}" data-act="colour"${x.label === r.colour ? " checked" : ""}><label for="qs-q-c-${idx}-${j}"${/^#[0-9a-f]{3,8}$/i.test(x.swatch || "") ? ` style="--sw:${x.swatch}"` : ""}><span class="qs-p-sr">${esc(x.label)}</span></label></span>`).join("")}${r.colour ? "" : `<span class="qs-q-choose">${esc(__("Choose a colour"))}</span>`}</div>`
			: "";
		return `<div class="qs-q-row" data-code="${esc(r.item_code)}" data-colour="${esc(r.colour)}" data-find="${esc(`${name} ${r.item_code} ${r.colour}`.toLowerCase())}" data-group="${esc(c.item_group || "")}">
			${img}
			<div class="qs-q-info">
				<div class="qs-q-name">${title}${colourText}</div>
				<div class="qs-q-note">${esc(note)}<span class="qs-q-price${note ? " qs-q-sep" : ""}">${esc(price)}</span></div>
				${select}
			</div>
			<div class="qs-q-step">
				<button type="button" aria-label="${esc(__("Decrease quantity"))}" data-act="dec">−</button>
				<label class="qs-p-sr" for="qs-q-qty-${idx}">${esc(__("Quantity for {0}", [name]))}</label>
				<input id="qs-q-qty-${idx}" type="number" min="${minQty(c)}" step="1" inputmode="numeric" value="${esc(r.qty)}" data-act="qty">
				<button type="button" aria-label="${esc(__("Increase quantity"))}" data-act="inc">+</button>
			</div>
			<button type="button" class="qs-q-x" aria-label="${esc(__("Remove {0}", [name]))}" data-act="rm">
				<svg width="18" height="18" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" aria-hidden="true"><path d="M6 6l12 12M18 6L6 18"></path></svg>
			</button>
		</div>`;
	}

	const minQty = (c) => Math.max(1, parseInt(c.min_qty, 10) || 1);

	function rowOf(el) {
		const row = el.closest("[data-code]");
		return row && rows.find((r) => r.item_code === row.dataset.code && r.colour === row.dataset.colour);
	}

	linesEl.addEventListener("click", (e) => {
		const btn = e.target.closest("button[data-act]");
		if (!btn) return;
		const r = rowOf(btn);
		if (!r) return;
		const min = minQty(r.card);
		const qty = Number(r.qty) || min;
		if (btn.dataset.act === "inc") setQty(r.item_code, qty + 1, r.colour);
		if (btn.dataset.act === "dec") setQty(r.item_code, Math.max(min, qty - 1), r.colour);
		if (btn.dataset.act === "rm") remove(r.item_code, r.colour);
	});
	linesEl.addEventListener("change", (e) => {
		const r = rowOf(e.target);
		if (!r) return;
		if (e.target.dataset.act === "colour") {
			refocus = [r.item_code, e.target.value]; // the rows are redrawn: keep the keyboard on this row's swatches
			return recolour(r.item_code, r.colour, e.target.value);
		}
		if (e.target.dataset.act !== "qty") return;
		const v = parseInt(e.target.value, 10);
		const min = minQty(r.card);
		setQty(r.item_code, isNaN(v) || v < min ? min : v, r.colour);
	});

	function applyFind() {
		const q = findEl.value.trim().toLowerCase();
		let any = false;
		linesEl.querySelectorAll(".qs-q-row:not(.qs-q-skel)").forEach((el) => {
			el.hidden = !!q && !el.dataset.find.includes(q);
			any = any || !el.hidden;
		});
		linesEl.querySelectorAll(".qs-q-group").forEach((h) => {
			h.hidden = ![...linesEl.querySelectorAll(".qs-q-row:not(.qs-q-skel)")].some((el) => el.dataset.group === h.dataset.group && !el.hidden);
		});
		$("[data-qs-nomatch]").hidden = any || !rows.length;
	}
	findEl.addEventListener("input", applyFind);

	window.addEventListener("qs:quote-changed", load);

	// ---- paste / upload ----
	const pasteText = $("[data-qs-paste-text]");
	const pasteResult = $("[data-qs-paste-result]");
	$("[data-qs-paste-file]").addEventListener("change", async (e) => {
		const file = e.target.files[0];
		if (file) pasteText.value = (await file.text()).replace(/"/g, "");
		e.target.value = "";
	});
	$("[data-qs-paste-add]").addEventListener("click", async (e) => {
		const text = pasteText.value.trim();
		if (!text) return pasteText.focus();
		e.target.disabled = true;
		try {
			const r = await call("api.parse_quote_paste", { text });
			const have = Object.fromEntries(listItems().filter((i) => !i.colour).map((i) => [i.item_code, Number(i.qty) || 0])); // pasted lines have no colour
			(r.matched || []).forEach((m) => setQty(m.item_code, (have[m.item_code] || 0) + Number(m.qty)));
			const bad = r.unmatched || [];
			pasteResult.innerHTML = `${esc(__("Added {0}.", [plural((r.matched || []).length, __("{0} product"), __("{0} products"))]))}${
				bad.length ? ` ${esc(__("{0} not matched:", [plural(bad.length, __("{0} line"), __("{0} lines"))]))}<ul>${bad.map((u) => `<li>${esc(u.line)} — ${esc(u.reason)}</li>`).join("")}</ul>` : ""
			}`;
			if (!bad.length) pasteText.value = "";
		} catch (err) {
			pasteResult.textContent = err.message;
		}
		e.target.disabled = false;
	});

	// ---- notes field: left column on desktop, last field on mobile ----
	const notes = $("[data-qs-notes]");
	if (notes) {
		const mq = matchMedia(MOBILE);
		const place = () => {
			(mq.matches ? $("[data-qs-notes-mob]") : $("[data-qs-notes-desk]")).append(notes);
			notes.querySelector("textarea").placeholder = mq.matches ? notes.dataset.phM : notes.dataset.phD;
		};
		mq.addEventListener("change", place);
		place();
	}

	// ---- details form ----
	root.querySelectorAll("[data-qs-buyer]").forEach((b) =>
		b.addEventListener("click", () => root.querySelectorAll("[data-qs-buyer]").forEach((x) => x.setAttribute("aria-pressed", String(x === b)))),
	);
	root.querySelectorAll(".qs-q-toggle").forEach((b) =>
		b.addEventListener("click", () => {
			const on = b.getAttribute("aria-pressed") !== "true";
			b.setAttribute("aria-pressed", String(on));
			b.textContent = on ? b.dataset.yes : b.dataset.no;
		}),
	);

	function fail(msg, field) {
		errEl.textContent = msg;
		errEl.hidden = false;
		if (field) {
			field.setAttribute("aria-invalid", "true");
			field.focus();
		}
		return null;
	}

	function collect() {
		root.querySelectorAll("[aria-invalid]").forEach((f) => f.removeAttribute("aria-invalid"));
		const val = (id) => root.querySelector(`#${id}`)?.value.trim() || "";
		const nameEl = $("#qs-q-name");
		const waEl = $("#qs-q-wa");
		if (!nameEl.value.trim()) return fail(__("Please enter your name."), nameEl);
		const mobile = normaliseMobile(waEl.value);
		if (!mobile) return fail(__("Please enter a valid WhatsApp number."), waEl);
		const pin = $("#qs-q-pin");
		if (pin?.required && !pin.value.trim()) return fail(__("Please enter your delivery pincode."), pin);
		const answers = [];
		for (const q of root.querySelectorAll("[data-qs-question]")) {
			const input = q.querySelector("input, select, textarea, .qs-q-toggle");
			const value = q.dataset.type === "Check" ? input.textContent.trim() : input.value.trim();
			if (q.dataset.required && !value) return fail(__("Please answer: {0}", [q.dataset.qsQuestion]), input);
			if (value) answers.push({ question: q.dataset.qsQuestion, value });
		}
		const data = {
			items: rows.map(line),
			buyer_name: nameEl.value.trim(),
			mobile,
			answers,
		};
		const biz = val("qs-q-biz");
		const buyer = root.querySelector('[data-qs-buyer][aria-pressed="true"]');
		if (biz) data.business_name = biz;
		if (pin?.value.trim()) data.pincode = pin.value.trim();
		if (buyer) data.buyer_type = buyer.dataset.qsBuyer;
		if (val("qs-q-note")) data.notes = val("qs-q-note");
		return data;
	}

	const line = (r) => ({ item_code: r.item_code, qty: Number(r.qty), colour: r.colour });

	function setLabel(key) {
		$("[data-qs-send-label]").textContent = sendBtn.dataset[key];
	}

	async function send() {
		errEl.hidden = true;
		if (!rows.length) return fail(__("Add at least one product to your list."));
		if (change) {
			const r = await call("quote_view.request_changes", {
				name: change.name,
				token: change.token,
				items: rows.map(line),
			});
			endChange(change);
			location.href = r.url;
			return;
		}
		const data = collect();
		if (!data) return;
		if (otpRequired && !(otpToken && otpFor === data.mobile)) {
			const otpInput = $("#qs-q-otp");
			if (otpBox.hidden || otpFor !== data.mobile) {
				await call("api.send_otp", { mobile: data.mobile });
				otpFor = data.mobile;
				otpToken = null;
				$("[data-qs-otp-to]").textContent = data.mobile;
				otpBox.hidden = false;
				otpInput.value = "";
				setLabel("labelVerify");
				otpInput.focus();
				return;
			}
			const code = otpInput.value.replace(/\D/g, "");
			if (code.length !== 6) return fail(__("Please enter the 6-digit code."), otpInput);
			otpToken = (await call("api.verify_otp", { mobile: data.mobile, otp: code })).otp_token;
		}
		if (otpToken) data.otp_token = otpToken;
		const r = await call("api.submit_enquiry", { data });
		done(r.name, data.items);
	}

	function done(ref, items) {
		const u = items.reduce((s, i) => s + i.qty, 0);
		clear();
		$("[data-qs-form-view]").hidden = true;
		$("[data-qs-done]").hidden = false;
		$("[data-qs-ref]").textContent = ref;
		$("[data-qs-done-summary]").textContent = __("{0}, {1} pcs", [plural(items.length, __("{0} product"), __("{0} products")), u.toLocaleString("en-IN")]);
		const wa = $("[data-qs-wa-link]");
		if (wa) wa.href += `?text=${encodeURIComponent(ref)}`;
		window.scrollTo(0, 0);
		$("#qs-q-done-h").focus();
	}

	sendBtn?.addEventListener("click", async () => {
		if (busy) return;
		busy = true;
		syncSend(loading);
		try {
			await send();
		} catch (e) {
			fail(e.message);
		}
		busy = false;
		syncSend(loading);
	});
	$("[data-qs-otp-resend]").addEventListener("click", async () => {
		try {
			await call("api.send_otp", { mobile: otpFor });
			fail(__("A new code is on its way."));
		} catch (e) {
			fail(e.message);
		}
	});

	// ---- change mode (coming from /q "Change") ----
	if (change) {
		$("[data-qs-change-banner]").hidden = false;
		$("[data-qs-change-text]").textContent = change.version ? __("Changing {0} · v{1}", [change.name, change.version]) : __("Changing {0}", [change.name]);
		$("[data-qs-details]").querySelectorAll(":scope > :not(.qs-q-send):not([data-qs-error]), .qs-q-fine").forEach((el) => (el.hidden = true));
		setLabel("labelChange");
		$("[data-qs-change-cancel]").addEventListener("click", () => {
			endChange(change);
			location.href = change.back || "/";
		});
	}

	load();
}
