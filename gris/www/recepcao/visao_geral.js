// Visão Geral da Recepção — interações cliente
// Usa exclusivamente o design system Basecoat: <dialog> HTML5 + componente select.

let currentCardId = null;
let previousModalId = null;
let currentWhatsappContatos = [];
let currentCardElement = null;
let whatsappSourceModalId = null;

// ---------- Helpers de dialog ---------------------------------------------

function openDialog(id) {
	const el = document.getElementById(id);
	if (!el || typeof el.showModal !== "function" || el.open) return;
	try {
		el.showModal();
	} catch (err) {
		console.error(`Falha ao abrir dialog "${id}":`, err);
		frappe.show_alert({
			message: "Não foi possível abrir o modal. Recarregue a página.",
			indicator: "red",
		});
	}
}

function closeDialog(id) {
	const el = document.getElementById(id);
	if (el && el.open) el.close();
}

function closeAllDialogs() {
	document.querySelectorAll("dialog[open]").forEach((d) => d.close());
}

function getOpenDialogId(exceptId) {
	const open = Array.from(document.querySelectorAll("dialog[open]")).find(
		(d) => !exceptId || d.id !== exceptId
	);
	return open ? open.id : null;
}

// ---------- Helpers de select Basecoat ------------------------------------

function getSelectValue(id) {
	const el = document.getElementById(id);
	if (!el) return "";
	if ("value" in el) {
		const v = el.value;
		return v == null ? "" : String(v);
	}
	const hidden = el.querySelector('input[type="hidden"]');
	return hidden ? hidden.value : "";
}

// Define o valor do select Basecoat sem disparar `change` (evita
// callbacks de salvamento ao apenas exibir um valor existente).
function setSelectValue(id, value) {
	const el = document.getElementById(id);
	if (!el) return;
	const target = value == null ? "" : String(value);
	const options = Array.from(el.querySelectorAll('[role="option"]'));
	const matched = options.find(
		(opt) => (opt.dataset.value ?? opt.textContent.trim()) === target
	);
	const hidden = el.querySelector('input[type="hidden"]');
	const triggerLabel = el.querySelector(":scope > button > span");

	options.forEach((opt) => opt.removeAttribute("aria-selected"));

	if (matched) {
		matched.setAttribute("aria-selected", "true");
		if (hidden) hidden.value = target;
		if (triggerLabel) triggerLabel.innerHTML = matched.innerHTML;
	} else {
		if (hidden) hidden.value = "";
		if (triggerLabel) {
			triggerLabel.textContent = el.dataset.placeholder || "Selecione…";
		}
	}
}

// Repopula um select Basecoat com novos items.
// items: [{label: "...", value: "..."}, ...]
//
// Estratégia: reconstruir o listbox + clonar o nó. O MutationObserver do
// Basecoat detecta o clone como nó novo e só inicializa ele (não pode
// chamar `basecoat.init('select')` porque isso tenta redefinir a
// propriedade `value` em selects já inicializados, e ela é non-configurable).
function repopulateSelect(id, items, selectedValue) {
	const oldEl = document.getElementById(id);
	if (!oldEl) return;

	const listbox = oldEl.querySelector('[role="listbox"]');
	const hidden = oldEl.querySelector('input[type="hidden"]');
	const triggerLabel = oldEl.querySelector(":scope > button > span");
	if (!listbox || !hidden || !triggerLabel) return;

	listbox.innerHTML = "";
	(items || []).forEach((item, index) => {
		const opt = document.createElement("div");
		opt.id = `${id}-items-${index + 1}`;
		opt.setAttribute("role", "option");
		opt.dataset.value = item.value;
		opt.textContent = item.label;
		listbox.appendChild(opt);
	});

	hidden.value = "";
	triggerLabel.textContent = oldEl.dataset.placeholder || "Selecione…";

	const newEl = oldEl.cloneNode(true);
	newEl.removeAttribute("data-select-initialized");
	oldEl.parentNode.replaceChild(newEl, oldEl);

	if (selectedValue !== undefined && selectedValue !== null && selectedValue !== "") {
		setSelectValue(id, selectedValue);
	}
}

// ---------- Listeners globais ---------------------------------------------

frappe.ready(function () {
	// Botão "Fechar" dos dialogs (atributo data-dialog-close)
	document.addEventListener("click", function (event) {
		const closer = event.target.closest("[data-dialog-close]");
		if (closer) {
			const dlg = closer.closest("dialog");
			if (dlg && dlg.open) dlg.close();
		}
	});

	// Não limpamos `currentCardId`/`currentCardElement` aqui porque o stack
	// de modais (fechar pai → abrir filho) deixaria o estado nulo entre os
	// passos. Esses valores são sobrescritos no próximo clique de card.

	// Clique no card → abre o modal correto
	document.querySelectorAll(".kanban-card").forEach((cardEl) => {
		cardEl.addEventListener("click", function (e) {
			e.preventDefault();
			currentCardElement = cardEl;
			const id = cardEl.dataset.id;
			const status = cardEl.dataset.status;
			const responsavel = cardEl.dataset.responsavel || "";
			const nome = cardEl.dataset.nome || "";
			const responsavelAssociado = cardEl.dataset.responsavelAssociado || "";
			const ramo = cardEl.dataset.ramo || "";
			const visitaData = cardEl.dataset.visitaData || "";
			const visitaConfirmada = cardEl.dataset.visitaConfirmada || "0";
			const steps = cardEl.dataset.steps || "[]";

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
				window.location.href = `/recepcao/detalhes?id=${id}`;
			}
		});
	});

	// ----- Listeners dos selects (CustomEvent change com detail.value) -----
	const responsavelSelect = document.getElementById("responsavelRecepcao");
	if (responsavelSelect) {
		responsavelSelect.addEventListener("change", function (e) {
			const value = e.detail ? e.detail.value : getSelectValue("responsavelRecepcao");
			const btn = document.getElementById("btnMoverConversa");
			if (value) {
				if (btn) btn.disabled = false;
				if (currentCardId) saveResponsavel(currentCardId, value);
			} else if (btn) {
				btn.disabled = true;
			}
		});
	}

	bindRamoSelect("ci_ramo");
	bindRamoSelect("va_ramo");

	bindResponsavelSelect("va_responsavel_recepcao");
	bindResponsavelSelect("ad_responsavel_recepcao");
	bindResponsavelSelect("fr_responsavel_recepcao");
	bindResponsavelSelect("ac_responsavel_recepcao");
	bindResponsavelSelect("ci_responsavel_acompanhamento");

	// Botão "Conversar no WhatsApp" no chooser
	const btnAbrirWhatsapp = document.getElementById("btnAbrirWhatsappContato");
	if (btnAbrirWhatsapp) {
		btnAbrirWhatsapp.addEventListener("click", function () {
			const selectedValue = getSelectValue("whatsappContatoSelect");
			if (!selectedValue) {
				frappe.msgprint("Selecione um responsável.");
				return;
			}
			const idx = Number(selectedValue);
			const contato = currentWhatsappContatos[idx];
			if (!contato || !contato.telefone) {
				frappe.msgprint("Selecione um responsável.");
				return;
			}
			openWhatsapp(contato.telefone);
			closeEscolherResponsavelWhatsapp();
		});
	}
});

function bindRamoSelect(id) {
	const el = document.getElementById(id);
	if (!el) return;
	el.addEventListener("change", function (e) {
		const ramo = e.detail ? e.detail.value : getSelectValue(id);
		if (!ramo || !currentCardId) return;
		frappe.call({
			method: "gris.api.recepcao.update_novo_associado",
			args: { name: currentCardId, ramo: ramo },
			callback: function (r) {
				if (!r.exc) {
					const card = document.querySelector(`.kanban-card[data-id="${currentCardId}"]`);
					if (card) card.dataset.ramo = ramo;
					frappe.show_alert({ message: "Ramo atualizado", indicator: "green" });
				}
			},
		});
	});
}

function bindResponsavelSelect(id) {
	const el = document.getElementById(id);
	if (!el) return;
	el.addEventListener("change", function (e) {
		const value = e.detail ? e.detail.value : getSelectValue(id);
		if (currentCardId && value) saveResponsavel(currentCardId, value);
	});
}

// ---------- Abertura dos modais por status --------------------------------

function openModal(id, responsavel, nome, responsavelAssociado, ramo) {
	currentCardId = id;
	updateWhatsappButtonState();
	document.getElementById("modalAssociadoNome").textContent = nome;
	document.getElementById("modalResponsavelNome").textContent = responsavelAssociado || "-";
	document.getElementById("modalRamo").textContent = ramo || "-";
	setSelectValue("responsavelRecepcao", responsavel);

	const btn = document.getElementById("btnMoverConversa");
	if (btn) btn.disabled = !responsavel;

	openDialog("modalNovoContato");
}

function openConversaInicialModal(id, responsavel, nome, responsavelAssociado, ramo) {
	currentCardId = id;
	updateWhatsappButtonState();
	document.getElementById("ci_associado_nome").textContent = nome;
	document.getElementById("ci_responsavel_nome").textContent = responsavelAssociado || "-";
	setSelectValue("ci_ramo", ramo);
	setSelectValue("ci_responsavel_acompanhamento", responsavel);

	openDialog("modalConversaInicial");
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
	updateWhatsappButtonState();
	document.getElementById("va_associado_nome").textContent = nome;
	document.getElementById("va_responsavel_nome").textContent = responsavelAssociado || "-";
	setSelectValue("va_ramo", ramo);
	setSelectValue("va_responsavel_recepcao", responsavel);
	document.getElementById("va_data_visita").textContent = visitaData || "-";

	const isConfirmed = parseInt(visitaConfirmada, 10) === 1;
	const statusEl = document.getElementById("va_status_visita");
	statusEl.innerHTML = isConfirmed
		? '<span class="badge badge-success">Confirmada</span>'
		: '<span class="badge">Pendente</span>';

	const btnConfirmar = document.getElementById("btnConfirmarVisita");
	const btnRemover = document.getElementById("btnRemoverConfirmacao");
	if (isConfirmed) {
		btnConfirmar.classList.add("hidden");
		btnRemover.classList.remove("hidden");
	} else {
		btnConfirmar.classList.remove("hidden");
		btnRemover.classList.add("hidden");
	}

	openDialog("modalVisitaAgendada");
}

function openAguardarDadosModal(id, responsavel, nome, responsavelAssociado, steps) {
	currentCardId = id;
	updateWhatsappButtonState();
	document.getElementById("ad_associado_nome").textContent = nome;
	document.getElementById("ad_responsavel_nome").textContent = responsavelAssociado || "-";
	setSelectValue("ad_responsavel_recepcao", responsavel);

	let parsedSteps = parseSteps(steps);
	const limit = parsedSteps.findIndex((s) => s.field === "dados_para_registro_enviados");
	if (limit !== -1) parsedSteps = parsedSteps.slice(0, limit + 1);

	renderTimeline("ad_timeline", parsedSteps);
	openDialog("modalAguardarDados");
}

function openFazerRegistroModal(id, responsavel, nome, responsavelAssociado, steps) {
	currentCardId = id;
	updateWhatsappButtonState();
	document.getElementById("fr_associado_nome").textContent = nome;
	document.getElementById("fr_responsavel_nome").textContent = responsavelAssociado || "-";
	setSelectValue("fr_responsavel_recepcao", responsavel);

	const parsedSteps = parseSteps(steps);
	renderTimeline("fr_timeline", parsedSteps);

	openDialog("modalFazerRegistro");
}

function openAcompanhamentoModal(id, responsavel, nome, responsavelAssociado, steps) {
	currentCardId = id;
	updateWhatsappButtonState();
	document.getElementById("ac_associado_nome").textContent = nome;
	document.getElementById("ac_responsavel_nome").textContent = responsavelAssociado || "-";
	setSelectValue("ac_responsavel_recepcao", responsavel);

	const parsedSteps = parseSteps(steps);
	renderTimeline("ac_timeline", parsedSteps);

	const actions = document.getElementById("ac_actions");
	const existingFinish = document.getElementById("btnFinalizarRecepcao");
	if (existingFinish) existingFinish.remove();

	const allCompleted = parsedSteps.length > 0 && parsedSteps.every((s) => s.completed);
	if (allCompleted && actions) {
		const finishBtn = document.createElement("button");
		finishBtn.type = "button";
		finishBtn.className = "btn-primary";
		finishBtn.id = "btnFinalizarRecepcao";
		finishBtn.textContent = "Finalizar Recepção";
		finishBtn.addEventListener("click", finalizarRecepcao);
		actions.prepend(finishBtn);
	}

	openDialog("modalAcompanhamento");
}

// ---------- Timeline -------------------------------------------------------

function parseSteps(steps) {
	if (Array.isArray(steps)) return steps;
	if (typeof steps !== "string") return [];
	try {
		return JSON.parse(steps) || [];
	} catch (e) {
		console.error("Erro ao interpretar steps:", e);
		return [];
	}
}

function renderTimeline(containerId, steps) {
	const container = document.getElementById(containerId);
	if (!container) return;
	container.innerHTML = "";

	if (!steps || steps.length === 0) {
		container.innerHTML = '<p class="text-muted-foreground">Nenhuma etapa encontrada.</p>';
		return;
	}

	const overdueSvg =
		' <svg class="ds-lucide ds-lucide--sm text-overdue inline-block align-text-bottom" viewBox="0 0 24 24" aria-hidden="true"><use href="/assets/gris/design_system/icons/lucide/sprite.svg#triangle-alert"/></svg>';

	steps.forEach((step) => {
		const completed = !!step.completed;
		const overdue = !!step.is_overdue && !completed;
		const fieldName = step.field;
		const clickable = !completed && fieldName;

		let dateClass = "timeline-date";
		let iconHtml = "";
		let dateLabel = "Previsto";
		let itemExtraClass = "";

		if (overdue) {
			dateClass = "timeline-date text-overdue";
			iconHtml = overdueSvg;
			itemExtraClass = "overdue";
			dateLabel = "Em atraso";
		}

		let labelHtml = escapeHtml(step.label);
		if (step.estimated_date && !completed) {
			labelHtml += ` <span class="${dateClass}">(${dateLabel}: ${escapeHtml(
				step.estimated_date
			)})${iconHtml}</span>`;
		}

		const item = document.createElement("div");
		item.className = [
			"timeline-item",
			completed ? "completed" : "",
			itemExtraClass,
			clickable ? "step-clickable" : "",
		]
			.filter(Boolean)
			.join(" ");

		if (clickable) {
			item.addEventListener("click", () => toggleStep(fieldName, item));
		}

		item.innerHTML = `
			<div class="timeline-marker"></div>
			<div class="timeline-content">
				<span class="timeline-label">${labelHtml}</span>
				${
					!completed
						? '<small class="timeline-helper">Clique para marcar como concluído</small>'
						: ""
				}
			</div>
		`;

		container.appendChild(item);
	});
}

function escapeHtml(value) {
	if (value == null) return "";
	return String(value)
		.replace(/&/g, "&amp;")
		.replace(/</g, "&lt;")
		.replace(/>/g, "&gt;")
		.replace(/"/g, "&quot;")
		.replace(/'/g, "&#39;");
}

// ---------- Operações de negócio ------------------------------------------

function saveResponsavel(id, responsavel) {
	frappe.call({
		method: "gris.api.recepcao.update_novo_associado",
		args: { name: id, responsavel_recepcao: responsavel },
		callback: function (r) {
			if (!r.exc) {
				const card = document.querySelector(`.kanban-card[data-id="${id}"]`);
				if (card) card.dataset.responsavel = responsavel;
				frappe.show_alert({ message: "Responsável atualizado", indicator: "green" });
			}
		},
	});
}

function moverParaConversaInicial() {
	if (!currentCardId) return;
	frappe.call({
		method: "gris.api.recepcao.update_novo_associado",
		args: { name: currentCardId, status: "Conversa Inicial" },
		callback: function (r) {
			if (!r.exc) {
				frappe.show_alert({ message: "Movido para Conversa Inicial", indicator: "green" });
				closeAllDialogs();
				setTimeout(() => window.location.reload(), 500);
			}
		},
	});
}

function openFicha() {
	if (currentCardId) window.location.href = `/recepcao/ficha_registro?name=${currentCardId}`;
}

function openAgendarVisita() {
	const ramo =
		(currentCardElement && currentCardElement.dataset.ramo) ||
		getSelectValue("ci_ramo") ||
		getSelectValue("va_ramo");

	if (!ramo) {
		frappe.show_alert({
			message: "Defina o Ramo antes de agendar.",
			indicator: "orange",
		});
		return;
	}

	previousModalId = getOpenDialogId("modalAgendarVisita");
	if (previousModalId) closeDialog(previousModalId);

	repopulateSelect("av_data", [{ label: "Carregando…", value: "" }], "");
	openDialog("modalAgendarVisita");

	frappe.call({
		method: "gris.www.recepcao.agenda_visitas.get_available_dates_for_ramo",
		args: { ramo: ramo },
		callback: function (r) {
			const items = (r.message || []).map((d) => ({ label: d.label, value: d.value }));
			if (items.length === 0) {
				repopulateSelect("av_data", [{ label: "Nenhuma data disponível", value: "" }], "");
			} else {
				repopulateSelect("av_data", items, "");
			}
		},
	});
}

function closeAgendarVisita() {
	closeDialog("modalAgendarVisita");
	if (previousModalId) {
		const prev = previousModalId;
		previousModalId = null;
		openDialog(prev);
	}
}

function confirmarAgendamento() {
	const date = getSelectValue("av_data");
	if (!date) {
		frappe.msgprint("Selecione uma data.");
		return;
	}
	frappe.call({
		method: "gris.www.recepcao.agenda_visitas.schedule_visit",
		args: { associate: currentCardId, date: date },
		callback: function (r) {
			if (!r.exc) {
				frappe.show_alert({ message: "Visita agendada com sucesso!", indicator: "green" });
				closeAllDialogs();
				setTimeout(() => window.location.reload(), 1000);
			}
		},
	});
}

function resetDesistenciaModal() {
	const conteudo = document.getElementById("desistencia_conteudo");
	const loading = document.getElementById("desistencia_loading");
	const erro = document.getElementById("desistencia_erro");
	const btnConfirmar = document.getElementById("btnConfirmarDesistencia");
	const btnCancelar = document.getElementById("btnCancelarDesistencia");
	if (conteudo) conteudo.classList.remove("hidden");
	if (loading) loading.classList.add("hidden");
	if (erro) erro.classList.add("hidden");
	if (btnConfirmar) btnConfirmar.disabled = false;
	if (btnCancelar) btnCancelar.disabled = false;
}

function registrarDesistencia() {
	previousModalId = getOpenDialogId("modalConfirmarDesistencia");
	if (previousModalId) closeDialog(previousModalId);
	resetDesistenciaModal();
	openDialog("modalConfirmarDesistencia");
}

function closeConfirmarDesistencia() {
	closeDialog("modalConfirmarDesistencia");
	resetDesistenciaModal();
	if (previousModalId) {
		const prev = previousModalId;
		previousModalId = null;
		openDialog(prev);
	}
}

function confirmarDesistencia() {
	const conteudo = document.getElementById("desistencia_conteudo");
	const loading = document.getElementById("desistencia_loading");
	const erro = document.getElementById("desistencia_erro");
	const btnConfirmar = document.getElementById("btnConfirmarDesistencia");
	const btnCancelar = document.getElementById("btnCancelarDesistencia");

	if (conteudo) conteudo.classList.add("hidden");
	if (erro) erro.classList.add("hidden");
	if (loading) loading.classList.remove("hidden");
	if (btnConfirmar) btnConfirmar.disabled = true;
	if (btnCancelar) btnCancelar.disabled = true;

	frappe.call({
		method: "gris.api.recepcao.processar_desistencia",
		args: { novo_associado_name: currentCardId },
		callback: function (r) {
			if (!r.exc) {
				frappe.show_alert({
					message: "Desistência registrada e dados removidos.",
					indicator: "green",
				});
				window.location.reload();
			}
		},
		error: function () {
			if (loading) loading.classList.add("hidden");
			if (erro) erro.classList.remove("hidden");
			if (btnCancelar) btnCancelar.disabled = false;
		},
	});
}

function enviarFilaEspera() {
	previousModalId = getOpenDialogId("modalConfirmarFilaEspera");
	if (previousModalId) closeDialog(previousModalId);
	openDialog("modalConfirmarFilaEspera");
}

function closeConfirmarFilaEspera() {
	closeDialog("modalConfirmarFilaEspera");
	if (previousModalId) {
		const prev = previousModalId;
		previousModalId = null;
		openDialog(prev);
	}
}

function confirmarFilaEspera() {
	frappe.call({
		method: "gris.api.recepcao.enviar_para_fila_espera",
		args: { novo_associado_name: currentCardId },
		callback: function (r) {
			if (!r.exc) {
				frappe.show_alert({ message: "Enviado para Fila de Espera", indicator: "green" });
				window.location.reload();
			}
		},
	});
}

function confirmarVisitaRealizada() {
	if (!currentCardId) return;
	frappe.call({
		method: "gris.api.recepcao.confirmar_visita",
		args: { novo_associado_name: currentCardId },
		callback: function (r) {
			if (!r.exc) {
				frappe.show_alert({ message: "Visita confirmada!", indicator: "green" });
				closeAllDialogs();
				setTimeout(() => window.location.reload(), 500);
			}
		},
	});
}

function removerConfirmacaoVisita() {
	if (!currentCardId) return;
	frappe.call({
		method: "gris.api.recepcao.remover_confirmacao_visita",
		args: { novo_associado_name: currentCardId },
		callback: function (r) {
			if (!r.exc) {
				frappe.show_alert({ message: "Confirmação removida!", indicator: "green" });
				closeAllDialogs();
				setTimeout(() => window.location.reload(), 500);
			}
		},
	});
}

function registrarRecepcaoRealizada() {
	if (!currentCardId) return;
	frappe.call({
		method: "gris.api.recepcao.registrar_recepcao_realizada",
		args: { novo_associado_name: currentCardId },
		callback: function (r) {
			if (!r.exc) {
				frappe.show_alert({
					message: "Recepção realizada! Movido para Aguardar Dados.",
					indicator: "green",
				});
				closeAllDialogs();
				setTimeout(() => window.location.reload(), 500);
			}
		},
	});
}

function confirmarRegistroCriado() {
	if (!currentCardId) return;
	frappe.call({
		method: "gris.www.recepcao.visao_geral.confirmar_registro_paxtu",
		args: { novo_associado_name: currentCardId },
		callback: function (r) {
			if (!r.exc) {
				frappe.show_alert({
					message: "Registro confirmado e movido para Acompanhamento",
					indicator: "green",
				});
				closeAllDialogs();
				setTimeout(() => window.location.reload(), 1500);
			}
		},
	});
}

function toggleStep(field, element) {
	if (!currentCardId || !field) return;
	frappe.call({
		method: "gris.www.recepcao.visao_geral.update_step_status",
		args: { novo_associado_name: currentCardId, field: field, value: 1 },
		callback: function (r) {
			if (!r.exc) {
				frappe.show_alert({ message: "Etapa atualizada", indicator: "green" });
				if (element) {
					element.classList.add("completed");
					element.classList.remove("step-clickable");
					const helper = element.querySelector(".timeline-helper");
					if (helper) helper.remove();
				}
				setTimeout(() => window.location.reload(), 1000);
			}
		},
	});
}

function finalizarRecepcao() {
	if (!currentCardId) return;
	const ok = window.confirm(
		"Tem certeza? Isso vinculará o Responsável ao Associado, anonimizará os dados do Responsável e excluirá o Novo Associado."
	);
	if (!ok) return;
	frappe.call({
		method: "gris.www.recepcao.visao_geral.finalizar_processo_recepcao",
		args: { novo_associado_name: currentCardId },
		freeze: true,
		freeze_message: "Finalizando…",
		callback: function (r) {
			if (!r.exc) {
				frappe.show_alert({
					message: "Recepção finalizada com sucesso!",
					indicator: "green",
				});
				closeAllDialogs();
				setTimeout(() => window.location.reload(), 1000);
			}
		},
	});
}

// ---------- WhatsApp -------------------------------------------------------

function updateWhatsappButtonState() {
	if (!currentCardElement) return;
	const disponivel = parseInt(currentCardElement.dataset.whatsappDisponivel, 10) === 1;
	const motivo =
		currentCardElement.dataset.whatsappMotivo || "Sem telefone de responsável para contato.";

	document.querySelectorAll(".js-whatsapp-modal-btn").forEach((btn) => {
		btn.disabled = !disponivel;
		btn.title = disponivel ? "" : motivo;
	});
}

function falarComResponsavelAtual() {
	if (!currentCardElement) {
		frappe.msgprint("Nenhum associado selecionado.");
		return;
	}

	const disponivel = parseInt(currentCardElement.dataset.whatsappDisponivel, 10) === 1;
	const motivo = currentCardElement.dataset.whatsappMotivo;

	if (!disponivel) {
		frappe.msgprint(motivo || "Sem telefone de responsável para contato.");
		return;
	}

	let contatos = currentCardElement.dataset.whatsappContatos || "[]";
	try {
		contatos = JSON.parse(contatos);
	} catch (err) {
		contatos = [];
	}
	contatos = normalizeWhatsappContatos(contatos);

	if (contatos.length === 0) {
		frappe.msgprint("Sem telefone de responsável para contato.");
		return;
	}

	if (contatos.length === 1) {
		openWhatsapp(contatos[0].telefone);
		return;
	}

	openEscolherResponsavelWhatsapp(contatos);
}

function normalizeWhatsappContatos(contatos) {
	if (Array.isArray(contatos)) {
		return contatos.filter((c) => c && c.telefone);
	}
	if (contatos && typeof contatos === "object") {
		return Object.values(contatos).filter((c) => c && c.telefone);
	}
	return [];
}

function openWhatsapp(phone) {
	const numero = String(phone || "").replace(/\D/g, "");
	if (!numero) {
		frappe.msgprint("Telefone do responsável inválido.");
		return;
	}
	window.open(`https://wa.me/${numero}`, "_blank", "noopener,noreferrer");
}

function openEscolherResponsavelWhatsapp(contatos) {
	currentWhatsappContatos = normalizeWhatsappContatos(contatos);

	whatsappSourceModalId = getOpenDialogId("modalEscolherResponsavelWhatsapp");
	if (whatsappSourceModalId) closeDialog(whatsappSourceModalId);

	const items = currentWhatsappContatos.map((contato, index) => ({
		label: contato.is_guardiao_legal ? `${contato.nome} (Responsável legal)` : contato.nome,
		value: String(index),
	}));

	repopulateSelect("whatsappContatoSelect", items, "");
	openDialog("modalEscolherResponsavelWhatsapp");
}

function closeEscolherResponsavelWhatsapp() {
	closeDialog("modalEscolherResponsavelWhatsapp");
	if (whatsappSourceModalId) {
		const prev = whatsappSourceModalId;
		whatsappSourceModalId = null;
		openDialog(prev);
	}
	currentWhatsappContatos = [];
}

// ---------- Expor funções para handlers onclick=... ------------------------

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
window.confirmarVisitaRealizada = confirmarVisitaRealizada;
window.removerConfirmacaoVisita = removerConfirmacaoVisita;
window.registrarRecepcaoRealizada = registrarRecepcaoRealizada;
window.finalizarRecepcao = finalizarRecepcao;
window.falarComResponsavelAtual = falarComResponsavelAtual;
window.closeEscolherResponsavelWhatsapp = closeEscolherResponsavelWhatsapp;
