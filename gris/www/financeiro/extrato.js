/**
 * Extrato financeiro: grid compacto, scroll infinito e edição em lote na célula.
 *
 * As linhas são renderizadas pelo mesmo template Jinja no servidor
 * (`templates/includes/financeiro/extrato_linhas.html`), tanto no primeiro
 * lote quanto nos lotes seguintes, entregues por
 * `gris.api.financeiro.transactions.get_extrato_rows`.
 */
(function () {
	"use strict";

	const FILTER_KEYS = [
		"descricao",
		"descricao_completa",
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

	const COLUNAS_STORAGE_KEY = "gris_extrato_colunas_v1";
	const FILTROS_STORAGE_KEY = "gris_extrato_filtros_abertos_v1";

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
	let scrollEl = null;
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

	/**
	 * Encaixa a área rolável do grid no que sobra da viewport.
	 *
	 * O cabeçalho é `position: sticky`, e como `overflow-x: auto` já torna o
	 * contêiner um scrollport vertical, ele só gruda se o contêiner couber na
	 * tela — caso contrário quem rola é a página e o cabeçalho sai junto. A
	 * altura depende de onde o grid começa (o card de filtros varia com a
	 * largura), então só o cliente sabe calcular.
	 */
	function ajustarAlturaDoGrid() {
		if (!scrollEl) return;
		// Abaixo de 48rem a rolagem é a da página, como define o CSS da rota.
		if (window.innerWidth < 768) {
			scrollEl.style.maxHeight = "";
			return;
		}
		const topo = scrollEl.getBoundingClientRect().top;
		const disponivel = window.innerHeight - topo - 24;
		scrollEl.style.maxHeight = Math.max(disponivel, 320) + "px";
	}

	/**
	 * Lembra se o painel de filtros fica aberto ou fechado.
	 *
	 * O servidor já abre o painel quando a URL traz filtro ativo; a escolha
	 * explícita do usuário, quando existe, tem precedência.
	 */
	function iniciarPainelDeFiltros() {
		const painel = document.getElementById("extratoFiltros");
		if (!painel) return;

		try {
			const salvo = window.localStorage.getItem(FILTROS_STORAGE_KEY);
			if (salvo === "1" || salvo === "0") painel.open = salvo === "1";
		} catch (_erro) {
			// Sem storage, vale o padrão do servidor.
		}

		painel.addEventListener("toggle", function () {
			try {
				window.localStorage.setItem(FILTROS_STORAGE_KEY, painel.open ? "1" : "0");
			} catch (_erro) {
				// Preferência é conveniência; ignorar falha de storage.
			}
			// Abrir/fechar move o grid na página, então a altura é recalculada.
			ajustarAlturaDoGrid();
		});
	}

	// -----------------------------------------------------------------------
	// Seletor de colunas
	//
	// Todas as colunas vêm renderizadas do servidor; mostrar/esconder é só CSS
	// sobre `data-col`, então a troca é imediata e vale também para as linhas
	// que o scroll infinito ainda vai carregar.
	// -----------------------------------------------------------------------

	function getColunaCheckboxes() {
		return Array.from(document.querySelectorAll("[data-col-toggle]"));
	}

	function lerPreferenciaColunas() {
		try {
			const salvo = JSON.parse(window.localStorage.getItem(COLUNAS_STORAGE_KEY) || "null");
			return salvo && typeof salvo === "object" ? salvo : null;
		} catch (_erro) {
			return null;
		}
	}

	function salvarPreferenciaColunas(visiveis) {
		try {
			window.localStorage.setItem(COLUNAS_STORAGE_KEY, JSON.stringify(visiveis));
		} catch (_erro) {
			// Preferência é conveniência; sem storage a tela segue no padrão.
		}
	}

	function aplicarColunas() {
		const style = document.getElementById("extratoColunasStyle");
		if (!style) return;
		const ocultas = getColunaCheckboxes()
			.filter(function (cb) {
				return !cb.checked;
			})
			.map(function (cb) {
				return '[data-col="' + cb.dataset.colToggle + '"]{display:none}';
			});
		style.textContent = ocultas.join("");
	}

	function iniciarSeletorDeColunas() {
		const checkboxes = getColunaCheckboxes();
		if (!checkboxes.length) return;

		const preferencia = lerPreferenciaColunas();
		if (preferencia) {
			checkboxes.forEach(function (cb) {
				const escolha = preferencia[cb.dataset.colToggle];
				// Coluna nova (ainda não conhecida pela preferência) entra no padrão.
				if (typeof escolha === "boolean") cb.checked = escolha;
			});
		}
		aplicarColunas();

		checkboxes.forEach(function (cb) {
			cb.addEventListener("change", function () {
				aplicarColunas();
				salvarPreferenciaColunas(
					Object.fromEntries(
						getColunaCheckboxes().map(function (item) {
							return [item.dataset.colToggle, item.checked];
						})
					)
				);
			});
		});

		const restaurar = document.getElementById("extratoColunasPadrao");
		if (restaurar) {
			restaurar.addEventListener("click", function () {
				checkboxes.forEach(function (cb) {
					// `defaultChecked` guarda o padrão renderizado pelo servidor.
					cb.checked = cb.defaultChecked;
				});
				aplicarColunas();
				try {
					window.localStorage.removeItem(COLUNAS_STORAGE_KEY);
				} catch (_erro) {
					// Sem storage não há preferência para remover.
				}
			});
		}
	}

	// -----------------------------------------------------------------------
	// Seleção e edição em lote direto na célula
	//
	// Toda coluna editável carrega `data-editavel` e `data-valor` na célula.
	// Clicar abre o editor ali mesmo; se a linha estiver selecionada, o valor
	// escolhido vai para todas as linhas selecionadas numa única chamada.
	// -----------------------------------------------------------------------

	let opcoesEditaveis = {};
	let editorAberto = null;

	function lerOpcoesEditaveis() {
		const el = document.getElementById("extratoOpcoesEditaveis");
		if (!el) return {};
		try {
			return JSON.parse(el.textContent || "{}") || {};
		} catch (_erro) {
			// Sem opções o editor de select fica vazio, mas a tela segue usável.
			return {};
		}
	}

	function idsSelecionados() {
		return Array.from(document.querySelectorAll(".transaction-checkbox:checked")).map(
			function (cb) {
				return cb.value;
			}
		);
	}

	function sincronizarSelectAll() {
		const todos = document.querySelectorAll(".transaction-checkbox");
		const marcados = document.querySelectorAll(".transaction-checkbox:checked");
		const selectAll = document.getElementById("selectAll");
		if (selectAll) {
			selectAll.checked = todos.length > 0 && marcados.length === todos.length;
			selectAll.indeterminate = marcados.length > 0 && marcados.length < todos.length;
		}
		atualizarBarraSelecao(marcados.length);
	}

	function atualizarBarraSelecao(quantidade) {
		const barra = document.getElementById("extratoSelecao");
		const contador = document.getElementById("selectedCount");
		if (contador) contador.textContent = quantidade;
		if (barra) barra.classList.toggle("hidden", quantidade === 0);
	}

	function toggleSelectAll(marcado) {
		document.querySelectorAll(".transaction-checkbox").forEach(function (cb) {
			cb.checked = marcado;
		});
		sincronizarSelectAll();
	}

	function limparSelecao() {
		document.querySelectorAll(".transaction-checkbox").forEach(function (cb) {
			cb.checked = false;
		});
		sincronizarSelectAll();
	}

	/** Linhas que recebem a edição: a seleção inteira, ou só a linha clicada. */
	function alvosDaEdicao(td) {
		const linha = td.closest("tr[data-transaction-id]");
		if (!linha) return [];
		const checkbox = linha.querySelector(".transaction-checkbox");
		if (checkbox && checkbox.checked) {
			const selecionados = idsSelecionados();
			if (selecionados.length) return selecionados;
		}
		return [linha.dataset.transactionId];
	}

	function marcarSalvando(ids, salvando) {
		ids.forEach(function (id) {
			const linha = tbody.querySelector('tr[data-transaction-id="' + CSS.escape(id) + '"]');
			if (!linha) return;
			linha.classList.toggle("extrato-row--salvando", salvando);
			if (salvando) linha.setAttribute("aria-busy", "true");
			else linha.removeAttribute("aria-busy");
		});
	}

	/** Troca as linhas alteradas pelo HTML recém-renderizado, mantendo a seleção. */
	function substituirLinhas(html) {
		const parser = document.createElement("tbody");
		parser.innerHTML = html || "";
		Array.from(parser.querySelectorAll("tr[data-transaction-id]")).forEach(function (nova) {
			const id = nova.getAttribute("data-transaction-id");
			const atual = tbody.querySelector('tr[data-transaction-id="' + CSS.escape(id) + '"]');
			if (!atual) return;
			const marcada = atual.querySelector(".transaction-checkbox");
			const novaCheckbox = nova.querySelector(".transaction-checkbox");
			if (marcada && novaCheckbox) novaCheckbox.checked = marcada.checked;
			atual.replaceWith(nova);
		});
		sincronizarSelectAll();
	}

	function salvarCampo(ids, campo, valor) {
		if (!ids.length) return;
		marcarSalvando(ids, true);
		frappe.call({
			method: "gris.api.financeiro.transactions.update_extrato_celulas",
			args: {
				transaction_ids: JSON.stringify(ids),
				campo: campo,
				valor: valor,
			},
			callback: function (r) {
				const dados = r && r.message;
				if (!dados) return;
				substituirLinhas(dados.html);
				frappe.show_alert({
					message:
						dados.updated_count === 1
							? __("1 transação atualizada")
							: __("{0} transações atualizadas", [dados.updated_count]),
					indicator: "green",
				});
				if (dados.falhas) {
					frappe.show_alert({
						message: __("{0} transações não puderam ser alteradas", [dados.falhas]),
						indicator: "orange",
					});
				}
			},
			always: function () {
				marcarSalvando(ids, false);
			},
		});
	}

	function fecharEditor(restaurar) {
		if (!editorAberto) return;
		const { td, conteudo } = editorAberto;
		editorAberto = null;
		if (restaurar !== false) td.innerHTML = conteudo;
		td.classList.remove("extrato-cell--editando");
	}

	function confirmarEdicao() {
		if (!editorAberto) return;
		const { td, campo, alvos, controle } = editorAberto;
		const novoValor = controle.value;
		const valorAtual = td.dataset.valor || "";
		fecharEditor();
		if (novoValor === valorAtual) return;
		salvarCampo(alvos, campo, novoValor);
	}

	function montarControle(tipo, campo, valorAtual) {
		if (tipo !== "opcoes") {
			const input = document.createElement("input");
			input.type = "text";
			input.className = "extrato-editor__campo";
			input.value = valorAtual;
			return input;
		}

		const select = document.createElement("select");
		select.className = "extrato-editor__campo";
		select.appendChild(new Option(__("— Sem valor —"), ""));
		const opcoes = opcoesEditaveis[campo] || [];
		opcoes.forEach(function (opcao) {
			select.appendChild(new Option(opcao, opcao));
		});
		// Valor legado fora da lista continua selecionável, para não ser apagado sem querer.
		if (valorAtual && opcoes.indexOf(valorAtual) === -1) {
			select.appendChild(new Option(valorAtual, valorAtual));
		}
		select.value = valorAtual;
		return select;
	}

	function abrirEditor(td) {
		if (editorAberto && editorAberto.td === td) return;
		fecharEditor();

		const campo = td.dataset.col;
		const tipo = td.dataset.editavel;
		const valorAtual = td.dataset.valor || "";
		const alvos = alvosDaEdicao(td);
		if (!alvos.length) return;

		const controle = montarControle(tipo, campo, valorAtual);
		const wrapper = document.createElement("div");
		wrapper.className = "extrato-editor";
		wrapper.appendChild(controle);
		if (alvos.length > 1) {
			const marcador = document.createElement("span");
			marcador.className = "extrato-editor__lote";
			marcador.textContent = __("{0} linhas", [alvos.length]);
			wrapper.appendChild(marcador);
		}

		editorAberto = {
			td: td,
			conteudo: td.innerHTML,
			campo: campo,
			alvos: alvos,
			controle: controle,
		};
		td.innerHTML = "";
		td.appendChild(wrapper);
		td.classList.add("extrato-cell--editando");

		controle.addEventListener("keydown", function (event) {
			if (event.key === "Enter") {
				event.preventDefault();
				confirmarEdicao();
			} else if (event.key === "Escape") {
				event.preventDefault();
				fecharEditor();
				td.focus();
			}
		});
		if (tipo === "opcoes") {
			controle.addEventListener("change", confirmarEdicao);
			// Sair sem escolher nada não altera nada.
			controle.addEventListener("blur", function () {
				fecharEditor();
			});
		} else {
			// Texto salva ao sair do campo, como numa planilha.
			controle.addEventListener("blur", confirmarEdicao);
		}

		// A célula já está visível; rolar o grid ao focar tiraria o contexto de vista.
		controle.focus({ preventScroll: true });
		if (typeof controle.select === "function") controle.select();
	}

	/** Campo booleano não abre editor: o clique já alterna o valor. */
	function alternarBooleano(td) {
		const alvos = alvosDaEdicao(td);
		if (!alvos.length) return;
		const novoValor = td.dataset.valor === "1" ? "0" : "1";
		salvarCampo(alvos, td.dataset.col, novoValor);
	}

	function editarCelula(td) {
		if (td.dataset.editavel === "booleano") alternarBooleano(td);
		else abrirEditor(td);
	}

	// -----------------------------------------------------------------------
	// Delegação de eventos (cobre linhas carregadas dinamicamente)
	// -----------------------------------------------------------------------

	function ligarEventosDoGrid() {
		if (!tbody) return;

		tbody.addEventListener("click", function (event) {
			const celula = event.target.closest("td[data-editavel]");
			if (celula) {
				// Célula editável abre o editor no lugar de navegar.
				editarCelula(celula);
				return;
			}
			const linha = event.target.closest("tr[data-transaction-id]");
			if (!linha) return;
			// Checkbox e demais controles não navegam para o detalhe.
			if (event.target.closest(".extrato-col-select, a, button, input, select, label"))
				return;
			window.location.href =
				"/financeiro/detalhe_extrato?name=" +
				encodeURIComponent(linha.dataset.transactionId);
		});

		tbody.addEventListener("keydown", function (event) {
			const celula = event.target.closest("td[data-editavel]");
			// Só a própria célula responde ao teclado; dentro do editor os
			// atalhos são do controle (Enter salva, Esc cancela).
			if (!celula || celula !== event.target) return;
			if (event.key === "Enter" || event.key === " ") {
				event.preventDefault();
				editarCelula(celula);
			}
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

		const limpar = document.getElementById("extratoLimparSelecao");
		if (limpar) limpar.addEventListener("click", limparSelecao);

		if (carregarMaisBtn) carregarMaisBtn.addEventListener("click", carregarProximoLote);
	}

	function iniciar() {
		tbody = document.getElementById("extratoTbody");
		sentinela = document.getElementById("extratoSentinela");
		loadingEl = document.getElementById("extratoSentinelaLoading");
		fimEl = document.getElementById("extratoSentinelaFim");
		scrollEl = document.getElementById("extratoScroll");
		erroEl = document.getElementById("extratoSentinelaErro");
		carregarMaisBtn = document.getElementById("extratoCarregarMais");
		contadorEl = document.getElementById("extratoCarregadas");

		if (!tbody) return;

		opcoesEditaveis = lerOpcoesEditaveis();
		iniciarPainelDeFiltros();
		iniciarSeletorDeColunas();
		ajustarAlturaDoGrid();
		window.addEventListener("resize", ajustarAlturaDoGrid);
		ligarEventosDoGrid();
		sincronizarSelectAll();
		iniciarScrollInfinito();
	}

	// O script da rota é carregado depois da tabela, então normalmente já dá
	// para aplicar as colunas antes da primeira pintura.
	if (document.readyState === "loading") {
		document.addEventListener("DOMContentLoaded", iniciar);
	} else {
		iniciar();
	}
})();
