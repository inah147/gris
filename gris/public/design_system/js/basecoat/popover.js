(() => {
  const initPopover = (popoverComponent) => {
    const trigger = popoverComponent.querySelector(':scope > button');
    const content = popoverComponent.querySelector(':scope > [data-popover]');

    if (!trigger || !content) {
      const missing = [];
      if (!trigger) missing.push('trigger');
      if (!content) missing.push('content');
      console.error(`Popover initialisation failed. Missing element(s): ${missing.join(', ')}`, popoverComponent);
      return;
    }

    const positionPopover = () => {
      const GAP = 8;
      const vw = window.innerWidth;
      const vh = window.innerHeight;
      const triggerRect = trigger.getBoundingClientRect();

      // Mede dimensões naturais sem exibir (visibility:hidden + sem transições)
      content.style.visibility = 'hidden';
      content.style.transition = 'none';
      content.setAttribute('aria-hidden', 'false');
      const contentW = content.scrollWidth;
      const contentH = content.scrollHeight;
      content.setAttribute('aria-hidden', 'true');
      content.style.removeProperty('visibility');
      content.style.removeProperty('transition');

      // Lado vertical: prefere baixo, inverte para cima se houver mais espaço
      const spaceBelow = vh - triggerRect.bottom - GAP;
      const spaceAbove = triggerRect.top - GAP;
      const side = (contentH > spaceBelow && spaceAbove > spaceBelow) ? 'top' : 'bottom';
      content.setAttribute('data-side', side);

      // Alinhamento horizontal: start (left:0, expande à direita) vs end (right:0, expande à esquerda)
      const spaceRight = vw - triggerRect.left - GAP;
      const spaceLeft = triggerRect.right - GAP;
      if (contentW > spaceRight && spaceLeft > spaceRight) {
        content.setAttribute('data-align', 'end');
      } else {
        content.setAttribute('data-align', 'start');
      }

      // Altura máxima: restringe ao espaço disponível com scroll interno
      const availH = Math.max(side === 'bottom' ? spaceBelow : spaceAbove, 120);
      if (contentH > availH) {
        content.style.maxHeight = `${availH}px`;
      } else {
        content.style.removeProperty('max-height');
      }

      // Largura máxima: evita overflow do viewport
      const maxW = vw - 2 * GAP;
      if (contentW > maxW) {
        content.style.maxWidth = `${maxW}px`;
      } else {
        content.style.removeProperty('max-width');
      }
    };

    const closePopover = (focusOnTrigger = true) => {
      if (trigger.getAttribute('aria-expanded') === 'false') return;
      trigger.setAttribute('aria-expanded', 'false');
      content.setAttribute('aria-hidden', 'true');
      content.style.removeProperty('max-height');
      content.style.removeProperty('max-width');
      if (focusOnTrigger) {
        trigger.focus();
      }
    };

    const openPopover = () => {
      document.dispatchEvent(new CustomEvent('basecoat:popover', {
        detail: { source: popoverComponent }
      }));

      positionPopover();

      const elementToFocus = content.querySelector('[autofocus]');
      if (elementToFocus) {
        content.addEventListener('transitionend', () => {
          elementToFocus.focus();
        }, { once: true });
      }

      trigger.setAttribute('aria-expanded', 'true');
      content.setAttribute('aria-hidden', 'false');
    };

    trigger.addEventListener('click', () => {
      const isExpanded = trigger.getAttribute('aria-expanded') === 'true';
      if (isExpanded) {
        closePopover();
      } else {
        openPopover();
      }
    });

    popoverComponent.addEventListener('keydown', (event) => {
      if (event.key === 'Escape') {
        closePopover();
      }
    });

    document.addEventListener('click', (event) => {
      if (!popoverComponent.contains(event.target)) {
        closePopover();
      }
    });

    document.addEventListener('basecoat:popover', (event) => {
      if (event.detail.source !== popoverComponent) {
        closePopover(false);
      }
    });

    popoverComponent.dataset.popoverInitialized = true;
    popoverComponent.dispatchEvent(new CustomEvent('basecoat:initialized'));
  };

  if (window.basecoat) {
    window.basecoat.register('popover', '.popover:not([data-popover-initialized])', initPopover);
  }
})();
