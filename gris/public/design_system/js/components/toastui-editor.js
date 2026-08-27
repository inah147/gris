(function (global) {
	"use strict";

	var VENDOR_BASE = "/assets/gris/vendor/toastui-editor";
	var CSS_HREF = VENDOR_BASE + "/toastui-editor.min.css";
	var CSS_DARK_HREF = VENDOR_BASE + "/toastui-editor-dark.min.css";
	var JS_SRC = VENDOR_BASE + "/toastui-editor-all.min.js";
	var I18N_SRC = VENDOR_BASE + "/i18n/pt-br.min.js";

	var DARK_CLASS = "toastui-editor-dark";
	var DARK_SCOPE_SELECTOR =
		".toastui-editor-defaultUI, .toastui-editor-md-mode, .toastui-editor-ww-mode, .toastui-editor-popup, .toastui-editor-context-menu";

	var loadPromise = null;
	var instances = [];
	var themeListenerBound = false;

	function isDarkMode() {
		return document.documentElement.classList.contains("dark");
	}

	function ensureCss(href, marker) {
		if (document.querySelector('link[data-gris-toastui="' + marker + '"]')) return;
		var link = document.createElement("link");
		link.rel = "stylesheet";
		link.href = href;
		link.dataset.grisToastui = marker;
		document.head.appendChild(link);
	}

	function loadScript(src, marker) {
		return new Promise(function (resolve, reject) {
			var existing = document.querySelector('script[data-gris-toastui="' + marker + '"]');
			if (existing) {
				if (existing.dataset.loaded === "1") {
					resolve();
				} else {
					existing.addEventListener(
						"load",
						function () {
							resolve();
						},
						{ once: true }
					);
					existing.addEventListener(
						"error",
						function () {
							reject(new Error("Falha ao carregar " + src));
						},
						{ once: true }
					);
				}
				return;
			}
			var script = document.createElement("script");
			script.src = src;
			script.async = false;
			script.dataset.grisToastui = marker;
			script.onload = function () {
				script.dataset.loaded = "1";
				resolve();
			};
			script.onerror = function () {
				reject(new Error("Falha ao carregar " + src));
			};
			document.head.appendChild(script);
		});
	}

	function applyDarkClass(rootEl, isDark) {
		if (!rootEl) return;
		rootEl.querySelectorAll(DARK_SCOPE_SELECTOR).forEach(function (el) {
			el.classList.toggle(DARK_CLASS, isDark);
		});
	}

	function refreshAllInstances() {
		var dark = isDarkMode();
		instances = instances.filter(function (entry) {
			return entry.rootEl && document.contains(entry.rootEl);
		});
		instances.forEach(function (entry) {
			applyDarkClass(entry.rootEl, dark);
		});
	}

	function ensureThemeListener() {
		if (themeListenerBound) return;
		themeListenerBound = true;
		document.addEventListener("gris:theme-change", refreshAllInstances);
		if (typeof MutationObserver !== "undefined") {
			var observer = new MutationObserver(refreshAllInstances);
			observer.observe(document.documentElement, {
				attributes: true,
				attributeFilter: ["class"],
			});
		}
	}

	function ensureToastUIEditor() {
		if (global.toastui && global.toastui.Editor) {
			return Promise.resolve(global.toastui.Editor);
		}
		if (loadPromise) return loadPromise;

		ensureCss(CSS_HREF, "css");
		ensureCss(CSS_DARK_HREF, "css-dark");
		loadPromise = loadScript(JS_SRC, "js")
			.then(function () {
				return loadScript(I18N_SRC, "i18n-pt-br");
			})
			.then(function () {
				if (!global.toastui || !global.toastui.Editor) {
					throw new Error("Toast UI Editor indisponível após carregamento");
				}
				return global.toastui.Editor;
			})
			.catch(function (err) {
				loadPromise = null;
				throw err;
			});
		return loadPromise;
	}

	function createGrisEditor(targetEl, options) {
		if (!targetEl) {
			return Promise.reject(new Error("createGrisEditor: elemento alvo obrigatório"));
		}
		return ensureToastUIEditor().then(function (Editor) {
			var dark = isDarkMode();
			var merged = Object.assign(
				{
					language: "pt-BR",
					previewStyle: "vertical",
					height: "auto",
					usageStatistics: false,
				},
				options || {}
			);
			merged.el = targetEl;
			merged.initialEditType = "wysiwyg";
			merged.hideModeSwitch = true;
			merged.theme = dark ? "dark" : "light";

			var instance = new Editor(merged);

			ensureThemeListener();
			instances.push({ rootEl: targetEl, instance: instance });
			applyDarkClass(targetEl, dark);

			return instance;
		});
	}

	global.gris = global.gris || {};
	global.gris.editor = {
		ensure: ensureToastUIEditor,
		create: createGrisEditor,
		refreshTheme: refreshAllInstances,
	};
})(window);
