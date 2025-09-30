// Exportar XLSX usando API que preenche o template
(function () {
  const btn = document.getElementById('export-xlsx');
  if (!btn) {
    console.warn('Export button not found');
    return;
  }

  btn.addEventListener('click', function () {
    try {
      // Read date inputs from the page (fall back to empty)
      const dataInicioInput = document.querySelector('input[name="data_inicio"]');
      const dataFimInput = document.querySelector('input[name="data_fim"]');

      const params = new URLSearchParams();
      if (dataInicioInput && dataInicioInput.value) params.set('data_inicio', dataInicioInput.value);
      if (dataFimInput && dataFimInput.value) params.set('data_fim', dataFimInput.value);

      // Build API method URL (Frappe whitelisted method)
      const url = '/api/method/gris.api.financeiro.relatorios.export_relatorio_contabil' + (params.toString() ? ('?' + params.toString()) : '');
      console.info('Export URL:', url);

      // Navigate to the URL to let browser download the file
      window.location.href = url;
    } catch (err) {
      console.error('Erro ao iniciar export:', err);
    }
  });
})();
