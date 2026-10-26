(function () {
	const THEME_STORAGE_KEY = "gris-theme";
	const LIGHT_THEME = "light";
	const DARK_THEME = "dark";
	const DEFAULT_THEME = LIGHT_THEME;
	const THEME_META_COLORS = Object.freeze({
		light: "#FFFFFF",
		dark: "#1B1D21",
	});

	function ensureBasecoatObserver() {
		if (window.basecoat && typeof window.basecoat.start === "function") {
			window.basecoat.start();
		}
	}

	function ensureToasterContainer() {
		if (!document.body || document.getElementById("toaster")) {
			return;
		}

		const toaster = document.createElement("div");
		toaster.id = "toaster";
		toaster.className = "toaster";
		document.body.appendChild(toaster);
	}

	const ALERT_CATEGORIES = Object.freeze({
		green: "success",
		red: "error",
		orange: "warning",
		yellow: "warning",
	});

	function escapeHtml(value) {
		const div = document.createElement("div");
		div.textContent = String(value ?? "");
		return div.innerHTML;
	}

	// Mensagem de erro vinda do servidor costuma explicar o que fazer: fica mais tempo na tela.
	const MSGPRINT_ERROR_DURATION = 8000;

	// Converte o HTML de uma mensagem em texto. O DOMParser monta um documento inerte
	// (nada de <img onerror> executando); quebras de linha e itens de lista são mantidos.
	function htmlToText(html) {
		const doc = new DOMParser().parseFromString(String(html ?? ""), "text/html");
		doc.querySelectorAll("br").forEach((br) => br.replaceWith("\n"));
		doc.querySelectorAll("li").forEach((li) => {
			li.prepend("• ");
			li.append("\n");
		});
		doc.querySelectorAll("p, div, tr").forEach((element) => element.append("\n"));
		return (doc.body.textContent || "").replace(/\n{2,}/g, "\n").trim();
	}

	function textToHtml(text) {
		return escapeHtml(text).replace(/\n/g, "<br>");
	}

	// Um <dialog> aberto com showModal() fica na top layer e cobriria o toast. Enquanto
	// houver um aberto, o toaster entra na top layer como popover; reabri-lo a cada toast
	// o põe acima do diálogo mais recente. Os estilos de [popover] são anulados em layout.css.
	function keepToasterAboveModal(toaster) {
		if (typeof toaster.showPopover !== "function") {
			return;
		}

		try {
			if (!document.querySelector("dialog:modal")) {
				toaster.removeAttribute("popover");
				return;
			}
			if (!toaster.hasAttribute("popover")) {
				toaster.setAttribute("popover", "manual");
			}
			if (toaster.matches(":popover-open")) {
				toaster.hidePopover();
			}
			toaster.showPopover();
		} catch (error) {
			// Navegador sem :modal ou Popover API: o toast aparece, só que atrás do diálogo.
		}
	}

	function showToast(config) {
		ensureToasterContainer();
		const toaster = document.getElementById("toaster");
		if (toaster) {
			keepToasterAboveModal(toaster);
		}
		document.dispatchEvent(new CustomEvent("basecoat:toast", { detail: { config } }));
	}

	/*
	 * APIs de diálogo do Desk no portal.
	 *
	 * frappe.show_alert, frappe.msgprint e frappe.confirm montam um modal Bootstrap, mas o
	 * portal não carrega o CSS do Desk: o botão de fechar vira um X gigante e a mensagem fica
	 * largada no rodapé da página. Cada uma é redirecionada para o componente equivalente do
	 * design system, preservando a assinatura original — inclusive o `frappe.call` do portal,
	 * que exibe o `frappe.throw` do servidor via frappe.msgprint.
	 *
	 * Ao usar outra API de diálogo do Desk numa página do portal, crie o shim aqui e registre-o
	 * em `PORTAL_SHIMS` de scripts/checks/portal_sem_dialogo_desk.py (pre-commit e testes).
	 */

	function showAlertAsToast(message, seconds) {
		const options = message && typeof message === "object" ? message : { message };
		const duration = Number(seconds || options.seconds || 0) * 1000;
		showToast({
			category: ALERT_CATEGORIES[options.indicator] || "info",
			description: escapeHtml(options.message),
			...(duration > 0 ? { duration } : {}),
		});
	}

	function parseMsgprintArgs(msg, title) {
		if (msg && typeof msg === "object" && !Array.isArray(msg)) {
			return { ...msg };
		}
		if (typeof msg === "string" && msg.trim().startsWith("{")) {
			try {
				return JSON.parse(msg);
			} catch (error) {
				// Não era JSON: segue como texto.
			}
		}
		return { message: msg, title };
	}

	function showMsgprintAsToast(msg, title) {
		if (!msg) {
			return;
		}

		// O servidor manda uma lista (`_server_messages`); havendo exceção, só ela importa.
		if (Array.isArray(msg)) {
			const messages = msg.map((item) => parseMsgprintArgs(item));
			const exceptions = messages.filter((item) => item.raise_exception);
			(exceptions.length ? exceptions : messages).forEach((item) =>
				showMsgprintAsToast(item)
			);
			return;
		}

		const data = parseMsgprintArgs(msg, title);
		if (Array.isArray(data.message)) {
			if (data.as_list) {
				data.message = data.message.map((item) => `<li>${item}</li>`).join("");
			} else if (data.as_table) {
				data.message = data.message.map((row) => [].concat(row).join(" · ")).join("<br>");
			} else {
				showMsgprintAsToast(data.message);
				return;
			}
		}

		if (data.alert || data.toast) {
			window.frappe.show_alert(data);
			return;
		}

		const text = htmlToText(data.message);
		if (!text) {
			return;
		}

		const category = ALERT_CATEGORIES[data.indicator] || "info";
		showToast({
			category,
			description: textToHtml(text),
			...(category === "error" ? { duration: MSGPRINT_ERROR_DURATION } : {}),
		});
	}

	function confirmAsDialog(message, ifYes, ifNo) {
		const dialog = document.createElement("dialog");
		dialog.className = "dialog";
		dialog.setAttribute("aria-labelledby", "grisConfirmTitulo");
		dialog.innerHTML = `
			<div>
				<header><h2 id="grisConfirmTitulo">Confirmar</h2></header>
				<section><p class="text-sm"></p></section>
				<footer>
					<button type="button" class="btn-outline" data-confirm="nao">Cancelar</button>
					<button type="button" class="btn" data-confirm="sim">Confirmar</button>
				</footer>
			</div>
		`;
		dialog.querySelector("p").innerHTML = textToHtml(htmlToText(message));

		let confirmed = false;
		dialog.addEventListener("click", (event) => {
			const button = event.target.closest("[data-confirm]");
			if (button) {
				confirmed = button.dataset.confirm === "sim";
				dialog.close();
			} else if (event.target === dialog) {
				dialog.close();
			}
		});
		// `close` também cobre o Esc: sem clicar em Confirmar, conta como "não".
		dialog.addEventListener("close", () => {
			dialog.remove();
			const callback = confirmed ? ifYes : ifNo;
			if (typeof callback === "function") {
				callback();
			}
		});

		document.body.appendChild(dialog);
		dialog.showModal();
		dialog.querySelector('[data-confirm="sim"]').focus();
		return dialog;
	}

	function overrideFrappeDialogs() {
		if (!window.frappe) {
			return;
		}

		window.frappe.show_alert = showAlertAsToast;
		window.frappe.msgprint = showMsgprintAsToast;
		window.msgprint = showMsgprintAsToast;
		window.frappe.confirm = confirmAsDialog;
	}

	function getThemeRoot() {
		return document.documentElement;
	}

	function normalizeTheme(theme) {
		return theme === DARK_THEME ? DARK_THEME : LIGHT_THEME;
	}

	function readStoredTheme() {
		try {
			const storedTheme = window.localStorage.getItem(THEME_STORAGE_KEY);
			if (storedTheme === LIGHT_THEME || storedTheme === DARK_THEME) {
				return storedTheme;
			}
		} catch (error) {
			return null;
		}

		return null;
	}

	function writeStoredTheme(theme) {
		try {
			window.localStorage.setItem(THEME_STORAGE_KEY, theme);
		} catch (error) {
			// Ignore storage failures and keep the active theme in memory only.
		}
	}

	function syncThemeMeta(theme) {
		const color = THEME_META_COLORS[theme] || THEME_META_COLORS[DEFAULT_THEME];
		document
			.querySelectorAll('meta[name="theme-color"], meta[name="msapplication-TileColor"]')
			.forEach((element) => {
				element.setAttribute("content", color);
			});
	}

	function syncThemeAffordances(theme) {
		const isDark = theme === DARK_THEME;

		document.querySelectorAll("[data-theme-dark-icon]").forEach((element) => {
			element.hidden = isDark;
		});

		document.querySelectorAll("[data-theme-light-icon]").forEach((element) => {
			element.hidden = !isDark;
		});

		document.querySelectorAll("[data-theme-toggle-label]").forEach((element) => {
			const lightText = element.dataset.themeLightText || "Tema escuro";
			const darkText = element.dataset.themeDarkText || "Tema claro";
			element.textContent = isDark ? darkText : lightText;
		});

		document.querySelectorAll("[data-theme-toggle-item]").forEach((element) => {
			const nextLabel = isDark
				? element.dataset.themeDarkLabel || "Ativar tema claro"
				: element.dataset.themeLightLabel || "Ativar tema escuro";

			element.setAttribute("aria-label", nextLabel);
			element.setAttribute("title", nextLabel);

			if (element.hasAttribute("data-tooltip")) {
				element.setAttribute("data-tooltip", nextLabel);
			}
		});
	}

	function getTheme() {
		return getThemeRoot().classList.contains("dark") ? DARK_THEME : LIGHT_THEME;
	}

	function applyTheme(theme, options = {}) {
		const nextTheme = normalizeTheme(theme);
		const root = getThemeRoot();

		root.classList.toggle("dark", nextTheme === DARK_THEME);
		root.dataset.theme = nextTheme;

		if (options.persist !== false) {
			writeStoredTheme(nextTheme);
		}

		syncThemeMeta(nextTheme);
		syncThemeAffordances(nextTheme);

		if (options.emit !== false) {
			document.dispatchEvent(
				new CustomEvent("gris:theme-change", {
					detail: {
						theme: nextTheme,
						isDark: nextTheme === DARK_THEME,
					},
				})
			);
		}

		return nextTheme;
	}

	function initializeTheme() {
		applyTheme(readStoredTheme() || DEFAULT_THEME, {
			emit: false,
			persist: false,
		});
	}

	function toggleTheme() {
		return applyTheme(getTheme() === DARK_THEME ? LIGHT_THEME : DARK_THEME);
	}

	function initializeDesignSystem() {
		initializeTheme();
		ensureToasterContainer();
		ensureBasecoatObserver();
		overrideFrappeDialogs();
	}

	// Basecoat already auto-initializes on DOMContentLoaded and watches future DOM insertions.
	// Re-running initAll on load duplicates event listeners for interactive components.
	document.addEventListener("basecoat:theme", toggleTheme);

	if (document.readyState === "loading") {
		document.addEventListener("DOMContentLoaded", initializeDesignSystem, { once: true });
	} else {
		initializeDesignSystem();
	}

	document.addEventListener("gris:design-system:init", ensureBasecoatObserver);

	window.grisDesignSystem = Object.freeze({
		getTheme,
		initAll: ensureBasecoatObserver,
		setTheme: applyTheme,
		toggleTheme,
	});
})();
