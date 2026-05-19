(function () {
  if (window.__importar_associados_inited) return;
  window.__importar_associados_inited = true;

  window._uploadedFileUrl = null;

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
        detail: {
          config: {
            category,
            title,
            description,
          },
        },
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

  function checkShowImportBtn() {
    const btn = document.getElementById('btnImportar');
    const hasFile = !!window._uploadedFileUrl;
    if (btn) {
      btn.classList.toggle('hidden', !hasFile);
      btn.disabled = !hasFile;
    }
  }

  function setupUploader() {
    const uploader = document.getElementById('associadosImportUpload');
    if (!uploader) return;

    uploader.addEventListener('gris:file-upload:success', function (event) {
      const file = event.detail?.files?.[0];
      if (!file) return;

      const fileInfo = document.getElementById('file-info');
      const fileName = document.getElementById('file-name');

      if (fileName) {
        fileName.textContent = file.file_name || file.name || file.file_url;
      }
      if (fileInfo) {
        fileInfo.classList.remove('hidden');
      }

      window._uploadedFileUrl = file.file_url;
      checkShowImportBtn();

      const resultsDiv = document.getElementById('import-results');
      if (resultsDiv) {
        resultsDiv.classList.add('hidden');
      }
    });
  }

  function renderResults(data) {
    const resultsDiv = document.getElementById('import-results');
    const resultsGrid = document.getElementById('results-grid');
    const errorsContainer = document.getElementById('errors-container');
    const errorsList = document.getElementById('errors-list');

    if (!resultsDiv || !resultsGrid) return;

    resultsGrid.innerHTML = '';
    if (errorsContainer) errorsContainer.classList.add('hidden');
    if (errorsList) errorsList.innerHTML = '';

    resultsDiv.classList.remove('hidden');

    const stats = [
      { label: 'Total de registros', value: data.total || 0, tone: 'primary' },
      { label: 'Criados', value: data.created || 0, tone: 'success' },
      { label: 'Atualizados', value: data.updated || 0, tone: 'info' },
      { label: 'Sem alteração', value: data.skipped || 0, tone: 'muted' },
      { label: 'Responsáveis criados', value: data.responsavel_created || 0, tone: 'success' },
      { label: 'Responsáveis atualizados', value: data.responsavel_updated || 0, tone: 'info' },
      { label: 'Vínculos criados', value: data.vinculo_created || 0, tone: 'success' },
      { label: 'Vínculos atualizados', value: data.vinculo_updated || 0, tone: 'info' },
      { label: 'Erros', value: data.errors || 0, tone: 'error' },
    ];

    stats.forEach(stat => {
      const card = document.createElement('article');
      card.className = 'card import-stat-card';
      card.dataset.tone = stat.tone;
      card.innerHTML = `
        <section>
          <p class="import-stat-card__value">${escapeHtml(stat.value)}</p>
          <p class="import-stat-card__label">${escapeHtml(stat.label)}</p>
        </section>
      `;
      resultsGrid.appendChild(card);
    });

    if (data.error_details && data.error_details.length > 0) {
      if (errorsContainer && errorsList) {
        const errorItems = data.error_details
          .slice(0, 50)
          .map(err => {
            const [mainLine, ...extraLines] = (err || '').split('\n');
            const extra = extraLines
              .map(l => l.replace(/^\s+/, ''))
              .filter(Boolean)
              .map(l => `<span class="import-error-detail">${escapeHtml(l)}</span>`)
              .join('');
            return `<li>${escapeHtml(mainLine)}${extra ? `<br>${extra}` : ''}</li>`;
          })
          .join('');

        const moreText = data.error_details.length > 50
          ? `<p class="import-errors__more">+${escapeHtml(data.error_details.length - 50)} erros adicionais. Consulte o Error Log para ver a lista completa.</p>`
          : '';

        errorsList.innerHTML = `<ul>${errorItems}</ul>${moreText}`;

        const alertSection = errorsContainer.querySelector('.alert section');
        if (alertSection) {
          alertSection.innerHTML = 'As linhas sem erros foram atualizadas com sucesso. Revise os itens abaixo e tente importar novamente após corrigir o relatório.';
        }

        errorsContainer.classList.remove('hidden');
      }
    }
  }

  function importAssociates() {
    if (!window._uploadedFileUrl) {
      frappe.msgprint('Selecione um arquivo antes de importar.');
      return;
    }

    const loadingIndicator = document.getElementById('loading-indicator');
    const btnImportar = document.getElementById('btnImportar');

    if (loadingIndicator) loadingIndicator.classList.remove('hidden');
    if (btnImportar) btnImportar.disabled = true;

    frappe.call({
      method: 'gris.api.associate.importer.parse_associates_report',
      args: {
        path_pdf: window._uploadedFileUrl
      },
      callback: function (r) {
        if (loadingIndicator) loadingIndicator.classList.add('hidden');
        if (btnImportar) btnImportar.disabled = false;

        if (r.message) {
          renderResults(r.message);
          window.scrollTo({ top: 0, behavior: 'smooth' });
          showToast(
            'success',
            'Importação concluída',
            'Os dados dos associados foram processados com sucesso.'
          );
        }
      },
      error: function (err) {
        if (loadingIndicator) loadingIndicator.classList.add('hidden');
        if (btnImportar) btnImportar.disabled = false;

        frappe.msgprint({
          title: 'Erro na Importação',
          message: 'Ocorreu um erro ao processar o arquivo. Verifique o console ou os logs do sistema.',
          indicator: 'red'
        });
        console.error('Erro ao importar associados:', err);
      }
    });
  }

  setupUploader();
  checkShowImportBtn();

  const btnImportar = document.getElementById('btnImportar');
  if (btnImportar) {
    btnImportar.addEventListener('click', importAssociates);
  }
})();
