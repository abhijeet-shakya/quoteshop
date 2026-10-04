// Quote list kept in the browser until submit (CONTRACTS §8, §11): localStorage "qs-quote" =
// {v: 1, items: [{item_code, qty, colour?}]}; a line is identified by (item_code, colour), colour "" = none.
// Every change dispatches window "qs:quote-changed" with {count, units} (lines, pieces).
const KEY = "qs-quote";

const colourOf = (i) => (typeof i.colour === "string" ? i.colour : "");
const find = (quote, code, colour) => quote.items.find((i) => i.item_code === code && colourOf(i) === colour);

export function getQuote() {
	try {
		const data = JSON.parse(localStorage.getItem(KEY));
		if (data && data.v === 1 && Array.isArray(data.items)) {
			const items = data.items.filter((i) => i && i.item_code && i.qty > 0);
			return { v: 1, items: items.map((i) => (colourOf(i) ? { item_code: i.item_code, qty: i.qty, colour: i.colour } : { item_code: i.item_code, qty: i.qty })) };
		}
	} catch (e) {
		/* corrupt or blocked storage: start empty */
	}
	return { v: 1, items: [] };
}

export function setQty(item_code, qty, colour = "") {
	const quote = getQuote();
	qty = Math.max(0, Math.floor(Number(qty) || 0));
	const line = find(quote, item_code, colour);
	if (qty && line) line.qty = qty;
	else if (qty) quote.items.push(colour ? { item_code, qty, colour } : { item_code, qty });
	else quote.items = quote.items.filter((i) => i !== line);
	save(quote);
}

// Move a line to another colour; when that (item, colour) line exists the two merge (quantities add up).
export function recolour(item_code, from, to) {
	const quote = getQuote();
	const line = find(quote, item_code, from);
	if (!line || from === to) return;
	const target = find(quote, item_code, to);
	if (target) {
		target.qty += line.qty;
		quote.items = quote.items.filter((i) => i !== line);
	} else if (to) line.colour = to;
	else delete line.colour;
	save(quote);
}

export const remove = (item_code, colour = "") => setQty(item_code, 0, colour);
export const clear = () => save({ v: 1, items: [] });
export const count = () => getQuote().items.length;
export const units = () => getQuote().items.reduce((sum, i) => sum + i.qty, 0);
export const qtyOf = (item_code, colour = "") => (find(getQuote(), item_code, colour) || {}).qty || 0;

function save(quote) {
	try {
		localStorage.setItem(KEY, JSON.stringify({ v: 1, items: quote.items.map(({ item_code, qty, colour }) => (colour ? { item_code, qty, colour } : { item_code, qty })) }));
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
