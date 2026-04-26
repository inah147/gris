// JS específico da página Lista de Associados (auto-carregado pelo Frappe quando está ao lado do .html)

frappe.ready(() => {
  const tableEl = document.getElementById('associadosTable');
  const listEl = tableEl?.querySelector('tbody');
  const form = document.getElementById('assoc-filters');
  const resetBtn = document.getElementById('btn-reset');
  const createUsersBtn = document.getElementById('btn-create-users');
  const confirmDlg = document.getElementById('modalCreateUsersConfirm');
  const resultDlg = document.getElementById('modalCreateUsersResult');
  const confirmCreateUsersBtn = document.getElementById('btn-confirm-create-users');
  const resultBody = document.getElementById('create-users-result-body');

  if (!listEl || !form) return;

  const COLSPAN = 8;

  function renderLoading() {
    listEl.innerHTML = `
      <tr>
        <td colspan="${COLSPAN}">
          <div class="assoc-loading">
            <span class="spinner" role="status" aria-label="Carregando"></span>
            <span>Carregando associados…</span>
          </div>
        </td>
      </tr>`;
  }

  function renderEmpty(title, description) {
    listEl.innerHTML = `
      <tr>
        <td colspan="${COLSPAN}">
          <section class="empty">
            <h2>${frappe.utils.escape_html(title)}</h2>
            <p>${frappe.utils.escape_html(description)}</p>
          </section>
        </td>
      </tr>`;
  }

  function statusDot(status) {
    if (status === 'Válido') {
      return '<span class="assoc-status-dot assoc-status-dot--ok" aria-label="Registro válido" title="Registro válido"></span>';
    }
    if (status === 'Vencido') {
      return '<span class="assoc-status-dot assoc-status-dot--danger" aria-label="Registro vencido" title="Registro vencido"></span>';
    }
    return '<span class="assoc-status-dot assoc-status-dot--warn" aria-label="Atenção necessária" title="Atenção necessária"></span>';
  }

  function badge(text, variant) {
    if (!text) return '<span class="text-muted-foreground">—</span>';
    const cls = variant === 'outline' ? 'badge-outline' : `badge-${variant}`;
    return `<span class="${cls}">${frappe.utils.escape_html(text)}</span>`;
  }

  function render(rows) {
    if (!rows.length) {
      renderEmpty('Nenhum associado encontrado', 'Tente ajustar os filtros acima.');
      return;
    }
    listEl.innerHTML = rows.map((row) => {
      const nome = frappe.utils.escape_html(row.nome_completo || row.name || '—');
      const registro = frappe.utils.escape_html(row.registro || '—');
      const status = row.status || 'Desconhecido';
      const ramo = row.ramo && row.ramo !== 'Não se aplica' ? row.ramo : '';
      const link = `/associados/detalhe?name=${encodeURIComponent(row.name)}`;

      return `
        <tr class="assoc-table-row" data-href="${link}">
          <td class="assoc-status-cell">${statusDot(status)}</td>
          <td><span class="assoc-name">${nome}</span></td>
          <td><span class="text-muted-foreground">${registro}</span></td>
          <td>${badge(row.categoria, 'primary')}</td>
          <td>${badge(ramo, 'secondary')}</td>
          <td>${badge(row.secao, 'outline')}</td>
          <td>${badge(row.funcao, 'outline')}</td>
          <td>${badge(row.area, 'outline')}</td>
        </tr>`;
    }).join('');
  }

  function getFormFilters() {
    const fd = new FormData(form);
    const get = (k) => (fd.get(k) || '').trim();
    return {
      nome: get('nome'),
      categoria: get('categoria'),
      ramo: get('ramo'),
      secao: get('secao'),
      funcao: get('funcao'),
      area: get('area'),
      status: get('status'),
      status_no_grupo: get('status_no_grupo'),
    };
  }

  async function fetchList() {
    renderLoading();
    const f = getFormFilters();
    const filters = [];
    if (f.status_no_grupo) filters.push(['Associado', 'status_no_grupo', '=', f.status_no_grupo]);
    if (f.nome) filters.push(['Associado', 'nome_completo', 'like', `%${f.nome}%`]);
    if (f.categoria) filters.push(['Associado', 'categoria', '=', f.categoria]);
    if (f.funcao) filters.push(['Associado', 'funcao', '=', f.funcao]);
    if (f.area) filters.push(['Associado', 'area', '=', f.area]);
    if (f.secao) filters.push(['Associado', 'secao', '=', f.secao]);
    if (f.ramo) filters.push(['Associado', 'ramo', '=', f.ramo]);
    if (f.status) filters.push(['Associado', 'status', '=', f.status]);

    try {
      const r = await frappe.call({
        method: 'frappe.client.get_list',
        args: {
          doctype: 'Associado',
          fields: ['name', 'nome_completo', 'registro', 'status', 'ramo', 'categoria', 'funcao', 'area', 'secao'],
          filters,
          limit_page_length: 500,
          order_by: 'nome_completo asc',
        },
      });
      render(r.message || []);
    } catch (e) {
      console.warn('Erro ao carregar lista de associados', e);
      renderEmpty('Erro ao carregar a lista', 'Tente recarregar a página.');
    }
  }

  function resetSelectsToDefault() {
    form.querySelectorAll('.select').forEach((el) => {
      el.value = el.id === 'f-status-grupo' ? 'Ativo' : '';
    });
  }

  // Listener delegado para navegação ao detalhe
  listEl.addEventListener('click', (e) => {
    const tr = e.target.closest('tr[data-href]');
    if (tr) window.location.href = tr.dataset.href;
  });

  form.addEventListener('submit', (e) => {
    e.preventDefault();
    fetchList();
  });

  form.addEventListener('reset', () => {
    setTimeout(() => {
      resetSelectsToDefault();
      fetchList();
    }, 0);
  });

  if (createUsersBtn && confirmDlg && resultDlg) {
    createUsersBtn.addEventListener('click', () => confirmDlg.showModal());

    confirmDlg.querySelectorAll('[data-dialog-close]').forEach((btn) => {
      btn.addEventListener('click', () => confirmDlg.close());
    });
    resultDlg.querySelectorAll('[data-dialog-close]').forEach((btn) => {
      btn.addEventListener('click', () => resultDlg.close());
    });

    if (confirmCreateUsersBtn) {
      confirmCreateUsersBtn.addEventListener('click', async () => {
        const originalConfirmText = confirmCreateUsersBtn.textContent;
        const originalButtonText = createUsersBtn.textContent;

        confirmCreateUsersBtn.disabled = true;
        confirmCreateUsersBtn.textContent = 'Processando…';
        createUsersBtn.disabled = true;
        createUsersBtn.textContent = 'Processando…';

        try {
          const response = await frappe.call({
            method: 'gris.api.users.user_manager.create_missing_associate_users',
          });
          confirmDlg.close();
          renderResult(response.message || {});
          fetchList();
        } catch (error) {
          console.warn('Erro ao criar usuários pendentes', error);
          confirmDlg.close();
          renderResult({}, true);
        } finally {
          confirmCreateUsersBtn.disabled = false;
          confirmCreateUsersBtn.textContent = originalConfirmText;
          createUsersBtn.disabled = false;
          createUsersBtn.textContent = originalButtonText;
        }
      });
    }
  }

  function renderResult(result, failed = false) {
    if (!resultBody || !resultDlg) return;
    const titleEl = resultDlg.querySelector('h2');
    if (titleEl) titleEl.textContent = failed ? 'Erro ao criar usuários' : 'Criação de usuários concluída';

    if (failed) {
      resultBody.innerHTML = '<p class="text-muted-foreground">Não foi possível concluir a criação dos usuários pendentes.</p>';
      resultDlg.showModal();
      return;
    }

    const item = (label, value) => `
      <div class="result-row">
        <span class="result-row__label">${label}</span>
        <span class="result-row__value">${value || 0}</span>
      </div>`;

    resultBody.innerHTML = `
      <div class="result-list">
        ${item('Associados analisados', result.total_associates)}
        ${item('Criados', result.created)}
        ${item('Ignorados (usuário já existe)', result.skipped_existing_user)}
        ${item('Ignorados (status inválido)', result.skipped_invalid_status)}
        ${item('Ignorados (domínio inválido)', result.skipped_invalid_domain)}
        ${item('Ignorados (dados incompletos)', result.skipped_missing_data)}
        ${item('Erros', result.errors)}
      </div>`;
    resultDlg.showModal();
  }

  fetchList();
});
