(() => {
	const initPopover = (popoverComponent) => {
		const trigger = popoverComponent.querySelector(":scope > button");
		const content = popoverComponent.querySelector(":scope > [data-popover]");

		if (!trigger || !content) {
			const missing = [];
			if (!trigger) missing.push("trigger");
			if (!content) missing.push("content");
			console.error(
				`Popover initialisation failed. Missing element(s): ${missing.join(", ")}`,
				popoverComponent
			);
			return;
		}

		// HTML Popover API: promove o content ao top layer ao abrir, fazendo-o
		// renderizar acima de qualquer elemento (incluindo <dialog> em showModal)
		// e isolando-o de ancestors com `overflow: hidden` ou
		// `transform`/`translate`/`scale` (que estabeleceriam novo containing
		// block para position:fixed).
		if (!content.hasAttribute("popover")) {
			content.setAttribute("popover", "manual");
		}

		const positionPopover = () => {
			const GAP = 8;
			const vw = window.innerWidth;
			const vh = window.innerHeight;
			const triggerRect = trigger.getBoundingClientRect();

			// Mede dimensões naturais sem exibir (visibility:hidden + sem transições).
			// Preserva o estado original de aria-hidden: positionPopover é chamada
			// tanto durante openPopover (estado inicial: 'true') quanto por
			// onReposition em scroll/resize (estado: 'false', popover aberto).
			// Restaurar evita esconder o popover por engano em reposicionamentos.
			const prevAriaHidden = content.getAttribute("aria-hidden");
			content.style.visibility = "hidden";
			content.style.transition = "none";
			content.setAttribute("aria-hidden", "false");
			const contentW = content.scrollWidth;
			const contentH = content.scrollHeight;
			content.setAttribute("aria-hidden", prevAriaHidden == null ? "true" : prevAriaHidden);
			content.style.removeProperty("visibility");
			content.style.removeProperty("transition");

			// Lado vertical: prefere baixo, inverte para cima se houver mais espaço
			const spaceBelow = vh - triggerRect.bottom - GAP;
			const spaceAbove = triggerRect.top - GAP;
			const side = contentH > spaceBelow && spaceAbove > spaceBelow ? "top" : "bottom";
			content.setAttribute("data-side", side);

			// Alinhamento horizontal: start (alinhado à esquerda do trigger) vs end (alinhado à direita)
			const spaceRight = vw - triggerRect.left - GAP;
			const spaceLeft = triggerRect.right - GAP;
			const align = contentW > spaceRight && spaceLeft > spaceRight ? "end" : "start";
			content.setAttribute("data-align", align);

			// Altura máxima: restringe ao espaço disponível com scroll interno
			const availH = Math.max(side === "bottom" ? spaceBelow : spaceAbove, 120);
			if (contentH > availH) {
				content.style.maxHeight = `${availH}px`;
			} else {
				content.style.removeProperty("max-height");
			}

			// Largura máxima: evita overflow do viewport
			const maxW = vw - 2 * GAP;
			if (contentW > maxW) {
				content.style.maxWidth = `${maxW}px`;
			} else {
				content.style.removeProperty("max-width");
			}

			// Materializa coordenadas (position: fixed → relativas ao viewport)
			if (side === "bottom") {
				content.style.top = `${triggerRect.bottom + GAP}px`;
				content.style.removeProperty("bottom");
			} else {
				content.style.bottom = `${vh - triggerRect.top + GAP}px`;
				content.style.removeProperty("top");
			}
			if (align === "start") {
				content.style.left = `${triggerRect.left}px`;
				content.style.removeProperty("right");
			} else {
				content.style.right = `${vw - triggerRect.right}px`;
				content.style.removeProperty("left");
			}
			content.style.minWidth = `${triggerRect.width}px`;
		};

		const onReposition = () => positionPopover();

		const closePopover = (focusOnTrigger = true) => {
			if (trigger.getAttribute("aria-expanded") === "false") return;
			trigger.setAttribute("aria-expanded", "false");
			content.setAttribute("aria-hidden", "true");
			content.style.removeProperty("max-height");
			content.style.removeProperty("max-width");
			content.style.removeProperty("top");
			content.style.removeProperty("bottom");
			content.style.removeProperty("left");
			content.style.removeProperty("right");
			content.style.removeProperty("min-width");
			window.removeEventListener("scroll", onReposition, true);
			window.removeEventListener("resize", onReposition);
			if (content.matches(":popover-open")) {
				content.hidePopover();
			}
			if (focusOnTrigger) {
				trigger.focus();
			}
		};

		const openPopover = () => {
			document.dispatchEvent(
				new CustomEvent("basecoat:popover", {
					detail: { source: popoverComponent },
				})
			);

			// Promove ao top layer antes de medir/posicionar; o navegador
			// automaticamente remove o `display: none` do estado fechado.
			if (!content.matches(":popover-open")) {
				content.showPopover();
			}

			positionPopover();

			const elementToFocus = content.querySelector("[autofocus]");
			if (elementToFocus) {
				elementToFocus.focus();
			}

			trigger.setAttribute("aria-expanded", "true");
			content.setAttribute("aria-hidden", "false");

			// Reposicionar enquanto aberto: scroll (capture pega scrolls internos
			// como o body de um <dialog>) e resize do viewport.
			window.addEventListener("scroll", onReposition, true);
			window.addEventListener("resize", onReposition);
		};

		trigger.addEventListener("click", () => {
			const isExpanded = trigger.getAttribute("aria-expanded") === "true";
			if (isExpanded) {
				closePopover();
			} else {
				openPopover();
			}
		});

		// Escape: trigger fica em popoverComponent; o content também recebe
		// listener próprio para casos em que o foco está em elementos internos
		// (ex.: input de busca).
		const onKeydown = (event) => {
			if (event.key === "Escape") closePopover();
		};
		popoverComponent.addEventListener("keydown", onKeydown);
		content.addEventListener("keydown", onKeydown);

		document.addEventListener("click", (event) => {
			if (!popoverComponent.contains(event.target)) {
				closePopover();
			}
		});

		document.addEventListener("basecoat:popover", (event) => {
			// Não fecha quando o popover/select que está abrindo é um descendente
			// deste (ex.: um select dentro do conteúdo do popover). Sem essa guarda,
			// abrir um select aninhado dispararia o fechamento do popover pai.
			const source = event.detail.source;
			if (source !== popoverComponent && !popoverComponent.contains(source)) {
				closePopover(false);
			}
		});

		popoverComponent.dataset.popoverInitialized = true;
		popoverComponent.dispatchEvent(new CustomEvent("basecoat:initialized"));
	};

	if (window.basecoat) {
		window.basecoat.register(
			"popover",
			".popover:not([data-popover-initialized])",
			initPopover
		);
	}
})();
