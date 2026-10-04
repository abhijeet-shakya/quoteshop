// Catalog pages (/, /c, /search, /p): card quick-add steppers, header/floating quote counters, product page.
import { __ } from "./i18n.js";
import { initGallery } from "./gallery.js";
import { count, getQuote, qtyOf, setQty, units } from "./quote_store.js";

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
}

export function init() {
	initPromos();
	initCards();
	initGallery();
	initProduct();
}

// Offers row: prev/next arrows (desktop) show only while there is more to scroll in that direction.
function initPromos() {
	const wrap = document.querySelector("[data-qs-promos]");
	const row = wrap && wrap.querySelector("[data-qs-promos-row]");
	if (!row) return;
	const prev = wrap.querySelector("[data-qs-promos-prev]");
	const next = wrap.querySelector("[data-qs-promos-next]");
	const sync = () => {
		const max = row.scrollWidth - row.clientWidth;
		prev.hidden = max <= 1 || row.scrollLeft <= 1;
		next.hidden = max <= 1 || row.scrollLeft >= max - 1;
	};
	const by = (dir) => {
		const tile = [...row.querySelectorAll(".qs-promo")].find((t) => t.offsetWidth);
		const step = (tile ? tile.offsetWidth : row.clientWidth) + parseFloat(getComputedStyle(row).columnGap || 0);
		row.scrollBy({ left: dir * step, behavior: matchMedia("(prefers-reduced-motion: reduce)").matches ? "auto" : "smooth" });
	};
	prev.addEventListener("click", () => by(-1));
	next.addEventListener("click", () => by(1));
	row.addEventListener("scroll", sync, { passive: true });
	new ResizeObserver(sync).observe(row);
	sync();
}

function initCards() {
	const cards = [...$$("[data-qs-card]")].filter((card) => card.querySelector("[data-qs-add]")); // cards without colour data only link
	if (!cards.length) return;
	cards.forEach((card) => {
		const add = card.querySelector("[data-qs-add]");
		add.dataset.label = add.getAttribute("aria-label");
		const img = card.querySelector(".qs-tile > img");
		if (img) Object.assign(img.dataset, { src: img.getAttribute("src"), srcset: img.getAttribute("srcset") || "", alt: img.alt }); // the general photo
		const link = card.querySelector(".qs-card-name");
		if (link) link.dataset.href = link.getAttribute("href");
	});
	// a card's colour = its checked swatch ("" for items without colours); the stepper is for that (item, colour) line
	const colourOf = (card) => card.querySelector("[data-qs-colours] input:checked")?.value || "";
	const sync = () => {
		const items = getQuote().items;
		cards.forEach((card) => {
			const code = card.dataset.item;
			const qty = qtyOf(code, colourOf(card));
			const add = card.querySelector("[data-qs-add]");
			card.classList.toggle("is-in", items.some((i) => i.item_code === code)); // any colour of the item
			card.classList.toggle("is-qty", qty > 0);
			card.querySelector("[data-qs-qty]").textContent = qty;
			add.setAttribute("aria-label", qty ? __("Increase quantity") : add.dataset.label);
		});
	};
	document.addEventListener("click", (e) => {
		const btn = e.target.closest("[data-qs-add], [data-qs-dec]");
		const card = btn && btn.closest("[data-qs-card]");
		if (!card) return;
		const code = card.dataset.item;
		const colour = colourOf(card);
		const min = Number(card.dataset.min) || 1;
		const qty = qtyOf(code, colour);
		if (btn.hasAttribute("data-qs-add")) return setQty(code, qty ? qty + 1 : min, colour);
		setQty(code, qty - 1 < min ? 0 : qty - 1, colour);
		if (!qtyOf(code, colour)) card.querySelector("[data-qs-add]").focus(); // the − button just disappeared
	});
	// choosing a colour: swap the tile photo (that colour's, else the general one), carry ?colour= in the link
	document.addEventListener("change", (e) => {
		const radio = e.target.closest?.("[data-qs-colours] input");
		const card = radio && radio.closest("[data-qs-card]");
		if (!card) return;
		const img = card.querySelector(".qs-tile > img");
		if (img) {
			const d = radio.dataset.src ? radio.dataset : img.dataset;
			img.src = d.src;
			if (d.srcset) img.srcset = d.srcset;
			else img.removeAttribute("srcset");
			img.alt = d.alt;
		}
		const link = card.querySelector(".qs-card-name");
		if (link) link.href = `${link.dataset.href}?colour=${encodeURIComponent(radio.value)}`;
		sync();
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
	const swatches = root.querySelector("[data-qs-colours]");
	let colour = root.dataset.colour || "";
	let qty = qtyOf(code, colour) || min;
	let toastTimer;

	const render = () => {
		root.querySelector("[data-qs-qty]").textContent = qty;
		const tier = TIERS[qty >= t3 ? 2 : qty >= t2 ? 1 : 0];
		$$("[data-qs-tier] > span", root).forEach((el, i) => (el.textContent = tier[i]));
		const label = qtyOf(code, colour) ? __("Update quote") : __("Add to quote");
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
			setQty(code, qty, colour);
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
	// colour swatches: name, ?colour= and the gallery order follow the chosen radio (CONTRACTS §11)
	const pick = (value) => {
		colour = value;
		root.querySelector("[data-qs-colour-name]").textContent = value;
		const url = new URL(location.href);
		url.searchParams.set("colour", value);
		history.replaceState(null, "", url);
		qty = qtyOf(code, colour) || qty;
		window.dispatchEvent(new CustomEvent("qs:colour", { detail: { colour: value } }));
		render();
	};
	swatches?.addEventListener("change", (e) => pick(e.target.value));
	const checked = swatches?.querySelector("input:checked");
	if (checked && checked.value !== colour) pick(checked.value); // browser restored another choice after reload/back
	window.addEventListener("qs:quote-changed", render);
	render();
}
