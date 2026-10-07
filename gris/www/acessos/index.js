// Portal de acessos: o que a pessoa tem, o que pediu e o que espera a decisão dela.
//
// A página inteira sai de um payload só (`dados_do_portal`), recarregado depois de cada
// ação: o volume é de dezenas de itens, e uma fonte única evita as abas divergirem.
(function () {
	const raiz = document.querySelector(".acessos");
	if (!raiz) return;

	const METODOS = {
		listar: "gris.api.acessos.catalogo.listar_meus_acessos",
		solicitar: "gris.api.acessos.solicitacoes.solicitar",
		cancelar: "gris.api.acessos.solicitacoes.cancelar",
		decidir: "gris.api.acessos.solicitacoes.decidir",
	};

	const SITUACOES = {
		tem: { rotulo: "Você tem", classe: "tem" },
		via_perfil: { rotulo: "Pelo seu perfil", classe: "tem" },
		em_provisionamento: { rotulo: "Liberando", classe: "andamento" },
		em_aprovacao: { rotulo: "Em aprovação", classe: "andamento" },
		aguardando_concessao: { rotulo: "Aprovado, aguardando liberação", classe: "andamento" },
		revogacao_pendente: { rotulo: "Será removido", classe: "alerta" },
		nao_tem: { rotulo: "Você não tem", classe: "neutro" },
		indisponivel: { rotulo: "Indisponível", classe: "neutro" },
	};

	const STATUS_SOLICITACAO = {
		"Em aprovação": "andamento",
		"Aguardando concessão": "andamento",
		Concedida: "tem",
		Recusada: "alerta",
		Cancelada: "neutro",
	};

	let dados = lerJson(raiz.dataset.payload, {});
	let acessoEmFoco = null;
	let solicitacaoEmFoco = null;
	let aoConfirmar = null;

	// ─── utilitários ────────────────────────────────────────────────────────

	function lerJson(texto, padrao) {
		try {
			return JSON.parse(texto || "null") || padrao;
		} catch (e) {
			return padrao;
		}
	}

	function escapeHtml(valor) {
		// Por substituição, e não pelo truque textContent -> innerHTML: aquele não escapa
		// aspas, e o texto também vai para atributos (data-*, title, href).
		return String(valor == null ? "" : valor)
			.replace(/&/g, "&amp;")
			.replace(/</g, "&lt;")
			.replace(/>/g, "&gt;")
			.replace(/"/g, "&quot;")
			.replace(/'/g, "&#39;");
	}

	function icone(nome, tamanho) {
		return `<svg class="ds-lucide ds-lucide--${
			tamanho || "sm"
		}" aria-hidden="true" focusable="false" viewBox="0 0 24 24"><use href="/assets/gris/design_system/icons/lucide/sprite.svg#${escapeHtml(
			nome
		)}" /></svg>`;
	}

	function textoSimples(html) {
		const doc = new DOMParser().parseFromString(String(html == null ? "" : html), "text/html");
		return (doc.body.textContent || "").trim();
	}

	function formatarData(valor) {
		if (!valor) return "";
		const [data] = String(valor).split(" ");
		const [ano, mes, dia] = data.split("-");
		return dia && mes && ano ? `${dia}/${mes}/${ano}` : String(valor);
	}

	// O acesso por seção vira "Contribuições da seção — Alcateia" nos títulos.
	function rotuloDoPedido(solicitacao) {
		return solicitacao.secao
			? `${solicitacao.acesso} — ${solicitacao.secao}`
			: solicitacao.acesso;
	}

	function toast(categoria, titulo) {
		document.dispatchEvent(
			new CustomEvent("basecoat:toast", {
				detail: { config: { category: categoria, title: titulo, duration: 4500 } },
			})
		);
	}

	// `frappe.call` no portal engole a mensagem do `frappe.throw`, e aqui ela importa:
	// é ela que diz por que o pedido não pôde ser feito.
	async function chamar(metodo, args, opcoes) {
		const get = opcoes && opcoes.get;
		const consulta = get ? `?${new URLSearchParams(args || {}).toString()}` : "";
		const resposta = await fetch(`/api/method/${metodo}${consulta}`, {
			method: get ? "GET" : "POST",
			headers: {
				"Content-Type": "application/json",
				Accept: "application/json",
				"X-Frappe-CSRF-Token": (window.frappe && frappe.csrf_token) || "",
			},
			credentials: "same-origin",
			body: get ? undefined : JSON.stringify(args || {}),
		});
		const json = await resposta.json().catch(() => ({}));
		if (!resposta.ok) {
			let mensagem = "Não foi possível concluir a ação.";
			try {
				const lista = JSON.parse(json._server_messages || "[]");
				if (lista.length) mensagem = JSON.parse(lista[0]).message;
			} catch (e) {
				/* fica a mensagem genérica */
			}
			throw new Error(textoSimples(mensagem));
		}
		return json.message;
	}

	async function recarregar() {
		dados = await chamar(METODOS.listar, {}, { get: true });
		renderizarTudo();
	}

	function abrirDialog(id) {
		const dialog = document.getElementById(id);
		if (dialog && !dialog.open) dialog.showModal();
	}

	function fecharDialog(id) {
		const dialog = document.getElementById(id);
		if (dialog && dialog.open) dialog.close();
	}

	async function comBotaoOcupado(botao, acao) {
		botao.disabled = true;
		botao.setAttribute("aria-busy", "true");
		try {
			await acao();
		} finally {
			botao.disabled = false;
			botao.removeAttribute("aria-busy");
		}
	}

	// ─── renderização ───────────────────────────────────────────────────────

	function selo(texto, classe) {
		return `<span class="badge acessos-selo acessos-selo--${classe}">${escapeHtml(
			texto
		)}</span>`;
	}

	function seloDaSituacao(item) {
		// "Você não tem" em todo card vira ruído: a ausência de selo já diz isso.
		if (item.estado.situacao === "nao_tem") return "";
		const situacao = SITUACOES[item.estado.situacao] || SITUACOES.nao_tem;
		let rotulo = situacao.rotulo;
		if (item.estado.situacao === "em_aprovacao" && item.solicitacao) {
			const s = item.solicitacao;
			if (s.total_etapas > 1)
				rotulo = `Em aprovação · etapa ${s.etapa_atual} de ${s.total_etapas}`;
		}
		return selo(rotulo, situacao.classe);
	}

	function detalhesDoItem(item) {
		const linhas = [];
		const estado = item.estado;

		if (estado.situacao === "via_perfil" && estado.detalhe) {
			linhas.push(
				`Vem do perfil <strong>${escapeHtml(
					estado.detalhe
				)}</strong>, definido pela sua função.`
			);
		}
		if (item.tipo === "Drive compartilhado" && estado.detalhe) {
			linhas.push(`Permissão: ${escapeHtml(estado.detalhe)}`);
		}
		if (estado.expira_em) {
			linhas.push(`Válido até ${escapeHtml(formatarData(estado.expira_em))}`);
		}
		if (item.tipo === "Ferramenta externa" && estado.detalhe) {
			linhas.push(`Conta: ${escapeHtml(estado.detalhe)}`);
		}
		if (item.recorte) {
			const r = item.recorte;
			if (r.concedidas.length) {
				linhas.push(
					`Seções liberadas: <strong>${r.concedidas.map(escapeHtml).join(", ")}</strong>`
				);
			} else if (["tem", "via_perfil"].includes(estado.situacao)) {
				linhas.push("Nenhuma seção pedida: você vê só a seção que chefia, se for o caso.");
			}
			if (r.pedidas.length) {
				linhas.push(
					`Em aprovação: ${r.pedidas.map((p) => escapeHtml(p.secao)).join(", ")}`
				);
			}
			if (!item.pode_solicitar && item.motivo_bloqueio) {
				linhas.push(escapeHtml(item.motivo_bloqueio));
			}
		}
		if (estado.situacao === "revogacao_pendente") {
			linhas.push("A equipe de tecnologia vai remover esta conta.");
		}
		if (item.vagas && item.vagas.limite) {
			const livres = item.vagas.disponiveis;
			linhas.push(
				livres > 0
					? `${livres} de ${item.vagas.limite} licenças livres`
					: `Sem licenças livres no momento (${item.vagas.limite} no total)`
			);
		}
		if (
			!item.recorte &&
			estado.situacao === "nao_tem" &&
			!item.pode_solicitar &&
			item.motivo_bloqueio
		) {
			linhas.push(escapeHtml(item.motivo_bloqueio));
		}
		if (!linhas.length) return "";
		return `<ul class="acessos-card__meta">${linhas
			.map((l) => `<li>${l}</li>`)
			.join("")}</ul>`;
	}

	function acoesDoItem(item) {
		const botoes = [];
		const situacao = item.estado.situacao;

		if (item.pode_solicitar) {
			const outra =
				item.recorte && (item.recorte.concedidas.length || item.recorte.pedidas.length);
			botoes.push(
				`<button type="button" class="btn-sm-primary" data-acao="solicitar" data-acesso="${escapeHtml(
					item.name
				)}">${icone("send")}<span>${
					outra ? "Pedir outra seção" : "Solicitar"
				}</span></button>`
			);
		}
		if (item.recorte) {
			item.recorte.pedidas.forEach((pedido) => {
				botoes.push(
					`<button type="button" class="btn-sm-outline acessos-card__cancelar-secao" data-acao="cancelar" data-solicitacao="${escapeHtml(
						pedido.solicitacao
					)}">Cancelar pedido de ${escapeHtml(pedido.secao)}</button>`
				);
			});
		} else if (!item.pode_solicitar && item.solicitacao) {
			botoes.push(
				`<button type="button" class="btn-sm-outline" data-acao="cancelar" data-solicitacao="${escapeHtml(
					item.solicitacao.name
				)}">Cancelar pedido</button>`
			);
		}
		if (item.link_externo && ["tem", "via_perfil"].includes(situacao)) {
			botoes.push(
				`<a class="btn-sm-outline" href="${escapeHtml(
					item.link_externo
				)}" target="_blank" rel="noopener noreferrer">${icone(
					"external-link"
				)}<span>Abrir</span></a>`
			);
		}
		if (!botoes.length) return "";
		return `<footer class="acessos-card__acoes">${botoes.join("")}</footer>`;
	}

	function cardDoItem(item) {
		const oQueMuda = item.o_que_muda
			? `<details class="acessos-card__detalhes"><summary>O que muda</summary><p>${escapeHtml(
					item.o_que_muda
			  )}</p></details>`
			: "";
		return `
			<article class="card acessos-card" data-situacao="${escapeHtml(item.estado.situacao)}">
				<header class="acessos-card__topo">
					<span class="acessos-card__icone">${icone(item.icone || "key-round", "md")}</span>
					<div class="acessos-card__titulos">
						<h3 class="acessos-card__titulo">${escapeHtml(item.titulo)}</h3>
						${seloDaSituacao(item)}
					</div>
				</header>
				<p class="acessos-card__descricao">${escapeHtml(item.descricao)}</p>
				${oQueMuda}
				${detalhesDoItem(item)}
				${acoesDoItem(item)}
			</article>`;
	}

	function clonarVazio(idTemplate) {
		const template = document.getElementById(idTemplate);
		return template ? template.innerHTML : "";
	}

	function semAcento(texto) {
		return String(texto || "")
			.normalize("NFD")
			.replace(/[\u0300-\u036f]/g, "")
			.toLowerCase();
	}

	function renderizarGrade(aba, alvoId) {
		const alvo = document.getElementById(alvoId);
		if (!alvo) return;
		const busca = document.getElementById("acessos-busca");
		const termo = semAcento(busca ? busca.value : "");
		const daAba = (dados.itens || []).filter((item) => item.aba === aba);
		const itens = daAba.filter(
			(item) =>
				!termo ||
				semAcento(`${item.titulo} ${item.descricao} ${item.o_que_muda || ""}`).includes(
					termo
				)
		);
		if (itens.length) {
			alvo.innerHTML = itens.map(cardDoItem).join("");
		} else if (daAba.length) {
			alvo.innerHTML = clonarVazio("acessos-vazio-busca");
		} else {
			alvo.innerHTML = clonarVazio("acessos-vazio-catalogo");
		}
	}

	function etapasDaSolicitacao(solicitacao) {
		if (!solicitacao.etapas || !solicitacao.etapas.length) return "";
		const itens = solicitacao.etapas.map((etapa) => {
			const atual =
				solicitacao.status === "Em aprovação" &&
				etapa.ordem === solicitacao.etapa_atual &&
				etapa.decisao === "Pendente";
			const classe = atual ? "atual" : (etapa.decisao || "Pendente").toLowerCase();
			const nomeIcone =
				etapa.decisao === "Aprovada"
					? "circle-check"
					: etapa.decisao === "Recusada"
					? "circle-x"
					: "clock";
			let texto = `<strong>${escapeHtml(
				etapa.descricao || `Etapa ${etapa.ordem}`
			)}</strong>`;
			if (etapa.decisao !== "Pendente" && etapa.decidido_por) {
				texto += ` · ${escapeHtml(etapa.decisao.toLowerCase())} por ${escapeHtml(
					etapa.decidido_por
				)}`;
				if (etapa.decidido_em)
					texto += ` em ${escapeHtml(formatarData(etapa.decidido_em))}`;
			} else if (atual) {
				texto += " · aguardando decisão";
			}
			if (etapa.observacao)
				texto += `<span class="acessos-etapas__obs">${escapeHtml(
					etapa.observacao
				)}</span>`;
			return `<li class="acessos-etapas__item acessos-etapas__item--${escapeHtml(
				classe
			)}">${icone(nomeIcone)}<span>${texto}</span></li>`;
		});
		return `<ol class="acessos-etapas" aria-label="Fluxo de aprovação">${itens.join("")}</ol>`;
	}

	function itemDeSolicitacao(solicitacao, modo) {
		const classe = STATUS_SOLICITACAO[solicitacao.status] || "neutro";
		const quem =
			modo === "pendente"
				? `<p class="acessos-solicitacao__quem">${icone("user")}<span>${escapeHtml(
						solicitacao.solicitante_nome
				  )}</span></p>`
				: "";
		const justificativa = solicitacao.justificativa
			? `<p class="acessos-solicitacao__texto"><span class="text-muted-foreground">Justificativa:</span> ${escapeHtml(
					solicitacao.justificativa
			  )}</p>`
			: "";
		const motivo =
			solicitacao.motivo && ["Recusada", "Cancelada"].includes(solicitacao.status)
				? `<p class="acessos-solicitacao__texto"><span class="text-muted-foreground">Motivo:</span> ${escapeHtml(
						solicitacao.motivo
				  )}</p>`
				: "";

		const acoes = [];
		if (modo === "pendente" && solicitacao.pode_decidir) {
			acoes.push(
				`<button type="button" class="btn-sm-primary" data-acao="decidir" data-solicitacao="${escapeHtml(
					solicitacao.name
				)}">Decidir</button>`
			);
		}
		if (modo === "minha" && solicitacao.pode_cancelar) {
			acoes.push(
				`<button type="button" class="btn-sm-outline" data-acao="cancelar" data-solicitacao="${escapeHtml(
					solicitacao.name
				)}">Cancelar pedido</button>`
			);
		}

		return `
			<article class="acessos-solicitacao">
				<header class="acessos-solicitacao__topo">
					<div>
						<h3 class="acessos-solicitacao__titulo">${escapeHtml(rotuloDoPedido(solicitacao))}</h3>
						<span class="acessos-solicitacao__data">Pedido em ${escapeHtml(
							formatarData(solicitacao.criada_em)
						)}</span>
					</div>
					${selo(solicitacao.status, classe)}
				</header>
				${quem}
				${justificativa}
				${motivo}
				${etapasDaSolicitacao(solicitacao)}
				${acoes.length ? `<footer class="acessos-card__acoes">${acoes.join("")}</footer>` : ""}
			</article>`;
	}

	function renderizarSolicitacoes() {
		const alvo = document.getElementById("acessos-solicitacoes");
		if (!alvo) return;
		const lista = dados.solicitacoes || [];
		alvo.innerHTML = lista.length
			? lista.map((s) => itemDeSolicitacao(s, "minha")).join("")
			: clonarVazio("acessos-vazio-solicitacoes");
	}

	function renderizarPendentes() {
		const secao = document.getElementById("acessos-pendentes");
		const alvo = document.getElementById("acessos-pendentes-lista");
		if (!secao || !alvo) return;
		const lista = dados.pendentes || [];
		secao.hidden = !lista.length;
		alvo.innerHTML = lista.map((s) => itemDeSolicitacao(s, "pendente")).join("");
	}

	function renderizarTudo() {
		renderizarPendentes();
		renderizarGrade("gris", "acessos-grade-gris");
		renderizarGrade("ferramentas", "acessos-grade-ferramentas");
		renderizarSolicitacoes();
	}

	// ─── ações ──────────────────────────────────────────────────────────────

	function porNome(nome) {
		return (dados.itens || []).find((item) => item.name === nome) || null;
	}

	function solicitacaoPorNome(nome) {
		return (
			(dados.pendentes || []).find((s) => s.name === nome) ||
			(dados.solicitacoes || []).find((s) => s.name === nome) ||
			(dados.itens || []).map((i) => i.solicitacao).find((s) => s && s.name === nome) ||
			null
		);
	}

	function abrirSolicitar(nome) {
		const item = porNome(nome);
		if (!item) return;
		acessoEmFoco = item;

		const dialog = document.getElementById("dialog-solicitar");
		dialog.querySelector("h2").textContent = `Solicitar: ${item.titulo}`;
		document.getElementById("solicitar-descricao").textContent = item.descricao || "";
		const blocoMuda = document.getElementById("solicitar-o-que-muda-bloco");
		blocoMuda.hidden = !item.o_que_muda;
		document.getElementById("solicitar-o-que-muda").textContent = item.o_que_muda || "";

		const conta = document.getElementById("solicitar-conta");
		conta.hidden = !item.email_concessao;
		conta.querySelector("span").textContent = item.email_concessao
			? `O acesso será criado na conta ${item.email_concessao}.`
			: "";

		const vagas = document.getElementById("solicitar-vagas");
		const semVagas = item.vagas && item.vagas.limite && !item.vagas.disponiveis;
		vagas.hidden = !semVagas;
		vagas.querySelector("span").textContent = semVagas
			? "Todas as licenças estão em uso. O pedido fica na fila até uma vaga ser liberada."
			: "";

		const blocoSecao = document.getElementById("solicitar-secao-bloco");
		const seletor = document.getElementById("solicitar-secao");
		blocoSecao.hidden = !item.recorte;
		seletor.innerHTML = item.recorte
			? [
					'<option value="">Escolha a seção…</option>',
					...item.recorte.disponiveis.map(
						(secao) =>
							`<option value="${escapeHtml(secao)}">${escapeHtml(secao)}</option>`
					),
			  ].join("")
			: "";

		document.getElementById("solicitar-justificativa").value = "";
		abrirDialog("dialog-solicitar");
	}

	async function enviarSolicitacao(botao) {
		if (!acessoEmFoco) return;
		const seletor = document.getElementById("solicitar-secao");
		const secao = acessoEmFoco.recorte ? seletor.value : "";
		if (acessoEmFoco.recorte && !secao) {
			toast("error", "Escolha a seção.");
			seletor.focus();
			return;
		}
		await comBotaoOcupado(botao, async () => {
			try {
				await chamar(METODOS.solicitar, {
					acesso: acessoEmFoco.name,
					secao,
					justificativa: document.getElementById("solicitar-justificativa").value,
				});
				fecharDialog("dialog-solicitar");
				toast(
					"success",
					"Solicitação enviada. Você recebe um aviso quando ela for decidida."
				);
				await recarregar();
			} catch (erro) {
				toast("error", erro.message);
			}
		});
	}

	function pedirConfirmacao(texto, rotuloBotao, acao) {
		document.getElementById("confirmar-texto").textContent = texto;
		document.getElementById("btn-confirmar").textContent = rotuloBotao;
		aoConfirmar = acao;
		abrirDialog("dialog-confirmar");
	}

	function cancelarSolicitacao(nome) {
		const solicitacao = solicitacaoPorNome(nome);
		const titulo = solicitacao ? rotuloDoPedido(solicitacao) : "este acesso";
		pedirConfirmacao(`Cancelar o pedido de ${titulo}?`, "Cancelar pedido", async () => {
			await chamar(METODOS.cancelar, { solicitacao: nome });
			toast("success", "Pedido cancelado.");
			await recarregar();
		});
	}

	function abrirDecidir(nome) {
		const solicitacao = solicitacaoPorNome(nome);
		if (!solicitacao) return;
		solicitacaoEmFoco = solicitacao;
		const dialog = document.getElementById("dialog-decidir");
		dialog.querySelector("h2").textContent = `${
			solicitacao.solicitante_nome
		} → ${rotuloDoPedido(solicitacao)}`;
		document.getElementById("decidir-resumo").innerHTML = itemDeSolicitacao(
			solicitacao,
			"resumo"
		);
		document.getElementById("decidir-observacao").value = "";
		abrirDialog("dialog-decidir");
	}

	async function enviarDecisao(botao, decisao) {
		if (!solicitacaoEmFoco) return;
		const observacao = document.getElementById("decidir-observacao").value.trim();
		if (decisao === "recusar" && !observacao) {
			toast("error", "Escreva o motivo da recusa: ele é enviado a quem pediu.");
			document.getElementById("decidir-observacao").focus();
			return;
		}
		await comBotaoOcupado(botao, async () => {
			try {
				await chamar(METODOS.decidir, {
					solicitacao: solicitacaoEmFoco.name,
					decisao,
					observacao,
				});
				fecharDialog("dialog-decidir");
				toast(
					"success",
					decisao === "aprovar" ? "Etapa aprovada." : "Solicitação recusada."
				);
				await recarregar();
			} catch (erro) {
				toast("error", erro.message);
			}
		});
	}

	// ─── eventos ────────────────────────────────────────────────────────────

	raiz.addEventListener("click", (evento) => {
		const alvo = evento.target.closest("[data-acao]");
		if (!alvo) return;
		const acao = alvo.dataset.acao;
		if (acao === "solicitar") abrirSolicitar(alvo.dataset.acesso);
		if (acao === "cancelar") cancelarSolicitacao(alvo.dataset.solicitacao);
		if (acao === "decidir") abrirDecidir(alvo.dataset.solicitacao);
	});

	const busca = document.getElementById("acessos-busca");
	if (busca) {
		busca.addEventListener("input", () => {
			renderizarGrade("gris", "acessos-grade-gris");
			renderizarGrade("ferramentas", "acessos-grade-ferramentas");
		});
	}

	document.querySelectorAll("[data-fechar-dialog]").forEach((botao) => {
		botao.addEventListener("click", () => {
			const dialog = botao.closest("dialog");
			if (dialog) dialog.close();
		});
	});

	document.getElementById("btn-enviar-solicitacao").addEventListener("click", (evento) => {
		enviarSolicitacao(evento.currentTarget);
	});
	document.getElementById("btn-aprovar").addEventListener("click", (evento) => {
		enviarDecisao(evento.currentTarget, "aprovar");
	});
	document.getElementById("btn-recusar").addEventListener("click", (evento) => {
		enviarDecisao(evento.currentTarget, "recusar");
	});
	document.getElementById("btn-confirmar").addEventListener("click", async (evento) => {
		if (!aoConfirmar) return;
		const acao = aoConfirmar;
		await comBotaoOcupado(evento.currentTarget, async () => {
			try {
				await acao();
				fecharDialog("dialog-confirmar");
			} catch (erro) {
				toast("error", erro.message);
			}
		});
	});

	renderizarTudo();
})();
