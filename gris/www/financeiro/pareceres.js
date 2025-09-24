// Placeholder for future interactions on pareceres page
(function(){
  function q(id){ return document.getElementById(id); }
  function openModal(el){
    if(!el) return;
    const alreadyOpen = el.classList.contains('show');
    el.classList.remove('d-none');
    el.classList.add('show');
    el.style.display='block';
    document.body.classList.add('modal-open');
    // Only add a backdrop if one doesn't already exist
    if(!document.querySelector('.modal-backdrop[data-modal-backdrop="parecer"]')){
      const backdrop=document.createElement('div');
      backdrop.className='modal-backdrop fade show';
      backdrop.dataset.modalBackdrop='parecer';
      document.body.appendChild(backdrop);
    }
  }
  function closeModal(el){ if(!el) return; el.classList.remove('show'); el.style.display='none'; el.classList.add('d-none'); document.body.classList.remove('modal-open'); document.querySelectorAll('[data-modal-backdrop="parecer"]').forEach(b=>b.remove()); }
  window.closeParecerModal = function(){ closeModal(q('parecerDetailModal')); };

  function populateAndOpen(card){
    const title = card.dataset.tipo || 'Parecer';
    const ano = card.dataset.ano || '—';
  const trimestre = card.dataset.trimestre || '';
    const area = card.dataset.area || '—';
    const published = card.dataset.published === '1';
    const file = card.dataset.file || '';
    const name = card.dataset.name || '';

    q('parecerModalTitle').textContent = title;
    const badge = q('parecerModalBadge');
    badge.innerHTML = `<span class="g-badge g-badge--small ${published ? 'g-badge--success' : 'g-badge--inactive'}">${published ? 'Publicado' : 'Rascunho'}</span>`;
    q('parecerModalAno').textContent = ano || '—';
    if(title === 'Parecer trimestral da comissão fiscal'){
      q('parecerModalTrimestreRow').classList.remove('d-none');
      q('parecerModalTrimestre').textContent = trimestre || '—';
    } else {
      q('parecerModalTrimestreRow').classList.add('d-none');
    }
    q('parecerModalArea').textContent = area || '—';

    const fileBtn = document.getElementById('parecerModalFileBtn');
    if(file){
      let href = file;
      if(!(href.startsWith('/files') || href.startsWith('/private/files') || href.startsWith('http'))){
        href = '/files/' + href;
      }
      fileBtn.href = href;
      fileBtn.style.display = '';
    } else {
      fileBtn.removeAttribute('href');
      fileBtn.style.display = 'none';
    }

    // Edit buttons (permission controlled server-side via template rendering)
    const publishBtn = document.getElementById('parecerPublishBtn');
    const unpublishBtn = document.getElementById('parecerUnpublishBtn');
    const deleteBtn = document.getElementById('parecerDeleteBtn');
    if(publishBtn && unpublishBtn && deleteBtn){
      // Store current docname for actions
      publishBtn.dataset.docname = name;
      unpublishBtn.dataset.docname = name;
      deleteBtn.dataset.docname = name;
      // Toggle which publish/unpublish is visible
      if(published){
        publishBtn.classList.add('d-none');
        unpublishBtn.classList.remove('d-none');
      } else {
        publishBtn.classList.remove('d-none');
        unpublishBtn.classList.add('d-none');
      }
      deleteBtn.classList.remove('d-none');
    }

    openModal(q('parecerDetailModal'));
  }
  
  // removed old duplicate populateParecerModal (logic merged into populateAndOpen)

  document.addEventListener('click', function(e){
    if(e.target.classList.contains('parecer-details-btn')){
      const card = e.target.closest('.parecer-card');
      if(card) populateAndOpen(card);
    } else if(e.target.matches('[data-modal-backdrop="parecer"]')){
      closeParecerModal();
    }
    else if(e.target.id === 'parecerPublishBtn'){
      const docname = e.target.dataset.docname;
      if(!docname) return;
      e.target.disabled = true;
      frappe.call({
        method: 'frappe.client.set_value',
        args: { doctype: 'Transparencia', name: docname, fieldname: { publicado: 1 } },
        callback: function(r){
          e.target.disabled = false;
          if(!r.exc){
            frappe.show_alert({message: 'Publicado', indicator: 'green'});
            // Update card dataset and re-open to refresh
            const card = document.querySelector(`.parecer-card[data-name="${docname}"]`);
            if(card){ card.dataset.published='1'; }
            populateAndOpen(card);
          }
        }
      });
    }
    else if(e.target.id === 'parecerUnpublishBtn'){
      const docname = e.target.dataset.docname;
      if(!docname) return;
      e.target.disabled = true;
      frappe.call({
        method: 'frappe.client.set_value',
        args: { doctype: 'Transparencia', name: docname, fieldname: { publicado: 0 } },
        callback: function(r){
          e.target.disabled = false;
          if(!r.exc){
            frappe.show_alert({message: 'Despublicado', indicator: 'orange'});
            const card = document.querySelector(`.parecer-card[data-name="${docname}"]`);
            if(card){ card.dataset.published='0'; }
            populateAndOpen(card);
          }
        }
      });
    }
    else if(e.target.id === 'parecerDeleteBtn'){
      const docname = e.target.dataset.docname;
      if(!docname) return;
      if(!confirm('Apagar este parecer? Essa ação não pode ser desfeita.')) return;
      e.target.disabled = true;
      frappe.call({
        method: 'frappe.client.delete',
        args: { doctype: 'Transparencia', name: docname },
        callback: function(r){
          e.target.disabled = false;
          if(!r.exc){
            frappe.show_alert({message: 'Parecer apagado', indicator: 'red'});
            // Remove card and close modal
            const card = document.querySelector(`.parecer-card[data-name="${docname}"]`);
            if(card){ card.remove(); }
            closeParecerModal();
          }
        }
      });
    }
    else if(e.target.id === 'addParecerBtn'){
      const modal = document.getElementById('parecerAddModal');
      if(modal){ openModal(modal); }
    }
    else if(e.target.id === 'addParecerCancelBtn'){
      const modal = document.getElementById('parecerAddModal');
      closeModal(modal);
    }
    else if(e.target.id === 'addParecerSaveBtn'){
      saveNewParecer(e.target);
    }
  });

  // Year filter
  document.addEventListener('change', function(e){
    if(e.target.id === 'parecerYearFilter'){
      const year = e.target.value;
      document.querySelectorAll('.parecer-card').forEach(card => {
        const cardYear = card.dataset.ano || '';
        if(!year || cardYear === year){
          card.parentElement.classList.remove('d-none');
        } else {
          card.parentElement.classList.add('d-none');
        }
      });
    }
  });

  // Handle tipo -> trimestre toggle
  document.addEventListener('change', function(e){
    if(e.target.id === 'addParecerTipo'){
      const group = document.getElementById('addParecerTrimestreGroup');
      if(e.target.value === 'trimestral') group.classList.remove('d-none');
      else group.classList.add('d-none');
    }
  });

  async function saveNewParecer(btn){
    const tipo = document.getElementById('addParecerTipo').value;
    const ano = document.getElementById('addParecerAno').value;
    const trimestreWrapper = document.getElementById('addParecerTrimestreGroup');
    const trimestre = !trimestreWrapper.classList.contains('d-none') ? document.getElementById('addParecerTrimestre').value : '';
  // File uploader integration: we store selected file data in window._parecerFileData
  if(!tipo || !ano || (tipo==='trimestral' && !trimestre) || !window._parecerFileData){
      frappe.show_alert({message: 'Preencha os campos obrigatórios', indicator: 'orange'});
      return;
    }
    btn.disabled = true;
    btn.textContent = 'Salvando...';
  const tipoArquivo = tipo === 'trimestral' ? 'Parecer trimestral da comissão fiscal' : 'Parecer anual da comissão fiscal';
    try {
      const docPayload = {
        doctype: 'Transparencia',
        tipo_arquivo: tipoArquivo,
        ano_referencia: parseInt(ano,10),
        area: 'Financeiro'
      };
      if(tipo==='trimestral') docPayload.trimestre_referencia = parseInt(trimestre,10);
      // Include file URL now (mandatory field)
      if(window._parecerFileData && window._parecerFileData.file_url){
        docPayload.arquivo = window._parecerFileData.file_url;
      }
      const insertRes = await frappe.call({ method: 'frappe.client.insert', args: { doc: docPayload } });
      if(insertRes.exc){ throw insertRes.exc; }
      const newDoc = insertRes.message;
      frappe.show_alert({message: 'Parecer criado', indicator: 'green'});
      // Add card dynamically to proper section
      addParecerCard({
        name: newDoc.name,
        tipo_arquivo: tipoArquivo,
        published: false,
        area: 'Financeiro',
        ano_referencia: ano,
  trimestre_referencia: tipo==='trimestral' ? trimestre : '',
        arquivo: ''
      });
      closeModal(document.getElementById('parecerAddModal'));
    } catch(err){
      console.error(err);
      frappe.show_alert({message: 'Erro ao salvar', indicator: 'red'});
    } finally {
      btn.disabled = false;
      btn.textContent = 'Salvar';
    }
  }

  function addParecerCard(p){
    const containerId = p.tipo_arquivo === 'Parecer trimestral da comissão fiscal' ? 'quarterlyParecers' : 'annualParecers';
    const container = document.getElementById(containerId);
    if(!container) return;
    const col = document.createElement('div');
    col.className = 'col';
  const period = p.tipo_arquivo === 'Parecer trimestral da comissão fiscal' && p.trimestre_referencia ? `${p.trimestre_referencia}º de ${p.ano_referencia}` : (p.ano_referencia || '—');
    col.innerHTML = `
  <div class="card h-100 shadow-sm parecer-card" data-name="${p.name}" data-tipo="${p.tipo_arquivo}" data-period="${period}" data-published="0" data-area="${p.area || ''}" data-ano="${p.ano_referencia || ''}" data-trimestre="${p.trimestre_referencia || ''}" data-file="${p.arquivo || ''}">
        <div class="card-body d-flex flex-column p-3">
          <h6 class="mb-1 fw-semibold text-truncate" title="${p.tipo_arquivo}">${p.tipo_arquivo}</h6>
          <div class="text-muted small mb-2">${period}</div>
          <div class="mt-auto d-flex justify-content-between align-items-center">
            <span class="g-badge g-badge--small g-badge--inactive">Rascunho</span>
            <button type="button" class="btn btn-sm btn-dark px-3 parecer-details-btn">Detalhes</button>
          </div>
        </div>
      </div>`;
    container.prepend(col);
  }

  // Initialize Frappe FileUploader when clicking the select button
  document.addEventListener('click', function(e){
    if(e.target && e.target.id === 'addParecerArquivoBtn'){
      if(typeof frappe === 'undefined' || !frappe.ui || !frappe.ui.FileUploader){
        frappe.msgprint('Uploader indisponível.');
        return;
      }
      new frappe.ui.FileUploader({
        allow_multiple: false,
        as_dataurl: false,
        disable_file_browser: false,
        restrictions: { max_number_of_files: 1 },
        folder: 'Home',
        is_private: 0, // ensure public
        // After upload complete
        on_success(file){
          window._parecerFileData = file;
          const wrap = document.getElementById('addParecerArquivoNameWrapper');
          const nameEl = document.getElementById('addParecerArquivoName');
          if(wrap && nameEl){
            nameEl.textContent = file.file_name || file.name;
            wrap.classList.remove('d-none');
          }
          // Removido ajuste pós-upload para evitar erro de nome duplicado ao mover arquivo.
        }
      });
    }
  });
  document.addEventListener('keydown', function(e){ if(e.key==='Escape'){ closeParecerModal(); }});
})();
