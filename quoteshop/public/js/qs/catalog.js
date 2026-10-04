// Catalog pages (/, /c, /search, /p): card quick-add steppers, header/floating quote counters, product page.
import { count, qtyOf, setQty, units } from "./quote_store.js";

const $$ = (sel, root = document) => root.querySelectorAll(sel);
const TIERS = [
	["Single piece", "Single piece"],
	["Multi-piece rate applies", "Multi-piece rate"],
	["Bulk / dealer rate applies", "Bulk rate"],
];

/** Header pill, floating bar and tab badges; runs on every QS page. */
export function initCounts() {
	const render = () => {
		const n = count();
		$$("[data-qs-quote-count]").forEach((el) => (el.textContent = n));
		$$("[data-qs-quote-units]").forEach((el) => (el.textContent = units()));
		$$("[data-qs-word]").forEach((el) => (el.textContent = el.dataset.qsWord + (n === 1 ? "" : "s")));
		$$("[data-qs-quote-bar]").forEach((el) => (el.hidden = !n));
	};
	window.addEventListener("qs:quote-changed", render);
	render();
	// Pages stay cacheable for guests; a signed-in buyer is detected from Frappe's readable user_id cookie.
	const user = /(?:^|; )user_id=([^;]*)/.exec(document.cookie);
	if (user && decodeURIComponent(user[1]) !== "Guest") $$("[data-qs-signin]").forEach((a) => (a.textContent = "Account"));
}

export function init() {
	initCards();
	initProduct();
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
			add.setAttribute("aria-label", qty ? "Increase quantity" : add.dataset.label);
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
		const label = qtyOf(code) ? "Update quote" : "Add to quote";
		$$("[data-qs-pd-add]").forEach((b) => (b.textContent = label));
		$$("[data-qs-addon]", root).forEach((a) => {
			const on = qtyOf(a.dataset.item) > 0;
			a.classList.toggle("is-on", on);
			a.querySelector("button").setAttribute("aria-pressed", on);
			a.querySelector("[data-qs-sign]").textContent = on ? "✓" : "+";
		});
	};

	const showPhoto = (i) => {
		const src = root.querySelector(`.qs-thumb[data-qs-thumb="${i}"]`);
		const stage = root.querySelector(".qs-stage-img");
		if (!src || !stage) return;
		stage.removeAttribute("fetchpriority");
		stage.srcset = src.dataset.srcset || "";
		stage.src = src.dataset.src;
		stage.alt = src.dataset.alt;
		$$("[data-qs-photo-n]", root).forEach((el) => (el.textContent = i + 1));
		$$("[data-qs-photo-alt]", root).forEach((el) => (el.textContent = src.dataset.alt));
		$$("[data-qs-thumb]", root).forEach((b) => b.setAttribute("aria-pressed", b.dataset.qsThumb === String(i)));
	};

	document.addEventListener("click", (e) => {
		const t = e.target;
		if (t.closest("[data-qs-pinc]")) qty += 1;
		else if (t.closest("[data-qs-pdec]")) qty = Math.max(min, qty - 1);
		else if (t.closest("[data-qs-pd-add]")) {
			setQty(code, qty);
			toast.querySelector("[data-qs-toast-qty]").textContent = qty;
			toast.hidden = false;
			clearTimeout(toastTimer);
			toastTimer = setTimeout(() => (toast.hidden = true), 6000);
		} else if (t.closest("[data-qs-thumb]")) return showPhoto(Number(t.closest("[data-qs-thumb]").dataset.qsThumb));
		else {
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
