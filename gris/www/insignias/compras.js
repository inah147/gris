(function () {
	const raiz = document.querySelector(".insignias-compras");
	if (!raiz) return;

	const dialogCompra = document.getElementById("dialog-compra");
	const dialogRecebimento = document.getElementById("dialog-recebimento");

	let pedidoSelecionado = null;

	function showToast(category, message) {
		document.dispatchEvent(
			new CustomEvent("basecoat:toast", {
				detail: { config: { category, title: message, duration: 3500 } },
			})
		);
	}

	function hoje() {
		const agora = new Date();
		const mes = String(agora.getMonth() + 1).padStart(2, "0");
		const dia = String(agora.getDate()).padStart(2, "0");
		return `${agora.getFullYear()}-${mes}-${dia}`;
	}

	function lerValor(dialog, nome) {
		const campo = dialog.querySelector(`[name="${nome}"]`);
		return campo ? (campo.value || "").trim() : "";
	}

	// Datepicker e currency-input expõem `value` no elemento raiz; escrever no hidden
	// input direto não atualizaria o rótulo visível do componente.
	function definirValorComponente(id, valor) {
		const root = document.getElementById(id);
		if (root) root.value = valor;
	}

	function limparCampos(dialog, nomes) {
		nomes.forEach(function (nome) {
			const campo = dialog.querySelector(`[name="${nome}"]`);
			if (campo) campo.value = "";
		});
	}

	function formatarMoeda(valor) {
		return Number(valor || 0).toLocaleString("pt-BR", { style: "currency", currency: "BRL" });
	}

	raiz.addEventListener("click", function (event) {
		const cancelar = event.target.closest("[data-dialog-cancel]");
		if (cancelar) {
			document.getElementById(cancelar.dataset.dialogCancel)?.close();
			return;
		}

		const botao = event.target.closest("[data-acao]");
		if (!botao) return;

		pedidoSelecionado = botao.dataset.nome;

		if (botao.dataset.acao === "comprar") {
			document.getElementById("compra-pedido").textContent = pedidoSelecionado;
			document.getElementById("compra-estimado").textContent = formatarMoeda(
				botao.dataset.estimado
			);
			limparCampos(dialogCompra, ["fornecedor", "numero_documento", "observacoes_compra"]);
			definirValorComponente("compra-data", hoje());
			// Pré-preenche com o estimado: normalmente é o valor de fato pago.
			definirValorComponente("compra-valor", Number(botao.dataset.estimado || 0));
			dialogCompra.showModal();
			return;
		}

		if (botao.dataset.acao === "receber") {
			document.getElementById("recebimento-pedido").textContent = pedidoSelecionado;
			definirValorComponente("recebimento-data", hoje());
			dialogRecebimento.showModal();
		}
	});

	function enviar(metodo, payload, botao, mensagem) {
		botao.disabled = true;
		frappe.call({
			method: metodo,
			args: { payload: JSON.stringify(payload) },
			freeze: true,
			freeze_message: "Salvando...",
			callback: function (r) {
				if (r.exc || !r.message) return;
				showToast("success", mensagem);
				window.location.reload();
			},
			always: function () {
				botao.disabled = false;
			},
		});
	}

	document.getElementById("btn-confirmar-compra")?.addEventListener("click", function () {
		if (!pedidoSelecionado) return;

		const dataCompra = lerValor(dialogCompra, "data_compra");
		if (!dataCompra) {
			showToast("warning", "Informe a data da compra.");
			return;
		}

		const valorPago = lerValor(dialogCompra, "valor_pago");
		if (!valorPago || Number(valorPago) <= 0) {
			showToast("warning", "Informe o valor pago.");
			return;
		}

		enviar(
			"gris.api.insignias.endpoints.registrar_compra",
			{
				name: pedidoSelecionado,
				data_compra: dataCompra,
				valor_pago: valorPago,
				fornecedor: lerValor(dialogCompra, "fornecedor"),
				numero_documento: lerValor(dialogCompra, "numero_documento"),
				observacoes_compra: lerValor(dialogCompra, "observacoes_compra"),
			},
			this,
			"Compra registrada."
		);
	});

	document.getElementById("btn-confirmar-recebimento")?.addEventListener("click", function () {
		if (!pedidoSelecionado) return;

		const dataRecebimento = lerValor(dialogRecebimento, "data_recebimento");
		if (!dataRecebimento) {
			showToast("warning", "Informe a data de recebimento.");
			return;
		}

		enviar(
			"gris.api.insignias.endpoints.registrar_recebimento",
			{ name: pedidoSelecionado, data_recebimento: dataRecebimento },
			this,
			"Recebimento registrado."
		);
	});
})();
