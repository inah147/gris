// Página /financeiro/despesas — modais HTML5 <dialog> e CRUD de Conta Fixa
;(() => {
	'use strict';

	function qs(id) { return document.getElementById(id); }

	function openDialog(id) {
		const dlg = qs(id);
		if (dlg && typeof dlg.showModal === 'function' && !dlg.open) dlg.showModal();
	}

	function closeDialog(id) {
		const dlg = qs(id);
		if (dlg && dlg.open) dlg.close();
	}

	function formatCurrency(v) {
		const num = Number(v || 0);
		return num.toLocaleString('pt-BR', { style: 'currency', currency: 'BRL' });
	}

	function statusVariantClass(slug) {
		if (slug === 'pago') return 'badge-success';
		if (slug === 'atrasado') return 'badge-destructive';
		if (slug === 'emaberto') return 'badge-warning';
		return 'badge-secondary';
	}

	function buildBadges(data) {
		const out = [];
		if (data.status) {
			const slug = data.status.toLowerCase().replace(/\s+/g, '');
			out.push('<span class="badge ' + statusVariantClass(slug) + '">' + data.status + '</span>');
		}
		out.push('<span class="badge ' + (data.ativa ? '' : 'badge-secondary') + '">' + (data.ativa ? 'Ativa' : 'Inativa') + '</span>');
		out.push('<span class="badge ' + (data.temporaria ? 'badge-info' : '') + '">' + (data.temporaria ? 'Temporária' : 'Contínua') + '</span>');
		return out.join('');
	}

	// Lê valor selecionado de um datepicker do design system (pelo id da raiz <div class="datepicker">)
	function dpGetValue(rootId) {
		const root = qs(rootId);
		if (!root) return '';
		const input = root.querySelector('[data-datepicker-value]');
		return input ? (input.value || '') : '';
	}

	// Define valor em um datepicker programaticamente: atualiza hidden input + label visível.
	// O estado interno do componente só é re-sincronizado quando o usuário interage com o popover;
	// se ele não interagir, o valor pré-preenchido é o que vai para o backend.
	function dpSetValue(rootId, isoDate) {
		const root = qs(rootId);
		if (!root) return;
		const input = root.querySelector('[data-datepicker-value]');
		const labelEl = root.querySelector('[data-datepicker-label]');
		const placeholder = root.dataset.placeholder || 'Selecione uma data';
		if (input) input.value = isoDate || '';
		if (labelEl) {
			if (isoDate) {
				const m = /^(\d{4})-(\d{2})-(\d{2})$/.exec(isoDate);
				if (m) {
					labelEl.textContent = `${m[3]}/${m[2]}/${m[1]}`;
					labelEl.classList.remove('datepicker-trigger__label--placeholder');
				} else {
					labelEl.textContent = isoDate;
					labelEl.classList.remove('datepicker-trigger__label--placeholder');
				}
			} else {
				labelEl.textContent = placeholder;
				labelEl.classList.add('datepicker-trigger__label--placeholder');
			}
		}
	}

	function openDespesa(btn) {
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
		const permEl = qs('financeiro-perms');
		const canEdit = permEl && permEl.dataset.canEdit === '1';

		qs('despesaTitulo').textContent = data.descricao;
		qs('despesaBadges').innerHTML = buildBadges(data);

		const dl = qs('despesaDados');
		let html = '';
		html += '<dt>Valor Base</dt><dd>' + formatCurrency(data.valor) + '</dd>';
		html += '<dt>Dia Vencimento</dt><dd>' + data.dia + '</dd>';
		if (data.temporaria) {
			html += '<dt>Início</dt><dd>' + (data.inicio || '—') + '</dd>';
			html += '<dt>Término</dt><dd>' + (data.termino || '—') + '</dd>';
		}
		dl.innerHTML = html;

		const tbody = document.querySelector('#historicoTabela tbody');
		if (tbody) tbody.innerHTML = '';
		qs('historicoPagamentos').classList.add('hidden');

		const editButtons = qs('editButtons');
		if (canEdit) {
			editButtons.style.display = '';
			editButtons.dataset.name = data.name;
			prefillEditForm(data);
			cancelEditMode();
		} else {
			editButtons.style.display = 'none';
		}

		openDialog('modalDespesa');
		loadHistorico(data.name);
	}

	let loadingHistorico = false;

	function loadHistorico(contaName) {
		if (loadingHistorico) return;
		loadingHistorico = true;

		const wrap = qs('historicoPagamentos');
		const tabela = document.querySelector('#historicoTabela tbody');
		const vazio = qs('historicoVazio');

		wrap.classList.remove('hidden');
		vazio.textContent = 'Carregando…';
		vazio.classList.remove('hidden');
		tabela.innerHTML = '';

		frappe.call({
			method: 'gris.api.financeiro.conta_fixa.get_pagamentos_conta',
			args: { conta: contaName, limit: 12 },
			callback: r => {
				loadingHistorico = false;
				const dados = (r && r.message) || [];
				if (!dados.length) {
					vazio.textContent = 'Nenhum pagamento encontrado.';
					return;
				}
				vazio.classList.add('hidden');
				tabela.innerHTML = '';
				const frag = document.createDocumentFragment();
				dados.forEach(p => {
					const tr = document.createElement('tr');
					const slug = (p.status || '').toLowerCase().replace(/\s+/g, '');
					const badgeHtml = '<span class="badge ' + statusVariantClass(slug) + '">' + p.status + '</span>';
					tr.innerHTML =
						'<td class="whitespace-nowrap">' + (p.mes_format || p.mes_referencia || '') + '</td>' +
						'<td>' + badgeHtml + '</td>' +
						'<td>' + formatCurrency(p.valor) + '</td>';
					frag.appendChild(tr);
				});
				tabela.appendChild(frag);
			},
			error: () => { loadingHistorico = false; }
		});
	}

	function prefillEditForm(data) {
		const form = qs('despesaEditForm');
		form.descricao.value = data.descricao;
		form.valor.value = Number(data.valor || 0).toFixed(2);
		form.dia_vencimento.value = data.dia;
		qs('editAtiva').checked = !!data.ativa;
		qs('editTemporaria').checked = !!data.temporaria;
		dpSetValue('field_data_inicio', data.inicio || '');
		dpSetValue('field_data_termino', data.termino || '');
		toggleTemporariaDates();
	}

	function enableEditMode() {
		qs('despesaEditForm').classList.remove('hidden');
		qs('despesaDados').classList.add('hidden');
		const footer = qs('editButtons');
		footer.querySelector('[data-action="edit"]').classList.add('hidden');
		footer.querySelector('[data-action="save"]').classList.remove('hidden');
		footer.querySelector('[data-action="cancel-edit"]').classList.remove('hidden');
	}

	function cancelEditMode() {
		const footer = qs('editButtons');
		footer.querySelector('[data-action="edit"]').classList.remove('hidden');
		footer.querySelector('[data-action="save"]').classList.add('hidden');
		footer.querySelector('[data-action="cancel-edit"]').classList.add('hidden');
		qs('despesaEditForm').classList.add('hidden');
		qs('despesaDados').classList.remove('hidden');
	}

	function toggleTemporariaDates() {
		const box = qs('temporariaDatas');
		if (qs('editTemporaria').checked) box.classList.remove('hidden');
		else box.classList.add('hidden');
	}

	function saveEdits(btn) {
		const footer = qs('editButtons');
		const name = footer.dataset.name;
		const form = qs('despesaEditForm');
		if (!form.reportValidity()) return;
		const isTemp = qs('editTemporaria').checked;
		const inicio = dpGetValue('field_data_inicio');
		const termino = dpGetValue('field_data_termino');
		if (isTemp) {
			if (!inicio || !termino) {
				frappe.msgprint({ message: 'Preencha Início e Término para despesa temporária.', indicator: 'orange' });
				return;
			}
			if (inicio > termino) {
				frappe.msgprint({ message: 'Data de início não pode ser maior que a data de término.', indicator: 'red' });
				return;
			}
		}
		btn.disabled = true;
		btn.textContent = 'Salvando…';
		frappe.call({
			method: 'gris.api.financeiro.conta_fixa.update_conta_fixa',
			args: {
				name,
				descricao: form.descricao.value.trim(),
				valor: form.valor.value,
				dia_vencimento: form.dia_vencimento.value,
				ativa: qs('editAtiva').checked ? 1 : 0,
				despesa_temporaria: isTemp ? 1 : 0,
				data_inicio: isTemp ? inicio : '',
				data_termino: isTemp ? termino : ''
			},
			callback: r => {
				btn.disabled = false;
				btn.textContent = 'Salvar';
				if (r && r.message && r.message.ok) window.location.reload();
			},
			error: () => { btn.disabled = false; btn.textContent = 'Salvar'; }
		});
	}

	function showCreateModal() {
		const form = qs('novaDespesaForm');
		if (form) form.reset();
		const ativa = qs('novaAtiva'); if (ativa) ativa.checked = true;
		const temp = qs('novaTemporaria'); if (temp) temp.checked = false;
		const cobrar = qs('novaCobrarMesAtual'); if (cobrar) cobrar.checked = false;
		dpSetValue('nova_data_inicio', '');
		dpSetValue('nova_data_termino', '');
		toggleNovaTemporariaDates();
		openDialog('modalNovaDespesa');
	}

	function toggleNovaTemporariaDates() {
		const box = qs('novaTemporariaDatas');
		if (!box) return;
		if (qs('novaTemporaria').checked) box.classList.remove('hidden');
		else box.classList.add('hidden');
	}

	function saveNovaDespesa(btn) {
		const form = qs('novaDespesaForm');
		if (!form.reportValidity()) return;
		const isTemp = qs('novaTemporaria').checked;
		const inicio = dpGetValue('nova_data_inicio');
		const termino = dpGetValue('nova_data_termino');
		if (isTemp) {
			if (!inicio || !termino) {
				frappe.msgprint({ message: 'Preencha Início e Término para despesa temporária.', indicator: 'orange' });
				return;
			}
			if (inicio > termino) {
				frappe.msgprint({ message: 'Data de início não pode ser maior que a data de término.', indicator: 'red' });
				return;
			}
		}
		btn.disabled = true;
		btn.textContent = 'Salvando…';
		frappe.call({
			method: 'gris.api.financeiro.conta_fixa.create_conta_fixa',
			args: {
				descricao: form.descricao.value.trim(),
				valor: form.valor.value,
				dia_vencimento: form.dia_vencimento.value,
				ativa: qs('novaAtiva').checked ? 1 : 0,
				despesa_temporaria: isTemp ? 1 : 0,
				cobrar_mes_atual: qs('novaCobrarMesAtual').checked ? 1 : 0,
				data_inicio: isTemp ? inicio : '',
				data_termino: isTemp ? termino : ''
			},
			callback: r => {
				btn.disabled = false;
				btn.textContent = 'Salvar';
				if (r && r.message && r.message.ok) window.location.reload();
			},
			error: () => { btn.disabled = false; btn.textContent = 'Salvar'; }
		});
	}

	let initialized = false;
	function init() {
		if (initialized) return;
		initialized = true;

		document.querySelectorAll('.detalhes-conta-btn').forEach(btn => {
			btn.addEventListener('click', () => openDespesa(btn));
		});

		const novaBtn = qs('btnNovaDespesa');
		if (novaBtn) novaBtn.addEventListener('click', showCreateModal);

		const modalDespesa = qs('modalDespesa');
		if (modalDespesa) {
			const editTemp = qs('editTemporaria');
			if (editTemp) editTemp.addEventListener('change', toggleTemporariaDates);
			const editButtons = qs('editButtons');
			if (editButtons) {
				editButtons.querySelector('[data-action="edit"]').addEventListener('click', enableEditMode);
				editButtons.querySelector('[data-action="cancel-edit"]').addEventListener('click', cancelEditMode);
				editButtons.querySelector('[data-action="save"]').addEventListener('click', e => saveEdits(e.currentTarget));
			}
		}

		const modalNova = qs('modalNovaDespesa');
		if (modalNova) {
			const novaTemp = qs('novaTemporaria');
			if (novaTemp) novaTemp.addEventListener('change', toggleNovaTemporariaDates);
			const saveNovaBtn = modalNova.querySelector('[data-action="save-nova"]');
			if (saveNovaBtn) saveNovaBtn.addEventListener('click', e => saveNovaDespesa(e.currentTarget));
		}
	}

	if (document.readyState === 'loading') {
		document.addEventListener('DOMContentLoaded', init);
	} else {
		init();
	}
})();
