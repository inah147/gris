(() => {
	const initSidebar = (sidebarComponent) => {
		const initialOpen = sidebarComponent.dataset.initialOpen !== "false";
		const initialMobileOpen = sidebarComponent.dataset.initialMobileOpen === "true";
		const breakpoint = parseInt(sidebarComponent.dataset.breakpoint) || 768;

		const isMobileViewport = () => breakpoint > 0 && window.innerWidth < breakpoint;

		let mobileViewport = isMobileViewport();
		let open = mobileViewport ? initialMobileOpen : initialOpen;

		const updateState = () => {
			sidebarComponent.dataset.sidebarViewport = mobileViewport ? "mobile" : "desktop";
			sidebarComponent.dataset.sidebarState = open ? "open" : "closed";
			sidebarComponent.setAttribute("aria-hidden", !open);
			if (open) {
				sidebarComponent.removeAttribute("inert");
			} else {
				sidebarComponent.setAttribute("inert", "");
			}
		};

		const emitStateChange = (reason) => {
			const detail = {
				id: sidebarComponent.id,
				open,
				viewport: mobileViewport ? "mobile" : "desktop",
				reason,
			};

			sidebarComponent.dispatchEvent(new CustomEvent("basecoat:sidebar-state", { detail }));
			document.dispatchEvent(new CustomEvent("basecoat:sidebar-state", { detail }));
		};

		const setState = (state, reason = "toggle") => {
			open = state;
			updateState();
			emitStateChange(reason);
		};

		const syncToViewport = (reason = "breakpoint") => {
			const nextMobileViewport = isMobileViewport();

			if (nextMobileViewport === mobileViewport) {
				return;
			}

			mobileViewport = nextMobileViewport;
			setState(mobileViewport ? initialMobileOpen : initialOpen, reason);
		};

		const sidebarId = sidebarComponent.id;

		document.addEventListener("basecoat:sidebar", (event) => {
			if (event.detail?.id && event.detail.id !== sidebarId) return;

			switch (event.detail?.action) {
				case "open":
					setState(true);
					break;
				case "close":
					setState(false);
					break;
				default:
					setState(!open);
					break;
			}
		});

		sidebarComponent.addEventListener("click", (event) => {
			const target = event.target;
			const nav = sidebarComponent.querySelector("nav");

			const isMobile = mobileViewport;

			if (
				isMobile &&
				target.closest("a, button") &&
				!target.closest("[data-keep-mobile-sidebar-open]")
			) {
				if (document.activeElement) document.activeElement.blur();
				setState(false, "navigation");
				return;
			}

			if (target === sidebarComponent || (nav && !nav.contains(target))) {
				if (document.activeElement) document.activeElement.blur();
				setState(false, "backdrop");
			}
		});

		let resizeFrame = null;
		window.addEventListener("resize", () => {
			if (resizeFrame !== null) {
				window.cancelAnimationFrame(resizeFrame);
			}

			resizeFrame = window.requestAnimationFrame(() => {
				resizeFrame = null;
				syncToViewport();
			});
		});

		updateState();
		sidebarComponent.dataset.sidebarInitialized = true;
		sidebarComponent.dispatchEvent(new CustomEvent("basecoat:initialized"));
	};

	if (window.basecoat) {
		window.basecoat.register(
			"sidebar",
			".sidebar:not([data-sidebar-initialized])",
			initSidebar
		);
	}
})();
