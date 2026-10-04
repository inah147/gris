(function () {
	"use strict";

	const root = document.querySelector(".mc-page");
	if (!root || root.dataset.estado !== "verificar") return;

	const token = root.dataset.token || "";
	const API = "/api/method/gris.api.festas.convite_publico.";
	const MENSAGEM_GENERICA = "Não foi possível abrir o convite. Confira os dígitos.";
	const MENSAGEM_LIMITE = "Muitas tentativas. Aguarde alguns minutos e tente de novo.";
	const MENSAGEM_REDE = "Sem conexão com o servidor. Confira a internet e tente de novo.";

	const form = document.getElementById("mc-verificacao");
	const campo = document.getElementById("mc-digitos");
	const botaoAbrir = document.getElementById("mc-abrir");
	const botaoBaixar = document.getElementById("mc-baixar");
	const secaoConvite = document.getElementById("mc-convite");
	// Os dígitos conferidos ficam só em memória, para o "Baixar PDF".
	let digitosConferidos = "";

	function mostrarErro(texto) {
		const caixa = document.getElementById("mc-erro");
		const alvo = document.getElementById("mc-erro-texto");
		if (!caixa || !alvo) return;
		alvo.textContent = texto || "";
		caixa.hidden = !texto;
	}

	function csrf() {
		return (window.frappe && window.frappe.csrf_token) || "";
	}

	// `frappe.call` do portal nunca chama `error`; com fetch dá para tratar 429 e 403.
	function chamar(metodo, corpo) {
		return fetch(API + metodo, {
			method: "POST",
			headers: {
				"Content-Type": "application/json",
				"X-Frappe-CSRF-Token": csrf(),
				"X-Requested-With": "XMLHttpRequest",
			},
			credentials: "same-origin",
			body: JSON.stringify(corpo),
		});
	}

	function mensagemDaFalha(resposta) {
		return resposta && resposta.status === 429 ? MENSAGEM_LIMITE : MENSAGEM_GENERICA;
	}

	function mostrarConvite(dados) {
		document.getElementById("mc-qr").src = "data:image/png;base64," + dados.qr_png_b64;
		document.getElementById("mc-nome").textContent = dados.nome || "";
		document.getElementById("mc-tipo").textContent = dados.tipo_convite || "";
		form.hidden = true;
		secaoConvite.hidden = false;
		secaoConvite.scrollIntoView({ behavior: "smooth", block: "start" });
	}

	async function abrir(evento) {
		evento.preventDefault();
		const digitos = (campo.value || "").replace(/\D/g, "");
		if (digitos.length !== 4) {
			mostrarErro("Digite os 4 últimos números do celular.");
			campo.focus();
			return;
		}
		mostrarErro("");
		botaoAbrir.disabled = true;
		try {
			const resposta = await chamar("abrir_convite", { token: token, digitos: digitos });
			const corpo = resposta.ok ? await resposta.json() : null;
			const dados = corpo && corpo.message;
			if (!dados || !dados.qr_png_b64) {
				mostrarErro(mensagemDaFalha(resposta));
				campo.select();
				return;
			}
			digitosConferidos = digitos;
			mostrarConvite(dados);
		} catch (erro) {
			mostrarErro(MENSAGEM_REDE);
		} finally {
			botaoAbrir.disabled = false;
		}
	}

	function nomeDoArquivo(resposta) {
		const disposicao = resposta.headers.get("Content-Disposition") || "";
		const achado = disposicao.match(/filename="?([^";]+)"?/i);
		return achado ? achado[1] : "convite.pdf";
	}

	async function baixar() {
		botaoBaixar.disabled = true;
		try {
			const resposta = await chamar("baixar_convite_pdf", {
				token: token,
				digitos: digitosConferidos,
			});
			if (!resposta.ok) {
				window.alert(mensagemDaFalha(resposta));
				return;
			}
			const arquivo = await resposta.blob();
			const url = URL.createObjectURL(arquivo);
			const link = document.createElement("a");
			link.href = url;
			link.download = nomeDoArquivo(resposta);
			document.body.appendChild(link);
			link.click();
			link.remove();
			setTimeout(() => URL.revokeObjectURL(url), 10000);
		} catch (erro) {
			window.alert(MENSAGEM_REDE);
		} finally {
			botaoBaixar.disabled = false;
		}
	}

	campo.addEventListener("input", () => {
		campo.value = campo.value.replace(/\D/g, "").slice(0, 4);
	});
	form.addEventListener("submit", abrir);
	botaoBaixar.addEventListener("click", baixar);
})();
