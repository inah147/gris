(function () {
	"use strict";

	const POLL_INTERVAL_MS = 5000;
	const MAX_ATTEMPTS = 60; // ~5 min

	const root = document.querySelector(".cp-page");
	if (!root) return;
	const token = root.dataset.token || "";

	function mostrarErro(texto) {
		const caixa = document.getElementById("cp-erro");
		if (!caixa) return;
		caixa.textContent = texto;
		caixa.hidden = !texto;
	}

	function csrf() {
		return (window.frappe && window.frappe.csrf_token) || "";
	}

	async function chamar(metodo, corpo) {
		const resposta = await fetch(
			"/api/method/gris.api.financeiro.contribuicao_publica." + metodo,
			{
				method: "POST",
				headers: {
					"Content-Type": "application/json",
					"X-Frappe-CSRF-Token": csrf(),
					"X-Requested-With": "XMLHttpRequest",
				},
				credentials: "same-origin",
				body: JSON.stringify(corpo),
			}
		);
		return resposta;
	}

	const checks = Array.from(document.querySelectorAll(".cp-mes__check"));
	const botaoPagar = document.getElementById("cp-pagar");
	const totalEl = document.getElementById("cp-total");

	function brl(valor) {
		return valor.toLocaleString("pt-BR", { style: "currency", currency: "BRL" });
	}

	function selecionadas() {
		return checks.filter((c) => c.checked);
	}

	function atualizarTotal() {
		const marcadas = selecionadas();
		const total = marcadas.reduce((soma, c) => soma + Number(c.dataset.valor || 0), 0);
		if (totalEl) totalEl.textContent = brl(total);
		if (botaoPagar) botaoPagar.disabled = marcadas.length === 0;
	}

	checks.forEach((c) => c.addEventListener("change", atualizarTotal));

	async function pagar(evento) {
		const botao = evento.currentTarget;
		mostrarErro("");
		const competencias = selecionadas().map((c) => c.value);
		if (!competencias.length) {
			mostrarErro("Selecione ao menos um mês para pagar.");
			return;
		}
		botao.disabled = true;
		try {
			const resposta = await chamar("iniciar_pagamento", {
				token: token,
				competencias: competencias,
			});
			if (resposta.status === 429) {
				mostrarErro("Muitas tentativas. Aguarde um minuto e tente de novo.");
				return;
			}
			const dados = await resposta.json();
			const link = dados && dados.message && dados.message.link_pagamento;
			if (!resposta.ok || !link) {
				mostrarErro(
					"Não foi possível gerar o link de pagamento agora. Tente novamente em instantes."
				);
				return;
			}
			window.location.assign(link);
		} catch (erro) {
			mostrarErro(
				"Não foi possível gerar o link de pagamento agora. Tente novamente em instantes."
			);
		} finally {
			atualizarTotal();
		}
	}

	if (botaoPagar) botaoPagar.addEventListener("click", pagar);

	// Ao voltar da InfinitePay a página confere o status até a baixa chegar.
	const params = new URLSearchParams(window.location.search);
	const voltouDoPagamento = ["order_nsu", "transaction_nsu", "slug", "capture_method"].some(
		(chave) => params.has(chave)
	);
	if (!voltouDoPagamento || root.dataset.estado === "pago") return;

	const aviso = document.getElementById("cp-confirmando");
	if (aviso) aviso.hidden = false;
	let tentativas = 0;

	async function conferir() {
		tentativas += 1;
		try {
			const url =
				"/api/method/gris.api.financeiro.contribuicao_publica.get_status?token=" +
				encodeURIComponent(token);
			const resposta = await fetch(url, {
				headers: { "X-Requested-With": "XMLHttpRequest" },
				credentials: "same-origin",
			});
			if (resposta.ok) {
				const dados = await resposta.json();
				if (dados && dados.message && dados.message.estado === "pago") {
					window.location.replace(window.location.pathname);
					return;
				}
			}
		} catch (erro) {
			// Segue tentando até o limite.
		}
		if (tentativas < MAX_ATTEMPTS) {
			setTimeout(conferir, POLL_INTERVAL_MS);
		} else if (aviso) {
			aviso.textContent =
				"O pagamento ainda não foi confirmado. Pode fechar a página: avisaremos assim que chegar.";
		}
	}
	conferir();
})();
