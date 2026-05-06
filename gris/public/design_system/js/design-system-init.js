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
