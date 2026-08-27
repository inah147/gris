(function () {
	const METHODS = {
		bootstrap: "gris.gestao_de_projetos.doctype.projeto.projeto.get_projeto_execucao_data",
		getContatoPessoa: "gris.gestao_de_projetos.doctype.projeto.projeto.get_contato_pessoa",
		saveParticipants:
			"gris.gestao_de_projetos.doctype.projeto.projeto.salvar_envolvidos_projeto_execucao",
		saveTask: "gris.gestao_de_projetos.doctype.projeto.projeto.salvar_tarefa_projeto_execucao",
		moveTask:
			"gris.gestao_de_projetos.doctype.projeto.projeto.atualizar_status_tarefa_projeto_execucao",
		getTaskComments:
			"gris.gestao_de_projetos.doctype.projeto.projeto.get_tarefa_projeto_execucao_comentarios",
		addTaskComment:
			"gris.gestao_de_projetos.doctype.projeto.projeto.adicionar_comentario_tarefa_projeto_execucao",
		editTaskComment:
			"gris.gestao_de_projetos.doctype.projeto.projeto.editar_comentario_tarefa_projeto_execucao",
		deleteTaskComment:
			"gris.gestao_de_projetos.doctype.projeto.projeto.apagar_comentario_tarefa_projeto_execucao",
		saveMeeting:
			"gris.gestao_de_projetos.doctype.projeto.projeto.salvar_reuniao_projeto_execucao",
		completeProject:
			"gris.gestao_de_projetos.doctype.projeto.projeto.concluir_projeto_execucao",
		cancelProject: "gris.gestao_de_projetos.doctype.projeto.projeto.cancelar_projeto_execucao",
		getAvaliacaoData:
			"gris.gestao_de_projetos.doctype.projeto.projeto.get_avaliacao_projeto_data",
		iniciarAvaliacao:
			"gris.gestao_de_projetos.doctype.projeto.projeto.iniciar_avaliacao_projeto",
		salvarAvaliacaoGeral:
			"gris.gestao_de_projetos.doctype.projeto.projeto.salvar_avaliacao_geral_projeto",
		reenviarEmailAvaliacao:
			"gris.gestao_de_projetos.doctype.projeto.projeto.reenviar_email_avaliacao",
		solicitarResumoIndividual:
			"gris.gestao_de_projetos.doctype.projeto.projeto.solicitar_resumo_avaliacoes_individuais",
		solicitarResumoCompleto:
			"gris.gestao_de_projetos.doctype.projeto.projeto.solicitar_resumo_avaliacao_completa",
		consultarResumo:
			"gris.gestao_de_projetos.doctype.projeto.projeto.consultar_resumo_avaliacao",
	};

	const state = {
		projetoName: "",
		loading: false,
		canEdit: false,
		choices: {
			associados: [],
			responsaveis: [],
		},
		responsavelOptions: [],
		projeto: null,
		activeTab: "dados-gerais",
		participantsSaving: false,
		meetingEditors: {
			pauta: null,
			ata: null,
		},
		meetingPersisted: false,
		projectStatusAction: "",
		projectStatusSaving: false,
		avaliacaoData: null,
		avaliacaoLoaded: false,
		avaliacaoSaving: false,
		avaliacaoResumoPolling: null,
		kanban: null,
	};

	const MS_PER_DAY = 24 * 60 * 60 * 1000;

	function escapeHtml(value) {
		return String(value || "")
			.replace(/&/g, "&amp;")
			.replace(/</g, "&lt;")
			.replace(/>/g, "&gt;")
			.replace(/\"/g, "&quot;")
			.replace(/'/g, "&#39;");
	}

	function toFlag(value, defaultValue) {
		if (value === null || value === undefined || value === "") {
			return defaultValue ? 1 : 0;
		}
		return Number(value) === 1 ? 1 : 0;
	}

	function showAlert(message, type) {
		const el = document.getElementById("projectAlert");
		if (!el) return;
		el.className = "alert " + (type === "error" ? "alert-destructive" : "alert-success");
		el.innerHTML = "<section>" + escapeHtml(message) + "</section>";
		el.removeAttribute("hidden");
	}

	function hideAlert() {
		const el = document.getElementById("projectAlert");
		if (!el) return;
		el.setAttribute("hidden", "");
		el.textContent = "";
	}

	function showToast(message, category = "info") {
		document.dispatchEvent(
			new CustomEvent("basecoat:toast", {
				detail: { config: { category, description: message } },
			})
		);
	}

	function getEventTargetElement(event) {
		const target = event?.target;
		if (target instanceof Element) {
			return target;
		}
		if (target && target.parentElement instanceof Element) {
			return target.parentElement;
		}
		return null;
	}

	function extractServerMessage(response) {
		if (!response) return "";

		let serverMessages = response._server_messages;
		if (typeof serverMessages === "string" && serverMessages.trim()) {
			try {
				serverMessages = JSON.parse(serverMessages);
			} catch (e) {
				serverMessages = [];
			}
		}

		if (Array.isArray(serverMessages) && serverMessages.length) {
			try {
				const raw = JSON.parse(serverMessages[0]);
				if (raw && raw.message) {
					return raw.message;
				}
			} catch (e) {
				return "";
			}
		}

		if (typeof response.message === "string" && response.message.trim()) {
			return response.message.trim();
		}

		return "";
	}

	function callApi(method, args) {
		return new Promise((resolve, reject) => {
			frappe.call({
				method,
				args,
				callback: (r) => {
					if (r.exc) {
						reject(
							new Error(extractServerMessage(r) || "Erro ao processar requisição.")
						);
						return;
					}
					resolve(r.message || {});
				},
				error: (err) => {
					const message =
						err && err.message ? err.message : "Erro de comunicação com o servidor.";
					reject(new Error(message));
				},
			});
		});
	}

	function getProjetoName() {
		const hidden = (document.getElementById("projetoName")?.value || "").trim();
		if (hidden) return hidden;
		const params = new URLSearchParams(window.location.search);
		return (params.get("projeto") || "").trim();
	}

	function fillValue(field, value) {
		const el = document.getElementById(`view_${field}`);
		if (!el) return;
		const text = String(value || "").trim();
		if ("value" in el) {
			el.value = text || "-";
			return;
		}
		el.textContent = text || "-";
	}

	function getSelectComponentValue(selectId, fallback = "") {
		const selectEl = document.getElementById(selectId);
		if (!selectEl) return fallback;

		const currentValue = selectEl.value;
		if (typeof currentValue === "string" && currentValue.trim()) {
			return currentValue.trim();
		}

		if (Array.isArray(currentValue) && currentValue.length) {
			return String(currentValue[0] || "").trim() || fallback;
		}

		const hiddenInput = selectEl.querySelector(':scope > input[type="hidden"]');
		const hiddenValue = String(hiddenInput?.value || "").trim();
		return hiddenValue || fallback;
	}

	function setSelectComponentValue(selectId, value) {
		const selectEl = document.getElementById(selectId);
		if (!selectEl) return;

		const nextValue = String(value || "").trim();
		selectEl.value = nextValue;

		const hiddenInput = selectEl.querySelector(':scope > input[type="hidden"]');
		if (hiddenInput) {
			hiddenInput.value = nextValue;
		}
	}

	function updateGoogleDriveButton(link) {
		const button = document.getElementById("btnAbrirGoogleDrive");
		if (!button) return;

		const url = String(link || "").trim();
		if (!url) {
			button.classList.add("d-none");
			button.setAttribute("href", "#");
			button.setAttribute("aria-hidden", "true");
			return;
		}

		button.classList.remove("d-none");
		button.setAttribute("href", url);
		button.setAttribute("aria-hidden", "false");
	}

	function sanitizeRenderedHtml(html) {
		const container = document.createElement("div");
		container.innerHTML = html || "";

		container
			.querySelectorAll("script, style, iframe, object, embed, link, meta, base, form")
			.forEach((node) => node.remove());

		container.querySelectorAll("*").forEach((node) => {
			Array.from(node.attributes).forEach((attribute) => {
				const name = String(attribute.name || "").toLowerCase();
				const value = String(attribute.value || "")
					.trim()
					.toLowerCase();

				if (name.startsWith("on") || name === "srcdoc") {
					node.removeAttribute(attribute.name);
					return;
				}

				if (
					(name === "href" || name === "src") &&
					(value.startsWith("javascript:") || value.startsWith("data:text/html"))
				) {
					node.removeAttribute(attribute.name);
				}
			});
		});

		return container.innerHTML;
	}

	function renderSimpleMarkdown(text) {
		return escapeHtml(text || "")
			.replace(/^\-\s+(.+)$/gm, "<li>$1</li>")
			.replace(/(<li>.*<\/li>)/gs, "<ul>$1</ul>")
			.replace(/\*\*(.+?)\*\*/g, "<strong>$1</strong>")
			.replace(/\*(.+?)\*/g, "<em>$1</em>")
			.replace(
				/\[(.+?)\]\((https?:\/\/[^\s)]+)\)/g,
				'<a href="$2" target="_blank" rel="noopener noreferrer">$1</a>'
			)
			.replace(/\n/g, "<br>");
	}

	function markdownToHtml(value) {
		if (!value) {
			return "-";
		}
		if (window.frappe && typeof frappe.markdown === "function") {
			return sanitizeRenderedHtml(frappe.markdown(value || ""));
		}
		return renderSimpleMarkdown(value || "");
	}

	function renderMarkdownToContainer(el, value) {
		if (!el) return;
		if (!value) {
			el.textContent = "-";
			return;
		}

		el.innerHTML = markdownToHtml(value || "");
	}

	function updateMeetingAtaAvailability(editable) {
		const ataSection = document.getElementById("meetingAtaSection");
		const canEditAta = Boolean(editable && state.meetingPersisted);

		if (ataSection) {
			ataSection.classList.toggle("d-none", !state.meetingPersisted);
		}

		if (!state.meetingPersisted) {
			setToastEditorValue(state.meetingEditors.ata, "");
		}
		setToastEditorReadOnly(state.meetingEditors.ata, !canEditAta, "meeting_ata_editor_host");
	}

	function setToastEditorValue(editor, value) {
		if (!editor || typeof editor.setMarkdown !== "function") return;
		try {
			editor.setMarkdown(value || "", false);
		} catch (error) {
			// ignore — editor pode estar em estado transitório
		}
	}

	function getToastEditorValue(editor) {
		if (!editor || typeof editor.getMarkdown !== "function") return "";
		try {
			return String(editor.getMarkdown() || "").trim();
		} catch (error) {
			return "";
		}
	}

	function setToastEditorReadOnly(editor, readOnly, hostId = "task_observacoes_editor_host") {
		const host = document.getElementById(hostId);
		if (host) {
			host.classList.toggle("is-readonly", Boolean(readOnly));
			host.querySelectorAll("[contenteditable]").forEach((el) => {
				el.setAttribute("contenteditable", readOnly ? "false" : "true");
			});
		}
	}

	async function initMeetingToastEditor(hostId) {
		const host = document.getElementById(hostId);
		if (!host || !window.gris?.editor?.create) {
			return null;
		}

		host.innerHTML = "";
		try {
			return await window.gris.editor.create(host, {
				initialValue: "",
				toolbarItems: [
					["heading", "bold", "italic", "strike"],
					["hr", "quote"],
					["ul", "ol", "task"],
					["table", "link"],
					["code", "codeblock"],
				],
			});
		} catch (error) {
			return null;
		}
	}

	async function initMeetingEditors() {
		const [pautaEditor, ataEditor] = await Promise.all([
			initMeetingToastEditor("meeting_pauta_editor_host"),
			initMeetingToastEditor("meeting_ata_editor_host"),
		]);
		state.meetingEditors.pauta = pautaEditor;
		state.meetingEditors.ata = ataEditor;
	}

	function renderTableRows(tbodyId, rows, columns) {
		const tbody = document.getElementById(tbodyId);
		if (!tbody) return;

		if (!rows || !rows.length) {
			tbody.innerHTML = `<tr><td colspan="${columns.length}">Nenhum registro informado.</td></tr>`;
			return;
		}

		tbody.innerHTML = rows
			.map((row) => {
				const tds = columns
					.map((column) => `<td>${escapeHtml(row[column] || "-")}</td>`)
					.join("");
				return `<tr>${tds}</tr>`;
			})
			.join("");
	}

	function parseDateFlexible(value) {
		const text = String(value || "").trim();
		if (!text) return null;

		const isoMatch = text.match(/^(\d{4})-(\d{2})-(\d{2})$/);
		if (isoMatch) {
			const year = Number(isoMatch[1]);
			const month = Number(isoMatch[2]);
			const day = Number(isoMatch[3]);
			const isoDate = new Date(year, month - 1, day);
			if (!Number.isNaN(isoDate.getTime())) {
				isoDate.setHours(0, 0, 0, 0);
				return isoDate;
			}
		}

		const brMatch = text.match(/^(\d{2})\/(\d{2})\/(\d{4})$/);
		if (brMatch) {
			const day = Number(brMatch[1]);
			const month = Number(brMatch[2]);
			const year = Number(brMatch[3]);
			const brDate = new Date(year, month - 1, day);
			if (!Number.isNaN(brDate.getTime())) {
				brDate.setHours(0, 0, 0, 0);
				return brDate;
			}
		}

		return null;
	}

	function addDays(date, days) {
		const result = new Date(date);
		result.setDate(result.getDate() + days);
		result.setHours(0, 0, 0, 0);
		return result;
	}

	function diffDays(start, end) {
		return Math.round((end.getTime() - start.getTime()) / MS_PER_DAY);
	}

	function formatDatePtBr(date) {
		if (!(date instanceof Date) || Number.isNaN(date.getTime())) return "-";
		return date.toLocaleDateString("pt-BR", {
			day: "2-digit",
			month: "2-digit",
			year: "numeric",
		});
	}

	function formatDateTimePtBr(value) {
		const date = parseDateTimeFlexible(value);
		if (!date) return "-";
		return date.toLocaleString("pt-BR", {
			day: "2-digit",
			month: "2-digit",
			year: "numeric",
			hour: "2-digit",
			minute: "2-digit",
		});
	}

	function formatTimePtBr(value) {
		const date = parseDateTimeFlexible(value);
		if (!date) return "-";
		return date.toLocaleTimeString("pt-BR", {
			hour: "2-digit",
			minute: "2-digit",
		});
	}

	function renderCronogramaGantt(rows, containerId) {
		const container = document.getElementById(containerId);
		if (!container) return;

		const tasks = (rows || [])
			.map((row) => {
				const start = parseDateFlexible(row.data_inicio);
				const end = parseDateFlexible(row.data_termino);
				const tarefa = String(row.tarefa || "").trim();
				if (!start || !end || !tarefa) return null;
				return {
					start,
					end: end < start ? start : end,
					tarefa,
				};
			})
			.filter(Boolean);

		if (!tasks.length) {
			container.innerHTML =
				'<div class="cronograma-gantt__empty">Nenhuma atividade com período válido para exibir no Gantt.</div>';
			return;
		}

		const minStart = tasks.reduce(
			(acc, task) => (task.start < acc ? task.start : acc),
			tasks[0].start
		);
		const maxEnd = tasks.reduce(
			(acc, task) => (task.end > acc ? task.end : acc),
			tasks[0].end
		);
		const chartStart = addDays(minStart, -1);
		const chartEnd = addDays(maxEnd, 1);
		const totalDays = Math.max(diffDays(chartStart, chartEnd) + 1, 2);

		const tickEvery = totalDays > 45 ? 7 : totalDays > 20 ? 3 : 1;
		const ticks = [];
		for (let day = 0; day < totalDays; day += tickEvery) {
			const date = addDays(chartStart, day);
			ticks.push(
				`<div class="cronograma-gantt__tick" style="left:${
					(day / totalDays) * 100
				}%">${date.toLocaleDateString("pt-BR", {
					day: "2-digit",
					month: "2-digit",
				})}</div>`
			);
		}

		const rowsHtml = tasks
			.map((task) => {
				const offsetDays = diffDays(chartStart, task.start);
				const durationDays = Math.max(diffDays(task.start, task.end) + 1, 1);
				const leftPct = (offsetDays / totalDays) * 100;
				const widthPct = (durationDays / totalDays) * 100;
				const tooltip = `Início: ${formatDatePtBr(task.start)} | Término: ${formatDatePtBr(
					task.end
				)}`;

				return `
                    <div class="cronograma-gantt__row">
                        <div class="cronograma-gantt__label" title="${escapeHtml(
							task.tarefa
						)}">${escapeHtml(task.tarefa)}</div>
                        <div class="cronograma-gantt__lane">
                            <div class="cronograma-gantt__bar" style="left:${leftPct}%;width:${widthPct}%;" title="${escapeHtml(
					tooltip
				)}">
                                <span class="cronograma-gantt__bar-text">${escapeHtml(
									task.tarefa
								)}</span>
                            </div>
                        </div>
                    </div>
                `;
			})
			.join("");

		container.innerHTML = `
            <div class="cronograma-gantt__header">
                <div class="cronograma-gantt__header-label">Tarefa</div>
                <div class="cronograma-gantt__timeline">${ticks.join("")}</div>
            </div>
            <div class="cronograma-gantt__body">
                ${rowsHtml}
            </div>
        `;
	}

	function renderReviewRows(rows) {
		const tbody = document.getElementById("view_rows_revisoes");
		if (!tbody) return;

		if (!rows || !rows.length) {
			tbody.innerHTML = "<tr><td colspan='6'>Sem histórico de revisão.</td></tr>";
			return;
		}

		tbody.innerHTML = rows
			.map((row) => {
				const resolvido = Number(row.resolvido || 0) === 1 ? "Sim" : "Não";
				return `
                    <tr>
                        <td>${escapeHtml(row.aprovador_label || row.aprovador || "-")}</td>
                        <td>${escapeHtml(row.etapa_label || row.etapa_aprovacao || "-")}</td>
                        <td>${escapeHtml(row.tipo_revisao || "-")}</td>
                        <td>${escapeHtml(row.data_da_revisao || "-")}</td>
                        <td>${escapeHtml(row.comentarios || "-")}</td>
                        <td>${escapeHtml(resolvido)}</td>
                    </tr>
                `;
			})
			.join("");
	}

	function renderDadosGerais(projeto) {
		fillValue("nome_do_projeto", projeto.nome_do_projeto);
		fillValue("status", projeto.status);
		fillValue("coordenador", projeto.coordenador_label || projeto.coordenador);
		fillValue("padrinho_nome", projeto.padrinho_nome || "");
		fillValue("data_de_inicio", projeto.data_de_inicio);
		fillValue("data_de_termino", projeto.data_de_termino);
		fillValue("justificativa", projeto.justificativa);
		fillValue("alinhamento_com_escotismo", projeto.alinhamento_com_escotismo);
		fillValue("competencias", projeto.competencias);
		fillValue("especialidade", projeto.especialidade);
		fillValue("observacoes_e_comentarios", projeto.observacoes_e_comentarios);
		updateGoogleDriveButton(projeto.link_pasta_google_drive);

		renderMarkdownToContainer(
			document.getElementById("view_avaliacao_tap"),
			projeto.avaliacao_tap || ""
		);

		renderTableRows("view_rows_objetivos", projeto.objetivos || [], [
			"objetivo",
			"metrica_de_sucesso",
		]);
		renderTableRows("view_rows_ods", projeto.ods || [], ["ods"]);
		renderTableRows("view_rows_recursos", projeto.recursos || [], ["recurso"]);
		renderTableRows("view_rows_riscos", projeto.riscos || [], ["risco", "mitigacao"]);
		renderReviewRows(projeto.comentarios_revisao_aprovacao || []);

		renderCronogramaGantt(projeto.cronograma || [], "view_cronograma_gantt");
		renderCronogramaGantt(projeto.cronograma || [], "modal_cronograma_gantt");
	}

	function normalizeParticipantRow(row) {
		const tipo = String(row?.tipo_pessoa || "Outro").trim() || "Outro";
		return {
			tipo_pessoa: ["Associado", "Responsavel", "Outro"].includes(tipo) ? tipo : "Outro",
			associado: String(row?.associado || "").trim(),
			responsavel: String(row?.responsavel || "").trim(),
			nome: String(row?.nome || "").trim(),
			email: String(row?.email || "").trim(),
			telefone: String(row?.telefone || "").trim(),
			funcao: String(row?.funcao || "").trim(),
			coordenador: toFlag(row?.coordenador, 0),
			padrinho_orientador: toFlag(row?.padrinho_orientador, 0),
			aprovador: toFlag(row?.aprovador, 0),
			origem_regra_aprovador: String(row?.origem_regra_aprovador || "").trim(),
			permite_remover: toFlag(row?.permite_remover, 1),
			participa_avaliacao: toFlag(row?.participa_avaliacao, 1),
		};
	}

	function getParticipants() {
		return (state.projeto?.envolvidos || []).map(normalizeParticipantRow);
	}

	function buildResponsavelOptionsFromProjeto(projeto) {
		const values = (projeto?.envolvidos || [])
			.map((row) => String(row?.nome || "").trim())
			.filter(Boolean);
		return Array.from(new Set(values)).sort((left, right) =>
			left.localeCompare(right, "pt-BR")
		);
	}

	function renderParticipantsTable() {
		const tbody = document.getElementById("participantsRows");
		if (!tbody) return;

		bindParticipantTableEvents();

		const rows = getParticipants();
		if (!rows.length) {
			tbody.innerHTML = '<tr><td colspan="8">Nenhum envolvido informado.</td></tr>';
			return;
		}

		tbody.innerHTML = rows
			.map((row, index) => {
				const coordinatorChip = row.coordenador
					? '<span class="participant-badge participant-badge--coordenador">Sim</span>'
					: '<span class="participant-badge">Não</span>';
				const sponsorChip = row.padrinho_orientador
					? '<span class="participant-badge participant-badge--padrinho">Sim</span>'
					: '<span class="participant-badge">Não</span>';
				const approverChip = row.aprovador
					? '<span class="participant-badge participant-badge--aprovador">Sim</span>'
					: '<span class="participant-badge">Não</span>';

				const participaDisabled = state.canEdit ? "" : "disabled";
				const participaChecked = row.participa_avaliacao ? "checked" : "";

				return `
                    <tr>
                        <td>${escapeHtml(row.nome || "-")}</td>
                        <td>${escapeHtml(row.email || "-")}</td>
                        <td>${escapeHtml(row.telefone || "-")}</td>
                        <td>${escapeHtml(row.funcao || "-")}</td>
                        <td>${coordinatorChip}</td>
                        <td>${sponsorChip}</td>
                        <td>${approverChip}</td>
                        <td>
                            <label class="switch">
                                <input type="checkbox" role="switch" class="input" data-participa-idx="${index}" ${participaChecked} ${participaDisabled} />
                            </label>
                        </td>
                    </tr>
                `;
			})
			.join("");
	}

	function buildBasecoatSelectHtml(
		id,
		items,
		{ isCombobox = false, searchPlaceholder = "Buscar..." } = {}
	) {
		const optionsHtml = items
			.map(
				(item) =>
					`<div role="option" data-value="${escapeHtml(item.value || "")}">${escapeHtml(
						item.label || item.value || ""
					)}</div>`
			)
			.join("");
		const listboxId = `${id}-listbox`;
		const popoverId = `${id}-popover`;
		const triggerId = `${id}-trigger`;

		const triggerIcon = isCombobox
			? `<svg xmlns="http://www.w3.org/2000/svg" width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round" aria-hidden="true"><path d="m7 15 5 5 5-5"/><path d="m7 9 5-5 5 5"/></svg>`
			: `<svg xmlns="http://www.w3.org/2000/svg" width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round" aria-hidden="true"><path d="m6 9 6 6 6-6"/></svg>`;

		const searchHeader = isCombobox
			? `<header>
                <svg xmlns="http://www.w3.org/2000/svg" width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round" aria-hidden="true"><circle cx="11" cy="11" r="8"/><path d="m21 21-4.3-4.3"/></svg>
                <input type="text" value="" placeholder="${escapeHtml(
					searchPlaceholder
				)}" autocomplete="off" autocorrect="off" spellcheck="false" aria-autocomplete="list" role="combobox" aria-expanded="false" aria-controls="${listboxId}" aria-labelledby="${triggerId}" />
            </header>`
			: "";

		return `<div id="${id}" class="select">
            <button type="button" class="btn-outline" id="${triggerId}" aria-haspopup="listbox" aria-expanded="false" aria-controls="${listboxId}">
                <span class="truncate">Selecione</span>
                ${triggerIcon}
            </button>
            <div id="${popoverId}" data-popover aria-hidden="true">
                ${searchHeader}
                <div role="listbox" id="${listboxId}" tabindex="0">${optionsHtml}</div>
            </div>
            <input type="hidden" name="${id}-value" value="">
        </div>`;
	}

	function populateParticipantSelects() {
		const associadoWrapper = document.getElementById("participant_associado_wrapper");
		const responsavelWrapper = document.getElementById("participant_responsavel_wrapper");

		if (associadoWrapper) {
			associadoWrapper.innerHTML = buildBasecoatSelectHtml(
				"participant_associado",
				state.choices?.associados || [],
				{ isCombobox: true }
			);
		}
		if (responsavelWrapper) {
			responsavelWrapper.innerHTML = buildBasecoatSelectHtml(
				"participant_responsavel",
				state.choices?.responsaveis || [],
				{ isCombobox: true }
			);
		}
	}

	function updateParticipantModalType() {
		const tipo = getSelectComponentValue("participant_tipo_pessoa", "Outro");
		const associadoGroup = document.getElementById("participant_associado_group");
		const responsavelGroup = document.getElementById("participant_responsavel_group");

		const showAssociado = tipo === "Associado";
		const showResponsavel = tipo === "Responsavel";

		if (associadoGroup) associadoGroup.classList.toggle("d-none", !showAssociado);
		if (responsavelGroup) responsavelGroup.classList.toggle("d-none", !showResponsavel);

		if (!showAssociado) {
			setSelectComponentValue("participant_associado", "");
		}
		if (!showResponsavel) {
			setSelectComponentValue("participant_responsavel", "");
		}
	}

	async function preloadParticipantContact(tipoPessoa, docname) {
		const tipo = String(tipoPessoa || "").trim();
		const name = String(docname || "").trim();
		if (!name || !["Associado", "Responsavel"].includes(tipo)) {
			return;
		}

		try {
			const contato = await callApi(METHODS.getContatoPessoa, {
				doctype_name: tipo,
				docname: name,
			});
			const nome = document.getElementById("participant_nome");
			const email = document.getElementById("participant_email");
			const telefone = document.getElementById("participant_telefone");
			if (nome) nome.value = contato.nome || "";
			if (email) email.value = contato.email || "";
			if (telefone) telefone.value = contato.telefone || "";
		} catch (error) {
			showAlert(error.message || "Falha ao carregar dados da pessoa selecionada.", "error");
		}
	}

	function setParticipantModalReadOnly(readOnly) {
		[
			"participant_tipo_pessoa",
			"participant_associado",
			"participant_responsavel",
			"participant_nome",
			"participant_email",
			"participant_telefone",
			"participant_funcao",
			"participant_coordenador",
			"participant_participa_avaliacao",
		].forEach((id) => {
			const el = document.getElementById(id);
			if (el) {
				el.disabled = Boolean(readOnly);
			}
		});

		const saveButton = document.getElementById("btnSalvarParticipante");
		if (saveButton) {
			saveButton.disabled = Boolean(readOnly);
		}
	}

	function openParticipantModal() {
		populateParticipantSelects();

		const row = {
			tipo_pessoa: "Associado",
			associado: "",
			responsavel: "",
			nome: "",
			email: "",
			telefone: "",
			funcao: "",
			coordenador: 0,
			padrinho_orientador: 0,
			aprovador: 0,
			origem_regra_aprovador: "",
			permite_remover: 1,
			participa_avaliacao: 1,
		};

		const title = document.getElementById("participantModalTitle");
		if (title) {
			title.textContent = "Novo envolvido";
		}

		const indexInput = document.getElementById("participant_index");
		if (indexInput) indexInput.value = "";

		const nomeInput = document.getElementById("participant_nome");
		const emailInput = document.getElementById("participant_email");
		const telefoneInput = document.getElementById("participant_telefone");
		const funcaoInput = document.getElementById("participant_funcao");
		const coordenadorInput = document.getElementById("participant_coordenador");
		const participaInput = document.getElementById("participant_participa_avaliacao");

		setSelectComponentValue("participant_tipo_pessoa", row.tipo_pessoa || "Outro");
		setSelectComponentValue("participant_associado", row.associado || "");
		setSelectComponentValue("participant_responsavel", row.responsavel || "");
		if (nomeInput) nomeInput.value = row.nome || "";
		if (emailInput) emailInput.value = row.email || "";
		if (telefoneInput) telefoneInput.value = row.telefone || "";
		if (funcaoInput) funcaoInput.value = row.funcao || "";
		if (coordenadorInput) coordenadorInput.checked = Number(row.coordenador) === 1;
		if (participaInput) participaInput.checked = Number(row.participa_avaliacao) === 1;

		updateParticipantModalType();
		setParticipantModalReadOnly(false);
		openModal("participantModal");
	}

	function collectParticipantModalPayload() {
		const tipo = getSelectComponentValue("participant_tipo_pessoa", "Outro") || "Outro";
		const associado = getSelectComponentValue("participant_associado", "");
		const responsavel = getSelectComponentValue("participant_responsavel", "");
		const nome = (document.getElementById("participant_nome")?.value || "").trim();
		const email = (document.getElementById("participant_email")?.value || "").trim();
		const telefone = (document.getElementById("participant_telefone")?.value || "").trim();
		const funcao = (document.getElementById("participant_funcao")?.value || "").trim();
		const coordenadorFlag = document.getElementById("participant_coordenador")?.checked
			? 1
			: 0;
		const participaAvaliacao = document.getElementById("participant_participa_avaliacao")
			?.checked
			? 1
			: 0;

		if (tipo === "Associado" && !associado) {
			showAlert("Selecione o associado para o envolvido.", "error");
			return null;
		}
		if (tipo === "Responsavel" && !responsavel) {
			showAlert("Selecione o responsável para o envolvido.", "error");
			return null;
		}
		if (!nome || !email || !telefone) {
			showAlert("Preencha nome, email e telefone do envolvido.", "error");
			return null;
		}

		return {
			tipo_pessoa: tipo,
			associado: tipo === "Associado" ? associado : "",
			responsavel: tipo === "Responsavel" ? responsavel : "",
			nome,
			email,
			telefone,
			funcao,
			coordenador: coordenadorFlag,
			participa_avaliacao: participaAvaliacao,
		};
	}

	async function persistParticipants(rows) {
		if (state.participantsSaving) {
			return false;
		}

		state.participantsSaving = true;
		const addButton = document.getElementById("btnNovoParticipante");
		if (addButton) {
			addButton.disabled = true;
		}

		hideAlert();
		try {
			const result = await callApi(METHODS.saveParticipants, {
				projeto_name: state.projetoName,
				envolvidos: JSON.stringify(rows),
			});

			state.projeto = result.projeto || state.projeto || {};
			state.responsavelOptions = buildResponsavelOptionsFromProjeto(state.projeto);

			renderDadosGerais(state.projeto);
			renderParticipantsTable();
			if (state.kanban) {
				state.kanban.setResponsavelOptions(state.responsavelOptions);
				state.kanban.setCanEdit(state.canEdit);
				state.kanban.setTasks(state.projeto?.tarefas || []);
			}
			renderMeetings();
			setEditabilityHints();

			return true;
		} catch (error) {
			showAlert(error.message || "Falha ao salvar envolvidos do projeto.", "error");
			return false;
		} finally {
			state.participantsSaving = false;
			if (addButton) {
				addButton.disabled = !state.canEdit;
			}
		}
	}

	async function saveParticipantFromModal() {
		if (!state.canEdit || state.participantsSaving) {
			return;
		}

		const rows = getParticipants();

		const payload = collectParticipantModalPayload();
		if (!payload) {
			return;
		}

		const nextRow = {
			...payload,
			padrinho_orientador: 0,
			aprovador: 0,
			origem_regra_aprovador: "",
			permite_remover: 1,
		};

		if (nextRow.coordenador) {
			rows.forEach((row) => {
				row.coordenador = 0;
			});
		}

		rows.push(normalizeParticipantRow(nextRow));

		if (!rows.some((row) => Number(row.coordenador) === 1)) {
			showAlert("Defina um coordenador para o projeto.", "error");
			return;
		}

		const ok = await persistParticipants(rows);
		if (ok) {
			closeModal("participantModal");
		}
	}

	async function toggleParticipantEvaluation(index, checked) {
		if (!state.canEdit || state.participantsSaving) {
			return;
		}

		const rows = getParticipants();
		const target = rows[index];
		if (!target) {
			return;
		}

		target.participa_avaliacao = checked ? 1 : 0;
		const ok = await persistParticipants(rows);
		if (!ok) {
			renderParticipantsTable();
		}
	}

	function bindParticipantTableEvents() {
		const participantsRows = document.getElementById("participantsRows");
		if (!participantsRows) {
			return;
		}
		if (participantsRows.dataset.boundParticipantEvents === "1") {
			return;
		}
		participantsRows.dataset.boundParticipantEvents = "1";

		participantsRows.addEventListener("change", (event) => {
			const target = getEventTargetElement(event);
			if (!target) {
				return;
			}

			const participaInput = target.closest("[data-participa-idx]");
			if (!participaInput || !participantsRows.contains(participaInput)) {
				return;
			}

			const idx = Number(participaInput.getAttribute("data-participa-idx"));
			if (!Number.isInteger(idx) || idx < 0) {
				return;
			}

			toggleParticipantEvaluation(idx, Boolean(participaInput.checked));
		});
	}

	function setActiveTab(tabKey) {
		state.activeTab = tabKey;

		const tabs = {
			"dados-gerais": { btn: "tabBtnDadosGerais", panel: "tabDadosGerais" },
			participantes: { btn: "tabBtnParticipantes", panel: "tabParticipantes" },
			tarefas: { btn: "tabBtnTarefas", panel: "tabGestaoTarefas" },
			reunioes: { btn: "tabBtnReunioes", panel: "tabReunioes" },
			avaliacoes: { btn: "tabBtnAvaliacoes", panel: "tabAvaliacoes" },
		};

		if (tabKey === "avaliacoes" && !state.avaliacaoLoaded) {
			loadAvaliacaoData();
		}

		Object.keys(tabs).forEach((key) => {
			const config = tabs[key];
			const btn = document.getElementById(config.btn);
			const panel = document.getElementById(config.panel);
			const active = key === tabKey;
			if (btn) {
				btn.classList.toggle("is-active", active);
				btn.setAttribute("aria-selected", active ? "true" : "false");
			}
			if (panel) {
				panel.classList.toggle("is-active", active);
			}
		});
	}

	function parseDateTimeFlexible(value) {
		const text = String(value || "").trim();
		if (!text) return null;

		const sqlMatch = text.match(
			/^(\d{4})-(\d{2})-(\d{2})[ T](\d{2}):(\d{2})(?::(\d{2}))?(?:\.\d{1,6})?$/
		);
		if (sqlMatch) {
			const year = Number(sqlMatch[1]);
			const month = Number(sqlMatch[2]);
			const day = Number(sqlMatch[3]);
			const hour = Number(sqlMatch[4]);
			const minute = Number(sqlMatch[5]);
			const second = Number(sqlMatch[6] || 0);

			const sqlDate = new Date(year, month - 1, day, hour, minute, second);
			if (!Number.isNaN(sqlDate.getTime())) {
				return sqlDate;
			}
		}

		const normalized = text.includes("T") ? text : text.replace(" ", "T");
		const normalizedMillis = normalized.replace(/\.(\d{3})\d+/, ".$1");
		const direct = new Date(normalizedMillis);
		if (!Number.isNaN(direct.getTime())) {
			return direct;
		}

		const alt = new Date(
			/:\d{2}$/.test(normalizedMillis) ? normalizedMillis : `${normalizedMillis}:00`
		);
		if (!Number.isNaN(alt.getTime())) {
			return alt;
		}

		return null;
	}

	function toDateKey(date) {
		const y = date.getFullYear();
		const m = String(date.getMonth() + 1).padStart(2, "0");
		const d = String(date.getDate()).padStart(2, "0");
		return `${y}-${m}-${d}`;
	}

	function toDatetimeLocalValue(value) {
		const date = parseDateTimeFlexible(value);
		if (!date) return "";

		const y = date.getFullYear();
		const m = String(date.getMonth() + 1).padStart(2, "0");
		const d = String(date.getDate()).padStart(2, "0");
		const h = String(date.getHours()).padStart(2, "0");
		const min = String(date.getMinutes()).padStart(2, "0");
		return `${y}-${m}-${d}T${h}:${min}`;
	}

	function fromDatetimeLocalValue(value) {
		const text = String(value || "").trim();
		if (!text) return "";
		return text.length === 16 ? `${text.replace("T", " ")}:00` : text.replace("T", " ");
	}

	function getMeetingByName(name) {
		return (state.projeto?.reunioes || []).find((item) => (item.name || "") === name) || null;
	}

	function renderMeetings() {
		const calendarEl = document.getElementById("meetingsCalendar");
		if (!calendarEl) return;
		const meetings = state.projeto?.reunioes || [];
		calendarEl.events = meetings.map((m) => ({
			id: m.name,
			title: m.descricao || "-",
			start: m.data_hora,
			all_day: false,
			data: m,
		}));
	}

	function setMeetingModalEditability(editable) {
		const modal = document.getElementById("meetingModal");
		if (!modal) return;

		modal.querySelectorAll("input, textarea").forEach((el) => {
			if (el.id === "meeting_name") return;
			if (el.closest("[data-datepicker]")) return;
			el.disabled = !editable;
		});

		const dpTrigger = modal.querySelector("#meeting_data_hora .datepicker-trigger");
		if (dpTrigger) dpTrigger.disabled = !editable;

		setToastEditorReadOnly(state.meetingEditors.pauta, !editable, "meeting_pauta_editor_host");

		updateMeetingAtaAvailability(editable);

		const saveButton = document.getElementById("btnSalvarReuniao");
		if (saveButton) saveButton.disabled = !editable;
	}

	function openMeetingModal(meetingName) {
		const meeting = meetingName ? getMeetingByName(meetingName) : null;
		state.meetingPersisted = Boolean(meeting?.name);

		document.getElementById("meeting_name").value = meeting?.name || "";
		const dp = document.getElementById("meeting_data_hora");
		if (dp) dp.value = toDatetimeLocalValue(meeting?.data_hora || "");
		document.getElementById("meeting_descricao").value = meeting?.descricao || "";
		const pautaValue = meeting?.pauta || "";
		const ataValue = state.meetingPersisted ? meeting?.ata || "" : "";

		setToastEditorValue(state.meetingEditors.pauta, pautaValue);
		setToastEditorValue(state.meetingEditors.ata, ataValue);

		setMeetingModalEditability(state.canEdit);
		openModal("meetingModal");
	}

	function collectMeetingPayload() {
		const pauta = getToastEditorValue(state.meetingEditors.pauta);
		const ata = getToastEditorValue(state.meetingEditors.ata);
		const dp = document.getElementById("meeting_data_hora");
		const dataHoraIso = dp?.value || "";

		return {
			name: (document.getElementById("meeting_name")?.value || "").trim(),
			data_hora: fromDatetimeLocalValue(dataHoraIso),
			descricao: (document.getElementById("meeting_descricao")?.value || "").trim(),
			pauta,
			ata: state.meetingPersisted ? ata : "",
		};
	}

	async function saveMeeting() {
		if (!state.canEdit || state.loading) return;

		const payload = collectMeetingPayload();
		if (!payload.data_hora) {
			showAlert("Informe data e hora da reunião.", "error");
			return;
		}
		if (!payload.descricao) {
			showAlert("Informe a descrição da reunião.", "error");
			return;
		}

		const saveBtn = document.getElementById("btnSalvarReuniao");
		if (saveBtn) saveBtn.disabled = true;

		hideAlert();
		try {
			const result = await callApi(METHODS.saveMeeting, {
				projeto_name: state.projetoName,
				reuniao: payload,
			});
			state.projeto.reunioes = result.reunioes || [];
			renderMeetings();
			closeModal("meetingModal");
			showAlert("Reunião salva com sucesso.", "success");
		} catch (error) {
			showAlert(error.message || "Falha ao salvar reunião.", "error");
		} finally {
			if (saveBtn) saveBtn.disabled = !state.canEdit;
		}
	}

	function openModal(modalId) {
		const modal = document.getElementById(modalId);
		if (!modal) return;
		modal.showModal();
	}

	function closeModal(modalId) {
		const modal = document.getElementById(modalId);
		if (!modal) return;
		modal.close();
	}

	function getProjectStatusActionConfig(action) {
		if (action === "concluir") {
			return {
				title: "Concluir projeto",
				message:
					"Deseja realmente concluir este projeto? Após confirmar, o status será alterado para Concluído.",
				confirmLabel: "Confirmar conclusão",
				confirmClass: "btn-modern--primary",
				method: METHODS.completeProject,
				errorMessage: "Falha ao concluir o projeto.",
			};
		}

		if (action === "cancelar") {
			return {
				title: "Cancelar projeto",
				message:
					"Deseja realmente cancelar este projeto? Após confirmar, o status será alterado para Cancelado.",
				confirmLabel: "Confirmar cancelamento",
				confirmClass: "btn-modern--danger",
				method: METHODS.cancelProject,
				errorMessage: "Falha ao cancelar o projeto.",
			};
		}

		return null;
	}

	function setProjectStatusButtonsDisabled(disabled) {
		["btnConcluirProjeto", "btnCancelarProjeto"].forEach((id) => {
			const button = document.getElementById(id);
			if (button) {
				button.disabled = disabled;
			}
		});
	}

	function openProjectStatusConfirmModal(action) {
		if (!state.canEdit || state.projectStatusSaving || !state.projetoName) {
			return;
		}

		const config = getProjectStatusActionConfig(action);
		if (!config) {
			return;
		}

		state.projectStatusAction = action;

		const title = document.getElementById("projectStatusConfirmModalTitle");
		const message = document.getElementById("projectStatusConfirmModalMessage");
		const confirmButton = document.getElementById("btnConfirmProjectStatus");

		if (title) {
			title.textContent = config.title;
		}

		if (message) {
			message.textContent = config.message;
		}

		if (confirmButton) {
			confirmButton.textContent = config.confirmLabel;
			confirmButton.classList.remove("btn-modern--primary", "btn-modern--danger");
			confirmButton.classList.add(config.confirmClass);
			confirmButton.disabled = false;
		}

		openModal("projectStatusConfirmModal");
	}

	function closeProjectStatusConfirmModal() {
		state.projectStatusAction = "";
		closeModal("projectStatusConfirmModal");
	}

	async function confirmProjectStatusChange() {
		if (!state.projetoName || state.projectStatusSaving || !state.projectStatusAction) {
			return;
		}

		const config = getProjectStatusActionConfig(state.projectStatusAction);
		if (!config) {
			return;
		}

		const confirmButton = document.getElementById("btnConfirmProjectStatus");
		state.projectStatusSaving = true;
		setProjectStatusButtonsDisabled(true);
		if (confirmButton) {
			confirmButton.disabled = true;
		}

		hideAlert();
		try {
			await callApi(config.method, { projeto_name: state.projetoName });
			window.location.assign("/projetos/visao_geral");
		} catch (error) {
			showAlert(error.message || config.errorMessage, "error");
		} finally {
			state.projectStatusSaving = false;
			if (confirmButton) {
				confirmButton.disabled = false;
			}
			closeProjectStatusConfirmModal();
			setProjectStatusButtonsDisabled(!state.canEdit);
		}
	}

	function setEditabilityHints() {
		const meetingHint = document.getElementById("meetingEditHint");
		const participantsHint = document.getElementById("participantsEditHint");

		if (meetingHint) {
			meetingHint.textContent = state.canEdit
				? "Visualize as reuniões em calendário ou lista, com cadastro e edição."
				: "Você possui acesso de leitura para reuniões neste projeto.";
		}

		if (participantsHint) {
			participantsHint.textContent = state.canEdit
				? "Adicione envolvidos e indique quem participa da avaliação."
				: "Você possui acesso de leitura para os participantes deste projeto.";
		}

		if (state.kanban) {
			state.kanban.setCanEdit(state.canEdit);
			state.kanban.setHint(
				state.canEdit
					? "Arraste cards entre colunas, clique para editar ou crie novas tarefas."
					: "Você possui acesso de leitura para tarefas neste projeto."
			);
		}

		const createMeetingButton = document.getElementById("btnNovaReuniao");
		const addParticipantButton = document.getElementById("btnNovoParticipante");
		if (createMeetingButton) createMeetingButton.disabled = !state.canEdit;
		if (addParticipantButton) addParticipantButton.disabled = !state.canEdit;
		setProjectStatusButtonsDisabled(!state.canEdit || state.projectStatusSaving);
	}

	async function reloadData() {
		if (!state.projetoName || state.loading) return;

		state.loading = true;
		hideAlert();

		try {
			const result = await callApi(METHODS.bootstrap, { projeto_name: state.projetoName });
			state.projeto = result.projeto || {};
			state.responsavelOptions = result.responsavel_options || [];
			state.choices = result.choices || { associados: [], responsaveis: [] };
			state.canEdit = Boolean(result.can_edit);

			renderDadosGerais(state.projeto);
			renderParticipantsTable();
			if (state.kanban) {
				state.kanban.setResponsavelOptions(state.responsavelOptions);
				state.kanban.setCanEdit(state.canEdit);
				state.kanban.setTasks(state.projeto?.tarefas || []);
			}
			renderMeetings();
			setEditabilityHints();
		} catch (error) {
			showAlert(error.message || "Falha ao carregar dados do projeto.", "error");
		} finally {
			state.loading = false;
		}
	}

	function bindEvents() {
		bindParticipantTableEvents();

		const avaliacoesTabBtn = document.getElementById("project-tabs-tab-5");
		if (avaliacoesTabBtn) {
			avaliacoesTabBtn.addEventListener("click", () => {
				if (!state.avaliacaoLoaded) {
					loadAvaliacaoData();
				}
			});
		}

		const openMeetingButton = document.getElementById("btnNovaReuniao");
		if (openMeetingButton) {
			openMeetingButton.addEventListener("click", () => openMeetingModal(""));
		}

		const openParticipantButton = document.getElementById("btnNovoParticipante");
		if (openParticipantButton) {
			openParticipantButton.addEventListener("click", () => openParticipantModal());
		}

		const concludeProjectButton = document.getElementById("btnConcluirProjeto");
		if (concludeProjectButton) {
			concludeProjectButton.addEventListener("click", () =>
				openProjectStatusConfirmModal("concluir")
			);
		}

		const cancelProjectButton = document.getElementById("btnCancelarProjeto");
		if (cancelProjectButton) {
			cancelProjectButton.addEventListener("click", () =>
				openProjectStatusConfirmModal("cancelar")
			);
		}

		const confirmProjectStatusButton = document.getElementById("btnConfirmProjectStatus");
		if (confirmProjectStatusButton) {
			confirmProjectStatusButton.addEventListener("click", confirmProjectStatusChange);
		}

		const saveMeetingButton = document.getElementById("btnSalvarReuniao");
		if (saveMeetingButton) {
			saveMeetingButton.addEventListener("click", saveMeeting);
		}

		const saveParticipantButton = document.getElementById("btnSalvarParticipante");
		if (saveParticipantButton) {
			saveParticipantButton.addEventListener("click", saveParticipantFromModal);
		}

		const participantTipo = document.getElementById("participant_tipo_pessoa");
		if (participantTipo) {
			participantTipo.addEventListener("change", updateParticipantModalType);
		}

		document.addEventListener("change", (event) => {
			if (event.target.id === "participant_associado") {
				preloadParticipantContact("Associado", event.target.value || "");
			} else if (event.target.id === "participant_responsavel") {
				preloadParticipantContact("Responsavel", event.target.value || "");
			}
		});

		const openCronogramaButton = document.getElementById("btnAbrirCronogramaModal");
		if (openCronogramaButton) {
			openCronogramaButton.addEventListener("click", () => {
				openModal("cronogramaModal");
			});
		}

		const meetingsCalendarEl = document.getElementById("meetingsCalendar");
		if (meetingsCalendarEl) {
			const lockMeetingsListVariant = () => {
				if (typeof meetingsCalendarEl.setListVariant === "function") {
					meetingsCalendarEl.setListVariant("default");
				}
			};

			lockMeetingsListVariant();
			meetingsCalendarEl.addEventListener("basecoat:initialized", lockMeetingsListVariant);
			meetingsCalendarEl.addEventListener("gris:calendar:event-click", (event) => {
				const { id } = event.detail;
				if (id) openMeetingModal(id);
			});
		}

		document.addEventListener("click", (event) => {
			const target = getEventTargetElement(event);
			if (!target) {
				return;
			}

			const meetingCard = target.closest(".meeting-card");
			if (meetingCard && meetingCard.dataset.meetingName) {
				openMeetingModal(meetingCard.dataset.meetingName);
			}
		});

		/* ── Avaliação: events ── */
		const btnIniciar = document.getElementById("btnIniciarAvaliacao");
		if (btnIniciar) {
			btnIniciar.addEventListener("click", iniciarAvaliacao);
		}

		const btnSalvarGeral = document.getElementById("btnSalvarAvaliacaoGeral");
		if (btnSalvarGeral) {
			btnSalvarGeral.addEventListener("click", salvarAvaliacaoGeral);
		}

		const btnResumoInd = document.getElementById("btnGerarResumoIndividual");
		if (btnResumoInd) {
			btnResumoInd.addEventListener("click", gerarResumoIndividual);
		}

		const btnResumoComp = document.getElementById("btnGerarResumoCompleto");
		if (btnResumoComp) {
			btnResumoComp.addEventListener("click", gerarResumoCompleto);
		}

		document.addEventListener("click", function (event) {
			var target = getEventTargetElement(event);
			if (!target) {
				return;
			}

			if (target.closest("[data-close-avaliacao-detalhe-modal]")) {
				document.getElementById("avaliacaoDetalheModal")?.close();
				return;
			}
			var reenviarBtn = target.closest("[data-reenviar-idx]");
			if (reenviarBtn) {
				var idx = reenviarBtn.getAttribute("data-reenviar-idx");
				reenviarEmailAvaliacao(idx);
				return;
			}
			var detalheBtn = target.closest("[data-ver-avaliacao-idx]");
			if (detalheBtn) {
				var idx2 = detalheBtn.getAttribute("data-ver-avaliacao-idx");
				abrirDetalheAvaliacao(idx2);
				return;
			}
		});
	}

	/* ══════════════════════════════════
       Avaliação — funções
       ══════════════════════════════════ */

	async function loadAvaliacaoData() {
		var loading = document.getElementById("avaliacaoLoading");
		var empty = document.getElementById("avaliacaoEmpty");
		var noAccess = document.getElementById("avaliacaoNoAccess");
		var content = document.getElementById("avaliacaoContent");

		if (loading) loading.classList.remove("d-none");
		if (empty) empty.classList.add("d-none");
		if (noAccess) noAccess.classList.add("d-none");
		if (content) content.classList.add("d-none");

		try {
			var data = await callApi(METHODS.getAvaliacaoData, {
				projeto_name: state.projetoName,
			});
			state.avaliacaoData = data;
			state.avaliacaoLoaded = true;
			renderAvaliacaoTab(data);
		} catch (err) {
			showAlert(err.message || "Falha ao carregar dados de avaliação.", "error");
		} finally {
			if (loading) loading.classList.add("d-none");
		}
	}

	function renderAvaliacaoTab(data) {
		var empty = document.getElementById("avaliacaoEmpty");
		var noAccess = document.getElementById("avaliacaoNoAccess");
		var content = document.getElementById("avaliacaoContent");

		if (!data || !data.avaliacao_exists) {
			if (data && data.can_start_evaluation) {
				if (empty) empty.classList.remove("d-none");
				if (noAccess) noAccess.classList.add("d-none");
			} else {
				if (empty) empty.classList.add("d-none");
				if (noAccess) noAccess.classList.remove("d-none");
			}
			if (content) content.classList.add("d-none");
			return;
		}

		if (empty) empty.classList.add("d-none");
		if (noAccess) noAccess.classList.add("d-none");
		if (content) content.classList.remove("d-none");

		var avaliacao = data.avaliacao || {};
		var individuais = avaliacao.individuais || [];
		var objetivos = avaliacao.objetivos_atingidos || [];

		/* Progresso */
		var total = individuais.length;
		var concluidas = individuais.filter(function (a) {
			return a.avaliacao_concluida;
		}).length;
		var pct = total > 0 ? Math.round((concluidas / total) * 100) : 0;

		var progressText = document.getElementById("avaliacaoProgressText");
		if (progressText)
			progressText.textContent = concluidas + " de " + total + " avaliações concluídas";

		var progressFill = document.getElementById("avaliacaoProgressFill");
		if (progressFill) progressFill.style.width = pct + "%";

		/* Métricas */
		var metricSatisfacao = document.getElementById("avaliacaoMetricSatisfacao");
		var metricGeral = document.getElementById("avaliacaoMetricGeral");

		if (concluidas > 0) {
			var somaResultado = 0,
				somaSatisfacao = 0;
			individuais.forEach(function (a) {
				if (a.avaliacao_concluida) {
					somaResultado += parseFloat(a.resultado_projeto || 0);
					somaSatisfacao += parseFloat(a.satisfacao_colaboracao || 0);
				}
			});
			if (metricGeral) metricGeral.textContent = (somaResultado / concluidas).toFixed(1);
			if (metricSatisfacao)
				metricSatisfacao.textContent = (somaSatisfacao / concluidas).toFixed(1);
		} else {
			if (metricGeral) metricGeral.textContent = "-";
			if (metricSatisfacao) metricSatisfacao.textContent = "-";
		}

		/* Resumo individual */
		var resumoIndSection = document.getElementById("avaliacaoResumoIndividual");
		var resumoIndContent = document.getElementById("avaliacaoResumoIndividualContent");
		var btnResumoInd = document.getElementById("btnGerarResumoIndividual");
		if (concluidas > 0) {
			if (resumoIndSection) resumoIndSection.classList.remove("d-none");
			var resumoText = avaliacao.resumo_avaliacoes_individuais || "";
			if (resumoIndContent) {
				resumoIndContent.innerHTML = resumoText
					? markdownToHtml(resumoText)
					: "<em>Nenhum resumo gerado ainda.</em>";
			}
			if (btnResumoInd && data.can_edit_general) {
				btnResumoInd.classList.remove("d-none");
			} else if (btnResumoInd) {
				btnResumoInd.classList.add("d-none");
			}
		} else {
			if (resumoIndSection) resumoIndSection.classList.add("d-none");
		}

		/* Lista de avaliadores */
		var listEl = document.getElementById("avaliacaoAvaliadoresList");
		if (listEl) {
			var html = "";
			individuais.forEach(function (a, i) {
				var statusClass = a.avaliacao_concluida
					? "aval-avaliador--concluido"
					: "aval-avaliador--pendente";
				var statusLabel = a.avaliacao_concluida ? "Concluída" : "Pendente";
				var statusBadgeClass = a.avaliacao_concluida
					? "badge badge-success"
					: "badge badge-secondary";
				html += '<div class="aval-avaliador ' + statusClass + '">';
				html += '<div class="aval-avaliador__info">';
				html +=
					'<span class="aval-avaliador__nome">' + escapeHtml(a.avaliador) + "</span>";
				html += '<span class="' + statusBadgeClass + '">' + statusLabel + "</span>";
				html += "</div>";
				html += '<div class="aval-avaliador__actions">';
				if (a.avaliacao_concluida) {
					html +=
						'<button type="button" class="btn-sm-outline" data-ver-avaliacao-idx="' +
						a.idx +
						'">Ver detalhes</button>';
				} else if (data.can_edit_general) {
					html +=
						'<button type="button" class="btn-sm-outline" data-reenviar-idx="' +
						a.idx +
						'">Reenviar e-mail e WhatsApp</button>';
				}
				html += "</div></div>";
			});
			listEl.innerHTML = html;
		}

		/* Objetivos */
		var objBody = document.getElementById("avaliacaoObjetivosBody");
		if (objBody) {
			var objHtml = "";
			if (objetivos.length === 0) {
				objHtml =
					'<tr><td colspan="3" class="text-center">Nenhum objetivo cadastrado</td></tr>';
			} else {
				var objAtingidoItems = [
					{ value: "", label: "Selecione" },
					{ value: "Completamente", label: "Completamente" },
					{ value: "Parcialmente", label: "Parcialmente" },
					{ value: "Nao", label: "Não" },
				];
				objetivos.forEach(function (obj, i) {
					var disabledAttr = data.can_edit_general ? "" : " disabled";
					var selectId = "aval_obj_sel_" + i;
					objHtml += "<tr>";
					objHtml += "<td>" + escapeHtml(obj.objetivo || "") + "</td>";
					objHtml +=
						"<td>" + buildBasecoatSelectHtml(selectId, objAtingidoItems) + "</td>";
					objHtml +=
						'<td><input type="text" class="form-input-modern form-input-modern--sm aval-obj-motivo" data-obj-idx="' +
						i +
						'" value="' +
						escapeHtml(obj.porque_nao_foi_atingido || "") +
						'"' +
						disabledAttr +
						' placeholder="Opcional" /></td>';
					objHtml += "</tr>";
				});
			}
			objBody.innerHTML = objHtml;
			objetivos.forEach(function (obj, i) {
				var selectId = "aval_obj_sel_" + i;
				var currentValue = obj.objetivo_atingido || "";
				var selectEl = document.getElementById(selectId);
				if (selectEl) {
					if (currentValue) {
						var optionEl = selectEl.querySelector(
							'[role="option"][data-value="' + currentValue + '"]'
						);
						var labelText = optionEl ? optionEl.textContent.trim() : currentValue;
						var btnLabel = selectEl.querySelector("button > span.truncate");
						var hiddenInput = selectEl.querySelector(':scope > input[type="hidden"]');
						if (btnLabel) btnLabel.textContent = labelText;
						if (hiddenInput) hiddenInput.value = currentValue;
					}
					if (!data.can_edit_general) {
						var triggerBtn = selectEl.querySelector(":scope > button");
						if (triggerBtn) triggerBtn.disabled = true;
					}
				}
			});
			document.dispatchEvent(new CustomEvent("gris:design-system:init"));
			initObjSelectsFloating();
		}

		/* Campos da avaliação geral */
		var geralFieldMap = {
			funcionou_bem: "o_que_funcionou_bem_na_dinamica_da_equipe",
			nao_funcionou: "o_que_nao_funcionou_na_dinamica_da_equipe",
			aprendizado: "maior_aprendizado_gerado",
			impacto: "impacto_gerado_para_comunidade",
			pontos_positivos: "pontos_positivos_adicionais",
			pontos_melhoria: "pontos_de_melhoria_adicionais",
		};
		Object.keys(geralFieldMap).forEach(function (shortName) {
			var el = document.getElementById("aval_" + shortName);
			if (el) {
				el.value = avaliacao[geralFieldMap[shortName]] || "";
				if (!data.can_edit_general) el.disabled = true;
			}
		});

		var btnSalvar = document.getElementById("btnSalvarAvaliacaoGeral");
		if (btnSalvar) {
			btnSalvar.style.display = data.can_edit_general ? "" : "none";
		}

		/* Resumo completo */
		var resumoCompSection = document.getElementById("avaliacaoResumoCompleto");
		var resumoCompContent = document.getElementById("avaliacaoResumoCompletoContent");
		var btnResumoComp = document.getElementById("btnGerarResumoCompleto");

		if (resumoCompSection) resumoCompSection.classList.remove("d-none");
		var resumoCompText = avaliacao.resumo_avaliacao_completa || "";
		if (resumoCompContent) {
			resumoCompContent.innerHTML = resumoCompText
				? markdownToHtml(resumoCompText)
				: "<em>Nenhum resumo gerado ainda.</em>";
		}
		if (btnResumoComp && data.can_edit_general) {
			btnResumoComp.classList.remove("d-none");
		} else if (btnResumoComp) {
			btnResumoComp.classList.add("d-none");
		}
	}

	function initObjSelectsFloating() {
		var objBody = document.getElementById("avaliacaoObjetivosBody");
		if (!objBody || objBody.dataset.floatingObserver === "1") return;
		objBody.dataset.floatingObserver = "1";

		var observer = new MutationObserver(function (mutations) {
			mutations.forEach(function (mutation) {
				if (mutation.type !== "attributes" || mutation.attributeName !== "aria-hidden")
					return;
				var popover = mutation.target;
				if (!popover.hasAttribute("data-popover")) return;
				var selectEl = popover.closest(".select");
				if (!selectEl || !objBody.contains(selectEl)) return;
				var trigger = selectEl.querySelector(":scope > button");
				if (!trigger) return;
				var isOpen = popover.getAttribute("aria-hidden") === "false";
				if (isOpen) {
					var rect = trigger.getBoundingClientRect();
					popover.style.position = "fixed";
					popover.style.top = rect.bottom + "px";
					popover.style.left = rect.left + "px";
					popover.style.minWidth = rect.width + "px";
					popover.style.zIndex = "9999";
				} else {
					popover.style.position = "";
					popover.style.top = "";
					popover.style.left = "";
					popover.style.minWidth = "";
					popover.style.zIndex = "";
				}
			});
		});

		observer.observe(objBody, {
			subtree: true,
			attributes: true,
			attributeFilter: ["aria-hidden"],
		});
	}

	async function iniciarAvaliacao() {
		var btn = document.getElementById("btnIniciarAvaliacao");
		if (btn) {
			btn.disabled = true;
			btn.textContent = "Iniciando...";
		}

		try {
			await callApi(METHODS.iniciarAvaliacao, { projeto_name: state.projetoName });
			state.avaliacaoLoaded = false;
			await loadAvaliacaoData();
		} catch (err) {
			showAlert(err.message || "Falha ao iniciar avaliação.", "error");
			if (btn) {
				btn.disabled = false;
				btn.textContent = "Iniciar avaliação";
			}
		}
	}

	async function salvarAvaliacaoGeral() {
		if (state.avaliacaoSaving) return;
		state.avaliacaoSaving = true;

		var btn = document.getElementById("btnSalvarAvaliacaoGeral");
		if (btn) {
			btn.disabled = true;
			btn.textContent = "Salvando...";
		}

		var avaliacao = state.avaliacaoData?.avaliacao || {};
		var objetivos = avaliacao.objetivos_atingidos || [];

		var objData = [];
		objetivos.forEach(function (obj, i) {
			var motEl = document.querySelector('.aval-obj-motivo[data-obj-idx="' + i + '"]');
			objData.push({
				objetivo: obj.objetivo || "",
				objetivo_atingido:
					getSelectComponentValue("aval_obj_sel_" + i) || obj.objetivo_atingido || "",
				porque_nao_foi_atingido: motEl ? motEl.value : obj.porque_nao_foi_atingido || "",
			});
		});

		var data = {
			objetivos_atingidos: objData,
			o_que_funcionou_bem_na_dinamica_da_equipe:
				(document.getElementById("aval_funcionou_bem") || {}).value || "",
			o_que_nao_funcionou_na_dinamica_da_equipe:
				(document.getElementById("aval_nao_funcionou") || {}).value || "",
			maior_aprendizado_gerado:
				(document.getElementById("aval_aprendizado") || {}).value || "",
			impacto_gerado_para_comunidade:
				(document.getElementById("aval_impacto") || {}).value || "",
			pontos_positivos_adicionais:
				(document.getElementById("aval_pontos_positivos") || {}).value || "",
			pontos_de_melhoria_adicionais:
				(document.getElementById("aval_pontos_melhoria") || {}).value || "",
		};

		try {
			await callApi(METHODS.salvarAvaliacaoGeral, {
				projeto_name: state.projetoName,
				data: JSON.stringify(data),
			});
			state.avaliacaoLoaded = false;
			await loadAvaliacaoData();
		} catch (err) {
			showAlert(err.message || "Falha ao salvar avaliação geral.", "error");
		} finally {
			state.avaliacaoSaving = false;
			if (btn) {
				btn.disabled = false;
				btn.textContent = "Salvar avaliação geral";
			}
		}
	}

	async function reenviarEmailAvaliacao(avaliadorIdx) {
		var btn = document.querySelector('[data-reenviar-idx="' + avaliadorIdx + '"]');
		if (btn) {
			btn.disabled = true;
			btn.textContent = "Enviando...";
		}

		try {
			var result = await callApi(METHODS.reenviarEmailAvaliacao, {
				projeto_name: state.projetoName,
				avaliador_idx: avaliadorIdx,
			});
			if (btn) {
				btn.textContent =
					result && result.whatsapp_sent ? "Convite reenviado!" : "E-mail reenviado";
				setTimeout(function () {
					btn.disabled = false;
					btn.textContent = "Reenviar e-mail e WhatsApp";
				}, 3000);
			}
		} catch (err) {
			showAlert(err.message || "Falha ao reenviar convite.", "error");
			if (btn) {
				btn.disabled = false;
				btn.textContent = "Reenviar e-mail e WhatsApp";
			}
		}
	}

	async function gerarResumoIndividual() {
		var btn = document.getElementById("btnGerarResumoIndividual");
		if (btn) {
			btn.disabled = true;
			btn.textContent = "Gerando resumo...";
		}

		try {
			await callApi(METHODS.solicitarResumoIndividual, { projeto_name: state.projetoName });
			iniciarPollingResumo("individual");
		} catch (err) {
			showAlert(err.message || "Falha ao solicitar resumo.", "error");
			if (btn) {
				btn.disabled = false;
				btn.textContent = "Gerar resumo individual";
			}
		}
	}

	async function gerarResumoCompleto() {
		var btn = document.getElementById("btnGerarResumoCompleto");
		if (btn) {
			btn.disabled = true;
			btn.textContent = "Gerando resumo...";
		}

		try {
			await callApi(METHODS.solicitarResumoCompleto, { projeto_name: state.projetoName });
			iniciarPollingResumo("completo");
		} catch (err) {
			showAlert(err.message || "Falha ao solicitar resumo.", "error");
			if (btn) {
				btn.disabled = false;
				btn.textContent = "Gerar avaliação completa";
			}
		}
	}

	function iniciarPollingResumo(tipo) {
		if (state.avaliacaoResumoPolling) {
			clearInterval(state.avaliacaoResumoPolling);
		}

		state.avaliacaoResumoPolling = setInterval(async function () {
			try {
				var result = await callApi(METHODS.consultarResumo, {
					projeto_name: state.projetoName,
				});

				if (tipo === "individual") {
					var resumo = result.resumo_individuais || "";
					if (
						resumo &&
						resumo.indexOf("Gerando") === -1 &&
						resumo.indexOf("processamento") === -1
					) {
						clearInterval(state.avaliacaoResumoPolling);
						state.avaliacaoResumoPolling = null;
						state.avaliacaoLoaded = false;
						await loadAvaliacaoData();
					}
				} else {
					var resumoC = result.resumo_completo || "";
					if (
						resumoC &&
						resumoC.indexOf("Gerando") === -1 &&
						resumoC.indexOf("processamento") === -1
					) {
						clearInterval(state.avaliacaoResumoPolling);
						state.avaliacaoResumoPolling = null;
						state.avaliacaoLoaded = false;
						await loadAvaliacaoData();
					}
				}
			} catch (e) {
				clearInterval(state.avaliacaoResumoPolling);
				state.avaliacaoResumoPolling = null;
			}
		}, 5000);
	}

	function abrirDetalheAvaliacao(idx) {
		var avaliacao = state.avaliacaoData?.avaliacao || {};
		var individuais = avaliacao.individuais || [];
		var item = individuais.find(function (a) {
			return String(a.idx) === String(idx);
		});
		if (!item) return;

		var contentEl = document.getElementById("avaliacaoDetalheContent");
		if (!contentEl) return;

		var titleEl = document.getElementById("avaliacaoDetalheModalTitle");
		if (titleEl) titleEl.textContent = "Avaliação de " + escapeHtml(item.avaliador);

		var html = '<div class="aval-detalhe-grid">';
		html +=
			'<div class="aval-detalhe-item"><label class="form-label-modern">Resultado do projeto</label><p>' +
			escapeHtml(item.resultado_projeto) +
			" / 10</p></div>";
		html +=
			'<div class="aval-detalhe-item"><label class="form-label-modern">Satisfação em colaborar</label><p>' +
			escapeHtml(item.satisfacao_colaboracao) +
			" / 10</p></div>";
		html +=
			'<div class="aval-detalhe-item aval-detalhe-item--full"><label class="form-label-modern">Objetivos atingidos</label><p>' +
			escapeHtml(item.objetivos_atingidos || "-") +
			"</p></div>";
		html +=
			'<div class="aval-detalhe-item aval-detalhe-item--full"><label class="form-label-modern">O que foi muito bom</label><p>' +
			escapeHtml(item.muito_bom || "-") +
			"</p></div>";
		html +=
			'<div class="aval-detalhe-item aval-detalhe-item--full"><label class="form-label-modern">Pontos de melhoria</label><p>' +
			escapeHtml(item.pontos_melhoria || "-") +
			"</p></div>";
		html += "</div>";

		contentEl.innerHTML = html;
		openModal("avaliacaoDetalheModal");
	}

	function initKanban() {
		if (!window.GrisKanbanTarefas) return;
		state.kanban = new window.GrisKanbanTarefas("#taskKanban", {
			mode: "projeto",
			currentUser: String(window.frappe?.session?.user || ""),
			currentUserFullName: String(window.frappe?.session?.user || ""),
			canEdit: state.canEdit,
			responsavelOptions: state.responsavelOptions,
			onSaveTask: async (payload) => {
				const result = await callApi(METHODS.saveTask, {
					projeto_name: state.projetoName,
					tarefa: payload,
				});
				state.projeto.tarefas = result.tarefas || [];
				return { tarefas: state.projeto.tarefas };
			},
			onMoveTask: async (taskName, status) => {
				const result = await callApi(METHODS.moveTask, {
					projeto_name: state.projetoName,
					tarefa_name: taskName,
					status,
				});
				state.projeto.tarefas = result.tarefas || [];
				return { tarefas: state.projeto.tarefas };
			},
			onLoadComments: async (taskName) => {
				const result = await callApi(METHODS.getTaskComments, {
					projeto_name: state.projetoName,
					tarefa_name: taskName,
				});
				return { comentarios: result.comentarios || [] };
			},
			onAddComment: async (taskName, texto) => {
				const result = await callApi(METHODS.addTaskComment, {
					projeto_name: state.projetoName,
					tarefa_name: taskName,
					conteudo: texto,
				});
				return { comentarios: result.comentarios || [] };
			},
			onEditComment: async (commentName, texto) => {
				const result = await callApi(METHODS.editTaskComment, {
					projeto_name: state.projetoName,
					tarefa_name: state.kanban?.activeTask?.name || "",
					comentario_name: commentName,
					conteudo: texto,
				});
				return { comentarios: result.comentarios || [] };
			},
			onDeleteComment: async (commentName) => {
				const result = await callApi(METHODS.deleteTaskComment, {
					projeto_name: state.projetoName,
					tarefa_name: state.kanban?.activeTask?.name || "",
					comentario_name: commentName,
				});
				return { comentarios: result.comentarios || [] };
			},
		});
	}

	async function bootstrap() {
		state.projetoName = getProjetoName();
		if (!state.projetoName) {
			showAlert("Projeto não informado na URL.", "error");
			return;
		}

		setActiveTab("dados-gerais");
		bindEvents();
		initKanban();
		await reloadData();
		initMeetingEditors().catch(() => {
			state.meetingEditors = { pauta: null, ata: null };
		});
	}

	document.addEventListener("DOMContentLoaded", bootstrap);
})();
