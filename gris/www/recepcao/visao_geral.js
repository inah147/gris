let currentCardId = null;
let previousModalId = null;

frappe.ready(function () {
	// Add click event to cards
	$(".kanban-card").on("click", function (e) {
		e.preventDefault();
		const id = $(this).data("id");
		const status = $(this).data("status");
		const responsavel = $(this).data("responsavel");
		const nome = $(this).data("nome");
		const responsavelAssociado = $(this).data("responsavel-associado");
		const ramo = $(this).data("ramo");
		const visitaData = $(this).data("visita-data");
		const visitaConfirmada = $(this).data("visita-confirmada");
		const steps = $(this).data("steps");

		if (status === "Novo Contato") {
			openModal(id, responsavel, nome, responsavelAssociado, ramo);
		} else if (status === "Conversa Inicial") {
			openConversaInicialModal(id, responsavel, nome, responsavelAssociado, ramo);
		} else if (status === "Visita Agendada") {
			openVisitaAgendadaModal(
				id,
				responsavel,
				nome,
				responsavelAssociado,
				ramo,
				visitaData,
				visitaConfirmada
			);
		} else if (status === "Aguardar Dados") {
			openAguardarDadosModal(id, responsavel, nome, responsavelAssociado, steps);
		} else if (status === "Fazer Registro") {
			openFazerRegistroModal(id, responsavel, nome, responsavelAssociado, steps);
		} else if (status === "Acompanhamento") {
			openAcompanhamentoModal(id, responsavel, nome, responsavelAssociado, steps);
		} else {
			// Navigate to details page for other statuses
			window.location.href = `/recepcao/detalhes?id=${id}`;
		}
	});

	// Handle select change for Novo Contato
	$("#responsavelRecepcao").on("change", function () {
		const responsavel = $(this).val();
		const btn = $("#btnMoverConversa");

		if (responsavel) {
			btn.prop("disabled", false);
			// Save responsible immediately when selected
			saveResponsavel(currentCardId, responsavel);
		} else {
			btn.prop("disabled", true);
		}
	});

	// Handle select change for Visita Agendada
	$("#va_ramo").on("change", function () {
		const ramo = $(this).val();
		if (currentCardId) {
			frappe.call({
				method: "gris.api.recepcao.update_novo_associado",
				args: { name: currentCardId, ramo: ramo },
				callback: function (r) {
					if (!r.exc) {
						$(`.kanban-card[data-id="${currentCardId}"]`).data("ramo", ramo);
						frappe.show_alert({ message: "Ramo atualizado", indicator: "green" });
					}
				},
			});
		}
	});

	$("#va_responsavel_recepcao").on("change", function () {
		const responsavel = $(this).val();
		if (currentCardId) {
			saveResponsavel(currentCardId, responsavel);
		}
	});

	// Handle select change for Conversa Inicial
	$("#ci_ramo").on("change", function () {
		const ramo = $(this).val();
		if (currentCardId) {
			frappe.call({
				method: "gris.api.recepcao.update_novo_associado",
				args: { name: currentCardId, ramo: ramo },
				callback: function (r) {
					if (!r.exc) {
						$(`.kanban-card[data-id="${currentCardId}"]`).data("ramo", ramo);
						frappe.show_alert({ message: "Ramo atualizado", indicator: "green" });
					}
				},
			});
		}
	});

	$("#va_responsavel_recepcao").on("change", function () {
		const responsavel = $(this).val();
		if (currentCardId) {
			saveResponsavel(currentCardId, responsavel);
		}
	});

	// Handle select change for Aguardar Dados
	$("#ad_responsavel_recepcao").on("change", function () {
		const responsavel = $(this).val();
		if (currentCardId) {
			saveResponsavel(currentCardId, responsavel);
		}
	});

	// Handle select change for Fazer Registro
	$("#fr_responsavel_recepcao").on("change", function () {
		const responsavel = $(this).val();
		if (currentCardId) {
			saveResponsavel(currentCardId, responsavel);
		}
	});

	// Handle select change for Acompanhamento
	$("#ac_responsavel_recepcao").on("change", function () {
		const responsavel = $(this).val();
		if (currentCardId) {
			saveResponsavel(currentCardId, responsavel);
		}
	});

	// Close modal handlers
	$("[data-dismiss-modal]").on("click", closeModal);

	// Close on backdrop click (delegated because backdrop is dynamic)
	$(document).on("click", ".modal-backdrop", function (e) {
		if ($(e.target).hasClass("modal-backdrop")) {
			closeModal();
		}
	});
});

function openModal(id, responsavel, nome, responsavelAssociado, ramo) {
	currentCardId = id;
	$("#modalAssociadoNome").text(nome);
	$("#modalResponsavelNome").text(responsavelAssociado || "-");
	$("#modalRamo").text(ramo || "-");
	$("#responsavelRecepcao").val(responsavel);

	if (responsavel) {
		$("#btnMoverConversa").prop("disabled", false);
	} else {
		$("#btnMoverConversa").prop("disabled", true);
	}

	const modal = $("#modalNovoContato");

	modal.removeClass("d-none");
	modal.addClass("show");

	$("body").addClass("modal-open");

	// Create backdrop
	if ($(".modal-backdrop").length === 0) {
		$('<div class="modal-backdrop fade show"></div>').appendTo(document.body);
	}
}

function openConversaInicialModal(id, responsavel, nome, responsavelAssociado, ramo) {
	currentCardId = id;
	$("#ci_associado_nome").text(nome);
	$("#ci_responsavel_nome").text(responsavelAssociado || "-");
	$("#ci_ramo").val(ramo);
	$("#ci_responsavel_acompanhamento").val(responsavel);

	const modal = $("#modalConversaInicial");
	modal.removeClass("d-none");
	modal.addClass("show");
	$("body").addClass("modal-open");

	if ($(".modal-backdrop").length === 0) {
		$('<div class="modal-backdrop fade show"></div>').appendTo(document.body);
	}
}

function closeModal() {
	$(".modal-modern").removeClass("show").addClass("d-none");
	$("body").removeClass("modal-open");
	$(".modal-backdrop").remove();
	currentCardId = null;
}

function saveResponsavel(id, responsavel) {
	frappe.call({
		method: "gris.api.recepcao.update_novo_associado",
		args: {
			name: id,
			responsavel_recepcao: responsavel,
		},
		callback: function (r) {
			if (!r.exc) {
				// Update data attribute on the card
				$(`.kanban-card[data-id="${id}"]`).data("responsavel", responsavel);
				frappe.show_alert({ message: "Responsável atualizado", indicator: "green" });
			}
		},
	});
}

function moverParaConversaInicial() {
	if (!currentCardId) return;

	frappe.call({
		method: "gris.api.recepcao.update_novo_associado",
		args: {
			name: currentCardId,
			status: "Conversa Inicial",
		},
		callback: function (r) {
			if (!r.exc) {
				frappe.show_alert({ message: "Movido para Conversa Inicial", indicator: "green" });
				closeModal();
				// Reload page to reflect changes in Kanban
				setTimeout(() => window.location.reload(), 500);
			}
		},
	});
}

function openFicha() {
	if (currentCardId) {
		window.location.href = `/recepcao/ficha_registro?name=${currentCardId}`;
	}
}

function openAgendarVisita() {
	const modal = $("#modalAgendarVisita");
	const dateSelect = $("#av_data");
	const ramo = $("#ci_ramo").val();

	if (!ramo) {
		frappe.msgprint("Defina o Ramo antes de agendar.");
		return;
	}

	dateSelect.html('<option value="">Carregando...</option>');

	modal.removeClass("d-none");
	modal.addClass("show");
	// Ensure backdrop is above the first modal if needed
	modal.css("z-index", 1060);

	frappe.call({
		method: "gris.www.recepcao.agenda_visitas.get_available_dates_for_ramo",
		args: { ramo: ramo },
		callback: function (r) {
			if (r.message && r.message.length > 0) {
				let html = '<option value="">Selecione uma data...</option>';
				r.message.forEach((d) => {
					html += `<option value="${d.value}">${d.label}</option>`;
				});
				dateSelect.html(html);
			} else {
				dateSelect.html('<option value="">Nenhuma data disponível</option>');
			}
		},
	});
}

function closeAgendarVisita() {
	const modal = $("#modalAgendarVisita");
	modal.removeClass("show");
	modal.addClass("d-none");
}

function confirmarAgendamento() {
	const date = $("#av_data").val();
	if (!date) {
		frappe.msgprint("Selecione uma data.");
		return;
	}

	frappe.call({
		method: "gris.www.recepcao.agenda_visitas.schedule_visit",
		args: {
			associate: currentCardId,
			date: date,
		},
		callback: function (r) {
			if (!r.exc) {
				frappe.show_alert({ message: "Visita agendada com sucesso!", indicator: "green" });
				closeAgendarVisita();
				setTimeout(() => window.location.reload(), 1000);
			}
		},
	});
}

function registrarDesistencia() {
	// Find currently open modal to save state
	const openModal = $(".modal-modern.show").not("#modalConfirmarDesistencia");
	if (openModal.length > 0) {
		previousModalId = openModal.attr("id");
		openModal.removeClass("show").addClass("d-none");
	} else {
		previousModalId = null;
	}

	// Open confirmation modal
	const modal = $("#modalConfirmarDesistencia");
	modal.removeClass("d-none");
	modal.addClass("show");
	// Ensure backdrop is correct
	if ($(".modal-backdrop").length === 0) {
		$('<div class="modal-backdrop fade show"></div>').appendTo(document.body);
	}
}

function closeConfirmarDesistencia() {
	const modal = $("#modalConfirmarDesistencia");
	modal.removeClass("show");
	modal.addClass("d-none");

	// Reopen previous modal
	if (previousModalId) {
		$("#" + previousModalId)
			.removeClass("d-none")
			.addClass("show");
	}
}

function confirmarDesistencia() {
	frappe.call({
		method: "gris.api.recepcao.processar_desistencia",
		args: {
			novo_associado_name: currentCardId,
		},
		callback: function (r) {
			if (!r.exc) {
				frappe.show_alert({
					message: "Desistência registrada e dados removidos.",
					indicator: "green",
				});
				window.location.reload();
			}
		},
	});
}

function enviarFilaEspera() {
	// Close current modal
	$("#modalConversaInicial").removeClass("show").addClass("d-none");

	// Open confirmation modal
	const modal = $("#modalConfirmarFilaEspera");
	modal.removeClass("d-none");
	modal.addClass("show");

	if ($(".modal-backdrop").length === 0) {
		$('<div class="modal-backdrop fade show"></div>').appendTo(document.body);
	}
}

function closeConfirmarFilaEspera() {
	const modal = $("#modalConfirmarFilaEspera");
	modal.removeClass("show");
	modal.addClass("d-none");

	// Reopen previous modal
	$("#modalConversaInicial").removeClass("d-none").addClass("show");
}

function openVisitaAgendadaModal(
	id,
	responsavel,
	nome,
	responsavelAssociado,
	ramo,
	visitaData,
	visitaConfirmada
) {
	currentCardId = id;
	$("#va_associado_nome").text(nome);
	$("#va_responsavel_nome").text(responsavelAssociado || "-");
	$("#va_ramo").val(ramo);
	$("#va_responsavel_recepcao").val(responsavel);
	$("#va_data_visita").text(visitaData || "-");

	const isConfirmed = parseInt(visitaConfirmada) === 1;

	if (isConfirmed) {
		$("#va_status_visita")
			.text("Confirmada")
			.addClass("text-success")
			.removeClass("text-muted");
		$("#btnConfirmarVisita").addClass("d-none");
		$("#btnRemoverConfirmacao").removeClass("d-none");
	} else {
		$("#va_status_visita").text("Pendente").addClass("text-muted").removeClass("text-success");
		$("#btnConfirmarVisita").removeClass("d-none");
		$("#btnRemoverConfirmacao").addClass("d-none");
	}

	const modal = $("#modalVisitaAgendada");
	modal.removeClass("d-none");
	modal.addClass("show");
	$("body").addClass("modal-open");

	if ($(".modal-backdrop").length === 0) {
		$('<div class="modal-backdrop fade show"></div>').appendTo(document.body);
	}
}

function confirmarVisitaRealizada() {
	if (!currentCardId) return;

	frappe.call({
		method: "gris.api.recepcao.confirmar_visita",
		args: {
			novo_associado_name: currentCardId,
		},
		callback: function (r) {
			if (!r.exc) {
				frappe.show_alert({ message: "Visita confirmada!", indicator: "green" });
				closeModal();
				setTimeout(() => window.location.reload(), 500);
			}
		},
	});
}

function removerConfirmacaoVisita() {
	if (!currentCardId) return;

	frappe.call({
		method: "gris.api.recepcao.remover_confirmacao_visita",
		args: {
			novo_associado_name: currentCardId,
		},
		callback: function (r) {
			if (!r.exc) {
				frappe.show_alert({ message: "Confirmação removida!", indicator: "green" });
				closeModal();
				setTimeout(() => window.location.reload(), 500);
			}
		},
	});
}

function registrarRecepcaoRealizada() {
	if (!currentCardId) return;

	frappe.call({
		method: "gris.api.recepcao.registrar_recepcao_realizada",
		args: {
			novo_associado_name: currentCardId,
		},
		callback: function (r) {
			if (!r.exc) {
				frappe.show_alert({
					message: "Recepção realizada! Movido para Aguardar Dados.",
					indicator: "green",
				});
				closeModal();
				setTimeout(() => window.location.reload(), 500);
			}
		},
	});
}

function confirmarFilaEspera() {
	frappe.call({
		method: "gris.api.recepcao.enviar_para_fila_espera",
		args: {
			novo_associado_name: currentCardId,
		},
		callback: function (r) {
			if (!r.exc) {
				frappe.show_alert({ message: "Enviado para Fila de Espera", indicator: "green" });
				window.location.reload();
			}
		},
	});
}

function openAguardarDadosModal(id, responsavel, nome, responsavelAssociado, steps) {
	currentCardId = id;
	$("#ad_associado_nome").text(nome);
	$("#ad_responsavel_nome").text(responsavelAssociado || "-");
	$("#ad_responsavel_recepcao").val(responsavel);

	// Build timeline
	const timelineContainer = $("#ad_timeline");
	timelineContainer.empty();

	// Ensure steps is an array if it came as a string (though jQuery .data usually parses it)
	if (typeof steps === "string") {
		try {
			steps = JSON.parse(steps);
		} catch (e) {
			console.error("Error parsing steps:", e);
			steps = [];
		}
	}

	// Filter steps for this specific modal (show only up to 'dados_para_registro_enviados')
	if (steps && Array.isArray(steps)) {
		const limitField = "dados_para_registro_enviados";
		const limitIndex = steps.findIndex((s) => s.field === limitField);
		if (limitIndex !== -1) {
			steps = steps.slice(0, limitIndex + 1);
		}
	}

	if (steps && steps.length > 0) {
		steps.forEach((step) => {
			const completedClass = step.completed ? "completed" : "";
			const fieldName = step.field;
			const clickAttr =
				!step.completed && fieldName
					? `onclick="toggleStep('${fieldName}', this)" style="cursor: pointer;"`
					: "";
			const hoverClass = !step.completed && fieldName ? "step-clickable" : "";

			let labelHtml = step.label;

			// Overdue check
			let dateClass = "timeline-date";
			let iconHtml = "";
			let itemExtraClass = "";
			let dateLabel = "Previsto";

			if (step.is_overdue && !step.completed) {
				dateClass = "timeline-date text-overdue font-weight-bold";
				iconHtml = ` <i class="fa fa-exclamation-triangle text-overdue" title="Atrasado"></i>`;
				itemExtraClass = "overdue";
				dateLabel = "Em atraso";
			}

			if (step.estimated_date && !step.completed) {
				labelHtml += ` <span class="${dateClass}">(${dateLabel}: ${step.estimated_date})${iconHtml}</span>`;
			}
			const html = `
                <div class="timeline-item ${completedClass} ${itemExtraClass} ${hoverClass}" ${clickAttr}>
                    <div class="timeline-marker"></div>
                    <div class="timeline-content">
                        <span class="timeline-label">${labelHtml}</span>
                        ${
							!step.completed
								? '<small class="d-block text-muted" style="font-size: 0.75rem;">Clique para marcar como concluído</small>'
								: ""
						}
                    </div>
                </div>
            `;
			timelineContainer.append(html);
		});
	} else {
		timelineContainer.html('<p class="text-muted">Nenhuma etapa encontrada.</p>');
	}

	const modal = $("#modalAguardarDados");
	modal.removeClass("d-none");
	modal.addClass("show");
	$("body").addClass("modal-open");

	if ($(".modal-backdrop").length === 0) {
		$('<div class="modal-backdrop fade show"></div>').appendTo(document.body);
	}
}

function openFazerRegistroModal(id, responsavel, nome, responsavelAssociado, steps) {
	currentCardId = id;
	$("#fr_associado_nome").text(nome);
	$("#fr_responsavel_nome").text(responsavelAssociado || "-");
	$("#fr_responsavel_recepcao").val(responsavel);

	// Build timeline
	const timelineContainer = $("#fr_timeline");
	timelineContainer.empty();

	// Ensure steps is an array if it came as a string (though jQuery .data usually parses it)
	if (typeof steps === "string") {
		try {
			steps = JSON.parse(steps);
		} catch (e) {
			console.error("Error parsing steps:", e);
			steps = [];
		}
	}

	if (steps && steps.length > 0) {
		steps.forEach((step) => {
			const completedClass = step.completed ? "completed" : "";
			const fieldName = step.field;
			const clickAttr =
				!step.completed && fieldName
					? `onclick="toggleStep('${fieldName}', this)" style="cursor: pointer;"`
					: "";
			const hoverClass = !step.completed && fieldName ? "step-clickable" : "";
			
			let labelHtml = step.label;

			// Overdue check
			let dateClass = "timeline-date";
			let iconHtml = "";
			let itemExtraClass = "";
			let dateLabel = "Previsto";

			if (step.is_overdue && !step.completed) {
				dateClass = "timeline-date text-overdue font-weight-bold";
				iconHtml = ` <i class="fa fa-exclamation-triangle text-overdue" title="Atrasado"></i>`;
				itemExtraClass = "overdue";
				dateLabel = "Em atraso";
			}

			if (step.estimated_date && !step.completed) {
				labelHtml += ` <span class="${dateClass}">(${dateLabel}: ${step.estimated_date})${iconHtml}</span>`;
			}
			const html = `
                <div class="timeline-item ${completedClass} ${itemExtraClass} ${hoverClass}" ${clickAttr}>
                    <div class="timeline-marker"></div>
                    <div class="timeline-content">
                        <span class="timeline-label">${labelHtml}</span>
                        ${
							!step.completed
								? '<small class="d-block text-muted" style="font-size: 0.75rem;">Clique para marcar como concluído</small>'
								: ""
						}
                    </div>
                </div>
            `;
			timelineContainer.append(html);
		});
	} else {
		timelineContainer.html('<p class="text-muted">Nenhuma etapa encontrada.</p>');
	}

	const modal = $("#modalFazerRegistro");
	modal.removeClass("d-none");
	modal.addClass("show");
	$("body").addClass("modal-open");

	if ($(".modal-backdrop").length === 0) {
		$('<div class="modal-backdrop fade show"></div>').appendTo(document.body);
	}
}

function confirmarRegistroCriado() {
	if (!currentCardId) return;

	frappe.call({
		method: "gris.www.recepcao.visao_geral.confirmar_registro_paxtu",
		args: {
			novo_associado_name: currentCardId,
		},
		callback: function (r) {
			if (!r.exc) {
				frappe.show_alert({
					message: "Registro confirmado e movido para Acompanhamento",
					indicator: "green",
				});
				closeModal();
				setTimeout(() => window.location.reload(), 1500);
			}
		},
	});
}

function openAcompanhamentoModal(id, responsavel, nome, responsavelAssociado, steps) {
	currentCardId = id;
	$("#ac_associado_nome").text(nome);
	$("#ac_responsavel_nome").text(responsavelAssociado || "-");
	$("#ac_responsavel_recepcao").val(responsavel);

	// Build timeline
	const timelineContainer = $("#ac_timeline");
	timelineContainer.empty();

	// Ensure steps is an array if it came as a string (though jQuery .data usually parses it)
	if (typeof steps === "string") {
		try {
			steps = JSON.parse(steps);
		} catch (e) {
			console.error("Error parsing steps:", e);
			steps = [];
		}
	}

	if (steps && steps.length > 0) {
		let allCompleted = true;

		steps.forEach((step) => {
			if (!step.completed) allCompleted = false;
			const completedClass = step.completed ? "completed" : "";
			// Backend now sends 'field' in the step object
			const fieldName = step.field;

			// Only add click handler if not completed and we have a field mapping
			const clickAttr =
				!step.completed && fieldName
					? `onclick="toggleStep('${fieldName}', this)" style="cursor: pointer;"`
					: "";
			const hoverClass = !step.completed && fieldName ? "step-clickable" : "";

			let labelHtml = step.label;

			// Overdue check
			let dateClass = "timeline-date";
			let iconHtml = "";
			let itemExtraClass = "";
			let dateLabel = "Previsto";

			if (step.is_overdue && !step.completed) {
				dateClass = "timeline-date text-overdue font-weight-bold";
				iconHtml = ` <i class="fa fa-exclamation-triangle text-overdue" title="Atrasado"></i>`;
				itemExtraClass = "overdue";
				dateLabel = "Em atraso";
			}

			if (step.estimated_date && !step.completed) {
				labelHtml += ` <span class="${dateClass}">(${dateLabel}: ${step.estimated_date})${iconHtml}</span>`;
			}

			const html = `
                <div class="timeline-item ${completedClass} ${itemExtraClass} ${hoverClass}" ${clickAttr}>
                    <div class="timeline-marker"></div>
                    <div class="timeline-content">
                        <span class="timeline-label">${labelHtml}</span>
                        ${
							!step.completed
								? '<small class="d-block text-muted" style="font-size: 0.75rem;">Clique para marcar como concluído</small>'
								: ""
						}
                    </div>
                </div>
            `;
			timelineContainer.append(html);
		});

		// Check if we need to show the Finalize button
		const modalActions = $("#modalAcompanhamento .modal-actions-vertical");
		// Remove existing finish button if persists (though modal content is static usually, better safe)
		modalActions.find("#btnFinalizarRecepcao").remove();

		if (allCompleted) {
			const finishBtn = `
				<button 
					type="button" 
					class="btn-modern btn-modern--success" 
					id="btnFinalizarRecepcao"
					onclick="finalizarRecepcao()"
					style="margin-bottom: 0.5rem;"
				>
					Finalizar Recepção
				</button>
			`;
			modalActions.prepend(finishBtn);
		}

	} else {
		timelineContainer.html('<p class="text-muted">Nenhuma etapa encontrada.</p>');
	}

	const modal = $("#modalAcompanhamento");
	modal.removeClass("d-none");
	modal.addClass("show");
	$("body").addClass("modal-open");

	if ($(".modal-backdrop").length === 0) {
		$('<div class="modal-backdrop fade show"></div>').appendTo(document.body);
	}
}

function toggleStep(field, element) {
	if (!currentCardId || !field) return;

	frappe.confirm("Deseja marcar esta etapa como concluída?", () => {
		frappe.call({
			method: "gris.www.recepcao.visao_geral.update_step_status",
			args: {
				novo_associado_name: currentCardId,
				field: field,
				value: 1,
			},
			callback: function (r) {
				if (!r.exc) {
					frappe.show_alert({ message: "Etapa atualizada", indicator: "green" });
					// Update UI immediately
					$(element)
						.addClass("completed")
						.removeAttr("onclick")
						.css("cursor", "default")
						.removeClass("step-clickable");
					$(element).find("small").remove();

					// Reload page after short delay to refresh all data
					setTimeout(() => window.location.reload(), 1000);
				}
			},
		});
	});
}

function finalizarRecepcao() {
	if (!currentCardId) return;

	frappe.confirm(
		"Tem certeza? Isso vinculará o Responsável ao Associado, anonimizará os dados do Responsável e excluirá o Novo Associado.",
		() => {
			frappe.call({
				method: "gris.www.recepcao.visao_geral.finalizar_processo_recepcao",
				args: {
					novo_associado_name: currentCardId,
				},
				freeze: true,
				freeze_message: "Finalizando...",
				callback: function (r) {
					if (!r.exc) {
						frappe.show_alert({ message: "Recepção finalizada com sucesso!", indicator: "green" });
						closeModal();
						setTimeout(() => window.location.reload(), 1000);
					}
				},
			});
		}
	);
}

// Expose functions to global scope for onclick handlers
window.moverParaConversaInicial = moverParaConversaInicial;
window.openFicha = openFicha;
window.openAgendarVisita = openAgendarVisita;
window.closeAgendarVisita = closeAgendarVisita;
window.confirmarAgendamento = confirmarAgendamento;
window.registrarDesistencia = registrarDesistencia;
window.confirmarRegistroCriado = confirmarRegistroCriado;
window.toggleStep = toggleStep;
window.closeConfirmarDesistencia = closeConfirmarDesistencia;
window.confirmarDesistencia = confirmarDesistencia;
window.enviarFilaEspera = enviarFilaEspera;
window.closeConfirmarFilaEspera = closeConfirmarFilaEspera;
window.confirmarFilaEspera = confirmarFilaEspera;
window.removerConfirmacaoVisita = removerConfirmacaoVisita;
window.registrarRecepcaoRealizada = registrarRecepcaoRealizada;
window.finalizarRecepcao = finalizarRecepcao;
