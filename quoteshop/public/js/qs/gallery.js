// Product page photo gallery (Item.dc.html / MobileItem.dc.html): rail or swipe track + full-screen viewer.
// All markup and strings come from www/p.html; this only moves state around.
const RAIL = 6; // desktop rail length; photo RAIL (and later) hide behind the "+N" tile
const mobile = matchMedia("(max-width: 767px)");

export function initGallery() {
	const root = document.querySelector("[data-qs-gallery]");
	const viewer = document.querySelector("[data-qs-viewer]");
	const slides = root ? [...root.querySelectorAll("[data-qs-slide]")] : [];
	const n = slides.length;
	if (!n) return;

	const $ = (sel) => viewer.querySelector(sel);
	const thumbs = [...document.querySelectorAll("[data-qs-gallery] [data-qs-thumb], [data-qs-viewer] [data-qs-thumb]")];
	const more = root.querySelector("[data-qs-more]");
	const vimg = $("[data-qs-vimg]");
	const zoomBtn = $("[data-qs-zoom]");
	const hint = $("[data-qs-zoomhint]");
	const tip = $("[data-qs-tip]");
	let idx = 0;
	let zoom = false;
	let opener = null;
	let moved = false; // a swipe must not also open the viewer
	let sx, sy;

	const centre = (btn) => {
		const row = btn.parentElement;
		if (row.scrollWidth <= row.clientWidth) return;
		const r = btn.getBoundingClientRect();
		const c = row.getBoundingClientRect();
		row.scrollTo({ left: row.scrollLeft + r.left + r.width / 2 - (c.left + c.width / 2), behavior: "smooth" });
	};

	const setZoom = (on) => {
		zoom = on;
		viewer.classList.toggle("is-zoomed", on);
		zoomBtn.setAttribute("aria-pressed", on);
		if (hint) hint.textContent = on ? hint.dataset.zoomed : hint.dataset.idle;
	};

	const render = () => {
		root.querySelector("[data-qs-track]").style.transform = `translateX(${-idx * 100}%)`;
		slides.forEach((s, i) => {
			s.inert = i !== idx;
			// slides start lazy; load the ones the visitor can reach next
			if (Math.abs(i - idx) <= 1) s.querySelector("img").loading = "eager";
		});
		document.querySelectorAll("[data-qs-n]").forEach((el) => (el.textContent = idx + 1));
		document.querySelectorAll("[data-qs-label]").forEach((el) => (el.textContent = slides[idx].dataset.label));
		thumbs.forEach((b) => b.setAttribute("aria-pressed", Number(b.dataset.qsThumb) === idx));
		if (more) more.classList.toggle("is-on", idx >= RAIL);
		if (!viewer.hidden) vimg.src = slides[idx].dataset.large;
		vimg.alt = slides[idx].dataset.label;
		thumbs.filter((b) => b.getAttribute("aria-pressed") === "true" && b.offsetParent).forEach(centre);
	};

	const go = (i) => {
		const next = mobile.matches ? Math.max(0, Math.min(n - 1, i)) : (i + n) % n; // swipe stops at the ends, arrows wrap
		if (next !== idx) setZoom(false);
		idx = next;
		render();
	};

	// ---- viewer: focus lives inside, Tab is trapped, page scroll is locked ----
	const focusable = () => [...viewer.querySelectorAll("button")].filter((b) => b.getClientRects().length);
	const open = (from) => {
		opener = from;
		const gap = window.innerWidth - document.documentElement.clientWidth;
		document.body.style.overflow = "hidden";
		if (gap > 0) document.body.style.paddingRight = `${gap}px`;
		viewer.hidden = false;
		setZoom(false);
		render();
		$("[data-qs-close]").focus();
		document.addEventListener("keydown", onKey);
		document.addEventListener("focusin", onFocus);
	};
	const close = () => {
		viewer.hidden = true;
		document.body.style.overflow = document.body.style.paddingRight = "";
		document.removeEventListener("keydown", onKey);
		document.removeEventListener("focusin", onFocus);
		// the opener may be a slide that is inert now: go to the current one
		const back = opener && opener.closest("[data-qs-slide]") ? slides[idx] : opener;
		(back && !back.inert ? back : slides[idx]).focus();
	};
	const onFocus = (e) => {
		if (!viewer.contains(e.target)) $("[data-qs-close]").focus();
	};
	const onKey = (e) => {
		if (e.key === "Escape") close();
		else if (e.key === "ArrowLeft" && n > 1) go(idx - 1);
		else if (e.key === "ArrowRight" && n > 1) go(idx + 1);
		else if (e.key === "Tab") {
			const f = focusable();
			const at = f.indexOf(document.activeElement);
			const to = e.shiftKey ? (at <= 0 ? f.length - 1 : at - 1) : at === f.length - 1 ? 0 : at + 1;
			f[to].focus();
		} else return;
		e.preventDefault();
	};

	// ---- page gallery ----
	root.addEventListener("click", (e) => {
		const t = e.target.closest("button");
		if (!t) return;
		if (t.hasAttribute("data-qs-slide")) {
			if (moved) moved = false;
			else open(t);
		} else if (t.hasAttribute("data-qs-more")) {
			idx = RAIL;
			open(t);
		} else if (t.hasAttribute("data-qs-thumb")) go(Number(t.dataset.qsThumb));
		else if (t.hasAttribute("data-qs-prev")) go(idx - 1);
		else if (t.hasAttribute("data-qs-next")) go(idx + 1);
	});
	root.addEventListener("keydown", (e) => {
		if (n > 1 && (e.key === "ArrowLeft" || e.key === "ArrowRight")) go(idx + (e.key === "ArrowLeft" ? -1 : 1));
	});
	const stage = root.querySelector(".qs-stage");
	stage.addEventListener("pointerdown", (e) => {
		sx = e.clientX;
		moved = false;
	});
	stage.addEventListener("pointerup", (e) => {
		if (!mobile.matches || n < 2) return;
		const dx = e.clientX - (sx ?? e.clientX);
		if (Math.abs(dx) > 8) moved = true;
		if (dx < -40) go(idx + 1);
		else if (dx > 40) go(idx - 1);
	});

	// ---- viewer controls ----
	viewer.addEventListener("click", (e) => {
		const t = e.target.closest("button");
		if (!t) return;
		if (t.hasAttribute("data-qs-close")) close();
		else if (t.hasAttribute("data-qs-prev")) go(idx - 1);
		else if (t.hasAttribute("data-qs-next")) go(idx + 1);
		else if (t.hasAttribute("data-qs-thumb")) go(Number(t.dataset.qsThumb));
		else if (t.hasAttribute("data-qs-zoom") && (!mobile.matches || e.detail === 0)) toggleZoom(); // phones: double-tap (detail 0 = keyboard / assistive tech)
	});
	const toggleZoom = () => {
		setZoom(!zoom);
		if (tip) tip.hidden = true;
	};
	const vmain = $("[data-qs-vmain]");
	vmain.addEventListener("dblclick", () => mobile.matches && toggleZoom());
	vmain.addEventListener("pointerdown", (e) => {
		sx = e.clientX;
		sy = e.clientY;
	});
	vmain.addEventListener("pointerup", (e) => {
		if (!mobile.matches) return;
		const dx = e.clientX - (sx ?? e.clientX);
		const dy = e.clientY - (sy ?? e.clientY);
		if (dy > 90 && Math.abs(dx) < 60) close();
		else if (zoom || n < 2) return;
		else if (dx < -50) go(idx + 1);
		else if (dx > 50) go(idx - 1);
	});
}
