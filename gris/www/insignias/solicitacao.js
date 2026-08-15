(function () {
	const raiz = document.querySelector(".insignias-detalhe");
	if (!raiz) return;

	const nomeSolicitacao = raiz.dataset.solicitacao || "";
	if (!nomeSolicitacao) return;

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

	raiz.addEventListener("click", function (event) {
		const cancelar = event.target.closest("[data-dialog-cancel]");
		if (cancelar) document.getElementById(cancelar.dataset.dialogCancel)?.close();
	});

	document.getElementById("btn-abrir-entrega")?.addEventListener("click", function () {
		// O datepicker expõe `value` no elemento raiz; escrever no hidden input
		// direto não atualizaria o rótulo visível.
		const campoData = document.getElementById("entrega-data");
		if (campoData) campoData.value = hoje();
		document.getElementById("dialog-entrega")?.showModal();
	});

	document.getElementById("btn-abrir-cancelamento")?.addEventListener("click", function () {
		document.getElementById("dialog-cancelamento")?.showModal();
	});

	document.getElementById("btn-confirmar-entrega")?.addEventListener("click", function () {
		const dialogEntrega = document.getElementById("dialog-entrega");
		const dataEntrega = lerValor(dialogEntrega, "data_entrega");
		if (!dataEntrega) {
			showToast("warning", "Informe a data da entrega.");
			return;
		}

		enviar(
			"gris.api.insignias.endpoints.registrar_entrega",
			{
				name: nomeSolicitacao,
				data_entrega: dataEntrega,
				observacoes_entrega: lerValor(dialogEntrega, "observacoes_entrega"),
			},
			this,
			"Entrega confirmada. Pedido concluído."
		);
	});

	document.getElementById("btn-confirmar-cancelamento")?.addEventListener("click", function () {
		const dialogCancelamento = document.getElementById("dialog-cancelamento");
		const motivo = lerValor(dialogCancelamento, "motivo");
		if (!motivo) {
			showToast("warning", "Informe o motivo do cancelamento.");
			return;
		}

		enviar(
			"gris.api.insignias.endpoints.cancelar_solicitacao",
			{ name: nomeSolicitacao, motivo: motivo },
			this,
			"Solicitação cancelada."
		);
	});
})();
