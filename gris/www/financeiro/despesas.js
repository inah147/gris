;(() => {
	function buildModal() {
		if (document.getElementById('modalDespesa')) return;
		const modalHtml = `
		<div id="modalDespesa" class="modal d-none" tabindex="-1">
			<div class="modal-dialog modal-dialog-centered">
				<div class="modal-content">
					<div class="modal-header">
						<h5 class="modal-title" id="despesaTitulo"></h5>
						
					</div>
					<div class="modal-body">
						<div class="d-flex flex-wrap gap-2 mb-3" id="despesaBadges"></div>
						<dl class="row mb-3" id="despesaDados"></dl>
						<div id="historicoPagamentos" class="border-top pt-3 d-none">
							<h6 class="fw-semibold mb-2">Histórico de Pagamentos</h6>
							<div class="table-responsive mb-0">
								<table class="table table-sm align-middle mb-0" id="historicoTabela">
									<thead>
										<tr>
											<th style="width:120px">Mês</th>
											<th>Status</th>
											<th class="text-end" style="width:80px">Ação</th>
										</tr>
									</thead>
									<tbody></tbody>
								</table>
								<div class="small text-muted py-2" id="historicoVazio">Carregando...</div>
							</div>
						</div>
						<form id="despesaEditForm" class="d-none">
							<div class="mb-2">
								<label class="form-label mb-1">Descrição</label>
								<input type="text" name="descricao" class="form-control form-control-sm" required />
							</div>
							<div class="row g-2">
								<div class="col-6">
									<label class="form-label mb-1">Valor (R$)</label>
									<input type="number" step="0.01" name="valor" class="form-control form-control-sm" required />
								</div>
								<div class="col-6">
									<label class="form-label mb-1">Dia Venc.</label>
									<input type="number" min="1" max="31" name="dia_vencimento" class="form-control form-control-sm" required />
								</div>
							</div>
							<div class="mt-2" id="checksRow">
								<div class="form-check form-check-inline me-4 align-middle m-0">
									<input class="form-check-input" type="checkbox" name="ativa" id="editAtiva" />
									<label class="form-check-label" for="editAtiva">Ativa</label>
								</div>
								<div class="form-check form-check-inline align-middle m-0">
									<input class="form-check-input" type="checkbox" name="temporaria" id="editTemporaria" />
									<label class="form-check-label" for="editTemporaria">Despesa Temporária</label>
								</div>
							</div>
							<div id="temporariaDatas" class="row g-2 mt-1 d-none">
								<div class="col-6">
									<label class="form-label mb-1" for="field_data_inicio">Início</label>
									<input id="field_data_inicio" type="date" name="data_inicio" class="form-control form-control-sm" />
								</div>
								<div class="col-6">
									<label class="form-label mb-1" for="field_data_termino">Término</label>
									<input id="field_data_termino" type="date" name="data_termino" class="form-control form-control-sm" />
								</div>
							</div>
						</form>
					</div>
					<div class="modal-footer">
						<div class="me-auto" id="editButtons" style="display:none">
							<button type="button" class="btn btn-sm btn-outline-primary" data-action="edit">Editar</button>
							<button type="button" class="btn btn-sm btn-success d-none" data-action="save">Salvar</button>
							<button type="button" class="btn btn-sm btn-outline-secondary d-none" data-action="cancel-edit">Cancelar</button>
						</div>
						<button type="button" class="btn btn-secondary" data-action="close">Fechar</button>
					</div>
				</div>
			</div>
		</div>`;
		document.body.insertAdjacentHTML('beforeend', modalHtml);
		const modal = document.getElementById('modalDespesa');
		modal.addEventListener('click', e => {
			if (e.target.dataset.action === 'close' || e.target === modal) hideModal();
		});
		modal.querySelector('[data-action="edit"]').addEventListener('click', enableEditMode);
		modal.querySelector('[data-action="cancel-edit"]').addEventListener('click', cancelEditMode);
		modal.querySelector('[data-action="save"]').addEventListener('click', saveEdits);
		modal.querySelector('#editTemporaria').addEventListener('change', toggleTemporariaDates);
	}

	// --- Criação de Nova Despesa ---
	function buildCreateModal(){
		if(document.getElementById('modalNovaDespesa')) return;
		const html = `
		<div id="modalNovaDespesa" class="modal d-none" tabindex="-1">
			<div class="modal-dialog modal-dialog-centered">
				<div class="modal-content">
					<div class="modal-header">
						<h5 class="modal-title">Nova Despesa</h5>
					</div>
					<div class="modal-body">
						<form id="novaDespesaForm">
							<div class="mb-2">
								<label class="form-label mb-1">Descrição</label>
								<input type="text" name="descricao" class="form-control form-control-sm" required />
							</div>
							<div class="row g-2">
								<div class="col-6">
									<label class="form-label mb-1">Valor (R$)</label>
									<input type="number" step="0.01" name="valor" class="form-control form-control-sm" required />
								</div>
								<div class="col-6">
									<label class="form-label mb-1">Dia Venc.</label>
									<input type="number" min="1" max="31" name="dia_vencimento" class="form-control form-control-sm" required />
								</div>
							</div>
							<div class="mt-2" id="novaChecksRow">
								<div class="form-check form-check-inline me-4 align-middle m-0">
									<input class="form-check-input" type="checkbox" name="ativa" id="novaAtiva" checked />
									<label class="form-check-label" for="novaAtiva">Ativa</label>
								</div>
								<div class="form-check form-check-inline align-middle m-0">
									<input class="form-check-input" type="checkbox" name="temporaria" id="novaTemporaria" />
									<label class="form-check-label" for="novaTemporaria">Despesa Temporária</label>
								</div>
							</div>
							<div id="novaTemporariaDatas" class="row g-2 mt-1 d-none">
								<div class="col-6">
									<label class="form-label mb-1" for="nova_data_inicio">Início</label>
									<input id="nova_data_inicio" type="date" name="data_inicio" class="form-control form-control-sm" />
								</div>
								<div class="col-6">
									<label class="form-label mb-1" for="nova_data_termino">Término</label>
									<input id="nova_data_termino" type="date" name="data_termino" class="form-control form-control-sm" />
								</div>
							</div>
						</form>
					</div>
					<div class="modal-footer">
						<button type="button" class="btn btn-secondary" data-action="close-nova">Fechar</button>
						<button type="button" class="btn btn-primary" data-action="save-nova">Salvar</button>
					</div>
				</div>
			</div>
		</div>`;
		document.body.insertAdjacentHTML('beforeend', html);
		const modal = document.getElementById('modalNovaDespesa');
		modal.addEventListener('click', e => {
			if(e.target.dataset.action === 'close-nova' || e.target === modal) hideCreateModal();
		});
		modal.querySelector('[data-action="save-nova"]').addEventListener('click', saveNovaDespesa);
		document.getElementById('novaTemporaria').addEventListener('change', toggleNovaTemporariaDates);
	}

	function showCreateModal(){
		buildCreateModal();
		const modal = document.getElementById('modalNovaDespesa');
		modal.classList.remove('d-none');
		modal.classList.add('show');
		modal.style.display = 'block';
		document.body.classList.add('modal-open');
		const backdrop = document.createElement('div');
		backdrop.className = 'modal-backdrop fade show modal-backdrop-soft';
		backdrop.id = 'modalNovaDespesaBackdrop';
		document.body.appendChild(backdrop);
	}

	function hideCreateModal(){
		const modal = document.getElementById('modalNovaDespesa');
		if(!modal) return;
		modal.classList.add('d-none');
		modal.classList.remove('show');
		modal.style.display = 'none';
		const backdrop = document.getElementById('modalNovaDespesaBackdrop');
		if(backdrop) backdrop.remove();
		if(!document.getElementById('modalDespesa')?.classList.contains('show')){
			document.body.classList.remove('modal-open');
		}
	}

	function toggleNovaTemporariaDates(){
		const form = document.getElementById('novaDespesaForm');
		const box = document.getElementById('novaTemporariaDatas');
		if(form.temporaria.checked){
			box.classList.remove('d-none');
			addAsteriskNova('data_inicio');
			addAsteriskNova('data_termino');
		}else{
			box.classList.add('d-none');
			removeAsteriskNova('data_inicio');
			removeAsteriskNova('data_termino');
		}
	}
	function addAsteriskNova(field){
		const id = field === 'data_inicio' ? 'nova_data_inicio' : 'nova_data_termino';
		const label = document.querySelector(`#novaTemporariaDatas label[for="${id}"]`);
		if(!label || label.querySelector('.req-star')) return;
		const span = document.createElement('span');
		span.className = 'req-star';
		span.style.color = '#dc3545';
		span.textContent = ' *';
		label.appendChild(span);
	}
	function removeAsteriskNova(field){
		const id = field === 'data_inicio' ? 'nova_data_inicio' : 'nova_data_termino';
		const label = document.querySelector(`#novaTemporariaDatas label[for="${id}"]`);
		if(!label) return; const star = label.querySelector('.req-star'); if(star) star.remove();
	}

	function saveNovaDespesa(){
		const btn = this;
		const form = document.getElementById('novaDespesaForm');
		if(!form.reportValidity()) return;
		if(form.temporaria.checked){
			if(!form.data_inicio.value || !form.data_termino.value){
				frappe.msgprint({ message: 'Preencha Início e Término para despesa temporária.', indicator: 'orange' });
				return;
			}
			if(form.data_inicio.value > form.data_termino.value){
				frappe.msgprint({ message: 'Data de início não pode ser maior que a data de término.', indicator: 'red' });
				return;
			}
		}
		btn.disabled = true; btn.textContent = 'Salvando...';
		frappe.call({
			method: 'gris.api.financeiro.conta_fixa.create_conta_fixa',
			args: {
				descricao: form.descricao.value.trim(),
				valor: form.valor.value,
				dia_vencimento: form.dia_vencimento.value,
				ativa: form.ativa.checked ? 1 : 0,
				despesa_temporaria: form.temporaria.checked ? 1 : 0,
				data_inicio: form.temporaria.checked ? form.data_inicio.value : '',
				data_termino: form.temporaria.checked ? form.data_termino.value : ''
			},
			callback: r => {
				btn.disabled = false; btn.textContent = 'Salvar';
				if(r && r.message && r.message.ok){
					window.location.reload();
				}
			},
			error: () => { btn.disabled = false; btn.textContent = 'Salvar'; }
		});
	}

	function showModal() {
		const modal = document.getElementById('modalDespesa');
		if (!modal) return;
		modal.classList.remove('d-none');
		modal.classList.add('show');
		modal.style.display = 'block';
		document.body.classList.add('modal-open');
		const backdrop = document.createElement('div');
		backdrop.className = 'modal-backdrop fade show modal-backdrop-soft';
		backdrop.id = 'modalDespesaBackdrop';
		document.body.appendChild(backdrop);
	}

	function hideModal() {
		const modal = document.getElementById('modalDespesa');
		if (!modal) return;
		modal.classList.add('d-none');
		modal.classList.remove('show');
		modal.style.display = 'none';
		document.body.classList.remove('modal-open');
		const backdrop = document.getElementById('modalDespesaBackdrop');
		if (backdrop) backdrop.remove();
	}

	function formatCurrency(v) {
		const num = Number(v || 0);
		return num.toLocaleString('pt-BR', { style: 'currency', currency: 'BRL' });
	}

	function buildBadges(data) {
		const badges = [];
		// Status
		if (data.status) {
			const slug = data.status.toLowerCase().replace(/\s+/g, '');
			badges.push(`<span class="fx-badge fx-badge-${['pago','atrasado','emaberto','aguardar'].includes(slug) ? slug : 'desconhecido'}">${data.status}</span>`);
		}
		// Ativa
		badges.push(`<span class="fx-badge fx-badge-${data.ativa ? 'ativa' : 'inativa'}">${data.ativa ? 'Ativa' : 'Inativa'}</span>`);
		// Tipo
		badges.push(`<span class="fx-badge fx-badge-${data.temporaria ? 'temporaria' : 'continua'}">${data.temporaria ? 'Temporária' : 'Contínua'}</span>`);
		return badges.join('');
	}

	function openDespesa(btn) {
		buildModal();
		const data = {
			name: btn.getAttribute('data-name'),
			descricao: btn.getAttribute('data-descricao'),
			valor: btn.getAttribute('data-valor'),
			dia: btn.getAttribute('data-dia'),
			status: btn.getAttribute('data-status') || 'Em Aberto',
			ativa: btn.getAttribute('data-ativa') === '1',
			temporaria: btn.getAttribute('data-temporaria') === '1',
			inicio: btn.getAttribute('data-inicio') || '',
			termino: btn.getAttribute('data-termino') || ''
		};
		const permEl = document.getElementById('financeiro-perms');
		const canEdit = permEl && permEl.dataset.canEdit === '1';
		document.getElementById('despesaTitulo').textContent = data.descricao;
		document.getElementById('despesaBadges').innerHTML = buildBadges(data);
		const dl = document.getElementById('despesaDados');
		let html = '';
		html += `<dt class="col-sm-4">Valor</dt><dd class="col-sm-8">${formatCurrency(data.valor)}</dd>`;
		html += `<dt class="col-sm-4">Dia Vencimento</dt><dd class="col-sm-8">${data.dia}</dd>`;
		if (data.temporaria) {
			html += `<dt class="col-sm-4">Início</dt><dd class="col-sm-8">${data.inicio || '-'} </dd>`;
			html += `<dt class="col-sm-4">Término</dt><dd class="col-sm-8">${data.termino || '-'} </dd>`;
		}
		dl.innerHTML = html;
		const editButtons = document.getElementById('editButtons');
		if (canEdit) {
			editButtons.style.display = '';
			editButtons.dataset.name = data.name;
			prefillEditForm(data);
		} else {
			editButtons.style.display = 'none';
		}
		showModal();
		loadHistorico(data.name);
	}

	function loadHistorico(contaName){
		const wrap = document.getElementById('historicoPagamentos');
		const tabela = document.querySelector('#historicoTabela tbody');
		const vazio = document.getElementById('historicoVazio');
		const canEdit = (document.getElementById('financeiro-perms')?.dataset.canEdit === '1');
		wrap.classList.remove('d-none');
		vazio.textContent = 'Carregando...';
		tabela.innerHTML = '';
		frappe.call({
			method: 'gris.api.financeiro.conta_fixa.get_pagamentos_conta',
			args: { conta: contaName, limit: 12 },
			callback: r => {
				const dados = (r && r.message) || [];
				if(!dados.length){
					vazio.textContent = 'Nenhum pagamento encontrado.';
					return;
				}
				vazio.classList.add('d-none');
				const frag = document.createDocumentFragment();
				dados.forEach(p => {
					const tr = document.createElement('tr');
					const statusSlug = (p.status || '').toLowerCase().replace(/\s+/g,'');
					const isPago = statusSlug === 'pago';
					const badgeHtml = `<span class="fx-badge fx-badge-${['pago','atrasado','emaberto','aguardar'].includes(statusSlug)?statusSlug:'desconhecido'} me-2">${p.status}</span>`;
					let actionHtml = '';
					if (!isPago && canEdit) {
						actionHtml = `<button type="button" class="btn btn-xs btn-success pay-btn" data-pagamento="${p.name}">Pago</button>`;
					}
					tr.innerHTML = `
						<td class="text-nowrap">${p.mes_format || p.mes_referencia || ''}</td>
						<td>${badgeHtml}</td>
						<td class="text-end">${actionHtml}</td>
					`;
					frag.appendChild(tr);
				});
				tabela.appendChild(frag);
				if (canEdit) attachPayHandlers();
			}
		});
	}

	function attachPayHandlers(){
		document.querySelectorAll('#historicoTabela .pay-btn').forEach(btn => {
			btn.addEventListener('click', () => {
				if(btn.disabled) return;
				btn.disabled = true;
				btn.textContent = '...';
				const pagamento = btn.getAttribute('data-pagamento');
				frappe.call({
					method: 'gris.api.financeiro.conta_fixa.marcar_pagamento_pago',
					args: { pagamento },
					callback: r => {
						if (r && r.message && r.message.ok) {
							const td = btn.parentElement;
							btn.remove();
							// replace badge to Pago
							const badge = td.querySelector('.fx-badge');
							if (badge) {
								badge.className = 'fx-badge fx-badge-pago me-2';
								badge.textContent = 'Pago';
							}
						}
					},
					error: () => {
						btn.disabled = false;
						btn.textContent = 'Pago';
					}
				});
			});
		});
	}

	function prefillEditForm(data) {
		const form = document.getElementById('despesaEditForm');
		form.descricao.value = data.descricao;
		form.valor.value = Number(data.valor || 0).toFixed(2);
		form.dia_vencimento.value = data.dia;
		form.ativa.checked = !!data.ativa;
		form.temporaria.checked = !!data.temporaria;
		form.data_inicio.value = data.inicio || '';
		form.data_termino.value = data.termino || '';
		toggleTemporariaDates();
	}

	function enableEditMode() {
		const form = document.getElementById('despesaEditForm');
		form.classList.remove('d-none');
		document.getElementById('despesaDados').classList.add('d-none');
		this.classList.add('d-none');
		const footer = this.parentElement;
		footer.querySelector('[data-action="save"]').classList.remove('d-none');
		footer.querySelector('[data-action="cancel-edit"]').classList.remove('d-none');
	}

	function cancelEditMode() {
		const footer = this.parentElement;
		footer.querySelector('[data-action="edit"]').classList.remove('d-none');
		footer.querySelector('[data-action="save"]').classList.add('d-none');
		footer.querySelector('[data-action="cancel-edit"]').classList.add('d-none');
		document.getElementById('despesaEditForm').classList.add('d-none');
		document.getElementById('despesaDados').classList.remove('d-none');
	}

	function toggleTemporariaDates() {
		const form = document.getElementById('despesaEditForm');
		const box = document.getElementById('temporariaDatas');
		if (form.temporaria.checked) {
			box.classList.remove('d-none');
			addAsterisk('data_inicio');
			addAsterisk('data_termino');
		} else {
			box.classList.add('d-none');
			removeAsterisk('data_inicio');
			removeAsterisk('data_termino');
		}
	}

	function addAsterisk(fieldName){
		const id = fieldName === 'data_inicio' ? 'field_data_inicio' : 'field_data_termino';
		const label = document.querySelector(`#temporariaDatas label[for="${id}"]`);
		if(!label || label.querySelector('.req-star')) return;
		const span = document.createElement('span');
		span.className = 'req-star';
		span.style.color = '#dc3545';
		span.textContent = ' *';
		label.appendChild(span);
	}
	function removeAsterisk(fieldName){
		const id = fieldName === 'data_inicio' ? 'field_data_inicio' : 'field_data_termino';
		const label = document.querySelector(`#temporariaDatas label[for="${id}"]`);
		if(!label) return;
		const star = label.querySelector('.req-star');
		if(star) star.remove();
	}

	function saveEdits() {
		const footer = this.parentElement;
		const name = footer.dataset.name;
		const form = document.getElementById('despesaEditForm');
		if (!form.reportValidity()) return; // mantém validação dos outros campos
		if (form.temporaria.checked) {
			if (!form.data_inicio.value || !form.data_termino.value) {
				frappe.msgprint({
					message: 'Preencha Início e Término para despesa temporária.',
					indicator: 'orange'
				});
				return;
			}
			if (form.data_inicio.value > form.data_termino.value) {
				frappe.msgprint({
					message: 'Data de início não pode ser maior que a data de término.',
					indicator: 'red'
				});
				return;
			}
		}
		this.disabled = true;
		this.textContent = 'Salvando...';
		const payload = {
			name,
			descricao: form.descricao.value.trim(),
			valor: form.valor.value,
			dia_vencimento: form.dia_vencimento.value,
			ativa: form.ativa.checked ? 1 : 0,
			despesa_temporaria: form.temporaria.checked ? 1 : 0,
			data_inicio: form.temporaria.checked ? form.data_inicio.value : '',
			data_termino: form.temporaria.checked ? form.data_termino.value : ''
		};
		frappe.call({
			method: 'gris.api.financeiro.conta_fixa.update_conta_fixa',
			args: payload,
			callback: (r) => {
				this.disabled = false;
				this.textContent = 'Salvar';
				if (r && r.message && r.message.ok) {
					// Simple strategy: reload page to reflect updates
					window.location.reload();
				}
			},
			error: () => {
				this.disabled = false;
				this.textContent = 'Salvar';
			}
		});
	}

	function init() {
		document.querySelectorAll('.detalhes-conta-btn').forEach(btn => {
			btn.addEventListener('click', () => openDespesa(btn));
		});
		const novaBtn = document.getElementById('btnNovaDespesa');
		if(novaBtn){
			novaBtn.addEventListener('click', showCreateModal);
		}
		document.addEventListener('keydown', e => {
			if (e.key === 'Escape') hideModal();
			if (e.key === 'Escape') hideCreateModal();
		});
	}
	if (document.readyState === 'loading') {
		document.addEventListener('DOMContentLoaded', init);
	} else {
		init();
	}
})();
