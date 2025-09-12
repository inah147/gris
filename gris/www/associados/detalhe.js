// detalhe.js - lógica JS da página detalhe do Associado
(function(){
  document.addEventListener('DOMContentLoaded', function(){
    // Section toggles
    document.querySelectorAll('[data-toggle-section]').forEach(btn => {
      btn.addEventListener('click', () => {
        const section = btn.closest('[data-section]');
        section.classList.toggle('collapsed');
      });
    });

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
      if(!form) return;
      const paisDivVal = (form.querySelector('[name="pais_divorciados"]')?.value || '').trim();
      const tipoGuardaVal = (form.querySelector('[name="tipo_guarda"]')?.value || '').trim();
      const show = paisDivVal === 'Sim' && tipoGuardaVal && tipoGuardaVal.toLowerCase() === 'unilateral';
      form.querySelectorAll('[data-guardian-field]').forEach(el => { el.style.display = show ? '' : 'none'; });
    }

    if(form){
      ['pais_divorciados','tipo_guarda'].forEach(n => {
        const el = form.querySelector('[name="'+n+'"]');
        if(el){ el.addEventListener('change', updateGuardianVisibility); }
      });
      updateGuardianVisibility();
    }

    function markChanged(field, value){
      if(!CAN_EDIT) return;
      changed[field] = value;
      if(saveBtn && saveBtn.classList.contains('d-none')) saveBtn.classList.remove('d-none');
    }

    if(form){
      if(!CAN_EDIT){
        form.querySelectorAll(editableSelectors).forEach(el => { el.setAttribute('disabled','disabled'); });
        if(saveBtn) saveBtn.remove();
      }
      form.querySelectorAll(editableSelectors).forEach(el => {
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
  });
})();
