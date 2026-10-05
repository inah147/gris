// Copyright (c) 2026, Grupo Escoteiro Professora Inah de Mello - 47/SP and contributors
// For license information, please see license.txt

// Monitor de Jobs: visão geral — quem está rodando agora (com botão Parar), a
// situação de cada job e o gráfico do período. O histórico de execuções fica
// na página "Execuções de Jobs". Dados vêm de gris.api.monitoramento_jobs.

frappe.pages["monitor-de-jobs"].on_page_load = function (wrapper) {
	const page = frappe.ui.make_app_page({
		parent: wrapper,
		title: __("Monitor de Jobs"),
		single_column: true,
	});

	frappe.require(
		[
			"/assets/gris/js/job_log_timeline.js",
			"/assets/gris/js/monitor_de_jobs_comum.js",
			"/assets/gris/vendor/echarts/echarts.min.js",
		],
		() => {
			wrapper.monitor_de_jobs = new MonitorDeJobs(page);
		}
	);
};

frappe.pages["monitor-de-jobs"].on_page_show = function (wrapper) {
	if (wrapper.monitor_de_jobs) {
		wrapper.monitor_de_jobs.carregar();
	}
};

// Paleta Okabe-Ito (segura para daltonismo), conforme a skill gris-echarts-charts.
const CORES_DO_STATUS = {
	Sucesso: "#009E73",
	"Sucesso com Avisos": "#E69F00",
	"Concluido com Erros": "#CC79A7",
	Erro: "#D55E00",
	"Em Execucao": "#0072B2",
};

const ORDEM_DOS_STATUS = [
	"Sucesso",
	"Sucesso com Avisos",
	"Concluido com Erros",
	"Erro",
	"Em Execucao",
];

class MonitorDeJobs {
	constructor(page) {
		this.page = page;
		this.filtros = { dias: 7 };
		this.paginacao = { inicio: 0, limite: 10, total: 0 };
		this.em_execucao = [];
		this.montar_estrutura();
		this.montar_filtros();
		this.montar_acoes();
		this.carregar();
		this.agendar_atualizacao();
	}

	// ------------------------------------------------------------------ layout

	montar_estrutura() {
		gris.job_logs.garantir_estilos();
		gris.job_monitor.garantir_estilos();

		this.corpo = $(`
			<div class="gris-monitor">
				<div class="gris-monitor-cards"></div>
				<div class="gris-monitor-rodando"></div>
				<div class="gris-monitor-secao-titulo">${__("Jobs")}</div>
				<div class="gris-monitor-jobs"></div>
				<div class="gris-monitor-paginador"></div>
				<div class="gris-monitor-grafico-wrapper">
					<div class="gris-monitor-secao-titulo">${__("Execuções por dia")}</div>
					<div class="gris-monitor-grafico"></div>
				</div>
			</div>
		`).appendTo(this.page.main);

		this.area_cards = this.corpo.find(".gris-monitor-cards");
		this.area_rodando = this.corpo.find(".gris-monitor-rodando");
		this.area_grafico = this.corpo.find(".gris-monitor-grafico");
		this.area_jobs = this.corpo.find(".gris-monitor-jobs");
		this.area_paginador = this.corpo.find(".gris-monitor-paginador");
	}

	montar_filtros() {
		this.campo_periodo = this.page.add_select(
			__("Período"),
			[
				{ label: __("Últimas 24 horas"), value: "1" },
				{ label: __("Últimos 7 dias"), value: "7" },
				{ label: __("Últimos 30 dias"), value: "30" },
				{ label: __("Últimos 90 dias"), value: "90" },
			],
			"7"
		);
		this.campo_periodo.val("7").on("change", () => {
			this.filtros.dias = cint(this.campo_periodo.val()) || 7;
			this.paginacao.inicio = 0;
			this.carregar();
		});
	}

	montar_acoes() {
		this.page.set_primary_action(__("Atualizar"), () => this.carregar(), "refresh");

		this.page.add_menu_item(__("Ver todas as execuções"), () => this.ir_para_execucoes());
		this.page.add_menu_item(__("Ver registros brutos"), () => {
			frappe.set_route("List", "Log de Execucao de Job");
		});
		this.page.add_menu_item(__("Configurar agendamentos"), () => {
			frappe.set_route("List", "Scheduled Job Type");
		});
		this.page.add_menu_item(__("Retenção dos logs"), () => {
			frappe.set_route("Form", "Log Settings");
		});
	}

	// A página de execuções lê estas opções ao abrir (e as descarta).
	ir_para_execucoes(opcoes = {}) {
		frappe.route_options = { dias: this.filtros.dias, ...opcoes };
		frappe.set_route("execucoes-de-jobs");
	}

	agendar_atualizacao() {
		// Recarrega sozinho enquanto a página estiver aberta. Com job rodando o
		// intervalo cai para 5 s, para o usuário ver o término (ou a parada) logo.
		const ciclo = () => {
			const visivel =
				frappe.get_route()[0] === "monitor-de-jobs" &&
				document.visibilityState === "visible";
			if (visivel) {
				this.carregar({ silencioso: true });
			}
			setTimeout(ciclo, this.em_execucao.length ? 5000 : 60000);
		};
		setTimeout(ciclo, 60000);

		// Cronômetro das execuções em andamento, sem novas chamadas ao servidor.
		setInterval(() => gris.job_monitor.atualizar_decorrido(this.corpo), 1000);
	}

	// ------------------------------------------------------------------- dados

	carregar(opcoes = {}) {
		if (!opcoes.silencioso) {
			this.area_jobs.html(this.html_carregando());
		}

		return Promise.all([
			this.carregar_em_execucao(),
			this.carregar_resumo(),
			this.carregar_jobs(),
		]);
	}

	carregar_em_execucao() {
		return frappe
			.call({ method: "gris.api.monitoramento_jobs.listar_em_execucao" })
			.then((resposta) => {
				const dados = resposta.message;
				if (!dados || !dados.success) {
					return;
				}
				this.em_execucao = dados.execucoes || [];
				this.renderizar_rodando();
				// O card "Rodando agora" usa esta lista; as chamadas chegam em ordem indefinida.
				if (this.resumo) {
					this.renderizar_cards(this.resumo);
				}
				// A tabela de jobs depende de quem está rodando (botão Parar/Executar).
				if (this.jobs) {
					this.renderizar_jobs();
				}
			});
	}

	carregar_resumo() {
		return frappe
			.call({
				method: "gris.api.monitoramento_jobs.resumo_geral",
				args: { dias: this.filtros.dias },
			})
			.then((resposta) => {
				const resumo = resposta.message;
				if (!resumo || !resumo.success) {
					return;
				}
				this.resumo = resumo;
				this.renderizar_cards(resumo);
				this.renderizar_grafico(resumo);
			});
	}

	carregar_jobs() {
		return frappe
			.call({
				method: "gris.api.monitoramento_jobs.listar_jobs",
				args: {
					dias: this.filtros.dias,
					limite: this.paginacao.limite,
					inicio_em: this.paginacao.inicio,
				},
			})
			.then((resposta) => {
				const dados = resposta.message;
				if (!dados || !dados.success) {
					return;
				}
				this.jobs = dados.jobs || [];
				this.paginacao.total = dados.total || 0;
				this.renderizar_jobs();
			});
	}

	// --------------------------------------------------------------- renderizacao

	html_carregando() {
		return `<div class="text-muted gris-monitor-vazio">${__("Carregando…")}</div>`;
	}

	renderizar_cards(resumo) {
		const cards = [
			{ rotulo: __("Execuções no período"), valor: resumo.execucoes },
			{
				rotulo: __("Taxa de sucesso"),
				valor: resumo.taxa_de_sucesso === null ? "—" : `${resumo.taxa_de_sucesso}%`,
				cor: resumo.falhas ? "orange" : "green",
			},
			{
				rotulo: __("Execuções com erro"),
				valor: resumo.falhas,
				cor: resumo.falhas ? "red" : "gray",
				alvo: "erros",
			},
			{
				rotulo: __("Duração média"),
				valor: gris.job_logs.formatar_duracao(resumo.duracao_media),
			},
			{
				rotulo: __("Rodando agora"),
				valor: this.em_execucao.length,
				cor: this.em_execucao.length ? "blue" : "gray",
				alvo: "rodando",
			},
		];

		this.area_cards.html(
			cards
				.map(
					(card) => `
					<div class="gris-monitor-card ${card.alvo ? "gris-monitor-card-clicavel" : ""}"
						${card.alvo ? `data-alvo="${card.alvo}" role="button" tabindex="0"` : ""}>
						<div class="gris-monitor-card-valor ${card.cor ? `text-${card.cor}` : ""}">
							${gris.job_logs.escapar(card.valor)}
						</div>
						<div class="gris-monitor-card-rotulo">${gris.job_logs.escapar(card.rotulo)}</div>
					</div>`
				)
				.join("")
		);

		this.area_cards.find(".gris-monitor-card-clicavel").on("click keydown", (evento) => {
			if (evento.type === "keydown" && !["Enter", " "].includes(evento.key)) {
				return;
			}
			this.usar_card_como_atalho($(evento.currentTarget).data("alvo"));
		});
	}

	usar_card_como_atalho(alvo) {
		if (alvo === "rodando") {
			if (this.em_execucao.length) {
				frappe.utils.scroll_to(this.area_rodando, true, 20);
			}
			return;
		}
		this.ir_para_execucoes({ status: "erros" });
	}

	renderizar_rodando() {
		if (!this.em_execucao.length) {
			this.area_rodando.empty();
			return;
		}

		const linhas = this.em_execucao
			.map(
				(execucao) => `
				<div class="gris-monitor-rodando-item">
					<div class="gris-monitor-rodando-info">
						<div class="gris-monitor-job-nome">${gris.job_logs.escapar(execucao.job)}</div>
						<div class="gris-monitor-job-metodo">
							${gris.job_logs.escapar(execucao.origem)} ·
							${__("há")} ${gris.job_monitor.html_decorrido(execucao.inicio)}
						</div>
						${
							execucao.resumo
								? `<div class="text-muted small">${gris.job_logs.escapar(
										execucao.resumo
								  )}</div>`
								: ""
						}
					</div>
					<div class="gris-monitor-rodando-acoes">
						<button class="btn btn-xs btn-default gris-monitor-ver"
							data-name="${gris.job_logs.escapar(execucao.name)}">${__("Ver andamento")}</button>
						${gris.job_monitor.html_botao_parar(execucao)}
					</div>
				</div>`
			)
			.join("");

		this.area_rodando.html(`
			<div class="gris-monitor-rodando-caixa">
				<div class="gris-monitor-rodando-titulo">
					<span class="indicator-pill blue">${__("Rodando agora")}</span>
					<span class="text-muted small">${__("Atualiza a cada 5 segundos")}</span>
				</div>
				${linhas}
			</div>
		`);

		this.ligar_parar(this.area_rodando);
		this.area_rodando.find(".gris-monitor-ver").on("click", (evento) => {
			this.ir_para_execucoes({ execucao: $(evento.currentTarget).data("name") });
		});
		gris.job_monitor.atualizar_decorrido(this.area_rodando);
	}

	ligar_parar(area) {
		gris.job_monitor.ligar_botoes_parar(area, () => this.carregar({ silencioso: true }));
	}

	renderizar_grafico(resumo) {
		const dias = (resumo.serie || []).map((linha) => linha.dia);
		if (!dias.length) {
			this.corpo.find(".gris-monitor-grafico-wrapper").hide();
			return;
		}
		this.corpo.find(".gris-monitor-grafico-wrapper").show();

		const series = ORDEM_DOS_STATUS.filter((status) =>
			(resumo.serie || []).some((linha) => linha[status])
		).map((status) => ({
			name: gris.job_logs.rotulo_status(status),
			type: "bar",
			stack: "execucoes",
			itemStyle: { color: CORES_DO_STATUS[status] },
			emphasis: { focus: "series" },
			data: (resumo.serie || []).map((linha) => linha[status] || 0),
		}));

		if (!this.grafico) {
			this.grafico = echarts.init(this.area_grafico[0], null, { renderer: "canvas" });
			$(window).on("resize.monitor_de_jobs", () => this.grafico && this.grafico.resize());
		}

		this.grafico.setOption(
			{
				aria: { enabled: true, decal: { show: true } },
				tooltip: { trigger: "axis", axisPointer: { type: "shadow" } },
				legend: { bottom: 0, icon: "roundRect" },
				grid: { left: 40, right: 16, top: 16, bottom: 48, containLabel: true },
				xAxis: {
					type: "category",
					data: dias.map((dia) => frappe.datetime.str_to_user(dia)),
					axisTick: { alignWithLabel: true },
				},
				yAxis: { type: "value", minInterval: 1, name: __("Execuções") },
				series: series,
			},
			true
		);
	}

	renderizar_jobs() {
		if (!this.jobs || !this.jobs.length) {
			this.area_jobs.html(
				`<div class="gris-monitor-vazio text-muted">
					${__("Nenhum job foi executado ainda. Assim que o scheduler rodar, as execuções aparecem aqui.")}
				</div>`
			);
			this.area_paginador.empty();
			return;
		}

		const linhas = this.jobs
			.map((job) => {
				const ultima = job.ultima;
				const status = ultima
					? gris.job_logs.badge_status(ultima.status)
					: `<span class="text-muted">${__("Sem execuções")}</span>`;
				const quando = ultima
					? `<span title="${gris.job_logs.escapar(ultima.inicio)}">
							${frappe.datetime.comment_when(ultima.inicio)}
						</span>`
					: "—";
				const agenda = job.parado
					? `<span class="indicator-pill gray">${__("Pausado")}</span>`
					: gris.job_logs.escapar(this.descrever_agenda(job));
				const falhas = job.falhas
					? `<span class="text-danger">${job.falhas}</span>`
					: `<span class="text-muted">0</span>`;
				const metodo = gris.job_logs.escapar(job.metodo);

				return `<tr data-metodo="${metodo}" class="gris-monitor-linha">
					<td>
						<div class="gris-monitor-job-nome">${gris.job_logs.escapar(job.rotulo)}</div>
						<div class="gris-monitor-job-metodo">${metodo}</div>
					</td>
					<td>${agenda}</td>
					<td>${status}</td>
					<td>${quando}</td>
					<td class="text-right">${job.execucoes}</td>
					<td class="text-right">${falhas}</td>
					<td class="text-right">${gris.job_logs.formatar_duracao(job.duracao_media)}</td>
					<td class="text-right">${this.html_acao_do_job(job)}</td>
				</tr>`;
			})
			.join("");

		this.area_jobs.html(`
			<div class="gris-monitor-tabela-wrapper">
				<table class="table table-sm gris-monitor-tabela">
					<thead>
						<tr>
							<th>${__("Job")}</th>
							<th>${__("Agenda")}</th>
							<th>${__("Última execução")}</th>
							<th>${__("Quando")}</th>
							<th class="text-right">${__("Execuções")}</th>
							<th class="text-right">${__("Com erro")}</th>
							<th class="text-right">${__("Duração média")}</th>
							<th></th>
						</tr>
					</thead>
					<tbody>${linhas}</tbody>
				</table>
			</div>
		`);

		gris.job_monitor.montar_paginador(this.area_paginador, this.paginacao, (nova) => {
			Object.assign(this.paginacao, nova);
			this.carregar_jobs();
		});

		this.area_jobs.find(".gris-monitor-linha").on("click", (evento) => {
			if ($(evento.target).closest("button").length) {
				return;
			}
			this.ir_para_execucoes({ metodo: $(evento.currentTarget).data("metodo") });
		});

		this.ligar_parar(this.area_jobs);
		this.area_jobs.find(".gris-monitor-executar").on("click", (evento) => {
			evento.stopPropagation();
			this.executar_agora($(evento.currentTarget).data("metodo"));
		});
	}

	html_acao_do_job(job) {
		const rodando = this.em_execucao.find((execucao) => execucao.metodo === job.metodo);
		if (rodando) {
			return gris.job_monitor.html_botao_parar(rodando);
		}
		if (job.agendado && !job.parado) {
			return `<button class="btn btn-xs btn-default gris-monitor-executar"
				data-metodo="${gris.job_logs.escapar(job.metodo)}">${__("Executar")}</button>`;
		}
		return "";
	}

	descrever_agenda(job) {
		if (!job.agendado) {
			return __("Sob demanda");
		}
		if (job.frequencia === "Cron") {
			return job.cron || __("Cron");
		}
		return job.frequencia || __("Agendado");
	}

	executar_agora(metodo) {
		frappe.confirm(__("Executar este job agora?"), () => {
			frappe
				.call({
					method: "gris.api.monitoramento_jobs.executar_job_agora",
					args: { metodo },
				})
				.then((resposta) => {
					const dados = resposta.message || {};
					frappe.show_alert({
						message: dados.mensagem || __("Job enviado para a fila."),
						indicator: dados.success ? "green" : "orange",
					});
					setTimeout(() => this.carregar({ silencioso: true }), 3000);
				});
		});
	}
}
