frappe.ready(function () {
	if ($("#meus-dados-form").length > 0) {
		const data = window.gris_meus_dados || { habilidades_iniciais: [], todas_habilidades: [] };
		let currentSkills = new Set(data.habilidades_iniciais);
		const allSkills = new Set(data.todas_habilidades);

		// Initial render
		renderSkills();
		renderSuggestions();

		// Handle adding skills
		$("#btn-add-habilidade").on("click", function () {
			addHabilidade();
		});

		$("#nova-habilidade").on("keypress", function (e) {
			if (e.which === 13) {
				e.preventDefault();
				addHabilidade();
			}
		});

		// Filter suggestions on type
		$("#nova-habilidade").on("input", function () {
			renderSuggestions($(this).val());
		});

		// Remove skill
		$(document).on("click", ".remove-habilidade", function () {
			const tag = $(this).closest(".habilidade-tag");
			const val = tag.data("val");
			currentSkills.delete(val);
			renderSkills();
			renderSuggestions(); // Move back to suggestions if it exists in allSkills
		});

		// Add suggestion
		$(document).on("click", ".sugestao-tag", function () {
			const val = $(this).data("val");
			addSkill(val);
		});

		function addSkill(val) {
			if (!val) return;
			val = val.trim();
			if (!val) return;

			// Case insensitive check
			let exists = false;
			currentSkills.forEach((s) => {
				if (s.toLowerCase() === val.toLowerCase()) exists = true;
			});

			if (exists) {
				// Blink existing?
				return;
			}

			currentSkills.add(val);
			renderSkills();
			renderSuggestions();
		}

		function addHabilidade() {
			const rawVal = $("#nova-habilidade").val();
			if (rawVal) {
				// Split by comma
				const values = rawVal
					.split(",")
					.map((s) => s.trim())
					.filter((s) => s.length > 0);

				let addedCount = 0;
				values.forEach((val) => {
					// Check duplicates
					let exists = false;
					currentSkills.forEach((s) => {
						if (s.toLowerCase() === val.toLowerCase()) exists = true;
					});

					if (!exists) {
						currentSkills.add(val);
						addedCount++;
					}
				});

				if (addedCount > 0) {
					renderSkills();
					renderSuggestions();
					$("#nova-habilidade").val("");
				} else if (values.length > 0) {
					frappe.show_alert({
						message: "Habilidade(s) já adicionada(s)",
						indicator: "orange",
					});
					$("#nova-habilidade").val("");
				}
			}
		}

		function renderSkills() {
			const container = $(".habilidades-list");
			container.empty();

			Array.from(currentSkills)
				.sort()
				.forEach((hab) => {
					const badge = `
					<span class="g-badge g-badge--primary me-1 mb-1 habilidade-tag" data-val="${hab}">
						${hab}
						<span class="remove-habilidade" style="cursor:pointer; margin-left:5px;">&times;</span>
					</span>
				`;
					container.append(badge);
				});
		}

		function renderSuggestions(filterText = "") {
			const container = $(".sugestoes-list");
			container.empty();

			const suggestionsContainer = $(".sugestoes-container");

			// Filter: In allSkills AND NOT in currentSkills
			// AND matches filterText

			const available = Array.from(allSkills)
				.filter((s) => {
					// Check if already selected (case insensitive)
					let selected = false;
					currentSkills.forEach((cs) => {
						if (cs.toLowerCase() === s.toLowerCase()) selected = true;
					});
					if (selected) return false;

					if (filterText) {
						return s.toLowerCase().includes(filterText.toLowerCase());
					}
					return true;
				})
				.sort();

			if (available.length === 0) {
				suggestionsContainer.hide();
				return;
			}

			suggestionsContainer.show();

			// Show max 15 to avoid clutter unless filtering
			const limit = filterText ? 100 : 15;

			available.slice(0, limit).forEach((hab) => {
				const badge = `
					<span class="g-badge g-badge--secondary me-1 mb-1 sugestao-tag pointer" data-val="${hab}" style="cursor:pointer; opacity: 0.8;">
						${hab} <i class="fa fa-plus ms-1" style="font-size: 0.8em"></i>
					</span>
				`;
				container.append(badge);
			});

			if (available.length > limit) {
				container.append(
					`<span class="text-muted small ms-1 align-self-center">+ ${
						available.length - limit
					} mais...</span>`
				);
			}
		}

		// Handle form submit
		$("#meus-dados-form").on("submit", function (e) {
			e.preventDefault();

			const btn = $(this).find('button[type="submit"]');
			const originalText = btn.text();
			btn.prop("disabled", true).text("Salvando...");

			const o_que_gosta = $("#o_que_gosta").val();
			const habilidades = Array.from(currentSkills);

			frappe.call({
				method: "gris.www.responsavel.meus_dados.update_meus_dados",
				args: {
					o_que_gosta_de_fazer_no_dia_a_dia: o_que_gosta,
					habilidades: JSON.stringify(habilidades),
				},
				freeze: true,
				callback: function (r) {
					btn.prop("disabled", false).text(originalText);
					if (!r.exc) {
						frappe.show_alert({
							message: "Dados atualizados com sucesso.",
							indicator: "green",
						});
					}
				},
				error: function () {
					btn.prop("disabled", false).text(originalText);
				},
			});
		});
	}
});
