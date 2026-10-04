// /account – WhatsApp OTP sign-in (guest), tabs, expandable orders, reorder into the quote list.
import { call, fillQuote, normaliseMobile } from "./quote.js";

export function init() {
	const root = document.querySelector("[data-qs-account]");
	if (!root) return;
	const errEl = root.querySelector("[data-qs-error]");
	const fail = (msg, field) => {
		errEl.textContent = msg;
		errEl.hidden = false;
		field?.focus();
	};

	// ---- guest sign-in ----
	const loginBtn = root.querySelector("[data-qs-login]");
	if (loginBtn) {
		const mobileEl = root.querySelector("[data-qs-login-mobile]");
		const otpBox = root.querySelector("[data-qs-login-otp]");
		const otpEl = otpBox.querySelector("input");
		let sentTo = null;
		loginBtn.addEventListener("click", async () => {
			errEl.hidden = true;
			const mobile = normaliseMobile(mobileEl.value);
			if (!mobile) return fail("Please enter a valid WhatsApp number.", mobileEl);
			loginBtn.disabled = true;
			try {
				if (sentTo !== mobile) {
					await call("api.send_otp", { mobile });
					sentTo = mobile;
					otpBox.hidden = false;
					otpBox.querySelector("[data-qs-otp-to]").textContent = mobile;
					loginBtn.textContent = loginBtn.dataset.labelVerify;
					otpEl.focus();
				} else {
					const otp = otpEl.value.replace(/\D/g, "");
					if (otp.length !== 6) throw Object.assign(new Error("Please enter the 6-digit code."), { field: otpEl });
					const { otp_token } = await call("api.verify_otp", { mobile, otp });
					const r = await call("portal.portal_login", { mobile, otp_token });
					location.href = root.dataset.next !== "/account" ? root.dataset.next : r?.redirect || "/account";
					return;
				}
			} catch (e) {
				fail(e.message, e.field);
			}
			loginBtn.disabled = false;
		});
		return;
	}

	// ---- tabs ----
	const tabs = [...root.querySelectorAll("[data-qs-tab]")];
	const pick = (tab) => {
		tabs.forEach((t) => {
			const on = t === tab;
			t.setAttribute("aria-selected", String(on));
			t.tabIndex = on ? 0 : -1;
			root.querySelector(`[data-qs-panel="${t.dataset.qsTab}"]`).hidden = !on;
		});
	};
	tabs.forEach((t, i) => {
		t.addEventListener("click", () => pick(t));
		t.addEventListener("keydown", (e) => {
			const step = { ArrowRight: 1, ArrowDown: 1, ArrowLeft: -1, ArrowUp: -1 }[e.key];
			if (!step) return;
			e.preventDefault();
			const next = tabs[(i + step + tabs.length) % tabs.length];
			pick(next);
			next.focus();
		});
	});

	// ---- order details ----
	root.querySelectorAll("[data-qs-order-toggle]").forEach((b) =>
		b.addEventListener("click", () => {
			const open = b.getAttribute("aria-expanded") !== "true";
			b.setAttribute("aria-expanded", String(open));
			document.getElementById(b.getAttribute("aria-controls")).hidden = !open;
			if (b.dataset.hide) b.textContent = open ? b.dataset.hide : b.dataset.show;
		}),
	);

	// ---- reorder ----
	root.querySelectorAll("[data-qs-reorder]").forEach((b) =>
		b.addEventListener("click", async () => {
			b.disabled = true;
			errEl.hidden = true;
			try {
				const r = await call("portal.reorder", { sales_order: b.dataset.qsReorder });
				fillQuote(r?.items || []);
				location.href = "/quote";
			} catch (e) {
				fail(e.message);
				b.disabled = false;
			}
		}),
	);
}
