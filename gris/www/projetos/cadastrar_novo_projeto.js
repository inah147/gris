(function () {
    const METHODS = {
        bootstrap: "gris.gestao_de_projetos.doctype.projeto.projeto.get_projeto_form_data",
        getContatoPessoa: "gris.gestao_de_projetos.doctype.projeto.projeto.get_contato_pessoa",
        getMandatoryAprovadores:
            "gris.gestao_de_projetos.doctype.projeto.projeto.get_aprovadores_obrigatorios_preview",
        salvarRascunho: "gris.gestao_de_projetos.doctype.projeto.projeto.salvar_rascunho_projeto",
        submeter: "gris.gestao_de_projetos.doctype.projeto.projeto.submeter_projeto",
        resolverComentarioRevisao: "gris.gestao_de_projetos.doctype.projeto.projeto.resolver_comentario_revisao",
        solicitarIA: "gris.gestao_de_projetos.doctype.projeto.projeto.solicitar_avaliacao_tap_llm",
        consultarIA: "gris.gestao_de_projetos.doctype.projeto.projeto.consultar_avaliacao_tap",
    };

    const TABLE_CONFIG = {
        equipe_de_interesse: {
            fields: ["tipo_pessoa", "associado", "responsavel", "nome", "email", "telefone", "funcao"],
        },
        aprovadores: {
            fields: [
                "tipo_pessoa",
                "associado",
                "responsavel",
                "nome",
                "email",
                "telefone",
                "origem_regra",
                "permite_remover",
            ],
        },
        objetivos: {
            fields: ["objetivo", "metrica_de_sucesso"],
        },
        ods: {
            fields: ["ods"],
        },
        cronograma: {
            fields: ["data_inicio", "data_termino", "tarefa"],
        },
        recursos: {
            fields: ["recurso"],
        },
        riscos: {
            fields: ["risco", "mitigacao"],
        },
    };

    const INFO_CONTENT = {
        justificativa: {
            title: "Descrição e Justificativa",
            body: `
                <p>Explique com clareza o problema/oportunidade e por que o projeto é necessário agora.</p>
                <p><strong>O que incluir:</strong> contexto, público impactado, dor principal e resultado esperado.</p>
                <p><strong>Exemplo:</strong> "Observamos baixa participação de jovens nas atividades de fim de semana. O projeto busca elevar a adesão com trilhas práticas e acompanhamento de responsáveis, fortalecendo permanência e desenvolvimento progressivo."</p>
            `,
        },
        alinhamento_com_escotismo: {
            title: "Alinhamento com o Escotismo",
            body: `
                <p>Descreva como o projeto aplica valores, método e propósito educativo do escotismo.</p>
                <p><strong>O que incluir:</strong> protagonismo juvenil, aprendizagem pela prática, vida em equipe, serviço e relação com a comunidade.</p>
                <p><strong>Exemplo:</strong> "As atividades serão conduzidas em patrulhas, com definição de papéis e ciclos de reflexão pós-atividade, reforçando autonomia, cooperação e cidadania ativa."</p>
            `,
        },
        equipe_de_interesse: {
            title: "Equipe de Interesse",
            body: `
                <p>Registre as pessoas-chave envolvidas no projeto e a função de cada uma.</p>
                <p><strong>O que incluir:</strong> nome, contato atualizado e papel esperado (coordenação, execução, apoio técnico, comunicação etc.).</p>
                <p><strong>Exemplo:</strong> "Maria Silva - Coordenação Geral; João Costa - Logística; Ana Souza - Comunicação com famílias."</p>
            `,
        },
        objetivos: {
            title: "Objetivos",
            body: `
                <p>Cadastre objetivos específicos, mensuráveis e conectados ao propósito do projeto.</p>
                <p><strong>O que incluir:</strong> objetivo claro + métrica de sucesso para comprovar resultado.</p>
                <p><strong>Exemplo:</strong> "Aumentar participação média mensal de 40 para 55 jovens até dezembro"; métrica: "presença registrada por encontro".</p>
            `,
        },
        competencias: {
            title: "Competências e Blocos de Aprendizagem",
            body: `
                <p>Indique quais competências serão desenvolvidas e quais blocos de aprendizagem serão trabalhados.</p>
                <p><strong>O que incluir:</strong> competências socioemocionais, técnicas e atitudes esperadas ao final.</p>
                <p><strong>Exemplo:</strong> "Trabalho em equipe, liderança situacional, planejamento de atividade, comunicação não violenta e resolução de conflitos."</p>
            `,
        },
        especialidade: {
            title: "Especialidades",
            body: `
                <p>Informe as especialidades relacionadas ao projeto e como elas contribuem para a proposta.</p>
                <p><strong>O que incluir:</strong> nomes de especialidades e vínculo prático com as atividades.</p>
                <p><strong>Exemplo:</strong> "Primeiros Socorros, Acampamento e Conservação Ambiental, aplicadas em oficinas práticas e saídas de campo."</p>
            `,
        },
        ods: {
            title: "ODS (Objetivos de Desenvolvimento Sustentável)",
            body: `
                <p>Selecione apenas os ODS que tenham relação direta com os resultados do projeto.</p>
                <p><strong>Orientação:</strong> prefira poucos ODS bem justificados, em vez de marcar muitos sem conexão clara.</p>
                <p><strong>Lista completa dos 17 ODS:</strong></p>
                <ol>
                    <li><strong>ODS 1 - Erradicação da Pobreza:</strong> acabar com a pobreza em todas as suas formas, em todos os lugares.</li>
                    <li><strong>ODS 2 - Fome Zero e Agricultura Sustentável:</strong> acabar com a fome, alcançar segurança alimentar e promover agricultura sustentável.</li>
                    <li><strong>ODS 3 - Saúde e Bem-Estar:</strong> assegurar vida saudável e promover bem-estar para todas as idades.</li>
                    <li><strong>ODS 4 - Educação de Qualidade:</strong> garantir educação inclusiva, equitativa e de qualidade, com oportunidades de aprendizagem ao longo da vida.</li>
                    <li><strong>ODS 5 - Igualdade de Gênero:</strong> alcançar igualdade de gênero e empoderar mulheres e meninas.</li>
                    <li><strong>ODS 6 - Água Potável e Saneamento:</strong> garantir disponibilidade e gestão sustentável da água e saneamento para todos.</li>
                    <li><strong>ODS 7 - Energia Limpa e Acessível:</strong> garantir acesso à energia confiável, sustentável, moderna e a preço acessível.</li>
                    <li><strong>ODS 8 - Trabalho Decente e Crescimento Econômico:</strong> promover crescimento econômico sustentado, inclusivo e sustentável, emprego pleno e produtivo e trabalho decente para todos.</li>
                    <li><strong>ODS 9 - Indústria, Inovação e Infraestrutura:</strong> construir infraestrutura resiliente, promover industrialização inclusiva e sustentável e fomentar inovação.</li>
                    <li><strong>ODS 10 - Redução das Desigualdades:</strong> reduzir desigualdades dentro dos países e entre eles.</li>
                    <li><strong>ODS 11 - Cidades e Comunidades Sustentáveis:</strong> tornar cidades e assentamentos humanos inclusivos, seguros, resilientes e sustentáveis.</li>
                    <li><strong>ODS 12 - Consumo e Produção Responsáveis:</strong> assegurar padrões de produção e de consumo sustentáveis.</li>
                    <li><strong>ODS 13 - Ação Contra a Mudança Global do Clima:</strong> adotar medidas urgentes para combater a mudança do clima e seus impactos.</li>
                    <li><strong>ODS 14 - Vida na Água:</strong> conservar e usar de forma sustentável oceanos, mares e recursos marinhos.</li>
                    <li><strong>ODS 15 - Vida Terrestre:</strong> proteger, recuperar e promover uso sustentável dos ecossistemas terrestres e da biodiversidade.</li>
                    <li><strong>ODS 16 - Paz, Justiça e Instituições Eficazes:</strong> promover sociedades pacíficas e inclusivas, com acesso à justiça e instituições eficazes.</li>
                    <li><strong>ODS 17 - Parcerias e Meios de Implementação:</strong> fortalecer meios de implementação e revitalizar parcerias para o desenvolvimento sustentável.</li>
                </ol>
                <p><strong>Exemplo:</strong> projeto de formação ambiental pode marcar ODS 4, 12, 13 e 15 quando houver atividades e metas concretas para cada um.</p>
            `,
        },
        cronograma: {
            title: "Cronograma",
            body: `
                <p>Detalhe etapas do projeto com datas de início e término e a tarefa correspondente.</p>
                <p><strong>O que incluir:</strong> marcos principais, sequência lógica e prazo realista para cada entrega.</p>
                <p><strong>Exemplo:</strong> "01/04 a 15/04 - Planejamento"; "16/04 a 30/06 - Execução das oficinas"; "01/07 a 15/07 - Avaliação final".</p>
            `,
        },
        recursos: {
            title: "Recursos",
            body: `
                <p>Liste recursos necessários para viabilizar o projeto.</p>
                <p><strong>O que incluir:</strong> recursos humanos, materiais, infraestrutura, parcerias e serviços.</p>
                <p><strong>Exemplo:</strong> "2 facilitadores voluntários, kit de primeiros socorros, transporte local para saída de campo e apoio de parceiro comunitário."</p>
            `,
        },
        riscos: {
            title: "Riscos",
            body: `
                <p>Registre os principais riscos do projeto e a estratégia de mitigação para cada um.</p>
                <p><strong>O que incluir:</strong> risco objetivo, impacto esperado e ação preventiva/corretiva.</p>
                <p><strong>Exemplo:</strong> risco: "baixa adesão nas primeiras semanas"; mitigação: "campanha prévia com responsáveis, calendário divulgado com antecedência e acompanhamento por equipe de comunicação".</p>
            `,
        },
    };

    const state = {
        projetoName: "",
        choices: {
            associados: [],
            associados_padrinho: [],
            responsaveis: [],
            ods: [],
        },
        pollingId: null,
        pollingAttempts: 0,
        saving: false,
        reviewComments: [],
        defaultAprovadores: [],
        cronogramaSeq: 0,
        ganttDrag: null,
        cronogramaTableDragId: "",
    };

    const MS_PER_DAY = 24 * 60 * 60 * 1000;
    const API_TIMEOUT_MS = 30000;
    const APROVADOR_ORIGEM_LABELS = {
        manual: "Adicionado manualmente",
        diretor_presidente: "Diretor presidente (padrão)",
        padrinho_orientador: "Padrinho/orientador (obrigatório)",
        chefe_secao: "Chefe de seção (obrigatório)",
    };

    function normalizeEquipeTipoPessoa(value) {
        const raw = String(value || "").trim();
        if (!raw) return "Outro";

        if (raw === "Associado" || raw === "Responsavel" || raw === "Outro") {
            return raw;
        }

        if (raw.toLowerCase() === "nome livre") {
            return "Outro";
        }

        return "Outro";
    }

    function escapeHtml(value) {
        return String(value || "")
            .replace(/&/g, "&amp;")
            .replace(/</g, "&lt;")
            .replace(/>/g, "&gt;")
            .replace(/\"/g, "&quot;")
            .replace(/'/g, "&#39;");
    }

    function showAlert(message, type) {
        const el = document.getElementById("formAlert");
        if (!el) return;
        el.classList.remove("d-none", "alert-modern--error", "alert-modern--success");
        el.classList.add(type === "error" ? "alert-modern--error" : "alert-modern--success");
        el.textContent = message;
    }

    function hideAlert() {
        const el = document.getElementById("formAlert");
        if (!el) return;
        el.classList.add("d-none");
        el.textContent = "";
    }

    function formatIsoToBrDate(value) {
        const iso = String(value || "").trim();
        const match = iso.match(/^(\d{4})-(\d{2})-(\d{2})$/);
        if (!match) return "";
        return `${match[3]}/${match[2]}/${match[1]}`;
    }

    function parseBrToIsoDate(value) {
        const br = String(value || "").trim();
        if (!br) return "";

        const isoMatch = br.match(/^(\d{4})-(\d{2})-(\d{2})$/);
        if (isoMatch) return `${isoMatch[1]}-${isoMatch[2]}-${isoMatch[3]}`;

        const match = br.match(/^(\d{2})\/(\d{2})\/(\d{4})$/);
        if (!match) return "";

        const day = Number(match[1]);
        const month = Number(match[2]);
        const year = Number(match[3]);
        const date = new Date(year, month - 1, day);
        if (Number.isNaN(date.getTime())) return "";
        if (date.getDate() !== day || date.getMonth() !== month - 1 || date.getFullYear() !== year) {
            return "";
        }

        return `${String(year).padStart(4, "0")}-${String(month).padStart(2, "0")}-${String(day).padStart(2, "0")}`;
    }

    function normalizeDateDisplayValue(value) {
        const raw = String(value || "").trim();
        if (!raw) return "";

        const fromIso = formatIsoToBrDate(raw);
        if (fromIso) return fromIso;

        const fromBr = parseBrToIsoDate(raw);
        if (fromBr) return formatIsoToBrDate(fromBr);

        return raw;
    }

    function applyDateMask(rawValue) {
        const digits = String(rawValue || "").replace(/\D/g, "").slice(0, 8);
        if (digits.length <= 2) return digits;
        if (digits.length <= 4) return `${digits.slice(0, 2)}/${digits.slice(2)}`;
        return `${digits.slice(0, 2)}/${digits.slice(2, 4)}/${digits.slice(4)}`;
    }

    function attachDateMask(input) {
        if (!input || input.dataset.dateMaskBound === "1") return;
        input.dataset.dateMaskBound = "1";

        input.addEventListener("input", () => {
            const previous = input.value;
            const masked = applyDateMask(previous);
            if (masked !== previous) {
                input.value = masked;
            }
        });

        input.addEventListener("blur", () => {
            input.value = normalizeDateDisplayValue(input.value);
        });
    }

    function getPendingReviewComments() {
        return (state.reviewComments || []).filter((row) => {
            const tipo = String(row?.tipo_revisao || "").trim();
            const resolvido = Number(row?.resolvido || 0) === 1;
            return tipo === "Solicitacao de alteracoes" && !resolvido;
        });
    }

    function renderPendingReviewRows() {
        const tbody = document.getElementById("rows_pending_review_comments");
        if (!tbody) return;

        const pending = getPendingReviewComments();
        if (!pending.length) {
            tbody.innerHTML = "<tr><td colspan='5'>Nenhum comentário pendente.</td></tr>";
            return;
        }

        tbody.innerHTML = pending
            .map(
                (row) => `
                <tr>
                    <td>${escapeHtml(row.aprovador_label || row.aprovador || "-")}</td>
                    <td>${escapeHtml(row.etapa_label || row.etapa_aprovacao || "-")}</td>
                    <td>${escapeHtml(row.comentarios || "-")}</td>
                    <td>${escapeHtml(row.data_da_revisao || "-")}</td>
                    <td>
                        <button
                            type="button"
                            class="btn-modern btn-modern--outline btn-modern--sm"
                            data-resolve-review-comment="${escapeHtml(row.name || "")}"
                        >
                            Resolver
                        </button>
                    </td>
                </tr>
            `
            )
            .join("");
    }

    function updatePendingReviewBanner() {
        const banner = document.getElementById("pendingReviewBanner");
        const countLabel = document.getElementById("pendingReviewCount");
        if (!banner || !countLabel) return;

        const pendingCount = getPendingReviewComments().length;
        if (!pendingCount) {
            banner.classList.add("d-none");
            countLabel.textContent = "";
            return;
        }

        banner.classList.remove("d-none");
        countLabel.textContent = `${pendingCount} comentário(s) pendente(s)`;
    }

    function openPendingReviewModal() {
        const modal = document.getElementById("pendingReviewModal");
        if (!modal) return;
        renderPendingReviewRows();
        modal.classList.remove("d-none");
        modal.setAttribute("aria-hidden", "false");
        document.body.classList.add("info-modal-open");
    }

    function closePendingReviewModal() {
        const modal = document.getElementById("pendingReviewModal");
        if (!modal) return;
        modal.classList.add("d-none");
        modal.setAttribute("aria-hidden", "true");
        document.body.classList.remove("info-modal-open");
    }

    async function resolveReviewComment(commentName) {
        if (!state.projetoName || !commentName) {
            return;
        }

        try {
            await callApi(METHODS.resolverComentarioRevisao, {
                projeto_name: state.projetoName,
                comentario_name: commentName,
            });

            state.reviewComments = (state.reviewComments || []).map((row) => {
                if ((row?.name || "") !== commentName) {
                    return row;
                }
                return {
                    ...row,
                    resolvido: 1,
                };
            });

            renderPendingReviewRows();
            updatePendingReviewBanner();
            showAlert("Comentário marcado como resolvido.", "success");
        } catch (error) {
            showAlert(error.message || "Falha ao resolver comentário.", "error");
        }
    }

    function setButtonsDisabled(disabled) {
        ["btnSalvarRascunho", "btnSubmeter", "btnAvaliacaoIA", "btnConfirmSubmitProjeto"].forEach((id) => {
            const btn = document.getElementById(id);
            if (btn) {
                btn.disabled = disabled;
            }
        });
    }

    function resetActionState() {
        state.saving = false;
        setButtonsDisabled(false);
    }

    function openSubmitConfirmModal() {
        const modal = document.getElementById("submitConfirmModal");
        if (!modal) return;
        modal.classList.remove("d-none");
        modal.setAttribute("aria-hidden", "false");
        document.body.classList.add("info-modal-open");
    }

    function closeSubmitConfirmModal() {
        const modal = document.getElementById("submitConfirmModal");
        if (!modal) return;
        modal.classList.add("d-none");
        modal.setAttribute("aria-hidden", "true");
        document.body.classList.remove("info-modal-open");
    }

    function redirectToApprovalPage() {
        if (!state.projetoName) return;
        window.location.assign(`/projetos/aprovacao_projeto?projeto=${encodeURIComponent(state.projetoName)}`);
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
                // Ignore parse errors and fallback to generic message.
            }
        }

        if (typeof response.message === "string" && response.message.trim()) {
            return response.message.trim();
        }

        return "";
    }

    function callApi(method, args) {
        return new Promise((resolve, reject) => {
            const timerId = setTimeout(() => {
                reject(new Error("Tempo limite excedido ao processar requisição. Tente novamente."));
            }, API_TIMEOUT_MS);

            frappe.call({
                method,
                args,
                callback: (r) => {
                    clearTimeout(timerId);
                    if (r.exc) {
                        reject(new Error(extractServerMessage(r) || "Erro ao processar requisição."));
                        return;
                    }
                    resolve(r.message || {});
                },
                error: (err) => {
                    clearTimeout(timerId);
                    const message = err && err.message ? err.message : "Erro de comunicação com o servidor.";
                    reject(new Error(message));
                },
            });
        });
    }

    function fillSelect(selectId, options, placeholder) {
        const select = document.getElementById(selectId);
        if (!select) return;

        const firstOption = `<option value="">${placeholder}</option>`;
        const optionTags = (options || [])
            .map((opt) => `<option value="${escapeHtml(opt.value || "")}">${escapeHtml(opt.label || opt.value || "")}</option>`)
            .join("");
        select.innerHTML = `${firstOption}${optionTags}`;
    }

    function getTrashButtonHtml() {
        return `
            <button type="button" class="btn-delete-row" aria-label="Remover linha" title="Remover linha">
                <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round" aria-hidden="true">
                    <polyline points="3 6 5 6 21 6"></polyline>
                    <path d="M8 6V4a1 1 0 0 1 1-1h6a1 1 0 0 1 1 1v2"></path>
                    <path d="M19 6l-1 14a1 1 0 0 1-1 1H7a1 1 0 0 1-1-1L5 6"></path>
                    <line x1="10" y1="11" x2="10" y2="17"></line>
                    <line x1="14" y1="11" x2="14" y2="17"></line>
                </svg>
            </button>
        `;
    }

    function updateSponsorVisibility() {
        const tipo = document.getElementById("tipo_padrinho_ou_orientador")?.value || "Associado";
        const fieldAssoc = document.getElementById("fieldPadrinhoAssociado");
        const fieldResp = document.getElementById("fieldPadrinhoResponsavel");

        if (!fieldAssoc || !fieldResp) return;

        if (tipo === "Responsavel") {
            fieldAssoc.classList.add("d-none");
            fieldResp.classList.remove("d-none");
        } else {
            fieldAssoc.classList.remove("d-none");
            fieldResp.classList.add("d-none");
        }
    }

    function getBasicPayload() {
        return {
            nome_do_projeto: document.getElementById("nome_do_projeto")?.value || "",
            coordenador: document.getElementById("coordenador")?.value || "",
            data_de_inicio: parseBrToIsoDate(document.getElementById("data_de_inicio")?.value || ""),
            data_de_termino: parseBrToIsoDate(document.getElementById("data_de_termino")?.value || ""),
            tipo_padrinho_ou_orientador: document.getElementById("tipo_padrinho_ou_orientador")?.value || "Associado",
            padrinho_associado: document.getElementById("padrinho_associado")?.value || "",
            padrinho_responsavel: document.getElementById("padrinho_responsavel")?.value || "",
            justificativa: document.getElementById("justificativa")?.value || "",
            alinhamento_com_escotismo: document.getElementById("alinhamento_com_escotismo")?.value || "",
            competencias: document.getElementById("competencias")?.value || "",
            especialidade: document.getElementById("especialidade")?.value || "",
            observacoes_e_comentarios: document.getElementById("observacoes_e_comentarios")?.value || "",
        };
    }

    function parseRows(tableKey) {
        const tbody = document.getElementById(`rows_${tableKey}`);
        if (!tbody) return [];

        const fields = TABLE_CONFIG[tableKey].fields;
        const rows = [];

        tbody.querySelectorAll("tr").forEach((tr) => {
            const row = {};
            fields.forEach((fieldname) => {
                const input = tr.querySelector(`[data-field='${fieldname}']`);
                row[fieldname] = input ? input.value || "" : "";
            });

            if (tableKey === "equipe_de_interesse") {
                row.tipo_pessoa = normalizeEquipeTipoPessoa(row.tipo_pessoa);
            }

            if (tableKey === "aprovadores") {
                row.tipo_pessoa = row.tipo_pessoa === "Responsavel" ? "Responsavel" : "Associado";
                if (row.tipo_pessoa === "Associado") {
                    row.responsavel = "";
                } else {
                    row.associado = "";
                }
                row.origem_regra = row.origem_regra || "manual";
                row.permite_remover = Number(row.permite_remover || 0) === 1 ? 1 : 0;
            }

            if (tableKey === "cronograma") {
                row.data_inicio = parseBrToIsoDate(row.data_inicio || "");
                row.data_termino = parseBrToIsoDate(row.data_termino || "");
            }

            rows.push(row);
        });

        return rows;
    }

    function buildPayload() {
        return {
            ...getBasicPayload(),
            equipe_de_interesse: parseRows("equipe_de_interesse"),
            aprovadores: parseRows("aprovadores"),
            objetivos: parseRows("objetivos"),
            ods: parseRows("ods"),
            cronograma: parseRows("cronograma"),
            recursos: parseRows("recursos"),
            riscos: parseRows("riscos"),
        };
    }

    function setEquipeFieldsReadOnly(readOnly) {
        ["equipe_nome", "equipe_email", "equipe_telefone"].forEach((id) => {
            const input = document.getElementById(id);
            if (input) {
                input.readOnly = readOnly;
            }
        });
    }

    function clearEquipeBuilderPersonalFields() {
        ["equipe_nome", "equipe_email", "equipe_telefone"].forEach((id) => {
            const input = document.getElementById(id);
            if (input) {
                input.value = "";
            }
        });
    }

    function setAprovadorFieldsReadOnly(readOnly) {
        ["aprovador_nome", "aprovador_email", "aprovador_telefone"].forEach((id) => {
            const input = document.getElementById(id);
            if (input) {
                input.readOnly = readOnly;
            }
        });
    }

    function clearAprovadorBuilderPersonalFields() {
        ["aprovador_nome", "aprovador_email", "aprovador_telefone"].forEach((id) => {
            const input = document.getElementById(id);
            if (input) {
                input.value = "";
            }
        });
    }

    function getAprovadorOrigemLabel(origemRegra) {
        const key = String(origemRegra || "manual").trim() || "manual";
        return APROVADOR_ORIGEM_LABELS[key] || APROVADOR_ORIGEM_LABELS.manual;
    }

    function getAprovadorKeyFromRowData(rowData) {
        const tipo = rowData?.tipo_pessoa === "Responsavel" ? "Responsavel" : "Associado";
        const docname = tipo === "Associado" ? rowData?.associado || "" : rowData?.responsavel || "";
        if (!docname) return "";
        return `${tipo}:${docname}`;
    }

    function updateAprovadorBuilderMode() {
        const tipo = document.getElementById("aprovador_tipo_pessoa")?.value || "Associado";
        const fieldAssociado = document.getElementById("aprovador_field_associado");
        const fieldResponsavel = document.getElementById("aprovador_field_responsavel");

        if (fieldAssociado && fieldResponsavel) {
            fieldAssociado.classList.toggle("d-none", tipo !== "Associado");
            fieldResponsavel.classList.toggle("d-none", tipo !== "Responsavel");
        }

        setAprovadorFieldsReadOnly(true);
        clearAprovadorBuilderPersonalFields();
    }

    async function preencherAprovadorPeloCadastro(tipoPessoa, docname) {
        if (!docname) {
            clearAprovadorBuilderPersonalFields();
            return;
        }

        try {
            const doctypeName = tipoPessoa === "Associado" ? "Associado" : "Responsavel";
            const contato = await callApi(METHODS.getContatoPessoa, {
                doctype_name: doctypeName,
                docname,
            });

            const nome = document.getElementById("aprovador_nome");
            const email = document.getElementById("aprovador_email");
            const telefone = document.getElementById("aprovador_telefone");
            if (nome) nome.value = contato.nome || "";
            if (email) email.value = contato.email || "";
            if (telefone) telefone.value = contato.telefone || "";
        } catch (error) {
            showAlert(error.message || "Falha ao obter dados do aprovador selecionado.", "error");
        }
    }

    function createAprovadorRow(rowData) {
        const tipoPessoa = rowData?.tipo_pessoa === "Responsavel" ? "Responsavel" : "Associado";
        const associado = rowData?.associado || "";
        const responsavel = rowData?.responsavel || "";
        const nome = escapeHtml(rowData?.nome || "");
        const email = escapeHtml(rowData?.email || "");
        const telefone = escapeHtml(rowData?.telefone || "");
        const origemRegra = (rowData?.origem_regra || "manual").trim() || "manual";
        const podeRemover = Number(rowData?.permite_remover || 0) === 1;
        const origemLabel = escapeHtml(getAprovadorOrigemLabel(origemRegra));
        const aprovadorKey = getAprovadorKeyFromRowData({
            tipo_pessoa: tipoPessoa,
            associado,
            responsavel,
        });

        const tr = document.createElement("tr");
        tr.dataset.canRemove = podeRemover ? "1" : "0";
        tr.dataset.origemRegra = origemRegra;
        tr.dataset.aprovadorKey = aprovadorKey;
        tr.innerHTML = `
            <td>
                <input type="hidden" data-field="tipo_pessoa" value="${escapeHtml(tipoPessoa)}" />
                <input type="hidden" data-field="associado" value="${escapeHtml(associado)}" />
                <input type="hidden" data-field="responsavel" value="${escapeHtml(responsavel)}" />
                <input type="hidden" data-field="origem_regra" value="${escapeHtml(origemRegra)}" />
                <input type="hidden" data-field="permite_remover" value="${podeRemover ? "1" : "0"}" />
                <input type="text" data-field="nome" value="${nome}" readonly />
            </td>
            <td><input type="text" data-field="email" value="${email}" readonly /></td>
            <td><input type="text" data-field="telefone" value="${telefone}" readonly /></td>
            <td><input type="text" data-field="origem_label" value="${origemLabel}" readonly /></td>
            <td>${getTrashButtonHtml()}</td>
        `;

        const deleteButton = tr.querySelector(".btn-delete-row");
        if (deleteButton && !podeRemover) {
            deleteButton.disabled = true;
            deleteButton.title = "Este aprovador é obrigatório e não pode ser removido.";
            deleteButton.setAttribute("aria-label", "Aprovador obrigatório");
        }

        return tr;
    }

    async function syncSponsorAprovadorRowInTable() {
        const tbody = document.getElementById("rows_aprovadores");
        if (!tbody) return;

        Array.from(tbody.querySelectorAll("tr")).forEach((tr) => {
            if (["padrinho_orientador", "chefe_secao"].includes(tr.dataset.origemRegra || "")) {
                tr.remove();
            }
        });

        try {
            const result = await callApi(METHODS.getMandatoryAprovadores, {
                payload: JSON.stringify({
                    coordenador: document.getElementById("coordenador")?.value || "",
                    tipo_padrinho_ou_orientador:
                        document.getElementById("tipo_padrinho_ou_orientador")?.value || "Associado",
                    padrinho_associado: document.getElementById("padrinho_associado")?.value || "",
                    padrinho_responsavel: document.getElementById("padrinho_responsavel")?.value || "",
                }),
            });

            const mandatoryRows = result.mandatory_aprovadores || [];
            const mandatoryKeys = new Set(
                mandatoryRows
                    .map((row) => getAprovadorKeyFromRowData(row))
                    .filter((key) => String(key || "").trim())
            );

            Array.from(tbody.querySelectorAll("tr")).forEach((tr) => {
                if (mandatoryKeys.has(tr.dataset.aprovadorKey || "")) {
                    tr.remove();
                }
            });

            mandatoryRows
                .slice()
                .reverse()
                .forEach((row) => {
                    tbody.prepend(
                        createAprovadorRow({
                            ...row,
                            permite_remover: 0,
                        })
                    );
                });
        } catch (error) {
            showAlert(
                error.message || "Falha ao sincronizar aprovadores obrigatórios.",
                "error"
            );
        }
    }

    function updateEquipeBuilderMode() {
        const tipo = document.getElementById("equipe_tipo_pessoa")?.value || "Associado";
        const fieldAssociado = document.getElementById("equipe_field_associado");
        const fieldResponsavel = document.getElementById("equipe_field_responsavel");

        if (fieldAssociado && fieldResponsavel) {
            fieldAssociado.classList.toggle("d-none", tipo !== "Associado");
            fieldResponsavel.classList.toggle("d-none", tipo !== "Responsavel");
        }

        if (tipo === "Outro") {
            clearEquipeBuilderPersonalFields();
            setEquipeFieldsReadOnly(false);
            return;
        }

        setEquipeFieldsReadOnly(true);
        clearEquipeBuilderPersonalFields();
    }

    async function preencherEquipePeloCadastro(tipoPessoa, docname) {
        if (!docname) {
            clearEquipeBuilderPersonalFields();
            return;
        }

        try {
            const doctypeName = tipoPessoa === "Associado" ? "Associado" : "Responsavel";
            const contato = await callApi(METHODS.getContatoPessoa, {
                doctype_name: doctypeName,
                docname,
            });

            const nome = document.getElementById("equipe_nome");
            const email = document.getElementById("equipe_email");
            const telefone = document.getElementById("equipe_telefone");
            if (nome) nome.value = contato.nome || "";
            if (email) email.value = contato.email || "";
            if (telefone) telefone.value = contato.telefone || "";
        } catch (error) {
            showAlert(error.message || "Falha ao obter dados da pessoa selecionada.", "error");
        }
    }

    function createInput(fieldname, value) {
        const safeValue = escapeHtml(value || "");

        if (fieldname === "ods") {
            const options = state.choices.ods
                .map((opt) => `<option value="${escapeHtml(opt.value || "")}">${escapeHtml(opt.label || "")}</option>`)
                .join("");
            return `<select data-field="${fieldname}"><option value=""></option>${options}</select>`;
        }

        if (fieldname.includes("data_")) {
            return `<input type="date" data-field="${fieldname}" value="${safeValue}" />`;
        }

        return `<input type="text" data-field="${fieldname}" value="${safeValue}" />`;
    }

    function createEquipeRow(rowData) {
        const tipoPessoa = normalizeEquipeTipoPessoa(rowData?.tipo_pessoa);
        const associado = rowData?.associado || "";
        const responsavel = rowData?.responsavel || "";
        const nome = escapeHtml(rowData?.nome || "");
        const email = escapeHtml(rowData?.email || "");
        const telefone = escapeHtml(rowData?.telefone || "");
        const funcao = escapeHtml(rowData?.funcao || "");
        const isReadOnly = tipoPessoa === "Associado" || tipoPessoa === "Responsavel";

        const tr = document.createElement("tr");
        tr.innerHTML = `
            <td>
                <input type="hidden" data-field="tipo_pessoa" value="${escapeHtml(tipoPessoa)}" />
                <input type="hidden" data-field="associado" value="${escapeHtml(associado)}" />
                <input type="hidden" data-field="responsavel" value="${escapeHtml(responsavel)}" />
                <input type="text" data-field="nome" value="${nome}" ${isReadOnly ? "readonly" : ""} />
            </td>
            <td><input type="text" data-field="email" value="${email}" ${isReadOnly ? "readonly" : ""} /></td>
            <td><input type="text" data-field="telefone" value="${telefone}" ${isReadOnly ? "readonly" : ""} /></td>
            <td><input type="text" data-field="funcao" value="${funcao}" /></td>
            <td>${getTrashButtonHtml()}</td>
        `;
        return tr;
    }

    function getCronogramaDragHandleHtml() {
        return `
            <button
                type="button"
                class="cronograma-row-handle"
                data-row-drag-handle
                draggable="true"
                aria-label="Arrastar para reordenar"
                title="Arraste para reordenar"
            >
                <span></span><span></span>
                <span></span><span></span>
                <span></span><span></span>
            </button>
        `;
    }

    function createCronogramaRow(rowData) {
        const inicio = normalizeDateDisplayValue(rowData?.data_inicio || "");
        const termino = normalizeDateDisplayValue(rowData?.data_termino || "");
        const tr = document.createElement("tr");
        tr.innerHTML = `
            <td class="cronograma-cell-handle">${getCronogramaDragHandleHtml()}</td>
            <td><input type="text" inputmode="numeric" placeholder="dd/mm/aaaa" data-field="data_inicio" value="${escapeHtml(inicio)}" /></td>
            <td><input type="text" inputmode="numeric" placeholder="dd/mm/aaaa" data-field="data_termino" value="${escapeHtml(termino)}" /></td>
            <td><input type="text" data-field="tarefa" value="${escapeHtml(rowData?.tarefa || "")}" /></td>
            <td>${getTrashButtonHtml()}</td>
        `;

        const inputInicio = tr.querySelector("[data-field='data_inicio']");
        const inputTermino = tr.querySelector("[data-field='data_termino']");
        attachDateMask(inputInicio);
        attachDateMask(inputTermino);
        return tr;
    }

    function parseDateIso(value) {
        const iso = parseBrToIsoDate(value);
        if (!iso) return null;
        const parts = String(iso).split("-");
        if (parts.length !== 3) return null;
        const year = Number(parts[0]);
        const month = Number(parts[1]);
        const day = Number(parts[2]);
        if (!Number.isInteger(year) || !Number.isInteger(month) || !Number.isInteger(day)) return null;
        const date = new Date(year, month - 1, day);
        if (Number.isNaN(date.getTime())) return null;
        date.setHours(0, 0, 0, 0);
        return date;
    }

    function formatDateIso(date) {
        if (!(date instanceof Date) || Number.isNaN(date.getTime())) return "";
        const y = String(date.getFullYear());
        const m = String(date.getMonth() + 1).padStart(2, "0");
        const d = String(date.getDate()).padStart(2, "0");
        return `${y}-${m}-${d}`;
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

    function ensureCronogramaRowId(tr) {
        if (!tr) return "";
        if (!tr.dataset.cronogramaId) {
            state.cronogramaSeq += 1;
            tr.dataset.cronogramaId = `crono_${state.cronogramaSeq}`;
        }
        return tr.dataset.cronogramaId;
    }

    function getCronogramaRows() {
        const tbody = document.getElementById("rows_cronograma");
        if (!tbody) return [];

        return Array.from(tbody.querySelectorAll("tr")).map((tr) => {
            const id = ensureCronogramaRowId(tr);
            const startInput = tr.querySelector("[data-field='data_inicio']");
            const endInput = tr.querySelector("[data-field='data_termino']");
            const tarefaInput = tr.querySelector("[data-field='tarefa']");

            const start = parseDateIso(startInput?.value || "");
            const end = parseDateIso(endInput?.value || "");
            const tarefa = (tarefaInput?.value || "").trim();

            return {
                id,
                tr,
                startInput,
                endInput,
                tarefaInput,
                tarefa,
                start,
                end,
            };
        });
    }

    function applyCronogramaDatesToRow(task, startDate, endDate) {
        if (!task?.startInput || !task?.endInput) return;
        task.startInput.value = normalizeDateDisplayValue(formatDateIso(startDate));
        task.endInput.value = normalizeDateDisplayValue(formatDateIso(endDate));
    }

    function renderCronogramaGantt() {
        const container = document.getElementById("cronogramaGantt");
        if (!container) return;
        const drag = state.ganttDrag;

        const rows = getCronogramaRows();
        const tasks = rows
            .filter((row) => row.start && row.end && row.tarefa)
            .map((row) => {
                const end = row.end < row.start ? row.start : row.end;
                return {
                    ...row,
                    end,
                };
            });

        if (!tasks.length) {
            container.innerHTML = `
                <div class="cronograma-gantt__empty">
                    Preencha tarefa, data inicial e data final para visualizar o Gantt.
                </div>
            `;
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
            ticks.push(`
                <div class="cronograma-gantt__tick" style="left:${(day / totalDays) * 100}%">
                    ${date.toLocaleDateString("pt-BR", { day: "2-digit", month: "2-digit" })}
                </div>
            `);
        }

        const rowsHtml = tasks
            .map((task) => {
                const offsetDays = diffDays(chartStart, task.start);
                const durationDays = Math.max(diffDays(task.start, task.end) + 1, 1);
                const leftPct = (offsetDays / totalDays) * 100;
                const widthPct = (durationDays / totalDays) * 100;
                const isDraggingRow = drag && drag.rowId === task.id;
                const isDropTarget = drag && drag.mode === "move" && drag.targetRowId === task.id && drag.rowId !== task.id;
                const rowClasses = ["cronograma-gantt__row"];
                const barClasses = ["cronograma-gantt__bar"];
                if (isDraggingRow) {
                    rowClasses.push("is-drag-source");
                    barClasses.push("is-dragging-source");
                }
                if (isDropTarget) {
                    rowClasses.push("is-drop-target");
                }

                return `
                    <div class="${rowClasses.join(" ")}" data-row-id="${escapeHtml(task.id)}">
                        <div class="cronograma-gantt__label" title="${escapeHtml(task.tarefa)}">${escapeHtml(task.tarefa)}</div>
                        <div class="cronograma-gantt__lane" data-row-id="${escapeHtml(task.id)}">
                            <div class="${barClasses.join(" ")}" data-row-id="${escapeHtml(task.id)}" style="left:${leftPct}%;width:${widthPct}%;">
                                <button type="button" class="cronograma-gantt__handle cronograma-gantt__handle--start" data-drag-mode="resize-start" aria-label="Ajustar data inicial"></button>
                                <span class="cronograma-gantt__bar-text">${escapeHtml(task.tarefa)}</span>
                                <button type="button" class="cronograma-gantt__handle cronograma-gantt__handle--end" data-drag-mode="resize-end" aria-label="Ajustar data final"></button>
                                <button type="button" class="cronograma-gantt__delete" data-delete-row="${escapeHtml(task.id)}" aria-label="Excluir atividade" title="Excluir atividade">×</button>
                            </div>
                        </div>
                    </div>
                `;
            })
            .join("");

        let dragHint = "";
        if (drag) {
            if (drag.mode === "move") {
                dragHint = `<span class="cronograma-gantt__drag-hint">Reordenando: solte sobre a linha destacada</span>`;
            } else {
                dragHint = `<span class="cronograma-gantt__drag-hint">Ajustando datas: arraste a extremidade da barra</span>`;
            }
        }

        container.innerHTML = `
            <div class="cronograma-gantt__header">
                <div class="cronograma-gantt__header-label">Tarefa</div>
                <div class="cronograma-gantt__timeline">${ticks.join("")}</div>
            </div>
            ${dragHint}
            <div class="cronograma-gantt__body" data-chart-start="${formatDateIso(chartStart)}" data-total-days="${totalDays}">
                ${rowsHtml}
            </div>
        `;
    }

    function findCronogramaTaskById(rowId) {
        return getCronogramaRows().find((row) => row.id === rowId) || null;
    }

    function reorderCronogramaRows(draggedId, targetId) {
        if (!draggedId || !targetId || draggedId === targetId) return;

        const tbody = document.getElementById("rows_cronograma");
        if (!tbody) return;

        const dragged = tbody.querySelector(`tr[data-cronograma-id='${draggedId}']`);
        const target = tbody.querySelector(`tr[data-cronograma-id='${targetId}']`);
        if (!dragged || !target) return;

        const rows = Array.from(tbody.querySelectorAll("tr"));
        const draggedIndex = rows.indexOf(dragged);
        const targetIndex = rows.indexOf(target);
        if (draggedIndex === -1 || targetIndex === -1 || draggedIndex === targetIndex) return;

        if (draggedIndex < targetIndex) {
            tbody.insertBefore(dragged, target.nextSibling);
        } else {
            tbody.insertBefore(dragged, target);
        }
    }

    function bindCronogramaTableDrag() {
        const tbody = document.getElementById("rows_cronograma");
        if (!tbody || tbody.dataset.dragBound === "1") return;
        tbody.dataset.dragBound = "1";

        tbody.addEventListener("dragstart", (event) => {
            const handle = event.target.closest("[data-row-drag-handle]");
            if (!handle) {
                event.preventDefault();
                return;
            }

            const tr = handle.closest("tr");
            if (!tr) {
                event.preventDefault();
                return;
            }

            const rowId = ensureCronogramaRowId(tr);
            state.cronogramaTableDragId = rowId;
            tr.classList.add("is-drag-source");
            if (event.dataTransfer) {
                event.dataTransfer.effectAllowed = "move";
                event.dataTransfer.setData("text/plain", rowId);
            }
        });

        tbody.addEventListener("dragover", (event) => {
            if (!state.cronogramaTableDragId) return;
            event.preventDefault();

            const target = event.target.closest("tr");
            if (!target) return;
            const targetId = ensureCronogramaRowId(target);

            tbody.querySelectorAll("tr").forEach((row) => {
                row.classList.remove("is-drop-target-before", "is-drop-target-after");
            });

            if (targetId === state.cronogramaTableDragId) return;

            const rect = target.getBoundingClientRect();
            const placeAfter = event.clientY > rect.top + rect.height / 2;
            target.classList.add(placeAfter ? "is-drop-target-after" : "is-drop-target-before");
        });

        tbody.addEventListener("drop", (event) => {
            if (!state.cronogramaTableDragId) return;
            event.preventDefault();

            const target = event.target.closest("tr");
            const dragged = tbody.querySelector(`tr[data-cronograma-id='${state.cronogramaTableDragId}']`);
            if (!target || !dragged || target === dragged) {
                renderCronogramaGantt();
                return;
            }

            const rect = target.getBoundingClientRect();
            const placeAfter = event.clientY > rect.top + rect.height / 2;
            if (placeAfter) {
                tbody.insertBefore(dragged, target.nextSibling);
            } else {
                tbody.insertBefore(dragged, target);
            }

            renderCronogramaGantt();
        });

        tbody.addEventListener("dragend", () => {
            state.cronogramaTableDragId = "";
            tbody.querySelectorAll("tr").forEach((row) => {
                row.classList.remove("is-drag-source", "is-drop-target-before", "is-drop-target-after");
            });
        });
    }

    function bindCronogramaGanttEvents() {
        const container = document.getElementById("cronogramaGantt");
        if (!container || container.dataset.bound === "1") return;
        container.dataset.bound = "1";

        container.addEventListener("click", (event) => {
            const deleteBtn = event.target.closest("[data-delete-row]");
            if (!deleteBtn) return;

            const rowId = deleteBtn.getAttribute("data-delete-row") || "";
            const row = document.querySelector(`#rows_cronograma tr[data-cronograma-id='${rowId}']`);
            if (row) {
                row.remove();
                renderCronogramaGantt();
            }
        });

        container.addEventListener("mousedown", (event) => {
            const bar = event.target.closest(".cronograma-gantt__bar");
            if (!bar) return;

            const rowId = bar.getAttribute("data-row-id") || "";
            const task = findCronogramaTaskById(rowId);
            if (!task || !task.start || !task.end) return;

            const body = container.querySelector(".cronograma-gantt__body");
            if (!body) return;
            const totalDays = Number(body.dataset.totalDays || 0);
            if (!totalDays) return;

            const lane = bar.closest(".cronograma-gantt__lane");
            if (!lane) return;
            const laneRect = lane.getBoundingClientRect();
            const dayWidth = laneRect.width / totalDays;
            if (!dayWidth) return;

            const mode = event.target.matches("[data-drag-mode='resize-start']")
                ? "resize-start"
                : event.target.matches("[data-drag-mode='resize-end']")
                  ? "resize-end"
                  : "move";

            state.ganttDrag = {
                rowId,
                mode,
                startX: event.clientX,
                dayWidth,
                origStart: task.start,
                origEnd: task.end,
                workingStart: task.start,
                workingEnd: task.end,
                targetRowId: rowId,
            };

            bar.classList.add("is-dragging");
            document.body.classList.add("gantt-is-dragging");
            event.preventDefault();
        });

        document.addEventListener("mousemove", (event) => {
            if (!state.ganttDrag) return;
            const drag = state.ganttDrag;

            const deltaDays = Math.round((event.clientX - drag.startX) / drag.dayWidth);
            let nextStart = drag.origStart;
            let nextEnd = drag.origEnd;

            if (drag.mode === "resize-start") {
                nextStart = addDays(drag.origStart, deltaDays);
                if (nextStart > drag.origEnd) nextStart = new Date(drag.origEnd);
            } else if (drag.mode === "resize-end") {
                nextEnd = addDays(drag.origEnd, deltaDays);
                if (nextEnd < drag.origStart) nextEnd = new Date(drag.origStart);
            } else {
                nextStart = addDays(drag.origStart, deltaDays);
                nextEnd = addDays(drag.origEnd, deltaDays);

                const hoverRow = event.target.closest(".cronograma-gantt__row");
                drag.targetRowId = hoverRow?.getAttribute("data-row-id") || drag.rowId;
            }

            drag.workingStart = nextStart;
            drag.workingEnd = nextEnd;

            const task = findCronogramaTaskById(drag.rowId);
            if (task) {
                applyCronogramaDatesToRow(task, nextStart, nextEnd);
                renderCronogramaGantt();
            }
        });

        document.addEventListener("mouseup", () => {
            if (!state.ganttDrag) return;
            const drag = state.ganttDrag;

            if (drag.mode === "move" && drag.targetRowId && drag.targetRowId !== drag.rowId) {
                reorderCronogramaRows(drag.rowId, drag.targetRowId);
            }
            document.body.classList.remove("gantt-is-dragging");
            state.ganttDrag = null;
            renderCronogramaGantt();
        });
    }

    function bindCronogramaTableSync() {
        const tbody = document.getElementById("rows_cronograma");
        if (!tbody || tbody.dataset.syncBound === "1") return;
        tbody.dataset.syncBound = "1";

        ["input", "change"].forEach((evtName) => {
            tbody.addEventListener(evtName, () => {
                renderCronogramaGantt();
            });
        });
    }

    function addRow(tableKey, rowData) {
        const tbody = document.getElementById(`rows_${tableKey}`);
        if (!tbody) return;

        if (tableKey === "equipe_de_interesse") {
            tbody.appendChild(createEquipeRow(rowData || {}));
            return;
        }

        if (tableKey === "aprovadores") {
            if (!rowData) return;
            tbody.appendChild(createAprovadorRow(rowData));
            return;
        }

        const fields = TABLE_CONFIG[tableKey].fields;
        const tr = tableKey === "cronograma" ? createCronogramaRow(rowData) : document.createElement("tr");

        if (tableKey !== "cronograma") {
            const cells = fields
                .map((fieldname) => `<td>${createInput(fieldname, rowData?.[fieldname] || "")}</td>`)
                .join("");

            tr.innerHTML = `${cells}<td>${getTrashButtonHtml()}</td>`;
        }
        tbody.appendChild(tr);

        if (tableKey === "cronograma") {
            ensureCronogramaRowId(tr);
        }

        if (rowData && tableKey !== "cronograma") {
            fields.forEach((fieldname) => {
                const input = tr.querySelector(`[data-field='${fieldname}']`);
                if (input) {
                    input.value = rowData[fieldname] || "";
                }
            });
        }

        if (tableKey === "cronograma") {
            renderCronogramaGantt();
        }
    }

    function replaceRows(tableKey, rows) {
        const tbody = document.getElementById(`rows_${tableKey}`);
        if (!tbody) return;
        tbody.innerHTML = "";

        if ((rows || []).length === 0 && tableKey !== "equipe_de_interesse" && tableKey !== "aprovadores") {
            addRow(tableKey, {});
            return;
        }

        rows.forEach((row) => addRow(tableKey, row));

        if (tableKey === "cronograma") {
            renderCronogramaGantt();
        }
    }

    function fillForm(data) {
        if (!data) return;

        state.reviewComments = data.comentarios_revisao_aprovacao || [];
        updatePendingReviewBanner();

        [
            "nome_do_projeto",
            "coordenador",
            "tipo_padrinho_ou_orientador",
            "padrinho_associado",
            "padrinho_responsavel",
            "justificativa",
            "alinhamento_com_escotismo",
            "competencias",
            "especialidade",
            "observacoes_e_comentarios",
        ].forEach((fieldname) => {
            const input = document.getElementById(fieldname);
            if (input && data[fieldname] !== undefined && data[fieldname] !== null) {
                input.value = data[fieldname];
            }
        });

        const dataInicio = document.getElementById("data_de_inicio");
        const dataTermino = document.getElementById("data_de_termino");
        if (dataInicio) dataInicio.value = normalizeDateDisplayValue(data.data_de_inicio || "");
        if (dataTermino) dataTermino.value = normalizeDateDisplayValue(data.data_de_termino || "");

        updateSponsorVisibility();

        replaceRows("equipe_de_interesse", data.equipe_de_interesse || []);
        replaceRows("aprovadores", data.aprovadores || []);
        replaceRows("objetivos", data.objetivos || []);
        replaceRows("ods", data.ods || []);
        replaceRows("cronograma", data.cronograma || []);
        replaceRows("recursos", data.recursos || []);
        replaceRows("riscos", data.riscos || []);

        const avaliacao = data.avaliacao_tap || "";
        if (avaliacao) {
            showAvaliacao(avaliacao);
            if (avaliacao === "Gerando avaliação...") {
                startPolling();
            }
        }
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

    function renderSimpleMarkdown(texto) {
        const escaped = escapeHtml(texto || "");
        return escaped
            .replace(/\*\*(.+?)\*\*/g, "<strong>$1</strong>")
            .replace(/\*(.+?)\*/g, "<em>$1</em>")
            .replace(/\n/g, "<br>");
    }

    function renderMarkdown(texto) {
        if (window.frappe && typeof frappe.markdown === "function") {
            return frappe.markdown(texto);
        }
        return renderSimpleMarkdown(texto);
    }

    function showAvaliacao(value) {
        const section = document.getElementById("avaliacaoSection");
        const container = document.getElementById("avaliacao_tap_markdown");
        if (!section || !container) return;

        const textValue = String(value || "").trim();
        if (!textValue) return;

        const html = renderMarkdown(textValue);
        container.innerHTML = sanitizeRenderedHtml(html);
        section.classList.remove("d-none");
    }

    function stopPolling() {
        if (state.pollingId) {
            clearInterval(state.pollingId);
            state.pollingId = null;
        }
        state.pollingAttempts = 0;
    }

    async function pollAvaliacao() {
        if (!state.projetoName) return;

        try {
            const result = await callApi(METHODS.consultarIA, {
                projeto_name: state.projetoName,
            });

            if (result.avaliacao_tap) {
                showAvaliacao(result.avaliacao_tap);
            }

            if (!result.pending) {
                stopPolling();
                showAlert("Revisão por IA concluída.", "success");
            }
        } catch (error) {
            stopPolling();
            showAlert(error.message || "Falha ao consultar revisão por IA.", "error");
        }

        state.pollingAttempts += 1;
        if (state.pollingAttempts > 90) {
            stopPolling();
            showAlert("A avaliação está demorando mais que o esperado. Tente atualizar a página em instantes.", "error");
        }
    }

    function startPolling() {
        stopPolling();
        state.pollingId = setInterval(pollAvaliacao, 4000);
    }

    async function saveDraft(silent) {
        if (state.saving) return false;

        hideAlert();
        state.saving = true;
        setButtonsDisabled(true);

        try {
            const payload = buildPayload();
            const result = await callApi(METHODS.salvarRascunho, {
                projeto_name: state.projetoName || null,
                payload: JSON.stringify(payload),
            });

            syncProjetoReference(result.name);

            if (!silent) {
                showAlert("Rascunho salvo com sucesso.", "success");
            }
            return true;
        } catch (error) {
            resetActionState();
            showAlert(error.message || "Falha ao salvar rascunho.", "error");
            return false;
        } finally {
            resetActionState();
        }
    }

    async function submitProject() {
        if (state.saving) return;

        const pendingComments = getPendingReviewComments();
        if (pendingComments.length > 0) {
            showAlert("Resolva todos os comentários pendentes antes de submeter novamente para aprovação.", "error");
            return;
        }

        hideAlert();
        state.saving = true;
        setButtonsDisabled(true);

        try {
            const payload = buildPayload();
            const result = await callApi(METHODS.submeter, {
                projeto_name: state.projetoName || null,
                payload: JSON.stringify(payload),
            });

            syncProjetoReference(result.name);
            redirectToApprovalPage();
        } catch (error) {
            resetActionState();
            showAlert(error.message || "Falha ao submeter projeto.", "error");
        } finally {
            resetActionState();
        }
    }

    async function runAvaliacaoIA() {
        hideAlert();

        if (!state.projetoName) {
            const ok = await saveDraft(true);
            if (!ok) {
                showAlert("Não foi possível iniciar avaliação sem salvar o projeto.", "error");
                return;
            }
        }

        setButtonsDisabled(true);

        try {
            const result = await callApi(METHODS.solicitarIA, {
                projeto_name: state.projetoName,
            });

            showAvaliacao(result.avaliacao_tap || "Gerando avaliação...");
            showAlert("Revisão por IA iniciada. Aguarde o processamento.", "success");
            startPolling();
        } catch (error) {
            setButtonsDisabled(false);
            showAlert(error.message || "Falha ao iniciar revisão por IA.", "error");
        } finally {
            setButtonsDisabled(false);
        }
    }

    function bindTableEvents() {
        document.querySelectorAll("[data-add-row]").forEach((btn) => {
            btn.addEventListener("click", () => {
                const tableKey = btn.getAttribute("data-add-row");
                addRow(tableKey, {});
                if (tableKey === "cronograma") {
                    renderCronogramaGantt();
                }
            });
        });

        document.querySelectorAll("tbody[id^='rows_']").forEach((tbody) => {
            tbody.addEventListener("click", (event) => {
                const deleteBtn = event.target?.closest?.(".btn-delete-row");
                if (deleteBtn) {
                    event.preventDefault();
                    const row = deleteBtn.closest("tr");
                    if (row) {
                        if (tbody.id === "rows_aprovadores" && (row.dataset.canRemove || "0") !== "1") {
                            showAlert("Este aprovador é obrigatório e não pode ser removido.", "error");
                            return;
                        }
                        row.remove();
                        if (tbody.id === "rows_cronograma") {
                            renderCronogramaGantt();
                        }
                    }
                }
            });
        });
    }

    function bindEquipeBuilderActions() {
        const tipoSelect = document.getElementById("equipe_tipo_pessoa");
        const associadoSelect = document.getElementById("equipe_associado");
        const responsavelSelect = document.getElementById("equipe_responsavel");
        const btnAdicionar = document.getElementById("btnAdicionarEquipe");

        if (tipoSelect) {
            tipoSelect.addEventListener("change", updateEquipeBuilderMode);
        }

        if (associadoSelect) {
            associadoSelect.addEventListener("change", () => {
                if ((tipoSelect?.value || "") === "Associado") {
                    preencherEquipePeloCadastro("Associado", associadoSelect.value || "");
                }
            });
        }

        if (responsavelSelect) {
            responsavelSelect.addEventListener("change", () => {
                if ((tipoSelect?.value || "") === "Responsavel") {
                    preencherEquipePeloCadastro("Responsavel", responsavelSelect.value || "");
                }
            });
        }

        if (btnAdicionar) {
            btnAdicionar.addEventListener("click", () => {
                const tipo = tipoSelect?.value || "Associado";
                const associado = document.getElementById("equipe_associado")?.value || "";
                const responsavel = document.getElementById("equipe_responsavel")?.value || "";
                const nome = document.getElementById("equipe_nome")?.value || "";
                const email = document.getElementById("equipe_email")?.value || "";
                const telefone = document.getElementById("equipe_telefone")?.value || "";
                const funcao = document.getElementById("equipe_funcao")?.value || "";

                if (tipo === "Associado" && !associado) {
                    showAlert("Selecione o associado para adicionar na equipe.", "error");
                    return;
                }

                if (tipo === "Responsavel" && !responsavel) {
                    showAlert("Selecione o responsável para adicionar na equipe.", "error");
                    return;
                }

                if (!nome || !email || !telefone) {
                    showAlert("Preencha nome, email e telefone para adicionar na equipe.", "error");
                    return;
                }

                addRow("equipe_de_interesse", {
                    tipo_pessoa: tipo,
                    associado: tipo === "Associado" ? associado : "",
                    responsavel: tipo === "Responsavel" ? responsavel : "",
                    nome,
                    email,
                    telefone,
                    funcao,
                });

                document.getElementById("equipe_associado").value = "";
                document.getElementById("equipe_responsavel").value = "";
                clearEquipeBuilderPersonalFields();
                document.getElementById("equipe_funcao").value = "";
                updateEquipeBuilderMode();
            });
        }
    }

    function hasAprovadorKeyInTable(aprovadorKey) {
        const key = String(aprovadorKey || "").trim();
        if (!key) return false;
        const tbody = document.getElementById("rows_aprovadores");
        if (!tbody) return false;
        return Array.from(tbody.querySelectorAll("tr")).some(
            (tr) => (tr.dataset.aprovadorKey || "") === key
        );
    }

    function bindAprovadorBuilderActions() {
        const tipoSelect = document.getElementById("aprovador_tipo_pessoa");
        const associadoSelect = document.getElementById("aprovador_associado");
        const responsavelSelect = document.getElementById("aprovador_responsavel");
        const btnAdicionar = document.getElementById("btnAdicionarAprovador");

        if (tipoSelect) {
            tipoSelect.addEventListener("change", updateAprovadorBuilderMode);
        }

        if (associadoSelect) {
            associadoSelect.addEventListener("change", () => {
                if ((tipoSelect?.value || "") === "Associado") {
                    preencherAprovadorPeloCadastro("Associado", associadoSelect.value || "");
                }
            });
        }

        if (responsavelSelect) {
            responsavelSelect.addEventListener("change", () => {
                if ((tipoSelect?.value || "") === "Responsavel") {
                    preencherAprovadorPeloCadastro("Responsavel", responsavelSelect.value || "");
                }
            });
        }

        if (btnAdicionar) {
            btnAdicionar.addEventListener("click", () => {
                const tipo = tipoSelect?.value === "Responsavel" ? "Responsavel" : "Associado";
                const associado = (associadoSelect?.value || "").trim();
                const responsavel = (responsavelSelect?.value || "").trim();
                const nome = (document.getElementById("aprovador_nome")?.value || "").trim();
                const email = (document.getElementById("aprovador_email")?.value || "").trim();
                const telefone = (document.getElementById("aprovador_telefone")?.value || "").trim();

                if (tipo === "Associado" && !associado) {
                    showAlert("Selecione o associado para adicionar o aprovador.", "error");
                    return;
                }
                if (tipo === "Responsavel" && !responsavel) {
                    showAlert("Selecione o responsável para adicionar o aprovador.", "error");
                    return;
                }
                if (!nome || !email || !telefone) {
                    showAlert("Nome, email e telefone do aprovador são obrigatórios.", "error");
                    return;
                }

                const aprovadorKey = `${tipo}:${tipo === "Associado" ? associado : responsavel}`;
                if (hasAprovadorKeyInTable(aprovadorKey)) {
                    showAlert("Este aprovador já está na lista.", "error");
                    return;
                }

                addRow("aprovadores", {
                    tipo_pessoa: tipo,
                    associado: tipo === "Associado" ? associado : "",
                    responsavel: tipo === "Responsavel" ? responsavel : "",
                    nome,
                    email,
                    telefone,
                    origem_regra: "manual",
                    permite_remover: 1,
                });

                if (associadoSelect) associadoSelect.value = "";
                if (responsavelSelect) responsavelSelect.value = "";
                clearAprovadorBuilderPersonalFields();
                updateAprovadorBuilderMode();
            });
        }
    }

    function bindActions() {
        const btnSalvar = document.getElementById("btnSalvarRascunho");
        const btnSubmeter = document.getElementById("btnSubmeter");
        const btnIA = document.getElementById("btnAvaliacaoIA");
        const btnPendencias = document.getElementById("btnPendenciasRevisao");
        const btnConfirmSubmit = document.getElementById("btnConfirmSubmitProjeto");
        const coordenador = document.getElementById("coordenador");
        const tipo = document.getElementById("tipo_padrinho_ou_orientador");
        const padrinhoAssociado = document.getElementById("padrinho_associado");
        const padrinhoResponsavel = document.getElementById("padrinho_responsavel");

        if (btnSalvar) {
            btnSalvar.addEventListener("click", () => saveDraft(false));
        }
        if (btnSubmeter) {
            btnSubmeter.addEventListener("click", openSubmitConfirmModal);
        }
        if (btnConfirmSubmit) {
            btnConfirmSubmit.addEventListener("click", submitProject);
        }
        if (btnIA) {
            btnIA.addEventListener("click", runAvaliacaoIA);
        }
        if (btnPendencias) {
            btnPendencias.addEventListener("click", openPendingReviewModal);
        }
        if (coordenador) {
            coordenador.addEventListener("change", async () => {
                await syncSponsorAprovadorRowInTable();
            });
        }
        if (tipo) {
            tipo.addEventListener("change", async () => {
                updateSponsorVisibility();
                await syncSponsorAprovadorRowInTable();
            });
        }
        if (padrinhoAssociado) {
            padrinhoAssociado.addEventListener("change", async () => {
                await syncSponsorAprovadorRowInTable();
            });
        }
        if (padrinhoResponsavel) {
            padrinhoResponsavel.addEventListener("change", async () => {
                await syncSponsorAprovadorRowInTable();
            });
        }

        document.querySelectorAll("[data-pending-review-close]").forEach((btn) => {
            btn.addEventListener("click", closePendingReviewModal);
        });

        document.querySelectorAll("[data-submit-confirm-close]").forEach((btn) => {
            btn.addEventListener("click", closeSubmitConfirmModal);
        });

        const pendingTable = document.getElementById("rows_pending_review_comments");
        if (pendingTable) {
            pendingTable.addEventListener("click", (event) => {
                const button = event.target.closest("[data-resolve-review-comment]");
                if (!button) return;
                const commentName = button.getAttribute("data-resolve-review-comment") || "";
                resolveReviewComment(commentName);
            });
        }

        bindEquipeBuilderActions();
        bindAprovadorBuilderActions();
    }

    function openInfoModal(key) {
        const modal = document.getElementById("infoModal");
        const title = document.getElementById("infoModalTitle");
        const body = document.getElementById("infoModalBody");
        const data = INFO_CONTENT[key];
        if (!modal || !title || !body || !data) return;

        title.textContent = data.title;
        body.innerHTML = data.body;
        modal.classList.remove("d-none");
        modal.setAttribute("aria-hidden", "false");
        document.body.classList.add("info-modal-open");
    }

    function closeInfoModal() {
        const modal = document.getElementById("infoModal");
        if (!modal) return;
        modal.classList.add("d-none");
        modal.setAttribute("aria-hidden", "true");
        document.body.classList.remove("info-modal-open");
    }

    function bindInfoModal() {
        document.querySelectorAll("[data-info-key]").forEach((btn) => {
            btn.addEventListener("click", () => {
                const key = btn.getAttribute("data-info-key") || "";
                openInfoModal(key);
            });
        });

        document.querySelectorAll("[data-info-close]").forEach((btn) => {
            btn.addEventListener("click", closeInfoModal);
        });

        document.addEventListener("keydown", (event) => {
            if (event.key === "Escape") {
                closeInfoModal();
                closePendingReviewModal();
                closeSubmitConfirmModal();
            }
        });
    }

    function syncProjetoReference(projetoName) {
        const normalized = String(projetoName || "").trim();
        if (!normalized) {
            return;
        }

        state.projetoName = normalized;

        const hidden = document.getElementById("projetoName");
        if (hidden) {
            hidden.value = normalized;
        }

        const url = new URL(window.location.href);
        if (url.searchParams.get("projeto") !== normalized) {
            url.searchParams.set("projeto", normalized);
            const nextUrl = `${url.pathname}?${url.searchParams.toString()}${url.hash}`;
            window.history.replaceState({}, "", nextUrl);
        }
    }

    function getProjetoNameFromPage() {
        const hidden = (document.getElementById("projetoName")?.value || "").trim();
        if (hidden) return hidden;

        const params = new URLSearchParams(window.location.search);
        return (params.get("projeto") || "").trim();
    }

    async function bootstrap() {
        bindInfoModal();
        bindActions();
        bindTableEvents();
        bindCronogramaTableSync();
        bindCronogramaTableDrag();
        bindCronogramaGanttEvents();
        attachDateMask(document.getElementById("data_de_inicio"));
        attachDateMask(document.getElementById("data_de_termino"));
        updateSponsorVisibility();
        updateAprovadorBuilderMode();

        state.projetoName = getProjetoNameFromPage();

        try {
            const result = await callApi(METHODS.bootstrap, {
                projeto_name: state.projetoName || null,
            });

            state.choices = result.choices || state.choices;
            state.defaultAprovadores = result.default_aprovadores || [];

            fillSelect("coordenador", state.choices.associados, "Selecione...");
            fillSelect(
                "padrinho_associado",
                state.choices.associados_padrinho || state.choices.associados,
                "Selecione..."
            );
            fillSelect("padrinho_responsavel", state.choices.responsaveis, "Selecione...");
            fillSelect("equipe_associado", state.choices.associados, "Selecione...");
            fillSelect("equipe_responsavel", state.choices.responsaveis, "Selecione...");
            fillSelect("aprovador_associado", state.choices.associados, "Selecione...");
            fillSelect("aprovador_responsavel", state.choices.responsaveis, "Selecione...");
            updateEquipeBuilderMode();
            updateAprovadorBuilderMode();

            const projeto = result.projeto;
            if (projeto) {
                syncProjetoReference(projeto.name);
                fillForm(projeto);
                await syncSponsorAprovadorRowInTable();
            } else {
                state.reviewComments = [];
                updatePendingReviewBanner();
                replaceRows("equipe_de_interesse", []);
                replaceRows("aprovadores", state.defaultAprovadores || []);
                replaceRows("objetivos", []);
                replaceRows("ods", []);
                replaceRows("cronograma", []);
                replaceRows("recursos", []);
                replaceRows("riscos", []);
                await syncSponsorAprovadorRowInTable();
            }

            renderCronogramaGantt();
        } catch (error) {
            showAlert(error.message || "Falha ao carregar dados do formulário.", "error");
        }
    }

    document.addEventListener("DOMContentLoaded", bootstrap);
})();
