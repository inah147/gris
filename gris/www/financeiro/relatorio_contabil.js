(() => {
  document.addEventListener("DOMContentLoaded", () => {
    const btn = document.getElementById("export-xlsx");
    if (!btn) {
      return;
    }

    const getFilterValue = (name) => {
      const hiddenInput = document.querySelector(`input[type="hidden"][name="${name}"]`);
      if (hiddenInput && typeof hiddenInput.value === "string") {
        return hiddenInput.value.trim();
      }

      const fallbackField = document.querySelector(`[name="${name}"]`);
      if (fallbackField && typeof fallbackField.value === "string") {
        return fallbackField.value.trim();
      }

      return "";
    };

    btn.addEventListener("click", () => {
      try {
        const params = new URLSearchParams();
        const dataInicio = getFilterValue("data_inicio");
        const dataFim = getFilterValue("data_fim");

        if (dataInicio) {
          params.set("data_inicio", dataInicio);
        }
        if (dataFim) {
          params.set("data_fim", dataFim);
        }

        const baseUrl = "/api/method/gris.api.financeiro.relatorios.export_relatorio_contabil";
        const url = params.toString() ? `${baseUrl}?${params.toString()}` : baseUrl;
        window.location.href = url;
      } catch (error) {
        console.error("Erro ao iniciar exportação XLSX:", error);
      }
    });
  });
})();
