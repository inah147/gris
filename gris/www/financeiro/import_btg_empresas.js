(function () {
  if (window.__btg_import_page_inited) return;
  window.__btg_import_page_inited = true;

  window._btgFileUrl = null;

  function checkShowConciliarBtn() {
    const btn = document.getElementById('btnConciliarBtg');
    const ok = !!window._btgFileUrl;
    if (btn) {
      btn.classList.toggle('d-none', !ok);
      btn.disabled = !ok;
    }
  }

  function setupUploader(btnId, nomeId, checkId, allowedExt) {
    const btn = document.getElementById(btnId);
    if (!btn) return;
    btn.addEventListener('click', function (e) {
      if (btn.disabled) return;
      e.stopPropagation();
      btn.setAttribute('accept', allowedExt.map((ext) => '.' + ext).join(','));
      if (typeof frappe === 'undefined' || !frappe.ui || !frappe.ui.FileUploader) {
        frappe.msgprint('Uploader indisponível.');
        return;
      }
      if (window.__btg_opening_uploader) return;
      window.__btg_opening_uploader = true;
      setTimeout(() => { window.__btg_opening_uploader = false; }, 500);

      new frappe.ui.FileUploader({
        allow_multiple: false,
        restrictions: { allowed_file_extensions: allowedExt, max_number_of_files: 1 },
        is_private: 0,
        options: ['Local'],
        on_success(file) {
          const nomeSpan = document.getElementById(nomeId);
          const checkSpan = document.getElementById(checkId);
          if (nomeSpan) { nomeSpan.textContent = file.file_name || file.name; nomeSpan.classList.remove('d-none'); }
          if (checkSpan) checkSpan.classList.remove('d-none');
          window._btgFileUrl = file.file_url;
          checkShowConciliarBtn();
        },
      });
    });
  }

  setupUploader('uploadBtgBtn', 'nomeBtg', 'checkBtg', ['ofx']);

  function renderResults(payload) {
    const grid = document.getElementById('btg-stat-card');
    const errWrap = document.getElementById('btg-errors-card');
    if (!grid || !errWrap) return;
    grid.innerHTML = '';
    errWrap.innerHTML = '';
    grid.classList.add('d-none');
    errWrap.classList.add('d-none');

    const stats = (payload && payload.stats) || { total: 0, inserted: 0, skipped_exist: 0, failed: 0 };
    const el = document.createElement('div');
    el.className = 'col-12 col-md-6 col-lg-4';
    el.innerHTML = `
      <div class="card shadow-sm h-100">
        <div class="card-body">
          <div class="small text-muted">Transacao Extrato Geral</div>
          <div class="d-flex flex-column mt-2 gap-1">
            <div><strong>Total:</strong> ${stats.total ?? 0}</div>
            <div class="text-success"><strong>Inseridos:</strong> ${stats.inserted ?? 0}</div>
            <div class="text-warning"><strong>Repetidos:</strong> ${stats.skipped_exist ?? 0}</div>
            <div class="text-danger"><strong>Erros:</strong> ${stats.failed ?? 0}</div>
          </div>
        </div>
      </div>`;
    grid.appendChild(el);
    grid.classList.remove('d-none');

    const errors = (payload && payload.errors) || [];
    if (errors.length) {
      const errEl = document.createElement('div');
      errEl.className = 'card shadow-sm mt-2';
      const items = errors.slice(0, 50).map((e) => `<li>${frappe.utils.escape_html(e || '')}</li>`).join('');
      const more = errors.length > 50 ? `<div class="text-muted small mt-2">(+${errors.length - 50} outras… ver Error Log)</div>` : '';
      errEl.innerHTML = `
        <div class="card-body">
          <div class="d-flex align-items-center mb-2">
            <span class="badge bg-danger me-2">Erros</span>
            <div class="fw-bold">Ocorreram erros de inserção</div>
          </div>
          <ul class="mb-0 small">${items}</ul>
          ${more}
        </div>`;
      errWrap.appendChild(errEl);
      errWrap.classList.remove('d-none');
    }
  }

  window.sendBtgFile = function () {
    if (!window._btgFileUrl) {
      frappe.msgprint('Selecione um arquivo antes de enviar.');
      return;
    }

    const loadingIndicator = document.getElementById('btg-loading-indicator');
    const btnConciliar = document.getElementById('btnConciliarBtg');
    const resultsDiv = document.getElementById('btg-results');

    // Show loading, hide results, disable button
    if (loadingIndicator) loadingIndicator.classList.remove('d-none');
    if (btnConciliar) btnConciliar.disabled = true;
    if (resultsDiv) resultsDiv.classList.add('d-none');

    frappe.call({
      method: 'gris.www.financeiro.import_btg_empresas.process_uploaded_btg_file',
      args: {
        file_url: window._btgFileUrl
      },
      callback: function (r) {
        // Hide loading, enable button, show results
        if (loadingIndicator) loadingIndicator.classList.add('d-none');
        if (btnConciliar) btnConciliar.disabled = false;
        if (resultsDiv) resultsDiv.classList.remove('d-none');

        if (r && r.exc) {
          console.error('Erro process_uploaded_btg_file', r.exc);
          frappe.msgprint('Erro ao processar: ver console.');
          return;
        }
        const payload = (r && r.message) ? r.message : r;
        renderResults(payload);
        frappe.show_alert({ message: 'Conciliação concluída', indicator: 'green' }, 5);
      }
    });
  };
})();
