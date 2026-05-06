frappe.ready(() => {
	const modalObservacao = document.getElementById("modal-observacao");
	const modalObservacaoPergunta = document.getElementById("modal-observacao-pergunta");
	const modalObservacaoMensagem = document.getElementById("modal-observacao-mensagem");

	if (!modalObservacao) {
		return;
	}

	document.querySelectorAll("[data-obs-trigger]").forEach((btn) => {
		btn.addEventListener("click", () => {
			const question = btn.dataset.question || "";
			const observation = btn.dataset.observation || "";

			modalObservacaoPergunta.textContent = question;
			modalObservacaoMensagem.innerHTML = frappe.utils
				.escape_html(observation || "Sem observações para esta resposta.")
				.replace(/\n/g, "<br>");

			modalObservacao.showModal();
		});
	});
});
