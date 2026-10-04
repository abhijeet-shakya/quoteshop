// Theme toggle: <html data-theme> + localStorage "qs-theme" (the inline head script applies it before paint).
const root = document.documentElement;

function sync() {
	const label = root.dataset.theme === "dark" ? "Switch to light mode" : "Switch to dark mode";
	document.querySelectorAll("[data-qs-theme-toggle]").forEach((b) => b.setAttribute("aria-label", label));
}

export function initTheme() {
	document.addEventListener("click", (e) => {
		if (!e.target.closest("[data-qs-theme-toggle]")) return;
		const theme = root.dataset.theme === "dark" ? "light" : "dark";
		root.dataset.theme = theme;
		try {
			localStorage.setItem("qs-theme", theme);
		} catch (err) {
			/* private mode: switch for this page only */
		}
		sync();
	});
	sync();
}
