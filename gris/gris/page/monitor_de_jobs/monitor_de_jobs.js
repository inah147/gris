// Copyright (c) 2026, Grupo Escoteiro Professora Inah de Mello - 47/SP and contributors
// For license information, please see license.txt

// Monitor de Jobs: mostra o que cada execução de job fez e onde falhou.
// Os dados vêm de gris.api.monitoramento_jobs, sobre o DocType
// "Log de Execucao de Job" alimentado por gris/utils/job_logger.py.

frappe.pages["monitor-de-jobs"].on_page_load = function (wrapper) {
	const page = frappe.ui.make_app_page({
		parent: wrapper,
		title: __("Monitor de Jobs"),
		single_column: true,
	});

	frappe.require(
		["/assets/gris/js/job_log_timeline.js", "/assets/gris/vendor/echarts/echarts.min.js"],
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
		this.filtros = { dias: 7, metodo: "", status: "", somente_com_erro: 0 };
		this.execucao_aberta = null;
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
		this.garantir_estilos_da_pagina();

		this.corpo = $(`
			<div class="gris-monitor">
				<div class="gris-monitor-cards"></div>
				<div class="gris-monitor-rodando"></div>
				<div class="gris-monitor-secao-titulo">${__("Jobs")}</div>
				<div class="gris-monitor-jobs"></div>
				<div class="gris-monitor-secao-titulo gris-monitor-titulo-execucoes">${__("Execuções")}</div>
				<div class="gris-monitor-execucoes"></div>
				<div class="gris-monitor-detalhe"></div>
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
		this.area_execucoes = this.corpo.find(".gris-monitor-execucoes");
		this.area_detalhe = this.corpo.find(".gris-monitor-detalhe");
		this.titulo_execucoes = this.corpo.find(".gris-monitor-titulo-execucoes");
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
			this.carregar();
		});

		this.campo_status = this.page.add_select(
			__("Status"),
			[{ label: __("Todos os status"), value: "" }].concat(
				ORDEM_DOS_STATUS.map((status) => ({
					label: gris.job_logs.rotulo_status(status),
					value: status,
				}))
			),
			""
		);
		this.campo_status.on("change", () => {
			this.filtros.status = this.campo_status.val();
			this.carregar_execucoes();
		});
	}

	montar_acoes() {
		this.page.set_primary_action(__("Atualizar"), () => this.carregar(), "refresh");

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

	agendar_atualizacao() {
		// Recarrega sozinho enquanto a página estiver aberta. Com job rodando o
		// intervalo cai para 5 s, para o usuário ver o término (ou a parada) logo.
		const ciclo = () => {
			const visivel =
				frappe.get_route()[0] === "monitor-de-jobs" && document.visibilityState === "visible";
			if (visivel) {
				this.carregar({ silencioso: true });
			}
			setTimeout(ciclo, this.em_execucao.length ? 5000 : 60000);
		};
		setTimeout(ciclo, 60000);

		// Cronômetro das execuções em andamento, sem novas chamadas ao servidor.
		setInterval(() => this.atualizar_decorrido(), 1000);
	}

	atualizar_decorrido() {
		this.corpo.find(".gris-monitor-decorrido").each((_indice, elemento) => {
			const inicio = $(elemento).data("inicio");
			const segundos = moment().diff(frappe.datetime.convert_to_user_tz(inicio, false), "seconds");
			$(elemento).text(gris.job_logs.formatar_duracao(Math.max(segundos, 0)));
		});
	}

	// ------------------------------------------------------------------- dados

	carregar(opcoes = {}) {
		if (!opcoes.silencioso) {
			this.area_jobs.html(this.html_carregando());
			this.area_execucoes.html(this.html_carregando());
		}

		return Promise.all([
			this.carregar_em_execucao(),
			this.carregar_resumo(),
			this.carregar_jobs(),
			this.carregar_execucoes(),
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
				this.renderizar_cards(resumo);
				this.renderizar_grafico(resumo);
			});
	}

	carregar_jobs() {
		return frappe
			.call({
				method: "gris.api.monitoramento_jobs.listar_jobs",
				args: { dias: this.filtros.dias },
			})
			.then((resposta) => {
				const dados = resposta.message;
				if (!dados || !dados.success) {
					return;
				}
				this.jobs = dados.jobs || [];
				this.renderizar_jobs();
			});
	}

	carregar_execucoes() {
		return frappe
			.call({
				method: "gris.api.monitoramento_jobs.listar_execucoes",
				args: {
					dias: this.filtros.dias,
					metodo: this.filtros.metodo || undefined,
					status: this.filtros.status || undefined,
					somente_com_erro: this.filtros.somente_com_erro,
					limite: 50,
				},
			})
			.then((resposta) => {
				const dados = resposta.message;
				if (!dados || !dados.success) {
					return;
				}
				this.execucoes = dados.execucoes || [];
				this.renderizar_execucoes();
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
					this.usar_card_como_filtro($(evento.currentTarget).data("alvo"));
				});
				}

				usar_card_como_filtro(alvo) {
					if (alvo === "rodando") {
						if (this.em_execucao.length) {
							frappe.utils.scroll_to(this.area_rodando, true, 20);
						}
						return;
					}

					this.filtros.somente_com_erro = this.filtros.somente_com_erro ? 0 : 1;
					this.area_cards
						.find('[data-alvo="erros"]')
						.toggleClass("gris-monitor-card-ativo", !!this.filtros.somente_com_erro);
					this.carregar_execucoes();
					frappe.utils.scroll_to(this.titulo_execucoes, true, 20);
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
										${__("há")} <span class="gris-monitor-decorrido"
											data-inicio="${gris.job_logs.escapar(execucao.inicio)}"></span>
									</div>
									${
										execucao.resumo
											? `<div class="text-muted small">${gris.job_logs.escapar(execucao.resumo)}</div>`
											: ""
									}
								</div>
								<div class="gris-monitor-rodando-acoes">
									<button class="btn btn-xs btn-default gris-monitor-ver"
										data-name="${gris.job_logs.escapar(execucao.name)}">${__("Ver andamento")}</button>
									<button class="btn btn-xs btn-danger gris-monitor-parar"
										data-name="${gris.job_logs.escapar(execucao.name)}"
										data-job="${gris.job_logs.escapar(execucao.job)}">${__("Parar")}</button>
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

					this.ligar_acoes_de_execucao(this.area_rodando);
					this.atualizar_decorrido();
				}

				// Botões "Parar"/"Ver andamento" são os mesmos no painel, nas tabelas e no detalhe.
				ligar_acoes_de_execucao(area) {
					area.find(".gris-monitor-parar")
						.off("click")
						.on("click", (evento) => {
							evento.stopPropagation();
							const botao = $(evento.currentTarget);
							this.parar_execucao(botao.data("name"), botao.data("job"));
						});
					area.find(".gris-monitor-ver")
						.off("click")
						.on("click", (evento) => {
							evento.stopPropagation();
							this.abrir_detalhe($(evento.currentTarget).data("name"));
						});
				}

				parar_execucao(name, job) {
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
									if (this.execucao_aberta === name) {
										this.abrir_detalhe(name);
									}
									this.carregar({ silencioso: true });
								});
						}
					);
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
					<td class="text-right">
						${this.html_acao_do_job(job)}
					</td>
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

		this.area_jobs.find(".gris-monitor-linha").on("click", (evento) => {
			if ($(evento.target).closest("button").length) {
				return;
			}
			this.filtrar_por_job($(evento.currentTarget).data("metodo"));
		});

		this.ligar_acoes_de_execucao(this.area_jobs);
		this.area_jobs.find(".gris-monitor-executar").on("click", (evento) => {
			evento.stopPropagation();
			this.executar_agora($(evento.currentTarget).data("metodo"));
		});
	}

	html_acao_do_job(job) {
		const rodando = this.em_execucao.find((execucao) => execucao.metodo === job.metodo);
		if (rodando) {
			return `<button class="btn btn-xs btn-danger gris-monitor-parar"
				data-name="${gris.job_logs.escapar(rodando.name)}"
				data-job="${gris.job_logs.escapar(rodando.job)}">${__("Parar")}</button>`;
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

	filtrar_por_job(metodo) {
		this.filtros.metodo = this.filtros.metodo === metodo ? "" : metodo;
		this.area_jobs.find(".gris-monitor-linha").removeClass("gris-monitor-linha-ativa");
		if (this.filtros.metodo) {
			this.area_jobs
				.find(`.gris-monitor-linha[data-metodo="${this.filtros.metodo}"]`)
				.addClass("gris-monitor-linha-ativa");
		}

		const job = (this.jobs || []).find((item) => item.metodo === this.filtros.metodo);
		this.titulo_execucoes.text(job ? `${__("Execuções")} — ${job.rotulo}` : __("Execuções"));
		this.fechar_detalhe();
		this.carregar_execucoes();
	}

	renderizar_execucoes() {
		if (!this.execucoes || !this.execucoes.length) {
			this.area_execucoes.html(
				`<div class="gris-monitor-vazio text-muted">${__(
					"Nenhuma execução encontrada com os filtros atuais."
				)}</div>`
			);
			return;
		}

		const linhas = this.execucoes
			.map((execucao) => {
				const alertas = [];
				if (execucao.total_erros) {
					alertas.push(
						`<span class="indicator-pill red">${execucao.total_erros} ${__(
							"erro(s)"
						)}</span>`
					);
				}
				if (execucao.total_avisos) {
					alertas.push(
						`<span class="indicator-pill orange">${execucao.total_avisos} ${__(
							"aviso(s)"
						)}</span>`
					);
				}

				// Escapado uma vez: `name` global do browser nao entra aqui.
				const nome_do_log = gris.job_logs.escapar(execucao.name);

				return `<tr class="gris-monitor-execucao" data-name="${nome_do_log}">
					<td>
						<div>${gris.job_logs.escapar(execucao.job)}</div>
						<div class="gris-monitor-job-metodo">${gris.job_logs.escapar(execucao.origem)}</div>
					</td>
					<td>${gris.job_logs.badge_status(execucao.status)}</td>
					<td title="${gris.job_logs.escapar(execucao.inicio)}">
						${frappe.datetime.str_to_user(execucao.inicio, true)}
					</td>
					<td class="text-right">${gris.job_logs.formatar_duracao(execucao.duracao)}</td>
					<td>${gris.job_logs.escapar(execucao.resumo || "")} ${alertas.join(" ")}</td>
						<td class="text-right">
							${
								execucao.status === "Em Execucao"
									? `<button class="btn btn-xs btn-danger gris-monitor-parar"
											data-name="${nome_do_log}"
											data-job="${gris.job_logs.escapar(execucao.job)}">${__("Parar")}</button>`
									: ""
							}
						</td>
					</tr>`;
			})
			.join("");

		this.area_execucoes.html(`
			<div class="gris-monitor-tabela-wrapper">
				<table class="table table-sm gris-monitor-tabela">
					<thead>
						<tr>
							<th>${__("Job")}</th>
							<th>${__("Status")}</th>
							<th>${__("Início")}</th>
							<th class="text-right">${__("Duração")}</th>
							<th>${__("Resumo")}</th>
								<th></th>
							</tr>
					</thead>
					<tbody>${linhas}</tbody>
				</table>
			</div>
		`);

		this.ligar_acoes_de_execucao(this.area_execucoes);
		this.area_execucoes.find(".gris-monitor-execucao").on("click", (evento) => {
			this.abrir_detalhe($(evento.currentTarget).data("name"));
		});

		if (this.execucao_aberta) {
			this.marcar_execucao_aberta();
		}
	}

	marcar_execucao_aberta() {
		this.area_execucoes.find(".gris-monitor-execucao").removeClass("gris-monitor-linha-ativa");
		this.area_execucoes
			.find(`.gris-monitor-execucao[data-name="${this.execucao_aberta}"]`)
			.addClass("gris-monitor-linha-ativa");
	}

	abrir_detalhe(name) {
		this.execucao_aberta = name;
		this.marcar_execucao_aberta();
		this.area_detalhe.html(this.html_carregando());

		frappe
			.call({ method: "gris.api.monitoramento_jobs.obter_execucao", args: { name } })
			.then((resposta) => {
				const dados = resposta.message;
				if (!dados || !dados.success) {
					return;
				}
				this.renderizar_detalhe(dados.execucao);
			});
	}

	fechar_detalhe() {
		this.execucao_aberta = null;
		this.area_detalhe.empty();
	}

	renderizar_detalhe(execucao) {
		this.area_detalhe.html(`
			<div class="gris-monitor-detalhe-caixa">
				<div class="gris-monitor-detalhe-topo">
					<div>
						<div class="gris-monitor-detalhe-titulo">${gris.job_logs.escapar(execucao.job)}</div>
						<div class="gris-monitor-job-metodo">
							${gris.job_logs.escapar(execucao.metodo)} ·
							${gris.job_logs.escapar(execucao.inicio)} ·
							${gris.job_logs.formatar_duracao(execucao.duracao)}
						</div>
					</div>
					<div class="gris-monitor-detalhe-acoes">
						${gris.job_logs.badge_status(execucao.status)}
						${
							execucao.status === "Em Execucao"
								? `<button class="btn btn-xs btn-danger gris-monitor-parar"
										data-name="${gris.job_logs.escapar(execucao.name)}"
										data-job="${gris.job_logs.escapar(execucao.job)}">${__("Parar")}</button>`
								: ""
						}
						<button class="btn btn-xs btn-default gris-monitor-abrir-registro">
							${__("Abrir registro")}
						</button>
						<button class="btn btn-xs btn-default gris-monitor-fechar">${__("Fechar")}</button>
					</div>
				</div>
				<div class="gris-monitor-detalhe-conteudo"></div>
			</div>
		`);

		gris.job_logs.render_detalhe(
			this.area_detalhe.find(".gris-monitor-detalhe-conteudo"),
			execucao
		);

		this.ligar_acoes_de_execucao(this.area_detalhe);
		this.area_detalhe.find(".gris-monitor-fechar").on("click", () => this.fechar_detalhe());
		this.area_detalhe.find(".gris-monitor-abrir-registro").on("click", () => {
			frappe.set_route("Form", "Log de Execucao de Job", execucao.name);
		});

		frappe.utils.scroll_to(this.area_detalhe, true, 20);
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

	garantir_estilos_da_pagina() {
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
			.gris-monitor-card-valor { font-size: 24px; font-weight: 600; font-variant-numeric: tabular-nums; }
			.gris-monitor-card-rotulo { font-size: 11px; color: var(--text-muted); text-transform: uppercase;
				letter-spacing: 0.4px; margin-top: 2px; }
			.gris-monitor-card-clicavel { cursor: pointer; }
			.gris-monitor-card-clicavel:hover, .gris-monitor-card-ativo { border-color: var(--primary); }
			.gris-monitor-rodando-caixa { border: 1px solid var(--border-color); border-left: 4px solid var(--blue-500);
				border-radius: var(--border-radius-md); padding: 12px 14px; background: var(--bg-blue); }
			.gris-monitor-rodando-titulo { display: flex; justify-content: space-between; align-items: center;
				gap: 8px; margin-bottom: 4px; flex-wrap: wrap; }
			.gris-monitor-rodando-item { display: flex; justify-content: space-between; align-items: center;
				gap: 12px; padding: 8px 0; border-top: 1px solid var(--border-color); flex-wrap: wrap; }
			.gris-monitor-rodando-acoes { display: flex; gap: 6px; }
			.gris-monitor-grafico-wrapper { margin-top: 24px; }
			.gris-monitor-secao-titulo { font-size: 13px; font-weight: 600; margin: 20px 0 8px; }
			.gris-monitor-grafico { height: 240px; }
			.gris-monitor-grafico-wrapper { border: 1px solid var(--border-color);
				border-radius: var(--border-radius-md); padding: 12px; background: var(--card-bg); }
			.gris-monitor-tabela-wrapper { border: 1px solid var(--border-color);
				border-radius: var(--border-radius-md); overflow-x: auto; background: var(--card-bg); }
			.gris-monitor-tabela { margin-bottom: 0; font-size: 12px; }
			.gris-monitor-tabela th { font-size: 11px; color: var(--text-muted); text-transform: uppercase;
				letter-spacing: 0.4px; white-space: nowrap; }
			.gris-monitor-tabela tbody tr { cursor: pointer; }
			.gris-monitor-tabela tbody tr:hover { background: var(--fg-hover-color); }
			.gris-monitor-linha-ativa, .gris-monitor-linha-ativa:hover { background: var(--bg-blue); }
			.gris-monitor-job-nome { font-weight: 500; }
			.gris-monitor-job-metodo { font-size: 11px; color: var(--text-muted); font-family: var(--font-stack-mono);
				word-break: break-all; }
			.gris-monitor-vazio { padding: 20px; border: 1px dashed var(--border-color);
				border-radius: var(--border-radius-md); text-align: center; }
			.gris-monitor-detalhe-caixa { margin-top: 16px; border: 1px solid var(--border-color);
				border-radius: var(--border-radius-md); padding: 14px; background: var(--card-bg); }
			.gris-monitor-detalhe-topo { display: flex; justify-content: space-between; align-items: flex-start;
				gap: 12px; flex-wrap: wrap; margin-bottom: 12px; }
			.gris-monitor-detalhe-titulo { font-weight: 600; }
			.gris-monitor-detalhe-acoes { display: flex; gap: 6px; align-items: center; flex-wrap: wrap; }
		`;
		document.head.appendChild(estilos);
	}
}
