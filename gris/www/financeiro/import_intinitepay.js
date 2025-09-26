// Página de importação Intinitepay: upload de 3 arquivos e processamento com cards de resultado
(function () {
  if (window.__ip_import_page_inited) return;
  window.__ip_import_page_inited = true;
  // Flag injetada no template via contexto (se disponível)
  const CAN_RECONCILE = (window.frappe && frappe.boot && frappe.boot.can_reconcile_intinitepay) || (typeof can_reconcile_intinitepay !== 'undefined' ? can_reconcile_intinitepay : undefined);

  window._extratoFileUrl = null;
  window._vendasFileUrl = null;
  window._recebimentosFileUrl = null;

  function checkShowConciliarBtn() {
    const btn = document.getElementById('btnConciliarInfinitepay');
    const ok = !!(window._extratoFileUrl && window._vendasFileUrl && window._recebimentosFileUrl);
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
      if (CAN_RECONCILE === false) { frappe.msgprint('Sem permissão para enviar arquivos.'); return; }
      e.stopPropagation();
      btn.setAttribute('accept', allowedExt.map((ext) => '.' + ext).join(','));
      if (typeof frappe === 'undefined' || !frappe.ui || !frappe.ui.FileUploader) {
        frappe.msgprint('Uploader indisponível.');
        return;
      }
      if (window.__ip_opening_uploader) return;
      window.__ip_opening_uploader = true;
      setTimeout(() => { window.__ip_opening_uploader = false; }, 500);

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
          if (btnId === 'uploadExtratoBtn') window._extratoFileUrl = file.file_url;
          if (btnId === 'uploadVendasBtn') window._vendasFileUrl = file.file_url;
          if (btnId === 'uploadRecebimentosBtn') window._recebimentosFileUrl = file.file_url;
          checkShowConciliarBtn();
        },
      });
    });
  }

  setupUploader('uploadExtratoBtn', 'nomeExtratoInfinitepay', 'checkExtratoInfinitepay', ['ofx']);
  setupUploader('uploadVendasBtn', 'nomeVendasInfinitepay', 'checkVendasInfinitepay', ['csv']);
  setupUploader('uploadRecebimentosBtn', 'nomeRecebimentosInfinitepay', 'checkRecebimentosInfinitepay', ['csv']);

  function renderResults(payload) {
    const container = document.getElementById('ip-results');
    const grid = document.getElementById('ip-stat-cards');
    const errWrap = document.getElementById('ip-errors-card');
    if (!container || !grid || !errWrap) return;

    grid.innerHTML = '';
    errWrap.innerHTML = '';
    grid.classList.add('d-none');
    errWrap.classList.add('d-none');

    const stats = (payload && payload.stats) || {};
    const cards = [
      { key: 'extrato', title: 'Transacao Infinitepay extrato' },
      { key: 'vendas', title: 'Transacao Infinitepay vendas' },
      { key: 'recebimentos', title: 'Transacao Infinitepay recebimento' },
      { key: 'geral', title: 'Transacao Extrato Geral' },
    ];

    let hasAny = false;
    cards.forEach((c) => {
      const s = stats[c.key] || { total: 0, inserted: 0, skipped_exist: 0, failed: 0 };
      const el = document.createElement('div');
      el.className = 'col-12 col-md-6 col-lg-3';
      el.innerHTML = `
        <div class="card shadow-sm h-100">
          <div class="card-body">
            <div class="small text-muted">${c.title}</div>
            <div class="d-flex flex-column mt-2 gap-1">
              <div><strong>Total:</strong> ${s.total ?? 0}</div>
              <div class="text-success"><strong>Inseridos:</strong> ${s.inserted ?? 0}</div>
              <div class="text-warning"><strong>Repetidos:</strong> ${s.skipped_exist ?? 0}</div>
              <div class="text-danger"><strong>Erros:</strong> ${s.failed ?? 0}</div>
            </div>
          </div>
        </div>`;
      grid.appendChild(el);
      hasAny = true;
    });
    if (hasAny) grid.classList.remove('d-none');

    const errors = (payload && payload.errors) || {};
    const sections = ['extrato', 'vendas', 'recebimentos', 'geral'];
    const flat = [];
    sections.forEach((k) => {
      const arr = errors[k] || [];
      arr.forEach((msg) => flat.push({ section: k, msg }));
    });
    if (flat.length) {
      const el = document.createElement('div');
      el.className = 'card shadow-sm mt-2';
      const items = flat
        .slice(0, 50)
        .map((e) => `<li><code>${e.section}</code>: ${frappe.utils.escape_html(e.msg || '')}</li>`)
        .join('');
      const more = flat.length > 50 ? `<div class="text-muted small mt-2">(+${flat.length - 50} outras… ver Error Log)</div>` : '';
      el.innerHTML = `
        <div class="card-body">
          <div class="d-flex align-items-center mb-2">
            <span class="badge bg-danger me-2">Erros</span>
            <div class="fw-bold">Ocorreram erros de inserção</div>
          </div>
          <ul class="mb-0 small">${items}</ul>
          ${more}
        </div>`;
      errWrap.appendChild(el);
      errWrap.classList.remove('d-none');
    }
  }

  window.enviarArquivosImportados = function () {
  if (CAN_RECONCILE === false) { frappe.msgprint('Sem permissão para conciliar.'); return; }
    if (!window._extratoFileUrl || !window._vendasFileUrl || !window._recebimentosFileUrl) {
      frappe.msgprint('Faça o upload dos três arquivos antes de enviar.');
      return;
    }
    frappe.call({
      method: 'gris.www.financeiro.contas.process_uploaded_files',
      args: {
        extrato_file_url: window._extratoFileUrl,
        vendas_file_url: window._vendasFileUrl,
        recebimentos_file_url: window._recebimentosFileUrl,
      },
      callback: function (r) {
        if (r && r.exc) {
          console.error('Erro process_uploaded_files', r.exc);
          frappe.msgprint('Erro ao processar: ver console.');
          return;
        }
        const payload = (r && r.message) ? r.message : r;
        renderResults(payload);
        frappe.show_alert({ message: 'Conciliação concluída', indicator: 'green' }, 5);
      },
    });
  };
})();
