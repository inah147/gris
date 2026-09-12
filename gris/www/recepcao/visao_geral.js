// Visão Geral da Recepção — interações cliente
// Usa exclusivamente o design system Basecoat: <dialog> HTML5 + componente select.

let currentCardId = null;
let previousModalId = null;
let currentWhatsappContatos = [];
let currentCardElement = null;
let whatsappSourceModalId = null;

// As duas listas de acompanhamento são o mesmo status "Acompanhamento" no banco,
// separado por gris.api.recepcao_funil.coluna_de_acompanhamento. Aqui elas só
// precisam abrir o mesmo dialog. Mantenha em sincronia com
// COLUNAS_DE_ACOMPANHAMENTO no Python.
const COLUNAS_DE_ACOMPANHAMENTO = ["Acompanhamento Provisório", "Acompanhamento Definitivo"];

// Etapas que exigem o número de registro antes de serem marcadas
// (gris.api.recepcao_funil.CAMPOS_DE_EFETIVACAO).
const CAMPOS_DE_EFETIVACAO = ["registro_provisorio_efetivado", "registro_definitivo_efetivado"];

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

// ---------- Filtros do cabeçalho -------------------------------------------

// Filtram os cards já renderizados pelo servidor (nenhuma ida ao backend).
// Precisa espelhar RAMO_FILTRO_SEM_RAMO em visao_geral.py.
const RAMO_FILTRO_SEM_RAMO = "__sem_ramo__";
const RAMO_FILTRO_STORAGE_KEY = "recepcao:visao_geral:filtro_ramo";
const NOME_FILTRO_STORAGE_KEY = "recepcao:visao_geral:filtro_nome";

function lerFiltroSalvo(chave) {
	// Várias ações da página recarregam a tela; sem isso o filtro se perderia.
	try {
		return sessionStorage.getItem(chave) || "";
	} catch (err) {
		return "";
	}
}

function salvarFiltro(chave, valor) {
	try {
		if (valor) {
			sessionStorage.setItem(chave, valor);
		} else {
			sessionStorage.removeItem(chave);
		}
	} catch (err) {
		// sessionStorage indisponível (aba privada): filtro segue funcionando.
	}
}

// "José" e "jose" precisam se encontrar: quem busca digita sem acento e sem caixa.
function normalizarTexto(valor) {
	return String(valor || "")
		.normalize("NFD")
		.replace(/\p{Diacritic}/gu, "")
		.toLowerCase()
		.trim();
}

function cardVisivelNoFiltro(card, filtroRamo, filtroNome) {
	if (filtroRamo) {
		const ramo = card.dataset.ramo || "";
		const combina = filtroRamo === RAMO_FILTRO_SEM_RAMO ? !ramo : ramo === filtroRamo;
		if (!combina) return false;
	}

	if (filtroNome && !normalizarTexto(card.dataset.nome).includes(filtroNome)) {
		return false;
	}

	return true;
}

function aplicarFiltros() {
	const filtroRamo = getSelectValue("filtroRamo");
	const campoNome = document.getElementById("filtroNome");
	const filtroNome = normalizarTexto(campoNome ? campoNome.value : "");
	const temFiltro = Boolean(filtroRamo || filtroNome);

	document.querySelectorAll(".kanban-column").forEach((coluna) => {
		let visiveis = 0;

		coluna.querySelectorAll(".kanban-card").forEach((card) => {
			const visivel = cardVisivelNoFiltro(card, filtroRamo, filtroNome);
			card.classList.toggle("filter-hidden", !visivel);
			if (visivel) visiveis += 1;
		});

		const contador = coluna.querySelector(".js-column-count");
		if (contador) contador.textContent = String(visiveis);

		// A mensagem só faz sentido quando um filtro escondeu tudo; sem filtro,
		// uma coluna vazia continua vazia como antes.
		const vazio = coluna.querySelector(".kanban-column__vazio");
		if (vazio) vazio.classList.toggle("hidden", !temFiltro || visiveis > 0);
	});
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

	// Balão de observações do card: atalho direto, sem passar pelo modal de status.
	// Precisa de stopPropagation, senão o listener do card abre os dois.
	document.querySelectorAll(".js-observacoes-badge").forEach((botao) => {
		botao.addEventListener("click", function (e) {
			e.preventDefault();
			e.stopPropagation();
			const cardEl = botao.closest(".kanban-card");
			if (!cardEl) return;
			currentCardElement = cardEl;
			currentCardId = cardEl.dataset.id;
			abrirObservacoes();
		});
	});

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
			const reagendamentoPendente = cardEl.dataset.reagendamentoPendente === "1";
			const reagendamentoData = cardEl.dataset.reagendamentoData || "";
			const steps = cardEl.dataset.steps || "[]";

			if (status === "Novo Contato") {
				openModal(id, responsavel, nome, responsavelAssociado, ramo);
			} else if (status === "Conversa Inicial") {
				openConversaInicialModal(
					id,
					responsavel,
					nome,
					responsavelAssociado,
					ramo,
					reagendamentoPendente,
					reagendamentoData
				);
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
			} else if (COLUNAS_DE_ACOMPANHAMENTO.includes(status)) {
				openAcompanhamentoModal(
					id,
					responsavel,
					nome,
					responsavelAssociado,
					steps,
					status
				);
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

	bindResponsavelSelect("va_responsavel_recepcao");
	bindResponsavelSelect("ad_responsavel_recepcao");
	bindResponsavelSelect("fr_responsavel_recepcao");
	bindResponsavelSelect("ac_responsavel_recepcao");
	bindResponsavelSelect("ci_responsavel_acompanhamento");

	// Filtros do cabeçalho (ramo e nome)
	const filtroRamoSelect = document.getElementById("filtroRamo");
	if (filtroRamoSelect) {
		const salvo = lerFiltroSalvo(RAMO_FILTRO_STORAGE_KEY);
		if (salvo) setSelectValue("filtroRamo", salvo);

		filtroRamoSelect.addEventListener("change", function (e) {
			salvarFiltro(
				RAMO_FILTRO_STORAGE_KEY,
				e.detail ? e.detail.value : getSelectValue("filtroRamo")
			);
			aplicarFiltros();
		});
	}

	const filtroNomeInput = document.getElementById("filtroNome");
	if (filtroNomeInput) {
		filtroNomeInput.value = lerFiltroSalvo(NOME_FILTRO_STORAGE_KEY);

		// `input` (e não `change`) para filtrar enquanto digita.
		filtroNomeInput.addEventListener("input", function () {
			salvarFiltro(NOME_FILTRO_STORAGE_KEY, filtroNomeInput.value);
			aplicarFiltros();
		});
	}

	if (filtroRamoSelect || filtroNomeInput) aplicarFiltros();

	const formObservacoes = document.getElementById("obs_form");
	if (formObservacoes) formObservacoes.addEventListener("submit", enviarObservacao);

	// Botão "Conversar no WhatsApp" no chooser
	const btnAbrirWhatsapp = document.getElementById("btnAbrirWhatsappContato");
	if (btnAbrirWhatsapp) {
		btnAbrirWhatsapp.addEventListener("click", function () {
			const selectedValue = getSelectValue("whatsappContatoSelect");
			if (!selectedValue) {
				frappe.msgprint(__("Selecione um responsável."));
				return;
			}
			const idx = Number(selectedValue);
			const contato = currentWhatsappContatos[idx];
			if (!contato || !contato.telefone) {
				frappe.msgprint(__("Selecione um responsável."));
				return;
			}
			openWhatsapp(contato.telefone);
			closeEscolherResponsavelWhatsapp();
		});
	}
});

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
	sincronizarCabecalhoDoDialog();
	document.getElementById("modalAssociadoNome").textContent = nome;
	document.getElementById("modalResponsavelNome").textContent = responsavelAssociado || "-";
	document.getElementById("modalRamo").textContent = ramo || "-";
	setSelectValue("responsavelRecepcao", responsavel);

	const btn = document.getElementById("btnMoverConversa");
	if (btn) btn.disabled = !responsavel;

	openDialog("modalNovoContato");
}

function openConversaInicialModal(
	id,
	responsavel,
	nome,
	responsavelAssociado,
	ramo,
	reagendamentoPendente,
	reagendamentoData
) {
	currentCardId = id;
	sincronizarCabecalhoDoDialog();
	document.getElementById("ci_associado_nome").textContent = nome;
	document.getElementById("ci_responsavel_nome").textContent = responsavelAssociado || "-";
	document.getElementById("ci_ramo").textContent = ramo || "-";
	setSelectValue("ci_responsavel_acompanhamento", responsavel);

	// Quem voltou por causa de uma visita que caiu chega aqui com o aviso ligado,
	// para a recepção agendar a nova data sem precisar abrir o histórico.
	const aviso = document.getElementById("ci_aviso_reagendamento");
	const texto = document.getElementById("ci_reagendamento_texto");
	if (aviso) aviso.classList.toggle("hidden", !reagendamentoPendente);
	if (texto) {
		texto.textContent = reagendamentoData
			? `Sinalizada para reagendar em ${reagendamentoData}. Agende uma nova data.`
			: "Agende uma nova data para a visita.";
	}

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
	sincronizarCabecalhoDoDialog();
	document.getElementById("va_associado_nome").textContent = nome;
	document.getElementById("va_responsavel_nome").textContent = responsavelAssociado || "-";
	document.getElementById("va_ramo").textContent = ramo || "-";
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
	sincronizarCabecalhoDoDialog();
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
	sincronizarCabecalhoDoDialog();
	document.getElementById("fr_associado_nome").textContent = nome;
	document.getElementById("fr_responsavel_nome").textContent = responsavelAssociado || "-";
	setSelectValue("fr_responsavel_recepcao", responsavel);

	const parsedSteps = parseSteps(steps);
	renderTimeline("fr_timeline", parsedSteps);

	openDialog("modalFazerRegistro");
}

function openAcompanhamentoModal(id, responsavel, nome, responsavelAssociado, steps, coluna) {
	currentCardId = id;
	sincronizarCabecalhoDoDialog();

	// O dialog é um só para as duas listas; o título diz em qual delas o card está.
	const titulo = document.getElementById("modalAcompanhamento-title");
	if (titulo) titulo.textContent = coluna || "Acompanhamento";
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

// ---------- Dica de conclusão da etapa -------------------------------------
//
// O `[data-tooltip]` do Basecoat é puro CSS: um `::before` `position: absolute`
// desenhado para fora do item. Aqui ele não serve como está — o corpo do dialog
// rola (`overflow-y: auto` em .dialog > div > section, dentro de um
// `overflow: hidden`), então a dica é recortada justamente nas etapas do topo, e
// o `white-space: nowrap` do componente trunca as duas linhas (data + autor).
//
// A saída é usar a aparência do componente (os mesmos tokens, em
// `.timeline-tooltip`) num nó único posicionado por JS e pendurado no próprio
// `<dialog>`, irmão da área que rola: nada o recorta e a quebra de linha cabe.

let timelineTooltipEl = null;

function obterTimelineTooltip(dialog) {
	if (!timelineTooltipEl) {
		// `span`, e não `div`: o `dialog.dialog > div` deste arquivo (o painel que
		// rola) casaria com a dica e traria `overflow: hidden` e `display: flex`.
		timelineTooltipEl = document.createElement("span");
		timelineTooltipEl.className = "timeline-tooltip";
		timelineTooltipEl.setAttribute("role", "tooltip");
		timelineTooltipEl.hidden = true;
	}
	// Pendurado no dialog aberto: no body ficaria atrás do backdrop da top layer.
	if (dialog && timelineTooltipEl.parentElement !== dialog)
		dialog.appendChild(timelineTooltipEl);
	return timelineTooltipEl;
}

function mostrarTimelineTooltip(gatilho) {
	const texto = gatilho.dataset.info;
	if (!texto) return;

	const tooltip = obterTimelineTooltip(gatilho.closest("dialog"));
	tooltip.textContent = texto;
	tooltip.hidden = false;
	tooltip.classList.remove("is-visible");

	// `offsetWidth/Height`, e não `getBoundingClientRect`: a dica entra em
	// `scale: 95%` e o retângulo devolveria o tamanho já encolhido, deixando-a uns
	// pixels fora do centro do ícone quando a escala chegasse a 100%.
	const alvo = gatilho.getBoundingClientRect();
	const largura = tooltip.offsetWidth;
	const altura = tooltip.offsetHeight;
	const margem = 8;

	let topo = alvo.top - altura - margem;
	if (topo < margem) topo = alvo.bottom + margem;

	let esquerda = alvo.left + alvo.width / 2 - largura / 2;
	esquerda = Math.max(margem, Math.min(esquerda, window.innerWidth - largura - margem));

	tooltip.style.top = `${topo}px`;
	tooltip.style.left = `${esquerda}px`;
	// No frame seguinte para a transição de opacidade/escala do Basecoat rodar.
	window.requestAnimationFrame(() => tooltip.classList.add("is-visible"));
}

function esconderTimelineTooltip() {
	if (!timelineTooltipEl) return;
	timelineTooltipEl.classList.remove("is-visible");
	timelineTooltipEl.hidden = true;
}

// Um ouvinte por container, em vez de quatro por ícone: a timeline é redesenhada
// a cada abertura de card e os ícones são recriados junto.
function ligarTooltipsDaTimeline(container) {
	container.addEventListener("mouseover", (evento) => {
		const gatilho = evento.target.closest("[data-info]");
		if (gatilho) mostrarTimelineTooltip(gatilho);
	});
	container.addEventListener("mouseout", (evento) => {
		const gatilho = evento.target.closest("[data-info]");
		// `relatedTarget` dentro do próprio gatilho é o mouse andando sobre o SVG.
		if (gatilho && !gatilho.contains(evento.relatedTarget)) esconderTimelineTooltip();
	});
	container.addEventListener("focusin", (evento) => {
		const gatilho = evento.target.closest("[data-info]");
		if (gatilho) mostrarTimelineTooltip(gatilho);
	});
	container.addEventListener("focusout", esconderTimelineTooltip);
	// Rolar move o gatilho e deixaria a dica flutuando solta.
	container.addEventListener("scroll", esconderTimelineTooltip, true);
}

function infoDeConclusao(step) {
	const partes = [];
	if (step.concluida_em_formatada) partes.push(`Concluído em ${step.concluida_em_formatada}`);
	if (step.concluido_por_nome) partes.push(`Por ${step.concluido_por_nome}`);

	const texto = partes.length
		? partes.join("\n")
		: "Concluído antes de o sistema passar a registrar data e autor.";

	return (
		` <span class="timeline-info" tabindex="0" role="img"` +
		` data-info="${escapeHtml(texto)}" aria-label="${escapeHtml(texto)}">` +
		'<svg class="ds-lucide ds-lucide--sm" viewBox="0 0 24 24" aria-hidden="true">' +
		'<use href="/assets/gris/design_system/icons/lucide/sprite.svg#info"/></svg></span>'
	);
}

function renderTimeline(containerId, steps) {
	const container = document.getElementById(containerId);
	if (!container) return;
	container.innerHTML = "";
	esconderTimelineTooltip();

	if (!container.dataset.tooltipsLigados) {
		ligarTooltipsDaTimeline(container);
		container.dataset.tooltipsLigados = "true";
	}

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
		// Concluída também é clicável: é como a recepção desfaz um clique errado.
		const clickable = !!fieldName;

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
		if (completed) {
			labelHtml += infoDeConclusao(step);
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
			item.addEventListener("click", (evento) => {
				// O ícone de informação existe para mostrar a dica, não para virar a
				// etapa: sem isto o clique nele sobe para o item e marca/desmarca.
				if (evento.target.closest(".timeline-info")) return;
				toggleStep(fieldName, item, completed, step.label);
			});
		}

		const helper = completed ? "Clique para desmarcar" : "Clique para marcar como concluído";

		item.innerHTML = `
			<div class="timeline-marker"></div>
			<div class="timeline-content">
				<span class="timeline-label">${labelHtml}</span>
				<small class="timeline-helper">${helper}</small>
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
	const ramo = currentCardElement && currentCardElement.dataset.ramo;

	// O ramo vem da idade, então card sem ramo é card sem data de nascimento — e é lá,
	// na ficha, que a recepção resolve; não há mais campo de ramo para preencher aqui.
	if (!ramo) {
		frappe.show_alert({
			message: "Sem ramo definido. Preencha a data de nascimento na ficha do associado.",
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
		frappe.msgprint(__("Selecione uma data."));
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

function sinalizarReagendamento() {
	if (!currentCardId) return;
	previousModalId = getOpenDialogId("modalReagendarDepois");
	if (previousModalId) closeDialog(previousModalId);
	const motivo = document.getElementById("rd_motivo");
	if (motivo) motivo.value = "";
	openDialog("modalReagendarDepois");
}

function closeReagendarDepois() {
	closeDialog("modalReagendarDepois");
	if (previousModalId) {
		const prev = previousModalId;
		previousModalId = null;
		openDialog(prev);
	}
}

function confirmarReagendamento() {
	if (!currentCardId) return;
	const campoMotivo = document.getElementById("rd_motivo");
	const botao = document.getElementById("btnConfirmarReagendamento");
	if (botao) botao.disabled = true;

	frappe.call({
		method: "gris.api.recepcao.sinalizar_reagendamento_de_visita",
		args: {
			novo_associado_name: currentCardId,
			motivo: campoMotivo ? campoMotivo.value : "",
		},
		callback: function (r) {
			if (!r.exc) {
				frappe.show_alert({
					message: "Visita a reagendar. Card movido para Conversa Inicial.",
					indicator: "orange",
				});
				closeAllDialogs();
				setTimeout(() => window.location.reload(), 500);
			} else if (botao) {
				botao.disabled = false;
			}
		},
		error: function () {
			if (botao) botao.disabled = false;
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

function toggleStep(field, element, completed, label) {
	if (!currentCardId || !field) return;

	// Desmarcar apaga o histórico da etapa, pode cancelar a visita e move o card de
	// lista: confirma antes.
	if (completed) {
		abrirDesmarcarEtapa(field, element, label);
		return;
	}

	// Efetivar o registro passa antes pelo diálogo dos números de registro. O
	// backend recusa a etapa sem eles de qualquer jeito (update_step_status);
	// aqui é só para pedir o dado em vez de mostrar um erro.
	if (CAMPOS_DE_EFETIVACAO.includes(field)) {
		abrirNumerosDeRegistro(field, element);
		return;
	}

	marcarEtapa(field, element);
}

function marcarEtapa(field, element, valor) {
	const concluir = valor === undefined ? 1 : valor;
	frappe.call({
		method: "gris.www.recepcao.visao_geral.update_step_status",
		args: { novo_associado_name: currentCardId, field: field, value: concluir },
		callback: function (r) {
			if (!r.exc) {
				frappe.show_alert({
					message: concluir ? "Etapa atualizada" : "Etapa desmarcada",
					indicator: concluir ? "green" : "orange",
				});
				if (element) element.classList.toggle("completed", !!concluir);
				setTimeout(() => window.location.reload(), 1000);
			}
		},
	});
}

// ---------- Desmarcar etapa ------------------------------------------------

// Etapa -> coluna para onde o card volta quando ela é a última concluída. Espelha
// ETAPAS_QUE_MOVEM_O_FUNIL (gris/api/recepcao_funil.py); serve só para o aviso do
// diálogo — quem decide o status é o servidor.
const COLUNA_ANTERIOR_POR_ETAPA = {
	visita_agendada: "Conversa Inicial",
	primeira_visita_realizada: "Visita Agendada",
	dados_para_registro_enviados: "Aguardar Dados",
	registro_criado_no_paxtu: "Fazer Registro",
};

let desmarcarEtapaPendente = null;
let desmarcarElementoPendente = null;

function abrirDesmarcarEtapa(field, element, label) {
	desmarcarEtapaPendente = field;
	desmarcarElementoPendente = element;

	const nome = document.getElementById("de_etapa_nome");
	if (nome) nome.textContent = label || field;

	const efeitos = document.getElementById("de_efeitos");
	if (efeitos) {
		const partes = [];
		const coluna = COLUNA_ANTERIOR_POR_ETAPA[field];
		if (coluna) partes.push(`O card pode voltar para <strong>${escapeHtml(coluna)}</strong>.`);
		if (field === "visita_agendada") partes.push("A visita marcada será cancelada.");
		efeitos.innerHTML = partes.join(" ");
	}

	previousModalId = getOpenDialogId("modalDesmarcarEtapa");
	if (previousModalId) closeDialog(previousModalId);
	openDialog("modalDesmarcarEtapa");
}

function closeDesmarcarEtapa() {
	closeDialog("modalDesmarcarEtapa");
	desmarcarEtapaPendente = null;
	desmarcarElementoPendente = null;
	if (previousModalId) {
		const prev = previousModalId;
		previousModalId = null;
		openDialog(prev);
	}
}

function confirmarDesmarcarEtapa() {
	const field = desmarcarEtapaPendente;
	const element = desmarcarElementoPendente;
	if (!field) return;

	const botao = document.getElementById("btnConfirmarDesmarcar");
	if (botao) botao.disabled = true;

	closeDialog("modalDesmarcarEtapa");
	desmarcarEtapaPendente = null;
	desmarcarElementoPendente = null;
	previousModalId = null;

	marcarEtapa(field, element, 0);
	if (botao) botao.disabled = false;
}

// ---------- Números de registro (etapas de efetivação) ---------------------

let numerosSourceModalId = null;
let numerosEtapaPendente = null;
let numerosElementoPendente = null;

// Abre o diálogo dos números de registro; se nada estiver faltando, marca a
// etapa direto, sem interromper quem já preencheu tudo antes.
function abrirNumerosDeRegistro(field, element) {
	numerosEtapaPendente = field;
	numerosElementoPendente = element;

	frappe.call({
		method: "gris.api.recepcao.obter_numeros_de_registro",
		args: { novo_associado_name: currentCardId },
		callback: function (r) {
			if (r.exc) return;
			const dados = r.message || {};
			if (!(dados.pendentes || []).length) {
				marcarEtapa(field, element);
				return;
			}
			renderizarCamposDeRegistro(dados);
			numerosSourceModalId = getOpenDialogId("modalNumerosDeRegistro");
			if (numerosSourceModalId) closeDialog(numerosSourceModalId);
			openDialog("modalNumerosDeRegistro");
		},
	});
}

function renderizarCamposDeRegistro(dados) {
	const container = document.getElementById("nr_campos");
	if (!container) return;
	container.innerHTML = "";
	definirErroDeRegistro("");

	const jovem = dados.jovem || {};
	container.appendChild(
		campoDeRegistro({
			id: "nr_jovem",
			rotulo: `${jovem.nome || "Jovem"} (jovem)`,
			valor: jovem.numero_de_registro || "",
			obrigatorio: true,
		})
	);

	(dados.responsaveis || []).forEach((responsavel, indice) => {
		const campo = campoDeRegistro({
			id: `nr_responsavel_${indice}`,
			rotulo: responsavel.nome,
			valor: responsavel.numero_de_registro || "",
			obrigatorio: responsavel.sera_registrado,
			ajuda: responsavel.sera_registrado
				? "Será registrado junto com o jovem."
				: "Opcional.",
		});
		campo.querySelector("input").dataset.responsavel = responsavel.responsavel;
		container.appendChild(campo);
	});
}

function campoDeRegistro({ id, rotulo, valor, obrigatorio, ajuda }) {
	const wrapper = document.createElement("div");
	wrapper.className = "field registro-numeros__campo";

	const label = document.createElement("label");
	label.className = "label";
	label.setAttribute("for", id);
	label.textContent = obrigatorio ? `${rotulo} *` : rotulo;

	const input = document.createElement("input");
	input.type = "text";
	input.className = "input";
	input.id = id;
	input.value = valor;
	input.autocomplete = "off";
	input.placeholder = "Número de registro";
	if (obrigatorio) input.dataset.obrigatorio = "1";

	wrapper.appendChild(label);
	wrapper.appendChild(input);

	if (ajuda) {
		const dica = document.createElement("p");
		dica.className = "text-muted-foreground text-xs mt-1";
		dica.textContent = ajuda;
		wrapper.appendChild(dica);
	}

	return wrapper;
}

function definirErroDeRegistro(mensagem) {
	const erro = document.getElementById("nr_erro");
	if (!erro) return;
	erro.textContent = mensagem || "";
	erro.hidden = !mensagem;
}

function fecharNumerosDeRegistro() {
	closeDialog("modalNumerosDeRegistro");
	numerosEtapaPendente = null;
	numerosElementoPendente = null;
	if (numerosSourceModalId) {
		const anterior = numerosSourceModalId;
		numerosSourceModalId = null;
		openDialog(anterior);
	}
}

function salvarNumerosDeRegistro() {
	const jovemInput = document.getElementById("nr_jovem");
	if (!jovemInput) return;

	const faltando = Array.from(
		document.querySelectorAll('#nr_campos input[data-obrigatorio="1"]')
	).filter((input) => !input.value.trim());

	if (faltando.length) {
		definirErroDeRegistro("Preencha o número de registro de todos os campos obrigatórios.");
		faltando[0].focus();
		return;
	}

	const responsaveis = {};
	document.querySelectorAll("#nr_campos input[data-responsavel]").forEach((input) => {
		responsaveis[input.dataset.responsavel] = input.value.trim();
	});

	const botao = document.getElementById("btnSalvarNumerosDeRegistro");
	if (botao) botao.disabled = true;
	definirErroDeRegistro("");

	const etapa = numerosEtapaPendente;
	const elemento = numerosElementoPendente;

	frappe.call({
		method: "gris.api.recepcao.salvar_numeros_de_registro",
		args: {
			novo_associado_name: currentCardId,
			numero_jovem: jovemInput.value.trim(),
			responsaveis: JSON.stringify(responsaveis),
		},
		callback: function (r) {
			if (botao) botao.disabled = false;
			if (r.exc) return;

			closeDialog("modalNumerosDeRegistro");
			numerosSourceModalId = null;
			numerosEtapaPendente = null;
			numerosElementoPendente = null;
			if (etapa) marcarEtapa(etapa, elemento);
		},
		error: function () {
			if (botao) botao.disabled = false;
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

// ---------- Observações -----------------------------------------------------

let observacoesSourceModalId = null;

// A macro `people_header` é usada pelos seis modais de card, então o rótulo existe
// seis vezes no DOM. Só um modal fica aberto por vez: atualizar todos é o correto.
function atualizarRotuloObservacoes() {
	const total = contarObservacoesDoCardAtual();
	document.querySelectorAll(".js-dialog-observacoes-total").forEach((el) => {
		el.textContent = total ? String(total) : "Nenhuma";
	});
}

// Cabeçalho compartilhado pelos modais de card (WhatsApp + observações).
function sincronizarCabecalhoDoDialog() {
	updateWhatsappButtonState();
	atualizarRotuloObservacoes();
	atualizarBotoesDeVagas();
}

// O ícone ao lado do ramo só aparece quando há vagas calculadas para o ramo do card.
function atualizarBotoesDeVagas() {
	const ramo = currentCardElement ? currentCardElement.dataset.ramo : "";
	const disponivel = Boolean(window.grisVagasDoRamo && window.grisVagasDoRamo.temDados(ramo));
	document.querySelectorAll(".js-vagas-do-ramo").forEach((botao) => {
		botao.classList.toggle("hidden", !disponivel);
	});
}

function abrirVagasDoRamoAtual() {
	const ramo = currentCardElement ? currentCardElement.dataset.ramo : "";
	if (!ramo || !window.grisVagasDoRamo) return;

	// Mesmo vaivém das mensagens e das observações: showModal() põe o dialog na top
	// layer e torna o resto inerte, então o modal do card fecha antes e reabre quando o
	// cálculo de vagas sai de cena.
	const origem = getOpenDialogId("modalVagas");
	if (origem) closeDialog(origem);

	window.grisVagasDoRamo.abrir(ramo, {
		aoFechar: function () {
			if (origem) openDialog(origem);
		},
	});
}

function contarObservacoesDoCardAtual() {
	if (!currentCardElement) return 0;
	const total = parseInt(currentCardElement.dataset.observacoes, 10);
	return Number.isNaN(total) ? 0 : total;
}

// Mantém card, balão e rótulo dos modais na mesma contagem, sem recarregar a página.
function definirTotalDeObservacoes(total) {
	if (!currentCardElement) return;
	currentCardElement.dataset.observacoes = String(total);

	const balao = currentCardElement.querySelector(".js-observacoes-badge");
	if (balao) {
		balao.classList.toggle("hidden", total < 1);
		const numero = balao.querySelector(".js-observacoes-total");
		if (numero) numero.textContent = String(total);
	}

	atualizarRotuloObservacoes();
}

function abrirMensagensDoCardAtual() {
	if (!currentCardId) {
		frappe.msgprint(__("Nenhum associado selecionado."));
		return;
	}

	// Mesmo vaivém do chooser de WhatsApp e das observações: showModal() põe o
	// diálogo na top layer e torna o resto inerte, então o modal do card fecha
	// antes e reabre quando as mensagens saem de cena.
	const origem = getOpenDialogId("mensagens-modal");
	if (origem) closeDialog(origem);

	window.grisMensagensEnviadas.abrir(currentCardId, {
		aoFechar: function () {
			if (origem) openDialog(origem);
		},
	});
}

function abrirObservacoesDoCardAtual() {
	if (!currentCardId) {
		frappe.msgprint(__("Nenhum associado selecionado."));
		return;
	}
	abrirObservacoes();
}

function abrirObservacoes() {
	// showModal() põe o dialog na top layer e torna o resto inerte: o modal de
	// origem precisa fechar antes e reabrir depois (mesmo padrão do chooser de WhatsApp).
	observacoesSourceModalId = getOpenDialogId("modalObservacoes");
	if (observacoesSourceModalId) closeDialog(observacoesSourceModalId);

	const nome = (currentCardElement && currentCardElement.dataset.nome) || "";
	document.getElementById("obs_associado_nome").textContent = nome;

	const form = document.getElementById("obs_form");
	const texto = document.getElementById("obs_texto");
	const erro = document.getElementById("obs_erro");
	if (texto) texto.value = "";
	if (erro) erro.hidden = true;
	if (form) form.classList.add("hidden");

	const lista = document.getElementById("obs_lista");
	lista.innerHTML = '<p class="text-muted-foreground">Carregando…</p>';

	openDialog("modalObservacoes");

	frappe.call({
		method: "gris.api.recepcao.listar_comentarios",
		args: { novo_associado_name: currentCardId },
		callback: function (r) {
			if (r.exc) {
				lista.innerHTML =
					'<p class="text-destructive">Não foi possível carregar as observações.</p>';
				return;
			}

			const dados = r.message || {};
			const comentarios = dados.comentarios || [];
			if (form) form.classList.toggle("hidden", !dados.pode_comentar);
			renderObservacoes(comentarios);
			// `total` é a contagem real; a lista pode vir truncada pelo limite do backend.
			definirTotalDeObservacoes(
				dados.total === undefined ? comentarios.length : dados.total
			);
		},
	});
}

function fecharObservacoes() {
	closeDialog("modalObservacoes");
	if (observacoesSourceModalId) {
		const anterior = observacoesSourceModalId;
		observacoesSourceModalId = null;
		openDialog(anterior);
	}
}

function renderObservacoes(comentarios) {
	const lista = document.getElementById("obs_lista");
	if (!lista) return;
	lista.innerHTML = "";

	if (!comentarios || comentarios.length === 0) {
		lista.innerHTML =
			'<p class="text-muted-foreground js-observacoes-vazio">Nenhuma observação ainda.</p>';
		return;
	}

	comentarios.forEach((c) => lista.appendChild(montarItemDeObservacao(c)));
}

function montarItemDeObservacao(comentario) {
	const item = document.createElement("div");
	item.className = "comment-item";
	item.dataset.commentName = comentario.name;
	item.innerHTML = `
		<div class="comment-item__meta">
			<span class="comment-item__author">${escapeHtml(comentario.owner_fullname)}</span>
			<span>•</span>
			<span>${escapeHtml(comentario.creation)}</span>
		</div>
		<div class="comment-item__content">${escapeHtml(comentario.content_text).replace(
			/\n/g,
			"<br>"
		)}</div>
	`;
	return item;
}

function enviarObservacao(event) {
	event.preventDefault();
	if (!currentCardId) return;

	const texto = document.getElementById("obs_texto");
	const erro = document.getElementById("obs_erro");
	const submit = document.getElementById("obs_submit");
	const conteudo = (texto.value || "").trim();

	if (!conteudo) {
		erro.textContent = "Escreva algo antes de adicionar.";
		erro.hidden = false;
		return;
	}

	erro.hidden = true;
	submit.disabled = true;
	submit.textContent = "Enviando…";

	frappe.call({
		method: "gris.api.recepcao.adicionar_comentario",
		args: { novo_associado_name: currentCardId, content: conteudo },
		always: function () {
			submit.disabled = false;
			submit.textContent = "Adicionar";
		},
		callback: function (r) {
			if (r.exc || !r.message) {
				erro.textContent = "Não foi possível salvar a observação.";
				erro.hidden = false;
				return;
			}

			const lista = document.getElementById("obs_lista");
			const vazio = lista.querySelector(".js-observacoes-vazio");
			if (vazio) vazio.remove();

			// Mais recente primeiro, como a listagem do backend.
			lista.prepend(montarItemDeObservacao(r.message));
			texto.value = "";
			definirTotalDeObservacoes(contarObservacoesDoCardAtual() + 1);
			frappe.show_alert({ message: "Observação adicionada", indicator: "green" });
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
		frappe.msgprint(__("Nenhum associado selecionado."));
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
		frappe.msgprint(__("Sem telefone de responsável para contato."));
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
		frappe.msgprint(__("Telefone do responsável inválido."));
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
window.abrirMensagensDoCardAtual = abrirMensagensDoCardAtual;
window.closeDesmarcarEtapa = closeDesmarcarEtapa;
window.confirmarDesmarcarEtapa = confirmarDesmarcarEtapa;
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
