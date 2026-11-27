// Envio de assunto geral para a assembleia.
(function () {
	const A = window.grisAssembleias;
	const raiz = document.querySelector(".asm-formulario-publico");
	const botao = document.getElementById("ag-enviar");
	if (!A || !raiz || !botao) return;

	const form = document.getElementById("form-assunto");
	const sucesso = document.getElementById("ag-sucesso");
	const campo = document.getElementById("ag-conteudo");
	const confirmacao = document.getElementById("ag-confirmacao");

	botao.addEventListener("click", async () => {
		if (!campo.value.trim()) {
			A.toast("error", "Escreva o assunto.");
			return;
		}
		if (!confirmacao.checked) {
			A.toast("error", "Marque a confirmação para enviar.");
			return;
		}
		botao.disabled = true;
		try {
			const resposta = await A.chamar("formularios.enviar_assunto_geral", {
				assembleia: raiz.dataset.assembleia,
				conteudo: campo.value,
				confirmacao: 1,
			});
			document.getElementById("ag-resumo").textContent = resposta.conteudo;
			form.hidden = true;
			sucesso.hidden = false;
		} catch (erro) {
			A.toast("error", erro.message);
		} finally {
			botao.disabled = false;
		}
	});

	document.getElementById("ag-outro")?.addEventListener("click", () => {
		campo.value = "";
		confirmacao.checked = false;
		sucesso.hidden = true;
		form.hidden = false;
		campo.focus();
	});
})();
