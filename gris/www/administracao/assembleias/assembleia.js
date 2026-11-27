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
				window.location.reload();
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
				<details class="asm-roteiro__editar">
					<summary>Editar orientação</summary>
					<textarea class="textarea asm-textarea-alta" data-orientacao aria-label="Orientação do item ${
						i + 1
					}">${A.escapeHtml(item.orientacao_conducao)}</textarea>
				</details>
			</li>`
			)
			.join("");

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
