// /quote – quote list (localStorage via quote_store), paste/upload, details form, OTP, submit.
// Also exports the small helpers (call, money, esc, fillQuote, startChange) used by quote_view.js and account.js.
import { __ } from "./i18n.js";
import { getQuote, setQty, remove, clear } from "./quote_store.js";

const API = "/api/method/quoteshop.quoteshop_enquiry.";
const CHANGE_KEY = "qs-change";
const MOBILE = "(max-width: 767px)";

export async function call(method, args = {}) {
	const headers = { "Content-Type": "application/json", Accept: "application/json" };
	const csrf = (window.frappe && window.frappe.csrf_token) || document.querySelector('meta[name="csrf-token"]')?.content;
	if (csrf && csrf !== "None") headers["X-Frappe-CSRF-Token"] = csrf;
	let res, data = {};
	try {
		res = await fetch(API + method, { method: "POST", headers, credentials: "same-origin", body: JSON.stringify(args) });
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
	items.forEach((i) => i.qty > 0 && setQty(i.item_code, i.qty));
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
	let busy = false;
	let otpFor = null;
	let otpToken = null;

	// ---- lines ----
	async function load() {
		const missing = listItems().map((i) => i.item_code).filter((c) => !cards.has(c));
		if (missing.length) {
			try {
				const found = (await call("api.get_quote_items", { item_codes: missing })) || [];
				found.forEach((c) => cards.set(c.item_code, c));
				missing.filter((c) => !cards.has(c)).forEach((c) => {
					cards.set(c, null);
					remove(c); // no longer published
				});
			} catch (e) {
				missing.forEach((c) => cards.set(c, { item_code: c, item_name: c, fallback: true }));
			}
		}
		render();
	}

	function render() {
		const focus = document.activeElement?.closest?.("[data-code]") && document.activeElement;
		const focusKey = focus ? [focus.closest("[data-code]").dataset.code, focus.dataset.act] : null;
		rows = listItems().filter((i) => cards.get(i.item_code)).map((i) => ({ ...i, card: cards.get(i.item_code) }));
		const grouped = rows.length > 20;
		let html = "";
		let lastGroup = null;
		const ordered = grouped ? groupRows(rows) : rows;
		ordered.forEach((r, idx) => {
			const group = r.card.item_group || "";
			if (grouped && group !== lastGroup) {
				const n = ordered.filter((x) => (x.card.item_group || "") === group).length;
				html += `<h2 class="qs-q-group" data-group="${esc(group)}">${esc(group || __("Other"))} · ${n}</h2>`;
				lastGroup = group;
			}
			html += rowHtml(r, idx);
		});
		linesEl.innerHTML = html;
		if (focusKey) (linesEl.querySelector(`[data-code="${CSS.escape(focusKey[0])}"] [data-act="${focusKey[1]}"]`) || linesEl.querySelector('[data-act="rm"]'))?.focus();

		const n = rows.length;
		const u = rows.reduce((s, r) => s + Number(r.qty || 0), 0);
		$("[data-qs-summary]").textContent = __("{0} · {1} pcs.", [plural(n, __("{0} product"), __("{0} products")), u.toLocaleString("en-IN")]);
		$("[data-qs-count-text]").textContent = plural(n, __("{0} item"), __("{0} items"));
		$("[data-qs-units-text]").textContent = __("{0} pcs total", [u.toLocaleString("en-IN")]);
		const sendCount = $("[data-qs-send-count]");
		if (sendCount) sendCount.textContent = n ? `\u00a0· ${plural(n, __("{0} item"), __("{0} items"))}` : "";
		$("[data-qs-empty]").hidden = n > 0;
		$("[data-qs-list-search]").hidden = n <= 10;
		applyFind();
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
		return `<div class="qs-q-row" data-code="${esc(r.item_code)}" data-find="${esc(`${name} ${r.item_code}`.toLowerCase())}" data-group="${esc(c.item_group || "")}">
			${img}
			<div class="qs-q-info">
				<div class="qs-q-name">${title}</div>
				<div class="qs-q-note">${esc(note)}<span class="qs-q-price${note ? " qs-q-sep" : ""}">${esc(price)}</span></div>
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
		const code = el.closest("[data-code]")?.dataset.code;
		return rows.find((r) => r.item_code === code);
	}

	linesEl.addEventListener("click", (e) => {
		const btn = e.target.closest("button[data-act]");
		if (!btn) return;
		const r = rowOf(btn);
		if (!r) return;
		const min = minQty(r.card);
		const qty = Number(r.qty) || min;
		if (btn.dataset.act === "inc") setQty(r.item_code, qty + 1);
		if (btn.dataset.act === "dec") setQty(r.item_code, Math.max(min, qty - 1));
		if (btn.dataset.act === "rm") remove(r.item_code);
	});
	linesEl.addEventListener("change", (e) => {
		if (e.target.dataset.act !== "qty") return;
		const r = rowOf(e.target);
		if (!r) return;
		const v = parseInt(e.target.value, 10);
		const min = minQty(r.card);
		setQty(r.item_code, isNaN(v) || v < min ? min : v);
	});

	function applyFind() {
		const q = findEl.value.trim().toLowerCase();
		let any = false;
		linesEl.querySelectorAll(".qs-q-row").forEach((el) => {
			el.hidden = !!q && !el.dataset.find.includes(q);
			any = any || !el.hidden;
		});
		linesEl.querySelectorAll(".qs-q-group").forEach((h) => {
			h.hidden = ![...linesEl.querySelectorAll(".qs-q-row")].some((el) => el.dataset.group === h.dataset.group && !el.hidden);
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
			const have = Object.fromEntries(listItems().map((i) => [i.item_code, Number(i.qty) || 0]));
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
			items: rows.map((r) => ({ item_code: r.item_code, qty: Number(r.qty) })),
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
				items: rows.map((x) => ({ item_code: x.item_code, qty: Number(x.qty) })),
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
		sendBtn.disabled = true;
		try {
			await send();
		} catch (e) {
			fail(e.message);
		}
		busy = false;
		sendBtn.disabled = false;
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
