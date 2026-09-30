// Formulário do detalhamento: o proponente escreve; a RI altera com motivo.
//
// O estado vive em `estado` e o HTML é redesenhado só ao adicionar/remover linhas;
// digitar atualiza o estado sem redesenhar, para não perder o foco do campo.
//
// As atividades formam o cronograma, em dias do projeto (dia 0, dia 10…): cada linha
// tem dia de início e de término, e o Gantt logo abaixo é desenhado a partir do
// estado. Arrastar uma barra muda os dias da linha — e digitar redesenha a barra.
(function () {
	const raiz = document.querySelector(".captacao-detalhamento");
	if (!raiz || !window.grisCaptacao) return;
	const C = window.grisCaptacao;
	const { escapeHtml, icone, toast, moeda, lerJson } = C;

	const projeto = lerJson(raiz.dataset.projeto, {});
	const modo = raiz.dataset.modo;
	const container = document.getElementById("detalhamento-secoes");
	let gantt = null;

	const TEXTOS = {
		descricao: "Detalhes do projeto e dos benefícios pretendidos.",
		publico_alvo: "Quem serão os beneficiados.",
		justificativa: "Por que o projeto é importante.",
		metodologia: "Processos e ferramentas usados para viabilizar os benefícios.",
		impacto_social: "Quais os benefícios do projeto para a sociedade.",
	};
	const CATEGORIAS = ["Humano", "Material", "Financeiro"];

	// Colunas de cada tabela e a linha vazia de partida.
	const TABELAS = {
		objetivos: { vazia: { objetivo: "", metrica_de_sucesso: "" } },
		equipe: { vazia: { nome: "", papel: "", apresentacao: "" } },
		atividades: { vazia: { atividade: "", dia_inicio: "", dia_termino: "", descricao: "" } },
		recursos: { vazia: { categoria: "", descricao: "", quantidade: 1, valor_unitario: 0 } },
	};

	const estado = {
		titulo: projeto.titulo || "",
		resumo: projeto.resumo || "",
	};
	Object.keys(TEXTOS).forEach((campo) => (estado[campo] = projeto[campo] || ""));
	Object.keys(TABELAS).forEach((tabela) => {
		estado[tabela] = (projeto[tabela] || []).map((linha) => ({ ...linha }));
		if (!estado[tabela].length) estado[tabela].push({ ...TABELAS[tabela].vazia });
	});
	estado.recursos.forEach((l) => (l.valor_unitario = formatarDecimal(l.valor_unitario)));
	// O proponente é o primeiro responsável do projeto: com a equipe ainda vazia, ele já
	// entra na lista, faltando só a apresentação.
	if (estado.equipe.length === 1 && !estado.equipe[0].nome && projeto.proponente?.nome) {
		estado.equipe[0] = {
			nome: projeto.proponente.nome,
			papel: "Proponente",
			apresentacao: "",
		};
	}
	// 0 a 0 é o que o campo inteiro guarda quando nada foi digitado: mostra vazio.
	estado.atividades.forEach((l) => {
		const vazio = !Number(l.dia_inicio) && !Number(l.dia_termino);
		l.dia_inicio = vazio ? "" : String(l.dia_inicio ?? "");
		l.dia_termino = vazio ? "" : String(l.dia_termino ?? "");
	});

	// ───────────────────────── números ─────────────────────────

	function formatarDecimal(valor) {
		const numero = Number(valor) || 0;
		return numero
			? numero.toLocaleString("pt-BR", {
					minimumFractionDigits: 2,
					maximumFractionDigits: 2,
			  })
			: "";
	}

	/** "1.234,56" → 1234.56 */
	function lerDecimal(texto) {
		const limpo = String(texto || "")
			.replace(/\s/g, "")
			.replace(/\./g, "")
			.replace(",", ".");
		const numero = Number(limpo);
		return Number.isFinite(numero) ? numero : 0;
	}

	function totalDosRecursos() {
		return estado.recursos.reduce(
			(soma, l) => soma + (Number(l.quantidade) || 0) * lerDecimal(l.valor_unitario),
			0
		);
	}

	// ───────────────────────── desenho ─────────────────────────

	function pendenciasDe(secao) {
		return (projeto.pendencias || []).filter((p) => p.secao === secao);
	}

	function avisoDePendencias(secao) {
		const pendencias = pendenciasDe(secao);
		if (!pendencias.length) return "";
		return `<div class="captacao-pendencias">${pendencias
			.map(
				(p) => `<div class="captacao-pendencia">
					<p class="m-0"><strong>${escapeHtml(p.de_quem || p.autor)}</strong> pediu:</p>
					<p class="m-0">${escapeHtml(p.comentario)}</p>
				</div>`
			)
			.join("")}</div>`;
	}

	function bloco(secao, titulo, dica, corpo) {
		return `<article class="card captacao-bloco${
			pendenciasDe(secao).length ? " captacao-bloco--pendente" : ""
		}">
			<section class="captacao-bloco__corpo">
				<div>
					<h2 class="captacao-bloco__titulo">${escapeHtml(titulo)}</h2>
					${dica ? `<p class="m-0 text-sm text-muted-foreground">${escapeHtml(dica)}</p>` : ""}
				</div>
				${avisoDePendencias(secao)}
				${corpo}
			</section>
		</article>`;
	}

	function linhas(tabela, desenharLinha, rotuloAdicionar) {
		return `<div class="captacao-linhas" data-tabela="${tabela}">
			${estado[tabela]
				.map(
					(linha, i) => `<div class="captacao-linha" data-indice="${i}">
						${desenharLinha(linha, i)}
						<button type="button" class="btn-sm-ghost" data-remover="${i}" aria-label="Remover linha ${
						i + 1
					}">${icone("trash-2")}</button>
					</div>`
				)
				.join("")}
		</div>
		<button type="button" class="btn-sm-outline" data-adicionar="${tabela}">${icone(
			"plus",
			"sm"
		)}<span>${rotuloAdicionar}</span></button>`;
	}

	function campo(nome, valor, atributos) {
		// `type` explícito: o Basecoat estiliza `.input` pelo tipo, e sem ele o campo sai sem borda.
		return `<input class="input" type="text" data-campo="${nome}" value="${escapeHtml(
			valor
		)}" ${atributos || ""}>`;
	}

	function caixa(nome, valor, atributos) {
		return `<textarea class="textarea" data-campo="${nome}" ${atributos || ""}>${escapeHtml(
			valor
		)}</textarea>`;
	}

	function renderizar() {
		const partes = [C.blocoDoProponente(projeto)];

		if (modo === "revisao") {
			partes.push(
				bloco(
					"titulo",
					"Título",
					"",
					`<input class="input" type="text" data-texto="titulo" maxlength="140" value="${escapeHtml(
						estado.titulo
					)}">`
				),
				bloco(
					"resumo",
					"Resumo",
					"",
					`<textarea class="textarea" data-texto="resumo" rows="4">${escapeHtml(
						estado.resumo
					)}</textarea>`
				)
			);
		}

		partes.push(
			bloco(
				"equipe",
				"Apresentação dos responsáveis *",
				"Quem conduz o projeto e o que cada pessoa traz de experiência.",
				linhas(
					"equipe",
					(l) => `<div class="captacao-linha__campos">
						<div class="captacao-linha__campos captacao-linha__campos--duplo">
							${campo("nome", l.nome, 'placeholder="Nome" maxlength="140" aria-label="Nome"')}
							${campo(
								"papel",
								l.papel,
								'placeholder="Papel no projeto" maxlength="140" aria-label="Papel no projeto"'
							)}
						</div>
						${caixa(
							"apresentacao",
							l.apresentacao,
							'rows="2" placeholder="Apresentação" aria-label="Apresentação"'
						)}
					</div>`,
					"Adicionar pessoa"
				)
			),
			bloco(
				"objetivos",
				"Objetivos *",
				"Enviados na ideia; revise se algo mudou.",
				linhas(
					"objetivos",
					(l) => `<div class="captacao-linha__campos captacao-linha__campos--duplo">
						${caixa("objetivo", l.objetivo, 'rows="2" placeholder="Objetivo" aria-label="Objetivo"')}
						${campo(
							"metrica_de_sucesso",
							l.metrica_de_sucesso,
							'placeholder="Métrica de sucesso (opcional)" aria-label="Métrica de sucesso"'
						)}
					</div>`,
					"Adicionar objetivo"
				)
			)
		);

		const rotulos = {
			descricao: "Descrição do projeto *",
			publico_alvo: "Público-alvo *",
			justificativa: "Justificativa *",
			metodologia: "Metodologia *",
		};
		Object.keys(rotulos).forEach((c) =>
			partes.push(
				bloco(
					c,
					rotulos[c],
					TEXTOS[c],
					`<textarea class="textarea" data-texto="${c}" rows="6">${escapeHtml(
						estado[c]
					)}</textarea>`
				)
			)
		);

		partes.push(
			bloco(
				"atividades",
				"Atividades e cronograma *",
				"Conte em dias a partir do início do projeto (dia 0): do dia 0 ao dia 10, do dia 10 ao dia 54… O Gantt abaixo mostra o cronograma.",
				linhas(
					"atividades",
					(l) => `<div class="captacao-linha__campos">
						<div class="captacao-linha__campos captacao-linha__campos--atividade">
							${campo(
								"atividade",
								l.atividade,
								'placeholder="Atividade" maxlength="140" aria-label="Atividade"'
							)}
							${campo(
								"dia_inicio",
								l.dia_inicio,
								'placeholder="Do dia" inputmode="numeric" maxlength="4" autocomplete="off" aria-label="Dia de início"'
							)}
							${campo(
								"dia_termino",
								l.dia_termino,
								'placeholder="Ao dia" inputmode="numeric" maxlength="4" autocomplete="off" aria-label="Dia de término"'
							)}
						</div>
						${caixa(
							"descricao",
							l.descricao,
							'rows="2" placeholder="Descrição (opcional)" aria-label="Descrição da atividade"'
						)}
					</div>`,
					"Adicionar atividade"
				) +
					`<p class="captacao-gantt__dica">Arraste uma barra para mudar o período; as pontas mudam o início e o término.</p>
					<div class="captacao-gantt-host" data-gantt-atividades></div>`
			),
			bloco(
				"impacto_social",
				"Impacto social *",
				TEXTOS.impacto_social,
				`<textarea class="textarea" data-texto="impacto_social" rows="6">${escapeHtml(
					estado.impacto_social
				)}</textarea>`
			),
			bloco(
				"recursos",
				"Recursos *",
				"Humanos, materiais e financeiros necessários, com o custo de cada um.",
				linhas(
					"recursos",
					(l, i) => `<div class="captacao-linha__campos">
						<div class="captacao-categorias" role="radiogroup" aria-label="Categoria">
							${CATEGORIAS.map(
								(cat) =>
									`<label class="captacao-categoria"><input type="radio" name="categoria-${i}" data-campo="categoria" value="${cat}" ${
										l.categoria === cat ? "checked" : ""
									}><span>${cat}</span></label>`
							).join("")}
						</div>
						<div class="captacao-linha__campos captacao-linha__campos--recurso">
							${campo(
								"descricao",
								l.descricao,
								'placeholder="Descrição" maxlength="140" aria-label="Descrição do recurso"'
							)}
							${campo(
								"quantidade",
								l.quantidade,
								'inputmode="decimal" placeholder="Qtd." aria-label="Quantidade"'
							)}
							${campo(
								"valor_unitario",
								l.valor_unitario,
								'inputmode="decimal" placeholder="Valor unitário (R$)" aria-label="Valor unitário"'
							)}
						</div>
					</div>`,
					"Adicionar recurso"
				) +
					`<p class="captacao-total">Total a captar: <strong data-total>${escapeHtml(
						moeda(totalDosRecursos())
					)}</strong></p>`
			)
		);

		container.innerHTML = partes.join("");
		montarGantt();
	}

	// ───────────────────────── cronograma ─────────────────────────

	function montarGantt() {
		if (gantt) gantt.destruir();
		gantt = null;
		const host = container.querySelector("[data-gantt-atividades]");
		if (!host) return;
		gantt = C.criarGantt(host, {
			editavel: true,
			aoMudarDias: (indice, inicio, termino) => {
				const linha = estado.atividades[Number(indice)];
				if (!linha) return;
				linha.dia_inicio = String(inicio);
				linha.dia_termino = String(termino);
				// Só os dois campos da linha: redesenhar o formulário tiraria o foco.
				const campos = container.querySelector(
					`[data-tabela="atividades"] [data-indice="${Number(indice)}"]`
				);
				if (campos) {
					campos.querySelector('[data-campo="dia_inicio"]').value = linha.dia_inicio;
					campos.querySelector('[data-campo="dia_termino"]').value = linha.dia_termino;
				}
				redesenharGantt();
			},
		});
		redesenharGantt();
	}

	function redesenharGantt() {
		if (gantt)
			gantt.desenhar(estado.atividades.map((linha, indice) => ({ ...linha, indice })));
	}

	// ───────────────────────── estado ─────────────────────────

	function aoDigitar(evento) {
		const alvo = evento.target;
		if (alvo.dataset.texto) {
			estado[alvo.dataset.texto] = alvo.value;
			return;
		}
		const linha = alvo.closest("[data-indice]");
		const tabela = alvo.closest("[data-tabela]");
		if (!linha || !tabela || !alvo.dataset.campo) return;
		// Dia do cronograma é número inteiro: o que não for dígito sai na hora.
		if (alvo.dataset.campo.startsWith("dia_")) alvo.value = alvo.value.replace(/\D/g, "");
		window.setTimeout(() => {
			estado[tabela.dataset.tabela][Number(linha.dataset.indice)][alvo.dataset.campo] =
				alvo.value;
			if (tabela.dataset.tabela === "recursos") {
				const total = raiz.querySelector("[data-total]");
				if (total) total.textContent = moeda(totalDosRecursos());
			}
			if (tabela.dataset.tabela === "atividades") redesenharGantt();
		}, 0);
	}

	function aoEscolher(evento) {
		const alvo = evento.target;
		if (alvo.type !== "radio") return;
		const linha = alvo.closest("[data-indice]");
		if (linha) estado.recursos[Number(linha.dataset.indice)].categoria = alvo.value;
	}

	function aoClicar(evento) {
		const adicionar = evento.target.closest("[data-adicionar]");
		if (adicionar) {
			const tabela = adicionar.dataset.adicionar;
			const nova = { ...TABELAS[tabela].vazia };
			// A atividade nova começa onde a última termina: é o caso comum de um
			// cronograma em sequência, e poupa conta de cabeça.
			if (tabela === "atividades") {
				const fins = estado.atividades.map((l) => Number(l.dia_termino) || 0);
				nova.dia_inicio = String(fins.length ? Math.max(...fins) : 0);
			}
			estado[tabela].push(nova);
			renderizar();
			raiz.querySelector(
				`[data-tabela="${tabela}"] .captacao-linha:last-child .input, [data-tabela="${tabela}"] .captacao-linha:last-child .textarea`
			)?.focus();
			return;
		}
		const remover = evento.target.closest("[data-remover]");
		if (remover) {
			const tabela = remover.closest("[data-tabela]").dataset.tabela;
			estado[tabela].splice(Number(remover.dataset.remover), 1);
			if (!estado[tabela].length) estado[tabela].push({ ...TABELAS[tabela].vazia });
			renderizar();
		}
	}

	container.addEventListener("input", aoDigitar);
	container.addEventListener("change", aoEscolher);
	container.addEventListener("click", aoClicar);

	// ───────────────────────── envio ─────────────────────────

	function preenchida(linha) {
		return Object.entries(linha).some(
			([chave, valor]) => chave !== "quantidade" && String(valor || "").trim()
		);
	}

	function payload() {
		const dados = {};
		Object.keys(TEXTOS).forEach((c) => (dados[c] = estado[c]));
		dados.objetivos = estado.objetivos.filter(preenchida);
		dados.equipe = estado.equipe.filter(preenchida);
		dados.atividades = estado.atividades.filter(preenchida);
		dados.recursos = estado.recursos.filter(preenchida).map((l) => ({
			...l,
			quantidade: lerDecimal(l.quantidade),
			valor_unitario: lerDecimal(l.valor_unitario),
		}));
		if (modo === "revisao") {
			dados.titulo = estado.titulo;
			dados.resumo = estado.resumo;
		}
		return JSON.stringify(dados);
	}

	async function enviar(botao, metodo, args, mensagem, destino) {
		botao.disabled = true;
		try {
			await C.chamar(metodo, { name: projeto.name, payload: payload(), ...(args || {}) });
			toast("success", mensagem);
			if (destino) window.location.href = destino;
		} catch (erro) {
			toast("error", erro.message);
		} finally {
			botao.disabled = false;
		}
	}

	const paginaDoProjeto = `/captacao/projeto?name=${encodeURIComponent(projeto.name)}`;

	document
		.getElementById("btn-salvar-rascunho")
		?.addEventListener("click", (evento) =>
			enviar(evento.currentTarget, "salvar_detalhamento", {}, "Detalhamento salvo.")
		);

	document
		.getElementById("btn-enviar-revisao")
		?.addEventListener("click", () =>
			document.getElementById("dialog-confirmar-envio").showModal()
		);

	document.getElementById("btn-confirmar-envio")?.addEventListener("click", (evento) => {
		document.getElementById("dialog-confirmar-envio").close();
		enviar(
			evento.currentTarget,
			"enviar_para_revisao",
			{},
			"Projeto enviado para a revisão técnica.",
			paginaDoProjeto
		);
	});

	document.getElementById("btn-salvar-alteracao")?.addEventListener("click", (evento) => {
		const motivo = document.getElementById("motivo-alteracao").value.trim();
		if (!motivo) {
			toast("error", "Informe o motivo da alteração.");
			return;
		}
		enviar(
			evento.currentTarget,
			"alterar_manualmente",
			{ motivo },
			"Alteração registrada.",
			paginaDoProjeto
		);
	});

	renderizar();
})();
