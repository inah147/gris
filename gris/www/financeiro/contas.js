// Função para enviar os arquivos ao backend
// Mostra botão de conciliação após upload dos três arquivos
function checkShowConciliarBtn(){
  const btn = document.getElementById('btnConciliarInfinitepay');
  if(window._extratoFileUrl && window._vendasFileUrl && window._recebimentosFileUrl){
    btn.classList.remove('d-none');
    btn.disabled = false;
  }else{
    btn.classList.add('d-none');
    btn.disabled = true;
  }
}

window._extratoFileUrl = null;
window._vendasFileUrl = null;
window._recebimentosFileUrl = null;

window.enviarArquivosImportados = function(){
  if(!window._extratoFileUrl || !window._vendasFileUrl || !window._recebimentosFileUrl){
    frappe.msgprint('Faça o upload dos três arquivos antes de enviar.');
    return;
  }
  frappe.call({
    method: 'gris.www.financeiro.contas.process_uploaded_files',
    args: {
      extrato_file_url: window._extratoFileUrl,
      vendas_file_url: window._vendasFileUrl,
      recebimentos_file_url: window._recebimentosFileUrl
    },
    callback: function(r){
      if(r && r.exc){
        console.error('Erro process_uploaded_files', r.exc);
        frappe.msgprint('Erro ao processar: ver console.');
      }else{
        console.debug('Resposta process_uploaded_files', r);
        frappe.msgprint(r.message || 'Arquivos enviados e processados!');
      }
    }
  });
};

// Chama checkShowConciliarBtn após cada upload
function setupUploader(btnId, nomeId, checkId, allowedExt){
  document.addEventListener('click', function(e){
    if(e.target && e.target.id === btnId){
      console.debug('[Infinitepay Upload] Click on', btnId);
      // Adiciona atributo 'accept' ao botão de upload
      const btn = document.getElementById(btnId);
      if(btn){
        btn.setAttribute('accept', allowedExt.map(ext => '.' + ext).join(','));
      }
      if(typeof frappe === 'undefined' || !frappe.ui || !frappe.ui.FileUploader){
        frappe.msgprint('Uploader indisponível.');
        return;
      }
      new frappe.ui.FileUploader({
        allow_multiple: false,
        restrictions: {
          allowed_file_extensions: allowedExt,
          max_number_of_files: 1
        },
        is_private: 0,
        options: ['Local'], // Apenas arquivos do computador
        on_success(file){
          console.debug('[Infinitepay Upload] Sucesso', btnId, file);
          const nomeSpan = document.getElementById(nomeId);
          const checkSpan = document.getElementById(checkId);
          if(nomeSpan){ nomeSpan.textContent = file.file_name || file.name; nomeSpan.classList.remove('d-none'); }
          if(checkSpan){ checkSpan.classList.remove('d-none'); }
          // Salva file_url globalmente para envio ao backend
          if(btnId === 'uploadExtratoBtn') window._extratoFileUrl = file.file_url;
          if(btnId === 'uploadVendasBtn') window._vendasFileUrl = file.file_url;
          if(btnId === 'uploadRecebimentosBtn') window._recebimentosFileUrl = file.file_url;
          console.debug('[Infinitepay Upload] URLs atuais', {
            extrato: window._extratoFileUrl,
            vendas: window._vendasFileUrl,
            recebimentos: window._recebimentosFileUrl
          });
          checkShowConciliarBtn();
        }
      });
    }
  });
}
// Adicione no HTML do modal de importação Infinitepay:
// <button id="btnConciliarInfinitepay" class="btn btn-success d-none mt-3" onclick="enviarArquivosImportados()">Realizar Conciliação</button>
  // Evita inicializar uploaders na página dedicada de importação, onde há script próprio
  const isImportInfinitepayPage = typeof window !== 'undefined' && window.location && window.location.pathname && window.location.pathname.startsWith('/financeiro/import_intinitepay');
  if(!isImportInfinitepayPage){
    // Extrato: só .ofx
    setupUploader('uploadExtratoBtn','nomeExtratoInfinitepay','checkExtratoInfinitepay',['ofx']);
    // Vendas: só .csv
    setupUploader('uploadVendasBtn','nomeVendasInfinitepay','checkVendasInfinitepay',['csv']);
    // Recebimentos: só .csv
    setupUploader('uploadRecebimentosBtn','nomeRecebimentosInfinitepay','checkRecebimentosInfinitepay',['csv']);
  }
// JS extraído de contas.html
// JS extraído de contas.html
(function(){
  function qs(id){return document.getElementById(id);}    
  function openSimpleModal(id){ const el=qs(id); if(!el) return; el.classList.remove('d-none'); el.classList.add('show'); el.style.display='block'; document.body.classList.add('modal-open'); const backdrop=document.createElement('div'); backdrop.className='modal-backdrop fade show'; backdrop.dataset.modalBackdrop='1'; backdrop.dataset.forModal=id; document.body.appendChild(backdrop); }
  window.fecharNovaInstituicaoModal = function(){ const m=qs('novaInstituicaoModal'); if(!m) return; m.classList.add('d-none'); m.classList.remove('show'); m.style.display='none'; document.body.classList.remove('modal-open'); document.querySelectorAll('[data-modal-backdrop="1"]').forEach(b=>b.remove()); };
  window.fecharNovaCarteiraModal = function(){ const m=qs('novaCarteiraModal'); if(!m) return; m.classList.add('d-none'); m.classList.remove('show'); m.style.display='none'; document.body.classList.remove('modal-open'); document.querySelectorAll('[data-modal-backdrop="1"]').forEach(b=>b.remove()); };
  function openModal(el){ if(!el) return; el.classList.remove('d-none'); el.classList.add('show'); el.style.display='block'; document.body.classList.add('modal-open'); const backdrop=document.createElement('div'); backdrop.className='modal-backdrop fade show'; backdrop.dataset.modalBackdrop='1'; backdrop.dataset.forModal=el.id; document.body.appendChild(backdrop); }
  function closeModal(el){ el.classList.remove('show'); el.style.display='none'; el.classList.add('d-none'); document.body.classList.remove('modal-open'); document.querySelectorAll('[data-modal-backdrop="1"]').forEach(b=>b.remove()); }
  window.fecharCarteiraModal = function(){ const m=qs('carteiraDetalheModal'); if(m) closeModal(m); };
  function fillAndOpen(btn){
    const nome = btn.dataset.nome || '';
    const inst = btn.dataset.instituicao || '';
    const instClasses = btn.dataset.instituicaoClasses || 'g-badge g-badge--neutral g-badge--small';
    const descricao = btn.dataset.descricao || '';
    const responsavel = btn.dataset.responsavel || '—';
    const centro = btn.dataset.centroCusto || '—';
    const pix = btn.dataset.chavePix || '—';
    const saldo = btn.dataset.saldo || '—';
    const dataAtualizacao = btn.dataset.dataAtualizacao || '—';
    qs('carteiraModalTitulo').textContent = nome;
    const instSpan = qs('carteiraModalInstituicao');
    instSpan.className = instClasses; instSpan.textContent = inst || '—';
    qs('carteiraModalDescricao').textContent = descricao || 'Sem descrição.';
    qs('carteiraModalResponsavel').textContent = responsavel || '—';
    qs('carteiraModalCentro').textContent = centro || '—';
    qs('carteiraModalPix').textContent = pix || '—';
    qs('carteiraModalSaldo').textContent = saldo || '—';
    qs('carteiraModalData').textContent = dataAtualizacao || '—';
    openModal(qs('carteiraDetalheModal'));
  }
  const modal = document.getElementById('carteiraDetalheModal');
  function setEditMode(on){
    const campos = qs('carteiraEdicaoCampos');
    if(campos){ campos.classList.toggle('d-none', !on); }
    qs('btnEditarCarteira').classList.toggle('d-none', on);
    qs('btnSalvarCarteira').classList.toggle('d-none', !on);
    qs('btnCancelarEdicaoCarteira').classList.toggle('d-none', !on);
  }
  let _cacheCentro = null, _cacheUsers = null;
  function extractResults(r){
    if(!r) return [];
    if(Array.isArray(r.results)) return r.results;
    if(r.message){
      if(Array.isArray(r.message)) return r.message;
      if(Array.isArray(r.message.results)) return r.message.results;
    }
    return [];
  }
  async function fetchCentroCustoOptions(){
    if(_cacheCentro) return _cacheCentro;
    try{
      const r = await frappe.call({ method: 'frappe.desk.search.search_link', args: { doctype: 'Centro de Custo', txt: '', page_length: 500 }});
      const raw = extractResults(r);
      _cacheCentro = raw.map(it=>({ value: it.value || it.name || '', label: it.value || it.name || '' })).filter(it=>it.value);
    }catch(e){ console.warn('Erro centros de custo', e); _cacheCentro = []; }
    return _cacheCentro;
  }
  async function fetchUsers(){
    if(_cacheUsers) return _cacheUsers;
    try{
      const r = await frappe.call({ method:'frappe.desk.search.search_link', args:{ doctype:'User', txt:'', page_length:500 } });
      const raw = extractResults(r);
      _cacheUsers = raw
        .map(it=>({ value: it.value || it.name || '', label: (it.description || it.value || it.name || '').replace(/<.*?>/g,'') }))
        .filter(it=>it.value && !['Guest','Administrator'].includes(it.value));
    }catch(e){ console.warn('Erro usuários', e); _cacheUsers = []; }
    return _cacheUsers;
  }
  async function populateSelect(selectEl, list, current){
    if(!selectEl) return;
    const cur = current || '';
    if(!list.length){
      selectEl.innerHTML = '<option value="">(nenhum encontrado)</option>';
      return;
    }
    selectEl.innerHTML = '<option value="">—</option>' + list.map(it=>`<option value="${it.value}">${it.label || it.value}</option>`).join('');
    if(cur){ selectEl.value = cur; }
  }
  async function salvarCampos(){
    const name = modal && modal.dataset.carteiraName;
    if(!name) return;
    const updates = {
      responsavel: qs('carteiraInputResponsavel').value || '',
      centro_de_custo: qs('carteiraInputCentro').value || '',
      chave_pix: qs('carteiraInputPix').value || '',
      descricao: qs('carteiraInputDescricao').value || ''
    };
    for(const [field,value] of Object.entries(updates)){
      try{ await frappe.call({ method:'frappe.client.set_value', args:{ doctype:'Carteira', name, fieldname:field, value } }); }
      catch(e){ frappe.msgprint('Erro ao salvar '+field); console.error(e); }
    }
    qs('carteiraModalResponsavel').textContent = updates.responsavel || '—';
    qs('carteiraModalCentro').textContent = updates.centro_de_custo || '—';
    qs('carteiraModalPix').textContent = updates.chave_pix || '—';
    qs('carteiraModalDescricao').textContent = updates.descricao || 'Sem descrição.';
    setEditMode(false);
  }
  window.fecharImportarDadosModal = function(){
    const m = document.getElementById('importarDadosModal');
    if(!m) return;
    m.classList.add('d-none');
    m.classList.remove('show');
    m.style.display = 'none';
    document.body.classList.remove('modal-open');
    document.querySelectorAll('[data-modal-backdrop="1"]').forEach(b=>b.remove());
  };

  document.addEventListener('click', function(e){
    // Abrir página de importação (Infinitepay, Portão 3, BTG Empresas) ao invés de modal
    if(e.target.classList.contains('importar-dados-btn')){
      const nome = (e.target.dataset.nome || '').trim().toLowerCase();
      if(nome === 'infinitepay'){
        window.location.href = '/financeiro/import_intinitepay';
        return;
      }
      if(nome === 'portão 3' || nome === 'portao 3'){
        window.location.href = '/financeiro/import_portao3';
        return;
      }
      if(nome === 'btg empresas' || nome === 'btgempresas' || nome === 'btg'){
        window.location.href = '/financeiro/import_btg_empresas';
        return;
      }
      frappe.msgprint('Funcionalidade em construção.');
      return;
    }
    if(e.target.matches('[data-modal-backdrop="1"]')){
      ['carteiraDetalheModal','novaInstituicaoModal','novaCarteiraModal'].forEach(id=>{ const m=qs(id); if(m && m.classList.contains('show')){ if(id==='carteiraDetalheModal') fecharCarteiraModal(); else if(id==='novaInstituicaoModal') fecharNovaInstituicaoModal(); else if(id==='novaCarteiraModal') fecharNovaCarteiraModal(); }});
      return;
    }
    if(e.target.classList.contains('modal') && !e.target.querySelector('.modal-dialog:hover')){
      const id=e.target.id;
      if(id==='carteiraDetalheModal') fecharCarteiraModal();
      else if(id==='novaInstituicaoModal') fecharNovaInstituicaoModal();
      else if(id==='novaCarteiraModal') fecharNovaCarteiraModal();
      return;
    }
    const btn = e.target.closest('.carteira-detalhes-btn');
    if(btn){
      fillAndOpen(btn);
      modal.dataset.carteiraName = btn.dataset.name;
      qs('carteiraInputResponsavel').value = (btn.dataset.responsavel && btn.dataset.responsavel !== '—') ? btn.dataset.responsavel : '';
      qs('carteiraInputCentro').value = (btn.dataset.centroCusto && btn.dataset.centroCusto !== '—') ? btn.dataset.centroCusto : '';
      qs('carteiraInputPix').value = (btn.dataset.chavePix && btn.dataset.chavePix !== '—') ? btn.dataset.chavePix : '';
      qs('carteiraInputDescricao').value = (btn.dataset.descricao && btn.dataset.descricao !== 'Sem descrição.') ? btn.dataset.descricao : '';
      setEditMode(false);
    }
    if(e.target.id==='btnNovaInstituicao'){
      qs('novaInstituicaoNome').value='';
      openSimpleModal('novaInstituicaoModal');
    } else if(e.target.id==='btnSalvarInstituicao'){
      (async function(){
        const nome = qs('novaInstituicaoNome').value.trim();
        if(!nome){ frappe.msgprint('Informe o nome.'); return; }
        try{
          const r = await frappe.call({ method:'frappe.client.insert', args:{ doc:{ doctype:'Instituicao Financeira', nome:nome } } });
          const doc = (r && r.message) || r;
          if(doc && doc.name){
            const grid = qs('listaContas');
            if(grid){
              const col = document.createElement('div');
              col.className='col mb-2';
              col.innerHTML = `<div class="card h-100 shadow-sm"><div class="card-body d-flex align-items-center justify-content-center text-center p-3"><span class="fw-semibold" title="${nome}">${nome}</span></div></div>`;
              grid.appendChild(col);
            }
            fecharNovaInstituicaoModal();
            frappe.show_alert({message:'Instituição criada', indicator:'green'});
          }
        }catch(err){ console.error(err); frappe.msgprint('Erro ao criar instituição.'); }
      })();
    } else if(e.target.id==='btnNovaCarteira'){
      ['nc_nome','nc_pix','nc_descricao'].forEach(id=>{ const el=qs(id); if(el) el.value=''; });
      qs('nc_instituicao').value='';
      Promise.all([fetchCentroCustoOptions(), fetchUsers()]).then(([centros, users])=>{
        const centroSel = qs('nc_centro');
        if(centroSel){ centroSel.innerHTML='<option value="">Selecione...</option>'+centros.map(c=>`<option value="${c.value}">${c.label||c.value}</option>`).join(''); }
        const respSel = qs('nc_responsavel');
        if(respSel){ respSel.innerHTML='<option value="">Selecione...</option>'+users.map(u=>`<option value="${u.value}">${u.label||u.value}</option>`).join(''); }
      });
      openSimpleModal('novaCarteiraModal');
    } else if(e.target.id==='btnSalvarCarteiraNova'){
      (async function(){
        const nome=qs('nc_nome').value.trim();
        const instituicao=qs('nc_instituicao').value.trim();
        const descricao=qs('nc_descricao').value.trim();
        const responsavel=qs('nc_responsavel').value.trim();
        const centro=qs('nc_centro').value.trim();
        const pix=qs('nc_pix').value.trim();
        if(!nome||!instituicao||!descricao||!responsavel||!centro){ frappe.msgprint('Preencha todos os campos obrigatórios.'); return; }
        try{
          const r = await frappe.call({ method:'frappe.client.insert', args:{ doc:{ doctype:'Carteira', nome:nome, instituicao_financeira:instituicao, descricao:descricao, responsavel:responsavel, centro_de_custo:centro, chave_pix:pix } } });
          const doc = (r && r.message) || r;
          if(doc && doc.name){
            const grid = document.querySelector('.row.row-cols-1.row-cols-sm-2.row-cols-md-3.row-cols-lg-5.g-3.gy-5');
            if(grid){
              const col=document.createElement('div'); col.className='col mb-2';
              col.innerHTML=`<div class=\"card h-100 shadow-sm\"><div class=\"card-body d-flex flex-column p-3\"><div class=\"d-flex justify-content-between align-items-start mb-2 flex-wrap gap-2\"><h6 class=\"mb-0 text-truncate\" title=\"${nome}\">${nome}</h6><span class=\"g-badge g-badge--neutral g-badge--small\" title=\"Instituição Financeira\">${instituicao}</span></div><div class=\"mb-1 small text-muted\">Saldo</div><div class=\"fw-semibold mb-3\">0,00</div><div class=\"mt-auto d-flex justify-content-between align-items-center gap-2 flex-wrap\"><div class=\"small text-muted\"><span>Atualização:</span> <span>—</span></div><button type=\"button\" class=\"btn btn-sm btn-outline-secondary px-3 carteira-detalhes-btn\" data-name=\"${doc.name}\" data-nome=\"${nome}\" data-instituicao=\"${instituicao}\" data-instituicao-classes=\"g-badge g-badge--neutral g-badge--small\" data-descricao=\"${descricao.replace(/\"/g,'&quot;')}\" data-responsavel=\"${responsavel}\" data-chave-pix=\"${pix}\" data-centro-custo=\"${centro}\" data-saldo=\"0,00\" data-data-atualizacao=\"\">Detalhes</button></div></div></div>`;
              grid.appendChild(col);
            }
            fecharNovaCarteiraModal();
            frappe.show_alert({message:'Carteira criada', indicator:'green'});
          }
        }catch(err){ console.error(err); frappe.msgprint('Erro ao criar carteira.'); }
      })();
    }
    if(e.target.id==='btnEditarCarteira'){
      setEditMode(true);
      Promise.all([fetchCentroCustoOptions(), fetchUsers()]).then(([centros, users])=>{
        const curCentro = qs('carteiraModalCentro').textContent.trim();
        const curResp = qs('carteiraModalResponsavel').textContent.trim();
        populateSelect(qs('carteiraInputCentro'), centros, curCentro === '—' ? '' : curCentro);
        populateSelect(qs('carteiraInputResponsavel'), users, curResp === '—' ? '' : curResp);
      });
    } else if(e.target.id==='btnCancelarEdicaoCarteira'){
      setEditMode(false);
    } else if(e.target.id==='btnSalvarCarteira'){
      salvarCampos();
    }
  });
  document.addEventListener('keydown', function(e){ if(e.key==='Escape'){ fecharCarteiraModal(); fecharNovaInstituicaoModal(); }});
})();
