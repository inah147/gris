(function () {
    const METHODS = {
        bootstrap: "gris.gestao_de_projetos.doctype.projeto.projeto.get_projeto_aprovacao_data",
        iniciarProjeto: "gris.gestao_de_projetos.doctype.projeto.projeto.iniciar_execucao_projeto",
        cancelProject: "gris.gestao_de_projetos.doctype.projeto.projeto.cancelar_projeto",
    };

    const state = {
        projetoName: "",
        loading: false,
        cancelProjectSaving: false,
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

    function showAlert(message, type) {
        const el = document.getElementById("approvalAlert");
        if (!el) return;
        el.classList.remove("d-none", "alert-modern--error", "alert-modern--success");
        el.classList.add(type === "error" ? "alert-modern--error" : "alert-modern--success");
        el.textContent = message;
    }

    function hideAlert() {
        const el = document.getElementById("approvalAlert");
        if (!el) return;
        el.classList.add("d-none");
        el.textContent = "";
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
                        reject(new Error(extractServerMessage(r) || "Erro ao processar requisição."));
                        return;
                    }
                    resolve(r.message || {});
                },
                error: (err) => {
                    const message = err && err.message ? err.message : "Erro de comunicação com o servidor.";
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

    function setActionButtonsDisabled(disabled) {
        ["btnIniciarProjeto", "btnCancelarProjeto", "btnConfirmarCancelarProjeto"].forEach((id) => {
            const btn = document.getElementById(id);
            if (btn) btn.disabled = disabled;
        });
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

    function sanitizeRenderedHtml(html) {
        const container = document.createElement("div");
        container.innerHTML = html || "";

        container
            .querySelectorAll("script, style, iframe, object, embed, link, meta, base, form")
            .forEach((node) => node.remove());

        container.querySelectorAll("*").forEach((node) => {
            Array.from(node.attributes).forEach((attribute) => {
                const name = String(attribute.name || "").toLowerCase();
                const value = String(attribute.value || "").trim().toLowerCase();

                if (name.startsWith("on") || name === "srcdoc") {
                    node.removeAttribute(attribute.name);
                    return;
                }

                if ((name === "href" || name === "src") && (value.startsWith("javascript:") || value.startsWith("data:text/html"))) {
                    node.removeAttribute(attribute.name);
                }
            });
        });

        return container.innerHTML;
    }

    function renderSimpleMarkdown(text) {
        return escapeHtml(text || "")
            .replace(/\*\*(.+?)\*\*/g, "<strong>$1</strong>")
            .replace(/\*(.+?)\*/g, "<em>$1</em>")
            .replace(/\n/g, "<br>");
    }

    function renderMarkdownToContainer(el, value) {
        if (!el) return;
        if (!value) {
            el.textContent = "-";
            return;
        }

        if (window.frappe && typeof frappe.markdown === "function") {
            el.innerHTML = sanitizeRenderedHtml(frappe.markdown(value || ""));
            return;
        }
        el.innerHTML = renderSimpleMarkdown(value || "");
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
        return date.toLocaleDateString("pt-BR", { day: "2-digit", month: "2-digit", year: "numeric" });
    }

    function renderCronogramaGantt(rows) {
        const container = document.getElementById("view_cronograma_gantt");
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
            container.innerHTML = '<div class="cronograma-gantt__empty">Nenhuma atividade com período válido para exibir no Gantt.</div>';
            return;
        }

        const minStart = tasks.reduce((acc, task) => (task.start < acc ? task.start : acc), tasks[0].start);
        const maxEnd = tasks.reduce((acc, task) => (task.end > acc ? task.end : acc), tasks[0].end);
        const chartStart = addDays(minStart, -1);
        const chartEnd = addDays(maxEnd, 1);
        const totalDays = Math.max(diffDays(chartStart, chartEnd) + 1, 2);

        const tickEvery = totalDays > 45 ? 7 : totalDays > 20 ? 3 : 1;
        const ticks = [];
        for (let day = 0; day < totalDays; day += tickEvery) {
            const date = addDays(chartStart, day);
            ticks.push(
                `<div class="cronograma-gantt__tick" style="left:${(day / totalDays) * 100}%">${date.toLocaleDateString("pt-BR", { day: "2-digit", month: "2-digit" })}</div>`
            );
        }

        const rowsHtml = tasks
            .map((task) => {
                const offsetDays = diffDays(chartStart, task.start);
                const durationDays = Math.max(diffDays(task.start, task.end) + 1, 1);
                const leftPct = (offsetDays / totalDays) * 100;
                const widthPct = (durationDays / totalDays) * 100;
                const tooltip = `Início: ${formatDatePtBr(task.start)} | Término: ${formatDatePtBr(task.end)}`;

                return `
                    <div class="cronograma-gantt__row">
                        <div class="cronograma-gantt__label" title="${escapeHtml(task.tarefa)}">${escapeHtml(task.tarefa)}</div>
                        <div class="cronograma-gantt__lane">
                            <div class="cronograma-gantt__bar" style="left:${leftPct}%;width:${widthPct}%;" title="${escapeHtml(tooltip)}">
                                <span class="cronograma-gantt__bar-text">${escapeHtml(task.tarefa)}</span>
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

    function renderFlow(approval) {
        const flow = document.getElementById("approvalFlow");
        if (!flow) return;

        const stages = approval?.stages || [];
        if (!stages.length) {
            flow.innerHTML = "<p>Nenhuma etapa configurada.</p>";
            return;
        }

        flow.innerHTML = stages
            .map((stage) => {
                const classes = ["approval-flow__step"];
                if (stage.completed) classes.push("is-done");
                if (stage.is_current) classes.push("is-current");

                const approvers = (stage.approvers || []).map((item) => item.label || item.name).filter(Boolean).join(", ");
                const statusLabel = stage.completed ? "Concluída" : stage.is_current ? "Etapa atual" : "Pendente";
                return `
                    <article class="${classes.join(" ")}">
                        <h4 class="approval-flow__label">${escapeHtml(stage.label || "Etapa")}</h4>
                        <p class="approval-flow__meta"><strong>Status:</strong> ${escapeHtml(statusLabel)}</p>
                        <p class="approval-flow__meta"><strong>Aprovadores elegíveis:</strong> ${escapeHtml(approvers || "Não definido")}</p>
                    </article>
                `;
            })
            .join("");
    }

    function fillProjeto(projeto, approval) {
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

        renderMarkdownToContainer(document.getElementById("view_avaliacao_tap"), projeto.avaliacao_tap || "");

        renderTableRows("view_rows_equipe", projeto.equipe_de_interesse || [], ["nome", "email", "telefone", "funcao"]);
        renderTableRows("view_rows_objetivos", projeto.objetivos || [], ["objetivo", "metrica_de_sucesso"]);
        renderTableRows("view_rows_ods", projeto.ods || [], ["ods"]);
        renderCronogramaGantt(projeto.cronograma || []);
        renderTableRows("view_rows_recursos", projeto.recursos || [], ["recurso"]);
        renderTableRows("view_rows_riscos", projeto.riscos || [], ["risco", "mitigacao"]);
        renderReviewRows(projeto.comentarios_revisao_aprovacao || []);

        renderFlow(approval || {});
    }

    async function reloadData() {
        if (!state.projetoName || state.loading) return;

        state.loading = true;
        hideAlert();

        try {
            const result = await callApi(METHODS.bootstrap, { projeto_name: state.projetoName });
            fillProjeto(result.projeto || {}, result.approval || {});
        } catch (error) {
            showAlert(error.message || "Falha ao carregar dados do projeto aprovado.", "error");
        } finally {
            state.loading = false;
        }
    }

    async function iniciarProjeto() {
        if (!state.projetoName || state.loading) return;

        setActionButtonsDisabled(true);
        hideAlert();

        try {
            await callApi(METHODS.iniciarProjeto, { projeto_name: state.projetoName });
            showAlert("Projeto iniciado com sucesso.", "success");
            window.location.assign("/projetos/visao_geral");
        } catch (error) {
            showAlert(error.message || "Falha ao iniciar projeto.", "error");
            setActionButtonsDisabled(false);
        }
    }

    function openCancelarProjetoModal() {
        const modal = document.getElementById("cancelarProjetoModal");
        if (!modal) return;
        modal.classList.remove("d-none");
        modal.setAttribute("aria-hidden", "false");
        document.body.classList.add("info-modal-open");
    }

    function closeCancelarProjetoModal() {
        const modal = document.getElementById("cancelarProjetoModal");
        if (!modal) return;
        modal.classList.add("d-none");
        modal.setAttribute("aria-hidden", "true");
        document.body.classList.remove("info-modal-open");
    }

    async function cancelarProjeto() {
        if (!state.projetoName || state.loading || state.cancelProjectSaving) return;

        state.cancelProjectSaving = true;
        setActionButtonsDisabled(true);
        hideAlert();

        try {
            await callApi(METHODS.cancelProject, { projeto_name: state.projetoName });
            closeCancelarProjetoModal();
            window.location.assign("/projetos/visao_geral");
        } catch (error) {
            showAlert(error.message || "Falha ao cancelar projeto.", "error");
            state.cancelProjectSaving = false;
            setActionButtonsDisabled(false);
        }
    }

    function bindEvents() {
        const btnIniciarProjeto = document.getElementById("btnIniciarProjeto");
        const btnCancelarProjeto = document.getElementById("btnCancelarProjeto");
        const btnConfirmarCancelarProjeto = document.getElementById("btnConfirmarCancelarProjeto");
        if (btnIniciarProjeto) {
            btnIniciarProjeto.addEventListener("click", iniciarProjeto);
        }
        if (btnCancelarProjeto) {
            btnCancelarProjeto.addEventListener("click", openCancelarProjetoModal);
        }
        if (btnConfirmarCancelarProjeto) {
            btnConfirmarCancelarProjeto.addEventListener("click", cancelarProjeto);
        }

        document.querySelectorAll("[data-close-cancelar-projeto]").forEach((btn) => {
            btn.addEventListener("click", closeCancelarProjetoModal);
        });

        document.addEventListener("keydown", (event) => {
            if (event.key === "Escape") {
                closeCancelarProjetoModal();
            }
        });
    }

    async function bootstrap() {
        state.projetoName = getProjetoName();
        if (!state.projetoName) {
            showAlert("Projeto não informado na URL.", "error");
            return;
        }

        bindEvents();
        await reloadData();
    }

    document.addEventListener("DOMContentLoaded", bootstrap);
})();
