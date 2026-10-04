// Catalog pages (/, /c, /search, /p): card quick-add steppers, header/floating quote counters, product page.
import { __ } from "./i18n.js";
import { initGallery } from "./gallery.js";
import { count, qtyOf, setQty, units } from "./quote_store.js";

const $$ = (sel, root = document) => root.querySelectorAll(sel);
const TIERS = [
	[__("Single piece"), __("Single piece")],
	[__("Multi-piece rate applies"), __("Multi-piece rate")],
	[__("Bulk / dealer rate applies"), __("Bulk rate")],
];

/** Header pill, floating bar and tab badges; runs on every QS page. */
export function initCounts() {
	const render = () => {
		const n = count();
		$$("[data-qs-quote-count]").forEach((el) => (el.textContent = n));
		$$("[data-qs-quote-units]").forEach((el) => (el.textContent = units()));
		$$("[data-qs-word]").forEach((el) => (el.textContent = n === 1 ? el.dataset.one : el.dataset.many));
		$$("[data-qs-quote-bar]").forEach((el) => (el.hidden = !n));
	};
	window.addEventListener("qs:quote-changed", render);
	render();
	// Pages stay cacheable for guests; a signed-in buyer is detected from Frappe's readable user_id cookie.
	const user = /(?:^|; )user_id=([^;]*)/.exec(document.cookie);
	if (user && decodeURIComponent(user[1]) !== "Guest") $$("[data-qs-signin]").forEach((a) => (a.textContent = __("Account")));
}

export function init() {
	initCards();
	initProduct();
	initGallery();
}

function initCards() {
	const cards = $$("[data-qs-card]");
	if (!cards.length) return;
	cards.forEach((card) => {
		const add = card.querySelector("[data-qs-add]");
		add.dataset.label = add.getAttribute("aria-label");
	});
	const sync = () =>
		cards.forEach((card) => {
			const qty = qtyOf(card.dataset.item);
			const add = card.querySelector("[data-qs-add]");
			card.classList.toggle("is-in", qty > 0);
			card.querySelector("[data-qs-qty]").textContent = qty;
			add.setAttribute("aria-label", qty ? __("Increase quantity") : add.dataset.label);
		});
	document.addEventListener("click", (e) => {
		const btn = e.target.closest("[data-qs-add], [data-qs-dec]");
		const card = btn && btn.closest("[data-qs-card]");
		if (!card) return;
		const code = card.dataset.item;
		const min = Number(card.dataset.min) || 1;
		const qty = qtyOf(code);
		if (btn.hasAttribute("data-qs-add")) return setQty(code, qty ? qty + 1 : min);
		setQty(code, qty - 1 < min ? 0 : qty - 1);
		if (!qtyOf(code)) card.querySelector("[data-qs-add]").focus(); // the − button just disappeared
	});
	window.addEventListener("qs:quote-changed", sync);
	sync();
}

function initProduct() {
	const root = document.querySelector("[data-qs-product]");
	if (!root) return;
	const code = root.dataset.item;
	const min = Number(root.dataset.min) || 1;
	const t2 = Number(root.dataset.t2);
	const t3 = Number(root.dataset.t3);
	const toast = document.querySelector("[data-qs-toast]");
	let qty = qtyOf(code) || min;
	let toastTimer;

	const render = () => {
		root.querySelector("[data-qs-qty]").textContent = qty;
		const tier = TIERS[qty >= t3 ? 2 : qty >= t2 ? 1 : 0];
		$$("[data-qs-tier] > span", root).forEach((el, i) => (el.textContent = tier[i]));
		const label = qtyOf(code) ? __("Update quote") : __("Add to quote");
		$$("[data-qs-pd-add]").forEach((b) => (b.textContent = label));
		$$("[data-qs-addon]", root).forEach((a) => {
			const on = qtyOf(a.dataset.item) > 0;
			a.classList.toggle("is-on", on);
			a.querySelector("button").setAttribute("aria-pressed", on);
			a.querySelector("[data-qs-sign]").textContent = on ? "✓" : "+";
		});
	};

	document.addEventListener("click", (e) => {
		const t = e.target;
		if (t.closest("[data-qs-pinc]")) qty += 1;
		else if (t.closest("[data-qs-pdec]")) qty = Math.max(min, qty - 1);
		else if (t.closest("[data-qs-pd-add]")) {
			setQty(code, qty);
			toast.querySelector("[data-qs-toast-text]").textContent = __("Added {0} to your quote", [qty]);
			toast.hidden = false;
			clearTimeout(toastTimer);
			toastTimer = setTimeout(() => (toast.hidden = true), 6000);
		} else {
			const addon = t.closest("[data-qs-addon]");
			if (!addon || t.closest("a")) return;
			const item = addon.dataset.item;
			setQty(item, qtyOf(item) ? 0 : Number(addon.dataset.min) || 1);
			return;
		}
		render();
	});
	window.addEventListener("qs:quote-changed", render);
	render();
}
