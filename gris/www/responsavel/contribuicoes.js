// Contribuições dos beneficiários, na visão do responsável.
// A página nasce pronta do servidor; aqui fica só a única ação da tela: dizer
// qual responsável da família passa a receber a cobrança de um beneficiário.
(function () {
	"use strict";

	function mostrarAviso(mensagem, indicador) {
		const categorias = { green: "success", red: "error" };
		document.dispatchEvent(
			new CustomEvent("basecoat:toast", {
				detail: {
					config: {
						category: categorias[indicador] || "info",
						title: mensagem,
						duration: 3000,
					},
				},
			})
		);
	}

	// Só o id do responsável escolhido viaja: e-mail e telefone são lidos no
	// servidor, na mesma fonte que montou a lista mostrada na tela.
	function definirDestinatario(botao) {
		const associado = botao.getAttribute("data-associado");
		const destinatario = botao.getAttribute("data-destinatario");
		if (!associado || !destinatario) return;

		const nome = botao.getAttribute("data-nome") || "o responsável escolhido";
		botao.disabled = true;

		frappe
			.call({
				method: "gris.api.financeiro.cobranca_contribuicao.definir_destinatario_da_cobranca",
				args: { associado: associado, destinatario: destinatario },
				freeze: true,
			})
			.then((resposta) => {
				const dados = (resposta && resposta.message) || {};
				if (!dados.ok) {
					botao.disabled = false;
					mostrarAviso("Não foi possível trocar quem recebe a cobrança.", "red");
					return;
				}
				mostrarAviso(`As próximas cobranças vão para ${nome}.`, "green");
				window.setTimeout(() => window.location.reload(), 600);
			})
			.catch(() => {
				botao.disabled = false;
				mostrarAviso("Erro ao trocar quem recebe a cobrança.", "red");
			});
	}

	function init() {
		document.addEventListener("click", (evento) => {
			const alvo = evento.target.closest('[data-acao="definir-destinatario"]');
			if (!alvo) return;
			evento.preventDefault();
			definirDestinatario(alvo);
		});
	}

	if (document.readyState === "loading") {
		document.addEventListener("DOMContentLoaded", init);
	} else {
		init();
	}
})();
