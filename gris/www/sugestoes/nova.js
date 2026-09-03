/* /sugestoes/nova — formulário de nova solicitação. */
(function () {
	"use strict";

	const TIPO_PROBLEMA = "Problema";
	const TIPO_FUNCIONALIDADE = "Nova funcionalidade";

	const form = document.getElementById("sugestoes-form");
	if (!form) return;

	const selectTipo = document.getElementById("sugestoes-tipo");
	const selectModulo = document.getElementById("sugestoes-modulo");
	const inputTitulo = document.getElementById("sugestoes-titulo");
	const inputDescricao = document.getElementById("sugestoes-descricao-input");
	const submitBtn = document.getElementById("sugestoes-submit");
	const checkAvisar = document.getElementById("sugestoes-avisar");
	const hintProblema = form.querySelector("[data-hint-problema]");
	const hintFuncionalidade = form.querySelector("[data-hint-funcionalidade]");

	// Sem telefone no cadastro o campo vem `disabled` do servidor, e prometer o
	// aviso seria mentira. O servidor revalida no `before_insert`.
	const podeAvisar = !!(checkAvisar && !checkAvisar.disabled);

	let editor = null;

	// Toaster do design system: em página de portal não se usa frappe.msgprint
	// nem frappe.show_alert, que são do Desk e renderizam sem estilo.
	function showToast(category, message) {
		document.dispatchEvent(
			new CustomEvent("basecoat:toast", {
				detail: { config: { category, description: message, duration: 5000 } },
			})
		);
	}

	// Registrar um handler por exc_type faz o request.js pular o msgprint padrão
	// (`cleanup` só exibe as mensagens quando `handlers.length === 0`), que numa
	// página de portal renderiza sem estilo.
	const ERROS_TRATADOS_POR_NOS = {
		ValidationError: () => {},
		PermissionError: () => {},
	};

	/** Mensagem legível da falha.
	 *
	 *  O argumento muda conforme o caminho no request.js: o handler de 417 passa
	 *  o corpo da resposta já parseado, enquanto outros passam o próprio xhr.
	 *  Tratar só um dos formatos faz todo erro de validação virar texto genérico.
	 */
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
		if (corpo.status) return `O servidor respondeu ${corpo.status}.`;
		return "Não foi possível enviar a solicitação.";
	}

	function valorSelect(el) {
		if (!el) return "";
		const hidden = el.querySelector('input[type="hidden"]');
		return ((hidden && hidden.value) || "").trim();
	}

	/** "Novo módulo" só existe para funcionalidade — não dá para relatar um bug
	 *  em algo que ainda não foi construído. O servidor revalida. */
	function aplicarRegrasDoTipo() {
		const tipo = valorSelect(selectTipo);

		if (hintProblema) hintProblema.hidden = tipo === TIPO_FUNCIONALIDADE;
		if (hintFuncionalidade) hintFuncionalidade.hidden = tipo !== TIPO_FUNCIONALIDADE;

		if (!selectModulo) return;
		const exclusivas = selectModulo.querySelectorAll('[data-so-funcionalidade="1"]');
		const permitido = tipo === TIPO_FUNCIONALIDADE;

		exclusivas.forEach((opcao) => {
			opcao.hidden = !permitido;
			// Se o módulo já escolhido deixou de ser válido, limpa a seleção em vez
			// de deixar o formulário num estado que o servidor vai recusar.
			if (!permitido && opcao.getAttribute("data-value") === valorSelect(selectModulo)) {
				selectModulo.value = "";
			}
		});
	}

	function textoDoEditor() {
		if (!editor) return "";
		const html = editor.getHTML() || "";
		const tmp = document.createElement("div");
		tmp.innerHTML = html;
		return (tmp.textContent || "").trim();
	}

	function validar() {
		if (!valorSelect(selectTipo)) return "Escolha o que você deseja fazer.";
		if (!valorSelect(selectModulo)) return "Escolha o módulo da solicitação.";
		if (!(inputTitulo.value || "").trim()) return "Informe um título para a solicitação.";
		if (!textoDoEditor()) return "Descreva a solicitação.";
		return "";
	}

	function enviar(event) {
		event.preventDefault();

		const erro = validar();
		if (erro) {
			showToast("error", erro);
			return;
		}

		inputDescricao.value = editor.getHTML();
		submitBtn.disabled = true;

		frappe.call({
			method: "gris.api.sugestoes.portal.submeter_solicitacao",
			args: {
				payload: {
					tipo: valorSelect(selectTipo),
					modulo: valorSelect(selectModulo),
					titulo: (inputTitulo.value || "").trim(),
					descricao: inputDescricao.value,
					avisar_por_whatsapp: podeAvisar && checkAvisar.checked,
				},
			},
			// Sem `silent`, o erro do servidor abre o modal do Desk, que no portal
			// renderiza como caixa branca sem estilo. Mostramos toast no lugar.
			silent: true,
			error_handlers: ERROS_TRATADOS_POR_NOS,
			callback: (resposta) => {
				const dados = resposta && resposta.message;
				if (!dados || dados.ok === false) {
					submitBtn.disabled = false;
					showToast("error", (dados && dados.error) || "Não foi possível enviar.");
					return;
				}
				// Quem não tem o papel de acompanhamento não enxerga o quadro:
				// mandá-lo para lá daria 403 logo depois de um envio bem-sucedido.
				if (dados.pode_acompanhar) {
					showToast("success", "Solicitação enviada. Redirecionando para o quadro...");
					window.setTimeout(() => {
						window.location.href =
							"/sugestoes/acompanhamento?item=" + encodeURIComponent(dados.name);
					}, 900);
					return;
				}

				const promessa = dados.avisar_por_whatsapp
					? " Te avisamos por WhatsApp quando estiver pronta."
					: "";
				showToast(
					"success",
					`Solicitação ${dados.name} enviada. Obrigado! Vamos analisar e trabalhar nela.${promessa}`
				);
				// `form.reset()` devolve o checkbox ao estado do HTML — marcado
				// quando há telefone, desmarcado e desabilitado quando não há.
				form.reset();
				form.querySelectorAll(".select").forEach((el) => {
					el.value = "";
				});
				if (editor) editor.setHTML("");
				aplicarRegrasDoTipo();
				submitBtn.disabled = false;
			},
			error: (xhr) => {
				submitBtn.disabled = false;
				showToast("error", mensagemDoErro(xhr));
			},
		});
	}

	document.addEventListener("change", (event) => {
		if (selectTipo && selectTipo.contains(event.target)) aplicarRegrasDoTipo();
	});
	// O componente de select do Basecoat troca o hidden input sem emitir "change"
	// em todos os navegadores; o clique na opção é o sinal confiável.
	if (selectTipo) {
		selectTipo.addEventListener("click", () => window.setTimeout(aplicarRegrasDoTipo, 0));
	}

	form.addEventListener("submit", enviar);

	function iniciarEditor() {
		if (!window.gris || !window.gris.editor) {
			window.setTimeout(iniciarEditor, 50);
			return;
		}
		window.gris.editor
			.create(document.getElementById("sugestoes-descricao-editor"), { height: "320px" })
			.then((instancia) => {
				editor = instancia;
			})
			.catch(() => {
				showToast("error", "Não foi possível carregar o editor de texto.");
			});
	}

	function iniciar() {
		aplicarRegrasDoTipo();
		iniciarEditor();
	}

	// Mesmo guarda do tarefas.js: o Frappe inlina este arquivo no meio do body,
	// antes de o select.js do Basecoat ter inicializado os selects que lemos.
	if (document.readyState === "loading") {
		document.addEventListener("DOMContentLoaded", iniciar);
	} else {
		iniciar();
	}
})();
