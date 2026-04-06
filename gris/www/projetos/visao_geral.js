(function () {
    function openDraftProject(card) {
        const projectName = (card.getAttribute("data-project-name") || "").trim();
        const status = (card.getAttribute("data-status") || "").trim();

        if (!projectName || status !== "Rascunho") {
            return;
        }

        const targetUrl = `/projetos/cadastrar_novo_projeto?projeto=${encodeURIComponent(projectName)}`;
        window.location.href = targetUrl;
    }

    function openApprovalProject(card) {
        const projectName = (card.getAttribute("data-project-name") || "").trim();
        const status = (card.getAttribute("data-status") || "").trim();

        if (!projectName || status !== "Em aprovacao") {
            return;
        }

        const targetUrl = `/projetos/aprovacao_projeto?projeto=${encodeURIComponent(projectName)}`;
        window.location.href = targetUrl;
    }

    function openApprovedProject(card) {
        const projectName = (card.getAttribute("data-project-name") || "").trim();
        const status = (card.getAttribute("data-status") || "").trim();

        if (!projectName || status !== "Aprovado") {
            return;
        }

        const targetUrl = `/projetos/projeto_aprovado?projeto=${encodeURIComponent(projectName)}`;
        window.location.href = targetUrl;
    }

    function openExecutionProject(card) {
        const projectName = (card.getAttribute("data-project-name") || "").trim();
        const status = (card.getAttribute("data-status") || "").trim();

        if (!projectName || status !== "Em execucao") {
            return;
        }

        const targetUrl = `/projetos/projeto?projeto=${encodeURIComponent(projectName)}`;
        window.location.href = targetUrl;
    }

    function openClosedProject(card) {
        const projectName = (card.getAttribute("data-project-name") || "").trim();
        const status = (card.getAttribute("data-status") || "").trim();

        if (!projectName || (status !== "Concluido" && status !== "Cancelado")) {
            return;
        }

        const targetUrl = `/projetos/projeto?projeto=${encodeURIComponent(projectName)}`;
        window.location.href = targetUrl;
    }

    function bindProjectCards() {
        document.addEventListener("click", (event) => {
            const card = event.target.closest(".kanban-card");
            if (!card) {
                return;
            }

            openDraftProject(card);
            openApprovalProject(card);
            openApprovedProject(card);
            openExecutionProject(card);
            openClosedProject(card);
        });
    }

    document.addEventListener("DOMContentLoaded", bindProjectCards);
})();
