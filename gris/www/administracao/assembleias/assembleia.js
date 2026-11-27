// Página da assembleia: Visão Geral, Edital e Auxílio para condução.
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

	// Aviso guardado antes de recarregar (ex.: edital publicado sem o PDF final).
	const avisoPendente = sessionStorage.getItem("asm-aviso");
	if (avisoPendente) {
		sessionStorage.removeItem("asm-aviso");
		setTimeout(() => A.toast("warning", avisoPendente), 300);
	}

	document.querySelectorAll("[data-data-br]").forEach((el) => {
		el.textContent = A.dataBR(el.dataset.dataBr);
	});
	["dialog-previa-edital", "dialog-publicar"].forEach((id) =>
		A.calendariosPorCimaDoDialog(document.getElementById(id))
	);

	// ─────────────────────────── Visão Geral ───────────────────────────

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
							<code title="${A.escapeHtml(f.link)}">${A.escapeHtml(f.link)}</code>
							<button type="button" class="btn-sm-ghost" data-copiar="${A.escapeHtml(
								f.link
							)}" aria-label="Copiar o link">${A.icone("copy")}</button>
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

	function desenharChecklist() {
		const alvo = document.getElementById("vg-checklist");
		if (!alvo) return;
		const fases = ["Antes", "No dia", "Depois"];
		alvo.innerHTML = fases
			.map((fase) => {
				const etapas = (dados.checklist || []).filter((e) => e.fase === fase);
				if (!etapas.length) return "";
				const itens = etapas
					.map((e) => {
						let detalhe = "";
						if (e.chave === "divulgar_edital") {
							detalhe = `<span class="asm-checklist__detalhe">${
								e.concluido
									? "Marcado ao publicar o edital."
									: `Prazo: ${A.dataBR(
											dados.prazo_edital
									  )}. Marcado sozinho ao publicar o edital.`
							}</span>`;
						} else if (
							e.chave === "separar_materiais" &&
							(dados.materiais || []).length
						) {
							detalhe = `<span class="asm-checklist__detalhe">${dados.materiais
								.map(A.escapeHtml)
								.join(" · ")}</span>`;
						} else if (e.concluido && e.concluido_por) {
							detalhe = `<span class="asm-checklist__detalhe">Marcado por ${A.escapeHtml(
								e.concluido_por
							)}${e.concluido_em ? ` em ${A.dataBR(e.concluido_em)}` : ""}</span>`;
						}
						return `<li><label class="asm-checklist__item">
							<input type="checkbox" class="input" data-etapa="${A.escapeHtml(e.chave)}"${
							e.concluido ? " checked" : ""
						}${e.automatico ? " disabled" : ""}>
							<span><span>${A.escapeHtml(e.titulo)}</span>${detalhe}</span>
						</label></li>`;
					})
					.join("");
				return `<div class="asm-checklist__fase"><h3>${fase}</h3><ul>${itens}</ul></div>`;
			})
			.join("");
	}

	desenharFormularios();
	desenharChecklist();

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

	const salvamento = A.criarSalvamentoAutomatico(estado, {
		metodo: "pagina.salvar_campos",
		aoSalvar(resposta) {
			if (typeof ata !== "undefined" && ata && "marcadores" in resposta) {
				ata.marcadores = resposta.marcadores;
				desenharStatusDaAta();
			}
			Object.entries(resposta.pauta || {}).forEach(([nome, html]) => {
				const alvo = document.querySelector(
					`[data-orientacao-html="${CSS.escape(nome)}"]`
				);
				if (alvo) alvo.innerHTML = html;
			});
		},
	});

	document.getElementById("vg-checklist")?.addEventListener("change", (evento) => {
		const caixa = evento.target.closest("[data-etapa]");
		if (!caixa) return;
		salvamento.agendar(
			{ checklist: { [caixa.dataset.etapa]: caixa.checked ? 1 : 0 } },
			document.querySelector('[data-salvamento="checklist"]')
		);
	});

	async function salvarVisaoGeral(trocarPauta) {
		const botao = document.getElementById("vg-salvar");
		botao.disabled = true;
		try {
			const payload = {
				modified: estado.modified,
				data: A.valorDaData("vg-data") || dados.data,
				tipo: A.valorDoSelect("vg-tipo") || dados.tipo,
				local: document.getElementById("vg-local").value.trim(),
				hora_primeira: document.getElementById("vg-hora-primeira").value,
				hora_segunda: document.getElementById("vg-hora-segunda").value,
				credenciamento: A.valorDoSelect("vg-credenciamento"),
				vagas_delegados:
					parseInt(document.getElementById("vg-vagas-delegados").value, 10) || 0,
				trocar_pauta: trocarPauta ? 1 : 0,
			};
			const resposta = await A.chamar("pagina.salvar_visao_geral", {
				name: dados.name,
				payload: JSON.stringify(payload),
			});
			// Data, tipo e pauta mexem no título, no edital e no roteiro: recarrega tudo.
			if (
				trocarPauta ||
				resposta.data !== dados.data ||
				resposta.tipo !== dados.tipo ||
				resposta.hora_primeira !== dados.hora_primeira
			) {
				window.location.reload();
				return;
			}
			dados = resposta;
			estado.modified = resposta.modified;
			desenharFormularios();
			A.toast("success", "Dados salvos.");
		} catch (erro) {
			A.toast("error", erro.message);
		} finally {
			botao.disabled = false;
		}
	}

	const dialogTrocarPauta = document.getElementById("dialog-trocar-pauta");
	document.getElementById("vg-salvar")?.addEventListener("click", () => {
		const tipo = A.valorDoSelect("vg-tipo");
		if (!publicado && tipo && tipo !== dados.tipo) {
			dialogTrocarPauta.showModal();
			return;
		}
		salvarVisaoGeral(false);
	});
	document.getElementById("btn-trocar-pauta")?.addEventListener("click", () => {
		dialogTrocarPauta.close();
		salvarVisaoGeral(true);
	});
	document.getElementById("btn-manter-pauta")?.addEventListener("click", () => {
		dialogTrocarPauta.close();
		salvarVisaoGeral(false);
	});

	// A segunda convocação acompanha a primeira (+30 min) enquanto ninguém a mudou à mão.
	const horaPrimeira = document.getElementById("vg-hora-primeira");
	const horaSegunda = document.getElementById("vg-hora-segunda");
	horaPrimeira?.addEventListener("change", () => {
		const [h, m] = horaPrimeira.value.split(":").map(Number);
		if (Number.isNaN(h)) return;
		const total = (h * 60 + m + 30) % (24 * 60);
		horaSegunda.value = `${String(Math.floor(total / 60)).padStart(2, "0")}:${String(
			total % 60
		).padStart(2, "0")}`;
	});

	// ─────────────────────────── Edital ───────────────────────────

	const orientacaoPadrao = (finalidade) =>
		(orientacoes.por_finalidade || {})[finalidade] || orientacoes.simples || "";
	const editorPauta = A.criarEditorDePauta(document.getElementById("ed-pauta"), dados.pauta, {
		finalidades,
		orientacaoPadrao,
		somenteLeitura: publicado,
		semOrientacao: true,
	});
	document
		.getElementById("ed-adicionar")
		?.addEventListener("click", () => editorPauta.adicionar());

	function payloadDoEdital() {
		return {
			modified: estado.modified,
			pauta: editorPauta.itens(),
			texto_topo: document.getElementById("ed-topo").value,
			texto_rodape: document.getElementById("ed-rodape").value,
			data_publicacao: A.valorDaData("ed-data-publicacao"),
			incluir_links: A.switchDe("ed-links")?.checked ? 1 : 0,
		};
	}

	async function salvarEdital() {
		const resposta = await A.chamar("pagina.salvar_edital", {
			name: dados.name,
			payload: JSON.stringify(payloadDoEdital()),
		});
		dados = resposta;
		estado.modified = resposta.modified;
		desenharFormularios();
		return resposta;
	}

	document.getElementById("ed-salvar")?.addEventListener("click", async (evento) => {
		const botao = evento.currentTarget;
		botao.disabled = true;
		try {
			await salvarEdital();
			// O roteiro da condução depende da pauta: recarrega para refletir.
			A.toast("success", "Edital salvo.");
			window.setTimeout(() => window.location.reload(), 600);
		} catch (erro) {
			A.toast("error", erro.message);
		} finally {
			botao.disabled = false;
		}
	});

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

	document.getElementById("ed-restaurar")?.addEventListener("click", () => {
		frappe.confirm(
			"Trocar a pauta atual pela pauta padrão das configurações? As mudanças feitas nela se perdem.",
			async () => {
				try {
					await A.chamar("pagina.restaurar_pauta_padrao", { name: dados.name });
					window.location.reload();
				} catch (erro) {
					A.toast("error", erro.message);
				}
			}
		);
	});

	const dialogPublicar = document.getElementById("dialog-publicar");
	let foraDoPrazo = false;
	document.getElementById("ed-publicar")?.addEventListener("click", () => {
		foraDoPrazo = false;
		document.getElementById("publicar-aviso-prazo").hidden = true;
		dialogPublicar.showModal();
	});
	document
		.getElementById("btn-confirmar-publicacao")
		?.addEventListener("click", async (evento) => {
			const botao = evento.currentTarget;
			botao.disabled = true;
			try {
				// Grava o que estiver na tela antes de travar.
				await salvarEdital();
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
				if (resposta.aviso) sessionStorage.setItem("asm-aviso", resposta.aviso);
				window.location.reload();
			} catch (erro) {
				A.toast("error", erro.message);
			} finally {
				botao.disabled = false;
			}
		});

	// ─────────────────────────── Lista de presença ───────────────────────────

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
		const restaurar = evento.target.closest("[data-restaurar-linha]");
		if (restaurar)
			acaoDaLista(
				"restaurar_votante",
				{ linha: restaurar.dataset.restaurarLinha },
				restaurar
			);
	});

	// ─────────────────────────── Ata ───────────────────────────

	let ata = A.lerJson(raiz.dataset.ata, {});
	const indicadorAta = document.querySelector('[data-salvamento="ata"]');
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

	function agendarAta(campos) {
		salvamento.agendar({ ata: campos }, indicadorAta);
	}

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

	async function iniciarEditorDaAta() {
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

	// ─────────────────────────── Candidaturas e assuntos gerais ───────────────────────────

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

	// ─────────────────────────── Auxílio para condução ───────────────────────────

	const gerais = document.getElementById("cd-gerais");
	if (gerais) gerais.innerHTML = dados.orientacoes_gerais_html || ""; // sanitizado no servidor

	const roteiro = document.getElementById("cd-roteiro");
	if (roteiro) {
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

		desenharInscricoes();
		const indicadorConducao = document.querySelector('[data-salvamento="conducao"]');
		roteiro.addEventListener("change", (evento) => {
			const caixa = evento.target.closest("[data-concluido]");
			if (!caixa) return;
			const nome = caixa.closest("[data-item-pauta]").dataset.itemPauta;
			salvamento.agendar(
				{ pauta: { [nome]: { concluido: caixa.checked ? 1 : 0 } } },
				indicadorConducao
			);
		});
		roteiro.addEventListener("input", (evento) => {
			const texto = evento.target.closest("[data-orientacao]");
			if (!texto) return;
			const nome = texto.closest("[data-item-pauta]").dataset.itemPauta;
			salvamento.agendar(
				{ pauta: { [nome]: { orientacao_conducao: texto.value } } },
				indicadorConducao
			);
		});
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

	document.getElementById("vg-criar-pasta")?.addEventListener("click", async (evento) => {
		const botao = evento.currentTarget;
		botao.disabled = true;
		try {
			const resposta = await A.chamar("documentos.criar_pasta", { name: dados.name });
			if (resposta.link) {
				window.location.reload();
				return;
			}
			document.getElementById("vg-pasta-erro").textContent = resposta.erro;
			A.toast("error", resposta.erro);
		} catch (erro) {
			A.toast("error", erro.message);
		} finally {
			botao.disabled = false;
		}
	});

	// ─────────────────────────── Exclusão ───────────────────────────

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
