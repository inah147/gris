// Gestão de acessos: solicitações, licenças, titulares, edição do catálogo e ações em massa.
//
// Os cards vêm prontos no HTML inicial e são recarregados (`resumo`) depois de qualquer
// ação que mude contagens; as solicitações e os titulares são buscados sob demanda.
(function () {
	const raiz = document.querySelector(".acessos-gestao");
	if (!raiz) return;

	const API = "gris.api.acessos";
	const METODOS = {
		resumo: `${API}.gestao.resumo`,
		solicitacoes: `${API}.gestao.listar_solicitacoes`,
		titulares: `${API}.gestao.listar_titulares`,
		elegiveis: `${API}.gestao.listar_usuarios_elegiveis`,
		conceder: `${API}.gestao.conceder_papel_em_massa`,
		revogar: `${API}.gestao.revogar_papel_em_massa`,
		revogarPapel: `${API}.gestao.revogar_papel_de_usuario`,
		revogarDrive: `${API}.gestao.revogar_concessao_drive`,
		salvarAcesso: `${API}.gestao.salvar_acesso`,
		registrarLicenca: `${API}.gestao.registrar_licenca`,
		marcarRevogacao: `${API}.gestao.marcar_revogacao`,
		desfazerRevogacao: `${API}.gestao.desfazer_revogacao`,
		confirmarRevogacao: `${API}.gestao.confirmar_revogacao`,
		decidir: `${API}.solicitacoes.decidir`,
		cancelar: `${API}.solicitacoes.cancelar`,
		confirmarConcessao: `${API}.provisionamento.confirmar_concessao`,
	};

	const STATUS_SOLICITACAO = {
		"Em aprovação": "andamento",
		"Aguardando concessão": "andamento",
		Concedida: "tem",
		Recusada: "alerta",
		Cancelada: "neutro",
	};

	let cards = lerJson(raiz.dataset.cards, []);
	let papelPadrao = raiz.dataset.papelPadrao || "";
	const solicitacoesPorAba = {
		gris: { status: "abertas", pagina: 1, lista: [], total: 0, porPagina: 50 },
		ferramentas: { status: "abertas", pagina: 1, lista: [], total: 0, porPagina: 50 },
	};
	let solicitacaoEmFoco = null;
	let titulares = { acesso: null, tipo: null, global: false, lista: [] };
	let edicao = { acesso: null, etapas: [] };
	const massa = { acesso: "", pessoas: [], selecionados: new Set() };
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
		// aspas, e o texto também vai para atributos (data-*, title, aria-label).
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

	function semAcento(texto) {
		return String(texto || "")
			.normalize("NFD")
			.replace(/[\u0300-\u036f]/g, "")
			.toLowerCase();
	}

	function toast(categoria, titulo, descricao) {
		document.dispatchEvent(
			new CustomEvent("basecoat:toast", {
				detail: {
					config: {
						category: categoria,
						title: titulo,
						description: descricao,
						duration: 6000,
					},
				},
			})
		);
	}

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

	function abrirDialog(id) {
		const dialog = document.getElementById(id);
		if (dialog && !dialog.open) dialog.showModal();
	}

	function fecharDialog(id) {
		const dialog = document.getElementById(id);
		if (dialog && dialog.open) dialog.close();
	}

	async function comBotaoOcupado(botao, acao) {
		if (botao) {
			botao.disabled = true;
			botao.setAttribute("aria-busy", "true");
		}
		try {
			await acao();
		} catch (erro) {
			toast("error", erro.message);
		} finally {
			if (botao) {
				botao.disabled = false;
				botao.removeAttribute("aria-busy");
			}
		}
	}

	function pedirConfirmacao(texto, rotuloBotao, acao) {
		document.getElementById("confirmar-texto").textContent = texto;
		document.getElementById("btn-confirmar").textContent = rotuloBotao;
		aoConfirmar = acao;
		abrirDialog("dialog-confirmar");
	}

	function selo(texto, classe) {
		return `<span class="badge acessos-selo acessos-selo--${classe}">${escapeHtml(
			texto
		)}</span>`;
	}

	function valorDoSelect(id) {
		const elemento = document.getElementById(id);
		if (!elemento) return "";
		const hidden = elemento.querySelector('input[type="hidden"]');
		return hidden ? hidden.value : "";
	}

	function definirSelect(id, valor) {
		// O select expõe `value` na raiz; escrever no hidden não atualiza o rótulo.
		const elemento = document.getElementById(id);
		if (elemento) elemento.value = valor || "";
	}

	/** O switch do design system põe o id no rótulo, não no checkbox. */
	function switchDe(id) {
		const rotulo = document.getElementById(id);
		return rotulo ? rotulo.querySelector('input[type="checkbox"]') : null;
	}

	function card(nome) {
		return cards.find((c) => c.name === nome) || null;
	}

	// ─── cards do catálogo ──────────────────────────────────────────────────

	function metricasDoCard(c) {
		const linhas = [];
		if (c.tipo === "Papel do Gris") {
			linhas.push(
				`${c.titulares} ${c.titulares === 1 ? "pessoa tem" : "pessoas têm"} este papel`
			);
		} else if (c.tipo === "Drive compartilhado") {
			linhas.push(
				c.global
					? `${c.titulares} associados com acesso automático`
					: `${c.titulares} ${
							c.titulares === 1 ? "concessão ativa" : "concessões ativas"
					  }`
			);
		} else if (c.vagas) {
			const v = c.vagas;
			if (v.limite) {
				linhas.push(`<strong>${v.usadas} de ${v.limite}</strong> licenças em uso`);
				linhas.push(`${v.disponiveis} livres · ${v.aguardando} aguardando concessão`);
			} else {
				linhas.push(`${v.usadas} licenças em uso (sem limite)`);
			}
		}
		if (c.abertos)
			linhas.push(`${c.abertos} ${c.abertos === 1 ? "pedido" : "pedidos"} em andamento`);
		return linhas;
	}

	function barraDeVagas(c) {
		if (!c.vagas || !c.vagas.limite) return "";
		const ocupado = Math.min(
			100,
			Math.round(((c.vagas.usadas + c.vagas.aguardando) / c.vagas.limite) * 100)
		);
		return `<div class="acessos-gestao-card__barra" role="progressbar" aria-label="Licenças ocupadas" aria-valuemin="0" aria-valuemax="100" aria-valuenow="${ocupado}"><span style="width: ${ocupado}%"></span></div>`;
	}

	function fluxoDoCard(c) {
		if (!c.etapas || !c.etapas.length) return `Aprovação: ${escapeHtml(papelPadrao)} (padrão)`;
		return `Aprovação: ${c.etapas.map((e) => escapeHtml(e.papel_aprovador)).join(" → ")}`;
	}

	function htmlDoCard(c) {
		const selos = [];
		if (!c.ativo) selos.push(selo("Fora do portal", "neutro"));
		if (c.ativo && !c.solicitavel) selos.push(selo("Informativo", "neutro"));
		return `
			<article class="card acessos-card acessos-gestao-card${
				c.ativo ? "" : " acessos-gestao-card--inativo"
			}">
				<header class="acessos-card__topo">
					<span class="acessos-card__icone">${icone(c.icone || "key-round", "md")}</span>
					<div class="acessos-card__titulos">
						<h3 class="acessos-card__titulo">${escapeHtml(c.titulo)}</h3>
						${c.papel ? `<span class="acessos-gestao-card__papel">${escapeHtml(c.papel)}</span>` : ""}
						${selos.join("")}
					</div>
				</header>
				<ul class="acessos-card__meta">${metricasDoCard(c)
					.map((l) => `<li>${l}</li>`)
					.join("")}</ul>
				${barraDeVagas(c)}
				<p class="acessos-gestao-card__fluxo">${fluxoDoCard(c)}</p>
				<footer class="acessos-card__acoes">
					<button type="button" class="btn-sm-outline" data-acao="titulares" data-acesso="${escapeHtml(
						c.name
					)}">${icone("users")}<span>Quem tem</span></button>
					<button type="button" class="btn-sm-ghost" data-acao="editar" data-acesso="${escapeHtml(
						c.name
					)}">${icone("pencil")}<span>Editar</span></button>
				</footer>
			</article>`;
	}

	function renderizarCards() {
		["gris", "ferramentas"].forEach((aba) => {
			const alvo = document.getElementById(`gestao-cards-${aba}`);
			if (!alvo) return;
			alvo.innerHTML = cards
				.filter((c) => c.aba === aba)
				.map(htmlDoCard)
				.join("");
		});
	}

	async function recarregarResumo() {
		const resultado = await chamar(METODOS.resumo, {}, { get: true });
		cards = resultado.cards || [];
		papelPadrao = resultado.papel_padrao || papelPadrao;
		renderizarCards();
	}

	// ─── solicitações ───────────────────────────────────────────────────────

	function linhaDeSolicitacao(s) {
		const etapa =
			s.status === "Em aprovação" && s.total_etapas
				? `${s.etapa_atual} de ${s.total_etapas}`
				: '<span class="text-muted-foreground">—</span>';
		return `
			<tr>
				<td><span class="acessos-gestao__pessoa">${escapeHtml(
					s.solicitante_nome
				)}</span><span class="acessos-gestao__email">${escapeHtml(
			s.email_concessao || s.solicitante
		)}</span></td>
				<td>${escapeHtml(s.acesso)}</td>
				<td>${selo(s.status, STATUS_SOLICITACAO[s.status] || "neutro")}</td>
				<td>${etapa}</td>
				<td class="acessos-gestao__nowrap">${escapeHtml(formatarData(s.criada_em))}</td>
				<td class="acessos-gestao__acoes"><button type="button" class="btn-sm-outline" data-acao="abrir-solicitacao" data-solicitacao="${escapeHtml(
					s.name
				)}">Abrir</button></td>
			</tr>`;
	}

	function renderizarSolicitacoes(aba) {
		const estado = solicitacoesPorAba[aba];
		const alvo = document.getElementById(`gestao-solicitacoes-${aba}`);
		const paginacao = document.getElementById(`gestao-paginacao-${aba}`);
		if (!alvo) return;

		if (!estado.lista.length) {
			const vazio = document.getElementById("gestao-vazio-solicitacoes");
			alvo.innerHTML = vazio ? vazio.innerHTML : "";
		} else {
			alvo.innerHTML = `
				<table class="table acessos-gestao__tabela">
					<thead><tr>
						<th scope="col">Quem pediu</th>
						<th scope="col">Acesso</th>
						<th scope="col">Status</th>
						<th scope="col">Etapa</th>
						<th scope="col">Pedido em</th>
						<th scope="col"><span class="sr-only">Ações</span></th>
					</tr></thead>
					<tbody>${estado.lista.map(linhaDeSolicitacao).join("")}</tbody>
				</table>`;
		}

		if (paginacao) {
			const paginas = Math.max(1, Math.ceil(estado.total / estado.porPagina));
			paginacao.innerHTML =
				paginas > 1
					? `<button type="button" class="btn-sm-outline" data-pagina-aba="${aba}" data-pagina="${
							estado.pagina - 1
					  }" ${estado.pagina <= 1 ? "disabled" : ""}>Anterior</button>
					   <span class="text-muted-foreground text-sm">Página ${estado.pagina} de ${paginas}</span>
					   <button type="button" class="btn-sm-outline" data-pagina-aba="${aba}" data-pagina="${
							estado.pagina + 1
					  }" ${estado.pagina >= paginas ? "disabled" : ""}>Próxima</button>`
					: "";
		}
	}

	async function carregarSolicitacoes(aba) {
		const estado = solicitacoesPorAba[aba];
		try {
			const resultado = await chamar(
				METODOS.solicitacoes,
				{ status: estado.status, aba, pagina: estado.pagina },
				{ get: true }
			);
			estado.lista = resultado.solicitacoes || [];
			estado.total = resultado.total || 0;
			estado.porPagina = resultado.por_pagina || 50;
			renderizarSolicitacoes(aba);
		} catch (erro) {
			toast("error", erro.message);
		}
	}

	function solicitacaoPorNome(nome) {
		for (const aba of Object.keys(solicitacoesPorAba)) {
			const achada = solicitacoesPorAba[aba].lista.find((s) => s.name === nome);
			if (achada) return achada;
		}
		return null;
	}

	function etapasDaSolicitacao(s) {
		if (!s.etapas || !s.etapas.length) return "";
		const itens = s.etapas.map((etapa) => {
			const atual =
				s.status === "Em aprovação" &&
				etapa.ordem === s.etapa_atual &&
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
			)}</strong> · ${escapeHtml(etapa.papel_aprovador)}`;
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

	function abrirSolicitacao(nome) {
		const s = solicitacaoPorNome(nome);
		if (!s) return;
		solicitacaoEmFoco = s;

		const dialog = document.getElementById("dialog-solicitacao");
		dialog.querySelector("h2").textContent = `${s.solicitante_nome} → ${s.acesso}`;

		const partes = [
			`<div class="acessos-solicitacao__topo"><span class="acessos-solicitacao__data">${escapeHtml(
				s.name
			)} · pedido em ${escapeHtml(formatarData(s.criada_em))}</span>${selo(
				s.status,
				STATUS_SOLICITACAO[s.status] || "neutro"
			)}</div>`,
		];
		if (s.email_concessao)
			partes.push(
				`<p class="acessos-solicitacao__texto"><span class="text-muted-foreground">Conta:</span> ${escapeHtml(
					s.email_concessao
				)}</p>`
			);
		if (s.justificativa)
			partes.push(
				`<p class="acessos-solicitacao__texto"><span class="text-muted-foreground">Justificativa:</span> ${escapeHtml(
					s.justificativa
				)}</p>`
			);
		if (s.motivo && ["Recusada", "Cancelada"].includes(s.status))
			partes.push(
				`<p class="acessos-solicitacao__texto"><span class="text-muted-foreground">Motivo:</span> ${escapeHtml(
					s.motivo
				)}</p>`
			);
		partes.push(etapasDaSolicitacao(s));
		document.getElementById("solicitacao-detalhe").innerHTML = partes.join("");

		const aguardandoFerramenta =
			s.status === "Aguardando concessão" && s.tipo === "Ferramenta externa";
		const instrucoes = document.getElementById("solicitacao-instrucoes");
		const item = card(s.acesso);
		const textoInstrucoes = aguardandoFerramenta && item ? item.instrucoes_concessao : "";
		instrucoes.hidden = !textoInstrucoes;
		instrucoes.querySelector("span").textContent = textoInstrucoes || "";

		document.getElementById("btn-gestao-aprovar").hidden = !s.pode_decidir;
		document.getElementById("btn-gestao-recusar").hidden = !s.pode_decidir;
		document.getElementById("btn-gestao-confirmar-concessao").hidden = !aguardandoFerramenta;
		document.getElementById("btn-gestao-cancelar").hidden = !s.pode_cancelar;
		document.getElementById("solicitacao-observacao-campo").hidden = !(
			s.pode_decidir ||
			aguardandoFerramenta ||
			s.pode_cancelar
		);
		document.getElementById("solicitacao-observacao").value = "";
		abrirDialog("dialog-solicitacao");
	}

	async function depoisDeMudarSolicitacao(mensagem) {
		fecharDialog("dialog-solicitacao");
		toast("success", mensagem);
		await Promise.all([
			carregarSolicitacoes("gris"),
			carregarSolicitacoes("ferramentas"),
			recarregarResumo(),
		]);
	}

	async function decidir(botao, decisao) {
		if (!solicitacaoEmFoco) return;
		const observacao = document.getElementById("solicitacao-observacao").value.trim();
		if (decisao === "recusar" && !observacao) {
			toast("error", "Escreva o motivo da recusa: ele é enviado a quem pediu.");
			document.getElementById("solicitacao-observacao").focus();
			return;
		}
		await comBotaoOcupado(botao, async () => {
			await chamar(METODOS.decidir, {
				solicitacao: solicitacaoEmFoco.name,
				decisao,
				observacao,
			});
			await depoisDeMudarSolicitacao(
				decisao === "aprovar" ? "Etapa aprovada." : "Solicitação recusada."
			);
		});
	}

	// ─── titulares ──────────────────────────────────────────────────────────

	function acoesDoTitular(t) {
		const dados = `data-acesso="${escapeHtml(titulares.acesso)}"`;
		if (titulares.tipo === "Papel do Gris") {
			return t.via_perfil
				? '<span class="text-muted-foreground text-sm">Muda com o perfil</span>'
				: `<button type="button" class="btn-sm-outline" data-acao="revogar-papel" ${dados} data-usuario="${escapeHtml(
						t.usuario
				  )}" data-nome="${escapeHtml(t.nome)}">Revogar</button>`;
		}
		if (titulares.tipo === "Drive compartilhado") {
			return t.concessao
				? `<button type="button" class="btn-sm-outline" data-acao="revogar-drive" data-concessao="${escapeHtml(
						t.concessao
				  )}" data-nome="${escapeHtml(t.nome)}">Revogar</button>`
				: '<span class="text-muted-foreground text-sm">Automático</span>';
		}
		const licenca = `data-licenca="${escapeHtml(t.licenca)}" data-nome="${escapeHtml(
			t.nome
		)}"`;
		if (t.status === "Revogação pendente") {
			return `<button type="button" class="btn-sm-primary" data-acao="confirmar-revogacao" ${licenca}>Conta removida</button>
				<button type="button" class="btn-sm-ghost" data-acao="desfazer-revogacao" ${licenca}>Manter</button>`;
		}
		return `<button type="button" class="btn-sm-outline" data-acao="marcar-revogacao" ${licenca}>Revogar</button>`;
	}

	function detalheDoTitular(t) {
		if (titulares.tipo === "Ferramenta externa") {
			const classe = t.status === "Ativa" ? "tem" : "alerta";
			const extra =
				t.status === "Revogação pendente" && t.origem
					? ` (${escapeHtml(t.origem.toLowerCase())})`
					: "";
			return `${selo(t.status, classe)}${extra}`;
		}
		if (titulares.tipo === "Drive compartilhado") {
			const partes = [escapeHtml(t.permissao)];
			if (t.expira_em) partes.push(`até ${escapeHtml(formatarData(t.expira_em))}`);
			if (t.em_provisionamento) partes.push("liberando");
			return partes.join(" · ");
		}
		return escapeHtml(t.origem);
	}

	function renderizarTitulares() {
		const alvo = document.getElementById("titulares-lista");
		const termo = semAcento(document.getElementById("titulares-busca").value);
		const lista = titulares.lista.filter(
			(t) => !termo || semAcento(`${t.nome} ${t.email}`).includes(termo)
		);
		if (!lista.length) {
			alvo.innerHTML = `<p class="text-muted-foreground text-sm m-0">${
				titulares.lista.length
					? "Ninguém encontrado com essa busca."
					: "Ninguém tem este acesso."
			}</p>`;
			return;
		}
		const aviso = titulares.global
			? '<p class="text-muted-foreground text-sm">Drive para todos: a inclusão e a revogação são automáticas, feitas pelo mecanismo do Google Workspace.</p>'
			: "";
		alvo.innerHTML = `${aviso}
			<table class="table acessos-gestao__tabela">
				<thead><tr>
					<th scope="col">Nome</th>
					<th scope="col">Detalhe</th>
					<th scope="col"><span class="sr-only">Ações</span></th>
				</tr></thead>
				<tbody>${lista
					.map(
						(t) => `<tr>
							<td><span class="acessos-gestao__pessoa">${escapeHtml(
								t.nome
							)}</span><span class="acessos-gestao__email">${escapeHtml(
							t.email
						)}</span></td>
							<td>${detalheDoTitular(t)}</td>
							<td class="acessos-gestao__acoes">${acoesDoTitular(t)}</td>
						</tr>`
					)
					.join("")}</tbody>
			</table>`;
	}

	async function carregarTitulares(nome) {
		const c = card(nome);
		const resultado = await chamar(METODOS.titulares, { acesso: nome }, { get: true });
		titulares = {
			acesso: nome,
			tipo: resultado.tipo,
			global: !!resultado.global,
			lista: resultado.titulares || [],
		};
		const dialog = document.getElementById("dialog-titulares");
		dialog.querySelector("h2").textContent = `Quem tem: ${c ? c.titulo : nome} (${
			titulares.lista.length
		})`;
		renderizarTitulares();
	}

	async function abrirTitulares(nome) {
		document.getElementById("titulares-busca").value = "";
		document.getElementById("titulares-lista").innerHTML =
			'<p class="text-muted-foreground text-sm m-0">Carregando…</p>';
		abrirDialog("dialog-titulares");
		try {
			await carregarTitulares(nome);
		} catch (erro) {
			toast("error", erro.message);
		}
	}

	function acaoNoTitular(alvo) {
		const acao = alvo.dataset.acao;
		const nome = alvo.dataset.nome || "esta pessoa";
		const recarregar = async (mensagem) => {
			toast("success", mensagem);
			await Promise.all([carregarTitulares(titulares.acesso), recarregarResumo()]);
		};

		if (acao === "revogar-papel") {
			pedirConfirmacao(`Revogar o papel de ${nome}?`, "Revogar", async () => {
				await chamar(METODOS.revogarPapel, {
					acesso: alvo.dataset.acesso,
					usuario: alvo.dataset.usuario,
				});
				await recarregar("Papel revogado.");
			});
		} else if (acao === "revogar-drive") {
			pedirConfirmacao(
				`Revogar o acesso de ${nome} a este drive? A remoção no Google acontece em instantes.`,
				"Revogar",
				async () => {
					await chamar(METODOS.revogarDrive, { concessao: alvo.dataset.concessao });
					await recarregar("Acesso ao drive revogado.");
				}
			);
		} else if (acao === "marcar-revogacao") {
			pedirConfirmacao(
				`Marcar a licença de ${nome} para revogação? A vaga só é liberada quando você confirmar que a conta foi removida da ferramenta.`,
				"Marcar",
				async () => {
					await chamar(METODOS.marcarRevogacao, { licenca: alvo.dataset.licenca });
					await recarregar("Licença marcada para revogação.");
				}
			);
		} else if (acao === "confirmar-revogacao") {
			pedirConfirmacao(
				`A conta de ${nome} já foi removida da ferramenta?`,
				"Sim, liberar a vaga",
				async () => {
					await chamar(METODOS.confirmarRevogacao, { licenca: alvo.dataset.licenca });
					await recarregar("Licença revogada e vaga liberada.");
				}
			);
		} else if (acao === "desfazer-revogacao") {
			comBotaoOcupado(alvo, async () => {
				await chamar(METODOS.desfazerRevogacao, { licenca: alvo.dataset.licenca });
				await recarregar("A licença continua ativa.");
			});
		}
	}

	// ─── edição do catálogo ─────────────────────────────────────────────────

	function renderizarEtapasDaEdicao() {
		const alvo = document.getElementById("editar-etapas");
		if (!edicao.etapas.length) {
			alvo.innerHTML = `<li class="text-muted-foreground text-sm">Sem etapas: ao salvar, volta para o padrão (${escapeHtml(
				papelPadrao
			)}).</li>`;
			return;
		}
		alvo.innerHTML = edicao.etapas
			.map(
				(etapa, indice) => `<li class="acessos-editar__etapa">
					<span class="acessos-editar__ordem">${indice + 1}</span>
					<span class="acessos-editar__texto"><strong>${escapeHtml(etapa.papel_aprovador)}</strong>${
					etapa.descricao ? ` · ${escapeHtml(etapa.descricao)}` : ""
				}</span>
					<button type="button" class="btn-sm-ghost" data-remover-etapa="${indice}" aria-label="Remover etapa ${
					indice + 1
				}">${icone("trash-2")}</button>
				</li>`
			)
			.join("");
	}

	function abrirEdicao(nome) {
		const c = card(nome);
		if (!c) return;
		edicao = { acesso: nome, etapas: (c.etapas || []).map((e) => ({ ...e })) };

		const dialog = document.getElementById("dialog-editar");
		dialog.querySelector("h2").textContent = `Editar: ${c.titulo}`;
		document.getElementById("editar-descricao").value = c.descricao || "";
		document.getElementById("editar-o-que-muda").value = c.o_que_muda || "";
		document.getElementById("editar-limite").value = c.limite_licencas || 0;
		document.getElementById("editar-link").value = c.link_externo || "";
		document.getElementById("editar-instrucoes").value = c.instrucoes_concessao || "";
		document.getElementById("editar-ordem").value = c.ordem || 0;
		definirSelect("editar-permissao-drive", c.permissao_drive || "reader");
		const solicitavel = switchDe("editar-solicitavel");
		const ativo = switchDe("editar-ativo");
		if (solicitavel) solicitavel.checked = !!c.solicitavel;
		if (ativo) ativo.checked = !!c.ativo;

		document.getElementById("editar-bloco-ferramenta").hidden =
			c.tipo !== "Ferramenta externa";
		document.getElementById("editar-bloco-drive").hidden = c.tipo !== "Drive compartilhado";
		definirSelect("editar-nova-etapa-papel", "");
		document.getElementById("editar-nova-etapa-descricao").value = "";
		renderizarEtapasDaEdicao();
		abrirDialog("dialog-editar");
	}

	async function salvarEdicao(botao) {
		const c = card(edicao.acesso);
		if (!c) return;
		const dados = {
			descricao: document.getElementById("editar-descricao").value,
			o_que_muda: document.getElementById("editar-o-que-muda").value,
			ordem: document.getElementById("editar-ordem").value,
			solicitavel: switchDe("editar-solicitavel").checked ? 1 : 0,
			ativo: switchDe("editar-ativo").checked ? 1 : 0,
			etapas: edicao.etapas,
		};
		if (c.tipo === "Ferramenta externa") {
			dados.limite_licencas = document.getElementById("editar-limite").value;
			dados.link_externo = document.getElementById("editar-link").value;
			dados.instrucoes_concessao = document.getElementById("editar-instrucoes").value;
		}
		if (c.tipo === "Drive compartilhado") {
			dados.permissao_drive = valorDoSelect("editar-permissao-drive");
		}
		await comBotaoOcupado(botao, async () => {
			await chamar(METODOS.salvarAcesso, {
				acesso: edicao.acesso,
				dados: JSON.stringify(dados),
			});
			fecharDialog("dialog-editar");
			toast("success", "Acesso atualizado.");
			await recarregarResumo();
		});
	}

	// ─── ação em massa ──────────────────────────────────────────────────────

	function alvoDaMassa() {
		const marcado = document.querySelector('input[name="massa-alvo"]:checked');
		return marcado ? marcado.value : "selecionados";
	}

	function pessoasVisiveis() {
		const termo = semAcento(document.getElementById("massa-busca").value);
		return massa.pessoas.filter(
			(p) => !termo || semAcento(`${p.nome} ${p.usuario}`).includes(termo)
		);
	}

	function renderizarPessoas() {
		const alvo = document.getElementById("massa-lista");
		const contagem = document.getElementById("massa-contagem");
		if (!massa.acesso) {
			alvo.innerHTML =
				'<p class="text-muted-foreground text-sm m-0">Escolha um papel para ver as pessoas.</p>';
			contagem.textContent = "";
			return;
		}
		const visiveis = pessoasVisiveis();
		contagem.textContent = `${massa.selecionados.size} selecionada(s) de ${massa.pessoas.length}`;
		if (!visiveis.length) {
			alvo.innerHTML =
				'<p class="text-muted-foreground text-sm m-0">Ninguém encontrado com essa busca.</p>';
			return;
		}
		const todosMarcados = visiveis.every((p) => massa.selecionados.has(p.usuario));
		alvo.innerHTML = `
			<label class="acessos-massa__pessoa acessos-massa__pessoa--todos">
				<input type="checkbox" class="input" data-massa-todos ${todosMarcados ? "checked" : ""}>
				<span>Selecionar as ${visiveis.length} pessoas da lista</span>
			</label>
			${visiveis
				.map((p) => {
					const marca = p.via_perfil
						? selo("Pelo perfil", "neutro")
						: p.tem
						? selo("Tem", "tem")
						: "";
					return `<label class="acessos-massa__pessoa">
						<input type="checkbox" class="input" data-massa-usuario="${escapeHtml(p.usuario)}" ${
						massa.selecionados.has(p.usuario) ? "checked" : ""
					}>
						<span class="acessos-massa__nome"><span>${escapeHtml(
							p.nome
						)}</span><span class="acessos-gestao__email">${escapeHtml(p.usuario)}${
						p.categoria ? ` · ${escapeHtml(p.categoria)}` : ""
					}</span></span>
						${marca}
					</label>`;
				})
				.join("")}`;
	}

	async function carregarPessoas() {
		massa.acesso = valorDoSelect("massa-acesso");
		massa.selecionados = new Set();
		massa.pessoas = [];
		if (!massa.acesso) {
			renderizarPessoas();
			return;
		}
		document.getElementById("massa-lista").innerHTML =
			'<p class="text-muted-foreground text-sm m-0">Carregando…</p>';
		try {
			const resultado = await chamar(
				METODOS.elegiveis,
				{ acesso: massa.acesso },
				{ get: true }
			);
			massa.pessoas = resultado.usuarios || [];
		} catch (erro) {
			toast("error", erro.message);
		}
		renderizarPessoas();
	}

	function executarMassa(acao) {
		if (!massa.acesso) {
			toast("error", "Escolha o papel.");
			return;
		}
		const todos = alvoDaMassa() === "todos";
		const quantidade = todos ? massa.pessoas.length : massa.selecionados.size;
		if (!quantidade) {
			toast("error", "Selecione ao menos uma pessoa.");
			return;
		}
		const c = card(massa.acesso);
		const verbo = acao === "conceder" ? "Conceder" : "Revogar";
		const destino = todos
			? `todos os ${quantidade} associados ativos`
			: `${quantidade} pessoa(s)`;
		pedirConfirmacao(
			`${verbo} "${c ? c.titulo : massa.acesso}" para ${destino}?`,
			verbo,
			async () => {
				const resultado = await chamar(
					acao === "conceder" ? METODOS.conceder : METODOS.revogar,
					{
						acesso: massa.acesso,
						usuarios: JSON.stringify(Array.from(massa.selecionados)),
						todos: todos ? 1 : 0,
					}
				);
				const ignorados = (resultado.ignorados_via_perfil || []).length;
				const extra = ignorados
					? `${ignorados} pessoa(s) ficaram de fora: o papel vem do perfil delas.`
					: "";
				if (resultado.enfileirado) {
					toast(
						"success",
						`Alteração de ${resultado.total} pessoa(s) enviada para processamento.`,
						extra
					);
				} else {
					toast("success", `${resultado.alterados} pessoa(s) alterada(s).`, extra);
				}
				await Promise.all([carregarPessoas(), recarregarResumo()]);
			}
		);
	}

	// ─── eventos ────────────────────────────────────────────────────────────

	document.addEventListener("click", (evento) => {
		const fechar = evento.target.closest("[data-fechar-dialog]");
		if (fechar) {
			const dialog = fechar.closest("dialog");
			if (dialog) dialog.close();
			return;
		}

		const pagina = evento.target.closest("[data-pagina-aba]");
		if (pagina && !pagina.disabled) {
			const aba = pagina.dataset.paginaAba;
			solicitacoesPorAba[aba].pagina = Number(pagina.dataset.pagina) || 1;
			carregarSolicitacoes(aba);
			return;
		}

		const remover = evento.target.closest("[data-remover-etapa]");
		if (remover) {
			edicao.etapas.splice(Number(remover.dataset.removerEtapa), 1);
			renderizarEtapasDaEdicao();
			return;
		}

		const alvo = evento.target.closest("[data-acao]");
		if (!alvo) return;
		const acao = alvo.dataset.acao;
		if (acao === "titulares") abrirTitulares(alvo.dataset.acesso);
		else if (acao === "editar") abrirEdicao(alvo.dataset.acesso);
		else if (acao === "abrir-solicitacao") abrirSolicitacao(alvo.dataset.solicitacao);
		else acaoNoTitular(alvo);
	});

	document.querySelectorAll("[data-filtro-aba]").forEach((filtro) => {
		filtro.addEventListener("change", () => {
			const aba = filtro.dataset.filtroAba;
			solicitacoesPorAba[aba].status = valorDoSelect(filtro.id) || "abertas";
			solicitacoesPorAba[aba].pagina = 1;
			carregarSolicitacoes(aba);
		});
	});

	document
		.getElementById("btn-gestao-aprovar")
		.addEventListener("click", (e) => decidir(e.currentTarget, "aprovar"));
	document
		.getElementById("btn-gestao-recusar")
		.addEventListener("click", (e) => decidir(e.currentTarget, "recusar"));
	document.getElementById("btn-gestao-cancelar").addEventListener("click", (e) => {
		const botao = e.currentTarget;
		comBotaoOcupado(botao, async () => {
			await chamar(METODOS.cancelar, {
				solicitacao: solicitacaoEmFoco.name,
				motivo: document.getElementById("solicitacao-observacao").value,
			});
			await depoisDeMudarSolicitacao("Pedido cancelado.");
		});
	});
	document.getElementById("btn-gestao-confirmar-concessao").addEventListener("click", (e) => {
		const botao = e.currentTarget;
		comBotaoOcupado(botao, async () => {
			await chamar(METODOS.confirmarConcessao, {
				solicitacao: solicitacaoEmFoco.name,
				observacao: document.getElementById("solicitacao-observacao").value,
			});
			await depoisDeMudarSolicitacao("Concessão confirmada: a pessoa foi avisada.");
		});
	});

	document.getElementById("titulares-busca").addEventListener("input", renderizarTitulares);

	document.getElementById("btn-adicionar-etapa").addEventListener("click", () => {
		const papel = valorDoSelect("editar-nova-etapa-papel");
		if (!papel) {
			toast("error", "Escolha o papel que aprova a etapa.");
			return;
		}
		const descricao = document.getElementById("editar-nova-etapa-descricao").value.trim();
		edicao.etapas.push({ papel_aprovador: papel, descricao });
		definirSelect("editar-nova-etapa-papel", "");
		document.getElementById("editar-nova-etapa-descricao").value = "";
		renderizarEtapasDaEdicao();
	});
	document
		.getElementById("btn-salvar-acesso")
		.addEventListener("click", (e) => salvarEdicao(e.currentTarget));

	const massaAcesso = document.getElementById("massa-acesso");
	if (massaAcesso) massaAcesso.addEventListener("change", carregarPessoas);
	document.getElementById("massa-busca").addEventListener("input", renderizarPessoas);
	document.querySelectorAll('input[name="massa-alvo"]').forEach((radio) => {
		radio.addEventListener("change", () => {
			document.getElementById("massa-pessoas").hidden = alvoDaMassa() === "todos";
		});
	});
	document.getElementById("massa-lista").addEventListener("change", (evento) => {
		const caixa = evento.target;
		if (caixa.matches("[data-massa-todos]")) {
			pessoasVisiveis().forEach((p) =>
				caixa.checked
					? massa.selecionados.add(p.usuario)
					: massa.selecionados.delete(p.usuario)
			);
			renderizarPessoas();
		} else if (caixa.matches("[data-massa-usuario]")) {
			const usuario = caixa.dataset.massaUsuario;
			caixa.checked ? massa.selecionados.add(usuario) : massa.selecionados.delete(usuario);
			renderizarPessoas();
		}
	});
	document
		.getElementById("btn-massa-conceder")
		.addEventListener("click", () => executarMassa("conceder"));
	document
		.getElementById("btn-massa-revogar")
		.addEventListener("click", () => executarMassa("revogar"));

	const registrar = document.getElementById("btn-registrar-licenca");
	if (registrar) {
		registrar.addEventListener("click", () => {
			definirSelect("licenca-acesso", "");
			definirSelect("licenca-associado", "");
			document.getElementById("licenca-observacao").value = "";
			abrirDialog("dialog-licenca");
		});
		document.getElementById("btn-salvar-licenca").addEventListener("click", (e) => {
			const acesso = valorDoSelect("licenca-acesso");
			const associado = valorDoSelect("licenca-associado");
			if (!acesso || !associado) {
				toast("error", "Escolha a ferramenta e o associado.");
				return;
			}
			comBotaoOcupado(e.currentTarget, async () => {
				await chamar(METODOS.registrarLicenca, {
					acesso,
					associado,
					observacao: document.getElementById("licenca-observacao").value,
				});
				fecharDialog("dialog-licenca");
				toast("success", "Licença registrada.");
				await recarregarResumo();
			});
		});
	}

	document.getElementById("btn-confirmar").addEventListener("click", async (evento) => {
		if (!aoConfirmar) return;
		const acao = aoConfirmar;
		await comBotaoOcupado(evento.currentTarget, async () => {
			await acao();
			fecharDialog("dialog-confirmar");
		});
	});

	renderizarCards();
	carregarSolicitacoes("gris");
	carregarSolicitacoes("ferramentas");
})();
