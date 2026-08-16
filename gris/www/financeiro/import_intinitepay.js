(function () {
  if (window.__ip_import_page_inited) return;
  window.__ip_import_page_inited = true;

  const CAN_RECONCILE = (window.frappe && frappe.boot && frappe.boot.can_reconcile_intinitepay);

  window._extratoFileUrl = null;
  window._vendasFileUrl = null;
  window._recebimentosFileUrl = null;

  function escapeHtml(value) {
    if (window.frappe && frappe.utils && frappe.utils.escape_html) {
      return frappe.utils.escape_html(String(value ?? ''));
    }
    const div = document.createElement('div');
    div.textContent = String(value ?? '');
    return div.innerHTML;
  }

  function showToast(category, title, description) {
    const toaster = document.getElementById('toaster');
    if (toaster) {
      document.dispatchEvent(new CustomEvent('basecoat:toast', {
        detail: { config: { category, title, description } },
      }));
      return;
    }
    if (window.frappe && frappe.show_alert) {
      frappe.show_alert({
        message: description || title,
        indicator: category === 'error' ? 'red' : 'green',
      });
    }
  }

  function checkShowConciliarBtn() {
    const btn = document.getElementById('btnConciliarInfinitepay');
    const ok = !!(window._extratoFileUrl && window._vendasFileUrl && window._recebimentosFileUrl);
    if (btn) {
      btn.classList.toggle('hidden', !ok);
      btn.disabled = !ok || CAN_RECONCILE === false;
    }
  }

  function setupUploader(uploaderId, fileInfoId, nomeId, urlSetter) {
    const uploader = document.getElementById(uploaderId);
    if (!uploader) return;

    uploader.addEventListener('gris:file-upload:success', function (event) {
      const file = event.detail && event.detail.files && event.detail.files[0];
      if (!file) return;

      const fileInfo = document.getElementById(fileInfoId);
      const fileName = document.getElementById(nomeId);

      if (fileName) {
        fileName.textContent = file.file_name || file.name || file.file_url || '';
      }
      if (fileInfo) fileInfo.classList.remove('hidden');

      urlSetter(file.file_url);
      checkShowConciliarBtn();

      const resultsDiv = document.getElementById('ip-results');
      if (resultsDiv) resultsDiv.classList.add('hidden');
    });
  }

  setupUploader('ipExtratoUpload', 'file-info-extrato', 'nomeExtratoInfinitepay', function (url) {
    window._extratoFileUrl = url;
  });
  setupUploader('ipVendasUpload', 'file-info-vendas', 'nomeVendasInfinitepay', function (url) {
    window._vendasFileUrl = url;
  });
  setupUploader('ipRecebimentosUpload', 'file-info-recebimentos', 'nomeRecebimentosInfinitepay', function (url) {
    window._recebimentosFileUrl = url;
  });

  function buildStatCards(stats) {
    const cards = [
      { label: 'Total de transações', value: stats.total || 0, tone: 'primary' },
      { label: 'Inseridos', value: stats.inserted || 0, tone: 'success' },
      { label: 'Repetidos', value: stats.skipped_exist || 0, tone: 'muted' },
      { label: 'Erros', value: stats.failed || 0, tone: 'error' },
    ];
    return cards.map(function (stat) {
      return `
        <article class="card import-stat-card" data-tone="${escapeHtml(stat.tone)}">
          <section>
            <p class="import-stat-card__value">${escapeHtml(stat.value)}</p>
            <p class="import-stat-card__label">${escapeHtml(stat.label)}</p>
          </section>
        </article>
      `;
    }).join('');
  }

  function renderResults(payload) {
    const resultsDiv = document.getElementById('ip-results');
    const sections = document.getElementById('ip-stat-cards');
    const errWrap = document.getElementById('ip-errors-card');
    const errList = document.getElementById('ip-errors-list');
    if (!resultsDiv || !sections || !errWrap || !errList) return;

    sections.innerHTML = '';
    errList.innerHTML = '';
    errWrap.classList.add('hidden');
    resultsDiv.classList.remove('hidden');

    const stats = (payload && payload.stats) || {};
    const groups = [
      { key: 'extrato', title: 'Transação Infinitepay extrato' },
      { key: 'vendas', title: 'Transação Infinitepay vendas' },
      { key: 'recebimentos', title: 'Transação Infinitepay recebimento' },
      { key: 'geral', title: 'Transação Extrato Geral' },
    ];

    groups.forEach(function (group) {
      const groupStats = stats[group.key] || { total: 0, inserted: 0, skipped_exist: 0, failed: 0 };
      const section = document.createElement('section');
      section.className = 'import-results__section';
      section.innerHTML = `
        <h3 class="import-results__section-title">${escapeHtml(group.title)}</h3>
        <div class="import-results-grid">${buildStatCards(groupStats)}</div>
      `;
      sections.appendChild(section);
    });

    const errors = (payload && payload.errors) || {};
    const sectionKeys = ['extrato', 'vendas', 'recebimentos', 'geral'];
    const flat = [];
    sectionKeys.forEach(function (k) {
      const arr = errors[k] || [];
      arr.forEach(function (msg) { flat.push({ section: k, msg: msg }); });
    });
    if (flat.length) {
      const items = flat
        .slice(0, 50)
        .map(function (e) {
          return `<li><strong>${escapeHtml(e.section)}:</strong> ${escapeHtml(e.msg || '')}</li>`;
        })
        .join('');
      const more = flat.length > 50
        ? `<p class="import-errors__more">+${escapeHtml(flat.length - 50)} erros adicionais. Consulte o Error Log para a lista completa.</p>`
        : '';
      errList.innerHTML = `<ul>${items}</ul>${more}`;
      errWrap.classList.remove('hidden');
    }
  }

  window.enviarArquivosImportados = function () {
    if (CAN_RECONCILE === false) {
      showToast('error', 'Permissão negada', 'Você não tem permissão para conciliar.');
      return;
    }
    if (!window._extratoFileUrl || !window._vendasFileUrl || !window._recebimentosFileUrl) {
      showToast('error', 'Arquivos ausentes', 'Faça o upload dos três arquivos antes de enviar.');
      return;
    }

    const loadingIndicator = document.getElementById('infinitepay-loading-indicator');
    const btnConciliar = document.getElementById('btnConciliarInfinitepay');
    const resultsDiv = document.getElementById('ip-results');

    if (loadingIndicator) loadingIndicator.classList.remove('hidden');
    if (btnConciliar) btnConciliar.disabled = true;
    if (resultsDiv) resultsDiv.classList.add('hidden');

    frappe.call({
      method: 'gris.www.financeiro.contas.process_uploaded_files',
      args: {
        extrato_file_url: window._extratoFileUrl,
        vendas_file_url: window._vendasFileUrl,
        recebimentos_file_url: window._recebimentosFileUrl,
      },
      callback: function (r) {
        if (loadingIndicator) loadingIndicator.classList.add('hidden');
        if (btnConciliar) btnConciliar.disabled = false;

        if (r && r.exc) {
          console.error('Erro process_uploaded_files', r.exc);
          showToast('error', 'Erro ao processar', 'Verifique o console e os logs do sistema.');
          return;
        }
        const payload = (r && r.message) ? r.message : r;

        // Sem `stats` o processamento abortou antes de inserir qualquer coisa
        // (arquivo em formato não reconhecido, ausente ou ilegível).
        if (!payload || !payload.stats) {
          const detalhe = (payload && payload.summary_text) || 'Verifique os arquivos enviados e tente novamente.';
          showToast('error', 'Erro ao processar', detalhe);
          return;
        }

        renderResults(payload);
        window.scrollTo({ top: 0, behavior: 'smooth' });
        showToast('success', 'Conciliação concluída', 'Os arquivos Infinitepay foram processados com sucesso.');
      },
      error: function (err) {
        if (loadingIndicator) loadingIndicator.classList.add('hidden');
        if (btnConciliar) btnConciliar.disabled = false;
        console.error('Erro ao processar Infinitepay:', err);
        showToast('error', 'Erro na conciliação', 'Ocorreu um erro ao processar os arquivos.');
      },
    });
  };

  checkShowConciliarBtn();

  const btnConciliar = document.getElementById('btnConciliarInfinitepay');
  if (btnConciliar) {
    btnConciliar.addEventListener('click', window.enviarArquivosImportados);
  }
})();
