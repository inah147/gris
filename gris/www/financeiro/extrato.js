/**
 * Extrato financeiro: grid compacto com scroll infinito e edição em lote.
 *
 * As linhas são renderizadas pelo mesmo template Jinja no servidor
 * (`templates/includes/financeiro/extrato_linhas.html`), tanto no primeiro
 * lote quanto nos lotes seguintes, entregues por
 * `gris.api.financeiro.transactions.get_extrato_rows`.
 */
(function () {
	"use strict";

	const FILTER_KEYS = [
		"data_inicio",
		"data_fim",
		"instituicao",
		"carteira",
		"categoria",
		"centro_de_custo",
		"fixo_variavel",
		"ordinaria_extraordinaria",
		"conta_fixa",
		"repasse_entre_contas",
		"transacao_revisada",
		"fonte",
	];

	const state = {
		carregadas: 0,
		total: 0,
		pageSize: 100,
		temMais: false,
		carregando: false,
		erro: false,
	};

	let tbody = null;
	let sentinela = null;
	let loadingEl = null;
	let fimEl = null;
	let erroEl = null;
	let carregarMaisBtn = null;
	let contadorEl = null;

	function getFiltrosAtivos() {
		const params = new URLSearchParams(window.location.search);
		const filtros = {};
		FILTER_KEYS.forEach(function (key) {
			const valor = params.get(key);
			if (valor !== null && valor !== "" && valor !== "null") filtros[key] = valor;
		});
		return filtros;
	}

	function atualizarContador() {
		if (contadorEl) contadorEl.textContent = state.carregadas;
	}

	function mostrar(el, visivel) {
		if (el) el.classList.toggle("hidden", !visivel);
	}

	function atualizarSentinela() {
		mostrar(loadingEl, state.carregando);
		mostrar(fimEl, !state.carregando && !state.temMais && state.carregadas > 0);
		// Falha de carregamento: avisa e oferece nova tentativa manual.
		mostrar(erroEl, !state.carregando && state.erro);
		mostrar(carregarMaisBtn, !state.carregando && state.temMais && state.erro);
	}

	/** Insere as linhas do lote, ignorando ids já presentes no grid. */
	function anexarLinhas(html) {
		const parser = document.createElement("tbody");
		parser.innerHTML = html;
		const fragmento = document.createDocumentFragment();
		let inseridas = 0;
		Array.from(parser.querySelectorAll("tr[data-transaction-id]")).forEach(function (tr) {
			const id = tr.getAttribute("data-transaction-id");
			if (tbody.querySelector('tr[data-transaction-id="' + CSS.escape(id) + '"]')) return;
			fragmento.appendChild(tr);
			inseridas += 1;
		});
		tbody.appendChild(fragmento);
		return inseridas;
	}

	function carregarProximoLote() {
		if (state.carregando || !state.temMais) return;
		state.carregando = true;
		state.erro = false;
		atualizarSentinela();

		frappe.call({
			method: "gris.api.financeiro.transactions.get_extrato_rows",
			args: {
				filtros: JSON.stringify(getFiltrosAtivos()),
				start: state.carregadas,
				page_length: state.pageSize,
			},
			callback: function (r) {
				const dados = r && r.message;
				if (!dados) {
					state.erro = true;
					return;
				}
				const inseridas = anexarLinhas(dados.html || "");
				state.carregadas += dados.count || 0;
				state.temMais = !!dados.has_more;
				atualizarContador();
				sincronizarSelectAll();
				// `start` avança por `count`, então lotes com linhas repetidas
				// (ordenação estável, mas concorrência com edições) não travam o scroll.
				if (!inseridas && !dados.count) state.temMais = false;
			},
			error: function () {
				state.erro = true;
			},
			always: function () {
				state.carregando = false;
				atualizarSentinela();
				// Se a sentinela continuar visível (tela alta), segue carregando.
				if (!state.erro && state.temMais && sentinelaVisivel()) {
					window.requestAnimationFrame(carregarProximoLote);
				}
			},
		});
	}

	function sentinelaVisivel() {
		if (!sentinela) return false;
		const rect = sentinela.getBoundingClientRect();
		const alturaVisivel = window.innerHeight || document.documentElement.clientHeight;
		return rect.top <= alturaVisivel && rect.bottom >= 0;
	}

	function iniciarScrollInfinito() {
		if (!sentinela) return;
		state.carregadas = parseInt(sentinela.dataset.carregadas, 10) || 0;
		state.total = parseInt(sentinela.dataset.total, 10) || 0;
		state.pageSize = parseInt(sentinela.dataset.pagesize, 10) || 100;
		state.temMais = sentinela.dataset.temMais === "1";
		atualizarSentinela();

		if (!state.temMais) return;

		if (typeof IntersectionObserver === "undefined") {
			// Navegador sem suporte: mantém o botão manual como alternativa.
			state.erro = true;
			atualizarSentinela();
			return;
		}

		const observer = new IntersectionObserver(
			function (entries) {
				entries.forEach(function (entry) {
					if (entry.isIntersecting) carregarProximoLote();
				});
			},
			{ rootMargin: "400px 0px" }
		);
		observer.observe(sentinela);
	}

	// -----------------------------------------------------------------------
	// Seleção e edição em lote
	// -----------------------------------------------------------------------

	function sincronizarSelectAll() {
		const todos = document.querySelectorAll(".transaction-checkbox");
		const marcados = document.querySelectorAll(".transaction-checkbox:checked");
		const selectAll = document.getElementById("selectAll");
		if (selectAll) {
			selectAll.checked = todos.length > 0 && marcados.length === todos.length;
			selectAll.indeterminate = marcados.length > 0 && marcados.length < todos.length;
		}
		atualizarPainelSelecao(marcados.length);
	}

	function atualizarPainelSelecao(quantidade) {
		const painel = document.getElementById("batchEditPanel");
		const contador = document.getElementById("selectedCount");
		if (contador) contador.textContent = quantidade;
		if (painel) painel.classList.toggle("hidden", quantidade === 0);
	}

	function toggleSelectAll(marcado) {
		document.querySelectorAll(".transaction-checkbox").forEach(function (cb) {
			cb.checked = marcado;
		});
		sincronizarSelectAll();
	}

	function cancelarSelecao() {
		document.querySelectorAll(".transaction-checkbox").forEach(function (cb) {
			cb.checked = false;
		});
		sincronizarSelectAll();

		const descricao = document.getElementById("batch_descricao_reduzida");
		if (descricao) descricao.value = "";
		[
			"batch_categoria",
			"batch_centro_de_custo",
			"batch_ordinaria_extraordinaria",
			"batch_transacao_revisada",
		].forEach(function (id) {
			const wrapper = document.getElementById(id);
			if (!wrapper) return;
			const hidden = wrapper.querySelector('input[type="hidden"]');
			if (hidden) hidden.value = "";
			const trigger = wrapper.querySelector('[id$="-trigger"] .truncate');
			if (trigger) trigger.textContent = "Não alterar";
		});
	}

	function getBatchSelectValue(wrapperId) {
		const wrapper = document.getElementById(wrapperId);
		if (!wrapper) return "";
		const hidden = wrapper.querySelector('input[type="hidden"]');
		return hidden ? hidden.value : "";
	}

	function salvarEdicaoLote() {
		const selecionadas = Array.from(
			document.querySelectorAll(".transaction-checkbox:checked")
		).map(function (cb) {
			return cb.value;
		});

		if (selecionadas.length === 0) {
			frappe.msgprint(__("Nenhuma transação selecionada"));
			return;
		}

		const updates = {};
		const descricaoEl = document.getElementById("batch_descricao_reduzida");
		const descricao = descricaoEl ? descricaoEl.value.trim() : "";
		const categoria = getBatchSelectValue("batch_categoria");
		const centroCusto = getBatchSelectValue("batch_centro_de_custo");
		const ordinaria = getBatchSelectValue("batch_ordinaria_extraordinaria");
		const revisada = getBatchSelectValue("batch_transacao_revisada");

		if (descricao) updates.descricao_reduzida = descricao;
		if (categoria) updates.categoria = categoria;
		if (centroCusto) updates.centro_de_custo = centroCusto;
		if (ordinaria) updates.ordinaria_extraordinaria = ordinaria;
		if (revisada) updates.transacao_revisada = parseInt(revisada, 10);

		if (Object.keys(updates).length === 0) {
			frappe.msgprint(__("Selecione pelo menos um campo para alterar"));
			return;
		}

		frappe.call({
			method: "gris.api.financeiro.transactions.batch_update_transactions",
			args: {
				transaction_ids: JSON.stringify(selecionadas),
				updates: JSON.stringify(updates),
			},
			freeze: true,
			freeze_message: __("Atualizando transações..."),
			callback: function (r) {
				if (r.message && r.message.success) {
					frappe.show_alert({
						message: __("{0} transações atualizadas com sucesso", [
							r.message.updated_count,
						]),
						indicator: "green",
					});
					setTimeout(function () {
						window.location.reload();
					}, 1500);
				}
			},
			error: function () {
				frappe.msgprint(__("Erro ao atualizar transações"));
			},
		});
	}

	// -----------------------------------------------------------------------
	// Delegação de eventos (cobre linhas carregadas dinamicamente)
	// -----------------------------------------------------------------------

	function ligarEventosDoGrid() {
		if (!tbody) return;

		tbody.addEventListener("click", function (event) {
			const linha = event.target.closest("tr[data-transaction-id]");
			if (!linha) return;
			// Checkbox e demais controles não navegam para o detalhe.
			if (event.target.closest(".extrato-col-select, a, button, input, label")) return;
			window.location.href =
				"/financeiro/detalhe_extrato?name=" +
				encodeURIComponent(linha.dataset.transactionId);
		});

		tbody.addEventListener("change", function (event) {
			if (event.target.classList.contains("transaction-checkbox")) sincronizarSelectAll();
		});

		const selectAll = document.getElementById("selectAll");
		if (selectAll) {
			selectAll.addEventListener("change", function () {
				toggleSelectAll(selectAll.checked);
			});
		}

		const cancelar = document.getElementById("batchCancelar");
		if (cancelar) cancelar.addEventListener("click", cancelarSelecao);

		const salvar = document.getElementById("batchSalvar");
		if (salvar) salvar.addEventListener("click", salvarEdicaoLote);

		if (carregarMaisBtn) carregarMaisBtn.addEventListener("click", carregarProximoLote);
	}

	document.addEventListener("DOMContentLoaded", function () {
		tbody = document.getElementById("extratoTbody");
		sentinela = document.getElementById("extratoSentinela");
		loadingEl = document.getElementById("extratoSentinelaLoading");
		fimEl = document.getElementById("extratoSentinelaFim");
		erroEl = document.getElementById("extratoSentinelaErro");
		carregarMaisBtn = document.getElementById("extratoCarregarMais");
		contadorEl = document.getElementById("extratoCarregadas");

		if (!tbody) return;

		ligarEventosDoGrid();
		sincronizarSelectAll();
		iniciarScrollInfinito();
	});
})();
