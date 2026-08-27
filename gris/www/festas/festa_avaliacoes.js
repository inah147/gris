(function () {
	"use strict";

	if (!window._festaData || !window._festaData.name) return;
	var FESTA_NAME = window._festaData.name;

	var METHODS = {
		getData: "gris.api.festas.avaliacao.get_festa_avaliacao_data",
		iniciar: "gris.api.festas.avaliacao.iniciar_avaliacao_festa",
		reenviar: "gris.api.festas.avaliacao.reenviar_email_avaliacao_festa",
		salvarGeral: "gris.api.festas.avaliacao.salvar_avaliacao_geral_festa",
		consultarResumo: "gris.api.festas.avaliacao.consultar_resumo_avaliacao_festa",
		enviarConvidadosWhatsapp: "gris.api.festas.avaliacao.enviar_avaliacao_convidados_whatsapp",
	};

	var RESUMO_CONFIG = {
		individual: {
			method: "gris.api.festas.avaliacao.solicitar_resumo_avaliacoes_individuais_festa",
			btn: "btnGerarResumoIndividual",
			pending: "pending_individuais",
		},
		completo: {
			method: "gris.api.festas.avaliacao.solicitar_resumo_avaliacao_completa_festa",
			btn: "btnGerarResumoCompleto",
			pending: "pending_completa",
		},
		convidados: {
			method: "gris.api.festas.avaliacao.solicitar_resumo_avaliacoes_convidados_festa",
			btn: "btnGerarResumoConvidados",
			pending: "pending_convidados",
		},
	};

	var state = { loaded: false, data: null, saving: false, polling: null };

	/* ── Helpers ──────────────────────────────────────────────────────────── */

	function $(id) {
		return document.getElementById(id);
	}

	function show(el, visible) {
		if (el) el.classList.toggle("d-none", !visible);
	}

	function escapeHtml(value) {
		return String(value === null || value === undefined ? "" : value)
			.replace(/&/g, "&amp;")
			.replace(/</g, "&lt;")
			.replace(/>/g, "&gt;")
			.replace(/"/g, "&quot;")
			.replace(/'/g, "&#39;");
	}

	function toast(message, category) {
		document.dispatchEvent(
			new CustomEvent("basecoat:toast", {
				detail: {
					config: { category: category || "info", description: message, duration: 3500 },
				},
			})
		);
	}

	function confirmDialog(opts) {
		opts = opts || {};
		return new Promise(function (resolve) {
			var dlg = $("confirm-dialog");
			if (!dlg || typeof dlg.showModal !== "function") {
				resolve(window.confirm(opts.message || opts.title || "Confirmar?"));
				return;
			}
			var titleEl = dlg.querySelector("header h2");
			var messageEl = dlg.querySelector("#confirm-dialog-message");
			var okBtn = dlg.querySelector("#confirm-dialog-ok");
			var cancelBtn = dlg.querySelector("#confirm-dialog-cancel");
			if (titleEl) titleEl.textContent = opts.title || "Confirmar ação";
			if (messageEl) messageEl.textContent = opts.message || "Tem certeza?";
			if (okBtn) {
				okBtn.textContent = opts.confirmLabel || "Confirmar";
				okBtn.className = opts.variant === "primary" ? "btn-primary" : "btn-destructive";
			}

			function cleanup() {
				if (okBtn) okBtn.removeEventListener("click", onOk);
				if (cancelBtn) cancelBtn.removeEventListener("click", onCancel);
				dlg.removeEventListener("close", onClose);
			}
			function onOk() {
				cleanup();
				dlg.close("confirm");
				resolve(true);
			}
			function onCancel() {
				cleanup();
				dlg.close("cancel");
				resolve(false);
			}
			function onClose() {
				cleanup();
				if (dlg.returnValue !== "confirm") resolve(false);
			}
			if (okBtn) okBtn.addEventListener("click", onOk);
			if (cancelBtn) cancelBtn.addEventListener("click", onCancel);
			dlg.addEventListener("close", onClose);
			dlg.showModal();
		});
	}

	function markdownToHtml(value) {
		if (!value) return "<em>Nenhum resumo gerado ainda.</em>";
		if (window.frappe && typeof frappe.markdown === "function") {
			return frappe.markdown(value);
		}
		return "<p>" + escapeHtml(value).replace(/\n/g, "<br>") + "</p>";
	}

	function callApi(method, args) {
		return new Promise(function (resolve, reject) {
			frappe.call({
				method: method,
				args: args,
				callback: function (r) {
					if (r && r.exc) {
						reject(new Error("Erro ao processar requisição."));
						return;
					}
					resolve((r && r.message) || {});
				},
				error: function (err) {
					reject(
						new Error((err && err.message) || "Erro de comunicação com o servidor.")
					);
				},
			});
		});
	}

	/* ── Carregamento sob demanda ─────────────────────────────────────────── */

	function loadData() {
		show($("avaliacaoLoading"), true);
		show($("avaliacaoEmpty"), false);
		show($("avaliacaoNoAccess"), false);
		show($("avaliacaoContent"), false);

		return callApi(METHODS.getData, { festa_name: FESTA_NAME })
			.then(function (data) {
				state.data = data;
				state.loaded = true;
				render(data);
			})
			.catch(function (err) {
				toast(err.message || "Falha ao carregar dados de avaliação.", "error");
			})
			.finally(function () {
				show($("avaliacaoLoading"), false);
			});
	}

	/* ── Renderização ─────────────────────────────────────────────────────── */

	function render(data) {
		if (!data || !data.avaliacao) {
			show($("avaliacaoContent"), false);
			return;
		}

		show($("avaliacaoContent"), true);
		var avaliacao = data.avaliacao;

		// Avaliação da equipe: prompt para iniciar ou cartões em andamento.
		show($("avaliacaoTeamEmpty"), !data.team_started);
		show($("avaliacaoTeamStarted"), data.team_started);
		if (data.team_started) {
			renderIndividuais(avaliacao, data);
			renderGeral(avaliacao, data);
		}

		// Avaliação de convidados: sempre disponível desde a criação da festa.
		renderConvidados(avaliacao, data);
	}

	function renderIndividuais(avaliacao, data) {
		var individuais = avaliacao.individuais || [];
		var total = individuais.length;
		var concluidas = individuais.filter(function (a) {
			return a.avaliacao_concluida;
		}).length;
		var pct = total > 0 ? Math.round((concluidas / total) * 100) : 0;

		if ($("avaliacaoProgressText")) {
			$("avaliacaoProgressText").textContent =
				concluidas + " de " + total + " avaliações concluídas";
		}
		if ($("avaliacaoProgressFill")) $("avaliacaoProgressFill").style.width = pct + "%";

		if ($("avaliacaoMetricGeral")) {
			$("avaliacaoMetricGeral").textContent =
				concluidas > 0 ? Number(avaliacao.avaliacao_geral || 0).toFixed(1) : "-";
		}
		if ($("avaliacaoMetricSatisfacao")) {
			$("avaliacaoMetricSatisfacao").textContent =
				concluidas > 0
					? Number(avaliacao.satisfacao_dos_participantes || 0).toFixed(2)
					: "-";
		}

		renderResumo(
			"avaliacaoResumoIndividual",
			"avaliacaoResumoIndividualContent",
			"btnGerarResumoIndividual",
			avaliacao.resumo_avaliacoes_individuais,
			concluidas > 0,
			data.can_edit_general
		);

		var listEl = $("avaliacaoAvaliadoresList");
		if (listEl) {
			listEl.innerHTML = individuais
				.map(function (a) {
					var badge = a.avaliacao_concluida
						? "badge badge-success"
						: "badge badge-secondary";
					var label = a.avaliacao_concluida ? "Concluída" : "Pendente";
					var actions = "";
					if (a.avaliacao_concluida) {
						actions =
							'<button type="button" class="btn-sm-outline" data-ver-avaliacao-idx="' +
							a.idx +
							'">Ver detalhes</button>';
					} else if (data.can_edit_general) {
						actions =
							'<button type="button" class="btn-sm-outline" data-reenviar-idx="' +
							a.idx +
							'">Reenviar e-mail e WhatsApp</button>';
					}
					return (
						'<div class="aval-avaliador">' +
						'<div class="aval-avaliador__info">' +
						'<span class="aval-avaliador__nome">' +
						escapeHtml(a.avaliador) +
						"</span>" +
						'<span class="' +
						badge +
						'">' +
						label +
						"</span></div>" +
						'<div class="aval-avaliador__actions">' +
						actions +
						"</div></div>"
					);
				})
				.join("");
		}
	}

	function renderGeral(avaliacao, data) {
		var fieldMap = {
			funcionou_bem: "o_que_funcionou_bem_na_dinamica_da_equipe",
			nao_funcionou: "o_que_nao_funcionou_na_dinamica_da_equipe",
			pontos_positivos: "pontos_positivos_adicionais",
			pontos_melhoria: "pontos_de_melhoria_adicionais",
		};
		Object.keys(fieldMap).forEach(function (short) {
			var el = $("aval_" + short);
			if (el) {
				el.value = avaliacao[fieldMap[short]] || "";
				el.disabled = !data.can_edit_general;
			}
		});

		if ($("btnSalvarAvaliacaoGeral")) {
			$("btnSalvarAvaliacaoGeral").style.display = data.can_edit_general ? "" : "none";
		}

		renderResumo(
			"avaliacaoResumoCompleto",
			"avaliacaoResumoCompletoContent",
			"btnGerarResumoCompleto",
			avaliacao.resumo_avaliacao_completa,
			true,
			data.can_edit_general
		);
	}

	function renderConvidados(avaliacao, data) {
		var convidados = avaliacao.convidados || [];

		var linkInput = $("avaliacaoPublicLink");
		if (linkInput) linkInput.value = data.public_link || "";

		var qr = $("avaliacaoPublicQr");
		if (qr) qr.src = data.public_link_qr || "";

		var btnWa = $("btnEnviarWhatsappConvidados");
		if (btnWa) {
			show(btnWa, !!data.whatsapp_integracao_ativa);
			btnWa.disabled = !data.can_send_convidados_whatsapp;
		}

		if ($("avaliacaoMetricRecomendacao")) {
			$("avaliacaoMetricRecomendacao").textContent =
				convidados.length > 0
					? Number(avaliacao.recomendacao_media_convidados || 0).toFixed(1)
					: "-";
		}
		if ($("avaliacaoConvidadosCount")) {
			$("avaliacaoConvidadosCount").textContent = String(convidados.length);
		}

		var listEl = $("avaliacaoConvidadosList");
		if (listEl) {
			if (convidados.length === 0) {
				listEl.innerHTML =
					'<p class="text-sm text-muted-foreground">Nenhuma avaliação de convidado recebida ainda.</p>';
			} else {
				listEl.innerHTML = convidados
					.map(function (c) {
						return (
							'<div class="aval-avaliador">' +
							'<div class="aval-avaliador__info">' +
							'<span class="aval-avaliador__nome">' +
							escapeHtml(c.email || "—") +
							"</span>" +
							'<span class="badge badge-secondary">Nota ' +
							escapeHtml(c.recomendacao) +
							"</span></div>" +
							'<div class="aval-avaliador__actions">' +
							'<button type="button" class="btn-sm-outline" data-ver-convidado-idx="' +
							c.idx +
							'">Ver detalhes</button>' +
							"</div></div>"
						);
					})
					.join("");
			}
		}

		renderResumo(
			"avaliacaoResumoConvidados",
			"avaliacaoResumoConvidadosContent",
			"btnGerarResumoConvidados",
			avaliacao.resumo_avaliacoes_convidados,
			convidados.length > 0,
			data.can_edit
		);
	}

	function renderResumo(sectionId, contentId, btnId, resumo, available, canEdit) {
		show($(sectionId), available);
		if (!available) return;
		if ($(contentId)) $(contentId).innerHTML = markdownToHtml(resumo);
		show($(btnId), Boolean(canEdit));
	}

	/* ── Ações ────────────────────────────────────────────────────────────── */

	function iniciarAvaliacao() {
		var btn = $("btnIniciarAvaliacao");
		if (btn) {
			btn.disabled = true;
			btn.textContent = "Iniciando...";
		}
		callApi(METHODS.iniciar, { festa_name: FESTA_NAME })
			.then(function () {
				state.loaded = false;
				return loadData();
			})
			.catch(function (err) {
				toast(err.message || "Falha ao iniciar avaliação.", "error");
				if (btn) {
					btn.disabled = false;
					btn.textContent = "Iniciar avaliação da equipe";
				}
			});
	}

	function salvarAvaliacaoGeral() {
		if (state.saving) return;
		state.saving = true;
		var btn = $("btnSalvarAvaliacaoGeral");
		if (btn) {
			btn.disabled = true;
			btn.textContent = "Salvando...";
		}

		var data = {
			o_que_funcionou_bem_na_dinamica_da_equipe: ($("aval_funcionou_bem") || {}).value || "",
			o_que_nao_funcionou_na_dinamica_da_equipe: ($("aval_nao_funcionou") || {}).value || "",
			pontos_positivos_adicionais: ($("aval_pontos_positivos") || {}).value || "",
			pontos_de_melhoria_adicionais: ($("aval_pontos_melhoria") || {}).value || "",
		};

		callApi(METHODS.salvarGeral, { festa_name: FESTA_NAME, data: JSON.stringify(data) })
			.then(function () {
				toast("Avaliação geral salva.", "success");
				state.loaded = false;
				return loadData();
			})
			.catch(function (err) {
				toast(err.message || "Falha ao salvar avaliação geral.", "error");
			})
			.finally(function () {
				state.saving = false;
				if (btn) {
					btn.disabled = false;
					btn.textContent = "Salvar avaliação geral";
				}
			});
	}

	function reenviarConvite(idx) {
		var btn = document.querySelector('[data-reenviar-idx="' + idx + '"]');
		if (btn) {
			btn.disabled = true;
			btn.textContent = "Enviando...";
		}
		callApi(METHODS.reenviar, { festa_name: FESTA_NAME, avaliador_idx: idx })
			.then(function (result) {
				if (btn) {
					btn.textContent =
						result && result.whatsapp_sent ? "Convite reenviado!" : "E-mail reenviado";
					setTimeout(function () {
						btn.disabled = false;
						btn.textContent = "Reenviar e-mail e WhatsApp";
					}, 3000);
				}
			})
			.catch(function (err) {
				toast(err.message || "Falha ao reenviar convite.", "error");
				if (btn) {
					btn.disabled = false;
					btn.textContent = "Reenviar e-mail e WhatsApp";
				}
			});
	}

	function gerarResumo(tipo) {
		var cfg = RESUMO_CONFIG[tipo];
		var btn = $(cfg.btn);
		if (btn) {
			btn.disabled = true;
			btn.textContent = "Gerando resumo...";
		}
		callApi(cfg.method, { festa_name: FESTA_NAME })
			.then(function () {
				iniciarPolling(tipo);
			})
			.catch(function (err) {
				toast(err.message || "Falha ao solicitar resumo.", "error");
				if (btn) {
					btn.disabled = false;
					btn.textContent = "Gerar resumo";
				}
			});
	}

	function iniciarPolling(tipo) {
		var cfg = RESUMO_CONFIG[tipo];
		if (state.polling) clearInterval(state.polling);
		state.polling = setInterval(function () {
			callApi(METHODS.consultarResumo, { festa_name: FESTA_NAME })
				.then(function (result) {
					if (!result[cfg.pending]) {
						clearInterval(state.polling);
						state.polling = null;
						state.loaded = false;
						loadData();
					}
				})
				.catch(function () {
					clearInterval(state.polling);
					state.polling = null;
				});
		}, 5000);
	}

	function abrirDetalheAvaliador(idx) {
		var item = (
			(state.data && state.data.avaliacao && state.data.avaliacao.individuais) ||
			[]
		).find(function (a) {
			return String(a.idx) === String(idx);
		});
		if (!item) return;
		abrirModal("Avaliação de " + escapeHtml(item.avaliador), [
			["Resultado da festa", escapeHtml(item.resultado_festa) + " / 10"],
			["Satisfação em colaborar", escapeHtml(item.satisfacao_colaboracao) + " / 10"],
			["O que foi muito bom", escapeHtml(item.muito_bom || "-")],
			["Pontos de melhoria", escapeHtml(item.pontos_melhoria || "-")],
		]);
	}

	function abrirDetalheConvidado(idx) {
		var item = (
			(state.data && state.data.avaliacao && state.data.avaliacao.convidados) ||
			[]
		).find(function (c) {
			return String(c.idx) === String(idx);
		});
		if (!item) return;
		abrirModal("Avaliação de convidado", [
			["E-mail", escapeHtml(item.email || "—")],
			["Recomendação", escapeHtml(item.recomendacao) + " / 10"],
			["O que mais gostou", escapeHtml(item.mais_gostou || "-")],
			["O que pode melhorar", escapeHtml(item.pode_melhorar || "-")],
		]);
	}

	function abrirModal(titulo, campos) {
		var titleEl = $("avaliacaoDetalheModalTitle");
		if (titleEl) titleEl.textContent = titulo;
		var contentEl = $("avaliacaoDetalheContent");
		if (contentEl) {
			contentEl.innerHTML =
				'<div class="aval-detalhe-grid">' +
				campos
					.map(function (c) {
						return (
							'<div class="aval-detalhe-item"><span class="aval-detalhe-item__label">' +
							c[0] +
							'</span><p class="aval-detalhe-item__value">' +
							c[1] +
							"</p></div>"
						);
					})
					.join("") +
				"</div>";
		}
		var modal = $("avaliacaoDetalheModal");
		if (modal && typeof modal.showModal === "function") modal.showModal();
	}

	function copiarLink() {
		var input = $("avaliacaoPublicLink");
		if (!input || !input.value) return;
		navigator.clipboard.writeText(input.value).then(
			function () {
				toast("Link copiado!", "success");
			},
			function () {
				input.select();
			}
		);
	}

	function baixarPdfQr() {
		var url =
			"/api/method/gris.api.festas.avaliacao.gerar_pdf_qr_convidados?festa_name=" +
			encodeURIComponent(FESTA_NAME);
		window.open(url, "_blank");
	}

	function enviarWhatsappConvidados() {
		confirmDialog({
			title: "Enviar avaliação por WhatsApp",
			message:
				"Enviar a avaliação por WhatsApp para todos os convidados que entraram na festa?",
			confirmLabel: "Enviar",
			variant: "primary",
		}).then(function (ok) {
			if (!ok) return;
			var btn = $("btnEnviarWhatsappConvidados");
			if (btn) btn.disabled = true;
			callApi(METHODS.enviarConvidadosWhatsapp, { festa_name: FESTA_NAME }).then(
				function (r) {
					var enviados = r.enviados || 0;
					if (enviados > 0) {
						toast("Envio iniciado para " + enviados + " convidado(s).", "success");
					} else {
						toast(
							"Nenhum convidado elegível para envio (com entrada, telefone e fora da equipe).",
							"info"
						);
					}
					if (btn) btn.disabled = false;
				},
				function () {
					toast("Não foi possível enviar as mensagens.", "error");
					if (btn) btn.disabled = false;
				}
			);
		});
	}

	/* ── Binding ──────────────────────────────────────────────────────────── */

	function bind() {
		var tabBtn = document.querySelector('#festa-tabs [data-tab="avaliacoes"]');
		if (tabBtn) {
			tabBtn.addEventListener("click", function () {
				if (!state.loaded) loadData();
			});
		}

		document.addEventListener("click", function (event) {
			var target = event.target instanceof Element ? event.target : null;
			if (!target) return;

			if (target.closest("#btnIniciarAvaliacao")) return iniciarAvaliacao();
			if (target.closest("#btnSalvarAvaliacaoGeral")) return salvarAvaliacaoGeral();
			if (target.closest("#btnGerarResumoIndividual")) return gerarResumo("individual");
			if (target.closest("#btnGerarResumoCompleto")) return gerarResumo("completo");
			if (target.closest("#btnGerarResumoConvidados")) return gerarResumo("convidados");
			if (target.closest("#btnCopiarLinkConvidados")) return copiarLink();
			if (target.closest("#btnBaixarPdfQr")) return baixarPdfQr();
			if (target.closest("#btnEnviarWhatsappConvidados")) return enviarWhatsappConvidados();

			var reenviar = target.closest("[data-reenviar-idx]");
			if (reenviar) return reenviarConvite(reenviar.getAttribute("data-reenviar-idx"));

			var verAval = target.closest("[data-ver-avaliacao-idx]");
			if (verAval)
				return abrirDetalheAvaliador(verAval.getAttribute("data-ver-avaliacao-idx"));

			var verConv = target.closest("[data-ver-convidado-idx]");
			if (verConv)
				return abrirDetalheConvidado(verConv.getAttribute("data-ver-convidado-idx"));
		});
	}

	if (document.readyState === "loading") {
		document.addEventListener("DOMContentLoaded", bind);
	} else {
		bind();
	}
})();
