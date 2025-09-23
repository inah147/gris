// JS específico da página Lista de Associados (auto-carregado pelo Frappe quando está ao lado do .html)

frappe.ready(() => {
  const listEl = document.getElementById('assoc-list');
  const form = document.getElementById('assoc-filters');
  const resetBtn = document.getElementById('btn-reset');
  const selCategoria = document.getElementById('f-categoria');
  const selRamo = document.getElementById('f-ramo');
  const selStatus = document.getElementById('f-status');
  const selFuncao = document.getElementById('f-funcao');
  const selArea = document.getElementById('f-area');
  const selSecao = document.getElementById('f-secao');

  function statusBadgeClass(s){
    if(s === 'Válido') return 'g-badge g-badge--success';
    if(s === 'Vencido') return 'g-badge g-badge--warning';
    return 'g-badge g-badge--secondary';
  }

  function render(rows){
    if(!rows.length){
      listEl.innerHTML = '<div class="list-group-item text-muted">Nenhum associado encontrado.</div>';
      return;
    }
  listEl.innerHTML = rows.map(row => {
      const nome = frappe.utils.escape_html(row.nome_completo || row.name || '—');
      const registro = frappe.utils.escape_html(row.registro || '—');
      const status = frappe.utils.escape_html(row.status || 'Desconhecido');
      const ramo = row.ramo ? frappe.utils.escape_html(row.ramo) : '';
      const categoria = row.categoria ? frappe.utils.escape_html(row.categoria) : '';
  // Badges de ramo e categoria (agora ambos, se existirem)
  const ramoBadge = (ramo && ramo !== 'Não se aplica') ? `<span class="g-badge g-badge--dark">${ramo}</span>` : '';
  const categoriaBadge = categoria ? `<span class="g-badge g-badge--accent g-badge--outline">${categoria}</span>` : '';
      const link = `/associados/detalhe?name=${encodeURIComponent(row.name)}`;
      return `
        <a href="${link}" class="list-group-item list-group-item-action" data-name="${row.name}">
          <div class="d-flex flex-column flex-md-row justify-content-between align-items-start gap-2">
            <div class="flex-grow-1">
              <div class="fw-semibold">${nome}</div>
              <div class="text-muted small d-flex align-items-center flex-wrap gap-2">Registro: ${registro}<span class="${statusBadgeClass(status)}">${status}</span></div>
            </div>
            <div class="d-flex gap-3 align-items-center mt-2 mt-md-0">
              ${categoriaBadge}${ramoBadge}
            </div>
          </div>
        </a>`;
    }).join('');
  }

  async function fetchList(){
    listEl.innerHTML = '<div class="list-group-item text-muted">Carregando...</div>';
    const nome = document.getElementById('f-nome').value.trim();
  const categoria = document.getElementById('f-categoria').value;
    const funcao = document.getElementById('f-funcao').value;
    const area = document.getElementById('f-area').value;
    const secao = document.getElementById('f-secao').value;
    const ramo = document.getElementById('f-ramo').value;
    const status = document.getElementById('f-status').value;

    const filters = [];
  // Mostrar apenas associados com status_no_grupo = 'Ativo'
  filters.push(["Associado","status_no_grupo","=","Ativo"]);
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
      listEl.innerHTML = '<div class="list-group-item text-danger">Erro ao carregar a lista.</div>';
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

  form.addEventListener('submit', (e)=>{ e.preventDefault(); fetchList(); });
  resetBtn.addEventListener('click', ()=>{ form.reset(); fetchList(); });
  // Popular selects e carregar a lista
  populateDynamicFilters().then(fetchList);
});
