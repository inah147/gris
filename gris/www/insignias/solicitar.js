(function () {
	const form = document.getElementById("insignias-form");
	if (!form) return;

	const lista = document.getElementById("insignias-itens");
	const template = document.getElementById("insignias-item-template");
	const btnAdd = document.getElementById("insignias-add-item");
	const submitBtn = document.getElementById("insignias-submit");
	const totalEl = document.getElementById("insignias-total");

	let precos = {};
	try {
		precos = JSON.parse(document.getElementById("insignias-precos").textContent) || {};
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
			const insignia = lerCampo(row, "insignia");
			const quantidade = lerQuantidade(row);
			const subtotal = insignia ? (precos[insignia] || 0) * quantidade : 0;
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
	}

	btnAdd.addEventListener("click", adicionarItem);

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
			const insignia = lerCampo(row, "insignia");
			if (!insignia) {
				linhaVazia = true;
				return;
			}
			const quantidade = lerQuantidade(row);
			if (!quantidade) {
				quantidadeInvalida = true;
				return;
			}
			itens.push({
				insignia: insignia,
				quantidade: quantidade,
				beneficiario: lerCampo(row, "beneficiario"),
				observacao: lerCampo(row, "observacao"),
			});
		});

		return { itens: itens, linhaVazia: linhaVazia, quantidadeInvalida: quantidadeInvalida };
	}

	form.addEventListener("submit", function (event) {
		event.preventDefault();
		if (submitBtn.disabled) return;

		const ramo = (form.querySelector('[name="ramo"]')?.value || "").trim();
		if (!ramo) {
			showToast("warning", "Selecione o ramo ou seção do pedido.");
			return;
		}

		const coleta = coletarItens();
		if (coleta.linhaVazia) {
			showToast("warning", "Escolha a insígnia de todas as linhas ou remova as vazias.");
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
			ramo: ramo,
			justificativa: (form.querySelector('[name="justificativa"]')?.value || "").trim(),
			itens: coleta.itens,
		};

		submitBtn.disabled = true;

		frappe.call({
			method: "gris.api.insignias.endpoints.criar_solicitacao",
			args: { payload: JSON.stringify(payload) },
			freeze: true,
			freeze_message: "Enviando solicitação...",
			callback: function (r) {
				if (r.exc || !r.message) return;
				showToast("success", "Solicitação enviada com sucesso.");
				window.location.href = r.message.redirect || "/insignias/minhas_solicitacoes";
			},
			always: function () {
				submitBtn.disabled = false;
			},
		});
	});

	adicionarItem();
})();
