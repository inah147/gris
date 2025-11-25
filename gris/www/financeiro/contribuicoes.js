let assocAtual = null;
function mostrarDetalhes(btn){
  const data = JSON.parse(btn.getAttribute('data-assoc'));
  assocAtual = data; // guardar para edição
  document.getElementById('detalheTitulo').textContent = data.nome;
  document.getElementById('detalheValor').textContent = frappe._.fmt_money ? frappe._.fmt_money(data.valor_contribuicao || 0) : (data.valor_contribuicao || 0);
  // Preenche dados de cobrança
  const emailSpan = document.getElementById('emailCobranca');
  const foneSpan = document.getElementById('foneCobranca');
  if(emailSpan) emailSpan.textContent = data.email_cobranca || '—';
  if(foneSpan) foneSpan.textContent = data.telefone_cobranca || '—';
  const tbody = document.getElementById('detalhePagamentos');
  tbody.innerHTML='';
  (data.pagamentos || []).forEach(p => {
    const tr = document.createElement('tr');
    tr.setAttribute('data-pag-id', p.name || '');
    let valorCell;
    if(p.status !== 'Pago') {
      if(window.canManageContrib) {
        valorCell = `<td><div class="d-flex align-items-center justify-content-between gap-2"><span>${p.valor ?? ''}</span><button class="btn btn-xs btn-success" onclick="marcarComoPago(this)" data-pag-id="${p.name}">Pago</button></div></td>`;
      } else {
        valorCell = `<td class="text-end">${p.valor ?? ''}</td>`;
      }
    } else { valorCell = `<td class="text-end">${p.valor ?? ''}</td>`; }
  tr.innerHTML = `<td>${p.mes_de_referencia || ''}</td><td><span class="g-badge g-badge--${mapBadge(p.status)} status-badge">${p.status}</span></td>${valorCell}`;
    tbody.appendChild(tr);
  });
  // Exibir botão de cadastro se status for Cadastrar
  const cadastroContainer = document.getElementById('cadastroContainer');
  const tabelaPagamentosContainer = document.getElementById('tabelaPagamentosContainer');
  if(data.status_geral === 'Cadastrar') {
    cadastroContainer.classList.remove('d-none');
    tabelaPagamentosContainer.classList.add('d-none');
  } else {
    cadastroContainer.classList.add('d-none');
    tabelaPagamentosContainer.classList.remove('d-none');
  }
  // Exibir botão de cancelamento se status for Cancelar
  const cancelarContainer = document.getElementById('cancelarContainer');
  if(cancelarContainer){
    if(data.status_geral === 'Cancelar') {
      cancelarContainer.classList.remove('d-none');
    } else {
      cancelarContainer.classList.add('d-none');
    }
  }
  
  // Mostra o modal e adiciona backdrop
  const modal = document.getElementById('detalheModal');
  modal.style.display = 'flex';
  modal.classList.add('show');
  
  // Cria backdrop
  let backdrop = document.getElementById('modalBackdrop');
  if (!backdrop) {
    backdrop = document.createElement('div');
    backdrop.id = 'modalBackdrop';
    backdrop.className = 'modal-backdrop fade show';
    backdrop.onclick = fecharDetalhes;
    document.body.appendChild(backdrop);
  }
  document.body.classList.add('modal-open');

  // Esconde elementos marcados manage-only se não tiver permissão
  if(!window.canManageContrib){
    document.querySelectorAll('[data-manage-only="1"]').forEach(el => el.classList.add('d-none'));
    const acoesValor = document.getElementById('acoesValor');
    if(acoesValor) acoesValor.innerHTML = '';
    const acoesCobranca = document.getElementById('acoesCobranca');
    if(acoesCobranca) acoesCobranca.innerHTML = '';
  }
}
function fecharDetalhes(){
  const modal = document.getElementById('detalheModal');
  modal.style.display = 'none';
  modal.classList.remove('show');
  
  // Remove backdrop
  const backdrop = document.getElementById('modalBackdrop');
  if (backdrop) {
    backdrop.remove();
  }
  document.body.classList.remove('modal-open');
}
function mapBadge(status){
  switch(status){
  case 'Cadastrar': return 'info';
  case 'Cancelar': return 'dark';
  case 'Aguardar': return 'secondary';
  case 'Atrasado': return 'danger';
  case 'Em Aberto': return 'warning';
  case 'Pago': return 'success';
  default: return 'secondary';
  tr.innerHTML = `<td>${p.mes_de_referencia || ''}</td><td><span class="g-badge g-badge--${mapBadge(p.status)} status-badge">${p.status}</span></td>${valorCell}`;
  }
}
function alterarValor(){
  if(!window.canManageContrib){ frappe.msgprint('Sem permissão para alterar valor.'); return; }
  if(!assocAtual) return;
  const container = document.getElementById('valorContainer');
  const acoes = document.getElementById('acoesValor');
  if(container.querySelector('input')) return; // já em edição
  const valorAtual = assocAtual.valor_contribuicao || 0;
  container.innerHTML = `
    <div class="form-group-modern" style="margin-bottom: 0;">
      <label class="form-label-modern">Novo Valor (R$)</label>
      <input type="number" min="0" step="0.01" id="inputNovoValor" class="form-input-modern form-input-modern--sm" style="max-width:180px;" value="${valorAtual}" />
    </div>
  `;
  acoes.innerHTML = `
    <button class="btn-modern btn-modern--success btn-modern--sm me-1" onclick="salvarNovoValor()">Salvar</button>
    <button class="btn-modern btn-modern--outline btn-modern--sm" onclick="cancelarEdicaoValor()">Cancelar</button>
  `;
}
function cancelarEdicaoValor(){
  if(!assocAtual) return;
  const container = document.getElementById('valorContainer');
  const acoes = document.getElementById('acoesValor');
  container.innerHTML = `<strong>Valor Atual:</strong> R$ <span id="detalheValor">${frappe._.fmt_money ? frappe._.fmt_money(assocAtual.valor_contribuicao || 0) : (assocAtual.valor_contribuicao || 0)}</span>`;
  acoes.innerHTML = `<button id="btnAlterarValor" class="btn-modern btn-modern--outline btn-modern--sm" onclick="alterarValor()">Alterar Valor</button>`;
}
function salvarNovoValor(){
  if(!assocAtual) return;
  const input = document.getElementById('inputNovoValor');
  if(!input) return;
  const novoValor = parseFloat(input.value);
  if(isNaN(novoValor) || novoValor < 0){
    frappe.msgprint('Informe um valor válido.');
    return;
  }
  frappe.call({
    method: 'gris.api.financeiro.monthly_payments.update_contribution_value',
    args: { associate_id: assocAtual.id, new_value: novoValor },
    freeze: true,
    callback: function(r){
      if(r.message && r.message.ok){
        assocAtual.valor_contribuicao = r.message.valor;
        cancelarEdicaoValor();
        document.getElementById('detalheValor').textContent = frappe._.fmt_money ? frappe._.fmt_money(assocAtual.valor_contribuicao) : assocAtual.valor_contribuicao;
        frappe.show_alert({message:'Valor atualizado', indicator:'green'});
      }
    },
    error: function(){ frappe.msgprint('Erro ao salvar valor.'); }
  });
}
// Paginação por status
// Inicia quando DOM carregado
if(document.readyState === 'loading'){
  document.addEventListener('DOMContentLoaded', () => { initStatusPagination(); });
} else { initStatusPagination(); }
function initStatusPagination(){
  const blocks = document.querySelectorAll('.status-bloco');
  blocks.forEach(block => { rebuildPaginationForBlock(block); });
}
function rebuildPaginationForBlock(block){
  if(!block) return;
  const pagContainer = block.querySelector('.status-pagination');
  if(pagContainer) pagContainer.innerHTML='';
  const list = block.querySelector('.assoc-list');
  if(!list) return;
  const visibleCards = Array.from(list.querySelectorAll('.assoc-card-col')).filter(c => !c.classList.contains('filter-hidden'));
  visibleCards.forEach((c, idx) => c.setAttribute('data-page', Math.floor(idx/12)+1));
  list.querySelectorAll('.assoc-card-col').forEach(c => c.classList.add('d-none'));
  if(visibleCards.length === 0) return;
  visibleCards.forEach(c => c.classList.remove('d-none'));
  const pages = Math.ceil(visibleCards.length / 12);
  if(pages > 1){
    renderPaginationControls(pagContainer, pages, 1, block.id);
    showStatusPage(block.id, 1);
  } else if(pagContainer){ pagContainer.innerHTML=''; }
}
function renderPaginationControls(container, totalPages, current, statusBlockId){
  const ul = document.createElement('ul');
  ul.className = 'pagination pagination-sm mb-0';
  const addItem = (label, page, disabled=false, active=false) => {
    const li = document.createElement('li');
    li.className = 'page-item' + (disabled? ' disabled':'') + (active? ' active':'');
    const a = document.createElement('a');
    a.className = 'page-link';
    a.textContent = label;
    if(!disabled && !active){
      a.addEventListener('click', () => {
        showStatusPage(statusBlockId, page);
        container.innerHTML='';
        renderPaginationControls(container, totalPages, page, statusBlockId);
      });
    }
    li.appendChild(a);
    ul.appendChild(li);
  };
  addItem('«', 1, current===1);
  addItem('‹', current-1, current===1);
  const windowSize = 5;
  let start = Math.max(1, current - Math.floor(windowSize/2));
  let end = start + windowSize -1;
  if(end > totalPages){
    end = totalPages;
    start = Math.max(1, end - windowSize +1);
  }
  for(let p = start; p<=end; p++) addItem(String(p), p, false, p===current);
  addItem('›', current+1, current===totalPages);
  addItem('»', totalPages, current===totalPages);
  container.appendChild(ul);
}
function showStatusPage(statusBlockId, page){
  const block = document.getElementById(statusBlockId);
  if(!block) return;
  const cards = block.querySelectorAll('.assoc-card-col');
  cards.forEach(c => {
    const p = parseInt(c.getAttribute('data-page'));
    if(p === page){ c.classList.remove('d-none'); } else { c.classList.add('d-none'); }
  });
}
function aplicarFiltroAssociado(){
  const termo = (document.getElementById('filtroAssociado')?.value || '').trim().toLowerCase();
  const blocks = document.querySelectorAll('.status-bloco');
  blocks.forEach(block => {
    const cards = block.querySelectorAll('.assoc-card-col');
    cards.forEach(card => {
      const nomeEl = card.querySelector('strong');
      const nome = (nomeEl?.getAttribute('title') || nomeEl?.textContent || '').toLowerCase();
      if(!termo || nome.includes(termo)){ card.classList.remove('filter-hidden'); } else { card.classList.add('filter-hidden'); }
    });
    rebuildPaginationForBlock(block);
  });
}
function marcarComoPago(btn){
  if(!window.canManageContrib){ frappe.msgprint('Sem permissão para marcar pagamento.'); return; }
  const pagId = btn.getAttribute('data-pag-id');
  if(!pagId) return;
  frappe.call({
    method: 'gris.api.financeiro.monthly_payments.mark_payment_as_paid',
    args: { payment_id: pagId },
    freeze: true,
    callback: function(r){
      if(r.message && r.message.ok){
        const tr = btn.closest('tr');
        if(tr){
          const badge = tr.querySelector('.status-badge');
          if(badge){
            badge.textContent = 'Pago';
            badge.className = 'g-badge g-badge--success status-badge';
          }
          btn.remove();
        }
        frappe.show_alert({message:'Pagamento marcado como Pago', indicator:'green'});
      }
    },
    error: function(){ frappe.msgprint('Erro ao marcar pagamento.'); }
  });
}
function cadastroRealizado(){
  if(!window.canManageContrib){ frappe.msgprint('Sem permissão.'); return; }
  if(!assocAtual) return;
  frappe.call({
    method: 'gris.api.financeiro.monthly_payments.activate_billing_status',
    args: { associate_id: assocAtual.id },
    freeze: true,
    callback: function(r){
      if(r.message && r.message.ok){
        assocAtual.status_cobranca = 'Ativo';
        document.getElementById('cadastroContainer').classList.add('d-none');
        frappe.show_alert({message:'Status de cobrança ativado', indicator:'green'});
        fecharDetalhes();
      }
    },
    error: function(){ frappe.msgprint('Erro ao atualizar status de cobrança.'); }
  });
}
function cadastroCancelado(){
  if(!window.canManageContrib){ frappe.msgprint('Sem permissão.'); return; }
  if(!assocAtual) return;
  frappe.call({
    method: 'gris.api.financeiro.monthly_payments.deactivate_billing_status',
    args: { associate_id: assocAtual.id },
    freeze: true,
    callback: function(r){
      if(r.message && r.message.ok){
        assocAtual.status_cobranca = 'Inativo';
        frappe.show_alert({message:'Status de cobrança inativado', indicator:'orange'});
        fecharDetalhes();
      }
    },
    error: function(){ frappe.msgprint('Erro ao inativar status de cobrança.'); }
  });
}
function editarCobranca(){
  if(!window.canManageContrib){ frappe.msgprint('Sem permissão para editar.'); return; }
  if(!assocAtual) return;
  const container = document.getElementById('cobrancaContainer');
  const acoes = document.getElementById('acoesCobranca');
  if(container.querySelector('input')) return; // já em edição
  const email = assocAtual.email_cobranca || '';
  const fone = assocAtual.telefone_cobranca || '';
  container.querySelector('#emailCobranca').innerHTML = `
    <div class="form-group-modern" style="margin-bottom: 0;">
      <label class="form-label-modern">E-mail</label>
      <input type="email" id="inputEmailCobranca" class="form-input-modern form-input-modern--sm" style="max-width:280px;" value="${email}" placeholder="email@exemplo.com" />
    </div>
  `;
  container.querySelector('#foneCobranca').innerHTML = `
    <div class="form-group-modern" style="margin-bottom: 0;">
      <label class="form-label-modern">Telefone</label>
      <input type="text" id="inputFoneCobranca" class="form-input-modern form-input-modern--sm" style="max-width:180px;" value="${fone}" placeholder="(xx) xxxxx-xxxx" />
    </div>
  `;
  acoes.innerHTML = `
    <button class="btn-modern btn-modern--success btn-modern--sm me-1" onclick="salvarDadosCobranca()">Salvar</button>
    <button class="btn-modern btn-modern--outline btn-modern--sm" onclick="cancelarEdicaoCobranca()">Cancelar</button>
  `;
}
function cancelarEdicaoCobranca(){
  if(!assocAtual) return;
  const emailSpan = document.getElementById('emailCobranca');
  const foneSpan = document.getElementById('foneCobranca');
  emailSpan.textContent = assocAtual.email_cobranca || '—';
  foneSpan.textContent = assocAtual.telefone_cobranca || '—';
  document.getElementById('acoesCobranca').innerHTML = `<button id="btnEditarCobranca" class="btn-modern btn-modern--outline btn-modern--sm" onclick="editarCobranca()">Editar Cobrança</button>`;
}
function salvarDadosCobranca(){
  if(!window.canManageContrib){ frappe.msgprint('Sem permissão para salvar.'); return; }
  if(!assocAtual) return;
  const emailInput = document.getElementById('inputEmailCobranca');
  const foneInput = document.getElementById('inputFoneCobranca');
  const email = emailInput ? emailInput.value.trim() : '';
  const phone = foneInput ? foneInput.value.trim() : '';
  frappe.call({
    method: 'gris.api.financeiro.monthly_payments.update_billing_contacts',
    args: { associate_id: assocAtual.id, email: email, phone: phone },
    freeze: true,
    callback: function(r){
      if(r.message && r.message.ok){
        assocAtual.email_cobranca = r.message.email;
        assocAtual.telefone_cobranca = r.message.phone;
        cancelarEdicaoCobranca();
        frappe.show_alert({message:'Dados de cobrança atualizados', indicator:'green'});
      }
    },
    error: function(){ frappe.msgprint('Erro ao salvar dados de cobrança.'); }
  });
}
