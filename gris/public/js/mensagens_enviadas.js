/*
 * Diálogo "Mensagens enviadas" — histórico do que o GRIS já tentou entregar sobre um jovem.
 *
 * Compartilhado pela ficha de registro (/recepcao/ficha_registro) e pelos cards da visão
 * geral (/recepcao/visao_geral): as duas telas mostram exatamente a mesma lista, e manter
 * duas cópias da renderização era pedir para elas divergirem.
 *
 * Marcação e assets vêm de templates/includes/mensagens_enviadas_dialog.html; a página só
 * chama `window.grisMensagensEnviadas.abrir(name, { aoFechar })`.
 *
 * `aoFechar` existe por causa da visão geral: lá o diálogo abre por cima do modal do card,
 * e showModal() põe o novo na top layer e torna o resto inerte — o modal de origem precisa
 * fechar antes e reabrir depois.
 */
(function () {
	"use strict";

	const ESTADO_POR_STATUS = {
		Enviada: { icone: "circle-check", classe: "is-enviada" },
		Falhou: { icone: "circle-alert", classe: "is-falhou" },
	};

	let aoFecharPendente = null;

	function escaparHtml(valor) {
		return String(valor == null ? "" : valor)
			.replace(/&/g, "&amp;")
			.replace(/</g, "&lt;")
			.replace(/>/g, "&gt;")
			.replace(/"/g, "&quot;")
			.replace(/'/g, "&#39;");
	}

	function iconeSvg(nome) {
		return (
			'<svg class="ds-lucide ds-lucide--sm" viewBox="0 0 24 24" aria-hidden="true">' +
			'<use href="/assets/gris/design_system/icons/lucide/sprite.svg#' +
			nome +
			'" /></svg>'
		);
	}

	function linhaDeMensagem(msg) {
		const estado = ESTADO_POR_STATUS[msg.status] || ESTADO_POR_STATUS.Falhou;
		const partes = [];

		partes.push(
			'<li class="ficha-mensagem ' +
				estado.classe +
				'"><div class="ficha-mensagem__topo">' +
				'<span class="ficha-mensagem__status">' +
				iconeSvg(estado.icone) +
				escaparHtml(msg.status) +
				"</span>" +
				'<span class="ficha-mensagem__quando">' +
				escaparHtml(msg.data) +
				" às " +
				escaparHtml(msg.hora) +
				"</span></div>"
		);

		if (msg.assunto) {
			partes.push('<p class="ficha-mensagem__assunto">' + escaparHtml(msg.assunto) + "</p>");
		}

		// Quando a Evolution API não responde, o nome do grupo cai no próprio JID
		// (ver _resolver_nomes_de_grupo): repetir os dois só polui a linha.
		const nome = msg.destinatario_nome || "Não informado";
		const numero = msg.destinatario_numero || "";
		const numeroHtml =
			numero && numero !== nome
				? '<span class="ficha-mensagem__numero">' + escaparHtml(numero) + "</span>"
				: "";

		partes.push(
			'<p class="ficha-mensagem__destinatario">' +
				'<span class="ficha-mensagem__nome">' +
				escaparHtml(nome) +
				"</span>" +
				'<span class="ficha-mensagem__tipo">' +
				escaparHtml(msg.destinatario_tipo) +
				"</span>" +
				numeroHtml +
				"</p>"
		);

		partes.push(
			'<pre class="ficha-mensagem__conteudo">' + escaparHtml(msg.conteudo) + "</pre>"
		);

		if (msg.status === "Falhou" && msg.erro) {
			partes.push('<p class="ficha-mensagem__erro">' + escaparHtml(msg.erro) + "</p>");
		}

		partes.push("</li>");
		return partes.join("");
	}

	function abrir(novoAssociadoName, opcoes) {
		const dialogEl = document.getElementById("mensagens-modal");
		if (!dialogEl || !novoAssociadoName) return;

		const lista = document.getElementById("mensagens-lista");
		const carregando = document.getElementById("mensagens-loading");
		const vazio = document.getElementById("mensagens-vazio");
		const erro = document.getElementById("mensagens-erro");

		aoFecharPendente = (opcoes && opcoes.aoFechar) || null;

		carregando.hidden = false;
		lista.hidden = true;
		vazio.hidden = true;
		erro.hidden = true;
		lista.innerHTML = "";

		if (typeof dialogEl.showModal === "function" && !dialogEl.open) dialogEl.showModal();

		frappe.call({
			method: "gris.www.recepcao.ficha_registro.listar_mensagens_enviadas",
			args: { novo_associado_name: novoAssociadoName },
			callback: function (r) {
				carregando.hidden = true;
				const mensagens = (r && r.message) || [];
				if (!mensagens.length) {
					vazio.hidden = false;
					return;
				}
				lista.innerHTML = mensagens.map(linhaDeMensagem).join("");
				lista.hidden = false;
			},
			error: function () {
				carregando.hidden = true;
				erro.textContent = "Não foi possível carregar as mensagens.";
				erro.hidden = false;
			},
		});
	}

	document.addEventListener("DOMContentLoaded", function () {
		const dialogEl = document.getElementById("mensagens-modal");
		if (!dialogEl) return;

		dialogEl.addEventListener("close", function () {
			const aoFechar = aoFecharPendente;
			aoFecharPendente = null;
			if (aoFechar) aoFechar();
		});
	});

	window.grisMensagensEnviadas = { abrir: abrir };
})();
