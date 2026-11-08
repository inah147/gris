/* /manutencao/solicitar — formulário de nova solicitação de manutenção. */
(function () {
	"use strict";

	const form = document.getElementById("manutencao-form");
	if (!form) return;

	const inputTitulo = document.getElementById("manutencao-titulo");
	const inputLocal = document.getElementById("manutencao-local");
	const selectCategoria = document.getElementById("manutencao-categoria");
	const inputDescricao = document.getElementById("manutencao-descricao");
	const submitBtn = document.getElementById("manutencao-submit");

	// Toaster do design system: no portal, frappe.msgprint e o modal do Desk
	// renderizam sem estilo.
	function showToast(category, message) {
		document.dispatchEvent(
			new CustomEvent("basecoat:toast", {
				detail: { config: { category, description: message, duration: 5000 } },
			})
		);
	}

	// Registrar um handler por exc_type faz o request.js pular o msgprint padrão.
	const ERROS_TRATADOS_POR_NOS = {
		ValidationError: () => {},
		PermissionError: () => {},
	};

	/** Mensagem legível da falha: o request.js ora passa o corpo já parseado,
	 *  ora o próprio xhr. */
	function mensagemDoErro(resposta) {
		const corpo = (resposta && resposta.responseJSON) || resposta || {};
		try {
			const mensagens = JSON.parse(corpo._server_messages || "[]");
			const primeira = mensagens.length ? JSON.parse(mensagens[0]) : null;
			if (primeira && primeira.message) return primeira.message;
		} catch (e) {
			/* resposta sem _server_messages utilizável */
		}
		if (corpo.exception)
			return String(corpo.exception).split(": ").slice(1).join(": ") || corpo.exception;
		return "Não foi possível enviar a solicitação.";
	}

	function valorSelect(el) {
		if (!el) return "";
		const hidden = el.querySelector('input[type="hidden"]');
		return ((hidden && hidden.value) || "").trim();
	}

	function urgenciaEscolhida() {
		const marcado = form.querySelector('input[name="urgencia_informada"]:checked');
		return marcado ? marcado.value : "";
	}

	function validar() {
		if (!(inputTitulo.value || "").trim())
			return "Conte em poucas palavras o que precisa ser feito.";
		if (!(inputLocal.value || "").trim()) return "Informe onde fica o problema.";
		if (!valorSelect(selectCategoria)) return "Escolha a categoria da manutenção.";
		if (!urgenciaEscolhida()) return "Escolha a urgência.";
		if (!(inputDescricao.value || "").trim()) return "Descreva o problema.";
		return "";
	}

	function enviar(event) {
		event.preventDefault();

		const erro = validar();
		if (erro) {
			showToast("error", erro);
			return;
		}

		submitBtn.disabled = true;

		frappe.call({
			method: "gris.api.manutencao.portal.solicitar",
			args: {
				payload: {
					titulo: inputTitulo.value.trim(),
					local: inputLocal.value.trim(),
					categoria: valorSelect(selectCategoria),
					urgencia_informada: urgenciaEscolhida(),
					descricao: inputDescricao.value.trim(),
				},
			},
			silent: true,
			error_handlers: ERROS_TRATADOS_POR_NOS,
			callback: (resposta) => {
				const dados = resposta && resposta.message;
				if (!dados || dados.ok === false) {
					submitBtn.disabled = false;
					showToast("error", (dados && dados.error) || "Não foi possível enviar.");
					return;
				}
				showToast("success", `Solicitação ${dados.name} enviada. Obrigado!`);
				window.setTimeout(() => {
					window.location.href = "/manutencao/acompanhamento?minhas=1";
				}, 1200);
			},
			error: (xhr) => {
				submitBtn.disabled = false;
				showToast("error", mensagemDoErro(xhr));
			},
		});
	}

	form.addEventListener("submit", enviar);
})();
