(() => {
  const formatBrazil = (digits) => {
    if (digits.length > 11) digits = digits.slice(0, 11);
    if (digits.length > 10) {
      return digits.replace(/^(\d{2})(\d{1})(\d{4})(\d{4}).*/, "($1) $2 $3-$4");
    }
    if (digits.length > 6) {
      return digits.replace(/^(\d{2})(\d{4})(\d{0,4})/, "($1) $2-$3");
    }
    if (digits.length > 2) {
      return digits.replace(/^(\d{2})(\d{0,5})/, "($1) $2");
    }
    return digits;
  };

  const initPhoneInput = (root) => {
    const country = root.querySelector(".phone-input__country");
    const numberInput = root.querySelector("[data-phone-input-number]");
    const hiddenInput = root.querySelector("[data-phone-input-value]");
    const trigger = country ? country.querySelector(":scope > button") : null;

    if (!country || !numberInput || !hiddenInput || !trigger) {
      console.error("Phone-input initialisation failed", root);
      return;
    }

    // Aguarda o select interno ser inicializado pelo basecoat antes de ler dial.
    const onSelectReady = () => {
      const setTriggerLabel = (option) => {
        if (!option) return;
        const flag = option.dataset.flag || "";
        const dial = option.dataset.dial || "";
        const labelEl = trigger.querySelector("span");
        if (labelEl) labelEl.textContent = `${flag} +${dial}`;
      };

      const getSelectedOption = () => {
        const isoValue = country.value;
        return country.querySelector(`[role="option"][data-value="${isoValue}"]`);
      };

      const currentDial = () => {
        const opt = getSelectedOption();
        return opt ? opt.dataset.dial || "" : "";
      };

      const applyMask = () => {
        const dial = currentDial();
        const raw = numberInput.value.replace(/\D/g, "");
        if (dial === "55") {
          numberInput.value = formatBrazil(raw);
        } else {
          numberInput.value = raw;
        }
      };

      const updateHidden = () => {
        const dial = currentDial();
        const digits = numberInput.value.replace(/\D/g, "");
        const previous = hiddenInput.value;
        hiddenInput.value = digits ? `+${dial}${digits}` : "";
        if (hiddenInput.value !== previous) {
          hiddenInput.dispatchEvent(new Event("change", { bubbles: true }));
          root.dispatchEvent(
            new CustomEvent("phone-input:change", {
              bubbles: true,
              detail: { value: hiddenInput.value, dial, digits, iso: country.value },
            }),
          );
        }
      };

      // Set initial trigger label
      setTriggerLabel(getSelectedOption());
      applyMask();
      updateHidden();

      country.addEventListener("change", () => {
        setTriggerLabel(getSelectedOption());
        applyMask();
        updateHidden();
      });

      numberInput.addEventListener("input", () => {
        applyMask();
        updateHidden();
      });

      const popover = country.querySelector("[data-popover]");
      if (popover) {
        const VIEWPORT_MARGIN = 8;
        const MIN_HEIGHT = 160;

        const adjustPopoverPlacement = () => {
          if (popover.getAttribute("aria-hidden") === "true") return;

          const triggerRect = trigger.getBoundingClientRect();
          const spaceBelow = window.innerHeight - triggerRect.bottom - VIEWPORT_MARGIN;
          const spaceAbove = triggerRect.top - VIEWPORT_MARGIN;
          const openUp = spaceAbove > spaceBelow && spaceBelow < MIN_HEIGHT;
          const available = Math.max(openUp ? spaceAbove : spaceBelow, MIN_HEIGHT);

          popover.style.top = "";
          popover.style.bottom = "";
          if (openUp) {
            popover.style.bottom = "100%";
            popover.dataset.side = "top";
          } else {
            popover.style.top = "100%";
            popover.dataset.side = "bottom";
          }
          popover.style.maxHeight = `${available}px`;
        };

        const popoverObserver = new MutationObserver(() => {
          if (popover.getAttribute("aria-hidden") === "false") {
            adjustPopoverPlacement();
          }
        });
        popoverObserver.observe(popover, {
          attributes: true,
          attributeFilter: ["aria-hidden"],
        });

        const onViewportChange = () => {
          if (popover.getAttribute("aria-hidden") === "false") {
            adjustPopoverPlacement();
          }
        };
        window.addEventListener("resize", onViewportChange);
        window.addEventListener("scroll", onViewportChange, true);
      }

      // Public API
      Object.defineProperty(root, "value", {
        configurable: true,
        get() {
          return hiddenInput.value;
        },
        set(next) {
          if (typeof next !== "string" || !next) {
            numberInput.value = "";
            updateHidden();
            return;
          }
          const digitsOnly = next.replace(/\D/g, "");
          // best-match country by longest dial prefix
          const options = Array.from(country.querySelectorAll('[role="option"]'));
          let bestIso = null;
          let bestLen = 0;
          for (const opt of options) {
            const dial = opt.dataset.dial || "";
            if (digitsOnly.startsWith(dial) && dial.length > bestLen) {
              bestLen = dial.length;
              bestIso = opt.dataset.value || opt.getAttribute("data-value");
            }
          }
          if (bestIso && country.value !== bestIso && typeof country.select === "function") {
            country.select(bestIso);
          }
          numberInput.value = digitsOnly.slice(bestLen);
          applyMask();
          updateHidden();
        },
      });
    };

    if (country.dataset.selectInitialized === "true") {
      onSelectReady();
    } else {
      country.addEventListener("basecoat:initialized", onSelectReady, { once: true });
    }

    root.dataset.phoneInputInitialized = "true";
    root.dispatchEvent(new CustomEvent("basecoat:initialized"));
  };

  if (window.basecoat) {
    window.basecoat.register(
      "phone-input",
      ".phone-input:not([data-phone-input-initialized])",
      initPhoneInput,
    );
  }
})();
