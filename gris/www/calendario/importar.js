(function () {
  if (window.__importar_calendario_inited) return;
  window.__importar_calendario_inited = true;

  window._uploadedFileUrl = null;

  function checkShowImportBtn() {
    const btn = document.getElementById('btnImportar');
    const hasFile = !!window._uploadedFileUrl;
    if (btn) {
      btn.classList.toggle('d-none', !hasFile);
      btn.disabled = !hasFile;
    }
  }

  function setupUploader() {
    const btn = document.getElementById('uploadPdfBtn');
    if (!btn) return;

    btn.addEventListener('click', function (e) {
      if (btn.disabled) return;
      e.stopPropagation();

      if (typeof frappe === 'undefined' || !frappe.ui || !frappe.ui.FileUploader) {
        frappe.msgprint('Uploader indisponível.');
        return;
      }

      if (window.__opening_uploader) return;
      window.__opening_uploader = true;
      setTimeout(() => { window.__opening_uploader = false; }, 500);

      new frappe.ui.FileUploader({
        allow_multiple: false,
        restrictions: { 
          allowed_file_extensions: ['pdf'], 
          max_number_of_files: 1 
        },
        is_private: 0,
        options: ['Local'],
        on_success(file) {
          const fileInfo = document.getElementById('file-info');
          const fileName = document.getElementById('file-name');
          
          if (fileName) {
            fileName.textContent = file.file_name || file.name;
          }
          if (fileInfo) {
            fileInfo.classList.remove('d-none');
          }
          
          window._uploadedFileUrl = file.file_url;
          checkShowImportBtn();
          
          // Hide previous results
          const resultsDiv = document.getElementById('import-results');
          if (resultsDiv) {
            resultsDiv.classList.add('d-none');
          }
        },
      });
    });
  }

  function renderResults(data) {
    const resultsDiv = document.getElementById('import-results');
    const resultsGrid = document.getElementById('results-grid');
    const errorsContainer = document.getElementById('errors-container');
    const errorsList = document.getElementById('errors-list');

    if (!resultsDiv || !resultsGrid) return;

    // Clear previous results
    resultsGrid.innerHTML = '';
    if (errorsContainer) errorsContainer.classList.add('d-none');
    if (errorsList) errorsList.innerHTML = '';

    // Show results section
    resultsDiv.classList.remove('d-none');

    // Create stats cards
    const stats = [
      { label: 'Total de Registros', value: data.total || 0, color: 'primary' },
      { label: 'Criados', value: data.created || 0, color: 'success' },
      { label: 'Atualizados', value: data.updated || 0, color: 'info' },
      { label: 'Sem Alteração', value: data.skipped || 0, color: 'secondary' },
      { label: 'Erros', value: data.errors || 0, color: 'danger' },
    ];

    stats.forEach(stat => {
      const card = document.createElement('div');
      card.className = 'col-6 col-lg-2dot4';
      card.innerHTML = `
        <div class="card border-0 shadow-sm h-100">
          <div class="card-body text-center">
            <div class="display-6 fw-bold text-${stat.color}">${stat.value}</div>
            <div class="text-muted small mt-2">${stat.label}</div>
          </div>
        </div>
      `;
      resultsGrid.appendChild(card);
    });

    // Show errors if any
    if (data.error_details && data.error_details.length > 0) {
      if (errorsContainer && errorsList) {
        const errorItems = data.error_details
          .slice(0, 50)
          .map(err => `<li>${frappe.utils.escape_html(err || '')}</li>`)
          .join('');
        
        const moreText = data.error_details.length > 50 
          ? `<div class="text-muted mt-2">(+${data.error_details.length - 50} erros adicionais... ver Error Log)</div>` 
          : '';
        
        errorsList.innerHTML = `<ul class="mb-0">${errorItems}</ul>${moreText}`;
        errorsContainer.classList.remove('d-none');
      }
    }
  }

  function importCalendario() {
    if (!window._uploadedFileUrl) {
      frappe.msgprint('Selecione um arquivo antes de importar.');
      return;
    }

    const loadingIndicator = document.getElementById('loading-indicator');
    const btnImportar = document.getElementById('btnImportar');

    // Show loading
    if (loadingIndicator) loadingIndicator.classList.remove('d-none');
    if (btnImportar) btnImportar.disabled = true;

    frappe.call({
      method: 'gris.api.calendario.importer.parse_calendario_report',
      args: {
        path_pdf: window._uploadedFileUrl
      },
      callback: function (r) {
        // Hide loading
        if (loadingIndicator) loadingIndicator.classList.add('d-none');
        if (btnImportar) btnImportar.disabled = false;

        if (r.message) {
          renderResults(r.message);
          frappe.show_alert({
            message: 'Importação concluída com sucesso!',
            indicator: 'green'
          });
        }
      },
      error: function (err) {
        // Hide loading
        if (loadingIndicator) loadingIndicator.classList.add('d-none');
        if (btnImportar) btnImportar.disabled = false;

        frappe.msgprint({
          title: 'Erro na Importação',
          message: 'Ocorreu um erro ao processar o arquivo. Verifique o console ou os logs do sistema.',
          indicator: 'red'
        });
        console.error('Erro ao importar calendário:', err);
      }
    });
  }

  // Setup
  setupUploader();
  checkShowImportBtn();

  // Bind import button
  const btnImportar = document.getElementById('btnImportar');
  if (btnImportar) {
    btnImportar.addEventListener('click', importCalendario);
  }
})();
