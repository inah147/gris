// Fila de Espera da Recepção — interações cliente
// Usa exclusivamente o design system Basecoat (<dialog> HTML5 + alert + badge).
// O dialog de vagas (com o gráfico de previsão) é compartilhado com a visão geral:
// ver public/js/vagas_do_ramo.js.
//
// Este arquivo é injetado inline pelo Frappe (co-location): não referenciar com
// <script src>, senão roda duas vezes e cada arrasto grava a ordem em dobro.

(function () {
	const API = "/api/method/gris.www.recepcao.fila_espera.";

	// Arrasto: com mouse começa ao passar do limiar; no toque, depois de um toque longo,
	// para que deslizar o dedo continue rolando a página.
	const LIMIAR_ARRASTO_PX = 6;
	const TOQUE_LONGO_MS = 250;
	const TOLERANCIA_TOQUE_PX = 8;
	const BORDA_ROLAGEM_PX = 48;
	const PASSO_ROLAGEM_PX = 12;
	const ESPERA_SALVAR_TECLADO_MS = 600;

	let currentFilaId = null;
	let currentAssociadoId = null;
	let currentAssociadoNome = "";
	let currentStatusRetorno = "";

	let historicoPorAssociado = {};

	// ---------- Helpers de dialog --------------------------------------------

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

	// ---------- Chamadas ao servidor ------------------------------------------

	// `frappe.call` do portal nunca chama `error`: com fetch a falha volta para a tela.
	async function chamarApi(metodo, corpo) {
		const resposta = await fetch(API + metodo, {
			method: "POST",
			headers: {
				"Content-Type": "application/json",
				"X-Frappe-CSRF-Token": (window.frappe && frappe.csrf_token) || "",
				"X-Requested-With": "XMLHttpRequest",
			},
			credentials: "same-origin",
			body: JSON.stringify(corpo),
		});
		let dados = null;
		try {
			dados = await resposta.json();
		} catch (err) {
			dados = null;
		}
		if (!resposta.ok) {
			const erro = new Error(mensagemDoServidor(dados));
			erro.status = resposta.status;
			throw erro;
		}
		return dados && dados.message;
	}

	function mensagemDoServidor(dados) {
		try {
			const mensagens = JSON.parse((dados && dados._server_messages) || "[]");
			const primeira = mensagens.length ? JSON.parse(mensagens[0]) : null;
			if (primeira && primeira.message) {
				const tmp = document.createElement("div");
				tmp.innerHTML = primeira.message;
				return tmp.textContent || "";
			}
		} catch (err) {
			// segue para a mensagem genérica
		}
		return "";
	}

	// ---------- Modal de detalhes da fila ------------------------------------

	function celula(texto) {
		const td = document.createElement("td");
		td.textContent = texto || "—";
		return td;
	}

	function preencherHistorico(associado) {
		const corpo = document.getElementById("filaHistoricoLinhas");
		const vazio = document.getElementById("filaHistoricoVazio");
		const tabela = corpo && corpo.closest(".fila-historico__rolagem");
		if (!corpo) return;

		corpo.replaceChildren();
		const passagens = historicoPorAssociado[associado] || [];
		for (const passagem of passagens) {
			const tr = document.createElement("tr");
			tr.appendChild(celula(passagem.entrada_em));
			tr.appendChild(celula(passagem.status_anterior));
			if (passagem.aberta) {
				const td = document.createElement("td");
				const selo = document.createElement("span");
				selo.className = "badge";
				selo.textContent = passagem.saida_em;
				td.appendChild(selo);
				tr.appendChild(td);
			} else {
				tr.appendChild(celula(passagem.saida_em));
			}
			tr.appendChild(celula(passagem.status_posterior));
			corpo.appendChild(tr);
		}

		if (tabela) tabela.hidden = passagens.length === 0;
		if (vazio) vazio.hidden = passagens.length > 0;
	}

	function openFilaModal(card) {
		currentFilaId = card.dataset.id;
		currentAssociadoId = card.dataset.associado;
		currentAssociadoNome = card.dataset.nome || "este associado";
		currentStatusRetorno = card.dataset.statusRetorno || "";

		document.getElementById("modalAssociadoNome").textContent = card.dataset.nome || "";
		document.getElementById("modalResponsavelNome").textContent =
			card.dataset.responsavel || "";
		document.getElementById("modalPosicao").textContent = "#" + (card.dataset.posicao || "");
		document.getElementById("modalPrevisao").textContent =
			card.dataset.previsao || "Sem previsão";
		document.getElementById("modalDataInclusao").textContent = card.dataset.dataInclusao || "";
		document.getElementById("modalStatusRetorno").textContent = currentStatusRetorno || "—";
		preencherHistorico(currentAssociadoId);

		openDialog("modalFilaEspera");
	}

	function abrirFicha() {
		if (currentAssociadoId) {
			window.location.href = `/recepcao/ficha_registro?name=${encodeURIComponent(
				currentAssociadoId
			)}`;
		}
	}

	// ---------- Modal de confirmação de chamada ------------------------------

	function abrirConfirmarChamada() {
		if (!currentFilaId) return;
		document.getElementById("modalChamadaNome").textContent = currentAssociadoNome;
		document.getElementById("modalChamadaDestino").textContent =
			currentStatusRetorno || "o status em que estava ao entrar";
		closeDialog("modalFilaEspera");
		openDialog("modalConfirmarChamada");
	}

	function cancelarChamada() {
		closeDialog("modalConfirmarChamada");
		// Reabre o modal anterior caso ainda haja contexto.
		if (currentFilaId) openDialog("modalFilaEspera");
	}

	async function confirmarChamada() {
		if (!currentFilaId) return;
		// Fecha antes de chamar o servidor: com um <dialog> aberto via showModal()
		// o restante da página fica inerte e mensagens do Frappe não apareceriam.
		closeDialog("modalConfirmarChamada");
		const botao = document.getElementById("btnConfirmarChamada");
		if (botao) botao.disabled = true;
		try {
			const resultado = await chamarApi("chamar_associado", { fila_id: currentFilaId });
			const destino = resultado && resultado.status;
			frappe.show_alert({
				message: destino
					? `Associado chamado: voltou para ${destino}`
					: "Associado chamado com sucesso",
				indicator: "green",
			});
			setTimeout(() => window.location.reload(), 800);
		} catch (err) {
			if (botao) botao.disabled = false;
			frappe.show_alert({
				message: err.message || "Não foi possível chamar o associado",
				indicator: "red",
			});
		}
	}

	// ---------- Modal de confirmação de desistência --------------------------

	function abrirConfirmarDesistencia() {
		if (!currentFilaId) return;
		closeDialog("modalFilaEspera");
		openDialog("modalConfirmarDesistencia");
	}

	function cancelarDesistencia() {
		closeDialog("modalConfirmarDesistencia");
		// Reabre o modal anterior caso ainda haja contexto.
		if (currentFilaId) openDialog("modalFilaEspera");
	}

	function confirmarDesistencia() {
		if (!currentFilaId) return;
		// Mesmo motivo de confirmarChamada: fechar o dialog antes da chamada.
		closeDialog("modalConfirmarDesistencia");
		frappe.call({
			method: "gris.www.recepcao.fila_espera.registrar_desistencia",
			args: { fila_id: currentFilaId },
			freeze: true,
			freeze_message: "Registrando desistência...",
			callback: function (r) {
				if (r.exc) return;
				frappe.show_alert({ message: "Desistência registrada", indicator: "green" });
				setTimeout(() => window.location.reload(), 800);
			},
		});
	}

	// ---------- Ordem da fila ---------------------------------------------------

	function cardsDa(coluna) {
		return Array.from(coluna.querySelectorAll(":scope > .kanban-card"));
	}

	function ordemDa(coluna) {
		return cardsDa(coluna).map((card) => card.dataset.id);
	}

	function anunciar(texto) {
		const alvo = document.getElementById("filaAnuncio");
		if (alvo) alvo.textContent = texto;
	}

	// Posição e previsão são da posição na fila, não da pessoa: quem sobe herda a
	// previsão do lugar que passou a ocupar. As previsões de cada coluna são lidas uma
	// vez, na ordem em que o servidor as calculou.
	function renumerar(coluna) {
		const previsoes = coluna._previsoes || [];
		cardsDa(coluna).forEach((card, indice) => {
			const posicao = indice + 1;
			card.dataset.posicao = String(posicao);
			card.dataset.previsao = previsoes[indice] || "Sem previsão";
			const selo = card.querySelector("[data-posicao-badge]");
			if (selo) selo.textContent = "#" + posicao;
		});
	}

	function aplicarOrdem(coluna, ordem) {
		const porId = new Map(cardsDa(coluna).map((card) => [card.dataset.id, card]));
		for (const id of ordem) {
			const card = porId.get(id);
			if (card) coluna.appendChild(card);
		}
		renumerar(coluna);
	}

	async function salvarOrdem(coluna, ordemAnterior) {
		const ordem = ordemDa(coluna);
		if (ordem.join("|") === ordemAnterior.join("|")) return;

		coluna.dataset.salvando = "1";
		cardsDa(coluna).forEach((card) => card.classList.add("is-saving"));
		try {
			await chamarApi("reordenar_fila", { ramo: coluna.dataset.ramo, ordem: ordem });
			frappe.show_alert({ message: "Ordem da fila atualizada", indicator: "green" });
		} catch (err) {
			aplicarOrdem(coluna, ordemAnterior);
			frappe.show_alert({
				message: err.message || "Não foi possível salvar a nova ordem da fila",
				indicator: "red",
			});
		} finally {
			delete coluna.dataset.salvando;
			cardsDa(coluna).forEach((card) => card.classList.remove("is-saving"));
		}
	}

	// ---------- Arrastar (mouse e toque) ----------------------------------------

	let arrasto = null;
	let ignorarProximoClique = false;

	function iniciarGesto(event) {
		if (event.button !== 0 || arrasto) return;
		const card = event.target.closest(".kanban-card");
		const coluna = card && card.parentElement;
		if (!coluna || coluna.dataset.salvando) return;

		arrasto = {
			card: card,
			coluna: coluna,
			pointerId: event.pointerId,
			toque: event.pointerType === "touch",
			inicioX: event.clientX,
			inicioY: event.clientY,
			ultimoX: event.clientX,
			ultimoY: event.clientY,
			ativo: false,
			timer: null,
		};

		if (arrasto.toque) {
			arrasto.timer = setTimeout(() => {
				if (arrasto && !arrasto.ativo) ativarArrasto();
			}, TOQUE_LONGO_MS);
		}
	}

	function ativarArrasto() {
		const { card, coluna } = arrasto;
		const caixa = card.getBoundingClientRect();

		arrasto.ativo = true;
		arrasto.ordemAnterior = ordemDa(coluna);
		arrasto.deslocX = arrasto.ultimoX - caixa.left;
		arrasto.deslocY = arrasto.ultimoY - caixa.top;

		const lugar = document.createElement("div");
		lugar.className = "kanban-card__placeholder";
		lugar.style.height = caixa.height + "px";
		coluna.insertBefore(lugar, card);
		arrasto.lugar = lugar;

		card.style.width = caixa.width + "px";
		card.style.left = caixa.left + "px";
		card.style.top = caixa.top + "px";
		card.classList.add("is-dragging");
		document.body.classList.add("fila-arrastando");
		if (arrasto.toque && navigator.vibrate) navigator.vibrate(15);
	}

	function moverGesto(event) {
		if (!arrasto || event.pointerId !== arrasto.pointerId) return;
		arrasto.ultimoX = event.clientX;
		arrasto.ultimoY = event.clientY;

		if (!arrasto.ativo) {
			const distancia = Math.hypot(
				event.clientX - arrasto.inicioX,
				event.clientY - arrasto.inicioY
			);
			if (arrasto.toque) {
				// Deslizou antes do toque longo: é rolagem, não arrasto.
				if (distancia > TOLERANCIA_TOQUE_PX) cancelarGesto();
				return;
			}
			if (distancia < LIMIAR_ARRASTO_PX) return;
			ativarArrasto();
		}

		event.preventDefault();
		const { card, coluna, lugar } = arrasto;
		card.style.left = event.clientX - arrasto.deslocX + "px";
		card.style.top = event.clientY - arrasto.deslocY + "px";

		rolarSePerto(coluna, event.clientY);

		// Só dentro da coluna de origem: o ramo vem da idade, não da posição na tela.
		const proximo = cardsDa(coluna).find((outro) => {
			if (outro === card) return false;
			const caixa = outro.getBoundingClientRect();
			return event.clientY < caixa.top + caixa.height / 2;
		});
		if (proximo) {
			if (lugar.nextElementSibling !== proximo) coluna.insertBefore(lugar, proximo);
		} else if (coluna.lastElementChild !== lugar) {
			coluna.appendChild(lugar);
		}
	}

	function rolarSePerto(coluna, y) {
		const caixa = coluna.getBoundingClientRect();
		if (coluna.scrollHeight > coluna.clientHeight) {
			if (y < caixa.top + BORDA_ROLAGEM_PX) coluna.scrollTop -= PASSO_ROLAGEM_PX;
			else if (y > caixa.bottom - BORDA_ROLAGEM_PX) coluna.scrollTop += PASSO_ROLAGEM_PX;
		}
		if (y < BORDA_ROLAGEM_PX) window.scrollBy(0, -PASSO_ROLAGEM_PX);
		else if (y > window.innerHeight - BORDA_ROLAGEM_PX) window.scrollBy(0, PASSO_ROLAGEM_PX);
	}

	function encerrarGesto(event, cancelado) {
		if (!arrasto || (event && event.pointerId !== arrasto.pointerId)) return;
		const atual = arrasto;
		arrasto = null;
		clearTimeout(atual.timer);
		if (!atual.ativo) return;

		const { card, coluna, lugar } = atual;
		coluna.insertBefore(card, lugar);
		lugar.remove();
		card.classList.remove("is-dragging");
		card.style.width = "";
		card.style.left = "";
		card.style.top = "";
		document.body.classList.remove("fila-arrastando");

		// O clique que o navegador dispara ao soltar não pode abrir o dialog.
		ignorarProximoClique = true;
		setTimeout(() => (ignorarProximoClique = false), 0);

		if (cancelado) {
			aplicarOrdem(coluna, atual.ordemAnterior);
			return;
		}
		renumerar(coluna);
		anunciar(
			`${card.dataset.nome || "Associado"} agora é o número ${
				card.dataset.posicao
			} da fila de ${coluna.dataset.ramo}.`
		);
		salvarOrdem(coluna, atual.ordemAnterior);
	}

	function cancelarGesto() {
		if (!arrasto) return;
		clearTimeout(arrasto.timer);
		if (arrasto.ativo) encerrarGesto(null, true);
		else arrasto = null;
	}

	// Com o arrasto por toque ativo, o deslizar não pode rolar a página.
	function segurarRolagemDoToque(event) {
		if (arrasto && arrasto.ativo) event.preventDefault();
	}

	// ---------- Teclado: Alt + ↑/↓ ----------------------------------------------

	const pendentesDoTeclado = new Map();

	function moverPeloTeclado(card, direcao) {
		const coluna = card.parentElement;
		if (!coluna || coluna.dataset.salvando) return;
		const vizinho = direcao < 0 ? card.previousElementSibling : card.nextElementSibling;
		if (!vizinho || !vizinho.classList.contains("kanban-card")) return;

		const pendente = pendentesDoTeclado.get(coluna) || { ordemAnterior: ordemDa(coluna) };
		clearTimeout(pendente.timer);

		if (direcao < 0) coluna.insertBefore(card, vizinho);
		else coluna.insertBefore(vizinho, card);
		card.focus();
		renumerar(coluna);
		anunciar(
			`${card.dataset.nome || "Associado"} agora é o número ${
				card.dataset.posicao
			} da fila de ${coluna.dataset.ramo}.`
		);

		// Várias setas seguidas viram uma gravação só.
		pendente.timer = setTimeout(() => {
			pendentesDoTeclado.delete(coluna);
			salvarOrdem(coluna, pendente.ordemAnterior);
		}, ESPERA_SALVAR_TECLADO_MS);
		pendentesDoTeclado.set(coluna, pendente);
	}

	function teclaNoCard(event) {
		const card = event.target.closest(".kanban-card");
		if (!card || event.target !== card) return;
		if (event.altKey && (event.key === "ArrowUp" || event.key === "ArrowDown")) {
			event.preventDefault();
			moverPeloTeclado(card, event.key === "ArrowUp" ? -1 : 1);
		} else if (event.key === "Enter" || event.key === " ") {
			event.preventDefault();
			openFilaModal(card);
		}
	}

	// ---------- Bootstrap -----------------------------------------------------

	function lerHistorico() {
		const fonte = document.getElementById("historicoFilaData");
		try {
			historicoPorAssociado = JSON.parse((fonte && fonte.textContent) || "{}") || {};
		} catch (err) {
			historicoPorAssociado = {};
		}
	}

	frappe.ready(function () {
		lerHistorico();

		const colunas = document.querySelectorAll(".kanban-column__body");
		colunas.forEach((coluna) => {
			coluna._previsoes = cardsDa(coluna).map((card) => card.dataset.previsao);
			coluna.addEventListener("pointerdown", iniciarGesto);
			coluna.addEventListener("keydown", teclaNoCard);
			coluna.addEventListener("click", (event) => {
				const card = event.target.closest(".kanban-card");
				if (!card || ignorarProximoClique) return;
				openFilaModal(card);
			});
		});

		document.addEventListener("pointermove", moverGesto, { passive: false });
		document.addEventListener("pointerup", (event) => encerrarGesto(event, false));
		document.addEventListener("pointercancel", (event) => {
			if (arrasto && event.pointerId === arrasto.pointerId) cancelarGesto();
		});
		document.addEventListener("touchmove", segurarRolagemDoToque, { passive: false });
		document.addEventListener("contextmenu", (event) => {
			if (arrasto) event.preventDefault();
		});
		document.addEventListener("keydown", (event) => {
			if (event.key === "Escape" && arrasto && arrasto.ativo) cancelarGesto();
		});

		// Botão de vagas no header de cada coluna → dialog compartilhado
		document.querySelectorAll(".kanban-column__vagas").forEach((btn) => {
			btn.addEventListener("click", () => window.grisVagasDoRamo.abrir(btn.dataset.ramo));
		});

		// Ações do modal de fila de espera
		document
			.getElementById("btnChamarAssociado")
			?.addEventListener("click", abrirConfirmarChamada);
		document.getElementById("btnAbrirFicha")?.addEventListener("click", abrirFicha);
		document
			.getElementById("btnRegistrarDesistencia")
			?.addEventListener("click", abrirConfirmarDesistencia);

		// Ações dos modais de confirmação
		document.getElementById("btnCancelarChamada")?.addEventListener("click", cancelarChamada);
		document
			.getElementById("btnConfirmarChamada")
			?.addEventListener("click", confirmarChamada);
		document
			.getElementById("btnCancelarDesistencia")
			?.addEventListener("click", cancelarDesistencia);
		document
			.getElementById("btnConfirmarDesistencia")
			?.addEventListener("click", confirmarDesistencia);

		// Botão "Fechar" dos dialogs (atributo data-dialog-close)
		document.addEventListener("click", (event) => {
			const closer = event.target.closest("[data-dialog-close]");
			if (closer) {
				const dlg = closer.closest("dialog");
				if (dlg && dlg.open) dlg.close();
			}
		});
	});
})();
