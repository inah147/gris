(() => {
  const initDropdownMenu = (dropdownMenuComponent) => {
    const trigger = dropdownMenuComponent.querySelector(':scope > button');
    const popover = dropdownMenuComponent.querySelector(':scope > [data-popover]');
    if (!popover) return;

    const menu = popover.querySelector('[role="menu"]');
    
    if (!trigger || !menu || !popover) {
      const missing = [];
      if (!trigger) missing.push('trigger');
      if (!menu) missing.push('menu');
      if (!popover) missing.push('popover');
      console.error(`Dropdown menu initialisation failed. Missing element(s): ${missing.join(', ')}`, dropdownMenuComponent);
      return;
    }

    let menuItems = [];
    let activeIndex = -1;

    const positionPopover = () => {
      const GAP = 8;
      const vw = window.innerWidth;
      const vh = window.innerHeight;
      const triggerRect = trigger.getBoundingClientRect();

      // Mede dimensões naturais sem exibir (visibility:hidden + sem transições)
      popover.style.visibility = 'hidden';
      popover.style.transition = 'none';
      popover.setAttribute('aria-hidden', 'false');
      const contentW = popover.scrollWidth;
      const contentH = popover.scrollHeight;
      popover.setAttribute('aria-hidden', 'true');
      popover.style.removeProperty('visibility');
      popover.style.removeProperty('transition');

      // Lado vertical: prefere baixo, inverte para cima se houver mais espaço
      const spaceBelow = vh - triggerRect.bottom - GAP;
      const spaceAbove = triggerRect.top - GAP;
      const side = (contentH > spaceBelow && spaceAbove > spaceBelow) ? 'top' : 'bottom';
      popover.setAttribute('data-side', side);

      // Alinhamento horizontal: start (left:0, expande à direita) vs end (right:0, expande à esquerda)
      const spaceRight = vw - triggerRect.left - GAP;
      const spaceLeft = triggerRect.right - GAP;
      if (contentW > spaceRight && spaceLeft > spaceRight) {
        popover.setAttribute('data-align', 'end');
      } else {
        popover.setAttribute('data-align', 'start');
      }

      // Altura máxima: restringe ao espaço disponível com scroll interno
      const availH = Math.max(side === 'bottom' ? spaceBelow : spaceAbove, 120);
      if (contentH > availH) {
        popover.style.maxHeight = `${availH}px`;
      } else {
        popover.style.removeProperty('max-height');
      }

      // Largura máxima: evita overflow do viewport
      const maxW = vw - 2 * GAP;
      if (contentW > maxW) {
        popover.style.maxWidth = `${maxW}px`;
      } else {
        popover.style.removeProperty('max-width');
      }
    };

    const closePopover = (focusOnTrigger = true) => {
      if (trigger.getAttribute('aria-expanded') === 'false') return;
      trigger.setAttribute('aria-expanded', 'false');
      trigger.removeAttribute('aria-activedescendant');
      popover.setAttribute('aria-hidden', 'true');
      popover.style.removeProperty('max-height');
      popover.style.removeProperty('max-width');
      
      if (focusOnTrigger) {
        trigger.focus();
      }
      
      setActiveItem(-1);
    };

    const openPopover = (initialSelection = false) => {
      document.dispatchEvent(new CustomEvent('basecoat:popover', {
        detail: { source: dropdownMenuComponent }
      }));

      positionPopover();
      
      trigger.setAttribute('aria-expanded', 'true');
      popover.setAttribute('aria-hidden', 'false');
      menuItems = Array.from(menu.querySelectorAll('[role^="menuitem"]')).filter(item => 
        !item.hasAttribute('disabled') && 
        item.getAttribute('aria-disabled') !== 'true'
      );
      
      if (menuItems.length > 0 && initialSelection) {
        if (initialSelection === 'first') {
          setActiveItem(0);
        } else if (initialSelection === 'last') {
          setActiveItem(menuItems.length - 1);
        }
      }
    };

    const setActiveItem = (index) => {
      if (activeIndex > -1 && menuItems[activeIndex]) {
        menuItems[activeIndex].classList.remove('active');
      }
      activeIndex = index;
      if (activeIndex > -1 && menuItems[activeIndex]) {
        const activeItem = menuItems[activeIndex];
        activeItem.classList.add('active');
        trigger.setAttribute('aria-activedescendant', activeItem.id);
      } else {
        trigger.removeAttribute('aria-activedescendant');
      }
    };

    trigger.addEventListener('click', () => {
      const isExpanded = trigger.getAttribute('aria-expanded') === 'true';
      if (isExpanded) {
        closePopover();
      } else {
        openPopover(false);
      }
    });

    dropdownMenuComponent.addEventListener('keydown', (event) => {
      const isExpanded = trigger.getAttribute('aria-expanded') === 'true';

      if (event.key === 'Escape') {
        if (isExpanded) closePopover();
        return;
      }
      
      if (!isExpanded) {
        if (['Enter', ' '].includes(event.key)) {
          event.preventDefault();
          openPopover(false);
        } else if (event.key === 'ArrowDown') {
          event.preventDefault();
          openPopover('first');
        } else if (event.key === 'ArrowUp') {
          event.preventDefault();
          openPopover('last');
        }
        return;
      }

      if (menuItems.length === 0) return;

      let nextIndex = activeIndex;

      switch (event.key) {
        case 'ArrowDown':
          event.preventDefault();
          nextIndex = activeIndex === -1 ? 0 : Math.min(activeIndex + 1, menuItems.length - 1);
          break;
        case 'ArrowUp':
          event.preventDefault();
          nextIndex = activeIndex === -1 ? menuItems.length - 1 : Math.max(activeIndex - 1, 0);
          break;
        case 'Home':
          event.preventDefault();
          nextIndex = 0;
          break;
        case 'End':
          event.preventDefault();
          nextIndex = menuItems.length - 1;
          break;
        case 'Enter':
        case ' ':
          event.preventDefault();
          menuItems[activeIndex]?.click();
          closePopover();
          return;
      }

      if (nextIndex !== activeIndex) {
        setActiveItem(nextIndex);
      }
    });

    menu.addEventListener('mousemove', (event) => {
      const menuItem = event.target.closest('[role^="menuitem"]');
      if (menuItem && menuItems.includes(menuItem)) {
        const index = menuItems.indexOf(menuItem);
        if (index !== activeIndex) {
          setActiveItem(index);
        }
      }
    });

    menu.addEventListener('mouseleave', () => {
      setActiveItem(-1);
    });

    menu.addEventListener('click', (event) => {
      if (event.target.closest('[role^="menuitem"]')) {
        closePopover();
      }
    });

    document.addEventListener('click', (event) => {
      if (!dropdownMenuComponent.contains(event.target)) {
        closePopover();
      }
    });

    document.addEventListener('basecoat:popover', (event) => {
      if (event.detail.source !== dropdownMenuComponent) {
        closePopover(false);
      }
    });

    dropdownMenuComponent.dataset.dropdownMenuInitialized = true;
    dropdownMenuComponent.dispatchEvent(new CustomEvent('basecoat:initialized'));
  };

  if (window.basecoat) {
    window.basecoat.register('dropdown-menu', '.dropdown-menu:not([data-dropdown-menu-initialized])', initDropdownMenu);
  }
})();
