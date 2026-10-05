// Copyright (c) 2026, Grupo Escoteiro Professora Inah de Mello - 47/SP and contributors
// For license information, please see license.txt

// Peças compartilhadas pelas páginas "Monitor de Jobs" e "Execuções de Jobs":
// estilos, paginador, cronômetro das execuções ativas e o fluxo de "Parar".
// Carregado sob demanda (frappe.require) depois de job_log_timeline.js.

frappe.provide("gris.job_monitor");

gris.job_monitor.OPCOES_DE_LIMITE = [10, 25, 50, 100];

gris.job_monitor.atualizar_decorrido = function (raiz) {
	$(raiz)
		.find(".gris-monitor-decorrido")
		.each((_indice, elemento) => {
			const inicio = $(elemento).data("inicio");
			const segundos = moment().diff(
				frappe.datetime.convert_to_user_tz(inicio, false),
				"seconds"
			);
			$(elemento).text(gris.job_logs.formatar_duracao(Math.max(segundos, 0)));
		});
};

gris.job_monitor.html_decorrido = function (inicio) {
	return `<span class="gris-monitor-decorrido"
		data-inicio="${gris.job_logs.escapar(inicio)}"></span>`;
};

gris.job_monitor.html_botao_parar = function (execucao) {
	return `<button class="btn btn-xs btn-danger gris-monitor-parar"
		data-name="${gris.job_logs.escapar(execucao.name)}"
		data-job="${gris.job_logs.escapar(execucao.job)}">${__("Parar")}</button>`;
};

// Liga os botões "Parar" de uma área. `depois` roda quando a parada termina.
gris.job_monitor.ligar_botoes_parar = function (area, depois) {
	area.find(".gris-monitor-parar")
		.off("click")
		.on("click", (evento) => {
			evento.stopPropagation();
			const botao = $(evento.currentTarget);
			gris.job_monitor.parar_execucao(botao.data("name"), botao.data("job"), depois);
		});
};

gris.job_monitor.parar_execucao = function (name, job, depois) {
	frappe.confirm(
		__("Parar a execução de <b>{0}</b>? O que já foi processado não é desfeito.", [
			frappe.utils.escape_html(job || name),
		]),
		() => {
			frappe
				.call({
					method: "gris.api.monitoramento_jobs.parar_execucao",
					args: { name },
					freeze: true,
					freeze_message: __("Parando…"),
				})
				.then((resposta) => {
					const dados = resposta.message || {};
					frappe.show_alert({
						message: dados.mensagem || __("Execução interrompida."),
						indicator: dados.success ? "green" : "orange",
					});
					if (depois) {
						depois(dados);
					}
				});
		}
	);
};

// Paginador: "11–20 de 37", tamanho da página e Anterior/Próxima.
// `estado` = { total, inicio, limite }; `ao_mudar({ inicio, limite })` recarrega os dados.
gris.job_monitor.montar_paginador = function (area, estado, ao_mudar) {
	const total = estado.total || 0;
	if (!total) {
		area.empty();
		return;
	}

	const limite = estado.limite;
	const inicio = Math.min(estado.inicio, Math.max(total - 1, 0));
	const fim = Math.min(inicio + limite, total);
	const pagina = Math.floor(inicio / limite) + 1;
	const paginas = Math.ceil(total / limite);

	const opcoes = gris.job_monitor.OPCOES_DE_LIMITE.map(
		(valor) =>
			`<option value="${valor}" ${valor === limite ? "selected" : ""}>${valor}</option>`
	).join("");

	area.html(`
		<div class="gris-monitor-paginacao">
			<span class="text-muted small">
				${inicio + 1}–${fim} ${__("de")} ${total}
			</span>
			<div class="gris-monitor-paginacao-controles">
				<label class="text-muted small">
					${__("Por página")}
					<select class="gris-monitor-limite">${opcoes}</select>
				</label>
				<button class="btn btn-xs btn-default gris-monitor-anterior"
					${pagina <= 1 ? "disabled" : ""}>${__("Anterior")}</button>
				<span class="small">${__("Página")} ${pagina} ${__("de")} ${paginas}</span>
				<button class="btn btn-xs btn-default gris-monitor-proxima"
					${pagina >= paginas ? "disabled" : ""}>${__("Próxima")}</button>
			</div>
		</div>
	`);

	area.find(".gris-monitor-limite").on("change", (evento) => {
		ao_mudar({ inicio: 0, limite: cint($(evento.currentTarget).val()) });
	});
	area.find(".gris-monitor-anterior").on("click", () => {
		ao_mudar({ inicio: Math.max(inicio - limite, 0), limite });
	});
	area.find(".gris-monitor-proxima").on("click", () => {
		ao_mudar({ inicio: inicio + limite, limite });
	});
};

gris.job_monitor.garantir_estilos = function () {
	if (document.getElementById("gris-monitor-estilos")) {
		return;
	}

	const estilos = document.createElement("style");
	estilos.id = "gris-monitor-estilos";
	estilos.textContent = `
		.gris-monitor { padding-bottom: 40px; }
		.gris-monitor-cards { display: flex; flex-wrap: wrap; gap: 12px; margin-bottom: 20px; }
		.gris-monitor-card { flex: 1 1 150px; border: 1px solid var(--border-color);
			border-radius: var(--border-radius-md); padding: 12px 14px; background: var(--card-bg); }
		.gris-monitor-card-clicavel { cursor: pointer; }
		.gris-monitor-card-clicavel:hover, .gris-monitor-card-ativo { border-color: var(--primary); }
		.gris-monitor-card-valor { font-size: 24px; font-weight: 600; font-variant-numeric: tabular-nums; }
		.gris-monitor-card-rotulo { font-size: 11px; color: var(--text-muted); text-transform: uppercase;
			letter-spacing: 0.4px; margin-top: 2px; }
		.gris-monitor-rodando-caixa { border: 1px solid var(--border-color); border-left: 4px solid var(--blue-500);
			border-radius: var(--border-radius-md); padding: 12px 14px; background: var(--bg-blue); }
		.gris-monitor-rodando-titulo { display: flex; justify-content: space-between; align-items: center;
			gap: 8px; margin-bottom: 4px; flex-wrap: wrap; }
		.gris-monitor-rodando-item { display: flex; justify-content: space-between; align-items: center;
			gap: 12px; padding: 8px 0; border-top: 1px solid var(--border-color); flex-wrap: wrap; }
		.gris-monitor-rodando-acoes { display: flex; gap: 6px; }
		.gris-monitor-secao-titulo { font-size: 13px; font-weight: 600; margin: 20px 0 8px; }
		.gris-monitor-grafico { height: 240px; }
		.gris-monitor-grafico-wrapper { margin-top: 24px; border: 1px solid var(--border-color);
			border-radius: var(--border-radius-md); padding: 12px; background: var(--card-bg); }
		.gris-monitor-tabela-wrapper { border: 1px solid var(--border-color);
			border-radius: var(--border-radius-md); overflow-x: auto; background: var(--card-bg); }
		.gris-monitor-tabela { margin-bottom: 0; font-size: 12px; }
		.gris-monitor-tabela th { font-size: 11px; color: var(--text-muted); text-transform: uppercase;
			letter-spacing: 0.4px; white-space: nowrap; }
		.gris-monitor-tabela td:not(:first-child):not(.gris-monitor-resumo) { white-space: nowrap; }
		.gris-monitor-tabela tbody tr { cursor: pointer; }
		.gris-monitor-tabela tbody tr:hover { background: var(--fg-hover-color); }
		.gris-monitor-linha-ativa, .gris-monitor-linha-ativa:hover { background: var(--bg-blue); }
		.gris-monitor-job-nome { font-weight: 500; }
		.gris-monitor-job-metodo { font-size: 11px; color: var(--text-muted); font-family: var(--font-stack-mono);
			word-break: break-all; }
		.gris-monitor-vazio { padding: 20px; border: 1px dashed var(--border-color);
			border-radius: var(--border-radius-md); text-align: center; }
		.gris-monitor-paginacao { display: flex; justify-content: space-between; align-items: center;
			gap: 8px 16px; flex-wrap: wrap; padding: 8px 2px 0; }
		.gris-monitor-paginacao-controles { display: flex; align-items: center; gap: 8px; flex-wrap: wrap; }
		.gris-monitor-limite { margin-left: 4px; }
		.gris-monitor-detalhe-topo { display: flex; justify-content: space-between; align-items: flex-start;
			gap: 12px; flex-wrap: wrap; margin-bottom: 12px; }
		.gris-monitor-detalhe-titulo { font-weight: 600; }
		.gris-monitor-detalhe-acoes { display: flex; gap: 6px; align-items: center; flex-wrap: wrap; }
	`;
	document.head.appendChild(estilos);
};
