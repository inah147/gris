/* /manutencao/gestao — dialog de organização de cada solicitação. */
(function () {
	"use strict";

	const dialogEl = document.getElementById("dialog-manutencao");
	const dadosEl = document.getElementById("manutencao-itens");
	if (!dialogEl || !dadosEl) return;

	let itens = [];
	try {
		itens = JSON.parse(dadosEl.textContent || "[]");
	} catch (e) {
		itens = [];
	}
	const porNome = new Map(itens.map((item) => [item.name, item]));

	const campos = {
		meta: dialogEl.querySelector("[data-campo-meta]"),
		status: document.getElementById("editar-status"),
		prioridade: document.getElementById("editar-prioridade"),
		dataPrevista: document.getElementById("editar-data-prevista"),
		responsavel: document.getElementById("editar-responsavel"),
		custo: document.getElementById("editar-custo"),
		observacoes: document.getElementById("editar-observacoes"),
		resumo: document.getElementById("editar-resumo"),
		titulo: document.getElementById("editar-titulo"),
		local: document.getElementById("editar-local"),
		categoria: document.getElementById("editar-categoria"),
		descricao: document.getElementById("editar-descricao"),
	};
	const btnSalvar = document.getElementById("btn-salvar");
	const corrigir = dialogEl.querySelector(".manutencao-dialog__corrigir");

	let atual = null;

	function showToast(category, message) {
		document.dispatchEvent(
			new CustomEvent("basecoat:toast", {
				detail: { config: { category, description: message, duration: 5000 } },
			})
		);
	}

	// Registrar um handler por exc_type faz o request.js pular o msgprint padrão,
	// que no portal renderiza sem estilo.
	const ERROS_TRATADOS_POR_NOS = {
		ValidationError: () => {},
		PermissionError: () => {},
	};

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
		return "Não foi possível salvar.";
	}

	function valorSelect(el) {
		if (!el) return "";
		const hidden = el.querySelector('input[type="hidden"]');
		return ((hidden && hidden.value) || "").trim();
	}

	function hiddenDe(el) {
		return el ? el.querySelector('input[type="hidden"]') : null;
	}

	function abrir(nome) {
		const item = porNome.get(nome);
		if (!item) return;
		atual = item;

		const partes = [item.name, `pedida por ${item.solicitante_nome || "—"}`];
		if (item.data_solicitacao_fmt) partes.push(`em ${item.data_solicitacao_fmt}`);
		if (item.urgencia_informada) partes.push(`urgência: ${item.urgencia_informada}`);
		if (item.data_inicio_fmt) partes.push(`iniciada em ${item.data_inicio_fmt}`);
		if (item.data_conclusao_fmt) partes.push(`concluída em ${item.data_conclusao_fmt}`);
		campos.meta.textContent = partes.join(" · ");

		// Os componentes expõem `.value` no elemento raiz (select, datepicker,
		// currency-input), que atualiza o rótulo visível junto com o hidden.
		campos.status.value = item.status || "";
		campos.prioridade.value = item.prioridade || "";
		campos.categoria.value = item.categoria || "";
		campos.dataPrevista.value = item.data_prevista || "";
		campos.custo.value = item.custo_estimado == null ? "" : item.custo_estimado;
		campos.responsavel.value = item.responsavel_execucao || "";
		campos.observacoes.value = item.observacoes_internas || "";
		campos.resumo.value = item.resumo_execucao || "";
		campos.titulo.value = item.titulo || "";
		campos.local.value = item.local || "";
		campos.descricao.value = item.descricao || "";
		if (corrigir) corrigir.open = false;

		btnSalvar.disabled = false;
		dialogEl.showModal();
	}

	function lerFormulario() {
		const dataHidden = hiddenDe(campos.dataPrevista);
		const custoHidden = hiddenDe(campos.custo);
		return {
			status: valorSelect(campos.status),
			prioridade: valorSelect(campos.prioridade),
			data_prevista: dataHidden ? dataHidden.value : "",
			responsavel_execucao: campos.responsavel.value.trim(),
			custo_estimado: custoHidden ? custoHidden.value : "",
			observacoes_internas: campos.observacoes.value.trim(),
			resumo_execucao: campos.resumo.value.trim(),
			titulo: campos.titulo.value.trim(),
			local: campos.local.value.trim(),
			categoria: valorSelect(campos.categoria),
			descricao: campos.descricao.value.trim(),
		};
	}

	function salvar() {
		if (!atual) return;
		const payload = lerFormulario();
		if (!payload.titulo || !payload.local || !payload.descricao) {
			if (corrigir) corrigir.open = true;
			showToast("error", "Título, local e descrição não podem ficar vazios.");
			return;
		}

		btnSalvar.disabled = true;
		frappe.call({
			method: "gris.api.manutencao.portal.atualizar",
			args: { name: atual.name, payload },
			silent: true,
			error_handlers: ERROS_TRATADOS_POR_NOS,
			callback: (resposta) => {
				const dados = resposta && resposta.message;
				if (!dados || dados.ok === false) {
					btnSalvar.disabled = false;
					showToast("error", "Não foi possível salvar.");
					return;
				}
				dialogEl.close();
				showToast("success", dados.alterou ? "Manutenção atualizada." : "Nada mudou.");
				// Recarrega para a linha cair na posição certa da fila e o resumo
				// por status refletir a mudança.
				if (dados.alterou) window.setTimeout(() => window.location.reload(), 700);
			},
			error: (xhr) => {
				btnSalvar.disabled = false;
				showToast("error", mensagemDoErro(xhr));
			},
		});
	}

	document.addEventListener("click", (event) => {
		const botao = event.target.closest("[data-editar]");
		if (botao) abrir(botao.getAttribute("data-editar"));
	});

	dialogEl.querySelectorAll("[data-dialog-close]").forEach((botao) => {
		botao.addEventListener("click", () => dialogEl.close());
	});

	btnSalvar.addEventListener("click", salvar);
})();
