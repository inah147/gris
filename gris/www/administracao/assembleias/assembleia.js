// Página da assembleia, em quatro etapas: Edital, Inscrições, Sessão e Ata.
// Tudo grava pelo salvamento automático (`pagina.salvar_campos`), numa fila só.
(function () {
	const A = window.grisAssembleias;
	const raiz = document.querySelector(".asm-assembleia");
	if (!A || !raiz) return;

	let dados = A.lerJson(raiz.dataset.dados, {});
	const finalidades = A.lerJson(raiz.dataset.finalidades, []);
	const orientacoes = A.lerJson(raiz.dataset.orientacoes, {});
	const publicado = !!(dados.edital && dados.edital.publicado);

	// Estado compartilhado pelas gravações: cada uma devolve o `modified` novo.
	const estado = { name: dados.name, modified: dados.modified };
	const indicador = document.querySelector('[data-salvamento="pagina"]');

	// Aviso guardado antes de recarregar (ex.: edital publicado sem o PDF final).
	const avisoPendente = sessionStorage.getItem("asm-aviso");
	if (avisoPendente) {
		sessionStorage.removeItem("asm-aviso");
		const [categoria, texto] = avisoPendente.includes("|")
			? avisoPendente.split("|", 2)
			: ["warning", avisoPendente];
		setTimeout(() => A.toast(categoria, texto), 300);
	}

	document.querySelectorAll("[data-data-br]").forEach((el) => {
		el.textContent = A.dataBR(el.dataset.dataBr);
	});
	["dialog-previa-edital", "dialog-publicar"].forEach((id) =>
		A.calendariosPorCimaDoDialog(document.getElementById(id))
	);

	// ─────────────────────────── Salvamento automático ───────────────────────────

	let editorPauta = null;
	let ata = A.lerJson(raiz.dataset.ata, {});

	const assinaturaDaPauta = (pauta) =>
		JSON.stringify((pauta || []).map((i) => [i.name, i.titulo, i.tem_votacao, i.finalidade]));

	const salvamento = A.criarSalvamentoAutomatico(estado, {
		metodo: "pagina.salvar_campos",
		aoSalvar(resposta) {
			if ("marcadores" in resposta) {
				ata.marcadores = resposta.marcadores;
				desenharStatusDaAta();
			}
			Object.entries(resposta.pauta || {}).forEach(([nome, html]) => {
				const alvo = document.querySelector(
					`[data-orientacao-html="${CSS.escape(nome)}"]`
				);
				if (alvo) alvo.innerHTML = html; // sanitizado no servidor
			});
			if (!resposta.pagina) return;
			// Data, tipo, primeira convocação ou pauta trocada mudam título, prazos e roteiro.
			if (resposta.recarregar) {
				sessionStorage.setItem("asm-aviso", "success|Dados salvos.");
				window.location.reload();
				return;
			}
			const pautaMudou =
				assinaturaDaPauta(resposta.pagina.pauta) !== assinaturaDaPauta(dados.pauta);
			dados = resposta.pagina;
			if (editorPauta) editorPauta.sincronizarNomes(dados.pauta);
			desenharFormularios();
			desenharTarefas();
			desenharEtapas();
			if (pautaMudou) desenharRoteiro();
		},
	});

	const salvar = (campos) => salvamento.agendar(campos, indicador);

	// ─────────────────────────── Etapas ───────────────────────────

	const ETAPAS = ["edital", "inscricoes", "sessao", "ata"];
	const ICONE_DO_TOM = {
		alerta: "triangle-alert",
		aviso: "circle-alert",
		info: "calendar-clock",
	};
	const tablist = document.querySelector("#asm-etapas [role=tablist]");

	function desenharEtapas() {
		const etapas = dados.etapas || {};
		(etapas.itens || []).forEach((item, i) => {
			const aba = tablist?.querySelector(`[data-etapa="${item.chave}"]`);
			if (!aba) return;
			aba.dataset.estado = item.estado;
			aba.querySelector("[data-estado-etapa]").textContent = item.descricao;
			aba.querySelector(".asm-etapa__marca").innerHTML =
				item.estado === "feito" ? A.icone("check", "xs") : String(i + 1);
		});

		const alvo = document.getElementById("asm-proximo");
		const p = etapas.proximo;
		alvo.innerHTML = p
			? `<div class="asm-proximo" data-tom="${A.escapeHtml(p.tom)}" role="status">
				${A.icone(ICONE_DO_TOM[p.tom] || "calendar-clock")}
				<div class="asm-proximo__texto">
					<p class="asm-proximo__titulo">${A.escapeHtml(p.titulo)}</p>
					<p class="asm-proximo__descricao">${A.escapeHtml(p.texto)}</p>
				</div>
				<button type="button" class="${
					p.tom === "alerta" ? "btn-sm-primary" : "btn-sm-outline"
				}" data-ir-etapa="${A.escapeHtml(p.etapa)}" data-alvo="${A.escapeHtml(
					p.alvo || ""
			  )}"><span>${A.escapeHtml(p.acao)}</span>${A.icone("arrow-right")}</button>
			</div>`
			: "";
	}

	function mostrarMomento(momento) {
		document.querySelectorAll("[data-momento]").forEach((botao) => {
			botao.setAttribute("aria-pressed", String(botao.dataset.momento === momento));
		});
		document.querySelectorAll("[data-momento-painel]").forEach((painel) => {
			painel.hidden = painel.dataset.momentoPainel !== momento;
		});
	}

	/** Seleciona a aba direto, sem `click()`: na carga da página o script das abas do
	 * Basecoat pode ainda não ter ligado o clique. */
	function selecionarAba(aba) {
		tablist.querySelectorAll("[role=tab]").forEach((outra) => {
			const ativa = outra === aba;
			outra.setAttribute("aria-selected", String(ativa));
			outra.setAttribute("tabindex", ativa ? "0" : "-1");
			const painel = document.getElementById(outra.getAttribute("aria-controls"));
			if (painel) painel.hidden = !ativa;
		});
		history.replaceState(null, "", `#${aba.dataset.etapa}`);
	}

	function irParaEtapa(chave, alvoId) {
		const aba = tablist?.querySelector(`[data-etapa="${chave}"]`);
		if (!aba) return;
		selecionarAba(aba);
		const alvo = alvoId && document.getElementById(alvoId);
		if (!alvo) return;
		const painelDoMomento = alvo.closest("[data-momento-painel]");
		if (painelDoMomento && painelDoMomento.hidden) {
			mostrarMomento(painelDoMomento.dataset.momentoPainel);
		}
		alvo.scrollIntoView({ behavior: "smooth", block: "start" });
	}

	// A etapa vai na URL (#edital, #inscricoes, #sessao, #ata) para dar para linkar direto.
	tablist?.addEventListener("click", (evento) => {
		const aba = evento.target.closest("[data-etapa]");
		if (aba) history.replaceState(null, "", `#${aba.dataset.etapa}`);
	});
	const etapaDaUrl = window.location.hash.slice(1);
	if (ETAPAS.includes(etapaDaUrl)) irParaEtapa(etapaDaUrl);

	raiz.addEventListener("click", (evento) => {
		const botao = evento.target.closest("[data-ir-etapa]");
		if (botao) irParaEtapa(botao.dataset.irEtapa, botao.dataset.alvo);
	});

	document.querySelectorAll("[data-momento]").forEach((botao) => {
		botao.addEventListener("click", () => mostrarMomento(botao.dataset.momento));
	});

	desenharEtapas();

	// ─────────────────────────── Tarefas do checklist ───────────────────────────

	function detalheDaTarefa(e) {
		if (e.chave === "divulgar_edital") {
			return e.concluido
				? "Marcada ao publicar o edital."
				: `Prazo: ${A.dataBR(dados.prazo_edital)}. Marcada sozinha ao publicar o edital.`;
		}
		if (e.chave === "separar_materiais" && (dados.materiais || []).length) {
			return dados.materiais.map(A.escapeHtml).join(" · ");
		}
		if (e.concluido && e.concluido_por) {
			return `Marcada por ${A.escapeHtml(e.concluido_por)}${
				e.concluido_em ? ` em ${A.dataBR(e.concluido_em)}` : ""
			}`;
		}
		return "";
	}

	function desenharTarefas() {
		const porChave = Object.fromEntries((dados.checklist || []).map((e) => [e.chave, e]));
		document.querySelectorAll("[data-tarefas]").forEach((lista) => {
			const tarefas = lista.dataset.tarefas
				.split(",")
				.map((chave) => porChave[chave])
				.filter(Boolean);
			const secao = lista.closest(".asm-tarefas");
			secao.hidden = !tarefas.length;
			const feitas = tarefas.filter((e) => e.concluido).length;
			secao.querySelector("[data-progresso]").textContent = `${feitas} de ${tarefas.length}`;
			lista.innerHTML = tarefas
				.map((e) => {
					const detalhe = detalheDaTarefa(e);
					return `<li><label class="asm-checklist__item">
						<input type="checkbox" class="input" data-tarefa="${A.escapeHtml(e.chave)}"${
						e.concluido ? " checked" : ""
					}${e.automatico ? " disabled" : ""}>
						<span><span>${A.escapeHtml(e.titulo)}</span>${
						detalhe ? `<span class="asm-checklist__detalhe">${detalhe}</span>` : ""
					}</span>
					</label></li>`;
				})
				.join("");
		});
	}

	raiz.addEventListener("change", (evento) => {
		const caixa = evento.target.closest("[data-tarefa]");
		if (!caixa) return;
		const chave = caixa.dataset.tarefa;
		const tarefa = (dados.checklist || []).find((e) => e.chave === chave);
		if (tarefa) tarefa.concluido = caixa.checked ? 1 : 0;
		const secao = caixa.closest(".asm-tarefas");
		const caixas = secao.querySelectorAll("[data-tarefa]");
		const feitas = Array.from(caixas).filter((c) => c.checked).length;
		secao.querySelector("[data-progresso]").textContent = `${feitas} de ${caixas.length}`;
		salvar({ checklist: { [chave]: caixa.checked ? 1 : 0 } });
	});

	desenharTarefas();

	// ─────────────────────────── 1. Edital: convocação ───────────────────────────

	document.getElementById("vg-data")?.addEventListener("datepicker:change", () => {
		const valor = A.valorDaData("vg-data");
		if (valor && valor !== dados.data) salvar({ dados: { data: valor } });
	});

	const dialogTrocarPauta = document.getElementById("dialog-trocar-pauta");
	let tipoEscolhido = null;
	document.getElementById("vg-tipo")?.addEventListener("change", (evento) => {
		const tipo = (evento.detail && evento.detail.value) || A.valorDoSelect("vg-tipo");
		if (!tipo || tipo === dados.tipo) return;
		tipoEscolhido = tipo;
		dialogTrocarPauta.showModal();
	});
	function trocarTipo(trocarPauta) {
		const tipo = tipoEscolhido;
		tipoEscolhido = null;
		dialogTrocarPauta.close();
		salvar({ dados: { tipo, trocar_pauta: trocarPauta ? 1 : 0 } });
		salvamento.gravarAgora().catch((erro) => A.toast("error", erro.message));
	}
	document.getElementById("btn-trocar-pauta")?.addEventListener("click", () => trocarTipo(true));
	document
		.getElementById("btn-manter-pauta")
		?.addEventListener("click", () => trocarTipo(false));
	// Fechar o diálogo sem escolher desfaz a troca na tela.
	dialogTrocarPauta?.addEventListener("close", () => {
		if (tipoEscolhido) {
			tipoEscolhido = null;
			A.definirComponente("vg-tipo", dados.tipo);
		}
	});

	// A segunda convocação acompanha a primeira (+30 min).
	const horaPrimeira = document.getElementById("vg-hora-primeira");
	const horaSegunda = document.getElementById("vg-hora-segunda");
	horaPrimeira?.addEventListener("change", () => {
		const [h, m] = horaPrimeira.value.split(":").map(Number);
		if (Number.isNaN(h) || Number.isNaN(m)) return;
		const total = (h * 60 + m + 30) % (24 * 60);
		horaSegunda.value = `${String(Math.floor(total / 60)).padStart(2, "0")}:${String(
			total % 60
		).padStart(2, "0")}`;
		salvar({ dados: { hora_primeira: horaPrimeira.value, hora_segunda: horaSegunda.value } });
	});
	horaSegunda?.addEventListener("change", () => {
		salvar({ dados: { hora_segunda: horaSegunda.value } });
	});

	document.getElementById("vg-local")?.addEventListener("input", (evento) => {
		const local = evento.target.value.trim();
		if (local) salvar({ dados: { local } });
	});

	// ─────────────────────────── 1. Edital: pauta e textos ───────────────────────────

	function payloadDoEdital() {
		return {
			pauta: editorPauta.itens(),
			texto_topo: document.getElementById("ed-topo").value,
			texto_rodape: document.getElementById("ed-rodape").value,
			data_publicacao: A.valorDaData("ed-data-publicacao"),
			incluir_links: A.switchDe("ed-links")?.checked ? 1 : 0,
		};
	}

	const agendarEdital = () => {
		if (!publicado) salvar({ edital: payloadDoEdital() });
	};

	const orientacaoPadrao = (finalidade) =>
		(orientacoes.por_finalidade || {})[finalidade] || orientacoes.simples || "";
	editorPauta = A.criarEditorDePauta(document.getElementById("ed-pauta"), dados.pauta, {
		finalidades,
		orientacaoPadrao,
		somenteLeitura: publicado,
		semOrientacao: true,
		aoMudar: agendarEdital,
	});
	document
		.getElementById("ed-adicionar")
		?.addEventListener("click", () => editorPauta.adicionar());
	["ed-topo", "ed-rodape"].forEach((id) =>
		document.getElementById(id)?.addEventListener("input", agendarEdital)
	);
	A.switchDe("ed-links")?.addEventListener("change", agendarEdital);
	document
		.getElementById("ed-data-publicacao")
		?.addEventListener("datepicker:change", agendarEdital);

	document.getElementById("ed-previa")?.addEventListener("click", async (evento) => {
		const botao = evento.currentTarget;
		botao.disabled = true;
		try {
			const resposta = await A.chamar("pagina.previa_edital", {
				name: dados.name,
				payload: publicado ? null : JSON.stringify(payloadDoEdital()),
			});
			// HTML sanitizado no servidor (markdown_em_html).
			document.getElementById("previa-edital").innerHTML = resposta.html;
			document.getElementById("dialog-previa-edital").showModal();
		} catch (erro) {
			A.toast("error", erro.message);
		} finally {
			botao.disabled = false;
		}
	});

	function restaurar(pergunta, metodo) {
		frappe.confirm(pergunta, async () => {
			try {
				await salvamento.gravarAgora();
				await A.chamar(metodo, { name: dados.name });
				window.location.reload();
			} catch (erro) {
				A.toast("error", erro.message);
			}
		});
	}
	document
		.getElementById("ed-restaurar-textos")
		?.addEventListener("click", () =>
			restaurar(
				"Trocar os textos antes e depois da pauta pelos textos padrão das configurações?",
				"pagina.restaurar_textos_padrao"
			)
		);
	document
		.getElementById("ed-restaurar")
		?.addEventListener("click", () =>
			restaurar(
				"Trocar a pauta atual pela pauta padrão das configurações? As mudanças feitas nela se perdem.",
				"pagina.restaurar_pauta_padrao"
			)
		);

	// ─────────────────────────── 1. Edital: publicar ───────────────────────────

	const DIA = 24 * 60 * 60 * 1000;
	const paraData = (iso) => {
		const [a, m, d] = String(iso).slice(0, 10).split("-").map(Number);
		return new Date(a, m - 1, d);
	};

	function resumoDaPublicacao() {
		const hoje = new Date();
		hoje.setHours(0, 0, 0, 0);
		const antecedencia = Math.round((paraData(dados.data) - hoje) / DIA);
		const exigidos = Math.round((paraData(dados.data) - paraData(dados.prazo_edital)) / DIA);
		const itens = editorPauta.itens().filter((i) => i.titulo);
		const formularios = (dados.formularios || []).filter((f) => f.previsto);
		const links = A.switchDe("ed-links")?.checked;
		const linhas = [
			`${itens.length} ${itens.length === 1 ? "item" : "itens"} na pauta`,
			formularios.length
				? `${formularios.length} formulário${
						formularios.length === 1 ? "" : "s"
				  } de inscrição${links ? ", com os links no edital" : ", sem os links no edital"}`
				: "Nenhum formulário de inscrição previsto na pauta",
			`Publicado hoje, a ${antecedencia} dia${
				antecedencia === 1 ? "" : "s"
			} da assembleia (o estatuto pede ${exigidos})`,
		];
		document.getElementById("publicar-resumo").innerHTML = linhas
			.map((l) => `<li>${A.escapeHtml(l)}</li>`)
			.join("");
	}

	const dialogPublicar = document.getElementById("dialog-publicar");
	const botaoConfirmarPublicacao = document.getElementById("btn-confirmar-publicacao");
	let foraDoPrazo = false;
	document.getElementById("ed-publicar")?.addEventListener("click", () => {
		foraDoPrazo = false;
		document.getElementById("publicar-aviso-prazo").hidden = true;
		botaoConfirmarPublicacao.textContent = "Publicar";
		resumoDaPublicacao();
		dialogPublicar.showModal();
	});
	botaoConfirmarPublicacao?.addEventListener("click", async () => {
		const botao = botaoConfirmarPublicacao;
		botao.disabled = true;
		try {
			// Grava o que estiver na tela antes de travar.
			await salvamento.gravarAgora();
			const resposta = await A.chamar("pagina.marcar_edital_publicado", {
				name: dados.name,
				fora_do_prazo: foraDoPrazo ? 1 : 0,
			});
			if (resposta.precisa_confirmar) {
				foraDoPrazo = true;
				const aviso = document.getElementById("publicar-aviso-prazo");
				aviso.textContent = `O estatuto exige ${
					resposta.dias
				} dias de antecedência, e o prazo terminou em ${A.dataBR(
					resposta.prazo
				)}. Publicar mesmo assim?`;
				aviso.hidden = false;
				botao.textContent = "Publicar mesmo assim";
				return;
			}
			sessionStorage.setItem(
				"asm-aviso",
				resposta.aviso ? `warning|${resposta.aviso}` : "success|Edital publicado."
			);
			window.location.hash = "inscricoes";
			window.location.reload();
		} catch (erro) {
			A.toast("error", erro.message);
		} finally {
			botao.disabled = false;
		}
	});

	// ─────────────────────────── 2. Inscrições ───────────────────────────

	function desenharFormularios() {
		const lista = document.getElementById("vg-formularios");
		if (!lista) return;
		lista.innerHTML = (dados.formularios || [])
			.map((f) => {
				let estadoHtml;
				if (!f.previsto) {
					estadoHtml = '<span class="badge-outline">Não previsto na pauta</span>';
				} else if (f.reaberto) {
					estadoHtml =
						'<span class="badge-secondary">Reaberto por falta de candidatos</span>';
				} else if (f.aberto) {
					estadoHtml = '<span class="badge">Aberto</span>';
				} else {
					estadoHtml = '<span class="badge-destructive">Fechado</span>';
				}
				const prazo = f.previsto
					? `<span class="text-sm text-muted-foreground">Até ${A.escapeHtml(
							f.prazo
					  )}</span>`
					: "";
				const link = f.previsto
					? `<div class="asm-formulario__link">
							<a class="btn-sm-outline" href="${A.escapeHtml(f.link)}" target="_blank" rel="noopener">${A.icone(
							"external-link"
					  )}<span>Abrir formulário</span></a>
							<button type="button" class="btn-sm-ghost" data-copiar="${A.escapeHtml(f.link)}">${A.icone(
							"copy"
					  )}<span>Copiar link</span></button>
						</div>`
					: "";
				return `<li class="asm-formulario">
					<div class="asm-formulario__topo"><strong>${A.escapeHtml(
						f.rotulo
					)}</strong>${estadoHtml}${prazo}</div>${link}
				</li>`;
			})
			.join("");
	}

	desenharFormularios();

	document.addEventListener("click", async (evento) => {
		const copiar = evento.target.closest("[data-copiar]");
		if (!copiar) return;
		try {
			await navigator.clipboard.writeText(copiar.dataset.copiar);
			A.toast("success", "Link copiado.");
		} catch (e) {
			A.toast("error", "Não foi possível copiar. Selecione o link e copie manualmente.");
		}
	});

	document.getElementById("vg-vagas-delegados")?.addEventListener("input", (evento) => {
		if (evento.target.value === "") return;
		salvar({
			dados: { vagas_delegados: Math.max(parseInt(evento.target.value, 10) || 0, 0) },
		});
	});

	let inscricoes = A.lerJson(raiz.dataset.inscricoes, {});

	function textoLongo(rotulo, valor) {
		return valor
			? `<p class="asm-candidato__rotulo">${rotulo}</p><p class="asm-candidato__texto">${A.escapeHtml(
					valor
			  )}</p>`
			: "";
	}

	function cartaoDeCandidato(cand, { funcao, tipo, retiravel } = {}) {
		const retirada = cand.status === "Retirada";
		return `<article class="asm-candidato${retirada ? " asm-candidato--retirada" : ""}">
			${funcao ? `<p class="asm-candidato__funcao">${A.escapeHtml(funcao)}</p>` : ""}
			<h3 class="asm-candidato__nome">${A.escapeHtml(cand.nome)}</h3>
			<p class="asm-candidato__registro">${
				cand.registro
					? `Registro ${A.escapeHtml(cand.registro)}`
					: "Sem registro informado"
			}${cand.registro_ativo ? "" : " · registro a regularizar até a posse"}</p>
			${textoLongo("Motivação", cand.motivacao)}
			${textoLongo("Biografia", cand.biografia)}
			${
				retirada
					? `<p class="asm-candidato__retirada">Retirada: ${A.escapeHtml(
							cand.motivo_retirada || ""
					  )}</p>`
					: retiravel
					? `<div><button type="button" class="btn-sm-ghost" data-retirar="${tipo}" data-retirar-name="${A.escapeHtml(
							cand.name
					  )}" data-retirar-nome="${A.escapeHtml(cand.nome || cand.titulo)}">${A.icone(
							"user-x"
					  )}<span>Retirar</span></button></div>`
					: ""
			}
		</article>`;
	}

	function desenharInscricoes() {
		const alvo = document.getElementById("cd-inscricoes");
		if (!alvo) return;
		const blocos = [];
		(inscricoes.chapas || []).forEach((chapa) => {
			const retirada = chapa.status === "Retirada";
			blocos.push(`<article class="card asm-bloco"><section>
				<div class="asm-bloco__topo">
					<h2 class="asm-bloco__titulo">Diretoria — ${A.escapeHtml(chapa.titulo)}${
				retirada ? ' <span class="badge-destructive">Retirada</span>' : ""
			}</h2>
					${
						retirada
							? ""
							: `<button type="button" class="btn-sm-ghost" data-retirar="chapa" data-retirar-name="${A.escapeHtml(
									chapa.name
							  )}" data-retirar-nome="${A.escapeHtml(chapa.titulo)}">${A.icone(
									"user-x"
							  )}<span>Retirar chapa</span></button>`
					}
				</div>
				<p class="asm-bloco__descricao">Inscrita por ${A.escapeHtml(
					chapa.responsavel_nome || "—"
				)} em ${A.dataBR(chapa.creation)}.${
				retirada ? ` Motivo: ${A.escapeHtml(chapa.motivo_retirada || "")}` : ""
			}</p>
				<div class="asm-candidatos">${(chapa.membros || [])
					.map((m) =>
						cartaoDeCandidato({ ...m, status: chapa.status }, { funcao: m.funcao })
					)
					.join("")}</div>
			</section></article>`);
		});
		(inscricoes.cargos || []).forEach((grupo) => {
			const lista = grupo.candidaturas || [];
			blocos.push(`<article class="card asm-bloco"><section>
				<h2 class="asm-bloco__titulo">${A.escapeHtml(grupo.cargo)} <span class="badge-outline">${
				lista.filter((cand) => cand.status !== "Retirada").length
			}</span></h2>
				${
					lista.length
						? `<div class="asm-candidatos">${lista
								.map((cand) =>
									cartaoDeCandidato(cand, {
										tipo: "candidatura",
										retiravel: true,
									})
								)
								.join("")}</div>`
						: '<p class="asm-secao__vazio">Nenhuma candidatura.</p>'
				}
			</section></article>`);
		});
		const assuntos = inscricoes.assuntos || [];
		blocos.push(`<article class="card asm-bloco"><section>
			<h2 class="asm-bloco__titulo">Assuntos gerais <span class="badge-outline">${
				assuntos.length
			}</span></h2>
			${
				assuntos.length
					? `<ol class="asm-assuntos">${assuntos
							.map(
								(a) =>
									`<li><p class="asm-candidato__registro">${A.escapeHtml(
										a.nome || "—"
									)} · ${A.dataBR(a.creation)} às ${String(a.creation).slice(
										11,
										16
									)}</p><p class="asm-candidato__texto">${A.escapeHtml(
										a.conteudo
									)}</p></li>`
							)
							.join("")}</ol>`
					: '<p class="asm-secao__vazio">Nenhum assunto enviado.</p>'
			}
		</section></article>`);
		alvo.innerHTML = blocos.join("");
		preencherAoVivo();
	}

	function nomesAtivos(cargo) {
		const grupo = (inscricoes.cargos || []).find((g) => g.cargo === cargo);
		return ((grupo && grupo.candidaturas) || [])
			.filter((cand) => cand.status !== "Retirada")
			.map((cand) => A.escapeHtml(cand.nome));
	}

	function listaOuNenhum(nomes) {
		return nomes.length ? nomes.join(", ") : "nenhum";
	}

	/** Dados ao vivo junto da orientação de cada eleição (CA-10.4). */
	function preencherAoVivo() {
		const assuntos = inscricoes.assuntos || [];
		const chapasAtivas = (inscricoes.chapas || []).filter((ch) => ch.status !== "Retirada");
		const conteudo = {
			"Eleição da mesa": `<p><strong>Candidatos a presidente:</strong> ${listaOuNenhum(
				nomesAtivos("Presidente da mesa")
			)}</p><p><strong>Candidatos a secretário:</strong> ${listaOuNenhum(
				nomesAtivos("Secretário da mesa")
			)}</p><p><strong>Assuntos gerais enviados:</strong> ${assuntos.length}</p>`,
			"Eleição de delegados": `<p><strong>Vagas:</strong> ${
				inscricoes.vagas_delegados
			}</p><p><strong>Candidatos:</strong> ${listaOuNenhum(nomesAtivos("Delegado"))}</p>`,
			"Eleição da comissão fiscal": `<p><strong>Titulares:</strong> ${
				inscricoes.titulares_cf
			} · <strong>Suplentes:</strong> ${
				inscricoes.suplentes_cf
			}</p><p><strong>Candidatos:</strong> ${listaOuNenhum(
				nomesAtivos("Comissão Fiscal")
			)}</p>`,
			"Eleição da diretoria": chapasAtivas.length
				? chapasAtivas
						.map(
							(ch) =>
								`<p><strong>${A.escapeHtml(ch.titulo)}:</strong> ${(
									ch.membros || []
								)
									.map(
										(m) => `${A.escapeHtml(m.funcao)}: ${A.escapeHtml(m.nome)}`
									)
									.join("; ")}</p>`
						)
						.join("")
				: "<p><strong>Chapas inscritas:</strong> nenhuma</p>",
			"Assuntos gerais": assuntos.length
				? `<ol>${assuntos
						.map(
							(a) =>
								`<li>${A.escapeHtml(
									a.conteudo
								)} <span class="text-muted-foreground">— ${A.escapeHtml(
									a.nome || ""
								)}</span></li>`
						)
						.join("")}</ol>`
				: "<p><strong>Assuntos enviados:</strong> nenhum</p>",
		};
		document.querySelectorAll("[data-ao-vivo]").forEach((el) => {
			const html = conteudo[el.dataset.aoVivo];
			el.innerHTML = html ? `<div class="asm-markdown">${html}</div>` : "";
			el.hidden = !html;
		});
	}

	const dialogRetirar = document.getElementById("dialog-retirar");
	let retirando = null;
	raiz.addEventListener("click", (evento) => {
		const botao = evento.target.closest("[data-retirar]");
		if (!botao) return;
		retirando = { tipo: botao.dataset.retirar, name: botao.dataset.retirarName };
		document.getElementById("retirar-nome").textContent = botao.dataset.retirarNome;
		document.getElementById("retirar-motivo").value = "";
		dialogRetirar.showModal();
	});
	document
		.getElementById("btn-confirmar-retirada")
		?.addEventListener("click", async (evento) => {
			const motivo = document.getElementById("retirar-motivo").value.trim();
			if (!motivo) {
				A.toast("error", "Informe o motivo.");
				return;
			}
			const botao = evento.currentTarget;
			botao.disabled = true;
			try {
				const resposta = await A.chamar("formularios.retirar_inscricao", {
					...retirando,
					motivo,
				});
				inscricoes = { ...inscricoes, ...resposta };
				desenharInscricoes();
				dialogRetirar.close();
				A.toast("success", "Inscrição retirada.");
			} catch (erro) {
				A.toast("error", erro.message);
			} finally {
				botao.disabled = false;
			}
		});

	// ─────────────────────────── 3. Sessão: preparar ───────────────────────────

	document.getElementById("vg-credenciamento")?.addEventListener("change", (evento) => {
		const valor =
			(evento.detail && evento.detail.value) ?? A.valorDoSelect("vg-credenciamento");
		salvar({ dados: { credenciamento: valor || "" } });
	});

	let lista = A.lerJson(raiz.dataset.lista, {});
	const RAMOS_AVISO = { Lobinho: "Lobinho", Escoteiro: "Escoteiro", Sênior: "Sênior" };

	function detalheDaLinha(linha) {
		if (linha.tipo_linha === "Jovem representado")
			return "representado por seu responsável legal";
		if (linha.tipo_linha === "Representante de equipe")
			return "nome do representante na assinatura";
		return "";
	}

	function desenharLista() {
		const corpo = document.getElementById("lp-corpo");
		if (!corpo) return;
		const editavel = !!lista.editavel;
		const gerada = document.getElementById("lp-gerada");
		gerada.textContent = lista.gerada_em
			? `Gerada em ${A.dataBR(lista.gerada_em)} às ${String(lista.gerada_em).slice(11, 16)}.`
			: "Ainda não gerada.";
		const botaoGerar = document.getElementById("lp-gerar");
		if (botaoGerar) {
			botaoGerar.querySelector("span").textContent = lista.gerada_em
				? "Gerar de novo"
				: "Gerar lista";
		}

		// Avisos: quem ficou de fora e por quê (CA-07.2).
		const avisos = lista.avisos || {};
		const blocos = [];
		if (avisos.registro_vencido) {
			const n = avisos.registro_vencido;
			blocos.push(
				n === 1
					? "1 associado ativo ficou de fora por registro vencido."
					: `${n} associados ativos ficaram de fora por registro vencido.`
			);
		}
		if (avisos.sem_nascimento) {
			blocos.push(
				`${avisos.sem_nascimento} beneficiário${
					avisos.sem_nascimento === 1 ? "" : "s"
				} sem data de nascimento: fica${
					avisos.sem_nascimento === 1 ? "" : "m"
				} de fora até a data ser preenchida.`
			);
		}
		Object.entries(avisos.sem_equipe || {}).forEach(([ramo, n]) => {
			blocos.push(
				`${n} jove${n === 1 ? "m" : "ns"} do ramo ${A.escapeHtml(
					RAMOS_AVISO[ramo] || ramo
				)} sem equipe cadastrada.`
			);
		});
		document.getElementById("lp-avisos").innerHTML = blocos
			.map(
				(texto) =>
					`<div class="alert">${A.icone(
						"triangle-alert"
					)}<section><p class="m-0">${texto} <a href="/associados">Ver associados</a></p></section></div>`
			)
			.join("");

		const t = lista.totais || {};
		document.getElementById("lp-totais").innerHTML = t.total
			? `<span class="asm-total"><strong>${t.total}</strong> com direito a voto</span>
			   <span class="asm-total"><strong>${
					t.maioria_absoluta
				}</strong> para a maioria absoluta (primeira convocação)</span>
			   ${(t.por_tipo || [])
					.map(
						(p) =>
							`<span class="badge-outline">${A.escapeHtml(p.tipo)}: ${
								p.total
							}</span>`
					)
					.join("")}`
			: "";

		const linhas = lista.linhas || [];
		corpo.innerHTML = linhas.length
			? linhas
					.map(
						(l) => `<tr>
				<td><span class="font-medium">${A.escapeHtml(l.nome)}</span>${
							detalheDaLinha(l)
								? `<span class="asm-tabela__detalhe">${detalheDaLinha(l)}</span>`
								: ""
						}</td>
				<td>${A.escapeHtml(l.tipo_linha)}</td>
				<td>${A.escapeHtml([l.ramo, l.equipe].filter(Boolean).join(" · "))}</td>
				<td class="asm-tabela__acoes">${
					editavel
						? `<button type="button" class="btn-sm-ghost" data-remover-linha="${A.escapeHtml(
								l.name
						  )}" aria-label="Remover ${A.escapeHtml(l.nome)}">${A.icone(
								"x"
						  )}</button>`
						: ""
				}</td>
			</tr>`
					)
					.join("")
			: `<tr><td colspan="4" class="text-muted-foreground">${
					lista.gerada_em
						? "Ninguém na lista."
						: "Gere a lista para ver quem vota nesta assembleia."
			  }</td></tr>`;

		const removidas = lista.removidas || [];
		const blocoRemovidos = document.getElementById("lp-removidos-bloco");
		blocoRemovidos.hidden = !removidas.length;
		blocoRemovidos.querySelector("summary").textContent = `${removidas.length} removido${
			removidas.length === 1 ? "" : "s"
		} da lista`;
		document.getElementById("lp-removidos").innerHTML = removidas
			.map(
				(l) =>
					`<li>${A.escapeHtml(
						l.nome
					)} <span class="text-muted-foreground">· ${A.escapeHtml(l.tipo_linha)}</span>${
						editavel
							? ` <button type="button" class="btn-sm-ghost" data-restaurar-linha="${A.escapeHtml(
									l.name
							  )}">${A.icone("undo-2")}<span>Desfazer</span></button>`
							: ""
					}</li>`
			)
			.join("");
	}

	async function acaoDaLista(metodo, args, botao) {
		if (botao) botao.disabled = true;
		try {
			// A lista grava direto: antes, o que estiver na fila, para não disputar o `modified`.
			await salvamento.gravarAgora();
			lista = await A.chamar(`votantes.${metodo}`, { name: dados.name, ...args });
			estado.modified = lista.modified;
			desenharLista();
			return true;
		} catch (erro) {
			A.toast("error", erro.message);
			return false;
		} finally {
			if (botao) botao.disabled = false;
		}
	}

	desenharLista();

	document.getElementById("lp-gerar")?.addEventListener("click", async (evento) => {
		if (await acaoDaLista("gerar_lista", {}, evento.currentTarget)) {
			A.toast("success", "Lista gerada.");
		}
	});
	document.getElementById("lp-incluir")?.addEventListener("click", async (evento) => {
		const pessoa = A.valorDoSelect("lp-pessoa");
		const campoNome = document.getElementById("lp-nome-livre");
		const ok = await acaoDaLista(
			"incluir_votante",
			{ pessoa, nome_livre: pessoa ? "" : campoNome.value.trim() },
			evento.currentTarget
		);
		if (ok) {
			campoNome.value = "";
			A.definirComponente("lp-pessoa", "");
			A.toast("success", "Incluído na lista.");
		}
	});
	raiz.addEventListener("click", (evento) => {
		const remover = evento.target.closest("[data-remover-linha]");
		if (remover) {
			acaoDaLista("remover_votante", { linha: remover.dataset.removerLinha }, remover);
			return;
		}
		const restaurarLinha = evento.target.closest("[data-restaurar-linha]");
		if (restaurarLinha)
			acaoDaLista(
				"restaurar_votante",
				{ linha: restaurarLinha.dataset.restaurarLinha },
				restaurarLinha
			);
	});

	// ─────────────────────────── 3. Sessão: conduzir ───────────────────────────

	const agendarAta = (campos) => salvar({ ata: campos });

	document.querySelectorAll("[data-campo-ata]").forEach((campo) => {
		campo.addEventListener("input", () => {
			agendarAta({ [campo.dataset.campoAta]: campo.value });
		});
	});
	["presidente", "secretario"].forEach((chave) => {
		document.getElementById(`at-${chave}`)?.addEventListener("change", (evento) => {
			const valor = (evento.detail && evento.detail.value) ?? A.valorDoSelect(`at-${chave}`);
			agendarAta({ [chave]: valor });
		});
	});

	const gerais = document.getElementById("cd-gerais");
	if (gerais) gerais.innerHTML = dados.orientacoes_gerais_html || ""; // sanitizado no servidor

	const roteiro = document.getElementById("cd-roteiro");

	function desenharRoteiro() {
		if (!roteiro) return;
		roteiro.innerHTML = (dados.pauta || [])
			.map(
				(item, i) => `<li class="asm-roteiro__item" data-item-pauta="${A.escapeHtml(
					item.name
				)}">
				<label class="asm-roteiro__titulo">
					<input type="checkbox" class="input" data-concluido${item.concluido ? " checked" : ""}>
					<span><strong>${i + 1}.</strong> ${A.escapeHtml(item.titulo)}</span>
					${item.tem_votacao ? '<span class="badge-outline">Votação</span>' : ""}
				</label>
				<div class="asm-markdown" data-orientacao-html="${A.escapeHtml(item.name)}">${
					item.orientacao_html || ""
				}</div>
				<div class="asm-ao-vivo" data-ao-vivo="${A.escapeHtml(item.finalidade || "")}"></div>
				<details class="asm-roteiro__editar">
					<summary>Editar orientação</summary>
					<textarea class="textarea asm-textarea-alta" data-orientacao aria-label="Orientação do item ${
						i + 1
					}">${A.escapeHtml(item.orientacao_conducao)}</textarea>
				</details>
			</li>`
			)
			.join("");
		preencherAoVivo();
	}

	roteiro?.addEventListener("change", (evento) => {
		const caixa = evento.target.closest("[data-concluido]");
		if (!caixa) return;
		const nome = caixa.closest("[data-item-pauta]").dataset.itemPauta;
		salvar({ pauta: { [nome]: { concluido: caixa.checked ? 1 : 0 } } });
	});
	roteiro?.addEventListener("input", (evento) => {
		const texto = evento.target.closest("[data-orientacao]");
		if (!texto) return;
		const nome = texto.closest("[data-item-pauta]").dataset.itemPauta;
		salvar({ pauta: { [nome]: { orientacao_conducao: texto.value } } });
	});

	desenharRoteiro();
	desenharInscricoes();

	// ─────────────────────────── 4. Ata ───────────────────────────

	let editorAta = null;
	let acompanhamento = null;

	function desenharStatusDaAta() {
		const alvo = document.getElementById("at-status");
		if (!alvo) return;
		const botao = document.getElementById("at-gerar-ia");
		const gerando = ata.status_geracao === "Gerando";
		botao.disabled = gerando;
		botao.querySelector("span").textContent = gerando ? "Gerando…" : "Gerar ata com IA";
		const partes = [];
		if (gerando) {
			partes.push(
				`<div class="alert">${A.icone(
					"loader-circle"
				)}<section><p class="m-0">Gerando a ata. Pode continuar escrevendo as anotações: o texto aparece aqui quando ficar pronto.</p></section></div>`
			);
		} else if (ata.status_geracao === "Falhou" && ata.erro_geracao) {
			partes.push(
				`<div class="alert-destructive">${A.icone(
					"triangle-alert"
				)}<section><p class="m-0">${A.escapeHtml(ata.erro_geracao)}</p></section></div>`
			);
		}
		if (ata.marcadores) {
			partes.push(
				`<p class="asm-marcadores">${A.icone("circle-alert")} ${ata.marcadores} trecho${
					ata.marcadores === 1 ? "" : "s"
				} [A CONFIRMAR] para revisar.</p>`
			);
		}
		alvo.innerHTML = partes.join("");
		if (editorAta) {
			const host = document.getElementById("at-editor");
			host.classList.toggle("is-readonly", gerando);
			host.querySelectorAll("[contenteditable]").forEach((el) =>
				el.setAttribute("contenteditable", gerando ? "false" : "true")
			);
		}
	}

	async function iniciarEditorDasAnotacoes() {
		const host = document.getElementById("at-anotacoes-editor");
		if (!host || !window.gris?.editor?.create) return;
		try {
			const editor = await window.gris.editor.create(host, {
				initialValue: ata.anotacoes || "",
				height: "380px",
				toolbarItems: [["heading", "bold", "italic"], ["ul", "ol", "task"], ["hr"]],
			});
			editor.on("change", () => {
				agendarAta({ anotacoes_secretario: String(editor.getMarkdown() || "") });
			});
		} catch (erro) {
			host.innerHTML =
				'<p class="text-muted-foreground">Não foi possível abrir o editor.</p>';
		}
	}

	async function iniciarEditorDaAta() {
		iniciarEditorDasAnotacoes();
		const host = document.getElementById("at-editor");
		if (!host || !window.gris?.editor?.create) return;
		try {
			editorAta = await window.gris.editor.create(host, {
				initialValue: ata.texto || "",
				height: "560px",
				toolbarItems: [["bold", "italic"], ["ul", "ol"], ["hr"]],
			});
			editorAta.on("change", () => {
				const texto = String(editorAta.getMarkdown() || "");
				ata.marcadores = (texto.match(/\[A CONFIRMAR/g) || []).length;
				agendarAta({ ata_texto: texto });
			});
			desenharStatusDaAta();
		} catch (erro) {
			host.innerHTML =
				'<p class="text-muted-foreground">Não foi possível abrir o editor.</p>';
		}
	}

	function acompanharGeracao() {
		clearInterval(acompanhamento);
		acompanhamento = setInterval(async () => {
			try {
				const resposta = await A.chamar("ata_ia.status_ata_ia", { name: dados.name });
				if (resposta.status_geracao === "Gerando") return;
				clearInterval(acompanhamento);
				ata = resposta;
				if (editorAta && resposta.status_geracao === "Concluída") {
					editorAta.setMarkdown(resposta.texto || "", false);
					A.toast("success", "Ata gerada. Revise o texto.");
				}
				desenharStatusDaAta();
			} catch (erro) {
				clearInterval(acompanhamento);
				A.toast("error", erro.message);
			}
		}, 4000);
	}

	async function pedirAta(substituir) {
		try {
			// Grava as anotações pendentes antes: a IA lê o que está no banco.
			await salvamento.gravarAgora();
			const resposta = await A.chamar("ata_ia.solicitar_ata_ia", {
				name: dados.name,
				substituir_texto: substituir ? 1 : 0,
			});
			if (resposta.precisa_confirmar) {
				frappe.confirm(
					"Já existe um texto da ata. Gerar de novo substitui esse texto. Continuar?",
					() => pedirAta(true)
				);
				return;
			}
			ata = resposta;
			desenharStatusDaAta();
			acompanharGeracao();
		} catch (erro) {
			A.toast("error", erro.message);
		}
	}

	document.getElementById("at-gerar-ia")?.addEventListener("click", () => pedirAta(false));
	desenharStatusDaAta();
	if (ata.status_geracao === "Gerando") acompanharGeracao();
	// O wrapper do editor é carregado com `defer`: só existe depois do parse.
	if (document.readyState === "loading") {
		document.addEventListener("DOMContentLoaded", iniciarEditorDaAta);
	} else {
		iniciarEditorDaAta();
	}

	// ─────────────────────────── Documentos no timbrado ───────────────────────────

	const NOMES_DE_ARQUIVO = { edital: "edital", lista: "lista-de-presenca", ata: "ata" };

	async function baixar(tipo, botao) {
		const rotulo = botao.querySelector("span");
		const original = rotulo.textContent;
		botao.disabled = true;
		rotulo.textContent = "Gerando no Drive…";
		try {
			await salvamento.gravarAgora();
			await A.baixarPdf(
				"documentos.baixar_pdf",
				{ name: dados.name, tipo },
				`${NOMES_DE_ARQUIVO[tipo]}-${dados.name}.pdf`
			);
			A.toast("success", "PDF gerado. O documento editável ficou na pasta da assembleia.");
		} catch (erro) {
			A.toast("error", erro.message);
		} finally {
			botao.disabled = false;
			rotulo.textContent = original;
		}
	}

	raiz.addEventListener("click", (evento) => {
		const botao = evento.target.closest("[data-baixar-pdf]");
		if (!botao) return;
		const tipo = botao.dataset.baixarPdf;
		if (tipo === "ata") {
			const texto = editorAta ? String(editorAta.getMarkdown() || "") : ata.texto || "";
			const pendentes = (texto.match(/\[A CONFIRMAR/g) || []).length;
			if (!texto.trim()) {
				A.toast("error", "Escreva ou gere o texto da ata antes de gerar o PDF.");
				return;
			}
			if (pendentes) {
				frappe.confirm(
					`A ata ainda tem ${pendentes} trecho${
						pendentes === 1 ? "" : "s"
					} [A CONFIRMAR]. Gerar o PDF mesmo assim?`,
					() => baixar(tipo, botao)
				);
				return;
			}
		}
		baixar(tipo, botao);
	});

	// ─────────────────────────── Menu da assembleia ───────────────────────────

	document.getElementById("vg-criar-pasta")?.addEventListener("click", async (evento) => {
		const botao = evento.currentTarget;
		botao.disabled = true;
		try {
			const resposta = await A.chamar("documentos.criar_pasta", { name: dados.name });
			if (resposta.link) {
				sessionStorage.setItem("asm-aviso", "success|Pasta criada no Drive.");
				window.location.reload();
				return;
			}
			A.toast("error", resposta.erro);
		} catch (erro) {
			A.toast("error", erro.message);
		} finally {
			botao.disabled = false;
		}
	});

	const dialogExcluir = document.getElementById("dialog-excluir-assembleia");
	document
		.querySelector("[data-excluir-assembleia]")
		?.addEventListener("click", () => dialogExcluir?.showModal());
	document
		.getElementById("btn-confirmar-exclusao")
		?.addEventListener("click", async (evento) => {
			const botao = evento.currentTarget;
			botao.disabled = true;
			try {
				await A.chamar("endpoints.excluir_assembleia", { name: dados.name });
				window.location.href = "/administracao/assembleias";
			} catch (erro) {
				A.toast("error", erro.message);
				botao.disabled = false;
			}
		});
})();
