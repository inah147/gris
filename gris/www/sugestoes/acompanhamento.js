/* /sugestoes/acompanhamento — quadro kanban das solicitações.
 *
 * Não reusa GrisKanbanTarefas: aquele componente tem TASK_STATUS_ORDER fixo e é
 * acoplado ao dialog de tarefa. Aqui reaproveitamos só o CSS (kanban-tarefas.css,
 * carregado globalmente em base.html) para o quadro ficar idêntico ao do Portal.
 */
(function () {
	"use strict";

	const raiz = document.querySelector(".sugestoes-quadro");
	if (!raiz) return;

	const METODOS = {
		board: "gris.api.sugestoes.portal.listar_board",
		detalhes: "gris.api.sugestoes.portal.detalhes",
		status: "gris.api.sugestoes.portal.atualizar_status",
		responsavel: "gris.api.sugestoes.portal.alocar_responsavel",
		comentar: "gris.api.sugestoes.portal.adicionar_comentario",
		descricao: "gris.api.sugestoes.portal.atualizar_descricao",
		reclassificar: "gris.api.sugestoes.portal.reclassificar",
		reordenar: "gris.api.sugestoes.portal.reordenar",
	};

	// {tipo: coluna de triagem}, renderizado pelo servidor.
	const TRIAGEM = (() => {
		const el = document.getElementById("sugestoes-triagem");
		try {
			return JSON.parse((el && el.textContent) || "{}");
		} catch (e) {
			return {};
		}
	})();

	const podeTriar = raiz.dataset.podeTriar === "1";
	const container = document.getElementById("sugestoesKanban");
	const dialogo = document.getElementById("dialog-detalhe-sugestao");
	const selectResponsavel = document.getElementById("detalhe-responsavel");
	const filtroTipo = document.getElementById("filtro-tipo");
	const filtroModulo = document.getElementById("filtro-modulo");

	// Nomes das colunas vindos do esqueleto que o servidor já renderizou, para
	// conseguir desenhar o quadro vazio mesmo quando a carga falha.
	const COLUNAS_INICIAIS = Array.from(container.querySelectorAll(".task-column__title")).map(
		(el) => el.textContent.trim()
	);

	let colunas = [];
	let itemAberto = "";
	let arrastando = "";
	let estaArrastando = false;

	function escapeHtml(valor) {
		return String(valor == null ? "" : valor).replace(
			/[&<>"']/g,
			(ch) => ({ "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;", "'": "&#39;" }[ch])
		);
	}

	function showToast(category, message) {
		document.dispatchEvent(
			new CustomEvent("basecoat:toast", {
				detail: { config: { category, description: message, duration: 5000 } },
			})
		);
	}

	// Registrar um handler por exc_type faz o request.js pular o msgprint padrão
	// (`cleanup` só exibe as mensagens quando `handlers.length === 0`). Junto com
	// `silent`, garante que nenhum erro nosso abra o modal do Desk, que numa
	// página de portal renderiza sem estilo e trava a tela.
	const ERROS_TRATADOS_POR_NOS = {
		ValidationError: () => {},
		PermissionError: () => {},
	};

	function chamar(metodo, args) {
		return new Promise((resolve, reject) => {
			frappe.call({
				method: metodo,
				args: args || {},
				silent: true,
				error_handlers: ERROS_TRATADOS_POR_NOS,
				callback: (resposta) => {
					const dados = resposta && resposta.message;
					if (!dados || dados.ok === false) {
						reject(new Error((dados && dados.error) || "Erro na requisição."));
						return;
					}
					resolve(dados);
				},
				error: (resposta) => reject(new Error(mensagemDoErro(resposta))),
			});
		});
	}

	/** Mensagem legível da falha.
	 *
	 *  O argumento muda conforme o caminho no request.js: o handler de 417 passa
	 *  o corpo da resposta já parseado, enquanto outros passam o próprio xhr.
	 *  Tratar só um dos formatos fazia todo erro de validação virar um texto
	 *  genérico, escondendo a mensagem real do servidor.
	 */
	function mensagemDoErro(resposta) {
		const corpo = (resposta && resposta.responseJSON) || resposta || {};
		try {
			const mensagens = JSON.parse(corpo._server_messages || "[]");
			const primeira = mensagens.length ? JSON.parse(mensagens[0]) : null;
			if (primeira && primeira.message) return primeira.message;
		} catch (e) {
			/* resposta sem _server_messages utilizável */
		}
		if (corpo.exception)
			return String(corpo.exception).split(": ").slice(1).join(": ") || corpo.exception;
		if (corpo.status) return `O servidor respondeu ${corpo.status}.`;
		return "Não foi possível falar com o servidor.";
	}

	function valorSelect(el) {
		if (!el) return "";
		const hidden = el.querySelector('input[type="hidden"]');
		return ((hidden && hidden.value) || "").trim();
	}

	function iniciais(nome) {
		const partes = String(nome || "")
			.trim()
			.split(/\s+/)
			.filter(Boolean);
		if (!partes.length) return "?";
		if (partes.length === 1) return partes[0].slice(0, 2).toUpperCase();
		return (partes[0][0] + partes[partes.length - 1][0]).toUpperCase();
	}

	function paraData(valor) {
		if (!valor) return null;
		const data = new Date(String(valor).replace(" ", "T"));
		return Number.isNaN(data.getTime()) ? null : data;
	}

	function formatarData(valor) {
		const data = paraData(valor);
		if (!data) return "";
		return data.toLocaleDateString("pt-BR", {
			day: "2-digit",
			month: "2-digit",
			year: "numeric",
		});
	}

	function formatarDataHora(valor) {
		const data = paraData(valor);
		if (!data) return "";
		return data.toLocaleString("pt-BR", {
			day: "2-digit",
			month: "2-digit",
			year: "numeric",
			hour: "2-digit",
			minute: "2-digit",
		});
	}

	/* ───────────────────────── render ───────────────────────── */

	function itensVisiveis(itens) {
		const tipo = valorSelect(filtroTipo);
		const modulo = valorSelect(filtroModulo);
		return itens.filter(
			(item) => (!tipo || item.tipo === tipo) && (!modulo || item.modulo === modulo)
		);
	}

	function avatarHtml(item) {
		if (!item.responsavel) {
			return '<span class="task-card__responsavel is-empty" title="Sem responsável">—</span>';
		}
		const nome = item.responsavel_nome || item.responsavel;
		if (item.responsavel_avatar) {
			return `<img class="task-card__responsavel sugestoes-avatar" src="${escapeHtml(
				item.responsavel_avatar
			)}" alt="${escapeHtml(nome)}" title="${escapeHtml(nome)}" />`;
		}
		return `<span class="task-card__responsavel" title="${escapeHtml(nome)}">${escapeHtml(
			iniciais(nome)
		)}</span>`;
	}

	function cardHtml(item) {
		const arrastavel = podeTriar ? "true" : "false";
		const tipoCurto = item.tipo === "Problema" ? "Problema" : "Funcionalidade";
		return `
			<article class="task-card sugestoes-card" data-item="${escapeHtml(
				item.name
			)}" draggable="${arrastavel}">
				<h4 class="task-card__title" title="${escapeHtml(item.titulo)}">${escapeHtml(item.titulo)}</h4>
				<div class="sugestoes-card__badges">
					<span class="sugestoes-badge" data-tipo="${escapeHtml(item.tipo)}">${escapeHtml(tipoCurto)}</span>
					<span class="sugestoes-badge sugestoes-badge--modulo">${escapeHtml(item.modulo)}</span>
				</div>
				<div class="task-card__footer">
					<span class="sugestoes-card__codigo">${escapeHtml(item.name)}</span>
					${avatarHtml(item)}
				</div>
			</article>`;
	}

	function renderizar() {
		container.setAttribute("aria-busy", "false");
		container.innerHTML = colunas
			.map((coluna) => {
				const itens = itensVisiveis(coluna.itens || []);
				const palavra = itens.length === 1 ? "solicitação" : "solicitações";
				const corpo = itens.length
					? itens.map(cardHtml).join("")
					: '<p class="sugestoes-coluna-vazia">Nada por aqui.</p>';
				return `
					<section class="task-column" data-coluna="${escapeHtml(coluna.status)}">
						<header class="task-column__header">
							<div class="task-column__heading">
								<h4 class="task-column__title">${escapeHtml(coluna.status)}</h4>
								<p class="task-column__subtitle">${itens.length} ${palavra}</p>
							</div>
							<span class="g-badge g-badge--secondary">${itens.length}</span>
						</header>
						<div class="task-column__body" data-status="${escapeHtml(coluna.status)}">${corpo}</div>
					</section>`;
			})
			.join("");
	}

	function mostrarErro(mensagem) {
		const caixa = raiz.querySelector("[data-erro]");
		if (!caixa) return;
		caixa.querySelector("[data-erro-texto]").textContent = mensagem;
		caixa.hidden = false;
	}

	function esconderErro() {
		const caixa = raiz.querySelector("[data-erro]");
		if (caixa) caixa.hidden = true;
	}

	function carregarBoard() {
		container.setAttribute("aria-busy", "true");
		return chamar(METODOS.board)
			.then((dados) => {
				esconderErro();
				colunas = dados.colunas || [];
				renderizar();
			})
			.catch((err) => {
				container.setAttribute("aria-busy", "false");
				// Desenha as colunas vazias mesmo em erro: um quadro vazio comunica
				// melhor que seis "Carregando..." parados para sempre.
				colunas = COLUNAS_INICIAIS.map((status) => ({ status, itens: [] }));
				renderizar();
				mostrarErro(`Não foi possível carregar o quadro. ${err.message}`);
			});
	}

	/* ─────────────────────── drag and drop ─────────────────────── */

	/** Tipo cuja coluna de triagem é esta, ou "" se for coluna de status. */
	function tipoDaColuna(status) {
		return Object.keys(TRIAGEM).find((tipo) => TRIAGEM[tipo] === status) || "";
	}

	/** Persiste a prioridade da coluna na ordem em que ela está na tela. */
	function salvarOrdem(status) {
		const coluna = colunas.find((c) => c.status === status);
		if (!coluna) return Promise.resolve();
		return chamar(METODOS.reordenar, {
			status,
			nomes: JSON.stringify((coluna.itens || []).map((item) => item.name)),
		});
	}

	function moverItem(nome, novoStatus, posicao) {
		const anterior = colunas.find((coluna) =>
			(coluna.itens || []).some((item) => item.name === nome)
		);
		const destino = colunas.find((coluna) => coluna.status === novoStatus);
		if (!anterior || !destino) return;

		const item = anterior.itens.find((i) => i.name === nome);
		const mudouDeColuna = anterior.status !== novoStatus;

		// As duas colunas de triagem representam o tipo. Soltar o card na coluna
		// do outro tipo é pedido de reclassificação, não mudança de status — e
		// isso precisa de confirmação, porque muda como o item é classificado.
		const tipoDestino = tipoDaColuna(novoStatus);
		if (mudouDeColuna && tipoDestino && item && item.tipo !== tipoDestino) {
			// Nada é movido antes de confirmar: o card fica onde estava.
			confirmarReclassificacao(item, tipoDestino);
			return;
		}

		// Move otimista: o card acompanha o gesto na hora e volta se o servidor recusar.
		const origem = anterior.itens.findIndex((i) => i.name === nome);
		const [movido] = anterior.itens.splice(origem, 1);
		// Ao reordenar dentro da mesma coluna, tirar o card antes desloca em um
		// tudo que vinha depois dele; sem este ajuste ele cai uma posição acima.
		let alvo = typeof posicao === "number" ? posicao : 0;
		if (!mudouDeColuna && origem < alvo) alvo -= 1;

		movido.status = novoStatus;
		destino.itens.splice(Math.max(0, Math.min(alvo, destino.itens.length)), 0, movido);
		renderizar();

		const aposMudanca = mudouDeColuna
			? chamar(METODOS.status, { name: nome, status: novoStatus })
			: Promise.resolve();

		aposMudanca
			// A ordem é gravada depois do status: o servidor só aceita reordenar
			// nomes que já estejam na coluna.
			.then(() => salvarOrdem(novoStatus))
			.then(() => {
				if (mudouDeColuna) showToast("success", `Movido para “${novoStatus}”.`);
				// Sair de uma coluna deixa buracos na numeração da origem.
				if (mudouDeColuna) salvarOrdem(anterior.status);
			})
			.catch((err) => {
				showToast("error", err.message);
				carregarBoard();
			});
	}

	function confirmarReclassificacao(item, tipoDestino) {
		const dlg = document.getElementById("dialog-reclassificar");
		if (!dlg) return;

		dlg.querySelector("[data-reclassificar-texto]").textContent =
			`“${item.titulo}” está registrada como ${item.tipo}. ` +
			`Movê-la para “${TRIAGEM[tipoDestino]}” muda o tipo para ${tipoDestino}.`;

		const confirmar = dlg.querySelector("[data-reclassificar-confirmar]");
		const cancelar = dlg.querySelector("[data-reclassificar-cancelar]");

		const encerrar = () => {
			confirmar.removeEventListener("click", aoConfirmar);
			cancelar.removeEventListener("click", encerrar);
			dlg.close();
		};

		const aoConfirmar = () => {
			encerrar();
			chamar(METODOS.reclassificar, { name: item.name, tipo: tipoDestino })
				.then(() => {
					showToast("success", `Reclassificada como ${tipoDestino}.`);
					return carregarBoard();
				})
				.catch((err) => showToast("error", err.message));
		};

		confirmar.addEventListener("click", aoConfirmar);
		cancelar.addEventListener("click", encerrar);
		dlg.showModal();
	}

	container.addEventListener("dragstart", (event) => {
		const card = event.target.closest(".task-card");
		if (!card || !podeTriar) return;
		arrastando = card.dataset.item || "";
		estaArrastando = true;
		card.classList.add("is-dragging");
		if (event.dataTransfer) {
			event.dataTransfer.effectAllowed = "move";
			event.dataTransfer.setData("text/plain", arrastando);
		}
	});

	container.addEventListener("dragend", (event) => {
		const card = event.target.closest(".task-card");
		if (card) card.classList.remove("is-dragging");
		limparIndicadores();
		arrastando = "";
		window.setTimeout(() => {
			estaArrastando = false;
		}, 0);
	});

	/** Índice em que o card cairia, pela metade de cada card já na coluna. */
	function posicaoDeInsercao(coluna, y) {
		const cards = Array.from(coluna.querySelectorAll(".task-card:not(.is-dragging)"));
		for (let i = 0; i < cards.length; i += 1) {
			const caixa = cards[i].getBoundingClientRect();
			if (y < caixa.top + caixa.height / 2) return i;
		}
		return cards.length;
	}

	/** Linha mostrando onde o card vai entrar — sem ela o arrasto para
	 *  reordenar é adivinhação. */
	function marcarPosicao(coluna, indice) {
		container
			.querySelectorAll(".is-drop-before, .is-drop-after")
			.forEach((el) => el.classList.remove("is-drop-before", "is-drop-after"));

		const cards = Array.from(coluna.querySelectorAll(".task-card:not(.is-dragging)"));
		if (!cards.length) return;
		if (indice >= cards.length) cards[cards.length - 1].classList.add("is-drop-after");
		else cards[indice].classList.add("is-drop-before");
	}

	function limparIndicadores() {
		container
			.querySelectorAll(".task-column__body.is-drop-target")
			.forEach((el) => el.classList.remove("is-drop-target"));
		container
			.querySelectorAll(".is-drop-before, .is-drop-after")
			.forEach((el) => el.classList.remove("is-drop-before", "is-drop-after"));
	}

	container.addEventListener("dragover", (event) => {
		const coluna = event.target.closest(".task-column__body");
		if (!coluna || !podeTriar || !arrastando) return;
		event.preventDefault();
		coluna.classList.add("is-drop-target");
		marcarPosicao(coluna, posicaoDeInsercao(coluna, event.clientY));
	});

	container.addEventListener("dragleave", (event) => {
		const coluna = event.target.closest(".task-column__body");
		if (!coluna || coluna.contains(event.relatedTarget)) return;
		coluna.classList.remove("is-drop-target");
	});

	container.addEventListener("drop", (event) => {
		const coluna = event.target.closest(".task-column__body");
		if (!coluna || !podeTriar) return;
		event.preventDefault();

		const nome =
			arrastando || (event.dataTransfer && event.dataTransfer.getData("text/plain")) || "";
		const novoStatus = coluna.dataset.status;
		const posicao = posicaoDeInsercao(coluna, event.clientY);
		limparIndicadores();

		// Zera antes de mover: renderizar() reescreve o innerHTML, o card de origem
		// some, e `dragend` não dispara a partir de um elemento já desanexado.
		arrastando = "";
		window.setTimeout(() => {
			estaArrastando = false;
		}, 0);
		if (nome && novoStatus) moverItem(nome, novoStatus, posicao);
	});

	/* ──────────────────────── dialog ──────────────────────── */

	// Mesma marcação do dialog de tarefa (kanban-tarefas.js) para herdar o CSS
	// de .task-comment-item já carregado em base.html.
	function comentarioHtml(comentario) {
		const autor = comentario.autor || "Usuário";
		return `
			<article class="task-comment-item">
				<div class="task-comment-item__row">
					<span class="task-comment-item__avatar" aria-hidden="true">${escapeHtml(iniciais(autor))}</span>
					<div class="task-comment-item__main">
						<header class="task-comment-item__header">
							<strong class="task-comment-item__author">${escapeHtml(autor)}</strong>
							<span class="task-comment-item__time">${escapeHtml(formatarDataHora(comentario.creation))}</span>
						</header>
						<div class="task-comment-item__bubble">
							<div class="task-comment-item__content">${escapeHtml(comentario.texto)}</div>
						</div>
					</div>
				</div>
			</article>`;
	}

	function pintarComentarios(comentarios) {
		const lista = dialogo.querySelector("[data-detalhe-comentarios]");
		lista.innerHTML = (comentarios || []).length
			? comentarios.map(comentarioHtml).join("")
			: '<div class="task-comments-empty">Nenhum comentário ainda.</div>';
	}

	/* ─────────────────────── linha do tempo ─────────────────────── */

	function pintarTimeline(item) {
		const linha = dialogo.querySelector("[data-detalhe-timeline]");
		if (!linha) return;

		const q = (sel) => linha.querySelector(sel);
		const submissao = formatarData(item.data_submissao);
		const inicio = formatarData(item.data_inicio_desenvolvimento);
		const conclusao = formatarData(item.data_conclusao);

		q("[data-timeline-submissao]").textContent = submissao || "-";
		q("[data-timeline-inicio]").textContent = inicio || "Não iniciado";
		q("[data-timeline-conclusao]").textContent = conclusao || "Em aberto";

		// Bolinha preenchida marca etapa já alcançada; vazia, etapa futura.
		q("[data-timeline-dot-inicio]").classList.toggle("is-on-time", Boolean(inicio));
		q("[data-timeline-dot-fim]").classList.toggle("is-on-time", Boolean(conclusao));

		const delta = q("[data-timeline-delta]");
		delta.textContent = conclusao ? duracao(item.data_submissao, item.data_conclusao) : "";
	}

	/** "em 3 dias" / "no mesmo dia" — quanto levou da submissão à entrega. */
	function duracao(de, ate) {
		const inicio = paraData(de);
		const fim = paraData(ate);
		if (!inicio || !fim) return "";
		const dias = Math.round((fim - inicio) / 86400000);
		if (dias <= 0) return "no mesmo dia";
		return dias === 1 ? "em 1 dia" : `em ${dias} dias`;
	}

	// As opções já vêm renderizadas do servidor (acompanhamento.py): o select.js
	// só reconhece os `[role="option"]` presentes na inicialização, então
	// injetá-las aqui faria o clique e o setter de `.value` não terem efeito.
	// Aqui só posicionamos a seleção do item aberto.
	let preenchendoResponsavel = false;

	function preencherResponsaveis(selecionado) {
		if (!selectResponsavel) return;
		// O setter dispara "change" como se fosse escolha do usuário; sem esta
		// trava, só abrir um card já salvaria o responsável de volta.
		preenchendoResponsavel = true;
		try {
			selectResponsavel.value = selecionado || "";
		} finally {
			window.setTimeout(() => {
				preenchendoResponsavel = false;
			}, 0);
		}
	}

	/* ────────────────── editor da descrição ────────────────── */

	let editorDescricao = null;
	let editorPromise = null;

	/** Cria o Toast UI uma vez só e reaproveita entre aberturas do dialog. */
	function garantirEditor() {
		if (editorPromise) return editorPromise;

		const host = dialogo.querySelector("[data-detalhe-editor-host]");
		if (!host || !window.gris || !window.gris.editor) return Promise.resolve(null);

		editorPromise = window.gris.editor
			.create(host, {
				height: "100%",
				toolbarItems: [
					["heading", "bold", "italic", "strike"],
					["hr", "quote"],
					["ul", "ol", "task"],
					["table", "link"],
					["code", "codeblock"],
				],
			})
			.then((instancia) => {
				editorDescricao = instancia;
				return instancia;
			})
			.catch(() => null);

		return editorPromise;
	}

	function montarDescricao(item, podeEditar) {
		const host = dialogo.querySelector("[data-detalhe-editor-host]");
		const leitura = dialogo.querySelector("[data-detalhe-descricao]");
		const btnSalvar = document.getElementById("btn-salvar-descricao");
		const html = item.descricao || "<p>Sem descrição.</p>";

		if (!podeEditar) {
			// O Frappe sanitiza HTML de Text Editor no save, então pode ir como markup.
			leitura.innerHTML = html;
			leitura.hidden = false;
			if (host) host.hidden = true;
			if (btnSalvar) btnSalvar.hidden = true;
			return;
		}

		garantirEditor().then((instancia) => {
			if (!instancia) {
				// Sem editor, cai para leitura: melhor ver o relato do que nada.
				leitura.innerHTML = html;
				leitura.hidden = false;
				if (btnSalvar) btnSalvar.hidden = true;
				return;
			}
			leitura.hidden = true;
			if (host) host.hidden = false;
			instancia.setHTML(item.descricao || "");
			if (btnSalvar) btnSalvar.hidden = false;
		});
	}

	function salvarDescricao() {
		const btnSalvar = document.getElementById("btn-salvar-descricao");
		if (!itemAberto || !editorDescricao) return;

		btnSalvar.disabled = true;
		chamar(METODOS.descricao, { name: itemAberto, descricao: editorDescricao.getHTML() })
			.then(() => showToast("success", "Descrição atualizada."))
			.catch((err) => showToast("error", err.message))
			.finally(() => {
				btnSalvar.disabled = false;
			});
	}

	function abrirDetalhe(nome) {
		itemAberto = nome;
		chamar(METODOS.detalhes, { name: nome })
			.then((dados) => {
				const item = dados.item || {};
				const q = (seletor) => dialogo.querySelector(seletor);

				q("[data-detalhe-titulo]").textContent = item.titulo || "";
				q("[data-detalhe-tipo]").textContent = item.tipo || "";
				q("[data-detalhe-tipo]").setAttribute("data-tipo", item.tipo || "");
				q("[data-detalhe-modulo]").textContent = item.modulo || "";
				q("[data-detalhe-status]").textContent = item.status || "";

				const autor = item.solicitante_nome || item.solicitante || "alguém";
				q("[data-detalhe-meta]").textContent = `${item.name} · aberta por ${autor}`;

				const display = q("[data-detalhe-responsavel-display]");
				if (display) display.value = item.responsavel_nome || "Sem responsável";

				pintarTimeline(item);
				montarDescricao(item, Boolean(dados.pode_editar));

				const linkTarefa = document.getElementById("detalhe-abrir-tarefa");
				if (linkTarefa) {
					linkTarefa.hidden = !item.tarefa;
					if (item.tarefa) linkTarefa.href = "/gestao_tarefas/tarefas";
				}

				pintarComentarios(dados.comentarios);
				dialogo.showModal();

				if (podeTriar) preencherResponsaveis(item.responsavel || "");
			})
			.catch((err) => showToast("error", err.message));
	}

	container.addEventListener("click", (event) => {
		const card = event.target.closest(".task-card");
		if (!card || estaArrastando) return;
		abrirDetalhe(card.dataset.item || "");
	});

	if (selectResponsavel) {
		// O componente emite "change" com detail.value ao escolher uma opção —
		// sinal confiável, ao contrário de ler o hidden input após o clique.
		selectResponsavel.addEventListener("change", (event) => {
			if (preenchendoResponsavel || !itemAberto) return;

			const escolhido = (event.detail && event.detail.value) || "";
			const atual =
				(
					colunas
						.flatMap((coluna) => coluna.itens || [])
						.find((item) => item.name === itemAberto) || {}
				).responsavel || "";
			if (escolhido === atual) return;

			chamar(METODOS.responsavel, { name: itemAberto, user: escolhido })
				.then(() => {
					showToast(
						"success",
						escolhido ? "Responsável alocado." : "Responsável removido."
					);
					return carregarBoard();
				})
				.catch((err) => {
					showToast("error", err.message);
					carregarBoard();
				});
		});
	}

	const btnComentar = document.getElementById("btn-comentar");
	if (btnComentar) {
		btnComentar.addEventListener("click", () => {
			const campo = document.getElementById("detalhe-comentario");
			const texto = (campo.value || "").trim();
			if (!texto || !itemAberto) return;

			btnComentar.disabled = true;
			chamar(METODOS.comentar, { name: itemAberto, texto })
				.then((dados) => {
					campo.value = "";
					pintarComentarios(dados.comentarios);
				})
				.catch((err) => showToast("error", err.message))
				.finally(() => {
					btnComentar.disabled = false;
				});
		});
	}

	const btnSalvarDescricao = document.getElementById("btn-salvar-descricao");
	if (btnSalvarDescricao) btnSalvarDescricao.addEventListener("click", salvarDescricao);

	dialogo.addEventListener("click", (event) => {
		if (event.target.closest("[data-dialog-close]")) dialogo.close();
	});

	/* ──────────────────────── filtros ──────────────────────── */

	[filtroTipo, filtroModulo].forEach((el) => {
		if (!el) return;
		el.addEventListener("click", () => window.setTimeout(renderizar, 0));
	});

	const btnAtualizar = document.getElementById("btn-atualizar");
	if (btnAtualizar) {
		btnAtualizar.addEventListener("click", () => {
			btnAtualizar.disabled = true;
			carregarBoard().finally(() => {
				btnAtualizar.disabled = false;
			});
		});
	}

	const btnRetry = raiz.querySelector("[data-erro-retry]");
	if (btnRetry) btnRetry.addEventListener("click", () => carregarBoard());

	function iniciar() {
		carregarBoard().then(() => {
			// Vindo de /sugestoes/nova, abre direto o item recém-criado.
			const alvo = new URLSearchParams(window.location.search).get("item");
			if (!alvo) return;

			// Tira o ?item= da URL antes de abrir: se o item não existir mais
			// (link antigo, registro apagado), recarregar a página repetiria o erro
			// para sempre.
			if (window.history && window.history.replaceState) {
				window.history.replaceState({}, "", window.location.pathname);
			}
			abrirDetalhe(alvo);
		});
	}

	// Mesmo guarda do tarefas.js: este arquivo é inlinado pelo Frappe no meio do
	// body, então roda antes de os componentes do Basecoat (select.js) terem
	// inicializado os selects de filtro e de responsável, dos quais lemos valor.
	if (document.readyState === "loading") {
		document.addEventListener("DOMContentLoaded", iniciar);
	} else {
		iniciar();
	}
})();
