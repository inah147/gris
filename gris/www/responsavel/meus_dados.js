frappe.ready(function () {
	const form = document.getElementById("meus-dados-form");
	if (!form) return;

	const data = window.gris_meus_dados || { habilidades_iniciais: [], todas_habilidades: [] };
	const SPRITE = "/assets/gris/design_system/icons/lucide/sprite.svg";
	const COMBOBOX_PLACEHOLDER = "Adicionar habilidade existente";

	const currentSkills = new Set(data.habilidades_iniciais || []);

	const selectedContainer = document.getElementById("habilidades-selecionadas");
	const novaInput = document.getElementById("nova-habilidade");
	const btnAdd = document.getElementById("btn-add-habilidade");
	const combobox = document.getElementById("combobox-habilidades");
	const comboboxTriggerLabel = combobox && combobox.querySelector(":scope > button > span");
	const comboboxHidden = combobox && combobox.querySelector(':scope > input[type="hidden"]');
	const submitBtn = document.getElementById("btn-salvar-meus-dados");

	function escapeHtml(value) {
		return String(value).replace(
			/[&<>"']/g,
			(ch) =>
				({
					"&": "&amp;",
					"<": "&lt;",
					">": "&gt;",
					'"': "&quot;",
					"'": "&#39;",
				}[ch])
		);
	}

	function lucideSvg(name, size) {
		const sizeClass = size === "sm" ? "ds-lucide--sm" : "ds-lucide--md";
		return `<svg class="ds-lucide ${sizeClass}" viewBox="0 0 24 24" aria-hidden="true"><use href="${SPRITE}#${name}"></use></svg>`;
	}

	function isAlreadySelected(value) {
		const target = value.trim().toLowerCase();
		for (const skill of currentSkills) {
			if (skill.toLowerCase() === target) return true;
		}
		return false;
	}

	function showToast(category, title, description) {
		document.dispatchEvent(
			new CustomEvent("basecoat:toast", {
				detail: {
					config: {
						category: category,
						title: title,
						description: description,
					},
				},
			})
		);
	}

	function resetCombobox() {
		if (!combobox) return;
		if (comboboxHidden) comboboxHidden.value = "";
		if (comboboxTriggerLabel) {
			comboboxTriggerLabel.textContent = COMBOBOX_PLACEHOLDER;
			comboboxTriggerLabel.classList.add("text-muted-foreground");
		}
		combobox.querySelectorAll('[role="option"][aria-selected="true"]').forEach((opt) => {
			opt.removeAttribute("aria-selected");
		});
	}

	function refreshComboboxOptions() {
		if (!combobox) return;
		combobox.querySelectorAll('[role="option"]').forEach((opt) => {
			const value = opt.dataset.value || opt.textContent.trim();
			if (isAlreadySelected(value)) {
				opt.setAttribute("data-selected-already", "true");
			} else {
				opt.removeAttribute("data-selected-already");
			}
		});
	}

	function renderSelectedSkills() {
		if (!selectedContainer) return;
		selectedContainer.innerHTML = "";
		const sorted = Array.from(currentSkills).sort((a, b) =>
			a.localeCompare(b, "pt-BR", { sensitivity: "base" })
		);
		for (const skill of sorted) {
			const safe = escapeHtml(skill);
			const tag = document.createElement("span");
			tag.className = "badge badge-secondary habilidade-tag";
			tag.dataset.val = skill;
			tag.innerHTML = `
				<span>${safe}</span>
				<button
					type="button"
					class="habilidade-tag__remove"
					data-remove-habilidade="${safe}"
					aria-label="Remover habilidade ${safe}"
				>${lucideSvg("x", "sm")}</button>
			`;
			selectedContainer.appendChild(tag);
		}
	}

	function addSkill(rawValue, { silent } = { silent: false }) {
		if (!rawValue) return false;
		const value = rawValue.trim();
		if (!value) return false;
		if (isAlreadySelected(value)) {
			if (!silent) {
				showToast(
					"warning",
					"Habilidade já adicionada",
					`“${value}” já está na sua lista.`
				);
			}
			return false;
		}
		currentSkills.add(value);
		renderSelectedSkills();
		refreshComboboxOptions();
		return true;
	}

	function removeSkill(value) {
		if (!currentSkills.has(value)) return;
		currentSkills.delete(value);
		renderSelectedSkills();
		refreshComboboxOptions();
	}

	if (combobox) {
		combobox.addEventListener("change", (event) => {
			const value = event.detail && event.detail.value;
			if (!value) return;
			addSkill(value, { silent: true });
			resetCombobox();
		});
	}

	if (selectedContainer) {
		selectedContainer.addEventListener("click", (event) => {
			const btn = event.target.closest("[data-remove-habilidade]");
			if (!btn) return;
			removeSkill(btn.getAttribute("data-remove-habilidade"));
		});
	}

	if (btnAdd) {
		btnAdd.addEventListener("click", () => {
			const value = novaInput ? novaInput.value : "";
			if (addSkill(value)) {
				if (novaInput) novaInput.value = "";
			}
			if (novaInput) novaInput.focus();
		});
	}

	if (novaInput) {
		novaInput.addEventListener("keydown", (event) => {
			if (event.key === "Enter") {
				event.preventDefault();
				if (addSkill(novaInput.value)) {
					novaInput.value = "";
				}
			}
		});
	}

	form.addEventListener("submit", (event) => {
		event.preventDefault();

		const textarea = document.getElementById("o_que_gosta");
		const oQueGosta = textarea ? textarea.value : "";
		const habilidades = Array.from(currentSkills);

		const originalLabel = submitBtn ? submitBtn.textContent : "";
		if (submitBtn) {
			submitBtn.disabled = true;
			submitBtn.textContent = "Salvando…";
		}

		frappe.call({
			method: "gris.www.responsavel.meus_dados.update_meus_dados",
			args: {
				o_que_gosta_de_fazer_no_dia_a_dia: oQueGosta,
				habilidades: JSON.stringify(habilidades),
			},
			callback: function (r) {
				if (submitBtn) {
					submitBtn.disabled = false;
					submitBtn.textContent = originalLabel;
				}
				if (!r.exc) {
					showToast(
						"success",
						"Dados atualizados",
						"Suas informações foram salvas com sucesso."
					);
				}
			},
			error: function () {
				if (submitBtn) {
					submitBtn.disabled = false;
					submitBtn.textContent = originalLabel;
				}
				showToast("error", "Não foi possível salvar", "Tente novamente em instantes.");
			},
		});
	});

	resetCombobox();
	refreshComboboxOptions();
	renderSelectedSkills();
});
