// Página /financeiro/pareceres — interações com modais HTML5 <dialog>
(function () {
	'use strict';

	function q(id) { return document.getElementById(id); }

	function openDialog(id) {
		const dlg = q(id);
		if (dlg && typeof dlg.showModal === 'function' && !dlg.open) dlg.showModal();
	}

	function closeDialog(id) {
		const dlg = q(id);
		if (dlg && dlg.open) dlg.close();
	}

	// Componente select do design system tem o id na div externa e um <input name="..."> escondido
	// dentro com o valor selecionado. Esta função lê o valor independentemente do tipo.
	function selectValue(id) {
		const root = q(id);
		if (!root) return '';
		if (root.tagName === 'SELECT' || root.tagName === 'INPUT') return root.value || '';
		const input = root.querySelector('input[name]');
		return input ? (input.value || '') : '';
	}

	function onSelectChange(id, handler) {
		const root = q(id);
		if (!root) return;
		// Tanto o evento change do <select> nativo quanto o evento custom do basecoat select
		// borbulham (bubble); um listener em qualquer ponto do componente captura ambos.
		root.addEventListener('change', () => handler(selectValue(id)));
	}

	window.closeParecerModal = function () { closeDialog('parecerDetailModal'); };

	function populateAndOpen(card) {
		const tipo = card.dataset.tipo || 'Parecer';
		const ano = card.dataset.ano || '—';
		const trimestre = card.dataset.trimestre || '';
		const area = card.dataset.area || '—';
		const published = card.dataset.published === '1';
		const file = card.dataset.file || '';
		const name = card.dataset.name || '';

		const titleEl = q('parecerModalTitle');
		if (titleEl) titleEl.textContent = tipo;
		const subtitleEl = q('parecerModalSubtitle');
		if (subtitleEl) subtitleEl.textContent = card.dataset.period || '';

		const badgeWrap = q('parecerModalBadge');
		if (badgeWrap) {
			const variant = published ? 'badge-success' : 'badge-secondary';
			badgeWrap.innerHTML = '<span class="badge ' + variant + '">' + (published ? 'Publicado' : 'Rascunho') + '</span>';
		}

		q('parecerModalAno').textContent = ano || '—';
		if (tipo === 'Parecer trimestral da comissão fiscal') {
			q('parecerModalTrimestreRow').classList.remove('hidden');
			q('parecerModalTrimestre').textContent = trimestre || '—';
		} else {
			q('parecerModalTrimestreRow').classList.add('hidden');
		}
		q('parecerModalArea').textContent = area || '—';

		const fileBtn = q('parecerModalFileBtn');
		if (file) {
			let href = file;
			if (!(href.startsWith('/files') || href.startsWith('/private/files') || href.startsWith('http'))) {
				href = '/files/' + href;
			}
			fileBtn.href = href;
			fileBtn.style.display = '';
		} else {
			fileBtn.removeAttribute('href');
			fileBtn.style.display = 'none';
		}

		const publishBtn = q('parecerPublishBtn');
		const unpublishBtn = q('parecerUnpublishBtn');
		const deleteBtn = q('parecerDeleteBtn');
		if (publishBtn && unpublishBtn && deleteBtn) {
			publishBtn.dataset.docname = name;
			unpublishBtn.dataset.docname = name;
			deleteBtn.dataset.docname = name;
			if (published) {
				publishBtn.classList.add('hidden');
				unpublishBtn.classList.remove('hidden');
			} else {
				publishBtn.classList.remove('hidden');
				unpublishBtn.classList.add('hidden');
			}
			deleteBtn.classList.remove('hidden');
		}

		openDialog('parecerDetailModal');
	}

	document.addEventListener('click', function (e) {
		const detailsBtn = e.target.closest('.parecer-details-btn');
		if (detailsBtn) {
			const card = detailsBtn.closest('.parecer-card');
			if (card) populateAndOpen(card);
			return;
		}

		const publishBtn = e.target.closest('#parecerPublishBtn');
		const unpublishBtn = e.target.closest('#parecerUnpublishBtn');
		if (publishBtn || unpublishBtn) {
			const target = publishBtn || unpublishBtn;
			const isPublish = target.id === 'parecerPublishBtn';
			const docname = target.dataset.docname;
			if (!docname) return;
			target.disabled = true;
			frappe.call({
				method: 'frappe.client.set_value',
				args: { doctype: 'Transparencia', name: docname, fieldname: { publicado: isPublish ? 1 : 0 } },
				callback: function (r) {
					target.disabled = false;
					if (!r.exc) {
						frappe.show_alert({ message: isPublish ? 'Publicado' : 'Despublicado', indicator: isPublish ? 'green' : 'orange' });
						const card = document.querySelector('.parecer-card[data-name="' + docname + '"]');
						if (card) {
							card.dataset.published = isPublish ? '1' : '0';
							populateAndOpen(card);
						}
					}
				}
			});
			return;
		}

		const deleteBtn = e.target.closest('#parecerDeleteBtn');
		if (deleteBtn) {
			const docname = deleteBtn.dataset.docname;
			if (!docname) return;
			if (!confirm('Apagar este parecer? Essa ação não pode ser desfeita.')) return;
			deleteBtn.disabled = true;
			frappe.call({
				method: 'frappe.client.delete',
				args: { doctype: 'Transparencia', name: docname },
				callback: function (r) {
					deleteBtn.disabled = false;
					if (!r.exc) {
						frappe.show_alert({ message: 'Parecer apagado', indicator: 'red' });
						const card = document.querySelector('.parecer-card[data-name="' + docname + '"]');
						if (card) card.remove();
						closeDialog('parecerDetailModal');
					}
				}
			});
			return;
		}

		if (e.target.closest('#addParecerBtn')) {
			openDialog('parecerAddModal');
			return;
		}

		if (e.target.closest('#addParecerSaveBtn')) {
			saveNewParecer(e.target.closest('#addParecerSaveBtn'));
			return;
		}

	});

	// Captura o sucesso do componente file_upload do design system
	document.addEventListener('gris:file-upload:success', function (e) {
		const root = e.target;
		if (!root || root.id !== 'addParecerArquivoUpload') return;
		const file = (e.detail && e.detail.files && e.detail.files[0]) || null;
		if (file) window._parecerFileData = file;
	});

	function applyYearFilter(year) {
		document.querySelectorAll('.parecer-card').forEach(function (card) {
			const cardYear = card.dataset.ano || '';
			const visible = !year || cardYear === year;
			card.classList.toggle('hidden', !visible);
		});
	}

	async function saveNewParecer(btn) {
		const tipo = selectValue('addParecerTipo');
		const ano = q('addParecerAno').value;
		const trimestreWrapper = q('addParecerTrimestreGroup');
		const trimestre = !trimestreWrapper.classList.contains('hidden') ? selectValue('addParecerTrimestre') : '';
		if (!tipo || !ano || (tipo === 'trimestral' && !trimestre) || !window._parecerFileData) {
			frappe.show_alert({ message: 'Preencha os campos obrigatórios', indicator: 'orange' });
			return;
		}
		btn.disabled = true;
		btn.textContent = 'Salvando...';
		const tipoArquivo = tipo === 'trimestral' ? 'Parecer trimestral da comissão fiscal' : 'Parecer anual da comissão fiscal';
		try {
			const docPayload = {
				doctype: 'Transparencia',
				tipo_arquivo: tipoArquivo,
				ano_referencia: parseInt(ano, 10),
				area: 'Financeiro'
			};
			if (tipo === 'trimestral') docPayload.trimestre_referencia = parseInt(trimestre, 10);
			if (window._parecerFileData && window._parecerFileData.file_url) {
				docPayload.arquivo = window._parecerFileData.file_url;
			}
			const insertRes = await frappe.call({ method: 'frappe.client.insert', args: { doc: docPayload } });
			if (insertRes.exc) throw insertRes.exc;
			frappe.show_alert({ message: 'Parecer criado', indicator: 'green' });
			closeDialog('parecerAddModal');
			setTimeout(() => window.location.reload(), 600);
		} catch (err) {
			console.error(err);
			frappe.show_alert({ message: 'Erro ao salvar', indicator: 'red' });
		} finally {
			btn.disabled = false;
			btn.textContent = 'Salvar Parecer';
		}
	}

	// Wire up handlers on first load
	function init() {
		onSelectChange('parecerYearFilter', applyYearFilter);
		onSelectChange('addParecerTipo', function (val) {
			const group = q('addParecerTrimestreGroup');
			if (!group) return;
			if (val === 'trimestral') group.classList.remove('hidden');
			else group.classList.add('hidden');
		});
	}

	if (document.readyState === 'loading') {
		document.addEventListener('DOMContentLoaded', init);
	} else {
		init();
	}
})();
