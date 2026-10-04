// Quote list kept in the browser until submit (CONTRACTS §8): localStorage "qs-quote" = {v: 1, items: [{item_code, qty}]}.
// Every change dispatches window "qs:quote-changed" with {count, units}.
const KEY = "qs-quote";

export function getQuote() {
	try {
		const data = JSON.parse(localStorage.getItem(KEY));
		if (data && data.v === 1 && Array.isArray(data.items)) {
			return { v: 1, items: data.items.filter((i) => i && i.item_code && i.qty > 0) };
		}
	} catch (e) {
		/* corrupt or blocked storage: start empty */
	}
	return { v: 1, items: [] };
}

export function setQty(item_code, qty) {
	const quote = getQuote();
	qty = Math.max(0, Math.floor(Number(qty) || 0));
	const line = quote.items.find((i) => i.item_code === item_code);
	if (qty && line) line.qty = qty;
	else if (qty) quote.items.push({ item_code, qty });
	else quote.items = quote.items.filter((i) => i.item_code !== item_code);
	save(quote);
}

export const remove = (item_code) => setQty(item_code, 0);
export const clear = () => save({ v: 1, items: [] });
export const count = () => getQuote().items.length;
export const units = () => getQuote().items.reduce((sum, i) => sum + i.qty, 0);
export const qtyOf = (item_code) => (getQuote().items.find((i) => i.item_code === item_code) || {}).qty || 0;

function save(quote) {
	try {
		localStorage.setItem(KEY, JSON.stringify({ v: 1, items: quote.items.map(({ item_code, qty }) => ({ item_code, qty })) }));
	} catch (e) {
		/* storage full or blocked: the event still updates this page */
	}
	emit();
}

function emit() {
	window.dispatchEvent(new CustomEvent("qs:quote-changed", { detail: { count: count(), units: units() } }));
}

// another tab changed the list
window.addEventListener("storage", (e) => e.key === KEY && emit());
