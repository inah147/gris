let assocAtual = null;

const TOAST_INDICATOR_TO_CATEGORY = {
	green: 'success',
	red: 'error',
	orange: 'warning',
	yellow: 'warning',
	blue: 'info',
};

function showToast(opts) {
	const message = typeof opts === 'string' ? opts : (opts.message || '');
	const indicator = (typeof opts === 'object' && opts.indicator) || 'blue';
	const category = TOAST_INDICATOR_TO_CATEGORY[indicator.toLowerCase()] || 'info';
	document.dispatchEvent(new CustomEvent('basecoat:toast', {
		detail: { config: { category, title: message, duration: 3000 } }
	}));
}

function getDialog() {
	return document.getElementById('detalheModal');
}

function getDialogTitle() {
	const dlg = getDialog();
	return dlg ? dlg.querySelector('h2#detalheModal-title') : null;
}

function formatarMoeda(valor) {
	const numero = parseFloat(valor || 0);
	if (isNaN(numero)) return '0,00';
	return numero.toLocaleString('pt-BR', { minimumFractionDigits: 2, maximumFractionDigits: 2 });
}

function badgeVariant(status) {
	switch (status) {
		case 'Cadastrar': return 'info';
		case 'Cancelar': return 'destructive';
		case 'Aguardar': return 'secondary';
		case 'Atrasado': return 'destructive';
		case 'Em Aberto': return 'warning';
		case 'Pago': return 'success';
		default: return 'secondary';
	}
}

function badgeClasses(status) {
	const variant = badgeVariant(status);
	if (variant === 'default' || variant === 'secondary') return 'badge';
	return 'badge badge-' + variant;
}

function mostrarDetalhes(btn) {
	const tr = btn.closest('tr');
	const data = JSON.parse((tr || btn).getAttribute('data-assoc'));
	assocAtual = data;

	const titulo = getDialogTitle();
	if (titulo) titulo.textContent = data.nome || 'Detalhes do beneficiário';

	const valorEl = document.getElementById('detalheValor');
	if (valorEl) valorEl.textContent = formatarMoeda(data.valor_contribuicao);

	const emailSpan = document.getElementById('emailCobranca');
	const foneSpan = document.getElementById('foneCobranca');
	if (emailSpan) emailSpan.textContent = data.email_cobranca || '—';
	if (foneSpan) foneSpan.textContent = data.telefone_cobranca || '—';

	const tbody = document.getElementById('detalhePagamentos');
	if (tbody) {
		tbody.innerHTML = '';
		(data.pagamentos || []).forEach(p => {
			const tr = document.createElement('tr');
			tr.setAttribute('data-pag-id', p.name || '');
			const valorFormatado = formatarMoeda(p.valor);
			let valorCell;
			if (p.status !== 'Pago' && window.canManageContrib) {
				valorCell = `<td class="text-right whitespace-nowrap"><div class="flex items-center justify-end gap-2"><span>R$ ${valorFormatado}</span><button type="button" class="btn-sm-primary" onclick="marcarComoPago(this)" data-pag-id="${p.name}">Pago</button></div></td>`;
			} else {
				valorCell = `<td class="text-right whitespace-nowrap">R$ ${valorFormatado}</td>`;
			}
			tr.innerHTML = `<td>${p.mes_de_referencia || ''}</td><td><span class="${badgeClasses(p.status)} status-badge">${p.status}</span></td>${valorCell}`;
			tbody.appendChild(tr);
		});
	}

	const cadastroContainer = document.getElementById('cadastroContainer');
	const tabelaPagamentosContainer = document.getElementById('tabelaPagamentosContainer');
	if (data.status_geral === 'Cadastrar') {
		if (cadastroContainer) cadastroContainer.classList.remove('hidden');
		if (tabelaPagamentosContainer) tabelaPagamentosContainer.classList.add('hidden');
	} else {
		if (cadastroContainer) cadastroContainer.classList.add('hidden');
		if (tabelaPagamentosContainer) tabelaPagamentosContainer.classList.remove('hidden');
	}

	const cancelarContainer = document.getElementById('cancelarContainer');
	if (cancelarContainer) {
		// Mostra "Cadastro Cancelado" para qualquer contribuição já cadastrada
		// (status_geral diferente de "Cadastrar"), permitindo desativar a cobrança.
		if (data.status_geral !== 'Cadastrar') {
			cancelarContainer.classList.remove('hidden');
		} else {
			cancelarContainer.classList.add('hidden');
		}
	}

	if (!window.canManageContrib) {
		document.querySelectorAll('[data-manage-only="1"]').forEach(el => el.classList.add('hidden'));
		const acoesValor = document.getElementById('acoesValor');
		if (acoesValor) acoesValor.innerHTML = '';
		const acoesCobranca = document.getElementById('acoesCobranca');
		if (acoesCobranca) acoesCobranca.innerHTML = '';
	}

	const dlg = getDialog();
	if (dlg && typeof dlg.showModal === 'function') {
		if (!dlg.open) dlg.showModal();
	}
}

function fecharDetalhes() {
	const dlg = getDialog();
	if (dlg && dlg.open) dlg.close();
}

function alterarValor() {
	if (!window.canManageContrib) { frappe.msgprint('Sem permissão para alterar valor.'); return; }
	if (!assocAtual) return;
	const container = document.getElementById('valorContainer');
	const acoes = document.getElementById('acoesValor');
	if (!container || !acoes) return;
	if (container.querySelector('input')) return;
	const valorAtual = assocAtual.valor_contribuicao || 0;
	container.innerHTML = `
		<div class="field">
			<label class="label" for="inputNovoValor">Novo valor (R$)</label>
			<input type="number" min="0" step="0.01" id="inputNovoValor" class="input" style="max-width:200px;" value="${valorAtual}" />
		</div>
	`;
	acoes.innerHTML = `
		<button type="button" class="btn-sm-primary" onclick="salvarNovoValor()">Salvar</button>
		<button type="button" class="btn-sm-outline" onclick="cancelarEdicaoValor()">Cancelar</button>
	`;
}

function cancelarEdicaoValor() {
	if (!assocAtual) return;
	const container = document.getElementById('valorContainer');
	const acoes = document.getElementById('acoesValor');
	if (container) {
		container.innerHTML = `<strong class="text-sm">Valor atual:</strong> <span class="text-sm">R$ <span id="detalheValor">${formatarMoeda(assocAtual.valor_contribuicao)}</span></span>`;
	}
	if (acoes) {
		acoes.innerHTML = `<button type="button" id="btnAlterarValor" class="btn-sm-outline" onclick="alterarValor()">Alterar Valor</button>`;
	}
}

function salvarNovoValor() {
	if (!assocAtual) return;
	const input = document.getElementById('inputNovoValor');
	if (!input) return;
	const novoValor = parseFloat(input.value);
	if (isNaN(novoValor) || novoValor < 0) {
		frappe.msgprint('Informe um valor válido.');
		return;
	}
	frappe.call({
		method: 'gris.api.financeiro.monthly_payments.update_contribution_value',
		args: { associate_id: assocAtual.id, new_value: novoValor },
		freeze: true,
		callback: function (r) {
			if (r.message && r.message.ok) {
				assocAtual.valor_contribuicao = r.message.valor;
				cancelarEdicaoValor();
				const detalheValor = document.getElementById('detalheValor');
				if (detalheValor) detalheValor.textContent = formatarMoeda(assocAtual.valor_contribuicao);
				showToast({ message: 'Valor atualizado', indicator: 'green' });
			}
		},
		error: function () { frappe.msgprint('Erro ao salvar valor.'); }
	});
}

if (document.readyState === 'loading') {
	document.addEventListener('DOMContentLoaded', () => { initStatusPagination(); });
} else {
	initStatusPagination();
}

function initStatusPagination() {
	document.querySelectorAll('.contrib-status-bloco').forEach(block => rebuildPaginationForBlock(block));
}

function rebuildPaginationForBlock(block) {
	if (!block) return;
	const pagContainer = block.querySelector('.contrib-status-pagination');
	if (pagContainer) pagContainer.innerHTML = '';
	const list = block.querySelector('.contrib-status-list');
	if (!list) return;
	const allRows = Array.from(list.querySelectorAll('tbody > tr.contrib-status-row'));
	const visibleRows = allRows.filter(r => !r.classList.contains('filter-hidden'));
	const countEl = block.querySelector('[data-status-count]');
	if (countEl) countEl.textContent = '(' + visibleRows.length + ')';

	allRows.forEach(r => r.classList.add('hidden-by-page'));
	visibleRows.forEach((r, idx) => {
		r.setAttribute('data-page', Math.floor(idx / 12) + 1);
	});
	if (visibleRows.length === 0) return;
	const pages = Math.ceil(visibleRows.length / 12);
	if (pages > 1) {
		renderPaginationControls(pagContainer, pages, 1, block.id);
		showStatusPage(block.id, 1);
	} else {
		visibleRows.forEach(r => r.classList.remove('hidden-by-page'));
		if (pagContainer) pagContainer.innerHTML = '';
	}
}

function renderPaginationControls(container, totalPages, current, statusBlockId) {
	if (!container) return;
	container.innerHTML = '';
	container.classList.add('btn-group');
	const addItem = (label, page, disabled = false, active = false) => {
		const btn = document.createElement('button');
		btn.type = 'button';
		btn.textContent = label;
		btn.className = active ? 'btn-sm-primary' : 'btn-sm-outline';
		if (active) btn.setAttribute('aria-current', 'page');
		if (disabled) {
			btn.disabled = true;
			btn.setAttribute('aria-disabled', 'true');
		}
		if (!disabled && !active) {
			btn.addEventListener('click', () => {
				showStatusPage(statusBlockId, page);
				renderPaginationControls(container, totalPages, page, statusBlockId);
			});
		}
		container.appendChild(btn);
	};
	addItem('«', 1, current === 1);
	addItem('‹', current - 1, current === 1);
	const windowSize = 5;
	let start = Math.max(1, current - Math.floor(windowSize / 2));
	let end = start + windowSize - 1;
	if (end > totalPages) {
		end = totalPages;
		start = Math.max(1, end - windowSize + 1);
	}
	for (let p = start; p <= end; p++) addItem(String(p), p, false, p === current);
	addItem('›', current + 1, current === totalPages);
	addItem('»', totalPages, current === totalPages);
}

function showStatusPage(statusBlockId, page) {
	const block = document.getElementById(statusBlockId);
	if (!block) return;
	const rows = block.querySelectorAll('.contrib-status-list tbody > tr.contrib-status-row');
	rows.forEach(r => {
		const p = parseInt(r.getAttribute('data-page'));
		if (p === page && !r.classList.contains('filter-hidden')) {
			r.classList.remove('hidden-by-page');
		} else {
			r.classList.add('hidden-by-page');
		}
	});
}

function aplicarFiltroAssociado() {
	const termo = (document.getElementById('filtroAssociado')?.value || '').trim().toLowerCase();
	document.querySelectorAll('.contrib-status-bloco').forEach(block => {
		const rows = block.querySelectorAll('.contrib-status-list tbody > tr.contrib-status-row');
		rows.forEach(row => {
			const nome = (row.getAttribute('data-nome') || '').toLowerCase();
			if (!termo || nome.includes(termo)) {
				row.classList.remove('filter-hidden');
			} else {
				row.classList.add('filter-hidden');
			}
		});
		rebuildPaginationForBlock(block);
	});
}

function marcarComoPago(btn) {
	if (!window.canManageContrib) { frappe.msgprint('Sem permissão para marcar pagamento.'); return; }
	const pagId = btn.getAttribute('data-pag-id');
	if (!pagId) return;
	frappe.call({
		method: 'gris.api.financeiro.monthly_payments.mark_payment_as_paid',
		args: { payment_id: pagId },
		freeze: true,
		callback: function (r) {
			if (r.message && r.message.ok) {
				const tr = btn.closest('tr');
				if (tr) {
					const badge = tr.querySelector('.status-badge');
					if (badge) {
						badge.textContent = 'Pago';
						badge.className = badgeClasses('Pago') + ' status-badge';
					}
					btn.remove();
				}
				showToast({ message: 'Pagamento marcado como Pago', indicator: 'green' });
			}
		},
		error: function () { frappe.msgprint('Erro ao marcar pagamento.'); }
	});
}

function cadastroRealizado() {
	if (!window.canManageContrib) { frappe.msgprint('Sem permissão.'); return; }
	if (!assocAtual) return;
	frappe.call({
		method: 'gris.api.financeiro.monthly_payments.activate_billing_status',
		args: { associate_id: assocAtual.id },
		freeze: true,
		callback: function (r) {
			if (r.message && r.message.ok) {
				assocAtual.status_cobranca = 'Ativo';
				const cadastroContainer = document.getElementById('cadastroContainer');
				if (cadastroContainer) cadastroContainer.classList.add('hidden');
				showToast({ message: 'Status de cobrança ativado', indicator: 'green' });
				fecharDetalhes();
			}
		},
		error: function () { frappe.msgprint('Erro ao atualizar status de cobrança.'); }
	});
}

function cadastroCancelado() {
	if (!window.canManageContrib) { frappe.msgprint('Sem permissão.'); return; }
	if (!assocAtual) return;
	frappe.call({
		method: 'gris.api.financeiro.monthly_payments.deactivate_billing_status',
		args: { associate_id: assocAtual.id },
		freeze: true,
		callback: function (r) {
			if (r.message && r.message.ok) {
				assocAtual.status_cobranca = 'Inativo';
				showToast({ message: 'Status de cobrança inativado', indicator: 'orange' });
				fecharDetalhes();
			}
		},
		error: function () { frappe.msgprint('Erro ao inativar status de cobrança.'); }
	});
}

function editarCobranca() {
	if (!window.canManageContrib) { frappe.msgprint('Sem permissão para editar.'); return; }
	if (!assocAtual) return;
	const container = document.getElementById('cobrancaContainer');
	const acoes = document.getElementById('acoesCobranca');
	if (!container || !acoes) return;
	if (container.querySelector('input')) return;
	const email = assocAtual.email_cobranca || '';
	const fone = assocAtual.telefone_cobranca || '';
	const emailWrapper = container.querySelector('#emailCobranca');
	const foneWrapper = container.querySelector('#foneCobranca');
	if (emailWrapper) {
		emailWrapper.outerHTML = `
			<span id="emailCobranca" class="block">
				<div class="field">
					<label class="label" for="inputEmailCobranca">E-mail</label>
					<input type="email" id="inputEmailCobranca" class="input" style="max-width:300px;" value="${email}" placeholder="email@exemplo.com" />
				</div>
			</span>
		`;
	}
	if (foneWrapper) {
		foneWrapper.outerHTML = `
			<span id="foneCobranca" class="block">
				<div class="field">
					<label class="label" for="inputFoneCobranca">Telefone</label>
					<input type="text" id="inputFoneCobranca" class="input" style="max-width:200px;" value="${fone}" placeholder="(xx) xxxxx-xxxx" />
				</div>
			</span>
		`;
	}
	acoes.innerHTML = `
		<button type="button" class="btn-sm-primary" onclick="salvarDadosCobranca()">Salvar</button>
		<button type="button" class="btn-sm-outline" onclick="cancelarEdicaoCobranca()">Cancelar</button>
	`;
}

function cancelarEdicaoCobranca() {
	if (!assocAtual) return;
	const container = document.getElementById('cobrancaContainer');
	if (!container) return;
	const emailWrapper = container.querySelector('#emailCobranca');
	const foneWrapper = container.querySelector('#foneCobranca');
	if (emailWrapper) {
		emailWrapper.outerHTML = `<span id="emailCobranca">${assocAtual.email_cobranca || '—'}</span>`;
	}
	if (foneWrapper) {
		foneWrapper.outerHTML = `<span id="foneCobranca">${assocAtual.telefone_cobranca || '—'}</span>`;
	}
	const acoes = document.getElementById('acoesCobranca');
	if (acoes) {
		acoes.innerHTML = `<button type="button" id="btnEditarCobranca" class="btn-sm-outline" onclick="editarCobranca()">Editar Cobrança</button>`;
	}
}

function salvarDadosCobranca() {
	if (!window.canManageContrib) { frappe.msgprint('Sem permissão para salvar.'); return; }
	if (!assocAtual) return;
	const emailInput = document.getElementById('inputEmailCobranca');
	const foneInput = document.getElementById('inputFoneCobranca');
	const email = emailInput ? emailInput.value.trim() : '';
	const phone = foneInput ? foneInput.value.trim() : '';
	frappe.call({
		method: 'gris.api.financeiro.monthly_payments.update_billing_contacts',
		args: { associate_id: assocAtual.id, email: email, phone: phone },
		freeze: true,
		callback: function (r) {
			if (r.message && r.message.ok) {
				assocAtual.email_cobranca = r.message.email;
				assocAtual.telefone_cobranca = r.message.phone;
				cancelarEdicaoCobranca();
				showToast({ message: 'Dados de cobrança atualizados', indicator: 'green' });
			}
		},
		error: function () { frappe.msgprint('Erro ao salvar dados de cobrança.'); }
	});
}
