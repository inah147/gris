// detalhe.js - lógica JS da página detalhe do Associado
(function(){
  document.addEventListener('DOMContentLoaded', function(){
    const form = document.querySelector('.assoc-form');
    const editableSelectors = 'input[name], select[name]';
    const changed = {}; // field -> value
    const saveBtn = document.getElementById('btn-salvar');
    const afastarBtn = document.getElementById('btn-afastar');
    const flagsEl = document.getElementById('assoc-flags');
    const associadoName = flagsEl?.dataset.name || '';
    const CAN_EDIT = flagsEl?.dataset.canEdit === '1';
    const HAS_OPEN_HIST = flagsEl?.dataset.hasOpen === '1';

    // Guardian visibility
    function updateGuardianVisibility(){
      const paisDivVal = (document.querySelector('[name="pais_divorciados"]')?.value || '').trim();
      const tipoGuardaVal = (document.querySelector('[name="tipo_guarda"]')?.value || '').trim();
      const show = paisDivVal === 'Sim' && tipoGuardaVal && tipoGuardaVal.toLowerCase() === 'unilateral';
      document.querySelectorAll('[data-guardian-field]').forEach(el => { el.style.display = show ? '' : 'none'; });
    }

    ['pais_divorciados','tipo_guarda'].forEach(n => {
      const el = document.querySelector('[name="'+n+'"]');
      if(el){ el.addEventListener('change', updateGuardianVisibility); }
    });
    updateGuardianVisibility();

    function markChanged(field, value){
      if(!CAN_EDIT) return;
      changed[field] = value;
      if(saveBtn && saveBtn.classList.contains('d-none')) saveBtn.classList.remove('d-none');
    }

    // Configure form fields
    if(!CAN_EDIT){
      document.querySelectorAll(editableSelectors).forEach(el => { el.setAttribute('disabled','disabled'); });
      if(saveBtn) saveBtn.remove();
    } else {
      document.querySelectorAll(editableSelectors).forEach(el => {
        if(el.disabled) return; // skip read-only
        el.addEventListener('change', () => {
          let val;
          if(el.type === 'checkbox') val = el.checked ? 1 : 0;
          else val = el.value;
          markChanged(el.name, val);
        });
      });
    }

    if(HAS_OPEN_HIST && CAN_EDIT && afastarBtn){ afastarBtn.classList.remove('d-none'); }

    function notify(msg, cls='info'){
      if(window.frappe?.show_alert){ frappe.show_alert({message: msg, indicator: cls}); }
      else { console.log(msg); }
    }

    saveBtn?.addEventListener('click', () => {
      if(Object.keys(changed).length === 0) return;
      saveBtn.disabled = true; saveBtn.textContent = 'Salvando...';
      frappe.call({
        method: 'gris.api.members_portal.update_member',
        args: { name: associadoName, changes: JSON.stringify(changed) }
      }).then(r => {
        saveBtn.disabled = false; saveBtn.textContent = 'Salvar';
        if(r.message && r.message.success){
          notify('Alterações salvas','green');
          for(const k in changed) delete changed[k];
          saveBtn.classList.add('d-none');
        } else {
          notify('Falha ao salvar','red');
        }
      }).catch(() => {
        saveBtn.disabled = false; saveBtn.textContent = 'Salvar';
        notify('Erro de comunicação','red');
      });
    });

    afastarBtn?.addEventListener('click', () => {
      if(!confirm('Confirmar afastamento?')) return;
      afastarBtn.disabled = true; afastarBtn.textContent = 'Processando...';
      frappe.call({
        method: 'gris.api.members_portal.set_member_leave',
        args: { name: associadoName }
      }).then(r => {
        afastarBtn.disabled = false; afastarBtn.textContent = 'Afastar associado';
        if(r.message && r.message.success){
          notify('Afastamento registrado','orange');
          window.location.reload();
        } else {
          notify(r.message && r.message.message ? r.message.message : 'Nada a afastar','yellow');
        }
      }).catch(() => {
        afastarBtn.disabled = false; afastarBtn.textContent = 'Afastar associado';
        notify('Erro ao afastar','red');
      });
    });

    // ========== GERENCIAMENTO DE HISTÓRICO ==========
    const modalHistorico = document.getElementById('modalHistorico');
    const modalHistoricoBackdrop = document.getElementById('modalHistoricoBackdrop');
    const btnEditHistorico = document.getElementById('btn-edit-historico');
    const btnAddHistorico = document.getElementById('btn-add-historico');
    const btnSaveHistorico = document.getElementById('btn-save-historico');
    const historicoList = document.getElementById('historico-list');
    let historicoData = [];

    function openHistoricoModal() {
      if(!modalHistorico) return;
      // Busca dados atuais do histórico
      frappe.call({
        method: 'gris.api.members_portal.get_member_history',
        args: { name: associadoName }
      }).then(r => {
        if(r.message && r.message.success) {
          historicoData = r.message.history || [];
          renderHistoricoList();
          
          // Mostra backdrop primeiro
          if(modalHistoricoBackdrop) {
            modalHistoricoBackdrop.style.display = 'block';
            setTimeout(() => modalHistoricoBackdrop.classList.add('show'), 10);
          }
          
          // Depois mostra modal
          modalHistorico.classList.add('show');
          modalHistorico.style.display = 'flex';
          document.body.classList.add('modal-open');
        } else {
          notify('Erro ao carregar histórico', 'red');
        }
      }).catch(err => {
        console.error('Erro ao carregar histórico:', err);
        notify('Erro ao carregar histórico', 'red');
      });
    }

    function closeHistoricoModal() {
      if(!modalHistorico) return;
      modalHistorico.classList.remove('show');
      modalHistorico.style.display = 'none';
      
      if(modalHistoricoBackdrop) {
        modalHistoricoBackdrop.classList.remove('show');
        setTimeout(() => modalHistoricoBackdrop.style.display = 'none', 300);
      }
      
      document.body.classList.remove('modal-open');
    }

    function renderHistoricoList() {
      if(!historicoList) return;
      if(historicoData.length === 0) {
        historicoList.innerHTML = '<div style="padding: var(--space-lg); text-align: center; color: var(--text-muted);">Nenhum período registrado. Clique em "Adicionar Período" para criar o primeiro.</div>';
        return;
      }
      
      let html = '';
      historicoData.forEach((item, idx) => {
        html += `
          <div class="historico-item" data-idx="${idx}" style="border: 1px solid var(--border-color); border-radius: var(--radius-md); padding: var(--space-md); margin-bottom: var(--space-md);">
            <div class="row g-3">
              <div class="col-12 col-md-5">
                <div class="form-group-modern">
                  <label class="form-label-modern">Data de Ingresso</label>
                  <input type="date" class="form-input-modern form-input-modern--sm" data-field="ingresso" value="${item.ingresso || ''}" required>
                </div>
              </div>
              <div class="col-12 col-md-5">
                <div class="form-group-modern">
                  <label class="form-label-modern">Data de Desligamento</label>
                  <input type="date" class="form-input-modern form-input-modern--sm" data-field="desligamento" value="${item.desligamento || ''}">
                </div>
              </div>
              <div class="col-12 col-md-2 d-flex align-items-end">
                <button type="button" class="btn-modern btn-modern--danger btn-modern--sm w-100" data-remove="${idx}">
                  <svg width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2">
                    <polyline points="3 6 5 6 21 6"/>
                    <path d="M19 6v14a2 2 0 0 1-2 2H7a2 2 0 0 1-2-2V6m3 0V4a2 2 0 0 1 2-2h4a2 2 0 0 1 2 2v2"/>
                  </svg>
                  Remover
                </button>
              </div>
            </div>
          </div>
        `;
      });
      historicoList.innerHTML = html;

      // Event listeners para campos
      historicoList.querySelectorAll('input[data-field]').forEach(input => {
        input.addEventListener('change', (e) => {
          const item = e.target.closest('.historico-item');
          const idx = parseInt(item.dataset.idx);
          const field = e.target.dataset.field;
          historicoData[idx][field] = e.target.value;
        });
      });

      // Event listeners para botões remover
      historicoList.querySelectorAll('[data-remove]').forEach(btn => {
        btn.addEventListener('click', (e) => {
          const idx = parseInt(e.currentTarget.dataset.remove);
          if(confirm('Remover este período do histórico?')) {
            historicoData.splice(idx, 1);
            renderHistoricoList();
          }
        });
      });
    }

    btnEditHistorico?.addEventListener('click', openHistoricoModal);

    btnAddHistorico?.addEventListener('click', () => {
      historicoData.push({ ingresso: '', desligamento: '' });
      renderHistoricoList();
    });

    btnSaveHistorico?.addEventListener('click', () => {
      // Valida dados
      for(let i = 0; i < historicoData.length; i++) {
        if(!historicoData[i].ingresso) {
          notify('Todos os períodos devem ter data de ingresso', 'red');
          return;
        }
      }

      btnSaveHistorico.disabled = true;
      btnSaveHistorico.textContent = 'Salvando...';
      
      frappe.call({
        method: 'gris.api.members_portal.update_member_history',
        args: { 
          name: associadoName,
          history: JSON.stringify(historicoData)
        }
      }).then(r => {
        btnSaveHistorico.disabled = false;
        btnSaveHistorico.textContent = 'Salvar Alterações';
        if(r.message && r.message.success) {
          notify('Histórico atualizado com sucesso', 'green');
          closeHistoricoModal();
          window.location.reload();
        } else {
          notify(r.message?.message || 'Erro ao salvar histórico', 'red');
        }
      }).catch(() => {
        btnSaveHistorico.disabled = false;
        btnSaveHistorico.textContent = 'Salvar Alterações';
        notify('Erro ao salvar histórico', 'red');
      });
    });

    // Fechar modal
    modalHistorico?.querySelectorAll('[data-dismiss-historico]').forEach(btn => {
      btn.addEventListener('click', closeHistoricoModal);
    });

    modalHistoricoBackdrop?.addEventListener('click', closeHistoricoModal);
  });
})();
