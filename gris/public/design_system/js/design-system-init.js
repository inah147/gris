(function () {
  function ensureBasecoatObserver() {
    if (window.basecoat && typeof window.basecoat.start === "function") {
      window.basecoat.start();
    }
  }

  // Basecoat already auto-initializes on DOMContentLoaded and watches future DOM insertions.
  // Re-running initAll on load duplicates event listeners for interactive components.
  document.addEventListener("DOMContentLoaded", ensureBasecoatObserver);
  document.addEventListener("gris:design-system:init", ensureBasecoatObserver);

  window.grisDesignSystem = Object.freeze({
    initAll: ensureBasecoatObserver,
  });
})();
