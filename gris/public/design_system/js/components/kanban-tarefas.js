/* GRIS Design System — Kanban de Tarefas
 * Componente reutilizavel para gestao de tarefas (modos "projeto" e "pessoal").
 * Expoe window.GrisKanbanTarefas com a API publica documentada no construtor.
 */
(function () {
    "use strict";

    const TASK_STATUS_ORDER = ["Nao iniciado", "Em andamento", "Atrasado", "Concluido", "Cancelado"];
    const TASK_STATUS_LABELS = {
        "Nao iniciado": "Nao iniciado",
        "Em andamento": "Em andamento",
        Atrasado: "Atrasado",
        Concluido: "Concluido",
        Cancelado: "Cancelado",
    };
    const MS_PER_DAY = 24 * 60 * 60 * 1000;

    /* ───────────────── Helpers de string/datas ───────────────── */
    function escapeHtml(value) {
        return String(value ?? "").replace(/[&<>"']/g, (ch) => (
            { "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;", "'": "&#39;" }[ch]
        ));
    }

    function parseDateFlexible(value) {
        const text = String(value || "").trim();
        if (!text) return null;
        const isoMatch = text.match(/^(\d{4})-(\d{2})-(\d{2})$/);
        if (isoMatch) {
            const date = new Date(Number(isoMatch[1]), Number(isoMatch[2]) - 1, Number(isoMatch[3]));
            if (!Number.isNaN(date.getTime())) {
                date.setHours(0, 0, 0, 0);
                return date;
            }
        }
        const brMatch = text.match(/^(\d{2})\/(\d{2})\/(\d{4})$/);
        if (brMatch) {
            const date = new Date(Number(brMatch[3]), Number(brMatch[2]) - 1, Number(brMatch[1]));
            if (!Number.isNaN(date.getTime())) {
                date.setHours(0, 0, 0, 0);
                return date;
            }
        }
        return null;
    }

    function parseDateTimeFlexible(value) {
        const text = String(value || "").trim();
        if (!text) return null;
        const sqlMatch = text.match(/^(\d{4})-(\d{2})-(\d{2})[ T](\d{2}):(\d{2})(?::(\d{2}))?(?:\.\d{1,6})?$/);
        if (sqlMatch) {
            const d = new Date(
                Number(sqlMatch[1]),
                Number(sqlMatch[2]) - 1,
                Number(sqlMatch[3]),
                Number(sqlMatch[4]),
                Number(sqlMatch[5]),
                Number(sqlMatch[6] || 0),
            );
            if (!Number.isNaN(d.getTime())) return d;
        }
        const normalized = text.includes("T") ? text : text.replace(" ", "T");
        const direct = new Date(normalized);
        if (!Number.isNaN(direct.getTime())) return direct;
        return null;
    }

    function formatTaskDeadline(value) {
        const date = parseDateFlexible(value);
        if (!date) return "Sem prazo";
        return date.toLocaleDateString("pt-BR", { day: "2-digit", month: "2-digit", year: "numeric" });
    }

    function formatTaskTimelineDate(value, fallback) {
        const date = parseDateFlexible(value);
        if (!date) return fallback || "-";
        return date.toLocaleDateString("pt-BR", { day: "2-digit", month: "2-digit", year: "numeric" });
    }

    function formatCommentDate(value) {
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

    function getTodayIso() {
        const now = new Date();
        const y = now.getFullYear();
        const m = String(now.getMonth() + 1).padStart(2, "0");
        const d = String(now.getDate()).padStart(2, "0");
        return `${y}-${m}-${d}`;
    }

    function diffDays(a, b) {
        return Math.round((b.getTime() - a.getTime()) / MS_PER_DAY);
    }

    function getInitials(name) {
        const words = String(name || "").trim().split(/\s+/).filter(Boolean);
        if (!words.length) return "--";
        const first = words[0][0] || "";
        const second = words.length > 1 ? words[words.length - 1][0] || "" : words[0][1] || "";
        return `${first}${second}`.toUpperCase();
    }

    /* ───────────────── Sanitizacao/markdown ───────────────── */
    function sanitizeHtml(html) {
        const container = document.createElement("div");
        container.innerHTML = html || "";
        container
            .querySelectorAll("script, style, iframe, object, embed, link, meta, base, form")
            .forEach((node) => node.remove());
        container.querySelectorAll("*").forEach((node) => {
            Array.from(node.attributes).forEach((attr) => {
                const name = String(attr.name || "").toLowerCase();
                const value = String(attr.value || "").trim().toLowerCase();
                if (name.startsWith("on") || name === "srcdoc") {
                    node.removeAttribute(attr.name);
                    return;
                }
                if ((name === "href" || name === "src") && (value.startsWith("javascript:") || value.startsWith("data:text/html"))) {
                    node.removeAttribute(attr.name);
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
            .replace(/\[(.+?)\]\((https?:\/\/[^\s)]+)\)/g, '<a href="$2" target="_blank" rel="noopener noreferrer">$1</a>')
            .replace(/\n/g, "<br>");
    }

    function markdownToHtml(value) {
        if (!value) return "-";
        if (window.frappe && typeof window.frappe.markdown === "function") {
            return sanitizeHtml(window.frappe.markdown(value));
        }
        return renderSimpleMarkdown(value);
    }

    /* ───────────────── Builders de Basecoat ───────────────── */
    function buildSelectHtml(id, items, { isCombobox = false, searchPlaceholder = "Buscar..." } = {}) {
        const optionsHtml = items
            .map((item) => `<div role="option" data-value="${escapeHtml(item.value || "")}">${escapeHtml(item.label || item.value || "")}</div>`)
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
                <input type="text" value="" placeholder="${escapeHtml(searchPlaceholder)}" autocomplete="off" autocorrect="off" spellcheck="false" aria-autocomplete="list" role="combobox" aria-expanded="false" aria-controls="${listboxId}" aria-labelledby="${triggerId}" />
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

    function buildDatepickerHtml(id, isoValue) {
        const spriteBase = "/assets/gris/design_system/icons/lucide/sprite.svg";
        const safeValue = escapeHtml(isoValue || "");
        const popoverId = `${id}-popover`;
        return `<div id="${id}" class="datepicker" data-datepicker data-mode="single" data-locale="pt-BR" data-placeholder="Selecione uma data">
  <button type="button" class="datepicker-trigger input" aria-haspopup="dialog" aria-expanded="false" aria-controls="${popoverId}">
    <svg class="ds-lucide ds-lucide--sm datepicker-trigger__icon" viewBox="0 0 24 24" aria-hidden="true"><use href="${spriteBase}#calendar"></use></svg>
    <span class="datepicker-trigger__label datepicker-trigger__label--placeholder" data-datepicker-label>Selecione uma data</span>
  </button>
  <input type="hidden" data-datepicker-value value="${safeValue}">
  <div id="${popoverId}" class="datepicker-popover" data-datepicker-popover role="dialog" aria-modal="false" aria-label="Selecionar data" hidden>
    <header class="datepicker-popover__header">
      <button type="button" class="datepicker-popover__nav" data-datepicker-prev aria-label="Mes anterior"><svg class="ds-lucide ds-lucide--sm" viewBox="0 0 24 24" aria-hidden="true"><use href="${spriteBase}#chevron-left"></use></svg></button>
      <span class="datepicker-popover__title" data-datepicker-title aria-live="polite"></span>
      <button type="button" class="datepicker-popover__nav" data-datepicker-next aria-label="Proximo mes"><svg class="ds-lucide ds-lucide--sm" viewBox="0 0 24 24" aria-hidden="true"><use href="${spriteBase}#chevron-right"></use></svg></button>
    </header>
    <div class="datepicker-popover__weekdays" aria-hidden="true" data-datepicker-weekdays></div>
    <div class="datepicker-popover__grid" role="grid" data-datepicker-grid></div>
    <footer class="datepicker-popover__footer">
      <button type="button" class="datepicker-popover__action" data-datepicker-clear>Limpar</button>
      <button type="button" class="datepicker-popover__action" data-datepicker-today>Hoje</button>
    </footer>
  </div>
</div>`;
    }

    function showToast(message, level) {
        const category = level === "error" ? "error" : level === "success" ? "success" : "info";
        document.dispatchEvent(new CustomEvent("basecoat:toast", {
            detail: { config: { category, description: message } },
        }));
    }

    /* ───────────────── Editor Toast UI opcional ───────────────── */
    async function createObservacoesEditor(host) {
        if (!host || !window.gris?.editor?.create) return null;
        host.innerHTML = "";
        try {
            return await window.gris.editor.create(host, {
                initialValue: "",
                // Preenche toda a altura do card (sobrescreve o default "auto",
                // que deixava a area de edicao so na metade do container).
                height: "100%",
                toolbarItems: [
                    ["heading", "bold", "italic", "strike"],
                    ["hr", "quote"],
                    ["ul", "ol", "task"],
                    ["table", "link"],
                    ["code", "codeblock"],
                ],
            });
        } catch (err) {
            return null;
        }
    }

    function setEditorValue(editor, value) {
        if (!editor || typeof editor.setMarkdown !== "function") return;
        try { editor.setMarkdown(value || "", false); } catch (_e) { /* ignore */ }
    }

    function getEditorValue(editor) {
        if (!editor || typeof editor.getMarkdown !== "function") return "";
        try { return String(editor.getMarkdown() || "").trim(); } catch (_e) { return ""; }
    }

    function setEditorReadOnly(host, readOnly) {
        if (!host) return;
        host.classList.toggle("is-readonly", Boolean(readOnly));
        host.querySelectorAll("[contenteditable]").forEach((el) => {
            el.setAttribute("contenteditable", readOnly ? "false" : "true");
        });
    }

    /* ───────────────── Classe principal ───────────────── */
    class GrisKanbanTarefas {
        /**
         * @param {string|HTMLElement} target seletor ou elemento do container
         * @param {object} options
         * @param {"projeto"|"pessoal"} options.mode
         * @param {string} options.currentUser
         * @param {string} options.currentUserFullName
         * @param {boolean} [options.canEdit=true]
         * @param {Array<{user:string,full_name:string}>} [options.responsavelOptions]
         * @param {() => Promise<{tarefas:any[], responsavelOptions?:any[], canEdit?:boolean}>} options.onLoad
         * @param {(payload:object) => Promise<{tarefas:any[]}>} options.onSaveTask
         * @param {(name:string,status:string) => Promise<{tarefas:any[]}>} options.onMoveTask
         * @param {(name:string) => Promise<{comentarios:any[]}>} options.onLoadComments
         * @param {(name:string,texto:string) => Promise<{comentarios:any[]}>} options.onAddComment
         * @param {(commentName:string,texto:string) => Promise<{comentarios:any[]}>} options.onEditComment
         * @param {(commentName:string) => Promise<{comentarios:any[]}>} options.onDeleteComment
         */
        constructor(target, options) {
            this.container = typeof target === "string"
                ? document.querySelector(target)
                : target;
            if (!this.container) {
                throw new Error("[GrisKanbanTarefas] container nao encontrado");
            }

            this.options = options || {};
            this.mode = this.options.mode === "projeto" ? "projeto" : "pessoal";
            this.currentUser = String(this.options.currentUser || "");
            this.currentUserFullName = String(this.options.currentUserFullName || this.currentUser);
            this.canEdit = this.options.canEdit !== false;
            this.responsavelOptions = Array.isArray(this.options.responsavelOptions)
                ? this.options.responsavelOptions
                : [];

            this.dialog = document.getElementById(this.container.dataset.dialogId);
            this.saveButtonId = this.container.dataset.saveButtonId;
            this.commentButtonId = this.container.dataset.commentButtonId;
            this.newButtonId = this.container.dataset.newButtonId;
            this.showTimeline = this.container.dataset.showTimeline === "1";

            this.tarefas = [];
            this.activeTask = null;
            this.dragTaskName = "";
            this.isDragging = false;
            this.taskComments = [];
            this.editingCommentName = "";
            this.editingCommentDraft = "";
            this.taskCommentsLoading = false;
            this.saving = false;
            this.savingComment = false;
            this.statusBeforeChange = "Nao iniciado";
            this.observacoesEditor = null;
            this.responsavelFallback = {};

            this._initEditor();
            this._bindEvents();
            this._updateNewButtonState();
        }

        /* ── API publica ── */
        setTasks(tasks) {
            this.tarefas = Array.isArray(tasks) ? tasks : [];
            this._renderKanban();
        }

        setResponsavelOptions(options) {
            this.responsavelOptions = Array.isArray(options) ? options : [];
        }

        setCanEdit(canEdit) {
            this.canEdit = Boolean(canEdit);
            this._updateNewButtonState();
            this._renderKanban();
        }

        setHint(text) {
            const hintEl = this.container.parentElement?.querySelector("[data-kanban-hint]");
            if (hintEl) hintEl.textContent = String(text || "");
        }

        async refresh() {
            if (typeof this.options.onLoad !== "function") return;
            try {
                const data = await this.options.onLoad();
                this.tarefas = data?.tarefas || [];
                if (Array.isArray(data?.responsavelOptions)) {
                    this.responsavelOptions = data.responsavelOptions;
                }
                if (typeof data?.canEdit === "boolean") {
                    this.canEdit = data.canEdit;
                }
                this._updateNewButtonState();
                this._renderKanban();
            } catch (err) {
                showToast(err?.message || "Falha ao carregar tarefas.", "error");
            }
        }

        openTask(taskName) {
            // Quando um nome e informado mas a tarefa nao esta carregada (ex.:
            // removida apos o link ser gerado), nao abrir o dialog de nova tarefa.
            if (taskName && !this._getTaskByName(taskName)) return;
            this._openDialog(taskName);
        }

        /* ── Setup ── */
        async _initEditor() {
            const host = this._dlg("[data-kanban-observacoes-editor-host]");
            const block = this._dlg("[data-kanban-observacoes-markdown]");
            const editor = await createObservacoesEditor(host);
            if (editor) {
                this.observacoesEditor = editor;
                host?.classList.remove("d-none");
                block?.classList.add("d-none");
            } else {
                host?.classList.add("d-none");
                block?.classList.remove("d-none");
            }
        }

        _updateNewButtonState() {
            const btn = this.newButtonId && document.getElementById(this.newButtonId);
            if (btn) btn.disabled = !this.canEdit;
        }

        _dlg(selector) {
            return this.dialog ? this.dialog.querySelector(selector) : null;
        }

        /* ── Render do quadro ── */
        _renderKanban() {
            const byStatus = Object.fromEntries(TASK_STATUS_ORDER.map((s) => [s, []]));
            this.tarefas.forEach((task) => {
                const status = TASK_STATUS_ORDER.includes(task.status) ? task.status : "Nao iniciado";
                byStatus[status].push(task);
            });
            TASK_STATUS_ORDER.forEach((status) => {
                byStatus[status].sort((a, b) => {
                    const ad = parseDateFlexible(a?.prazo);
                    const bd = parseDateFlexible(b?.prazo);
                    if (ad && bd) {
                        const diff = ad.getTime() - bd.getTime();
                        if (diff !== 0) return diff;
                    } else if (ad) {
                        return -1;
                    } else if (bd) {
                        return 1;
                    }
                    return String(a?.descricao || "").localeCompare(String(b?.descricao || ""), "pt-BR");
                });
            });

            this.container.innerHTML = TASK_STATUS_ORDER.map((status) => {
                const tasks = byStatus[status] || [];
                const bodyHtml = tasks.length ? tasks.map((t) => this._renderCardHtml(t)).join("") : "";
                const taskWord = tasks.length !== 1 ? "tarefas" : "tarefa";
                return `
                    <section class="task-column" data-task-column="${escapeHtml(status)}">
                        <header class="task-column__header">
                            <div class="task-column__heading">
                                <h4 class="task-column__title">${escapeHtml(TASK_STATUS_LABELS[status] || status)}</h4>
                                <p class="task-column__subtitle">${tasks.length} ${taskWord}</p>
                            </div>
                            <span class="g-badge g-badge--secondary">${tasks.length}</span>
                        </header>
                        <div class="task-column__body" data-task-status="${escapeHtml(status)}">
                            ${bodyHtml}
                        </div>
                    </section>
                `;
            }).join("");
        }

        _renderCardHtml(task) {
            const deadline = formatTaskDeadline(task.prazo);
            const draggable = this.canEdit ? "true" : "false";

            let extraTopHtml = "";
            let footerExtraHtml = "";

            if (this.mode === "pessoal") {
                const badgeLabel = task.board_badge_label
                    || (task.board_referencia_doctype === "User" ? "Pessoal" : "");
                const badgeTipo = task.board_badge_tipo || "";
                if (badgeLabel) {
                    extraTopHtml = `<span class="task-board-badge task-card__board-badge" data-tipo="${escapeHtml(badgeTipo)}" title="${escapeHtml(badgeLabel)}">${escapeHtml(badgeLabel)}</span>`;
                }
            } else {
                const responsavelDisplay = task.responsavel_full_name || task.responsavel || "";
                const initials = getInitials(responsavelDisplay);
                const label = responsavelDisplay || "Sem responsavel";
                const cls = responsavelDisplay ? "" : " is-empty";
                footerExtraHtml = `<span class="task-card__responsavel${cls}" title="${escapeHtml(label)}">${escapeHtml(initials)}</span>`;
            }

            return `
                <article class="task-card" data-task-name="${escapeHtml(task.name || "")}" draggable="${draggable}">
                    <h4 class="task-card__title" title="${escapeHtml(task.descricao || "-")}">${escapeHtml(task.descricao || "-")}</h4>
                    ${extraTopHtml}
                    <div class="task-card__footer">
                        <span class="task-card__deadline" title="Prazo">
                            <svg viewBox="0 0 24 24" aria-hidden="true" focusable="false">
                                <circle cx="12" cy="12" r="8"></circle>
                                <path d="M12 8v4l2.5 1.5"></path>
                            </svg>
                            ${escapeHtml(deadline)}
                        </span>
                        ${footerExtraHtml}
                    </div>
                </article>
            `;
        }

        /* ── Dialog: helpers de campo ── */
        _getField(name) {
            const el = this._dlg(`[data-kanban-field="${name}"]`);
            if (!el) return "";
            if (name === "status") {
                return this._getSelectValue(el) || "Nao iniciado";
            }
            return (el.value || "").trim();
        }

        _setField(name, value) {
            const el = this._dlg(`[data-kanban-field="${name}"]`);
            if (!el) return;
            if (name === "status") {
                this._setSelectValue(el, value || "Nao iniciado");
                return;
            }
            el.value = value == null ? "" : value;
        }

        _getSelectValue(el) {
            const v = el.value;
            if (typeof v === "string" && v.trim()) return v.trim();
            const hidden = el.querySelector(':scope > input[type="hidden"]');
            return String(hidden?.value || "").trim();
        }

        _setSelectValue(el, value) {
            const v = String(value || "").trim();
            el.value = v;
            const hidden = el.querySelector(':scope > input[type="hidden"]');
            if (hidden) hidden.value = v;
            const option = el.querySelector(`[role="option"][data-value="${CSS.escape(v)}"]`);
            const labelEl = el.querySelector("button > span.truncate");
            if (labelEl) {
                labelEl.textContent = option?.textContent?.trim() || v || "Selecione";
            }
        }

        _getPrazoValue() {
            const wrapper = this._dlg("[data-kanban-prazo-wrapper]");
            return wrapper?.querySelector("[data-datepicker-value]")?.value || "";
        }

        _setPrazoWrapper(value) {
            const wrapper = this._dlg("[data-kanban-prazo-wrapper]");
            if (!wrapper) return;
            const id = `${this.container.id}-prazo-${Math.floor(Math.random() * 1e6)}`;
            wrapper.innerHTML = buildDatepickerHtml(id, value || "");
            wrapper.classList.remove("is-invalid");
            document.dispatchEvent(new CustomEvent("gris:design-system:init"));
        }

        _renderResponsavelCombobox(selectedValue) {
            const wrapper = this._dlg("[data-kanban-responsavel-wrapper]");
            if (!wrapper) return;
            const id = `${this.container.id}-responsavel`;
            const selected = String(selectedValue || "").trim();

            const dedup = new Map();
            (this.responsavelOptions || []).forEach((opt) => {
                const user = String(opt?.user || "").trim();
                const fullName = String(opt?.full_name || "").trim();
                if (!user || dedup.has(user)) return;
                dedup.set(user, fullName || user);
            });
            if (selected && !dedup.has(selected)) {
                dedup.set(selected, this.responsavelFallback[selected] || selected);
            }

            const items = [{ value: "", label: "Selecione" }]
                .concat(Array.from(dedup.entries()).map(([value, label]) => ({ value, label })));

            wrapper.innerHTML = buildSelectHtml(id, items, {
                isCombobox: true,
                searchPlaceholder: "Buscar responsavel...",
            });

            if (selected) {
                const el = document.getElementById(id);
                if (el) this._setSelectValue(el, selected);
            }

            document.dispatchEvent(new CustomEvent("gris:design-system:init"));
        }

        _getResponsavelValue() {
            if (this.mode === "pessoal") return this.currentUser;
            const id = `${this.container.id}-responsavel`;
            const el = document.getElementById(id);
            return el ? this._getSelectValue(el) : "";
        }

        /* ── Subtitle e badge ── */
        _setBoardBadge(task) {
            if (this.mode !== "pessoal") return;
            const badge = this._dlg("[data-kanban-board-badge]");
            if (!badge) return;
            const label = task?.board_badge_label || (task ? "Pessoal" : "Nova tarefa pessoal");
            const tipo = task?.board_badge_tipo || "pessoal";
            badge.textContent = label;
            badge.dataset.tipo = tipo;
        }

        _setSubtitle(task) {
            const text = this._dlg("[data-kanban-subtitle-text]");
            if (!text) return;
            text.textContent = task?.name
                ? "Atualize os detalhes e registre atividades nos comentarios."
                : "Preencha os dados e salve para habilitar comentarios.";
        }

        /* ── Timeline infografica ── */
        _updateTimeline() {
            if (!this.showTimeline) return;
            const timeline = this._dlg("[data-kanban-timeline]");
            if (!timeline) return;

            const status = this._getField("status") || "Nao iniciado";
            const startValue = this._getField("data_inicio");
            const deliveryEl = this._dlg('[data-kanban-field="data_entrega"]');
            const dueValue = this._getPrazoValue();

            if (status === "Nao iniciado" || status === "Cancelado") {
                timeline.classList.add("d-none");
                return;
            }
            timeline.classList.remove("d-none");

            const startDateEl = this._dlg("[data-kanban-timeline-start]");
            const endDateEl = this._dlg("[data-kanban-timeline-end]");
            const deltaEl = this._dlg("[data-kanban-timeline-delta]");
            const endDot = this._dlg("[data-kanban-timeline-end-dot]");

            if (startDateEl) startDateEl.textContent = formatTaskTimelineDate(startValue, "-");
            if (endDot) endDot.classList.remove("is-on-time", "is-late");
            if (deltaEl) {
                deltaEl.classList.remove("is-late", "is-early");
                deltaEl.textContent = "";
            }

            const isCompleted = status === "Concluido";
            if (!isCompleted) {
                if (endDateEl) endDateEl.textContent = "Em execucao";
                return;
            }

            const resolvedDelivery = (deliveryEl?.value || "").trim() || getTodayIso();
            if (deliveryEl && !deliveryEl.value) deliveryEl.value = resolvedDelivery;
            if (endDateEl) endDateEl.textContent = formatTaskTimelineDate(resolvedDelivery, "-");

            const dueDate = parseDateFlexible(dueValue);
            const deliveryDate = parseDateFlexible(resolvedDelivery);
            if (!dueDate || !deliveryDate) {
                if (endDot) endDot.classList.add("is-on-time");
                return;
            }

            const diff = diffDays(dueDate, deliveryDate);
            if (!deltaEl || !endDot) return;
            if (diff > 0) {
                deltaEl.textContent = `(${diff} dia${diff === 1 ? "" : "s"} atrasado)`;
                deltaEl.classList.add("is-late");
                endDot.classList.add("is-late");
            } else if (diff < 0) {
                const days = Math.abs(diff);
                deltaEl.textContent = `(${days} dia${days === 1 ? "" : "s"} adiantado)`;
                deltaEl.classList.add("is-early");
                endDot.classList.add("is-on-time");
            } else {
                deltaEl.textContent = "(entregue no prazo)";
                endDot.classList.add("is-on-time");
            }
        }

        _applyStatusChangeRules() {
            const next = this._getField("status") || "Nao iniciado";
            const prev = this.statusBeforeChange || "Nao iniciado";
            const startEl = this._dlg('[data-kanban-field="data_inicio"]');
            const deliveryEl = this._dlg('[data-kanban-field="data_entrega"]');
            if (prev === "Nao iniciado" && next !== "Nao iniciado" && startEl && !startEl.value) {
                startEl.value = getTodayIso();
            }
            if (next === "Concluido") {
                if (deliveryEl) deliveryEl.value = deliveryEl.value || getTodayIso();
            } else if (deliveryEl) {
                deliveryEl.value = "";
            }
            this.statusBeforeChange = next;
            this._updateTimeline();
        }

        /* ── Editabilidade ── */
        _setDialogEditable(editable) {
            this.dialog?.querySelectorAll("[data-kanban-field], [data-kanban-comment-input]").forEach((el) => {
                if (el.dataset.kanbanField === "responsavel-display") {
                    el.readOnly = true;
                    return;
                }
                if (el.tagName === "INPUT" && el.type === "hidden") return;
                el.disabled = !editable;
            });
            const responsavelTrigger = this._dlg("[data-kanban-responsavel-wrapper] .select > button");
            if (responsavelTrigger) responsavelTrigger.disabled = !editable;
            const prazoTrigger = this._dlg("[data-kanban-prazo-wrapper] .datepicker-trigger");
            if (prazoTrigger) prazoTrigger.disabled = !editable;
            const statusSelect = this._dlg('[data-kanban-field="status"] > button');
            if (statusSelect) statusSelect.disabled = !editable;

            if (this.observacoesEditor) {
                const host = this._dlg("[data-kanban-observacoes-editor-host]");
                setEditorReadOnly(host, !editable);
            }

            this.dialog?.querySelectorAll("[data-kanban-markdown-action]").forEach((btn) => {
                btn.disabled = !editable || Boolean(this.observacoesEditor);
            });
            const saveBtn = this.saveButtonId && document.getElementById(this.saveButtonId);
            if (saveBtn) saveBtn.disabled = !editable;

            this._refreshComposerState();
        }

        /* ── Markdown preview ── */
        _renderObservacoesPreview() {
            if (this.observacoesEditor) return;
            const value = this._getField("observacoes");
            const preview = this._dlg("[data-kanban-observacoes-preview]");
            if (preview) preview.innerHTML = value ? markdownToHtml(value) : "-";
        }

        _applyMarkdownAction(action) {
            if (this.observacoesEditor) return;
            const textarea = this._dlg('[data-kanban-field="observacoes"]');
            if (!textarea || textarea.disabled || textarea.readOnly) return;
            const start = textarea.selectionStart || 0;
            const end = textarea.selectionEnd || 0;
            const selected = textarea.value.slice(start, end);
            if (action === "bold") {
                textarea.setRangeText(`**${selected}**`, start, end, "end");
            } else if (action === "italic") {
                textarea.setRangeText(`*${selected}*`, start, end, "end");
            } else if (action === "list") {
                const lines = (selected || "item").split("\n").map((l) => (l.trim() ? `- ${l}` : "- "));
                textarea.setRangeText(lines.join("\n"), start, end, "end");
            } else if (action === "link") {
                textarea.setRangeText(`[${selected || "texto"}](https://)`, start, end, "end");
            }
            textarea.focus();
            this._renderObservacoesPreview();
        }

        /* ── Abrir/fechar dialog ── */
        _getTaskByName(name) {
            return (this.tarefas || []).find((t) => t.name === name) || null;
        }

        _openDialog(taskName) {
            const task = taskName ? this._getTaskByName(taskName) : null;
            this.activeTask = task;
            this.taskComments = [];
            this.editingCommentName = "";
            this.editingCommentDraft = "";

            const responsavelId = task?.responsavel || "";
            const responsavelFullName = task?.responsavel_full_name || "";
            if (responsavelId && responsavelFullName) {
                this.responsavelFallback[responsavelId] = responsavelFullName;
            }

            this._setField("name", task?.name || "");
            this._setField("data_inicio", task?.data_inicio || "");
            this._setField("data_entrega", task?.data_entrega || "");
            this._setPrazoWrapper(task?.prazo || "");

            this._setField("titulo", task?.descricao || "");
            this._setField("descricao", task?.descricao || "");

            const initialStatus = task?.status || "Nao iniciado";
            this._setField("status", initialStatus);
            this.statusBeforeChange = initialStatus;

            const observacoes = task?.observacoes || "";
            this._setField("observacoes", observacoes);
            if (this.observacoesEditor) setEditorValue(this.observacoesEditor, observacoes);

            if (this.mode === "projeto") {
                this._renderResponsavelCombobox(responsavelId);
            } else {
                const displayLabel = task
                    ? (task.responsavel_full_name || task.responsavel || this.currentUserFullName)
                    : this.currentUserFullName;
                this._setField("responsavel-display", displayLabel || "");
            }

            const commentInput = this._dlg("[data-kanban-comment-input]");
            if (commentInput) commentInput.value = "";

            this._setBoardBadge(task);
            this._setSubtitle(task);
            this._renderComments();
            this._refreshComposerState();
            this._setDialogEditable(this.canEdit);
            this._renderObservacoesPreview();
            this._updateTimeline();

            if (this.dialog && typeof this.dialog.showModal === "function") {
                this.dialog.showModal();
            } else if (this.dialog) {
                this.dialog.setAttribute("open", "");
            }

            if (task?.name && typeof this.options.onLoadComments === "function") {
                this._loadComments(task.name);
            }
        }

        _closeDialog() {
            if (this.dialog && typeof this.dialog.close === "function") {
                this.dialog.close();
            } else if (this.dialog) {
                this.dialog.removeAttribute("open");
            }
        }

        /* ── Salvar tarefa ── */
        _collectPayload() {
            const observacoes = this.observacoesEditor
                ? getEditorValue(this.observacoesEditor)
                : this._getField("observacoes");
            return {
                name: this._getField("name"),
                data_inicio: this._getField("data_inicio") || null,
                data_entrega: this._getField("data_entrega") || null,
                prazo: this._getPrazoValue() || null,
                descricao: this._getField("titulo"),
                status: this._getField("status") || "Nao iniciado",
                responsavel: this._getResponsavelValue(),
                observacoes,
            };
        }

        async _saveTask() {
            if (this.saving || !this.canEdit) return;
            if (typeof this.options.onSaveTask !== "function") return;
            const saveBtn = this.saveButtonId && document.getElementById(this.saveButtonId);
            const payload = this._collectPayload();
            if (!payload.descricao) {
                showToast("Informe o titulo da tarefa.", "error");
                return;
            }
            const prazoWrapper = this._dlg("[data-kanban-prazo-wrapper]");
            if (!payload.prazo) {
                if (prazoWrapper) prazoWrapper.classList.add("is-invalid");
                showToast("Informe o prazo da tarefa.", "error");
                return;
            }
            if (prazoWrapper) prazoWrapper.classList.remove("is-invalid");

            this.saving = true;
            if (saveBtn) saveBtn.disabled = true;
            try {
                const data = await this.options.onSaveTask(payload);
                this.tarefas = data?.tarefas || this.tarefas;
                this._renderKanban();
                this._closeDialog();
                showToast("Tarefa salva.", "success");
            } catch (err) {
                showToast(err?.message || "Falha ao salvar tarefa.", "error");
            } finally {
                this.saving = false;
                if (saveBtn) saveBtn.disabled = !this.canEdit;
            }
        }

        async _moveTask(taskName, nextStatus) {
            if (!this.canEdit) return;
            if (typeof this.options.onMoveTask !== "function") return;
            const task = this._getTaskByName(taskName);
            if (!task || task.status === nextStatus) return;
            const previous = task.status;
            task.status = nextStatus;
            this._renderKanban();
            try {
                const data = await this.options.onMoveTask(taskName, nextStatus);
                this.tarefas = data?.tarefas || this.tarefas;
                this._renderKanban();
            } catch (err) {
                task.status = previous;
                this._renderKanban();
                showToast(err?.message || "Falha ao mover tarefa.", "error");
            }
        }

        /* ── Comentarios ── */
        _refreshComposerState() {
            const hint = this._dlg("[data-kanban-comments-hint]");
            const input = this._dlg("[data-kanban-comment-input]");
            const button = this.commentButtonId && document.getElementById(this.commentButtonId);
            const hasTask = Boolean(this.activeTask?.name);
            const canCompose = Boolean(this.canEdit && hasTask && !this.taskCommentsLoading);
            if (input) input.disabled = !canCompose;
            if (button) button.disabled = !canCompose;
            if (!hint) return;
            if (!hasTask) {
                hint.textContent = "Salve a tarefa para habilitar comentarios.";
            } else if (!this.canEdit) {
                hint.textContent = "Voce possui acesso de leitura para os comentarios desta tarefa.";
            } else if (this.taskCommentsLoading) {
                hint.textContent = "Atualizando comentarios...";
            } else {
                hint.textContent = "Use os comentarios para registrar decisoes e andamento.";
            }
        }

        _renderComments() {
            const list = this._dlg("[data-kanban-comments-list]");
            if (!list) return;
            if (this.taskCommentsLoading) {
                list.innerHTML = '<div class="task-comments-empty">Carregando comentarios...</div>';
                return;
            }
            if (!this.activeTask?.name) {
                list.innerHTML = '<div class="task-comments-empty">Salve a tarefa para liberar o historico de comentarios.</div>';
                return;
            }
            if (!this.taskComments.length) {
                list.innerHTML = '<div class="task-comments-empty">Nenhum comentario registrado para esta tarefa.</div>';
                return;
            }

            const currentUserLc = String(this.currentUser || "").toLowerCase();
            list.innerHTML = this.taskComments.map((comment) => {
                const commentName = String(comment?.name || "").trim();
                const author = comment.author || comment.author_email || "Usuario";
                const initials = getInitials(author);
                const timestamp = formatCommentDate(comment.creation);
                const rawContent = (comment.content || "").trim();
                const fallback = String(comment.content_text || "").trim();
                const contentHtml = rawContent
                    ? sanitizeHtml(rawContent)
                    : escapeHtml(fallback || "-").replace(/\n/g, "<br>");
                const owner = String(comment.owner || comment.author_email || "").trim().toLowerCase();
                const isAuthor = Boolean(commentName && owner && currentUserLc && owner === currentUserLc);
                const isEditing = Boolean(commentName && this.editingCommentName === commentName);

                if (isEditing) {
                    return `
                        <article class="task-comment-item task-comment-item--editing">
                            <div class="task-comment-item__row">
                                <span class="task-comment-item__avatar" aria-hidden="true">${escapeHtml(initials)}</span>
                                <div class="task-comment-item__main">
                                    <header class="task-comment-item__header">
                                        <strong class="task-comment-item__author">${escapeHtml(author)}</strong>
                                        <span class="task-comment-item__time">${escapeHtml(timestamp)}</span>
                                    </header>
                                    <div class="task-comment-item__bubble task-comment-item__bubble--edit">
                                        <textarea class="textarea task-comment-item__edit-input" rows="4"
                                            data-kanban-comment-edit-input="${escapeHtml(commentName)}"
                                            placeholder="Edite o comentario">${escapeHtml(this.editingCommentDraft || fallback)}</textarea>
                                    </div>
                                    <div class="task-comment-item__actions task-comment-item__actions--edit">
                                        <button type="button" class="task-comment-item__action-link task-comment-item__action-link--primary"
                                            data-kanban-comment-action="save-edit" data-comment-name="${escapeHtml(commentName)}">Salvar</button>
                                        <span class="task-comment-item__action-sep" aria-hidden="true">•</span>
                                        <button type="button" class="task-comment-item__action-link"
                                            data-kanban-comment-action="cancel-edit">Cancelar</button>
                                    </div>
                                </div>
                            </div>
                        </article>
                    `;
                }

                const actionsHtml = isAuthor ? `
                    <div class="task-comment-item__actions">
                        <span class="task-comment-item__action-icon" aria-hidden="true">↪</span>
                        <button type="button" class="task-comment-item__action-link"
                            data-kanban-comment-action="edit" data-comment-name="${escapeHtml(commentName)}"
                            aria-label="Editar comentario" title="Editar comentario">
                            <svg class="task-comment-item__icon" viewBox="0 0 24 24" aria-hidden="true" focusable="false">
                                <path d="M12 20h9"></path>
                                <path d="M16.5 3.5a2.1 2.1 0 0 1 3 3L7 19l-4 1 1-4 12.5-12.5z"></path>
                            </svg>
                        </button>
                        <span class="task-comment-item__action-sep" aria-hidden="true">•</span>
                        <button type="button" class="task-comment-item__action-link"
                            data-kanban-comment-action="delete" data-comment-name="${escapeHtml(commentName)}"
                            aria-label="Excluir comentario" title="Excluir comentario">
                            <svg class="task-comment-item__icon" viewBox="0 0 24 24" aria-hidden="true" focusable="false">
                                <path d="M6 6h12"></path>
                                <path d="M7 6v13a1 1 0 0 0 1 1h8a1 1 0 0 0 1-1V6"></path>
                            </svg>
                        </button>
                    </div>
                ` : "";

                return `
                    <article class="task-comment-item">
                        <div class="task-comment-item__row">
                            <span class="task-comment-item__avatar" aria-hidden="true">${escapeHtml(initials)}</span>
                            <div class="task-comment-item__main">
                                <header class="task-comment-item__header">
                                    <strong class="task-comment-item__author">${escapeHtml(author)}</strong>
                                    <span class="task-comment-item__time">${escapeHtml(timestamp)}</span>
                                </header>
                                <div class="task-comment-item__bubble">
                                    <div class="task-comment-item__content">${contentHtml}</div>
                                </div>
                                ${actionsHtml}
                            </div>
                        </div>
                    </article>
                `;
            }).join("");
        }

        async _loadComments(taskName) {
            if (typeof this.options.onLoadComments !== "function") return;
            const requested = String(taskName || "").trim();
            if (!requested) return;
            this.taskCommentsLoading = true;
            this._renderComments();
            this._refreshComposerState();
            try {
                const data = await this.options.onLoadComments(requested);
                if (this.activeTask?.name !== requested) return;
                this.taskComments = data?.comentarios || [];
                this.editingCommentName = "";
                this.editingCommentDraft = "";
            } catch (err) {
                if (this.activeTask?.name === requested) {
                    this.taskComments = [];
                }
                showToast(err?.message || "Falha ao carregar comentarios.", "error");
            } finally {
                if (this.activeTask?.name === requested) {
                    this.taskCommentsLoading = false;
                    this._renderComments();
                    this._refreshComposerState();
                }
            }
        }

        async _addComment() {
            if (this.savingComment || !this.canEdit || !this.activeTask?.name) return;
            if (typeof this.options.onAddComment !== "function") return;
            const input = this._dlg("[data-kanban-comment-input]");
            const texto = (input?.value || "").trim();
            if (!texto) {
                showToast("Digite um comentario antes de enviar.", "error");
                return;
            }
            const requested = this.activeTask.name;
            this.savingComment = true;
            this._refreshComposerState();
            try {
                const data = await this.options.onAddComment(requested, texto);
                if (this.activeTask?.name !== requested) return;
                this.taskComments = data?.comentarios || [];
                if (input) input.value = "";
                this._renderComments();
            } catch (err) {
                showToast(err?.message || "Falha ao adicionar comentario.", "error");
            } finally {
                this.savingComment = false;
                this._refreshComposerState();
            }
        }

        _beginEditComment(commentName) {
            const comment = (this.taskComments || []).find((c) => c.name === commentName);
            if (!comment) return;
            this.editingCommentName = commentName;
            this.editingCommentDraft = String(comment.content_text || "").trim();
            this._renderComments();
        }

        _cancelEditComment() {
            this.editingCommentName = "";
            this.editingCommentDraft = "";
            this._renderComments();
        }

        async _saveEditComment(commentName) {
            if (!this.canEdit || !commentName || this.editingCommentName !== commentName) return;
            if (typeof this.options.onEditComment !== "function") return;
            const input = this.dialog?.querySelector(`[data-kanban-comment-edit-input="${CSS.escape(commentName)}"]`);
            const texto = (input?.value || "").trim();
            if (!texto) {
                showToast("O comentario nao pode ficar vazio.", "error");
                return;
            }
            try {
                const data = await this.options.onEditComment(commentName, texto);
                this.taskComments = data?.comentarios || this.taskComments;
                this.editingCommentName = "";
                this.editingCommentDraft = "";
                this._renderComments();
            } catch (err) {
                showToast(err?.message || "Falha ao salvar edicao do comentario.", "error");
            }
        }

        async _deleteComment(commentName) {
            if (!this.canEdit || !commentName) return;
            if (typeof this.options.onDeleteComment !== "function") return;
            if (!window.confirm("Deseja apagar este comentario?")) return;
            try {
                const data = await this.options.onDeleteComment(commentName);
                this.taskComments = data?.comentarios || this.taskComments;
                if (this.editingCommentName === commentName) {
                    this.editingCommentName = "";
                    this.editingCommentDraft = "";
                }
                this._renderComments();
            } catch (err) {
                showToast(err?.message || "Falha ao apagar comentario.", "error");
            }
        }

        /* ── Eventos ── */
        _bindEvents() {
            const newBtn = this.newButtonId && document.getElementById(this.newButtonId);
            if (newBtn && !newBtn.dataset.kanbanBound) {
                newBtn.dataset.kanbanBound = "1";
                newBtn.addEventListener("click", () => this._openDialog(""));
            }

            const saveBtn = this.saveButtonId && document.getElementById(this.saveButtonId);
            if (saveBtn && !saveBtn.dataset.kanbanBound) {
                saveBtn.dataset.kanbanBound = "1";
                saveBtn.addEventListener("click", () => this._saveTask());
            }

            const commentBtn = this.commentButtonId && document.getElementById(this.commentButtonId);
            if (commentBtn && !commentBtn.dataset.kanbanBound) {
                commentBtn.dataset.kanbanBound = "1";
                commentBtn.addEventListener("click", () => this._addComment());
            }

            // Click handlers do quadro (cards)
            this.container.addEventListener("click", (event) => {
                const card = event.target.closest(".task-card");
                if (card && this.container.contains(card)) {
                    if (this.isDragging) return;
                    this._openDialog(card.dataset.taskName || "");
                }
            });

            // Drag-and-drop
            this.container.addEventListener("dragstart", (event) => {
                const card = event.target.closest(".task-card");
                if (!card || !this.canEdit) return;
                this.dragTaskName = card.dataset.taskName || "";
                this.isDragging = true;
                card.classList.add("is-dragging");
                if (event.dataTransfer) {
                    event.dataTransfer.effectAllowed = "move";
                    event.dataTransfer.setData("text/plain", this.dragTaskName);
                }
            });
            this.container.addEventListener("dragend", (event) => {
                const card = event.target.closest(".task-card");
                if (card) card.classList.remove("is-dragging");
                this.container.querySelectorAll(".task-column__body.is-drop-target").forEach((c) => c.classList.remove("is-drop-target"));
                this.dragTaskName = "";
                setTimeout(() => { this.isDragging = false; }, 0);
            });
            this.container.addEventListener("dragover", (event) => {
                const column = event.target.closest(".task-column__body");
                if (!column || !this.canEdit || !this.dragTaskName) return;
                event.preventDefault();
                column.classList.add("is-drop-target");
            });
            this.container.addEventListener("dragleave", (event) => {
                const column = event.target.closest(".task-column__body");
                if (!column) return;
                if (column.contains(event.relatedTarget)) return;
                column.classList.remove("is-drop-target");
            });
            this.container.addEventListener("drop", (event) => {
                const column = event.target.closest(".task-column__body");
                if (!column || !this.canEdit) return;
                event.preventDefault();
                column.classList.remove("is-drop-target");
                const taskName = this.dragTaskName || event.dataTransfer?.getData("text/plain") || "";
                const nextStatus = column.dataset.taskStatus;
                // Reseta antes de mover: _moveTask re-renderiza o kanban (innerHTML),
                // o card de origem some, e dragend nao propaga a partir de elemento desanexado.
                this.dragTaskName = "";
                setTimeout(() => { this.isDragging = false; }, 0);
                if (!taskName || !nextStatus) return;
                this._moveTask(taskName, nextStatus);
            });

            if (!this.dialog) return;

            // Comentarios e markdown dentro do dialog
            this.dialog.addEventListener("click", (event) => {
                const commentAction = event.target.closest("[data-kanban-comment-action]");
                if (commentAction) {
                    const action = commentAction.getAttribute("data-kanban-comment-action");
                    const commentName = commentAction.getAttribute("data-comment-name") || "";
                    if (action === "edit") this._beginEditComment(commentName);
                    else if (action === "cancel-edit") this._cancelEditComment();
                    else if (action === "save-edit") this._saveEditComment(commentName);
                    else if (action === "delete") this._deleteComment(commentName);
                    return;
                }
                const markdownBtn = event.target.closest("[data-kanban-markdown-action]");
                if (markdownBtn) {
                    this._applyMarkdownAction(markdownBtn.dataset.kanbanMarkdownAction);
                    return;
                }
                const prazoTrigger = event.target.closest("[data-kanban-prazo-wrapper] .datepicker-trigger");
                if (prazoTrigger) {
                    this._dlg("[data-kanban-prazo-wrapper]")?.classList.remove("is-invalid");
                }
            });

            this.dialog.addEventListener("input", (event) => {
                const obs = event.target.closest('[data-kanban-field="observacoes"]');
                if (obs) {
                    this._renderObservacoesPreview();
                    return;
                }
                const editInput = event.target.closest("[data-kanban-comment-edit-input]");
                if (editInput) {
                    const commentName = editInput.getAttribute("data-kanban-comment-edit-input");
                    if (commentName && this.editingCommentName === commentName) {
                        this.editingCommentDraft = editInput.value;
                    }
                    return;
                }
                const titulo = event.target.closest('[data-kanban-field="titulo"]');
                if (titulo) {
                    this._setField("descricao", titulo.value.trim());
                    return;
                }
                const startField = event.target.closest('[data-kanban-field="data_inicio"]');
                if (startField) {
                    this._updateTimeline();
                }
            });

            // Status mudancas (via custom event do select basecoat ou change nativo)
            this.dialog.addEventListener("change", (event) => {
                const statusSelect = event.target.closest('[data-kanban-field="status"]');
                if (statusSelect) {
                    this._applyStatusChangeRules();
                }
            });

            this.dialog.addEventListener("keydown", (event) => {
                if (event.key === "Enter" && (event.ctrlKey || event.metaKey)) {
                    const composer = event.target.closest("[data-kanban-comment-input]");
                    if (composer) {
                        event.preventDefault();
                        this._addComment();
                    }
                }
            });

            // Datepicker e select tambem disparam evento custom — ouvimos no document
            const dpHandler = (event) => {
                const wrapper = this._dlg("[data-kanban-prazo-wrapper]");
                if (wrapper && wrapper.contains(event.target)) {
                    this._updateTimeline();
                }
            };
            document.addEventListener("datepicker:change", dpHandler);
        }
    }

    window.GrisKanbanTarefas = GrisKanbanTarefas;
})();
