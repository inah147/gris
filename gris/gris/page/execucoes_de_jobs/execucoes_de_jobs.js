// Copyright (c) 2026, Grupo Escoteiro Professora Inah de Mello - 47/SP and contributors
// For license information, please see license.txt

// Execuções de Jobs: histórico paginado de tudo o que os jobs fizeram, com
// filtros por período, status e job. Linhas ativas têm botão Parar; clicar numa
// linha abre o detalhe (linha do tempo, métricas e erro). Visão geral e gráfico
// ficam em "Monitor de Jobs".

frappe.pages["execucoes-de-jobs"].on_page_load = function (wrapper) {
	const page = frappe.ui.make_app_page({
		parent: wrapper,
		title: __("Execuções de Jobs"),
		single_column: true,
	});

	frappe.require(
		["/assets/gris/js/job_log_timeline.js", "/assets/gris/js/monitor_de_jobs_comum.js"],
		() => {
			wrapper.execucoes_de_jobs = new ExecucoesDeJobs(page);
			wrapper.execucoes_de_jobs.aplicar_opcoes_de_rota();
		}
	);
};

frappe.pages["execucoes-de-jobs"].on_page_show = function (wrapper) {
	if (wrapper.execucoes_de_jobs) {
		wrapper.execucoes_de_jobs.aplicar_opcoes_de_rota();
	}
};

class ExecucoesDeJobs {
	constructor(page) {
		this.page = page;
		this.filtros = { dias: 7, metodo: "", status: "" };
		this.paginacao = { inicio: 0, limite: 25, total: 0 };
		this.execucoes = [];
		this.montar_estrutura();
		this.montar_filtros();
		this.montar_acoes();
		this.carregar_metodos();
		this.agendar_atualizacao();
	}

	// ------------------------------------------------------------------ layout

	montar_estrutura() {
		gris.job_logs.garantir_estilos();
		gris.job_monitor.garantir_estilos();

		this.corpo = $(`
			<div class="gris-monitor">
				<div class="gris-monitor-execucoes"></div>
				<div class="gris-monitor-paginador"></div>
			</div>
		`).appendTo(this.page.main);

		this.area_execucoes = this.corpo.find(".gris-monitor-execucoes");
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
			this.filtrar();
		});

		this.campo_status = this.page.add_select(
			__("Status"),
			[
				{ label: __("Todos os status"), value: "" },
				{ label: __("Somente com erro"), value: "erros" },
			].concat(
				[
					"Em Execucao",
					"Sucesso",
					"Sucesso com Avisos",
					"Concluido com Erros",
					"Erro",
				].map((status) => ({ label: gris.job_logs.rotulo_status(status), value: status }))
			),
			""
		);
		this.campo_status.on("change", () => {
			this.filtros.status = this.campo_status.val();
			this.filtrar();
		});

		this.campo_job = this.page.add_field({
			fieldname: "job",
			label: __("Job"),
			fieldtype: "Select",
			options: [{ label: __("Todos os jobs"), value: "" }],
			default: "",
			change: () => {
				const valor = this.campo_job.get_value() || "";
				if (valor !== this.filtros.metodo) {
					this.filtros.metodo = valor;
					this.filtrar();
				}
			},
		});
	}

	montar_acoes() {
		this.page.set_primary_action(__("Atualizar"), () => this.carregar(), "refresh");

		this.page.add_menu_item(__("Ver visão geral"), () => frappe.set_route("monitor-de-jobs"));
		this.page.add_menu_item(__("Ver registros brutos"), () => {
			frappe.set_route("List", "Log de Execucao de Job");
		});
	}

	// Opções vindas do Monitor (job clicado, card de erros, "Ver andamento").
	aplicar_opcoes_de_rota() {
		const opcoes = frappe.route_options;
		frappe.route_options = null;

		// Sem opções (abrir a página direto, voltar a ela): mantém os filtros atuais.
		if (!opcoes) {
			this.carregar();
			return;
		}

		if (opcoes.dias) {
			this.filtros.dias = cint(opcoes.dias);
			this.campo_periodo.val(String(this.filtros.dias));
		}
		this.filtros.metodo = opcoes.metodo || "";
		this.filtros.status = opcoes.status || "";
		this.campo_status.val(this.filtros.status);
		this.campo_job.set_value(this.filtros.metodo);
		this.paginacao.inicio = 0;

		this.carregar();
		if (opcoes.execucao) {
			this.abrir_detalhe(opcoes.execucao);
		}
	}

	agendar_atualizacao() {
		// Com execução ativa na página, recarrega a cada 5 s; senão, a cada minuto.
		const ciclo = () => {
			const visivel =
				frappe.get_route()[0] === "execucoes-de-jobs" &&
				document.visibilityState === "visible";
			if (visivel && !this.detalhe) {
				this.carregar({ silencioso: true });
			}
			const ativa = this.execucoes.some((execucao) => execucao.status === "Em Execucao");
			setTimeout(ciclo, ativa ? 5000 : 60000);
		};
		setTimeout(ciclo, 60000);

		setInterval(() => gris.job_monitor.atualizar_decorrido(this.corpo), 1000);
	}

	// ------------------------------------------------------------------- dados

	carregar_metodos() {
		return frappe
			.call({ method: "gris.api.monitoramento_jobs.listar_metodos_dos_jobs" })
			.then((resposta) => {
				const dados = resposta.message;
				if (!dados || !dados.success) {
					return;
				}
				this.campo_job.df.options = [{ label: __("Todos os jobs"), value: "" }].concat(
					dados.jobs.map((job) => ({ label: job.rotulo, value: job.metodo }))
				);
				this.campo_job.refresh();
				this.campo_job.set_value(this.filtros.metodo);
			});
	}

	filtrar() {
		this.paginacao.inicio = 0;
		this.carregar();
	}

	carregar(opcoes = {}) {
		if (!opcoes.silencioso) {
			this.area_execucoes.html(
				`<div class="text-muted gris-monitor-vazio">${__("Carregando…")}</div>`
			);
		}

		return frappe
			.call({
				method: "gris.api.monitoramento_jobs.listar_execucoes",
				args: {
					dias: this.filtros.dias,
					metodo: this.filtros.metodo || undefined,
					status:
						this.filtros.status === "erros"
							? undefined
							: this.filtros.status || undefined,
					somente_com_erro: this.filtros.status === "erros" ? 1 : 0,
					limite: this.paginacao.limite,
					inicio_em: this.paginacao.inicio,
				},
			})
			.then((resposta) => {
				const dados = resposta.message;
				if (!dados || !dados.success) {
					return;
				}
				this.execucoes = dados.execucoes || [];
				this.paginacao.total = dados.total || 0;
				this.renderizar_execucoes();
			});
	}

	// --------------------------------------------------------------- renderizacao

	renderizar_execucoes() {
		if (!this.execucoes.length) {
			this.area_execucoes.html(
				`<div class="gris-monitor-vazio text-muted">${__(
					"Nenhuma execução encontrada com os filtros atuais."
				)}</div>`
			);
			this.area_paginador.empty();
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

				const ativa = execucao.status === "Em Execucao";
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
					<td class="text-right">${
						ativa
							? gris.job_monitor.html_decorrido(execucao.inicio)
							: gris.job_logs.formatar_duracao(execucao.duracao)
					}</td>
					<td class="gris-monitor-resumo">${gris.job_logs.escapar(execucao.resumo || "")} ${alertas.join(
					" "
				)}</td>
					<td class="text-right">${ativa ? gris.job_monitor.html_botao_parar(execucao) : ""}</td>
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

		gris.job_monitor.montar_paginador(this.area_paginador, this.paginacao, (nova) => {
			Object.assign(this.paginacao, nova);
			this.carregar();
		});

		gris.job_monitor.ligar_botoes_parar(this.area_execucoes, () =>
			this.carregar({ silencioso: true })
		);
		this.area_execucoes.find(".gris-monitor-execucao").on("click", (evento) => {
			this.abrir_detalhe($(evento.currentTarget).data("name"));
		});
		gris.job_monitor.atualizar_decorrido(this.area_execucoes);
	}

	// ----------------------------------------------------------------- detalhe

	abrir_detalhe(name) {
		frappe
			.call({ method: "gris.api.monitoramento_jobs.obter_execucao", args: { name } })
			.then((resposta) => {
				const dados = resposta.message;
				if (!dados || !dados.success) {
					return;
				}
				this.mostrar_detalhe(dados.execucao);
			});
	}

	mostrar_detalhe(execucao) {
		if (!this.detalhe) {
			this.detalhe = new frappe.ui.Dialog({
				title: __("Detalhe da execução"),
				size: "extra-large",
				fields: [{ fieldtype: "HTML", fieldname: "corpo" }],
				on_hide: () => {
					clearInterval(this.atualizador_do_detalhe);
					this.detalhe = null;
				},
			});
			this.detalhe.show();
		}

		const corpo = this.detalhe.fields_dict.corpo.$wrapper;
		corpo.html(`
			<div class="gris-monitor-detalhe-topo">
				<div>
					<div class="gris-monitor-detalhe-titulo">${gris.job_logs.escapar(execucao.job)}</div>
					<div class="gris-monitor-job-metodo">
						${gris.job_logs.escapar(execucao.metodo)} ·
						${gris.job_logs.escapar(execucao.inicio)} ·
						${
							execucao.status === "Em Execucao"
								? gris.job_monitor.html_decorrido(execucao.inicio)
								: gris.job_logs.formatar_duracao(execucao.duracao)
						}
					</div>
				</div>
				<div class="gris-monitor-detalhe-acoes">
					${gris.job_logs.badge_status(execucao.status)}
					${execucao.status === "Em Execucao" ? gris.job_monitor.html_botao_parar(execucao) : ""}
					<button class="btn btn-xs btn-default gris-monitor-abrir-registro">
						${__("Abrir registro")}
					</button>
				</div>
			</div>
			<div class="gris-monitor-detalhe-conteudo"></div>
		`);

		gris.job_logs.render_detalhe(corpo.find(".gris-monitor-detalhe-conteudo"), execucao);
		gris.job_monitor.atualizar_decorrido(corpo);

		gris.job_monitor.ligar_botoes_parar(corpo, () => {
			this.detalhe.hide();
			this.carregar({ silencioso: true });
		});
		corpo.find(".gris-monitor-abrir-registro").on("click", () => {
			this.detalhe.hide();
			frappe.set_route("Form", "Log de Execucao de Job", execucao.name);
		});

		// Execução ativa: atualiza a linha do tempo enquanto o detalhe estiver aberto.
		clearInterval(this.atualizador_do_detalhe);
		if (execucao.status === "Em Execucao") {
			this.atualizador_do_detalhe = setInterval(
				() => this.abrir_detalhe(execucao.name),
				5000
			);
		}
	}
}
