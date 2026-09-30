// Página de um projeto de captação: conteúdo, decisões, histórico e comentários.
//
// Tudo é desenhado a partir do JSON do projeto; cada ação devolve o projeto
// atualizado e a tela é redesenhada com ele. Quem pode o quê vem de
// `projeto.acoes`, calculado no servidor — e conferido de novo em cada endpoint.
(function () {
	const raiz = document.querySelector(".captacao-projeto");
	if (!raiz || !window.grisCaptacao) return;
	const C = window.grisCaptacao;
	const { escapeHtml, icone, toast, dataBR, dataHoraBR, moeda, paragrafos, lerJson } = C;

	let projeto = lerJson(raiz.dataset.projeto, {});
	let versoes = lerJson(raiz.dataset.versoes, []);
	let comentarios = lerJson(raiz.dataset.comentarios, []);
	let acaoConfirmada = null;

	const TEXTOS = ["descricao", "publico_alvo", "justificativa", "metodologia", "impacto_social"];
	let gantt = null;
	const ENCERRADO = "Cancelado";

	// ───────────────────────── cabeçalho ─────────────────────────

	function renderizarCabecalho() {
		document.getElementById("projeto-titulo").textContent = projeto.titulo;
		const meta = [
			C.badgeDeStatus(projeto.status),
			projeto.tipo_projeto
				? `<span class="badge-outline">${escapeHtml(projeto.tipo_projeto)}</span>`
				: "",
			`<span>${icone("user", "xs")} Proponente: <strong>${escapeHtml(
				projeto.proponente.nome || "—"
			)}</strong></span>`,
			`<span class="text-muted-foreground">${escapeHtml(projeto.name)}</span>`,
		];
		document.getElementById("projeto-meta").innerHTML = meta.filter(Boolean).join("");

		const a = projeto.acoes || {};
		const nome = encodeURIComponent(projeto.name);
		const botoes = [];
		if (projeto.link_pasta_google_drive) {
			botoes.push(
				`<a class="btn-outline" href="${escapeHtml(
					projeto.link_pasta_google_drive
				)}" target="_blank" rel="noopener">${icone(
					"folder-open"
				)}<span>Pasta no Drive</span></a>`
			);
		}
		if (a.editar_ideia) {
			botoes.push(
				`<a class="btn-outline" href="/captacao/nova_ideia?name=${nome}">${icone(
					"pencil"
				)}<span>Editar ideia</span></a>`
			);
		}
		if (a.decidir_preliminar) {
			botoes.push(
				`<button type="button" class="btn-primary" data-abrir="dialog-decisao-preliminar">${icone(
					"check"
				)}<span>Decidir</span></button>`
			);
		}
		if (a.detalhar) {
			botoes.push(
				`<a class="btn-outline" href="/captacao/detalhamento?name=${nome}">${icone(
					"pencil"
				)}<span>Detalhar projeto</span></a>`
			);
		}
		if (a.enviar_para_revisao) {
			botoes.push(
				`<button type="button" class="btn-primary" data-acao="enviar_para_revisao">${icone(
					"send"
				)}<span>Enviar para revisão técnica</span></button>`
			);
		}
		if (a.revisar) {
			botoes.push(
				`<a class="btn-outline" href="/captacao/detalhamento?name=${nome}">${icone(
					"pencil"
				)}<span>Alterar manualmente</span></a>`,
				`<button type="button" class="btn-outline" data-abrir="dialog-pedidos">${icone(
					"message-square"
				)}<span>Pedir alterações</span></button>`,
				`<button type="button" class="btn-primary" data-abrir="dialog-aprovar-revisao">${icone(
					"check"
				)}<span>Aprovar revisão</span></button>`
			);
		}
		if (a.aprovacao_final) {
			botoes.push(
				`<button type="button" class="btn-primary" data-abrir="dialog-aprovacao-final">${icone(
					"check"
				)}<span>Aprovação final</span></button>`
			);
		}
		if (a.cancelar) {
			botoes.push(
				`<button type="button" class="btn-ghost" data-abrir="dialog-cancelar">${icone(
					"x"
				)}<span>Cancelar projeto</span></button>`
			);
		}
		document.getElementById("projeto-acoes").innerHTML = botoes.join("");
	}

	// ───────────────────────── avisos ─────────────────────────

	function renderizarAvisos() {
		const avisos = [];
		if (projeto.status === ENCERRADO && projeto.motivo_encerramento) {
			avisos.push(
				`<div class="alert alert-destructive" role="status">${icone(
					"circle-x"
				)}<h2>${escapeHtml(
					projeto.categoria_encerramento || "Encerrado"
				)}</h2><section>${escapeHtml(projeto.motivo_encerramento)}</section></div>`
			);
		}
		const gerais = (projeto.pendencias || []).filter((p) => !p.secao);
		if (gerais.length) {
			avisos.push(
				`<div class="alert alert-warning" role="status">${icone(
					"message-square"
				)}<h2>Pedidos de alteração</h2><section><ul class="captacao-lista-pedidos">${gerais
					.map((p) => `<li>${pendenciaHtml(p)}</li>`)
					.join("")}</ul></section></div>`
			);
		}
		const a = projeto.acoes || {};
		if (a.enviar_para_revisao && (projeto.secoes_incompletas || []).length) {
			avisos.push(
				`<div class="alert" role="status">${icone(
					"info"
				)}<h2>Falta preencher antes da revisão técnica</h2><section>${escapeHtml(
					projeto.secoes_incompletas.join(", ")
				)}</section></div>`
			);
		}
		document.getElementById("projeto-avisos").innerHTML = avisos.join("");
	}

	function pendenciaHtml(p) {
		const podeResolver =
			projeto.acoes && projeto.acoes.resolver_pendencias && p.etapa !== "Aprovação inicial";
		return `<div class="captacao-pendencia">
			<p class="m-0"><strong>${escapeHtml(p.de_quem || p.autor)}</strong> · ${escapeHtml(
			dataBR(p.data)
		)}</p>
			<p class="m-0">${escapeHtml(p.comentario)}</p>
			${
				podeResolver
					? `<button type="button" class="btn-sm-outline" data-resolver="${escapeHtml(
							p.name
					  )}">${icone("check", "xs")}<span>Marcar como atendido</span></button>`
					: ""
			}
		</div>`;
	}

	// ───────────────────────── seções ─────────────────────────

	function tabelaHtml(cabecalho, linhas) {
		if (!linhas.length) return '<p class="captacao-vazio">Não preenchido.</p>';
		return `<div class="overflow-x-auto"><table class="table captacao-tabela"><thead><tr>${cabecalho
			.map((c) => `<th scope="col">${c}</th>`)
			.join("")}</tr></thead><tbody>${linhas
			.map((l) => `<tr>${l.map((c) => `<td>${c}</td>`).join("")}</tr>`)
			.join("")}</tbody></table></div>`;
	}

	function conteudoDaSecao(campo) {
		if (campo === "titulo") return `<p>${escapeHtml(projeto.titulo)}</p>`;
		if (campo === "resumo") return paragrafos(projeto.resumo);
		if (TEXTOS.includes(campo)) return paragrafos(projeto[campo]);
		if (campo === "objetivos") {
			return tabelaHtml(
				["Objetivo", "Métrica de sucesso"],
				(projeto.objetivos || []).map((o) => [
					escapeHtml(o.objetivo),
					escapeHtml(o.metrica_de_sucesso || "—"),
				])
			);
		}
		if (campo === "equipe") {
			const equipe = projeto.equipe || [];
			if (!equipe.length) return '<p class="captacao-vazio">Não preenchido.</p>';
			return `<ul class="captacao-equipe">${equipe
				.map(
					(p) =>
						`<li><strong>${escapeHtml(p.nome)}</strong>${
							p.papel
								? ` <span class="text-muted-foreground">· ${escapeHtml(
										p.papel
								  )}</span>`
								: ""
						}${paragrafos(p.apresentacao)}</li>`
				)
				.join("")}</ul>`;
		}
		if (campo === "atividades") {
			// O Gantt é montado depois que a seção entra no DOM (ver renderizarSecoes).
			const descricoes = (projeto.atividades || []).filter((l) =>
				(l.descricao || "").trim()
			);
			const lista = descricoes.length
				? `<ul class="captacao-atividades-descricoes">${descricoes
						.map(
							(l) =>
								`<li><strong>${escapeHtml(l.atividade)}</strong> — ${escapeHtml(
									l.descricao
								)}</li>`
						)
						.join("")}</ul>`
				: "";
			return `<div class="captacao-gantt-host" data-gantt-atividades></div>${lista}`;
		}
		if (campo === "recursos") {
			const linhas = (projeto.recursos || []).map((l, i) => [
				escapeHtml(l.categoria || "—"),
				escapeHtml(l.descricao),
				escapeHtml(String(l.quantidade)),
				escapeHtml(moeda(l.valor_unitario)),
				escapeHtml(moeda((projeto.recursos_totais || [])[i])),
			]);
			const tabela = tabelaHtml(
				["Categoria", "Descrição", "Qtd.", "Valor unitário", "Total"],
				linhas
			);
			return linhas.length
				? `${tabela}<p class="captacao-total">Total a captar: <strong>${escapeHtml(
						moeda(projeto.valor_total)
				  )}</strong></p>`
				: tabela;
		}
		return "";
	}

	function renderizarSecoes() {
		const pendenciasPorSecao = {};
		(projeto.pendencias || []).forEach((p) => {
			if (!p.secao) return;
			(pendenciasPorSecao[p.secao] = pendenciasPorSecao[p.secao] || []).push(p);
		});

		// Antes do detalhamento só a ideia existe; mostrar nove seções vazias confunde.
		const soIdeia =
			["Preliminar"].includes(projeto.status) ||
			(projeto.status === ENCERRADO && !projeto.aprovado_inicialmente_em);
		const ideia = ["titulo", "resumo", "objetivos"];
		const secoes = (projeto.secoes || []).filter(
			(s) => s.campo !== "titulo" && (!soIdeia || ideia.includes(s.campo))
		);

		document.getElementById("projeto-secoes").innerHTML =
			C.blocoDoProponente(projeto) +
			secoes
				.map((s) => {
					const pendencias = pendenciasPorSecao[s.campo] || [];
					return `<article class="card captacao-bloco${
						pendencias.length ? " captacao-bloco--pendente" : ""
					}" id="secao-${s.campo}">
					<section class="captacao-bloco__corpo">
						<h2 class="captacao-bloco__titulo">${escapeHtml(s.rotulo)}</h2>
						${pendencias.map(pendenciaHtml).join("")}
						<div class="captacao-conteudo">${conteudoDaSecao(s.campo)}</div>
					</section>
				</article>`;
				})
				.join("");

		// O Gantt é só leitura aqui: o cronograma é editado no detalhamento.
		if (gantt) gantt.destruir();
		gantt = null;
		const host = document.querySelector("[data-gantt-atividades]");
		if (host) {
			gantt = C.criarGantt(host, { editavel: false });
			gantt.desenhar((projeto.atividades || []).map((l, indice) => ({ ...l, indice })));
		}
	}

	// ───────────────────────── histórico ─────────────────────────

	function renderizarHistorico() {
		const decisoes = projeto.decisoes || [];
		document.getElementById("projeto-decisoes").innerHTML = decisoes.length
			? decisoes
					.map((d) => {
						const mudanca =
							d.status_anterior &&
							d.status_novo &&
							d.status_anterior !== d.status_novo
								? `<p class="m-0 text-sm text-muted-foreground">${escapeHtml(
										d.status_anterior
								  )} → ${escapeHtml(d.status_novo)}</p>`
								: "";
						const secao = d.secao_rotulo
							? `<span class="badge-outline">${escapeHtml(d.secao_rotulo)}</span>`
							: "";
						const estado =
							d.decisao === "Solicitar alteração"
								? `<span class="${
										d.resolvido ? "badge-secondary" : "badge-destructive"
								  }">${d.resolvido ? "Atendido" : "Em aberto"}</span>`
								: "";
						return `<li class="captacao-timeline__item">
							<p class="m-0"><strong>${escapeHtml(d.decisao)}</strong> ${secao} ${estado}</p>
							<p class="m-0 text-sm text-muted-foreground">${escapeHtml(d.etapa || "")} · ${escapeHtml(
							d.autor
						)} · ${escapeHtml(dataHoraBR(d.data))}</p>
							${mudanca}
							${d.comentario ? `<p class="captacao-timeline__texto">${escapeHtml(d.comentario)}</p>` : ""}
							${
								d.resumo_alteracoes
									? `<p class="m-0 text-sm">Alterado: ${escapeHtml(
											d.resumo_alteracoes
									  )}</p>`
									: ""
							}
						</li>`;
					})
					.join("")
			: '<li class="captacao-vazio">Nenhuma decisão ainda.</li>';

		document.getElementById("projeto-versoes").innerHTML = versoes.length
			? versoes
					.map(
						(v) => `<li class="captacao-timeline__item">
							<p class="m-0"><strong>${escapeHtml(v.autor)}</strong> · ${escapeHtml(dataHoraBR(v.data))}</p>
							<p class="m-0 text-sm">${escapeHtml(v.campos.join(", "))}</p>
						</li>`
					)
					.join("")
			: '<li class="captacao-vazio">Nenhuma alteração registrada.</li>';
	}

	// ───────────────────────── comentários ─────────────────────────

	function iniciais(nome) {
		return String(nome || "?")
			.split(/\s+/)
			.filter(Boolean)
			.slice(0, 2)
			.map((p) => p[0].toUpperCase())
			.join("");
	}

	function renderizarComentarios() {
		document.getElementById("contador-comentarios").textContent = String(comentarios.length);
		const lista = document.getElementById("projeto-comentarios");
		lista.innerHTML = comentarios.length
			? comentarios
					.map(
						(c) => `<article class="task-comment-item" data-comentario="${escapeHtml(
							c.name
						)}">
					<div class="task-comment-item__row">
						<span class="task-comment-item__avatar" aria-hidden="true">${escapeHtml(iniciais(c.autor))}</span>
						<div class="task-comment-item__main">
							<header class="task-comment-item__header">
								<strong class="task-comment-item__author">${escapeHtml(c.autor)}</strong>
								<span class="task-comment-item__time">${escapeHtml(dataHoraBR(c.criado_em))}${
							c.editado ? " · editado" : ""
						}</span>
							</header>
							<div class="task-comment-item__bubble">
								<div class="task-comment-item__content captacao-comentario__texto">${escapeHtml(c.texto)}</div>
							</div>
							${
								c.pode_editar
									? `<div class="task-comment-item__actions">
								<button type="button" class="btn-sm-ghost" data-editar-comentario="${escapeHtml(c.name)}">${icone(
											"pencil",
											"xs"
									  )}<span>Editar</span></button>
								<button type="button" class="btn-sm-ghost" data-apagar-comentario="${escapeHtml(c.name)}">${icone(
											"trash-2",
											"xs"
									  )}<span>Apagar</span></button>
							</div>`
									: ""
							}
						</div>
					</div>
				</article>`
					)
					.join("")
			: '<p class="task-comments-empty">Nenhum comentário ainda.</p>';
	}

	function editarComentario(name) {
		const item = document.querySelector(`[data-comentario="${CSS.escape(name)}"]`);
		const comentario = comentarios.find((c) => c.name === name);
		if (!item || !comentario) return;
		const bolha = item.querySelector(".task-comment-item__bubble");
		bolha.innerHTML = `<textarea class="textarea" rows="3" maxlength="5000">${escapeHtml(
			comentario.texto
		)}</textarea>
			<div class="task-comment-item__actions">
				<button type="button" class="btn-sm-outline" data-cancelar-edicao>Cancelar</button>
				<button type="button" class="btn-sm-primary" data-salvar-comentario="${escapeHtml(
					name
				)}">Salvar</button>
			</div>`;
		// As ações de Editar/Apagar ficam fora da bolha; some com elas durante a edição.
		item.querySelector(".task-comment-item__main > .task-comment-item__actions")?.remove();
		bolha.querySelector("textarea").focus();
	}

	// ───────────────────────── ações ─────────────────────────

	function aplicarResposta(resposta) {
		if (resposta && resposta.projeto) projeto = resposta.projeto;
		if (resposta && resposta.versoes) versoes = resposta.versoes;
		renderizarTudo();
	}

	async function executar(botao, metodo, args, mensagem, dialogId) {
		if (botao) botao.disabled = true;
		try {
			const resposta = await C.chamar(metodo, { name: projeto.name, ...args });
			if (dialogId) document.getElementById(dialogId)?.close();
			if (resposta.comentarios) {
				comentarios = resposta.comentarios;
				renderizarComentarios();
			} else {
				aplicarResposta(resposta);
			}
			if (mensagem) toast("success", mensagem);
			return true;
		} catch (erro) {
			toast("error", erro.message);
			return false;
		} finally {
			if (botao) botao.disabled = false;
		}
	}

	function valorRadio(nome) {
		const marcado = document.querySelector(`input[name="${nome}"]:checked`);
		return marcado ? marcado.value : "";
	}

	function prepararPedidos() {
		document.getElementById("pedidos-secoes").innerHTML = (projeto.secoes || [])
			.map(
				(s) => `<div class="field">
					<label for="pedido-${s.campo}">${escapeHtml(s.rotulo)}</label>
					<textarea class="textarea" id="pedido-${s.campo}" data-secao="${
					s.campo
				}" rows="2" placeholder="Sem pedido"></textarea>
				</div>`
			)
			.join("");
	}

	function limparDialog(id) {
		const dialog = document.getElementById(id);
		if (!dialog) return;
		dialog.querySelectorAll("textarea").forEach((t) => (t.value = ""));
		const primeiro = dialog.querySelector('input[type="radio"]');
		if (primeiro) primeiro.checked = true;
	}

	function confirmar(texto, acao) {
		document.getElementById("texto-confirmar").textContent = texto;
		acaoConfirmada = acao;
		document.getElementById("dialog-confirmar").showModal();
	}

	const CONFIRMACOES = {
		decidir_preliminar: (botao) =>
			executar(
				botao,
				"decidir_preliminar",
				{
					decisao: valorRadio("decisao_preliminar"),
					comentario: document.getElementById("comentario-preliminar").value.trim(),
				},
				"Decisão registrada.",
				"dialog-decisao-preliminar"
			),
		solicitar_alteracoes: (botao) => {
			const pedidos = Array.from(document.querySelectorAll("#pedidos-secoes textarea"))
				.map((t) => ({ secao: t.dataset.secao, comentario: t.value.trim() }))
				.filter((p) => p.comentario);
			if (!pedidos.length) {
				toast("error", "Escreva ao menos um pedido de alteração.");
				return;
			}
			return executar(
				botao,
				"solicitar_alteracoes",
				{ pedidos: JSON.stringify(pedidos) },
				"Pedidos enviados ao proponente.",
				"dialog-pedidos"
			);
		},
		aprovar_revisao: (botao) =>
			executar(
				botao,
				"aprovar_revisao",
				{ comentario: document.getElementById("comentario-revisao").value.trim() },
				"Revisão aprovada. O projeto foi para a aprovação final.",
				"dialog-aprovar-revisao"
			),
		decidir_aprovacao_final: (botao) =>
			executar(
				botao,
				"decidir_aprovacao_final",
				{
					decisao: valorRadio("decisao_final"),
					comentario: document.getElementById("comentario-final").value.trim(),
				},
				"Decisão registrada.",
				"dialog-aprovacao-final"
			),
		cancelar: (botao) =>
			executar(
				botao,
				"cancelar",
				{ motivo: document.getElementById("motivo-cancelamento").value.trim() },
				"Projeto cancelado.",
				"dialog-cancelar"
			),
	};

	document.addEventListener("click", (evento) => {
		const abrir = evento.target.closest("[data-abrir]");
		if (abrir) {
			const id = abrir.dataset.abrir;
			limparDialog(id);
			if (id === "dialog-pedidos") prepararPedidos();
			document.getElementById(id)?.showModal();
			return;
		}

		const confirmarBotao = evento.target.closest("[data-confirmar]");
		if (confirmarBotao) {
			CONFIRMACOES[confirmarBotao.dataset.confirmar]?.(confirmarBotao);
			return;
		}

		if (evento.target.closest("#btn-confirmar-generico")) {
			const acao = acaoConfirmada;
			acaoConfirmada = null;
			document.getElementById("dialog-confirmar").close();
			if (acao) acao();
			return;
		}

		const acao = evento.target.closest('[data-acao="enviar_para_revisao"]');
		if (acao) {
			confirmar(
				"Enviar o projeto para a revisão técnica? Depois de enviado, ele só volta para edição se a revisão pedir alterações.",
				() =>
					executar(
						acao,
						"enviar_para_revisao",
						{},
						"Projeto enviado para a revisão técnica."
					)
			);
			return;
		}

		const resolver = evento.target.closest("[data-resolver]");
		if (resolver) {
			executar(
				resolver,
				"resolver_pendencia",
				{ decisao: resolver.dataset.resolver },
				"Pedido marcado como atendido."
			);
			return;
		}

		if (evento.target.closest("#btn-comentar")) {
			const campo = document.getElementById("novo-comentario");
			const texto = campo.value.trim();
			if (!texto) {
				toast("error", "Escreva algo antes de comentar.");
				return;
			}
			executar(evento.target.closest("#btn-comentar"), "comentar", { texto }).then((ok) => {
				if (ok) campo.value = "";
			});
			return;
		}

		const editar = evento.target.closest("[data-editar-comentario]");
		if (editar) {
			editarComentario(editar.dataset.editarComentario);
			return;
		}

		if (evento.target.closest("[data-cancelar-edicao]")) {
			renderizarComentarios();
			return;
		}

		const salvar = evento.target.closest("[data-salvar-comentario]");
		if (salvar) {
			const texto = salvar
				.closest(".task-comment-item__bubble")
				.querySelector("textarea")
				.value.trim();
			executar(
				salvar,
				"editar_comentario",
				{ comentario: salvar.dataset.salvarComentario, texto },
				"Comentário editado."
			);
			return;
		}

		const apagar = evento.target.closest("[data-apagar-comentario]");
		if (apagar) {
			confirmar("Apagar este comentário?", () =>
				executar(
					null,
					"apagar_comentario",
					{ comentario: apagar.dataset.apagarComentario },
					"Comentário apagado."
				)
			);
		}
	});

	function renderizarTudo() {
		renderizarCabecalho();
		renderizarAvisos();
		renderizarSecoes();
		renderizarHistorico();
	}

	renderizarTudo();
	renderizarComentarios();
})();
