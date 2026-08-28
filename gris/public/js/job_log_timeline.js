// Copyright (c) 2026, Grupo Escoteiro Professora Inah de Mello - 47/SP and contributors
// For license information, please see license.txt

// Renderizador compartilhado da linha do tempo de execucao de jobs.
// Carregado sob demanda (frappe.require) pelo formulario do DocType
// "Log de Execucao de Job" e pela pagina "Monitor de Jobs".

frappe.provide("gris.job_logs");

gris.job_logs.COR_POR_NIVEL = {
	DEBUG: "gray",
	INFO: "blue",
	AVISO: "orange",
	ERRO: "red",
};

gris.job_logs.COR_POR_STATUS = {
	"Em Execucao": "blue",
	Sucesso: "green",
	"Sucesso com Avisos": "orange",
	"Concluido com Erros": "orange",
	Erro: "red",
};

gris.job_logs.ROTULO_POR_STATUS = {
	"Em Execucao": __("Em execução"),
	Sucesso: __("Sucesso"),
	"Sucesso com Avisos": __("Sucesso com avisos"),
	"Concluido com Erros": __("Concluído com erros"),
	Erro: __("Erro"),
};

gris.job_logs.cor_status = function (status) {
	return gris.job_logs.COR_POR_STATUS[status] || "gray";
};

gris.job_logs.rotulo_status = function (status) {
	return gris.job_logs.ROTULO_POR_STATUS[status] || status || "";
};

gris.job_logs.escapar = function (valor) {
	return frappe.utils.escape_html(valor === null || valor === undefined ? "" : String(valor));
};

gris.job_logs.formatar_duracao = function (segundos) {
	if (segundos === null || segundos === undefined || isNaN(segundos)) {
		return "—";
	}
	if (segundos < 1) {
		return `${Math.round(segundos * 1000)} ms`;
	}
	if (segundos < 60) {
		return `${flt(segundos, 2)} s`;
	}
	const minutos = Math.floor(segundos / 60);
	const resto = Math.round(segundos % 60);
	return `${minutos} min ${resto} s`;
};

gris.job_logs.badge_status = function (status) {
	return `<span class="indicator-pill ${gris.job_logs.cor_status(status)}">
		${gris.job_logs.escapar(gris.job_logs.rotulo_status(status))}
	</span>`;
};

gris.job_logs.html_metricas = function (metricas) {
	const chaves = Object.keys(metricas || {});
	if (!chaves.length) {
		return "";
	}

	const itens = chaves
		.map((chave) => {
			const rotulo = gris.job_logs.escapar(chave.replace(/_/g, " "));
			const valor = gris.job_logs.escapar(metricas[chave]);
			return `<div class="gris-job-metrica">
				<div class="gris-job-metrica-valor">${valor}</div>
				<div class="gris-job-metrica-rotulo">${rotulo}</div>
			</div>`;
		})
		.join("");

	return `<div class="gris-job-metricas">${itens}</div>`;
};

gris.job_logs.html_eventos = function (eventos) {
	if (!eventos || !eventos.length) {
		return `<div class="text-muted">${__(
			"Este job não registrou nenhum detalhe nesta execução."
		)}</div>`;
	}

	const linhas = eventos
		.map((evento) => {
			const nivel = evento.nivel || "INFO";
			const cor = gris.job_logs.COR_POR_NIVEL[nivel] || "gray";
			const horario = evento.horario ? evento.horario.split(" ")[1] || evento.horario : "";
			let contexto = "";
			if (evento.contexto && Object.keys(evento.contexto).length) {
				contexto = `<div class="gris-job-evento-contexto">${gris.job_logs.escapar(
					JSON.stringify(evento.contexto)
				)}</div>`;
			}

			return `<div class="gris-job-evento gris-job-evento-${cor}">
				<div class="gris-job-evento-horario">${gris.job_logs.escapar(horario)}</div>
				<div class="gris-job-evento-nivel"><span class="indicator-pill ${cor}">${gris.job_logs.escapar(
				nivel
			)}</span></div>
				<div class="gris-job-evento-mensagem">${gris.job_logs.escapar(evento.mensagem)}${contexto}</div>
			</div>`;
		})
		.join("");

	return `<div class="gris-job-timeline">${linhas}</div>`;
};

gris.job_logs.html_erro = function (erro) {
	if (!erro) {
		return "";
	}

	return `<div class="gris-job-erro">
		<div class="gris-job-erro-titulo">${__("Erro registrado")}</div>
		<pre>${gris.job_logs.escapar(erro)}</pre>
	</div>`;
};

// Monta o bloco completo (métricas + linha do tempo + erro) dentro de um wrapper jQuery.
gris.job_logs.render_detalhe = function (wrapper, execucao) {
	gris.job_logs.garantir_estilos();

	const partes = [
		gris.job_logs.html_metricas(execucao.metricas),
		gris.job_logs.html_eventos(execucao.eventos),
		gris.job_logs.html_erro(execucao.erro),
	];

	$(wrapper).html(`<div class="gris-job-detalhe">${partes.filter(Boolean).join("")}</div>`);
};

gris.job_logs.garantir_estilos = function () {
	if (document.getElementById("gris-job-logs-estilos")) {
		return;
	}

	const estilos = document.createElement("style");
	estilos.id = "gris-job-logs-estilos";
	estilos.textContent = `
		.gris-job-metricas { display: flex; flex-wrap: wrap; gap: 8px; margin-bottom: 12px; }
		.gris-job-metrica { border: 1px solid var(--border-color); border-radius: var(--border-radius-md);
			padding: 8px 12px; min-width: 96px; background: var(--card-bg); }
		.gris-job-metrica-valor { font-size: 18px; font-weight: 600; font-variant-numeric: tabular-nums; }
		.gris-job-metrica-rotulo { font-size: 11px; color: var(--text-muted); text-transform: uppercase;
			letter-spacing: 0.4px; }
		.gris-job-timeline { border: 1px solid var(--border-color); border-radius: var(--border-radius-md);
			overflow: hidden; }
		.gris-job-evento { display: grid; grid-template-columns: 72px 84px 1fr; gap: 8px; padding: 6px 10px;
			border-bottom: 1px solid var(--border-color); font-size: 12px; align-items: baseline; }
		.gris-job-evento:last-child { border-bottom: none; }
		.gris-job-evento-red { background: var(--bg-red); }
		.gris-job-evento-orange { background: var(--bg-orange); }
		.gris-job-evento-horario { color: var(--text-muted); font-variant-numeric: tabular-nums; }
		.gris-job-evento-mensagem { white-space: pre-wrap; word-break: break-word; }
		.gris-job-evento-contexto { color: var(--text-muted); font-family: var(--font-stack-mono);
			font-size: 11px; margin-top: 2px; word-break: break-all; }
		.gris-job-erro { margin-top: 12px; }
		.gris-job-erro-titulo { font-weight: 600; margin-bottom: 4px; color: var(--red-600); }
		.gris-job-erro pre { background: var(--bg-red); border: 1px solid var(--border-color);
			border-radius: var(--border-radius-md); padding: 10px; font-size: 11px; max-height: 320px;
			overflow: auto; white-space: pre-wrap; }
		@media (max-width: 640px) {
			.gris-job-evento { grid-template-columns: 1fr; gap: 2px; }
		}
	`;
	document.head.appendChild(estilos);
};
