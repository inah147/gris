frappe.ready(function () {
	const escapeHtml = (value) => {
		const div = document.createElement("div");
		div.textContent = value == null ? "" : String(value);
		return div.innerHTML;
	};

	const showToast = (category, title, description) => {
		document.dispatchEvent(
			new CustomEvent("basecoat:toast", {
				detail: {
					config: {
						category,
						title: escapeHtml(title),
						description: escapeHtml(description || ""),
					},
				},
			})
		);
	};

	const setLoading = (button, loading, label) => {
		if (!button) return;
		if (!button.dataset.originalHtml) {
			button.dataset.originalHtml = button.innerHTML;
		}
		button.disabled = loading;
		button.setAttribute("aria-busy", loading ? "true" : "false");
		button.innerHTML = loading ? label : button.dataset.originalHtml;
	};

	document.querySelectorAll("[data-gerar-link-pagamento]").forEach((button) => {
		button.addEventListener("click", () => gerarLinkPagamento(button));
	});

	function gerarLinkPagamento(button) {
		const associado = button.dataset.gerarLinkPagamento;
		if (!associado) return;

		setLoading(button, true, "Gerando link...");
		frappe.call({
			method: "gris.api.financeiro.cobranca_contribuicao.gerar_cobranca_responsavel",
			args: {
				associado: associado,
				meses: button.dataset.meses || undefined,
			},
			callback: function (r) {
				const link = r.message && r.message.success ? r.message.cobranca.link_pagamento : null;
				if (link) {
					showToast(
						"success",
						"Link gerado",
						"Abrindo a página de pagamento em uma nova aba."
					);
					window.open(link, "_blank", "noopener,noreferrer");
					window.setTimeout(() => window.location.reload(), 1200);
				}
			},
			error: function () {
				showToast(
					"error",
					"Não foi possível gerar o link",
					"Tente novamente em instantes ou fale com a tesouraria do grupo."
				);
			},
			always: function () {
				setLoading(button, false, "Gerando link...");
			},
		});
	}
});
