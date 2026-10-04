(function () {
	const form = document.getElementById("compras-form");
	if (!form) return;

	const raiz = document.querySelector(".compras-solicitar");
	const area = raiz.dataset.area;
	const areaSlug = raiz.dataset.areaSlug;
	const programaEducativo = raiz.dataset.programaEducativo === "1";
	const itemNovo = raiz.dataset.itemNovo || "";
	// Rascunho do pedido guardado enquanto a página recarrega para mostrar um item
	// recém-cadastrado no catálogo: o select do Basecoat lê as opções só na inicialização.
	const CHAVE_RASCUNHO = `compras-rascunho-${areaSlug}`;

	const lista = document.getElementById("compras-itens");
	const template = document.getElementById("compras-item-template");
	const btnAdd = document.getElementById("compras-add-item");
	const submitBtn = document.getElementById("compras-submit");
	const totalEl = document.getElementById("compras-total");

	let precos = {};
	try {
		precos = JSON.parse(document.getElementById("compras-precos").textContent) || {};
	} catch (error) {
		precos = {};
	}

	let proximoIndice = 0;

	function showToast(category, message) {
		document.dispatchEvent(
			new CustomEvent("basecoat:toast", {
				detail: { config: { category, title: message, duration: 3500 } },
			})
		);
	}

	function formatarMoeda(valor) {
		return valor.toLocaleString("pt-BR", { style: "currency", currency: "BRL" });
	}

	function lerCampo(row, nome) {
		const campo = row.querySelector(`[name="${nome}"]`);
		return campo ? (campo.value || "").trim() : "";
	}

	function lerQuantidade(row) {
		const bruto = parseInt(lerCampo(row, "quantidade"), 10);
		return Number.isFinite(bruto) && bruto > 0 ? bruto : 0;
	}

	function atualizarTotais() {
		let total = 0;
		lista.querySelectorAll("[data-item-row]").forEach(function (row) {
			const item = lerCampo(row, "item_catalogo");
			const quantidade = lerQuantidade(row);
			const subtotal = item ? (precos[item] || 0) * quantidade : 0;
			total += subtotal;

			const alvo = row.querySelector("[data-item-subtotal]");
			if (alvo) alvo.textContent = formatarMoeda(subtotal);
		});

		totalEl.textContent = formatarMoeda(total);
	}

	function atualizarBotoesRemover() {
		const rows = lista.querySelectorAll("[data-item-row]");
		rows.forEach(function (row) {
			const botao = row.querySelector("[data-item-remove]");
			if (botao) botao.disabled = rows.length <= 1;
		});
	}

	function adicionarItem() {
		const markup = template.innerHTML.replace(/__IDX__/g, String(proximoIndice));
		proximoIndice += 1;
		lista.insertAdjacentHTML("beforeend", markup);
		// Inicializa os componentes Basecoat da linha recém-inserida.
		document.dispatchEvent(new CustomEvent("gris:design-system:init"));
		atualizarBotoesRemover();
		atualizarTotais();
		return lista.lastElementChild;
	}

	btnAdd.addEventListener("click", function () {
		adicionarItem();
	});

	lista.addEventListener("click", function (event) {
		const botao = event.target.closest("[data-item-remove]");
		if (!botao || botao.disabled) return;
		const row = botao.closest("[data-item-row]");
		if (row) row.remove();
		atualizarBotoesRemover();
		atualizarTotais();
	});

	// `change` cobre tanto os inputs nativos quanto o hidden atualizado pelo select.
	lista.addEventListener("change", atualizarTotais);
	lista.addEventListener("input", atualizarTotais);

	function coletarItens() {
		const itens = [];
		let linhaVazia = false;
		let quantidadeInvalida = false;

		lista.querySelectorAll("[data-item-row]").forEach(function (row) {
			const item = lerCampo(row, "item_catalogo");
			if (!item) {
				linhaVazia = true;
				return;
			}
			const quantidade = lerQuantidade(row);
			if (!quantidade) {
				quantidadeInvalida = true;
				return;
			}
			itens.push({
				item_catalogo: item,
				quantidade: quantidade,
				observacao: lerCampo(row, "observacao"),
			});
		});

		return { itens: itens, linhaVazia: linhaVazia, quantidadeInvalida: quantidadeInvalida };
	}

	form.addEventListener("submit", function (event) {
		event.preventDefault();
		if (submitBtn.disabled) return;

		const ramo = (form.querySelector('[name="ramo"]')?.value || "").trim();
		if (programaEducativo && !ramo) {
			showToast("warning", "Selecione o ramo ou seção do pedido.");
			return;
		}

		const coleta = coletarItens();
		if (coleta.linhaVazia) {
			showToast("warning", "Escolha o item de todas as linhas ou remova as vazias.");
			return;
		}
		if (coleta.quantidadeInvalida) {
			showToast("warning", "Informe uma quantidade maior que zero em todos os itens.");
			return;
		}
		if (!coleta.itens.length) {
			showToast("warning", "Inclua ao menos um item na solicitação.");
			return;
		}

		const payload = {
			area: area,
			ramo: ramo,
			justificativa: (form.querySelector('[name="justificativa"]')?.value || "").trim(),
			itens: coleta.itens,
		};

		submitBtn.disabled = true;

		frappe.call({
			method: "gris.api.compras.endpoints.criar_solicitacao",
			args: { payload: JSON.stringify(payload) },
			freeze: true,
			freeze_message: "Enviando solicitação...",
			callback: function (r) {
				if (r.exc || !r.message) return;
				limparRascunho();
				showToast("success", "Solicitação enviada com sucesso.");
				window.location.href = r.message.redirect || "/compras/minhas_solicitacoes";
			},
			always: function () {
				submitBtn.disabled = false;
			},
		});
	});

	// ---------------------------------------------------------------- rascunho

	// O Basecoat expõe `value` no elemento raiz do select; escrever só no hidden não
	// atualizaria o rótulo visível.
	function definirSelect(root, valor) {
		if (!root || !valor) return;
		root.value = valor;
	}

	function salvarRascunho() {
		const rascunho = {
			ramo: (form.querySelector('[name="ramo"]')?.value || "").trim(),
			justificativa: (form.querySelector('[name="justificativa"]')?.value || "").trim(),
			itens: Array.from(lista.querySelectorAll("[data-item-row]")).map(function (row) {
				return {
					item_catalogo: lerCampo(row, "item_catalogo"),
					quantidade: lerCampo(row, "quantidade"),
					observacao: lerCampo(row, "observacao"),
				};
			}),
		};
		try {
			window.sessionStorage.setItem(CHAVE_RASCUNHO, JSON.stringify(rascunho));
		} catch (error) {
			// Sem sessionStorage o pedido recomeça, mas o item novo continua cadastrado.
		}
	}

	function lerRascunho() {
		try {
			return JSON.parse(window.sessionStorage.getItem(CHAVE_RASCUNHO) || "null");
		} catch (error) {
			return null;
		}
	}

	function limparRascunho() {
		try {
			window.sessionStorage.removeItem(CHAVE_RASCUNHO);
		} catch (error) {
			// nada a limpar
		}
	}

	function preencherLinha(row, dados) {
		const quantidade = row.querySelector('[name="quantidade"]');
		const observacao = row.querySelector('[name="observacao"]');
		if (quantidade && dados.quantidade) quantidade.value = dados.quantidade;
		if (observacao && dados.observacao) observacao.value = dados.observacao;
		// Item que saiu do catálogo (ou de outra área) não é restaurado.
		if (dados.item_catalogo && dados.item_catalogo in precos) {
			definirSelect(row.querySelector(".select"), dados.item_catalogo);
		}
	}

	function iniciar() {
		const rascunho = itemNovo ? lerRascunho() : null;
		limparRascunho();

		const linhas = (rascunho && rascunho.itens) || [];
		const novas = (linhas.length ? linhas : [{}]).map(function () {
			return adicionarItem();
		});

		// Espera os selects das linhas novas terminarem de inicializar.
		window.setTimeout(function () {
			if (rascunho) {
				definirSelect(document.getElementById("compras-ramo"), rascunho.ramo);
				const justificativa = form.querySelector('[name="justificativa"]');
				if (justificativa && rascunho.justificativa)
					justificativa.value = rascunho.justificativa;
			}
			novas.forEach(function (row, indice) {
				preencherLinha(row, linhas[indice] || {});
			});

			if (itemNovo && itemNovo in precos) {
				const vazia = novas.find(function (row) {
					return !lerCampo(row, "item_catalogo");
				});
				const alvo = vazia || adicionarItem();
				window.setTimeout(function () {
					definirSelect(alvo.querySelector(".select"), itemNovo);
					atualizarTotais();
				}, 0);
			}
			atualizarTotais();
		}, 0);
	}

	// ------------------------------------------------------- cadastro de item

	const dialogCadastro = document.getElementById("dialog-cadastrar-item");

	function campoCadastro(nome) {
		const campo = dialogCadastro?.querySelector(`[name="${nome}"]`);
		return campo ? (campo.value || "").trim() : "";
	}

	document.getElementById("compras-cadastrar-item")?.addEventListener("click", function () {
		dialogCadastro?.showModal();
	});

	dialogCadastro?.addEventListener("click", function (event) {
		const cancelar = event.target.closest("[data-dialog-cancel]");
		if (cancelar) dialogCadastro.close();
	});

	document.getElementById("btn-salvar-cadastro")?.addEventListener("click", function () {
		const nome = campoCadastro("nome");
		if (nome.length < 3) {
			showToast("warning", "Informe um nome com pelo menos 3 caracteres.");
			return;
		}

		const payload = {
			area: area,
			nome: nome,
			valor_unitario: campoCadastro("valor_unitario") || 0,
			codigo: campoCadastro("codigo"),
			descricao: campoCadastro("descricao"),
		};
		if (programaEducativo) {
			payload.tipo = campoCadastro("tipo");
			payload.ramo = campoCadastro("ramo");
		}

		this.disabled = true;
		frappe.call({
			method: "gris.api.compras.endpoints.salvar_item_catalogo",
			args: { payload: JSON.stringify(payload) },
			freeze: true,
			freeze_message: "Cadastrando item...",
			callback: function (r) {
				if (r.exc || !r.message) return;
				salvarRascunho();
				const destino = new URL(window.location.href);
				destino.searchParams.set("area", areaSlug);
				destino.searchParams.set("item_novo", r.message.name);
				window.location.href = destino.toString();
			},
			always: () => {
				this.disabled = false;
			},
		});
	});

	iniciar();
})();
