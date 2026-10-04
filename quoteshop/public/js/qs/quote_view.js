// /q/<name>?t= – filters, search, collapsible groups, "Show all", accept, change (edits on /quote).
import { __ } from "./i18n.js";
import { call, money, startChange } from "./quote.js";

export function init() {
	const root = document.querySelector("[data-qs-view]");
	if (!root) return;
	const { name, token, currency } = root.dataset;
	const mobile = matchMedia("(max-width: 767px)");
	const shownDesk = parseInt(root.dataset.shown, 10) || 10;
	const groups = [...root.querySelectorAll("[data-qs-group]")].map((el, i) => ({
		el,
		head: el.querySelector(".qs-v-ghead"),
		body: el.querySelector(".qs-v-gbody"),
		rows: [...el.querySelectorAll(".qs-v-row")],
		open: el.dataset.open === "1" && (!mobile.matches || i < 2), // mobile design opens 2 groups
		all: false,
	}));
	const findEl = root.querySelector("[data-qs-find]");
	let filter = "all";

	const match = (row, q) =>
		(filter === "all" || (filter === "changes" && row.dataset.chg) || (filter === "none" && row.dataset.st === "none")) &&
		(!q || row.dataset.find.includes(q));

	function apply() {
		const q = (findEl?.value || "").trim().toLowerCase();
		const shown = mobile.matches ? 5 : shownDesk; // MobileQuoteDetail shows 5 lines per group
		let any = false;
		groups.forEach((g) => {
			const visible = g.rows.filter((r) => match(r, q));
			const open = g.open || filter !== "all" || !!q;
			g.rows.forEach((r) => (r.hidden = true));
			(g.all ? visible : visible.slice(0, shown)).forEach((r) => (r.hidden = false));
			g.el.hidden = !visible.length;
			g.body.hidden = !open;
			g.head.setAttribute("aria-expanded", String(open));
			g.head.querySelector(".qs-v-arrow").textContent = open ? "−" : "+";
			g.el.querySelectorAll("[data-qs-gcount]").forEach((c) => (c.textContent = visible.length));
			g.el.querySelector("[data-qs-gsub]").textContent = money(visible.reduce((s, r) => s + (parseFloat(r.dataset.amount) || 0), 0), currency);
			g.el.querySelector("[data-qs-showall]").hidden = g.all || visible.length <= shown;
			any = any || visible.length > 0;
		});
		const none = root.querySelector("[data-qs-nomatch]");
		if (none) none.hidden = any;
	}

	groups.forEach((g) => {
		g.head.addEventListener("click", () => {
			g.open = g.head.getAttribute("aria-expanded") !== "true";
			apply();
		});
		g.el.querySelector("[data-qs-showall]").addEventListener("click", () => {
			g.all = true;
			apply();
			g.rows.find((r) => !r.hidden)?.scrollIntoView({ block: "nearest" });
		});
	});
	findEl?.addEventListener("input", apply);
	root.querySelectorAll("[data-qs-filter]").forEach((b) =>
		b.addEventListener("click", () => {
			filter = b.dataset.qsFilter;
			root.querySelectorAll("[data-qs-filter]").forEach((x) => x.setAttribute("aria-pressed", String(x === b)));
			apply();
		}),
	);

	mobile.addEventListener("change", apply);
	apply();

	const errEl = root.querySelector("[data-qs-error]");
	const acceptBtn = root.querySelector("[data-qs-accept]");
	acceptBtn?.addEventListener("click", async () => {
		acceptBtn.disabled = true;
		errEl.hidden = true;
		try {
			await call("quote_view.accept_quote", { name, token });
			root.querySelectorAll("[data-qs-actions] > :not([data-qs-accepted])").forEach((el) => (el.hidden = true));
			root.querySelector("[data-qs-accepted]").hidden = false;
			root.querySelectorAll("[data-qs-status]").forEach((s) => {
				s.textContent = __("Accepted");
				s.className = s.className.replace(/qs-v-tone-\w+/, "qs-v-tone-accent");
			});
		} catch (e) {
			errEl.textContent = e.message;
			errEl.hidden = false;
			acceptBtn.disabled = false;
		}
	});

	root.querySelector("[data-qs-change]")?.addEventListener("click", () => {
		const items = JSON.parse(root.querySelector("[data-qs-change-items]")?.textContent || "[]");
		startChange({ name, token, version: root.dataset.version }, items);
	});
}
