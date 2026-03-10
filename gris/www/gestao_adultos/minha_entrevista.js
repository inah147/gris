frappe.ready(() => {
	(async function () {
		const root = document.getElementById("minha-entrevista-root");
		const entrevistaName = root?.dataset?.entrevistaName || "";
		const associadoContainer = document.getElementById("associado-container");
		const dadosIniciaisContainer = document.getElementById("dados-iniciais-container");
		const secoesContainer = document.getElementById("secoes-perguntas");
		const modalObservacao = document.getElementById("modal-observacao");
		const modalObservacaoBackdrop = document.getElementById("modal-observacao-backdrop");
		const modalObservacaoPergunta = document.getElementById("modal-observacao-pergunta");
		const modalObservacaoMensagem = document.getElementById("modal-observacao-mensagem");
		const btnOkModalObservacao = document.getElementById("ok-modal-observacao");

		const INFO_ICON_SVG =
			'<svg class="question-item__icon" viewBox="0 0 20 20" aria-hidden="true" focusable="false"><circle cx="10" cy="10" r="8" /><line x1="10" y1="8" x2="10" y2="13" /><circle cx="10" cy="6" r="0.8" fill="currentColor" stroke="none" /></svg>';

		if (!entrevistaName) {
			frappe.msgprint("Entrevista não informada.");
			window.location.href = "/gestao_adultos";
			return;
		}

		let config = null;
		let entrevista = null;

		function openObservationModal(question, message) {
			if (!modalObservacao || !modalObservacaoBackdrop || !modalObservacaoMensagem || !modalObservacaoPergunta) {
				return;
			}

			modalObservacaoPergunta.textContent = question || "Pergunta";
			modalObservacaoMensagem.innerHTML = frappe.utils
				.escape_html(message || "Sem observações para esta resposta.")
				.replace(/\n/g, "<br>");
			modalObservacaoBackdrop.style.display = "block";
			modalObservacao.style.display = "flex";
			document.body.classList.add("modal-open");
		}

		function closeObservationModal() {
			if (!modalObservacao || !modalObservacaoBackdrop) {
				return;
			}

			modalObservacao.style.display = "none";
			modalObservacaoBackdrop.style.display = "none";
			document.body.classList.remove("modal-open");
		}

		function renderAssociado() {
			const associadoDisplay = entrevista.associado_nome || entrevista.associado || "Não informado";
			if (!associadoContainer) {
				return;
			}

			associadoContainer.innerHTML = `
				<h3 class="card-modern__title mb-2">Associado</h3>
				<p class="mb-0">${frappe.utils.escape_html(associadoDisplay)}</p>
			`;
		}

		function renderDadosIniciais() {
			dadosIniciaisContainer.innerHTML = `
				<h3 class="card-modern__title mb-3">Dados iniciais</h3>
				<div class="row g-3">
					<div class="col-12 col-md-6">
						<label class="form-label-modern">Motivo da entrevista</label>
						<select class="form-input-modern" id="motivo_da_entrevista" disabled></select>
					</div>
					<div class="col-12 col-md-6">
						<label class="form-label-modern">Função atual</label>
						<input type="text" class="form-input-modern" id="funcao_atual" disabled />
					</div>
					<div class="col-12 col-md-6">
						<label class="form-label-modern">Profissão</label>
						<input type="text" class="form-input-modern" id="profissao" disabled />
					</div>
					<div class="col-12 col-md-6">
						<label class="form-label-modern">Formação</label>
						<input type="text" class="form-input-modern" id="formacao" disabled />
					</div>
					<div class="col-12 col-md-6">
						<label class="form-label-modern">Hobbies e interesses</label>
						<input type="text" class="form-input-modern" id="hobbies_e_interesses" disabled />
					</div>
					<div class="col-12">
						<label class="form-label-modern">Observações gerais</label>
						<textarea class="form-input-modern" rows="3" id="observacoes" disabled></textarea>
					</div>
				</div>
			`;

			const motivoSelect = document.getElementById("motivo_da_entrevista");
			motivoSelect.innerHTML = ["<option value=''>Selecione</option>"]
				.concat(
					(config.motivos_entrevista || []).map(
						(item) => `<option value="${frappe.utils.escape_html(item)}">${frappe.utils.escape_html(item)}</option>`
					)
				)
				.join("");

			["motivo_da_entrevista", "funcao_atual", "profissao", "formacao", "hobbies_e_interesses", "observacoes"].forEach(
				(field) => {
					const el = document.getElementById(field);
					if (el) {
						el.value = entrevista[field] || "";
					}
				}
			);
		}

		function renderSections() {
			secoesContainer.innerHTML = (config.sections || [])
				.map(
					(section) => `
						<div class="card-modern mb-4">
							<div class="card-modern__header">
								<h3 class="card-modern__title">${frappe.utils.escape_html(section.label)}</h3>
							</div>
							<div class="card-modern__body">
								${(section.fields || [])
									.map(
										(field) => `
											<div class="question-item">
												<div class="question-item__header">
													<label class="form-label-modern mb-0">${frappe.utils.escape_html(field.label)}</label>
													<div class="question-item__actions">
														<button type="button" id="obs-indicator-${field.fieldname}" class="question-item__info" title="Sem observações" aria-label="Sem observações" disabled>${INFO_ICON_SVG}</button>
													</div>
												</div>
												<select class="form-input-modern" id="${field.fieldname}" disabled>
													<option value="">Selecione</option>
													${(field.options || [])
														.map(
															(option) => `<option value="${frappe.utils.escape_html(option)}">${frappe.utils.escape_html(option)}</option>`
														)
														.join("")}
												</select>
												<textarea class="form-input-modern question-item__obs-store" rows="2" id="${field.observation_fieldname}" disabled></textarea>
											</div>
										`
									)
									.join("")}
							</div>
						</div>
					`
				)
				.join("");

			(config.sections || []).forEach((section) => {
				(section.fields || []).forEach((field) => {
					const select = document.getElementById(field.fieldname);
					const obs = document.getElementById(field.observation_fieldname);
					const observationIndicator = document.getElementById(`obs-indicator-${field.fieldname}`);
					if (select) {
						select.value = entrevista[field.fieldname] || "";
					}
					if (obs) {
						obs.value = entrevista[field.observation_fieldname] || "";
					}

					if (observationIndicator) {
						observationIndicator.addEventListener("click", () => {
							if (!obs) {
								return;
							}

							openObservationModal(field.label, obs.value || "Sem observações para esta resposta.");
						});
					}
				});
			});

			updateObservationIndicators();
		}

		function updateObservationIndicators() {
			(config.sections || []).forEach((section) => {
				(section.fields || []).forEach((field) => {
					const obs = document.getElementById(field.observation_fieldname);
					const indicator = document.getElementById(`obs-indicator-${field.fieldname}`);
					if (!obs || !indicator) {
						return;
					}

					const hasObservation = String(obs.value || "").trim().length > 0;
					indicator.disabled = !hasObservation;
					indicator.classList.toggle("is-visible", hasObservation);
					indicator.setAttribute("title", hasObservation ? "Ver observação" : "Sem observações");
					indicator.setAttribute("aria-label", hasObservation ? "Ver observação" : "Sem observações");
				});
			});
		}

		async function carregarMinhaEntrevista() {
			const response = await frappe.call({
				method: "gris.api.gestao_adultos.obter_minha_entrevista",
				args: { name: entrevistaName },
			});

			config = response.message?.config || {};
			entrevista = response.message?.entrevista || {};

			renderAssociado();
			renderDadosIniciais();
			renderSections();
		}

		try {
			await carregarMinhaEntrevista();
		} catch (error) {
			console.error(error);
			frappe.msgprint("Não foi possível carregar sua entrevista.");
		}

		btnOkModalObservacao?.addEventListener("click", closeObservationModal);
		modalObservacaoBackdrop?.addEventListener("click", closeObservationModal);
		document.addEventListener("keydown", (event) => {
			if (event.key === "Escape" && modalObservacao?.style.display === "flex") {
				closeObservationModal();
			}
		});
	})();
});
