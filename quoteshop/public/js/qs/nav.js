// Header and category navigation on every page: message strip, hide-on-scroll, search row, All categories panel,
// phone menu, the /search filter (tree + bottom sheet), home category rows, and the floating quote bar's idle delay.
import { __ } from "./i18n.js";

const $ = (sel, root = document) => root.querySelector(sel);
const $$ = (sel, root = document) => [...root.querySelectorAll(sel)];
const root = document.documentElement;
const SUB_FIRST = 5; // sub-categories shown per group in the All categories panel before "+ N more"

function el(tag, cls, text) {
	const node = document.createElement(tag);
	if (cls) node.className = cls;
	if (text != null) node.textContent = text;
	return node;
}
function link(cls, route, text) {
	const a = el("a", cls, text);
	a.href = `/c/${encodeURIComponent(route)}`;
	return a;
}
const lock = (on) => root.classList.toggle("qs-lock", on);

// The category tree (cached on the server) is fetched once, on first use.
let treePromise;
function loadTree() {
	treePromise ||= fetch("/api/method/quoteshop.quoteshop_catalog.catalog.get_category_tree", { credentials: "same-origin", headers: { Accept: "application/json" } })
		.then((r) => (r.ok ? r.json() : Promise.reject(new Error(r.status))))
		.then((j) => j.message || [])
		.catch(() => {
			treePromise = null; // try again next time
			return [];
		});
	return treePromise;
}
const matches = (text, q) => text.toLowerCase().includes(q);
const treeCount = (tree) => __("{0} categories · {1} sub-categories", [tree.length, tree.reduce((n, g) => n + g.kids.length, 0)]);

export function initNav() {
	initTop();
	initAnn();
	initSearch();
	initMega();
	initDrawer();
	initFilter();
	initRows();
}

// Down hides the header, up brings it back; transparent over the hero until the page moves. The floating quote bar
// fades while the page is moving and returns after its idle delay.
function initTop() {
	const top = $("[data-qs-top]");
	const bar = $("[data-qs-quote-bar]");
	const idle = Number(bar?.dataset.delay);
	let last = scrollY;
	let hidden = false;
	let idleTimer;
	let ticking = false;
	const panelOpen = () => !!$("[data-qs-spanel]:not([hidden]), [data-qs-mega]:not([hidden])");
	const update = () => {
		ticking = false;
		const y = Math.max(scrollY, 0);
		if (top) {
			if (y - last > 4 && y > 80 && !panelOpen()) hidden = true;
			else if (last - y > 4 || y <= 80 || panelOpen()) hidden = false;
			top.classList.toggle("is-hidden", hidden);
			top.classList.toggle("is-solid", y > 16 || panelOpen());
		}
		if (y !== last && bar) {
			bar.classList.add("is-moving");
			clearTimeout(idleTimer);
			idleTimer = setTimeout(() => bar.classList.remove("is-moving"), Number.isFinite(idle) ? idle : 500);
		}
		last = y;
	};
	addEventListener("scroll", () => ticking || ((ticking = true), requestAnimationFrame(update)), { passive: true });
	window.addEventListener("qs:panel", update);
	update();
}

function initAnn() {
	const box = $("[data-qs-ann]");
	if (!box) return;
	const msgs = $$(".qs-ann-msg", box);
	let i = 0;
	const show = (n) => {
		i = (n + msgs.length) % msgs.length;
		msgs.forEach((m, k) => (m.hidden = k !== i));
	};
	$("[data-qs-ann-prev]", box).addEventListener("click", () => show(i - 1));
	$("[data-qs-ann-next]", box).addEventListener("click", () => show(i + 1));
}

// Search button → the search row under the header (both breakpoints share one form).
function initSearch() {
	const panel = $("[data-qs-spanel]");
	if (!panel) return;
	const btns = $$("[data-qs-search-btn]");
	const set = (on) => {
		panel.hidden = !on;
		btns.forEach((b) => b.setAttribute("aria-expanded", on));
		window.dispatchEvent(new Event("qs:panel"));
	};
	btns.forEach((b) =>
		b.addEventListener("click", () => {
			const on = panel.hidden;
			if (on) window.dispatchEvent(new Event("qs:close-mega"));
			set(on);
			if (on) $("input", panel).focus();
		}),
	);
	$("[data-qs-search-close]", panel).addEventListener("click", () => {
		set(false);
		(btns.find((b) => b.offsetParent) || btns[0]).focus();
	});
	panel.addEventListener("keydown", (e) => e.key === "Escape" && $("[data-qs-search-close]", panel).click());
	window.addEventListener("qs:close-search", () => set(false));
}

// Desktop "All categories": every group with its first sub-categories, find box, "+ N more".
function initMega() {
	const btn = $("[data-qs-mega-btn]");
	const panel = $("[data-qs-mega]");
	if (!btn || !panel) return;
	const grid = $("[data-qs-mega-grid]", panel);
	const find = $("[data-qs-mega-find]", panel);
	const none = $("[data-qs-mega-none]", panel);
	const expanded = new Set();
	let tree = [];
	const render = () => {
		const q = find.value.trim().toLowerCase();
		grid.replaceChildren();
		let shown = 0;
		tree.forEach((g) => {
			const all = !q || matches(g.name, q);
			const kids = all ? g.kids : g.kids.filter((k) => matches(k.name, q));
			if (!all && !kids.length) return;
			shown++;
			const col = el("div", "qs-mg");
			const head = link("qs-mg-h", g.route, g.name);
			head.append(el("span", "", g.count));
			col.append(head);
			const open = q || expanded.has(g.name) ? kids : kids.slice(0, SUB_FIRST);
			open.forEach((k) => col.append(link("qs-mg-k", k.route, k.name)));
			if (kids.length > open.length) {
				const more = el("button", "qs-mg-more", __("+ {0} more", [kids.length - open.length]));
				more.type = "button";
				more.addEventListener("click", () => (expanded.add(g.name), render()));
				col.append(more);
			}
			grid.append(col);
		});
		none.hidden = shown > 0;
	};
	const set = async (on) => {
		panel.hidden = !on;
		btn.setAttribute("aria-expanded", on);
		window.dispatchEvent(new Event("qs:panel"));
		if (!on) return;
		window.dispatchEvent(new Event("qs:close-search"));
		if (!tree.length) {
			tree = await loadTree();
			$$("[data-qs-mega-count]").forEach((c) => (c.textContent = treeCount(tree)));
			render();
		}
		find.focus();
	};
	btn.addEventListener("click", (e) => {
		e.preventDefault();
		set(panel.hidden);
	});
	find.addEventListener("input", render);
	window.addEventListener("qs:close-mega", () => set(false));
	document.addEventListener("click", (e) => !panel.hidden && !e.target.closest("[data-qs-mega], [data-qs-mega-btn]") && set(false));
	document.addEventListener("keydown", (e) => {
		if (e.key === "Escape" && !panel.hidden) {
			set(false);
			btn.focus();
		}
	});
}

// Phone menu: groups → one group's sub-categories (back button); the find box lists matching groups and sub-categories.
function initDrawer() {
	const drawer = $("[data-qs-drawer]");
	if (!drawer) return;
	const l1 = $("[data-qs-menu-l1]", drawer);
	const l2 = $("[data-qs-menu-l2]", drawer);
	const list = $("[data-qs-menu-list]", drawer);
	const kids = $("[data-qs-menu-kids]", drawer);
	const title = $("[data-qs-menu-title]", drawer);
	const find = $("[data-qs-menu-find]", drawer);
	const none = $("[data-qs-menu-none]", drawer);
	const opener = $("[data-qs-menu-open]");
	let tree = [];
	const row = (tag, route, label, side) => {
		const node = route ? link("qs-dr", route, "") : el("button", "qs-dr");
		if (!route) node.type = "button";
		node.append(el("span", "", label), el("span", "", side));
		return node;
	};
	const renderL1 = () => {
		const q = find.value.trim().toLowerCase();
		list.replaceChildren();
		let n = 0;
		tree.forEach((g) => {
			if (!q) {
				// a group without sub-categories opens its page; the others open their sub-category list
				const r = g.kids.length ? row("button", null, g.name, __("{0} groups", [g.kids.length])) : row("a", g.route, g.name, g.count);
				if (g.kids.length) r.addEventListener("click", () => showL2(g));
				list.append(r);
				n++;
				return;
			}
			if (matches(g.name, q)) (list.append(row("a", g.route, g.name, g.count)), n++);
			g.kids.filter((k) => matches(k.name, q)).forEach((k) => (list.append(row("a", k.route, k.name, __("in {0}", [g.name]))), n++));
		});
		none.hidden = n > 0;
	};
	const showL2 = (g) => {
		title.textContent = g.name;
		kids.replaceChildren(row("a", g.route, __("All {0}", [g.name.toLowerCase()]), g.count), ...g.kids.map((k) => row("a", k.route, k.name, k.count)));
		l1.hidden = true;
		l2.hidden = false;
		$("[data-qs-menu-back]", drawer).focus();
	};
	const back = () => {
		l2.hidden = true;
		l1.hidden = false;
	};
	const set = async (on) => {
		drawer.hidden = !on;
		opener?.setAttribute("aria-expanded", on);
		lock(on);
		if (!on) return opener?.focus();
		back();
		$("[data-qs-menu-close]", drawer).focus();
		if (!tree.length) {
			tree = await loadTree();
			$$("[data-qs-mega-count]").forEach((c) => (c.textContent = treeCount(tree)));
			renderL1();
		}
	};
	opener?.addEventListener("click", () => set(true));
	$("[data-qs-menu-close]", drawer).addEventListener("click", () => set(false));
	$("[data-qs-menu-back]", drawer).addEventListener("click", back);
	find.addEventListener("input", renderL1);
	drawer.addEventListener("keydown", (e) => e.key === "Escape" && set(false));
}

// /search and /c: tree toggles, find box, "Show all N categories", phone bottom sheet.
function initFilter() {
	const box = $("[data-qs-filter]");
	if (!box) return;
	const tree = $("[data-qs-ftree]", box);
	const find = $("[data-qs-ffind]", box);
	const none = $("[data-qs-fnone]", box);
	const showAll = $("[data-qs-fshow]", box);
	box.addEventListener("click", (e) => {
		const tog = e.target.closest("[data-qs-ftog]");
		if (!tog) return;
		const open = tog.closest(".qs-fg").classList.toggle("is-open");
		tog.setAttribute("aria-expanded", open);
	});
	let all = false; // "Show all N categories" pressed
	const fit = () => {
		const q = find.value.trim();
		tree.classList.toggle("is-all", all || !!q);
		if (showAll) showAll.hidden = all || !!q;
	};
	showAll?.addEventListener("click", () => {
		all = true;
		fit();
	});
	find.addEventListener("input", () => {
		const q = find.value.trim().toLowerCase();
		fit();
		let any = false;
		$$(".qs-fg", tree).forEach((g) => {
			const byGroup = !q || matches(g.dataset.name, q);
			let byKid = false;
			$$(".qs-fk li", g).forEach((k) => {
				const hit = byGroup || matches(k.dataset.name, q);
				k.hidden = !hit;
				byKid ||= hit;
			});
			g.hidden = !(byGroup || byKid);
			any ||= !g.hidden;
			if (q && !g.hidden) {
				g.classList.add("is-open");
				$("[data-qs-ftog]", g)?.setAttribute("aria-expanded", "true");
			}
		});
		none.hidden = any;
	});
	// phone bottom sheet
	const backdrop = $("[data-qs-filter-close].qs-fback");
	const openBtn = $("[data-qs-filter-open]");
	const set = (on) => {
		box.classList.toggle("is-open", on);
		if (backdrop) backdrop.hidden = !on;
		lock(on);
		if (on) find.focus();
		else openBtn?.focus();
	};
	openBtn?.addEventListener("click", () => set(true));
	$$("[data-qs-filter-close]").forEach((b) => b.addEventListener("click", () => set(false)));
	box.addEventListener("keydown", (e) => e.key === "Escape" && set(false));
}

// Home category rows: arrows (desktop) show only while there is more to scroll in that direction; one page = one view of cards.
function initRows() {
	$$("[data-qs-row]").forEach((wrap) => {
		const track = $("[data-qs-row-track]", wrap);
		const prev = $("[data-qs-row-prev]", wrap);
		const next = $("[data-qs-row-next]", wrap);
		const sync = () => {
			const max = track.scrollWidth - track.clientWidth;
			prev.hidden = max <= 1 || track.scrollLeft <= 1;
			next.hidden = max <= 1 || track.scrollLeft >= max - 1;
		};
		const by = (dir) => track.scrollBy({ left: dir * (track.clientWidth + parseFloat(getComputedStyle(track).columnGap || 0)), behavior: matchMedia("(prefers-reduced-motion: reduce)").matches ? "auto" : "smooth" });
		prev.addEventListener("click", () => by(-1));
		next.addEventListener("click", () => by(1));
		track.addEventListener("scroll", sync, { passive: true });
		new ResizeObserver(sync).observe(track);
		sync();
	});
}
