// Detalhe da contribuição mensal de um associado — ações de gestão da tela cheia.
// O mês a mês e as transações vêm renderizados do servidor; aqui ficam só as
// ações: alterar o valor, editar os dados de cobrança e cobrar pela InfinitePay.
(function () {
	"use strict";

	const associado = window.contribAssociado || "";
	const meses = window.contribMeses;

	// Espelho do que está na tela: o formulário inline volta a mostrar o valor
	// corrente depois de um cancelamento ou de um salvamento bem-sucedido.
	let esperadoMensal = window.contribEsperadoMensal || 0;
	let emailCobranca = window.contribEmailCobranca || "";
	let telefoneCobranca = window.contribTelefoneCobranca || "";

	// ─────────────────────────── utilitários ───────────────────────────

	function parseNumber(valor) {
		const numero = typeof valor === "number" ? valor : parseFloat(valor || 0);
		return Number.isFinite(numero) ? numero : 0;
	}

	function formatarMoeda(valor) {
		return parseNumber(valor).toLocaleString("pt-BR", {
			minimumFractionDigits: 2,
			maximumFractionDigits: 2,
		});
	}

	// Escapa também aspas: o resultado é interpolado em atributos, não só em texto.
	function escapeHtml(texto) {
		return String(texto == null ? "" : texto)
			.replace(/&/g, "&amp;")
			.replace(/</g, "&lt;")
			.replace(/>/g, "&gt;")
			.replace(/"/g, "&quot;")
			.replace(/'/g, "&#39;");
	}

	function showToast(mensagem, indicador) {
		const categorias = { green: "success", red: "error", orange: "warning", blue: "info" };
		document.dispatchEvent(
			new CustomEvent("basecoat:toast", {
				detail: {
					config: {
						category: categorias[indicador] || "info",
						title: mensagem,
						duration: 3000,
					},
				},
			})
		);
	}

	function semPermissao() {
		if (window.canManageContrib) return false;
		showToast("Sem permissão para esta ação.", "red");
		return true;
	}

	function chamarApi(metodo, args, mensagemSucesso) {
		frappe
			.call({ method: metodo, args: args, freeze: true })
			.then((resposta) => {
				const dados = (resposta && resposta.message) || {};
				if (!dados.ok) {
					showToast("Não foi possível concluir a ação.", "red");
					return;
				}
				showToast(mensagemSucesso, "green");
				// A apuração é calculada no servidor: recarregar mantém tela e números coerentes.
				window.setTimeout(() => window.location.reload(), 600);
			})
			.catch(() => showToast("Erro ao executar a ação.", "red"));
	}

	// ─────────────────────────── valor esperado ───────────────────────────

	function alterarValor() {
		if (semPermissao()) return;
		const container = document.getElementById("valorContainer");
		const acoes = document.getElementById("acoesValor");
		if (!container || !acoes || container.querySelector("input")) return;

		container.classList.remove("hidden");
		container.innerHTML = `
			<div class="field">
				<label class="label" for="inputNovoValor">Novo valor esperado por mês (R$)</label>
				<input type="number" min="0" step="0.01" id="inputNovoValor" class="input contrib-input-valor"
					value="${parseNumber(esperadoMensal)}" />
			</div>
		`;
		acoes.innerHTML = `
			<button type="button" class="btn-sm-primary" data-acao="salvar-valor">Salvar</button>
			<button type="button" class="btn-sm-outline" data-acao="cancelar-valor">Cancelar</button>
		`;
	}

	function cancelarEdicaoValor() {
		const container = document.getElementById("valorContainer");
		const acoes = document.getElementById("acoesValor");
		if (container) {
			container.innerHTML = "";
			container.classList.add("hidden");
		}
		if (acoes && window.canManageContrib) {
			acoes.innerHTML =
				'<button type="button" id="btnAlterarValor" class="btn-sm-outline" data-acao="alterar-valor">Alterar valor</button>';
		}
	}

	function salvarNovoValor() {
		if (semPermissao()) return;
		const input = document.getElementById("inputNovoValor");
		if (!input) return;
		const novoValor = parseFloat(input.value);
		if (!Number.isFinite(novoValor) || novoValor < 0) {
			showToast("Informe um valor válido.", "orange");
			return;
		}
		frappe
			.call({
				method: "gris.api.financeiro.monthly_payments.update_contribution_value",
				args: { associate_id: associado, new_value: novoValor },
				freeze: true,
			})
			.then((resposta) => {
				const dados = (resposta && resposta.message) || {};
				if (!dados.ok) {
					showToast("Não foi possível salvar o valor.", "red");
					return;
				}
				esperadoMensal = novoValor;
				showToast("Valor atualizado", "green");
				window.setTimeout(() => window.location.reload(), 600);
			})
			.catch(() => showToast("Erro ao salvar valor.", "red"));
	}

	// ─────────────────────────── cadastro da cobrança ───────────────────────────

	function cadastroRealizado() {
		if (semPermissao()) return;
		chamarApi(
			"gris.api.financeiro.monthly_payments.activate_billing_status",
			{ associate_id: associado },
			"Cobrança ativada"
		);
	}

	function cadastroCancelado() {
		if (semPermissao()) return;
		chamarApi(
			"gris.api.financeiro.monthly_payments.deactivate_billing_status",
			{ associate_id: associado },
			"Cobrança inativada"
		);
	}

	function editarCobranca() {
		if (semPermissao()) return;
		const container = document.getElementById("cobrancaContainer");
		const acoes = document.getElementById("acoesCobranca");
		if (!container || !acoes || container.querySelector("input")) return;

		const alvo = container.querySelector(".flex-1");
		if (alvo) {
			alvo.innerHTML = `
				<div class="field">
					<label class="label" for="inputEmailCobranca">E-mail de cobrança</label>
					<input type="email" id="inputEmailCobranca" class="input" value="${escapeHtml(
						emailCobranca
					)}" placeholder="email@exemplo.com" />
				</div>
				<div class="field">
					<label class="label" for="inputFoneCobranca">Telefone de cobrança</label>
					<input type="text" id="inputFoneCobranca" class="input" value="${escapeHtml(
						telefoneCobranca
					)}" placeholder="(xx) xxxxx-xxxx" />
				</div>
			`;
		}
		acoes.innerHTML = `
			<button type="button" class="btn-sm-primary" data-acao="salvar-cobranca">Salvar</button>
			<button type="button" class="btn-sm-outline" data-acao="cancelar-cobranca">Cancelar</button>
		`;
	}

	function restaurarCobranca() {
		const container = document.getElementById("cobrancaContainer");
		const acoes = document.getElementById("acoesCobranca");
		if (container) {
			const alvo = container.querySelector(".flex-1");
			if (alvo) {
				alvo.innerHTML = `
					<div class="text-sm"><strong>E-mail de cobrança:</strong> <span id="emailCobranca">${escapeHtml(
						emailCobranca || "—"
					)}</span></div>
					<div class="text-sm"><strong>Telefone de cobrança:</strong> <span id="foneCobranca">${escapeHtml(
						telefoneCobranca || "—"
					)}</span></div>
				`;
			}
		}
		if (acoes) {
			acoes.innerHTML =
				'<button type="button" id="btnEditarCobranca" class="btn-sm-outline" data-acao="editar-cobranca">Editar cobrança</button>';
		}
	}

	function salvarDadosCobranca() {
		if (semPermissao()) return;
		const email = document.getElementById("inputEmailCobranca")?.value.trim() || "";
		const telefone = document.getElementById("inputFoneCobranca")?.value.trim() || "";

		frappe
			.call({
				method: "gris.api.financeiro.monthly_payments.update_billing_contacts",
				args: { associate_id: associado, email: email, phone: telefone },
				freeze: true,
			})
			.then((resposta) => {
				const dados = (resposta && resposta.message) || {};
				if (!dados.ok) {
					showToast("Não foi possível salvar os dados de cobrança.", "red");
					return;
				}
				emailCobranca = dados.email;
				telefoneCobranca = dados.phone;
				restaurarCobranca();
				showToast("Dados de cobrança atualizados", "green");
			})
			.catch(() => showToast("Erro ao salvar dados de cobrança.", "red"));
	}

	// ─────────────────────────── mês a mês (status e transação vinculada) ───────────────────────────

	const STATUS_OPCOES = ["Em Aberto", "Atrasado", "Pago"];

	// A escolha manual (opção "Outro…") continua existindo para o caso raro de a
	// transação certa cair fora da janela buscada pelo servidor (5 meses ao redor
	// do mês de referência). No dia a dia, o gestor escolhe da lista.
	const VALOR_TRANSACAO_MANUAL = "__manual__";

	function formatarDataCurta(iso) {
		const partes = String(iso || "").split("-");
		return partes.length === 3 ? `${partes[2]}/${partes[1]}` : iso || "";
	}

	function montarOpcaoTransacao(transacao, transacaoSelecionada) {
		const rotulo =
			`${formatarDataCurta(transacao.data)} · R$ ${formatarMoeda(transacao.valor)}` +
			(transacao.descricao ? ` · ${transacao.descricao}` : "") +
			(transacao.vinculada ? "" : " · não vinculada");
		const selecionada = transacao.name === transacaoSelecionada ? "selected" : "";
		return `<option value="${escapeHtml(transacao.name)}" ${selecionada}>${escapeHtml(
			rotulo
		)}</option>`;
	}

	function alternarInputManual(select, manual) {
		if (!manual) return;
		manual.classList.toggle("hidden", select.value !== VALOR_TRANSACAO_MANUAL);
	}

	function carregarTransacoesCandidatas(editor, ym, transacaoAtual, valorAtual) {
		const select = editor.querySelector(".contrib-edit-transacao");
		const manual = editor.querySelector(".contrib-edit-transacao-manual");
		if (!select) return;

		select.addEventListener("change", () => alternarInputManual(select, manual));

		frappe
			.call({
				method: "gris.api.financeiro.contribuicoes.buscar_transacoes_para_vincular",
				args: { associado: associado, mes_de_referencia: `${ym}-01`, valor: valorAtual },
			})
			.then((resposta) => {
				const dados = (resposta && resposta.message) || {};
				const transacoes = dados.transacoes || [];
				const encontrouAtual = transacoes.some(
					(transacao) => transacao.name === transacaoAtual
				);

				const opcoes = ['<option value="">— nenhuma —</option>'];
				transacoes.forEach((transacao) =>
					opcoes.push(montarOpcaoTransacao(transacao, transacaoAtual))
				);
				if (transacaoAtual && !encontrouAtual) {
					opcoes.push(
						`<option value="${escapeHtml(transacaoAtual)}" selected>${escapeHtml(
							transacaoAtual
						)} (fora da janela buscada)</option>`
					);
				}
				opcoes.push(
					`<option value="${VALOR_TRANSACAO_MANUAL}">Outro (informar ID manualmente)…</option>`
				);

				select.innerHTML = opcoes.join("");
				alternarInputManual(select, manual);
			})
			.catch(() => {
				select.innerHTML = `<option value="${VALOR_TRANSACAO_MANUAL}" selected>Outro (informar ID manualmente)…</option>`;
				alternarInputManual(select, manual);
			});
	}

	function editarMes(botao) {
		if (semPermissao()) return;
		const linha = botao.closest("tr.contrib-mes");
		if (!linha || linha.querySelector(".contrib-mes__editor")) return;

		// Tudo que entra no innerHTML abaixo passa por escapeHtml, mesmo o que hoje só
		// vem de atributos que este mesmo script escreveu (data-ym, data-status...):
		// são todos derivados de dado editável por quem gerencia a contribuição, e o
		// scanner de segurança (corretamente) não assume que vão continuar inofensivos.
		const ym = escapeHtml(linha.getAttribute("data-ym") || "");
		const statusAtual = linha.getAttribute("data-status") || "Em Aberto";
		const valorNumerico = parseNumber(linha.getAttribute("data-valor"));
		const valorAtual = escapeHtml(String(valorNumerico));
		const transacaoAtual = linha.getAttribute("data-transacao") || "";
		const atrasouAtual = linha.getAttribute("data-atrasou") === "1";

		const opcoesStatus = STATUS_OPCOES.map(
			(opcao) =>
				`<option value="${escapeHtml(opcao)}" ${
					opcao === statusAtual ? "selected" : ""
				}>${escapeHtml(opcao)}</option>`
		).join("");

		const editor = document.createElement("tr");
		editor.className = "contrib-mes__editor";
		const colspan = window.canManageContrib ? 5 : 4;
		editor.innerHTML = `
			<td colspan="${colspan}">
				<div class="flex flex-wrap items-end gap-2 py-2">
					<div class="field">
						<label class="label" for="editStatus-${ym}">Status</label>
						<select id="editStatus-${ym}" class="input contrib-edit-status">${opcoesStatus}</select>
					</div>
					<div class="field">
						<label class="label" for="editValor-${ym}">Valor (R$)</label>
						<input type="number" min="0" step="0.01" id="editValor-${ym}" class="input contrib-edit-valor" value="${valorAtual}" />
					</div>
					<label class="flex items-center gap-2 text-sm">
						<input type="checkbox" class="contrib-edit-atrasou" ${atrasouAtual ? "checked" : ""} />
						Pago em atraso
					</label>
					<div class="field flex-1 min-w-[260px]">
						<label class="label" for="editTransacao-${ym}">Transação vinculada</label>
						<select id="editTransacao-${ym}" class="input contrib-edit-transacao">
							<option value="">Carregando transações do período…</option>
						</select>
						<input type="text" class="input contrib-edit-transacao-manual hidden mt-1"
							value="${escapeHtml(transacaoAtual)}" placeholder="ID da transação" />
					</div>
					<button type="button" class="btn-sm-primary" data-acao="salvar-mes">Salvar</button>
					<button type="button" class="btn-sm-outline" data-acao="cancelar-mes">Cancelar</button>
				</div>
			</td>
		`;
		linha.after(editor);
		botao.classList.add("hidden");

		carregarTransacoesCandidatas(editor, ym, transacaoAtual, valorNumerico);
	}

	function cancelarEdicaoMes(botao) {
		const editor = botao.closest("tr.contrib-mes__editor");
		if (!editor) return;
		const linha = editor.previousElementSibling;
		editor.remove();
		if (linha) {
			const botaoEditar = linha.querySelector(".contrib-mes__editar");
			if (botaoEditar) botaoEditar.classList.remove("hidden");
		}
	}

	function salvarMes(botao) {
		if (semPermissao()) return;
		const editor = botao.closest("tr.contrib-mes__editor");
		const linha = editor && editor.previousElementSibling;
		if (!editor || !linha) return;

		const status = editor.querySelector(".contrib-edit-status")?.value;
		const valor = parseFloat(editor.querySelector(".contrib-edit-valor")?.value);
		const atrasou = editor.querySelector(".contrib-edit-atrasou")?.checked;
		const selectTransacao = editor.querySelector(".contrib-edit-transacao");
		const transacao =
			selectTransacao?.value === VALOR_TRANSACAO_MANUAL
				? (editor.querySelector(".contrib-edit-transacao-manual")?.value || "").trim()
				: (selectTransacao?.value || "").trim();

		if (!Number.isFinite(valor) || valor < 0) {
			showToast("Informe um valor válido.", "orange");
			return;
		}

		frappe
			.call({
				method: "gris.api.financeiro.monthly_payments.definir_pagamento",
				args: {
					associado: associado,
					mes_de_referencia: `${linha.getAttribute("data-ym")}-01`,
					status: status,
					valor: valor,
					atrasou: atrasou ? 1 : 0,
					transacao_extrato: transacao,
				},
				freeze: true,
			})
			.then((resposta) => {
				const dados = (resposta && resposta.message) || {};
				if (!dados.ok) {
					showToast("Não foi possível salvar o mês.", "red");
					return;
				}
				showToast("Mês atualizado", "green");
				window.setTimeout(() => window.location.reload(), 600);
			})
			.catch(() => showToast("Erro ao salvar o mês.", "red"));
	}

	// ─────────────────────────── cobrança InfinitePay ───────────────────────────

	function elementosCobranca() {
		return {
			secao: document.getElementById("cobrancaInfinitepay"),
			pendentes: document.getElementById("cobrancaPendentes"),
			acoes: document.getElementById("cobrancaAcoes"),
			total: document.getElementById("cobrancaTotal"),
			emitidas: document.getElementById("cobrancaEmitidas"),
		};
	}

	function competenciasMarcadas() {
		const marcadas = document.querySelectorAll(".contrib-cobranca__competencia:checked");
		return Array.prototype.map.call(marcadas, (item) => item.value);
	}

	function atualizarTotalCobranca() {
		const { total } = elementosCobranca();
		if (!total) return;
		const marcadas = document.querySelectorAll(".contrib-cobranca__competencia:checked");
		const soma = Array.prototype.reduce.call(
			marcadas,
			(acumulado, item) => acumulado + parseNumber(item.getAttribute("data-valor")),
			0
		);
		total.textContent = marcadas.length ? `Total: R$ ${formatarMoeda(soma)}` : "";
	}

	function renderPendentes(pendentes) {
		const { pendentes: caixa, acoes } = elementosCobranca();
		if (!caixa) return;

		if (!pendentes || !pendentes.length) {
			caixa.innerHTML =
				'<p class="m-0 text-sm text-muted-foreground">Nenhuma competência em aberto no período apurado.</p>';
			if (acoes) acoes.classList.add("hidden");
			return;
		}

		caixa.innerHTML = pendentes
			.map(
				(pendente) => `
				<label class="contrib-cobranca__item">
					<input type="checkbox" class="contrib-cobranca__competencia" checked
						value="${escapeHtml(pendente.ym)}" data-valor="${escapeHtml(pendente.valor)}" />
					<span>${escapeHtml(pendente.rotulo)}</span>
					<span class="badge contrib-badge contrib-badge--${escapeHtml(pendente.status_slug)}">${escapeHtml(
					pendente.status
				)}</span>
					<span class="contrib-num text-muted-foreground">R$ ${formatarMoeda(pendente.valor)}</span>
				</label>`
			)
			.join("");

		if (acoes) acoes.classList.remove("hidden");
		atualizarTotalCobranca();
	}

	function renderCobrancasEmitidas(cobrancas) {
		const { emitidas } = elementosCobranca();
		if (!emitidas) return;

		const pendentesComLink = (cobrancas || []).filter(
			(cobranca) => cobranca.status === "Pendente" && cobranca.link_pagamento
		);
		if (!pendentesComLink.length) {
			emitidas.innerHTML = "";
			return;
		}

		emitidas.innerHTML = `
			<h4 class="text-xs font-semibold text-muted-foreground mb-2">Cobranças em aberto</h4>
			${pendentesComLink
				.map(
					(cobranca) => `
				<div class="contrib-cobranca__emitida">
					<a href="${escapeHtml(cobranca.link_pagamento)}" target="_blank" rel="noopener noreferrer">
						${escapeHtml(cobranca.name)}
					</a>
					<span class="text-xs text-muted-foreground">${escapeHtml(cobranca.competencias || "")}</span>
					<button type="button" class="btn-sm-outline" data-acao="reenviar-cobranca"
						data-cobranca="${escapeHtml(cobranca.name)}">Reenviar no WhatsApp</button>
				</div>`
				)
				.join("")}`;
	}

	function carregarCobranca() {
		const { secao, pendentes, acoes, emitidas } = elementosCobranca();
		if (!secao) return;

		if (pendentes) {
			pendentes.innerHTML = '<p class="m-0 text-sm text-muted-foreground">Carregando…</p>';
		}
		if (acoes) acoes.classList.add("hidden");
		if (emitidas) emitidas.innerHTML = "";

		frappe
			.call({
				method: "gris.api.financeiro.cobranca_contribuicao.get_cobranca_do_associado",
				args: { associado: associado, meses: meses },
			})
			.then((resposta) => {
				const dados = (resposta && resposta.message) || {};
				renderPendentes(dados.pendentes);
				renderCobrancasEmitidas(dados.cobrancas);
			})
			.catch(() => {
				if (pendentes) {
					pendentes.innerHTML =
						'<p class="m-0 text-sm text-muted-foreground">Não foi possível carregar as competências em aberto.</p>';
				}
			});
	}

	function relatarEnvio(whatsapp) {
		if (!whatsapp) return;
		if (whatsapp.enviado) {
			showToast(`Link enviado no WhatsApp para ${whatsapp.telefone}.`, "green");
			return;
		}
		// A cobrança foi criada mesmo assim: o gestor ainda pode copiar o link da lista.
		showToast(`Cobrança criada, mas o WhatsApp falhou: ${whatsapp.motivo}`, "orange");
	}

	function gerarCobranca(enviarWhatsapp) {
		if (semPermissao()) return;
		const competencias = competenciasMarcadas();
		if (!competencias.length) {
			showToast("Selecione ao menos uma competência para cobrar.", "orange");
			return;
		}

		frappe
			.call({
				method: "gris.api.financeiro.cobranca_contribuicao.gerar_cobranca",
				args: {
					associado: associado,
					competencias: competencias.join(","),
					enviar_whatsapp: enviarWhatsapp ? 1 : 0,
					meses: meses,
				},
				freeze: true,
			})
			.then((resposta) => {
				const dados = (resposta && resposta.message) || {};
				if (!dados.success) {
					showToast("Não foi possível gerar a cobrança.", "red");
					return;
				}
				if (!enviarWhatsapp) showToast("Link de pagamento gerado.", "green");
				relatarEnvio(dados.whatsapp);
				carregarCobranca();
			})
			.catch(() => showToast("Erro ao gerar a cobrança.", "red"));
	}

	function reenviarCobranca(elemento) {
		if (semPermissao()) return;
		const name = elemento.getAttribute("data-cobranca");
		if (!name) return;

		frappe
			.call({
				method: "gris.api.financeiro.cobranca_contribuicao.enviar_cobranca_whatsapp",
				args: { name: name },
				freeze: true,
			})
			.then((resposta) => {
				const dados = (resposta && resposta.message) || {};
				relatarEnvio(dados.whatsapp);
			})
			.catch(() => showToast("Erro ao reenviar a cobrança.", "red"));
	}

	// ─────────────────────────── ligações ───────────────────────────

	const ACOES = {
		"alterar-valor": alterarValor,
		"salvar-valor": salvarNovoValor,
		"cancelar-valor": cancelarEdicaoValor,
		"editar-mes": editarMes,
		"salvar-mes": salvarMes,
		"cancelar-mes": cancelarEdicaoMes,
		"editar-cobranca": editarCobranca,
		"salvar-cobranca": salvarDadosCobranca,
		"cancelar-cobranca": restaurarCobranca,
		"cadastro-realizado": cadastroRealizado,
		"cadastro-cancelado": cadastroCancelado,
		"cobrar-whatsapp": () => gerarCobranca(true),
		"cobrar-link": () => gerarCobranca(false),
		"reenviar-cobranca": reenviarCobranca,
	};

	function init() {
		if (!associado) return;

		document.addEventListener("change", (evento) => {
			if (evento.target.classList.contains("contrib-cobranca__competencia")) {
				atualizarTotalCobranca();
			}
		});

		document.addEventListener("click", (evento) => {
			const alvo = evento.target.closest("[data-acao]");
			if (!alvo) return;
			const acao = ACOES[alvo.getAttribute("data-acao")];
			if (!acao) return;
			evento.preventDefault();
			acao(alvo);
		});

		if (window.canManageContrib) carregarCobranca();
	}

	if (document.readyState === "loading") {
		document.addEventListener("DOMContentLoaded", init);
	} else {
		init();
	}
})();
