// JS específico da página Lista de Associados (auto-carregado pelo Frappe quando está ao lado do .html)

frappe.ready(() => {
  const listEl = document.getElementById('assoc-list');
  const form = document.getElementById('assoc-filters');
  const resetBtn = document.getElementById('btn-reset');
  const createUsersBtn = document.getElementById('btn-create-users');
  const confirmModal = document.getElementById('modalCreateUsersConfirm');
  const confirmBackdrop = document.getElementById('modalCreateUsersConfirmBackdrop');
  const resultModal = document.getElementById('modalCreateUsersResult');
  const resultBackdrop = document.getElementById('modalCreateUsersResultBackdrop');
  const confirmCreateUsersBtn = document.getElementById('btn-confirm-create-users');
  const resultTitle = document.getElementById('create-users-result-title');
  const resultBody = document.getElementById('create-users-result-body');
  const selCategoria = document.getElementById('f-categoria');
  const selRamo = document.getElementById('f-ramo');
  const selStatus = document.getElementById('f-status');
  const selStatusGrupo = document.getElementById('f-status-grupo');
  const selFuncao = document.getElementById('f-funcao');
  const selArea = document.getElementById('f-area');
  const selSecao = document.getElementById('f-secao');

  function getStatusIndicator(status){
    // status: Válido (verde), Vencido (vermelho), próximo de vencer (amarelo)
    if(status === 'Válido') {
      return `<span class="status-indicator status-indicator--active" title="Registro válido">
        <span class="status-indicator__dot"></span>
      </span>`;
    }
    if(status === 'Vencido') {
      return `<span class="status-indicator status-indicator--danger" title="Registro vencido">
        <span class="status-indicator__dot"></span>
      </span>`;
    }
    // Para "Vence em breve" ou outros status de alerta
    return `<span class="status-indicator status-indicator--warning" title="Atenção necessária">
      <span class="status-indicator__dot"></span>
    </span>`;
  }

  function render(rows){
    if(!rows.length){
      listEl.innerHTML = `
        <tr>
          <td colspan="8">
            <div class="empty-state" style="border: none; margin: 2rem 0;">
              <svg class="empty-state__icon" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.5" stroke-linecap="round" stroke-linejoin="round" style="width: 64px; height: 64px; margin-bottom: 1rem; color: var(--text-muted);">
                <circle cx="12" cy="12" r="10"></circle>
                <path d="M16 16s-1.5-2-4-2-4 2-4 2M9 9h.01M15 9h.01"></path>
              </svg>
              <h3 class="empty-state__title">Nenhum associado encontrado</h3>
              <p class="empty-state__description">Tente ajustar os filtros acima</p>
            </div>
          </td>
        </tr>`;
      return;
    }
    listEl.innerHTML = rows.map(row => {
      const nome = frappe.utils.escape_html(row.nome_completo || row.name || '—');
      const registro = frappe.utils.escape_html(row.registro || '—');
      const status = row.status || 'Desconhecido';
      const ramo = row.ramo ? frappe.utils.escape_html(row.ramo) : '';
      const categoria = row.categoria ? frappe.utils.escape_html(row.categoria) : '';
      const funcao = row.funcao ? frappe.utils.escape_html(row.funcao) : '';
      const area = row.area ? frappe.utils.escape_html(row.area) : '';
      const secao = row.secao ? frappe.utils.escape_html(row.secao) : '';
      const link = `/associados/detalhe?name=${encodeURIComponent(row.name)}`;
      
      return `
        <tr class="clickable" onclick="window.location.href='${link}'" style="cursor: pointer;">
          <td style="text-align: center;">
            ${getStatusIndicator(status)}
          </td>
          <td>
            <div style="font-weight: 500; color: var(--text-primary);">
              ${nome}
            </div>
          </td>
          <td>
            <span style="font-size: 0.875rem; color: var(--text-secondary);">${registro}</span>
          </td>
          <td>
            ${categoria ? `<span class="g-badge g-badge--accent g-badge--small g-badge--outline">${categoria}</span>` : '<span style="color: var(--text-muted); font-size: 0.75rem;">—</span>'}
          </td>
          <td>
            ${(ramo && ramo !== 'Não se aplica') ? `<span class="g-badge g-badge--dark g-badge--small">${ramo}</span>` : '<span style="color: var(--text-muted); font-size: 0.75rem;">—</span>'}
          </td>
          <td>
            ${secao ? `<span class="g-badge g-badge--secondary g-badge--small">${secao}</span>` : '<span style="color: var(--text-muted); font-size: 0.75rem;">—</span>'}
          </td>
          <td>
            ${funcao ? `<span class="g-badge g-badge--primary g-badge--small g-badge--outline">${funcao}</span>` : '<span style="color: var(--text-muted); font-size: 0.75rem;">—</span>'}
          </td>
          <td>
            ${area ? `<span class="g-badge g-badge--info g-badge--small g-badge--outline">${area}</span>` : '<span style="color: var(--text-muted); font-size: 0.75rem;">—</span>'}
          </td>
        </tr>`;
    }).join('');
  }

  async function fetchList(){
    listEl.innerHTML = `
      <tr>
        <td colspan="8">
          <div class="loading-container">
            <div class="loading-spinner"></div>
            <span class="loading-text">Carregando associados...</span>
          </div>
        </td>
      </tr>`;
    const nome = document.getElementById('f-nome').value.trim();
    const categoria = document.getElementById('f-categoria').value;
    const funcao = document.getElementById('f-funcao').value;
    const area = document.getElementById('f-area').value;
    const secao = document.getElementById('f-secao').value;
    const ramo = document.getElementById('f-ramo').value;
    const status = document.getElementById('f-status').value;
    const statusGrupo = document.getElementById('f-status-grupo').value;

    const filters = [];
    // Filtro de status no grupo (padrão: Ativo)
    if(statusGrupo) filters.push(["Associado","status_no_grupo","=",statusGrupo]);
    if(nome) filters.push(["Associado","nome_completo","like","%"+nome+"%"]);
    if(categoria) filters.push(["Associado","categoria","=",categoria]);
    if(funcao) filters.push(["Associado","funcao","=",funcao]);
    if(area) filters.push(["Associado","area","=",area]);
    if(secao) filters.push(["Associado","secao","=",secao]);
    if(ramo) filters.push(["Associado","ramo","=",ramo]);
    if(status) filters.push(["Associado","status","=",status]);

    try {
      const r = await frappe.call({
        method: 'frappe.client.get_list',
        args: {
          doctype: 'Associado',
          fields: ['name','nome_completo','registro','status','ramo','categoria','funcao','area','secao'],
          filters,
          limit_page_length: 500,
          order_by: 'nome_completo asc'
        }
      });
      render(r.message || []);
    } catch (e) {
      console.warn('Erro ao carregar lista de associados', e);
      listEl.innerHTML = `
        <tr>
          <td colspan="8">
            <div class="empty-state" style="border: none; margin: 2rem 0;">
              <h3 class="empty-state__title" style="color: var(--color-danger);">Erro ao carregar a lista</h3>
              <p class="empty-state__description">Tente recarregar a página</p>
            </div>
          </td>
        </tr>`;
    }
  }

  function fillSelect(select, values, placeholder){
    const current = select.value;
    const label = placeholder || 'Todas';
    const options = [`<option value="">${label}</option>`]
      .concat(Array.from(values).filter(Boolean).sort()
      .map(v => `<option value="${frappe.utils.escape_html(v)}">${frappe.utils.escape_html(v)}</option>`));
    select.innerHTML = options.join('');
    if ([...select.options].some(o => o.value === current)) select.value = current;
  }

  async function populateDynamicFilters(){
    try {
      const r = await frappe.call({
        method: 'frappe.client.get_list',
        args: {
          doctype: 'Associado',
          fields: ['categoria','ramo','status','funcao','area','secao'],
          filters: [["Associado","status_no_grupo","=","Ativo"]],
          limit_page_length: 5000
        }
      });
      const rows = r.message || [];
      const categorias = new Set();
      const ramos = new Set();
      const statusSet = new Set();
      const funcoes = new Set();
      const areas = new Set();
      const secoes = new Set();
      rows.forEach(x => {
        if(x.categoria) categorias.add(x.categoria);
        if(x.ramo) ramos.add(x.ramo);
        if(x.status) statusSet.add(x.status);
        if(x.funcao) funcoes.add(x.funcao);
        if(x.area) areas.add(x.area);
        if(x.secao) secoes.add(x.secao);
      });
      fillSelect(selCategoria, categorias, 'Todas');
      fillSelect(selRamo, ramos, 'Todos');
      fillSelect(selStatus, statusSet, 'Todos');
      fillSelect(selFuncao, funcoes, 'Todas');
      fillSelect(selArea, areas, 'Todas');
      fillSelect(selSecao, secoes, 'Todas');
    } catch(e){ console.warn('Erro ao carregar opções dinâmicas', e); }
  }

  function openModal(modal, backdrop) {
    if (!modal || !backdrop) return;
    backdrop.style.display = 'block';
    modal.style.display = 'flex';
    setTimeout(() => {
      backdrop.classList.add('show');
      modal.classList.add('show');
    }, 10);
    document.body.classList.add('modal-open');
  }

  function closeModal(modal, backdrop) {
    if (!modal || !backdrop) return;
    modal.classList.remove('show');
    backdrop.classList.remove('show');
    setTimeout(() => {
      modal.style.display = 'none';
      backdrop.style.display = 'none';
      if (!document.querySelector('.modal-modern.show')) {
        document.body.classList.remove('modal-open');
      }
    }, 250);
  }

  function renderResultModal(result, failed = false) {
    if (!resultModal || !resultBackdrop || !resultBody || !resultTitle) return;

    resultTitle.textContent = failed ? 'Erro ao criar usuários' : 'Criação de usuários concluída';

    if (failed) {
      resultBody.innerHTML = '<p style="margin: 0; color: var(--text-secondary);">Não foi possível concluir a criação dos usuários pendentes.</p>';
      openModal(resultModal, resultBackdrop);
      return;
    }

    resultBody.innerHTML = [
      `<div style="display: grid; gap: 0.5rem; color: var(--text-secondary);">`,
      `<div>Associados analisados: <strong>${result.total_associates || 0}</strong></div>`,
      `<div>Criados: <strong>${result.created || 0}</strong></div>`,
      `<div>Ignorados (usuário já existe): <strong>${result.skipped_existing_user || 0}</strong></div>`,
      `<div>Ignorados (status inválido): <strong>${result.skipped_invalid_status || 0}</strong></div>`,
      `<div>Ignorados (domínio inválido): <strong>${result.skipped_invalid_domain || 0}</strong></div>`,
      `<div>Ignorados (dados incompletos): <strong>${result.skipped_missing_data || 0}</strong></div>`,
      `<div>Erros: <strong>${result.errors || 0}</strong></div>`,
      `</div>`
    ].join('');

    openModal(resultModal, resultBackdrop);
  }

  form.addEventListener('submit', (e)=>{ e.preventDefault(); fetchList(); });
  resetBtn.addEventListener('click', ()=>{ form.reset(); fetchList(); });

  if (createUsersBtn) {
    createUsersBtn.onclick = () => openModal(confirmModal, confirmBackdrop);

    confirmModal?.querySelectorAll('[data-dismiss-create-users-confirm]').forEach(btn => {
      btn.addEventListener('click', () => closeModal(confirmModal, confirmBackdrop));
    });

    confirmBackdrop?.addEventListener('click', () => closeModal(confirmModal, confirmBackdrop));

    resultModal?.querySelectorAll('[data-dismiss-create-users-result]').forEach(btn => {
      btn.addEventListener('click', () => closeModal(resultModal, resultBackdrop));
    });

    resultBackdrop?.addEventListener('click', () => closeModal(resultModal, resultBackdrop));

    if (confirmCreateUsersBtn) {
      confirmCreateUsersBtn.onclick = async () => {
        const originalConfirmText = confirmCreateUsersBtn.textContent;
        const originalButtonText = createUsersBtn.textContent;

        confirmCreateUsersBtn.disabled = true;
        confirmCreateUsersBtn.textContent = 'Processando...';
        createUsersBtn.disabled = true;
        createUsersBtn.textContent = 'Processando...';

        try {
          const response = await frappe.call({
            method: 'gris.api.users.user_manager.create_missing_associate_users'
          });

          closeModal(confirmModal, confirmBackdrop);
          renderResultModal(response.message || {});
          fetchList();
        } catch (error) {
          console.warn('Erro ao criar usuários pendentes', error);
          closeModal(confirmModal, confirmBackdrop);
          renderResultModal({}, true);
        } finally {
          confirmCreateUsersBtn.disabled = false;
          confirmCreateUsersBtn.textContent = originalConfirmText;
          createUsersBtn.disabled = false;
          createUsersBtn.textContent = originalButtonText;
        }
      };
    }
  }

  // Popular selects e carregar a lista
  populateDynamicFilters().then(fetchList);
});
