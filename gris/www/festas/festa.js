(function () {
	"use strict";

	const { name: festaName, canEdit, associadosItems, responsaveisItems } = window._festaData;
	let cenarioSimulacao = window._festaData.cenarioSimulacao || "Intermediário";
	let areas = window._festaData.areas.slice();
	let barracas = window._festaData.barracas.slice();
	let produtos = (window._festaData.produtos || []).slice();
	let compras = (window._festaData.compras || []).slice();
	let contratacoes = (window._festaData.contratacoes || []).slice();
	let barracasItems = window._festaData.barracasItems || [];
	let areasItems = window._festaData.areasItems || [];
	let areasItemsObrigatorio = areasItems.filter(function (it) { return it.value; });
	let produtosItems = window._festaData.produtosItems || [];
	let unidadesItems = window._festaData.unidadesItems || [];
	let compraDraftCotacoes = [];
	let compraDraftUsos = [];
	let contratacaoDraftCotacoes = [];

	// ─── Toast helper ───────────────────────────────────────────────────────────

	function toast(message, category) {
		document.dispatchEvent(
			new CustomEvent("basecoat:toast", {
				detail: { config: { category: category || "info", description: message, duration: 3500 } },
			})
		);
	}

	// ─── API helper ─────────────────────────────────────────────────────────────

	function api(method, args) {
		return new Promise(function (resolve, reject) {
			frappe.call({
				method: method,
				args: args,
				callback: function (r) {
					if (r && r.message) resolve(r.message);
					else reject(new Error("Resposta inesperada do servidor."));
				},
				error: function (err) {
					reject(err);
				},
			});
		});
	}

	// ─── Confirm dialog helper ──────────────────────────────────────────────────

	function confirmDialog(opts) {
		opts = opts || {};
		return new Promise(function (resolve) {
			var dlg = document.getElementById("confirm-dialog");
			if (!dlg || typeof dlg.showModal !== "function") {
				resolve(window.confirm(opts.message || opts.title || "Confirmar?"));
				return;
			}
			var titleEl = dlg.querySelector("header h2");
			var messageEl = dlg.querySelector("#confirm-dialog-message");
			var okBtn = dlg.querySelector("#confirm-dialog-ok");
			var cancelBtn = dlg.querySelector("#confirm-dialog-cancel");
			if (titleEl) titleEl.textContent = opts.title || "Confirmar ação";
			if (messageEl) messageEl.textContent = opts.message || "Tem certeza?";
			if (okBtn) {
				okBtn.textContent = opts.confirmLabel || "Confirmar";
				okBtn.className = opts.variant === "primary" ? "btn-primary" : "btn-destructive";
			}

			function cleanup() {
				if (okBtn) okBtn.removeEventListener("click", onOk);
				if (cancelBtn) cancelBtn.removeEventListener("click", onCancel);
				dlg.removeEventListener("close", onClose);
			}
			function onOk() {
				cleanup();
				dlg.close("confirm");
				resolve(true);
			}
			function onCancel() {
				cleanup();
				dlg.close("cancel");
				resolve(false);
			}
			function onClose() {
				cleanup();
				if (dlg.returnValue !== "confirm") resolve(false);
			}
			if (okBtn) okBtn.addEventListener("click", onOk);
			if (cancelBtn) cancelBtn.addEventListener("click", onCancel);
			dlg.addEventListener("close", onClose);
			dlg.showModal();
		});
	}

	// ─── Sortable table helpers ─────────────────────────────────────────────────

	function sortHeaderHtml(label, opts) {
		opts = opts || {};
		var attrs = "";
		if (opts.sortType) attrs += ' data-sort-type="' + opts.sortType + '"';
		return '<th data-sortable' + attrs + '>'
			+ '<button type="button" class="table-sort-trigger">'
			+ escHtml(label)
			+ '<svg class="table-sort-icon ds-lucide ds-lucide--xs" viewBox="0 0 24 24" aria-hidden="true">'
			+ '<use href="/assets/gris/design_system/icons/lucide/sprite.svg#chevrons-up-down"></use>'
			+ '</svg>'
			+ '</button>'
			+ '</th>';
	}

	function buildSortableTable(headers, bodyHtml) {
		var ths = headers.map(function (h) {
			if (h.sortable === false) return '<th>' + (h.label || "") + '</th>';
			return sortHeaderHtml(h.label || "", { sortType: h.sortType });
		}).join("");
		return '<div class="festa-table-scroll">'
			+ '<table class="festa-table" data-table-sortable>'
			+ '<thead><tr>' + ths + '</tr></thead>'
			+ '<tbody>' + bodyHtml + '</tbody>'
			+ '</table>'
			+ '</div>';
	}

	function notifyDesignSystem() {
		document.dispatchEvent(new CustomEvent("gris:design-system:init"));
		if (window.basecoat && typeof window.basecoat.init === "function") {
			window.basecoat.init("table-sortable");
			window.basecoat.init("select");
		}
		initActionPopovers();
	}

	// ─── Refresh global após mutações ───────────────────────────────────────────

	function refreshSelectOptions(id, items, selectedValue) {
		var el = document.getElementById(id);
		if (!el) return;
		var listbox = el.querySelector("[role='listbox']");
		if (!listbox) return;
		listbox.innerHTML = items.map(function (item, idx) {
			var value = item.value == null ? "" : String(item.value);
			var sel = value === String(selectedValue || "") ? ' aria-selected="true"' : "";
			return '<div id="' + id + '-items-' + idx + '" role="option" data-value="' + escHtml(value) + '"' + sel + '>' + escHtml(item.label || value) + '</div>';
		}).join("");
		var hidden = el.querySelector(":scope > input[type='hidden']");
		var span = el.querySelector(":scope > button span.truncate");
		var currentValue = hidden ? hidden.value : "";
		if (currentValue) {
			var label = selectLabelFor(items, currentValue, "");
			if (span && label) span.textContent = label;
		}
	}

	function refreshAllDependentSelects() {
		refreshSelectOptions("add-produto-barraca", barracasItems);
		refreshSelectOptions("edit-produto-barraca", barracasItems);
		refreshSelectOptions("compra-area", areasItems);
		refreshSelectOptions("contratacao-area", areasItems);
		refreshSelectOptions("add-barraca-area", areasItemsObrigatorio);
		refreshSelectOptions("edit-barraca-area", areasItemsObrigatorio);
	}

	let refreshInFlight = null;
	function refreshFestaData() {
		if (refreshInFlight) return refreshInFlight;
		refreshInFlight = api("gris.www.festas.festa.get_festa_payload", { festa_name: festaName })
			.then(function (payload) {
				if (!payload) return;
				areas = payload.areas || [];
				barracas = payload.barracas || [];
				produtos = payload.produtos || [];
				compras = payload.compras || [];
				contratacoes = payload.contratacoes || [];
				barracasItems = payload.barracas_items || [];
				areasItems = payload.areas_items || [];
				areasItemsObrigatorio = payload.areas_items_obrigatorio || [];
				produtosItems = payload.produtos_items || [];
				unidadesItems = payload.unidades_items || unidadesItems;
				cenarioSimulacao = payload.cenario_simulacao || cenarioSimulacao;

				window._festaData.areas = areas;
				window._festaData.barracas = barracas;
				window._festaData.produtos = produtos;
				window._festaData.compras = compras;
				window._festaData.contratacoes = contratacoes;
				window._festaData.barracasItems = barracasItems;
				window._festaData.areasItems = areasItems;
				window._festaData.produtosItems = produtosItems;
				window._festaData.unidadesItems = unidadesItems;
				window._festaData.cenarioSimulacao = cenarioSimulacao;
				window._festaData.publicoMin = payload.expectativa_min || 0;
				window._festaData.publicoIntermediario = payload.expectativa_intermediario || 0;
				window._festaData.publicoMax = payload.expectativa_max || 0;
				window._festaData.totais = payload.totais || {};
				window._festaData.receitasPorArea = payload.receitas_por_area || [];
				window._festaData.despesasPorArea = payload.despesas_por_area || [];
				window._festaData.receitasPorBarraca = payload.receitas_por_barraca || [];
				window._festaData.despesasPorBarraca = payload.despesas_por_barraca || [];
				window._festaData.precoMinConvite = payload.preco_min_convite || 0;
				window._festaData.precoSugeridoConvite = payload.preco_sugerido_convite || 0;
				window._festaData.precoConvite = payload.preco_convite || 0;
				window._festaData.margemSeguranca = payload.margem_seguranca || 0;

				renderAreasTable();
				renderBarracasTable();
				renderProdutosTable();
				renderComprasTable();
				renderContratacoesTable();
				renderOrcamentoTab();
				var precoMin = document.getElementById("preco-min-convite");
				var precoSug = document.getElementById("preco-sugerido-convite");
				if (precoMin) precoMin.value = fmtCurrency(window._festaData.precoMinConvite);
				if (precoSug) precoSug.value = fmtCurrency(window._festaData.precoSugeridoConvite);
				refreshAllDependentSelects();
				notifyDesignSystem();
			})
			.catch(function (err) {
				console.error("refreshFestaData", err);
			})
			.finally(function () {
				refreshInFlight = null;
			});
		return refreshInFlight;
	}

	// ─── Coord type picker (shared logic) ───────────────────────────────────────

	function setupCoordPicker(tipoSelectId, pickerIds) {
		const tipoEl = document.getElementById(tipoSelectId);
		if (!tipoEl) return;

		function updateVisibility() {
			const tipo = getSelectValue(tipoSelectId);
			Object.keys(pickerIds).forEach(function (key) {
				const el = document.getElementById(pickerIds[key]);
				if (el) el.hidden = key !== tipo;
			});
		}

		tipoEl.addEventListener("change", updateVisibility);
		updateVisibility();
	}

	// ─── Basecoat select helpers ─────────────────────────────────────────────────

	function getSelectValue(id) {
		const el = document.getElementById(id);
		if (!el) return "";
		const input = el.querySelector(":scope > input[type='hidden']");
		return input ? input.value : "";
	}

	function setSelectValue(id, value, label) {
		const el = document.getElementById(id);
		if (!el) return;
		const input = el.querySelector(":scope > input[type='hidden']");
		const span = el.querySelector(":scope > button span.truncate");
		if (input) input.value = value;
		if (span) span.textContent = label || "";
		el.querySelectorAll("[role='option']").forEach(function (opt) {
			const v = opt.dataset.value !== undefined ? opt.dataset.value : opt.textContent.trim();
			opt.setAttribute("aria-selected", v === value ? "true" : "false");
		});
	}

	// ─── Action popover — top-layer para escapar overflow clip ────────────────

	function initActionPopovers() {
		var hasPopoverAPI = "popover" in HTMLElement.prototype;
		document.querySelectorAll(".festa-popover-menu").forEach(function (content) {
			if (content._festaPopInit) return;
			content._festaPopInit = true;
			var comp = content.closest(".popover");
			var trigger = comp && comp.querySelector(":scope > button");
			if (!trigger) return;
			if (hasPopoverAPI) content.setAttribute("popover", "manual");
			new MutationObserver(function () {
				if (content.getAttribute("aria-hidden") === "false") {
					var r = trigger.getBoundingClientRect();
					content.style.cssText = "position:fixed;margin:0;inset:auto;"
						+ "top:" + (r.bottom + 4) + "px;"
						+ "right:" + (window.innerWidth - r.right) + "px;";
					if (hasPopoverAPI) try { content.showPopover(); } catch (_e) {}
				} else {
					content.style.cssText = "";
					if (hasPopoverAPI) try { content.hidePopover(); } catch (_e) {}
				}
			}).observe(content, { attributes: true, attributeFilter: ["aria-hidden"] });
		});
	}

	function selectLabelFor(items, value, fallback) {
		for (var i = 0; i < items.length; i++) {
			if (items[i].value === value) return items[i].label || fallback || "";
		}
		return fallback || value || "";
	}

	function renderNativeSelect(dataField, items, selectedValue, extraClass) {
		var opts = items.map(function (item) {
			var value = item.value === undefined || item.value === null ? "" : String(item.value);
			var selected = value === String(selectedValue || "") ? " selected" : "";
			return '<option value="' + escHtml(value) + '"' + selected + ">" + escHtml(item.label || value) + "</option>";
		}).join("");
		var cls = "select" + (extraClass ? " " + extraClass : "");
		return '<select class="' + cls + '" data-field="' + escHtml(dataField) + '">' + opts + "</select>";
	}

	// ─── Equipe form helpers ─────────────────────────────────────────────────────

	function updateEqPickers(renderPrefix, tipo) {
		const short = renderPrefix.replace("edit-", "");
		const resp = document.getElementById("eq-" + short + "-picker-responsavel");
		const assoc = document.getElementById("eq-" + short + "-picker-associado");
		const outro = document.getElementById("eq-" + short + "-picker-outro");
		if (resp) resp.hidden = tipo !== "Responsavel";
		if (assoc) assoc.hidden = tipo !== "Associado";
		if (outro) outro.hidden = tipo !== "Outro";
	}

	function openEquipeForm(renderPrefix, equipe, container, editIdx) {
		const short = renderPrefix.replace("edit-", "");
		const popoverEl = document.getElementById("eq-" + short + "-popover");
		const trigger = document.getElementById("btn-add-" + short + "-membro");
		const content = document.getElementById("eq-" + short + "-form-popover");
		if (!popoverEl || !trigger || !content) return;

		popoverEl._editEquipe = equipe;
		popoverEl._container = container;
		popoverEl._renderPrefix = renderPrefix;
		popoverEl.dataset.editIdx = editIdx;

		const m = editIdx >= 0 ? equipe[editIdx] : null;
		const tipo = m ? (m.tipo_pessoa || "Outro") : "Outro";
		const tipoLabel = tipo === "Responsavel" ? "Respons\u00e1vel" : tipo === "Associado" ? "Associado" : "Outro";

		setSelectValue("eq-" + short + "-tipo", tipo, tipoLabel);
		updateEqPickers(renderPrefix, tipo);

		if (tipo === "Responsavel") {
			setSelectValue("eq-" + short + "-select-responsavel", m.responsavel || "", m.nome || "");
			var eEmailEl = document.getElementById("eq-" + short + "-resp-email");
			var eTelEl = document.getElementById("eq-" + short + "-resp-telefone");
			if (eEmailEl) eEmailEl.value = m.email || "";
			if (eTelEl) eTelEl.value = m.telefone || "";
		} else if (tipo === "Associado") {
			setSelectValue("eq-" + short + "-select-associado", m.associado || "", m.nome || "");
			var eEmailEl = document.getElementById("eq-" + short + "-assoc-email");
			var eTelEl = document.getElementById("eq-" + short + "-assoc-telefone");
			if (eEmailEl) eEmailEl.value = m.email || "";
			if (eTelEl) eTelEl.value = m.telefone || "";
		} else {
			const nomeEl = document.getElementById("eq-" + short + "-outro-nome");
			const emailEl = document.getElementById("eq-" + short + "-outro-email");
			const telEl = document.getElementById("eq-" + short + "-outro-telefone");
			if (nomeEl) nomeEl.value = m ? (m.nome || "") : "";
			if (emailEl) emailEl.value = m ? (m.email || "") : "";
			if (telEl) telEl.value = m ? (m.telefone || "") : "";
		}

		const funcaoEl = document.getElementById("eq-" + short + "-funcao");
		if (funcaoEl) funcaoEl.value = m ? (m.funcao || "") : "";

		// Open popover
		trigger.setAttribute("aria-expanded", "true");
		content.setAttribute("aria-hidden", "false");
	}

	function closeEquipeForm(renderPrefix) {
		const short = renderPrefix.replace("edit-", "");
		const trigger = document.getElementById("btn-add-" + short + "-membro");
		const content = document.getElementById("eq-" + short + "-form-popover");
		// Move focus to trigger before hiding to avoid aria-hidden-with-focus warning
		if (trigger && content && content.contains(document.activeElement)) {
			trigger.focus();
		}
		if (trigger) trigger.setAttribute("aria-expanded", "false");
		if (content) content.setAttribute("aria-hidden", "true");
	}

	function confirmEquipeForm(renderPrefix) {
		const short = renderPrefix.replace("edit-", "");
		const popoverEl = document.getElementById("eq-" + short + "-popover");
		if (!popoverEl) return;

		const equipe = popoverEl._editEquipe;
		const container = popoverEl._container;
		const editIdx = parseInt(popoverEl.dataset.editIdx, 10);
		const tipo = getSelectValue("eq-" + short + "-tipo") || "Outro";

		let nome = "";
		let email = "";
		let telefone = "";
		let linkedValue = "";

		if (tipo === "Responsavel") {
			linkedValue = getSelectValue("eq-" + short + "-select-responsavel");
			if (!linkedValue) { toast("Selecione o respons\u00e1vel.", "error"); return; }
			const sel = document.getElementById("eq-" + short + "-select-responsavel");
			nome = sel ? sel.querySelector(":scope > button span.truncate").textContent.trim() : linkedValue;
			email = (document.getElementById("eq-" + short + "-resp-email") || {}).value || "";
			telefone = (document.getElementById("eq-" + short + "-resp-telefone") || {}).value || "";
		} else if (tipo === "Associado") {
			linkedValue = getSelectValue("eq-" + short + "-select-associado");
			if (!linkedValue) { toast("Selecione o associado.", "error"); return; }
			const sel = document.getElementById("eq-" + short + "-select-associado");
			nome = sel ? sel.querySelector(":scope > button span.truncate").textContent.trim() : linkedValue;
			email = (document.getElementById("eq-" + short + "-assoc-email") || {}).value || "";
			telefone = (document.getElementById("eq-" + short + "-assoc-telefone") || {}).value || "";
		} else {
			nome = (document.getElementById("eq-" + short + "-outro-nome").value || "").trim();
			email = (document.getElementById("eq-" + short + "-outro-email").value || "").trim();
			telefone = (document.getElementById("eq-" + short + "-outro-telefone").value || "").trim();
			if (!nome) { toast("Informe o nome do membro.", "error"); return; }
		}

		const funcao = (document.getElementById("eq-" + short + "-funcao").value || "").trim();

		const membro = {
			tipo_pessoa: tipo,
			nome: nome,
			email: email,
			telefone: telefone,
			funcao: funcao,
			responsavel: tipo === "Responsavel" ? linkedValue : "",
			associado: tipo === "Associado" ? linkedValue : "",
		};

		if (editIdx >= 0) {
			equipe[editIdx] = membro;
		} else {
			equipe.push(membro);
		}

		renderEquipeTable(container, equipe, renderPrefix);
		closeEquipeForm(renderPrefix);
	}

	function escHtml(str) {
		return String(str || "")
			.replace(/&/g, "&amp;")
			.replace(/</g, "&lt;")
			.replace(/>/g, "&gt;")
			.replace(/"/g, "&quot;");
	}

	// ─── Equipe table ───────────────────────────────────────────────────────────

	function renderEquipeTable(container, equipe, prefix) {
		if (!equipe || !equipe.length) {
			container.innerHTML =
				'<p class="text-sm text-muted-foreground festa-equipe-empty">Nenhum membro adicionado.</p>';
			return;
		}

		const rows = equipe
			.map(function (m, i) {
				return `
<tr data-equipe-idx="${i}">
	<td>${escHtml(m.nome || "—")}</td>
	<td>${escHtml(m.email || "—")}</td>
	<td>${escHtml(m.telefone || "—")}</td>
	<td>${escHtml(m.funcao || "—")}</td>
	<td class="festa-table-actions">
		<div class="popover" id="${prefix}-equipe-pop-${i}">
			<button type="button" class="btn-sm-ghost festa-actions-btn" aria-expanded="false" aria-controls="${prefix}-equipe-pop-${i}-popover">…</button>
			<div id="${prefix}-equipe-pop-${i}-popover" data-popover aria-hidden="true" class="festa-popover-menu">
				<button type="button" class="festa-popover-item" data-equipe-action="edit" data-equipe-idx="${i}">Editar</button>
				<button type="button" class="festa-popover-item festa-popover-item--destructive" data-equipe-action="delete" data-equipe-idx="${i}">Apagar</button>
			</div>
		</div>
	</td>
</tr>`;
			})
			.join("");

		container.innerHTML = `
<div class="festa-equipe-scroll"><table class="festa-table">
	<thead>
		<tr>
			<th>Nome</th>
			<th>E-mail</th>
			<th>Telefone</th>
			<th>Função</th>
			<th></th>
		</tr>
	</thead>
	<tbody>${rows}</tbody>
</table></div>`;

		document.dispatchEvent(new CustomEvent("gris:design-system:init"));

		container.querySelectorAll("[data-equipe-action]").forEach(function (btn) {
			btn.addEventListener("click", function () {
				const idx = parseInt(btn.dataset.equipeIdx, 10);
				const action = btn.dataset.equipeAction;

				// Close popover
				const pop = document.getElementById(`${prefix}-equipe-pop-${idx}`);
				if (pop) {
					const trigger = pop.querySelector("[aria-expanded]");
					if (trigger) trigger.setAttribute("aria-expanded", "false");
					const popover = pop.querySelector("[data-popover]");
					if (popover) popover.setAttribute("aria-hidden", "true");
				}

				if (action === "edit") {
					openEquipeForm(prefix, equipe, container, idx);
				} else if (action === "delete") {
					equipe.splice(idx, 1);
					renderEquipeTable(container, equipe, prefix);
				}
			});
		});
	}

	// ─── Áreas table ────────────────────────────────────────────────────────────

	function renderAreasTable() {
		const container = document.getElementById("areas-table-container");
		if (!container) return;

		if (!areas.length) {
			container.innerHTML = `
<section class="empty">
	<div class="empty-media">
		<img src="/assets/gris/images/gris-character/gris-search.png" alt="Personagem Gris procurando" class="empty-image empty-image--sm" loading="lazy" decoding="async" />
	</div>
	<h2>Nenhuma área</h2>
	<p>${canEdit ? "Adicione a primeira área usando o botão acima." : "Nenhuma área cadastrada."}</p>
</section>`;
			return;
		}

		const rows = areas
			.map(function (a, i) {
				return `
<tr data-area-idx="${i}">
	<td>${escHtml(a.nome_area)}</td>
	<td>${escHtml(a.nome_coord || "—")}</td>
	${canEdit ? `
	<td class="festa-table-actions">
		<div class="popover" id="area-pop-${i}">
			<button type="button" class="btn-sm-ghost festa-actions-btn" aria-expanded="false" aria-controls="area-pop-${i}-popover">…</button>
			<div id="area-pop-${i}-popover" data-popover aria-hidden="true" class="festa-popover-menu">
				<button type="button" class="festa-popover-item" data-area-action="edit" data-area-idx="${i}">Editar</button>
				<button type="button" class="festa-popover-item festa-popover-item--destructive" data-area-action="delete" data-area-idx="${i}">Apagar</button>
			</div>
		</div>
	</td>` : ""}
</tr>`;
			})
			.join("");

		var headers = [
			{ label: "Nome", sortType: "text" },
			{ label: "Coordenador", sortType: "text" },
		];
		if (canEdit) headers.push({ label: "", sortable: false });
		container.innerHTML = buildSortableTable(headers, rows);

		notifyDesignSystem();

		if (!canEdit) return;

		container.querySelectorAll("[data-area-action]").forEach(function (btn) {
			btn.addEventListener("click", function () {
				const idx = parseInt(btn.dataset.areaIdx, 10);
				const action = btn.dataset.areaAction;
				// Close popover
				const pop = document.getElementById(`area-pop-${idx}`);
				if (pop) {
					const trigger = pop.querySelector("[aria-expanded]");
					if (trigger) trigger.setAttribute("aria-expanded", "false");
					const popover = pop.querySelector("[data-popover]");
					if (popover) popover.setAttribute("aria-hidden", "true");
				}
				if (action === "edit") openEditAreaDialog(idx);
				else if (action === "delete") deleteArea(idx);
			});
		});
	}

	function openEditAreaDialog(idx) {
		const area = areas[idx];
		const dlg = document.getElementById("dialog-edit-area");
		if (!dlg) return;

		dlg.dataset.areaIdx = idx;

		dlg.querySelector("#edit-area-nome").value = area.nome_area || "";
		dlg.querySelector("#edit-area-descricao").value = area.descricao || "";

		const tipo = area.tipo_coord || "Outro";
		const tipoLabel = tipo === "Responsavel" ? "Responsável" : tipo === "Associado" ? "Associado" : "Outro";
		setSelectValue("edit-area-tipo-coord", tipo, tipoLabel);
		updateAreaCoordPickers(tipo);

		if (tipo === "Responsavel") {
			setSelectValue("edit-area-select-responsavel", area.responsavel_coord || "", area.nome_coord || "");
			const eEl = dlg.querySelector("#edit-area-coord-resp-email");
			const tEl = dlg.querySelector("#edit-area-coord-resp-telefone");
			if (eEl) eEl.value = area.email_coord || "";
			if (tEl) tEl.value = area.telefone_coord || "";
		} else if (tipo === "Associado") {
			setSelectValue("edit-area-select-associado", area.associado_coord || "", area.nome_coord || "");
			const eEl = dlg.querySelector("#edit-area-coord-assoc-email");
			const tEl = dlg.querySelector("#edit-area-coord-assoc-telefone");
			if (eEl) eEl.value = area.email_coord || "";
			if (tEl) tEl.value = area.telefone_coord || "";
		} else {
			const outroNome = dlg.querySelector("#edit-area-coord-outro-nome");
			const outroEmail = dlg.querySelector("#edit-area-coord-outro-email");
			const outroTel = dlg.querySelector("#edit-area-coord-outro-telefone");
			if (outroNome) outroNome.value = area.nome_coord || "";
			if (outroEmail) outroEmail.value = area.email_coord || "";
			if (outroTel) outroTel.value = area.telefone_coord || "";
		}

		const equipeContainer = dlg.querySelector("#edit-area-equipe-container");
		const equipe = area.equipe ? area.equipe.map(function (m) { return Object.assign({}, m); }) : [];
		area._editEquipe = equipe;
		renderEquipeTable(equipeContainer, equipe, "edit-area");

		// Reset equipe popover
		closeEquipeForm("edit-area");

		dlg.showModal();
	}

	function updateAreaCoordPickers(tipo) {
		const resp = document.getElementById("edit-area-coord-responsavel");
		const assoc = document.getElementById("edit-area-coord-associado");
		const outro = document.getElementById("edit-area-coord-outro");
		if (resp) resp.hidden = tipo !== "Responsavel";
		if (assoc) assoc.hidden = tipo !== "Associado";
		if (outro) outro.hidden = tipo !== "Outro";
	}

	function deleteArea(idx) {
		const area = areas[idx];
		confirmDialog({
			title: "Apagar área",
			message: `Apagar a área "${area.nome_area}"? Esta ação não pode ser desfeita.`,
			confirmLabel: "Apagar",
		}).then(function (ok) {
			if (!ok) return;
			api("gris.api.festas.excluir_area", { area_name: area.name, festa_name: festaName })
				.then(function () {
					return refreshFestaData();
				})
				.then(function () {
					toast("Área removida.", "success");
				})
				.catch(function (err) {
					toast(err.message || "Erro ao remover área.", "error");
				});
		});
	}

	// ─── Barracas table ─────────────────────────────────────────────────────────

	function renderBarracasTable() {
		const container = document.getElementById("barracas-table-container");
		if (!container) return;

		if (!barracas.length) {
			container.innerHTML = `
<section class="empty">
	<div class="empty-media">
		<img src="/assets/gris/images/gris-character/gris-search.png" alt="Personagem Gris procurando" class="empty-image empty-image--sm" loading="lazy" decoding="async" />
	</div>
	<h2>Nenhuma barraca</h2>
	<p>${canEdit ? "Adicione a primeira barraca usando o botão acima." : "Nenhuma barraca cadastrada."}</p>
</section>`;
			return;
		}

		const rows = barracas
			.map(function (b, i) {
				return `
<tr data-barraca-idx="${i}">
	<td>${escHtml(b.nome_barraca)}</td>
	<td>${escHtml(b.nome_area || "—")}</td>
	<td>${escHtml(b.nome_coord || "—")}</td>
	${canEdit ? `
	<td class="festa-table-actions">
		<div class="popover" id="barraca-pop-${i}">
			<button type="button" class="btn-sm-ghost festa-actions-btn" aria-expanded="false" aria-controls="barraca-pop-${i}-popover">…</button>
			<div id="barraca-pop-${i}-popover" data-popover aria-hidden="true" class="festa-popover-menu">
				<button type="button" class="festa-popover-item" data-barraca-action="edit" data-barraca-idx="${i}">Editar</button>
				<button type="button" class="festa-popover-item festa-popover-item--destructive" data-barraca-action="delete" data-barraca-idx="${i}">Apagar</button>
			</div>
		</div>
	</td>` : ""}
</tr>`;
			})
			.join("");

		var headers = [
			{ label: "Nome", sortType: "text" },
			{ label: "Área", sortType: "text" },
			{ label: "Coordenador", sortType: "text" },
		];
		if (canEdit) headers.push({ label: "", sortable: false });
		container.innerHTML = buildSortableTable(headers, rows);

		notifyDesignSystem();

		if (!canEdit) return;

		container.querySelectorAll("[data-barraca-action]").forEach(function (btn) {
			btn.addEventListener("click", function () {
				const idx = parseInt(btn.dataset.barracaIdx, 10);
				const action = btn.dataset.barracaAction;
				const pop = document.getElementById(`barraca-pop-${idx}`);
				if (pop) {
					const trigger = pop.querySelector("[aria-expanded]");
					if (trigger) trigger.setAttribute("aria-expanded", "false");
					const popover = pop.querySelector("[data-popover]");
					if (popover) popover.setAttribute("aria-hidden", "true");
				}
				if (action === "edit") openEditBarracaDialog(idx);
				else if (action === "delete") deleteBarraca(idx);
			});
		});
	}

	function openEditBarracaDialog(idx) {
		const barraca = barracas[idx];
		const dlg = document.getElementById("dialog-edit-barraca");
		if (!dlg) return;

		dlg.dataset.barracaIdx = idx;

		dlg.querySelector("#edit-barraca-nome").value = barraca.nome_barraca || "";
		dlg.querySelector("#edit-barraca-descricao").value = barraca.descricao || "";
		setSelectValue("edit-barraca-area", barraca.area || "", barraca.nome_area || "");

		const tipo = barraca.tipo_coord || "Outro";
		const tipoLabel = tipo === "Responsavel" ? "Responsável" : tipo === "Associado" ? "Associado" : "Outro";
		setSelectValue("edit-barraca-tipo-coord", tipo, tipoLabel);
		updateBarracaCoordPickers(tipo);

		if (tipo === "Responsavel") {
			setSelectValue("edit-barraca-select-responsavel", barraca.responsavel_coord || "", barraca.nome_coord || "");
			const eEl = dlg.querySelector("#edit-barraca-coord-resp-email");
			const tEl = dlg.querySelector("#edit-barraca-coord-resp-telefone");
			if (eEl) eEl.value = barraca.email_coord || "";
			if (tEl) tEl.value = barraca.telefone_coord || "";
		} else if (tipo === "Associado") {
			setSelectValue("edit-barraca-select-associado", barraca.associado_coord || "", barraca.nome_coord || "");
			const eEl = dlg.querySelector("#edit-barraca-coord-assoc-email");
			const tEl = dlg.querySelector("#edit-barraca-coord-assoc-telefone");
			if (eEl) eEl.value = barraca.email_coord || "";
			if (tEl) tEl.value = barraca.telefone_coord || "";
		} else {
			const outroNome = dlg.querySelector("#edit-barraca-coord-outro-nome");
			const outroEmail = dlg.querySelector("#edit-barraca-coord-outro-email");
			const outroTel = dlg.querySelector("#edit-barraca-coord-outro-telefone");
			if (outroNome) outroNome.value = barraca.nome_coord || "";
			if (outroEmail) outroEmail.value = barraca.email_coord || "";
			if (outroTel) outroTel.value = barraca.telefone_coord || "";
		}

		const equipeContainer = dlg.querySelector("#edit-barraca-equipe-container");
		const equipe = barraca.equipe ? barraca.equipe.map(function (m) { return Object.assign({}, m); }) : [];
		barraca._editEquipe = equipe;
		renderEquipeTable(equipeContainer, equipe, "edit-barraca");

		// Reset equipe popover
		closeEquipeForm("edit-barraca");

		dlg.showModal();
	}

	function updateBarracaCoordPickers(tipo) {
		const resp = document.getElementById("edit-barraca-coord-responsavel");
		const assoc = document.getElementById("edit-barraca-coord-associado");
		const outro = document.getElementById("edit-barraca-coord-outro");
		if (resp) resp.hidden = tipo !== "Responsavel";
		if (assoc) assoc.hidden = tipo !== "Associado";
		if (outro) outro.hidden = tipo !== "Outro";
	}

	function deleteBarraca(idx) {
		const barraca = barracas[idx];
		confirmDialog({
			title: "Apagar barraca",
			message: `Apagar a barraca "${barraca.nome_barraca}"? Esta ação não pode ser desfeita.`,
			confirmLabel: "Apagar",
		}).then(function (ok) {
			if (!ok) return;
			api("gris.api.festas.excluir_barraca", { barraca_name: barraca.name, festa_name: festaName })
				.then(function () { return refreshFestaData(); })
				.then(function () { toast("Barraca removida.", "success"); })
				.catch(function (err) {
					toast(err.message || "Erro ao remover barraca.", "error");
				});
		});
	}

	// ─── Init: coordenador ───────────────────────────────────────────────────────

	function initCoordEdit() {
		if (!canEdit) return;

		setupCoordPicker("coord-tipo", {
			Responsavel: "coord-picker-responsavel",
			Associado: "coord-picker-associado",
		});

		const btnSalvar = document.getElementById("btn-coord-salvar");
		if (!btnSalvar) return;
		btnSalvar.addEventListener("click", function () {
			const tipo = document.getElementById("coord-tipo").value;
			let coordenador = "";
			if (tipo === "Responsavel") {
				coordenador = document.getElementById("coord-select-responsavel").value;
			} else {
				coordenador = document.getElementById("coord-select-associado").value;
			}
			if (!coordenador) {
				toast("Selecione o coordenador.", "error");
				return;
			}
			btnSalvar.disabled = true;
			api("gris.api.festas.update_coordenador", {
				festa_name: festaName,
				tipo_coord: tipo,
				coordenador: coordenador,
			})
				.then(function (r) {
					document.getElementById("display-nome-coord").textContent = r.nome_coord || coordenador;
					document.getElementById("display-tipo-coord").textContent = tipo;
					document.getElementById("dialog-coord").close();
					return refreshFestaData();
				})
				.then(function () {
					toast("Coordenador atualizado.", "success");
				})
				.catch(function (err) {
					toast(err.message || "Erro ao salvar coordenador.", "error");
				})
				.finally(function () {
					btnSalvar.disabled = false;
				});
		});
	}

	// ─── Init: estimativas ──────────────────────────────────────────────────────

	function initEstimativasEdit() {
		if (!canEdit) return;

		const btnSalvar = document.getElementById("btn-salvar-estimativas");
		const inputs = document.querySelectorAll(".festa-estimativa-input");
		if (!btnSalvar) return;

		inputs.forEach(function (input) {
			input.addEventListener("input", function () {
				btnSalvar.hidden = false;
			});
		});

		btnSalvar.addEventListener("click", function () {
			const minVal = document.getElementById("est-min").value;
			const intVal = document.getElementById("est-int").value;
			const maxVal = document.getElementById("est-max").value;

			btnSalvar.disabled = true;
			api("gris.api.festas.update_estimativas", {
				festa_name: festaName,
				min_val: minVal,
				intermediario_val: intVal,
				max_val: maxVal,
			})
				.then(function () {
					btnSalvar.hidden = true;
					return refreshFestaData();
				})
				.then(function () {
					toast("Estimativas salvas.", "success");
				})
				.catch(function (err) {
					toast(err.message || "Erro ao salvar estimativas.", "error");
				})
				.finally(function () {
					btnSalvar.disabled = false;
				});
		});
	}

	// ─── Init: adicionar área ────────────────────────────────────────────────────

	function initAddArea() {
		if (!canEdit) return;
		const btn = document.getElementById("btn-add-area-salvar");
		if (!btn) return;
		btn.addEventListener("click", function () {
			const nome = (document.getElementById("add-area-nome").value || "").trim();
			const descricao = (document.getElementById("add-area-descricao").value || "").trim();
			if (!nome) { toast("Informe o nome da área.", "error"); return; }
			if (!descricao) { toast("Informe a descrição da área.", "error"); return; }

			btn.disabled = true;
			api("gris.api.festas.criar_area", { festa_name: festaName, nome_area: nome, descricao: descricao })
				.then(function () {
					document.getElementById("dialog-add-area").close();
					document.getElementById("add-area-nome").value = "";
					document.getElementById("add-area-descricao").value = "";
					return refreshFestaData();
				})
				.then(function () {
					toast("Área criada.", "success");
				})
				.catch(function (err) {
					toast(err.message || "Erro ao criar área.", "error");
				})
				.finally(function () { btn.disabled = false; });
		});
	}

	// ─── Init: editar área ───────────────────────────────────────────────────────

	function initEditArea() {
		if (!canEdit) return;

		const tipoCoordEl = document.getElementById("edit-area-tipo-coord");
		if (tipoCoordEl) {
			tipoCoordEl.addEventListener("change", function (e) {
				updateAreaCoordPickers(e.detail ? e.detail.value : getSelectValue("edit-area-tipo-coord"));
			});
		}

		const eqTipoEl = document.getElementById("eq-area-tipo");
		if (eqTipoEl) {
			eqTipoEl.addEventListener("change", function (e) {
				updateEqPickers("edit-area", e.detail ? e.detail.value : getSelectValue("eq-area-tipo"));
			});
		}

		// Auto-fill coord contact info when Responsavel/Associado is selected
		const selAreaResp = document.getElementById("edit-area-select-responsavel");
		if (selAreaResp) {
			selAreaResp.addEventListener("change", function (e) {
				const val = e.detail ? e.detail.value : getSelectValue("edit-area-select-responsavel");
				const opt = selAreaResp.querySelector('[role="option"][data-value="' + val + '"]');
				const eEl = document.getElementById("edit-area-coord-resp-email");
				const tEl = document.getElementById("edit-area-coord-resp-telefone");
				if (eEl) eEl.value = opt ? (opt.dataset.email || "") : "";
				if (tEl) tEl.value = opt ? (opt.dataset.telefone || "") : "";
			});
		}
		const selAreaAssoc = document.getElementById("edit-area-select-associado");
		if (selAreaAssoc) {
			selAreaAssoc.addEventListener("change", function (e) {
				const val = e.detail ? e.detail.value : getSelectValue("edit-area-select-associado");
				const opt = selAreaAssoc.querySelector('[role="option"][data-value="' + val + '"]');
				const eEl = document.getElementById("edit-area-coord-assoc-email");
				const tEl = document.getElementById("edit-area-coord-assoc-telefone");
				if (eEl) eEl.value = opt ? (opt.dataset.email || "") : "";
				if (tEl) tEl.value = opt ? (opt.dataset.telefone || "") : "";
			});
		}

		// Auto-fill equipe member contact info when Responsavel/Associado is selected
		const selEqAreaResp = document.getElementById("eq-area-select-responsavel");
		if (selEqAreaResp) {
			selEqAreaResp.addEventListener("change", function (e) {
				const val = e.detail ? e.detail.value : getSelectValue("eq-area-select-responsavel");
				const opt = selEqAreaResp.querySelector('[role="option"][data-value="' + val + '"]');
				const eEl = document.getElementById("eq-area-resp-email");
				const tEl = document.getElementById("eq-area-resp-telefone");
				if (eEl) eEl.value = opt ? (opt.dataset.email || "") : "";
				if (tEl) tEl.value = opt ? (opt.dataset.telefone || "") : "";
			});
		}
		const selEqAreaAssoc = document.getElementById("eq-area-select-associado");
		if (selEqAreaAssoc) {
			selEqAreaAssoc.addEventListener("change", function (e) {
				const val = e.detail ? e.detail.value : getSelectValue("eq-area-select-associado");
				const opt = selEqAreaAssoc.querySelector('[role="option"][data-value="' + val + '"]');
				const eEl = document.getElementById("eq-area-assoc-email");
				const tEl = document.getElementById("eq-area-assoc-telefone");
				if (eEl) eEl.value = opt ? (opt.dataset.email || "") : "";
				if (tEl) tEl.value = opt ? (opt.dataset.telefone || "") : "";
			});
		}

		const btnEqCancelar = document.getElementById("btn-eq-area-cancelar");
		if (btnEqCancelar) {
			btnEqCancelar.addEventListener("click", function () { closeEquipeForm("edit-area"); });
		}

		const btnEqConfirmar = document.getElementById("btn-eq-area-confirmar");
		if (btnEqConfirmar) {
			btnEqConfirmar.addEventListener("click", function () { confirmEquipeForm("edit-area"); });
		}

		const btnAddMembro = document.getElementById("btn-add-area-membro");
		if (btnAddMembro) {
			btnAddMembro.addEventListener("click", function () {
				const dlg = document.getElementById("dialog-edit-area");
				const idx = parseInt(dlg.dataset.areaIdx, 10);
				const area = areas[idx];
				if (!area._editEquipe) area._editEquipe = [];
				const container = dlg.querySelector("#edit-area-equipe-container");
				openEquipeForm("edit-area", area._editEquipe, container, -1);
			});
		}

		// Click-outside closes the equipe popover
		document.addEventListener("click", function (e) {
			const popoverEl = document.getElementById("eq-area-popover");
			const trigger = document.getElementById("btn-add-area-membro");
			if (!popoverEl || !trigger) return;
			if (trigger.getAttribute("aria-expanded") !== "true") return;
			if (!popoverEl.contains(e.target)) closeEquipeForm("edit-area");
		});

		const btnSalvar = document.getElementById("btn-edit-area-salvar");
		if (!btnSalvar) return;
		btnSalvar.addEventListener("click", function () {
			const dlg = document.getElementById("dialog-edit-area");
			const idx = parseInt(dlg.dataset.areaIdx, 10);
			const area = areas[idx];

			const tipo = getSelectValue("edit-area-tipo-coord") || "Outro";
			let coordenador = "";
			if (tipo === "Responsavel") coordenador = getSelectValue("edit-area-select-responsavel");
			else if (tipo === "Associado") coordenador = getSelectValue("edit-area-select-associado");

			const dados = {
				nome_area: dlg.querySelector("#edit-area-nome").value.trim(),
				descricao: dlg.querySelector("#edit-area-descricao").value.trim(),
				tipo_coord: tipo,
				coordenador: coordenador,
				nome_coord: tipo === "Outro" ? (dlg.querySelector("#edit-area-coord-outro-nome").value || "").trim() : "",
				email_coord: tipo === "Outro" ? ((dlg.querySelector("#edit-area-coord-outro-email") || {}).value || "").trim() : "",
				telefone_coord: tipo === "Outro" ? ((dlg.querySelector("#edit-area-coord-outro-telefone") || {}).value || "").trim() : "",
				equipe: area._editEquipe || [],
			};

			btnSalvar.disabled = true;
			api("gris.api.festas.salvar_area", { area_name: area.name, dados_json: JSON.stringify(dados) })
				.then(function () {
					dlg.close();
					return refreshFestaData();
				})
				.then(function () {
					toast("Área salva.", "success");
				})
				.catch(function (err) {
					toast(err.message || "Erro ao salvar área.", "error");
				})
				.finally(function () { btnSalvar.disabled = false; });
		});
	}

	// ─── Init: adicionar barraca ─────────────────────────────────────────────────

	function initAddBarraca() {
		if (!canEdit) return;
		const btn = document.getElementById("btn-add-barraca-salvar");
		if (!btn) return;
		btn.addEventListener("click", function () {
			const nome = (document.getElementById("add-barraca-nome").value || "").trim();
			const descricao = (document.getElementById("add-barraca-descricao").value || "").trim();
			const area = (getSelectValue("add-barraca-area") || "").trim();
			if (!nome) { toast("Informe o nome da barraca.", "error"); return; }
			if (!area) { toast("Selecione a área da barraca.", "error"); return; }
			if (!descricao) { toast("Informe a descrição da barraca.", "error"); return; }

			btn.disabled = true;
			api("gris.api.festas.criar_barraca", { festa_name: festaName, nome_barraca: nome, descricao: descricao, area: area })
				.then(function () {
					document.getElementById("dialog-add-barraca").close();
					document.getElementById("add-barraca-nome").value = "";
					document.getElementById("add-barraca-descricao").value = "";
					setSelectValue("add-barraca-area", "", "");
					return refreshFestaData();
				})
				.then(function () {
					toast("Barraca criada.", "success");
				})
				.catch(function (err) {
					toast(err.message || "Erro ao criar barraca.", "error");
				})
				.finally(function () { btn.disabled = false; });
		});
	}

	// ─── Init: editar barraca ────────────────────────────────────────────────────

	function initEditBarraca() {
		if (!canEdit) return;

		const tipoCoordEl = document.getElementById("edit-barraca-tipo-coord");
		if (tipoCoordEl) {
			tipoCoordEl.addEventListener("change", function (e) {
				updateBarracaCoordPickers(e.detail ? e.detail.value : getSelectValue("edit-barraca-tipo-coord"));
			});
		}

		const eqTipoEl = document.getElementById("eq-barraca-tipo");
		if (eqTipoEl) {
			eqTipoEl.addEventListener("change", function (e) {
				updateEqPickers("edit-barraca", e.detail ? e.detail.value : getSelectValue("eq-barraca-tipo"));
			});
		}

		// Auto-fill coord contact info when Responsavel/Associado is selected
		const selBarracaResp = document.getElementById("edit-barraca-select-responsavel");
		if (selBarracaResp) {
			selBarracaResp.addEventListener("change", function (e) {
				const val = e.detail ? e.detail.value : getSelectValue("edit-barraca-select-responsavel");
				const opt = selBarracaResp.querySelector('[role="option"][data-value="' + val + '"]');
				const eEl = document.getElementById("edit-barraca-coord-resp-email");
				const tEl = document.getElementById("edit-barraca-coord-resp-telefone");
				if (eEl) eEl.value = opt ? (opt.dataset.email || "") : "";
				if (tEl) tEl.value = opt ? (opt.dataset.telefone || "") : "";
			});
		}
		const selBarracaAssoc = document.getElementById("edit-barraca-select-associado");
		if (selBarracaAssoc) {
			selBarracaAssoc.addEventListener("change", function (e) {
				const val = e.detail ? e.detail.value : getSelectValue("edit-barraca-select-associado");
				const opt = selBarracaAssoc.querySelector('[role="option"][data-value="' + val + '"]');
				const eEl = document.getElementById("edit-barraca-coord-assoc-email");
				const tEl = document.getElementById("edit-barraca-coord-assoc-telefone");
				if (eEl) eEl.value = opt ? (opt.dataset.email || "") : "";
				if (tEl) tEl.value = opt ? (opt.dataset.telefone || "") : "";
			});
		}

		// Auto-fill equipe member contact info when Responsavel/Associado is selected
		const selEqBarracaResp = document.getElementById("eq-barraca-select-responsavel");
		if (selEqBarracaResp) {
			selEqBarracaResp.addEventListener("change", function (e) {
				const val = e.detail ? e.detail.value : getSelectValue("eq-barraca-select-responsavel");
				const opt = selEqBarracaResp.querySelector('[role="option"][data-value="' + val + '"]');
				const eEl = document.getElementById("eq-barraca-resp-email");
				const tEl = document.getElementById("eq-barraca-resp-telefone");
				if (eEl) eEl.value = opt ? (opt.dataset.email || "") : "";
				if (tEl) tEl.value = opt ? (opt.dataset.telefone || "") : "";
			});
		}
		const selEqBarracaAssoc = document.getElementById("eq-barraca-select-associado");
		if (selEqBarracaAssoc) {
			selEqBarracaAssoc.addEventListener("change", function (e) {
				const val = e.detail ? e.detail.value : getSelectValue("eq-barraca-select-associado");
				const opt = selEqBarracaAssoc.querySelector('[role="option"][data-value="' + val + '"]');
				const eEl = document.getElementById("eq-barraca-assoc-email");
				const tEl = document.getElementById("eq-barraca-assoc-telefone");
				if (eEl) eEl.value = opt ? (opt.dataset.email || "") : "";
				if (tEl) tEl.value = opt ? (opt.dataset.telefone || "") : "";
			});
		}

		const btnEqCancelar = document.getElementById("btn-eq-barraca-cancelar");
		if (btnEqCancelar) {
			btnEqCancelar.addEventListener("click", function () { closeEquipeForm("edit-barraca"); });
		}

		const btnEqConfirmar = document.getElementById("btn-eq-barraca-confirmar");
		if (btnEqConfirmar) {
			btnEqConfirmar.addEventListener("click", function () { confirmEquipeForm("edit-barraca"); });
		}

		const btnAddMembro = document.getElementById("btn-add-barraca-membro");
		if (btnAddMembro) {
			btnAddMembro.addEventListener("click", function () {
				const dlg = document.getElementById("dialog-edit-barraca");
				const idx = parseInt(dlg.dataset.barracaIdx, 10);
				const barraca = barracas[idx];
				if (!barraca._editEquipe) barraca._editEquipe = [];
				const container = dlg.querySelector("#edit-barraca-equipe-container");
				openEquipeForm("edit-barraca", barraca._editEquipe, container, -1);
			});
		}

		// Click-outside closes the equipe popover
		document.addEventListener("click", function (e) {
			const popoverEl = document.getElementById("eq-barraca-popover");
			const trigger = document.getElementById("btn-add-barraca-membro");
			if (!popoverEl || !trigger) return;
			if (trigger.getAttribute("aria-expanded") !== "true") return;
			if (!popoverEl.contains(e.target)) closeEquipeForm("edit-barraca");
		});

		const btnSalvar = document.getElementById("btn-edit-barraca-salvar");
		if (!btnSalvar) return;
		btnSalvar.addEventListener("click", function () {
			const dlg = document.getElementById("dialog-edit-barraca");
			const idx = parseInt(dlg.dataset.barracaIdx, 10);
			const barraca = barracas[idx];

			const tipo = getSelectValue("edit-barraca-tipo-coord") || "Outro";
			let coordenador = "";
			if (tipo === "Responsavel") coordenador = getSelectValue("edit-barraca-select-responsavel");
			else if (tipo === "Associado") coordenador = getSelectValue("edit-barraca-select-associado");

			const area = (getSelectValue("edit-barraca-area") || "").trim();
			if (!area) { toast("Selecione a área da barraca.", "error"); return; }

			const dados = {
				nome_barraca: dlg.querySelector("#edit-barraca-nome").value.trim(),
				descricao: dlg.querySelector("#edit-barraca-descricao").value.trim(),
				area: area,
				tipo_coord: tipo,
				coordenador: coordenador,
				nome_coord: tipo === "Outro" ? (dlg.querySelector("#edit-barraca-coord-outro-nome").value || "").trim() : "",
				email_coord: tipo === "Outro" ? ((dlg.querySelector("#edit-barraca-coord-outro-email") || {}).value || "").trim() : "",
				telefone_coord: tipo === "Outro" ? ((dlg.querySelector("#edit-barraca-coord-outro-telefone") || {}).value || "").trim() : "",
				equipe: barraca._editEquipe || [],
			};

			btnSalvar.disabled = true;
			api("gris.api.festas.salvar_barraca", { barraca_name: barraca.name, dados_json: JSON.stringify(dados) })
				.then(function () {
					dlg.close();
					return refreshFestaData();
				})
				.then(function () {
					toast("Barraca salva.", "success");
				})
				.catch(function (err) {
					toast(err.message || "Erro ao salvar barraca.", "error");
				})
				.finally(function () { btnSalvar.disabled = false; });
		});
	}

	// ─── Cenário de simulação ─────────────────────────────────────────────────────

	function initCenarioSimulacao() {
		var selectEl = document.getElementById("cenario-simulacao-select");
		var btnSalvar = document.getElementById("btn-salvar-cenario");
		if (!selectEl) return;

		if (!canEdit) return;

		selectEl.addEventListener("change", function () {
			if (btnSalvar) btnSalvar.hidden = false;
		});

		if (!btnSalvar) return;
		btnSalvar.addEventListener("click", function () {
			var cenario = getSelectValue("cenario-simulacao-select");
			if (!cenario) return;
			btnSalvar.disabled = true;
			api("gris.api.festas.update_cenario_simulacao", {
				festa_name: festaName,
				cenario: cenario,
			})
				.then(function () {
					btnSalvar.hidden = true;
					return refreshFestaData();
				})
				.then(function () {
					toast("Cenário salvo.", "success");
				})
				.catch(function (err) {
					toast(err.message || "Erro ao salvar cenário.", "error");
				})
				.finally(function () { btnSalvar.disabled = false; });
		});
	}

	// ─── Boot ────────────────────────────────────────────────────────────────────

	// ─── Formatação de moeda / número ────────────────────────────────────────────

	function fmtCurrency(val) {
		return new Intl.NumberFormat("pt-BR", { style: "currency", currency: "BRL" }).format(val || 0);
	}

	function fmtNum(val) {
		return new Intl.NumberFormat("pt-BR", { maximumFractionDigits: 2 }).format(val || 0);
	}

	// ─── Calcula margem de lucro no frontend ──────────────────────────────────────

	function calcMargemLucro(precoCusto, precoVenda) {
		var venda = parseFloat(precoVenda) || 0;
		var custo = parseFloat(precoCusto) || 0;
		if (venda <= 0) return 0;
		return ((venda - custo) / venda) * 100;
	}

	// ─── Produtos table ───────────────────────────────────────────────────────────

	function renderProdutosTable() {
		var container = document.getElementById("produtos-table-container");
		if (!container) return;

		if (!produtos.length) {
			container.innerHTML = `
<section class="empty">
	<div class="empty-media">
		<img src="/assets/gris/images/gris-character/gris-search.png" alt="Personagem Gris procurando" class="empty-image empty-image--sm" loading="lazy" decoding="async" />
	</div>
	<h2>Nenhum produto</h2>
	<p>${canEdit ? "Adicione o primeiro produto usando o botão acima." : "Nenhum produto cadastrado."}</p>
</section>`;
			return;
		}

		var rows = produtos
			.map(function (p, i) {
				var conviteIcon = '<label class="switch" aria-label="' + (p.faz_parte_convite ? 'Sim' : 'Não') + '"><input type="checkbox" role="switch" class="input" disabled' + (p.faz_parte_convite ? ' checked' : '') + '></label>';
				var margem = p.margem_lucro != null ? fmtNum(p.margem_lucro) + "%" : "—";
				return `
<tr data-produto-idx="${i}">
	<td>${escHtml(p.nome_produto)}</td>
	<td>${escHtml(p.nome_barraca || "—")}</td>
	<td data-sort-value="${Number(p.preco_custo) || 0}">${fmtCurrency(p.preco_custo)}</td>
	<td data-sort-value="${Number(p.preco_venda) || 0}">${fmtCurrency(p.preco_venda)}</td>
	<td data-sort-value="${Number(p.margem_lucro) || 0}">${margem}</td>
	<td class="festa-switch-cell" data-sort-value="${p.faz_parte_convite ? 1 : 0}">${conviteIcon}</td>
	${canEdit ? `
	<td class="festa-table-actions">
		<div class="popover" id="produto-pop-${i}">
			<button type="button" class="btn-sm-ghost festa-actions-btn" aria-expanded="false" aria-controls="produto-pop-${i}-popover">…</button>
			<div id="produto-pop-${i}-popover" data-popover data-align="end" aria-hidden="true" class="festa-popover-menu">
				<button type="button" class="festa-popover-item" data-produto-action="edit" data-produto-idx="${i}">Editar</button>
				<button type="button" class="festa-popover-item festa-popover-item--destructive" data-produto-action="delete" data-produto-idx="${i}">Excluir</button>
			</div>
		</div>
	</td>` : ""}
</tr>`;
			})
			.join("");

		var headers = [
			{ label: "Nome", sortType: "text" },
			{ label: "Barraca", sortType: "text" },
			{ label: "Preço de custo", sortType: "number" },
			{ label: "Preço de venda", sortType: "number" },
			{ label: "Margem", sortType: "number" },
			{ label: "Convite", sortType: "number" },
		];
		if (canEdit) headers.push({ label: "", sortable: false });
		container.innerHTML = buildSortableTable(headers, rows);

		notifyDesignSystem();

		if (!canEdit) return;

		container.querySelectorAll("[data-produto-action]").forEach(function (btn) {
			btn.addEventListener("click", function () {
				var idx = parseInt(btn.dataset.produtoIdx, 10);
				var action = btn.dataset.produtoAction;
				var pop = document.getElementById("produto-pop-" + idx);
				if (pop) {
					var trigger = pop.querySelector("[aria-expanded]");
					if (trigger) trigger.setAttribute("aria-expanded", "false");
					var popover = pop.querySelector("[data-popover]");
					if (popover) popover.setAttribute("aria-hidden", "true");
				}
				if (action === "edit") openEditProdutoDialog(idx);
				else if (action === "delete") deleteProduto(idx);
			});
		});

	}

	function calcCenariosLocal(precoCusto, precoVenda, expectativaVendaPorPessoa) {
		var publicos = {
			min: window._festaData.publicoMin || 0,
			intermediario: window._festaData.publicoIntermediario || 0,
			max: window._festaData.publicoMax || 0,
		};
		var result = {};
		["min", "intermediario", "max"].forEach(function (chave) {
			var qtd = expectativaVendaPorPessoa * publicos[chave];
			result["qtd_" + chave] = qtd;
			result["custo_total_" + chave] = qtd * precoCusto;
			result["receita_total_" + chave] = qtd * precoVenda;
			result["superavit_" + chave] = qtd * precoVenda - qtd * precoCusto;
		});
		return result;
	}

	function updateCenariosTable(produto) {
		var fields = [
			{ prefix: "cen-qtd-", min: fmtNum(produto.qtd_min), int: fmtNum(produto.qtd_intermediario), max: fmtNum(produto.qtd_max) },
			{ prefix: "cen-custo-", min: fmtCurrency(produto.custo_total_min), int: fmtCurrency(produto.custo_total_intermediario), max: fmtCurrency(produto.custo_total_max) },
			{ prefix: "cen-receita-", min: fmtCurrency(produto.receita_total_min), int: fmtCurrency(produto.receita_total_intermediario), max: fmtCurrency(produto.receita_total_max) },
			{ prefix: "cen-superavit-", min: fmtCurrency(produto.superavit_min), int: fmtCurrency(produto.superavit_intermediario), max: fmtCurrency(produto.superavit_max) },
		];
		fields.forEach(function (f) {
			var minEl = document.getElementById(f.prefix + "min");
			var intEl = document.getElementById(f.prefix + "int");
			var maxEl = document.getElementById(f.prefix + "max");
			if (minEl) minEl.textContent = f.min;
			if (intEl) intEl.textContent = f.int;
			if (maxEl) maxEl.textContent = f.max;
		});
	}

	function openEditProdutoDialog(idx) {
		var produto = produtos[idx];
		var dlg = document.getElementById("dialog-edit-produto");
		if (!dlg) return;

		dlg.dataset.produtoIdx = idx;

		var nomeEl = dlg.querySelector("#edit-produto-nome");
		var precoEl = dlg.querySelector("#edit-produto-preco-venda");
		var margemEl = dlg.querySelector("#edit-produto-margem");
		var expectEl = dlg.querySelector("#edit-produto-expectativa");
		var conviteEl = dlg.querySelector("#edit-produto-convite input[type='checkbox']");

		if (nomeEl) nomeEl.value = produto.nome_produto || "";
		if (precoEl) precoEl.value = produto.preco_venda || "";
		if (expectEl) expectEl.value = produto.expectativa_venda_por_pessoa || "";
		if (conviteEl) conviteEl.checked = !!produto.faz_parte_convite;

		var precoCustoEl = dlg.querySelector("#edit-produto-preco-custo");
		if (precoCustoEl) precoCustoEl.value = fmtCurrency(produto.preco_custo);

		var margem = calcMargemLucro(produto.preco_custo, produto.preco_venda);
		if (margemEl) margemEl.value = fmtNum(margem) + "%";

		var barracaLabel = produto.nome_barraca || "";
		setSelectValue("edit-produto-barraca", produto.barraca || "", barracaLabel);

		updateCenariosTable(produto);
		renderProdutoComprasVinculadas(dlg, produto);

		dlg.showModal();
	}

	function renderProdutoComprasVinculadas(dlg, produto) {
		var container = dlg.querySelector("#edit-produto-compras-container");
		if (!container) return;

		var linhas = [];
		(compras || []).forEach(function (c) {
			(c.usos_em_produto || []).forEach(function (u) {
				if (u.produto === produto.name) {
					linhas.push({ nome_item: c.nome_item || "—", uso: u });
				}
			});
		});

		console.log("[compras-vinculadas] produto.name=", produto.name, "linhas=", linhas.length, linhas);

		if (!linhas.length) {
			container.innerHTML = '<p class="text-sm text-muted-foreground festa-equipe-empty">Nenhuma compra vinculada.</p>';
			return;
		}

		var rows = linhas.map(function (l) {
			var qtdLabel = fmtNum(l.uso.quantidade_usada) + " " + (l.uso.unidade_medida_uso || "unidade");
			return "<tr><td>" + escHtml(l.nome_item) + "</td><td>" + escHtml(qtdLabel) + "</td><td>" + fmtCurrency(l.uso.valor_uso) + "</td></tr>";
		}).join("");

		container.innerHTML =
			'<div class="festa-table-scroll"><table class="festa-table">' +
			"<thead><tr><th>Item</th><th>Qtd usada</th><th>Preço de custo</th></tr></thead>" +
			"<tbody>" + rows + "</tbody>" +
			"</table></div>";
	}

	function deleteProduto(idx) {
		var produto = produtos[idx];
		confirmDialog({
			title: "Excluir produto",
			message: "Excluir o produto \"" + produto.nome_produto + "\"? Esta ação não pode ser desfeita.",
			confirmLabel: "Excluir",
		}).then(function (ok) {
			if (!ok) return;
			api("gris.api.festas.excluir_produto", { produto_name: produto.name, festa_name: festaName })
				.then(function () { return refreshFestaData(); })
				.then(function () { toast("Produto removido.", "success"); })
				.catch(function (err) {
					toast(err.message || "Erro ao remover produto.", "error");
				});
		});
	}

	// ─── Init: adicionar produto ──────────────────────────────────────────────────

	function initAddProduto() {
		if (!canEdit) return;
		var btn = document.getElementById("btn-add-produto-salvar");
		if (!btn) return;

		btn.addEventListener("click", function () {
			var nome = (document.getElementById("add-produto-nome").value || "").trim();
			var barraca = getSelectValue("add-produto-barraca");
			var conviteEl = document.querySelector("#add-produto-convite input[type='checkbox']");
			var faz_parte_convite = conviteEl && conviteEl.checked ? "1" : "0";
			var preco_venda = (document.getElementById("add-produto-preco-venda").value || "0").trim();
			var expectativa = (document.getElementById("add-produto-expectativa").value || "0").trim();

			if (!nome) { toast("Informe o nome do produto.", "error"); return; }
			if (faz_parte_convite === "1" && (parseFloat(expectativa) || 0) < 1) {
				toast("Produtos do convite exigem expectativa de venda por pessoa maior ou igual a 1.", "error");
				return;
			}

			btn.disabled = true;
			api("gris.api.festas.criar_produto", {
				festa_name: festaName,
				nome_produto: nome,
				barraca: barraca,
				faz_parte_convite: faz_parte_convite,
				preco_venda: preco_venda,
				expectativa_venda_por_pessoa: expectativa,
			})
				.then(function () {
					document.getElementById("dialog-add-produto").close();
					document.getElementById("add-produto-nome").value = "";
					var conviteReset = document.querySelector("#add-produto-convite input[type='checkbox']");
					if (conviteReset) conviteReset.checked = false;
					document.getElementById("add-produto-preco-venda").value = "";
					document.getElementById("add-produto-expectativa").value = "";
					setSelectValue("add-produto-barraca", "", "Selecionar…");
					return refreshFestaData();
				})
				.then(function () {
					toast("Produto criado.", "success");
				})
				.catch(function (err) {
					toast(err.message || "Erro ao criar produto.", "error");
				})
				.finally(function () { btn.disabled = false; });
		});
	}

	// ─── Init: editar produto ─────────────────────────────────────────────────────

	function initEditProduto() {
		if (!canEdit) return;

		// Recalcular margem e cenários ao vivo quando preço de venda ou expectativa mudam
		var precoVendaEl = document.getElementById("edit-produto-preco-venda");
		var margemEl = document.getElementById("edit-produto-margem");
		var expectativaEl = document.getElementById("edit-produto-expectativa");

		function recalcLiveEditProduto() {
			var dlg = document.getElementById("dialog-edit-produto");
			var idx = parseInt(dlg ? dlg.dataset.produtoIdx : NaN, 10);
			if (isNaN(idx) || idx < 0) return;
			var precoCusto = produtos[idx] ? produtos[idx].preco_custo : 0;
			var precoVenda = parseFloat(precoVendaEl ? precoVendaEl.value : 0) || 0;
			var expectativa = parseFloat(expectativaEl ? expectativaEl.value : 0) || 0;
			if (margemEl) margemEl.value = fmtNum(calcMargemLucro(precoCusto, precoVenda)) + "%";
			updateCenariosTable(calcCenariosLocal(precoCusto, precoVenda, expectativa));
		}

		if (precoVendaEl) precoVendaEl.addEventListener("input", recalcLiveEditProduto);
		if (expectativaEl) expectativaEl.addEventListener("input", recalcLiveEditProduto);

		var btnSalvar = document.getElementById("btn-edit-produto-salvar");
		if (!btnSalvar) return;

		btnSalvar.addEventListener("click", function () {
			var dlg = document.getElementById("dialog-edit-produto");
			var idx = parseInt(dlg.dataset.produtoIdx, 10);
			var produto = produtos[idx];

			var nome = (dlg.querySelector("#edit-produto-nome").value || "").trim();
			if (!nome) { toast("Informe o nome do produto.", "error"); return; }

			var barraca = getSelectValue("edit-produto-barraca");
			var conviteEl = dlg.querySelector("#edit-produto-convite input[type='checkbox']");
			var faz_parte_convite = conviteEl && conviteEl.checked;
			var preco_venda = (dlg.querySelector("#edit-produto-preco-venda").value || "0").trim();
			var expectativa = (dlg.querySelector("#edit-produto-expectativa").value || "0").trim();

			if (faz_parte_convite && (parseFloat(expectativa) || 0) < 1) {
				toast("Produtos do convite exigem expectativa de venda por pessoa maior ou igual a 1.", "error");
				return;
			}

			var dados = {
				nome_produto: nome,
				barraca: barraca,
				faz_parte_convite: faz_parte_convite,
				preco_venda: parseFloat(preco_venda) || 0,
				expectativa_venda_por_pessoa: parseFloat(expectativa) || 0,
			};

			btnSalvar.disabled = true;
			api("gris.api.festas.salvar_produto", { produto_name: produto.name, dados_json: JSON.stringify(dados) })
				.then(function () {
					dlg.close();
					return refreshFestaData();
				})
				.then(function () {
					toast("Produto salvo.", "success");
				})
				.catch(function (err) {
					toast(err.message || "Erro ao salvar produto.", "error");
				})
				.finally(function () { btnSalvar.disabled = false; });
		});
	}

	// ─── Compras table/dialog ────────────────────────────────────────────────────

	var UNIT_FACTORS = {
		unidade: { family: "unidade", factor: 1 },
		kg: { family: "massa", factor: 1000 },
		g: { family: "massa", factor: 1 },
		litro: { family: "volume", factor: 1000 },
		ml: { family: "volume", factor: 1 },
	};

	function convertUnit(qtd, fromUnit, toUnit) {
		var from = UNIT_FACTORS[fromUnit];
		var to = UNIT_FACTORS[toUnit];
		if (!from || !to || from.family !== to.family) return null;
		return (qtd * from.factor) / to.factor;
	}

	function ceilPacotes(qtdTotal, qtdPacote) {
		if (qtdPacote <= 0) return 0;
		return Math.ceil(qtdTotal / qtdPacote);
	}

	function calcCompraCenarios() {
		var unidadeCompra = getSelectValue("compra-unidade") || "unidade";
		var variaComPublico = getSwitchChecked("compra-varia-publico");
		var usadoEmProdutos = getSwitchChecked("compra-usado-produtos");
		var finalQty = parseFloat((document.getElementById("compra-quantidade-final") || {}).value || "0") || 0;

		var escolhida = compraDraftCotacoes.find(function (c) { return c.escolhida; }) || null;
		var qtdPacote = 0, valorPacote = 0;
		if (escolhida && !escolhida.doacao && (escolhida.quantidade || 0) > 0) {
			var conv = convertUnit(escolhida.quantidade, escolhida.unidade_medida || "unidade", unidadeCompra);
			if (conv !== null && conv > 0) { qtdPacote = conv; valorPacote = escolhida.valor || 0; }
		}

		var prodQtdMap = {};
		(window._festaData.produtos || []).forEach(function (p) {
			prodQtdMap[p.name] = {
				min: p.qtd_min || 0,
				intermediario: p.qtd_intermediario || 0,
				max: p.qtd_max || 0,
			};
		});

		var publicos = {
			min: window._festaData.publicoMin || 0,
			intermediario: window._festaData.publicoIntermediario || 0,
			max: window._festaData.publicoMax || 0,
		};

		// soma_uso_total: base sem multiplicador de cenário (para cálculo de sobra)
		var somaUsoTotal = 0;
		if (usadoEmProdutos) {
			compraDraftUsos.forEach(function (uso) {
				if (!uso.quantidade_usada || !uso.unidade_medida_uso) return;
				var c = convertUnit(Number(uso.quantidade_usada), uso.unidade_medida_uso, unidadeCompra);
				if (c !== null) somaUsoTotal += c;
			});
		}

		var result = {};
		["min", "intermediario", "max"].forEach(function (chave) {
			var qtdSugerida;
			if (usadoEmProdutos) {
				var somaCenario = 0;
				compraDraftUsos.forEach(function (uso) {
					if (!uso.produto || !uso.quantidade_usada || !uso.unidade_medida_uso) return;
					var qtdUso = convertUnit(Number(uso.quantidade_usada), uso.unidade_medida_uso, unidadeCompra);
					if (qtdUso === null) return;
					var qtdProdCenario = (prodQtdMap[uso.produto] || {})[chave] || 0;
					somaCenario += qtdUso * qtdProdCenario;
				});
				qtdSugerida = ceilPacotes(somaCenario, qtdPacote);
			} else if (variaComPublico) {
				qtdSugerida = ceilPacotes(finalQty * publicos[chave], qtdPacote);
			} else {
				qtdSugerida = ceilPacotes(finalQty, qtdPacote);
			}

			var valorTotal = qtdPacote > 0 ? qtdSugerida * valorPacote : 0;
			var qtdSobra = 0;
			if (usadoEmProdutos && qtdPacote > 0) {
				qtdSobra = Math.max(0, qtdSugerida * qtdPacote - somaUsoTotal);
			}
			var precoUnitario = qtdPacote > 0 ? valorPacote / qtdPacote : 0;
			result[chave] = {
				qtd_sugerida: qtdSugerida,
				valor_total: valorTotal,
				qtd_sobra_individual: qtdSobra,
				valor_sobra: qtdSobra * precoUnitario,
			};
		});
		return result;
	}

	function getSwitchChecked(id) {
		var el = document.querySelector("#" + id + " input[type='checkbox']");
		return !!(el && el.checked);
	}

	function setSwitchChecked(id, checked) {
		var el = document.querySelector("#" + id + " input[type='checkbox']");
		if (el) el.checked = !!checked;
	}

	function closeActionPopover(prefix, idx) {
		var pop = document.getElementById(prefix + "-pop-" + idx);
		if (!pop) return;
		var trigger = pop.querySelector("[aria-expanded]");
		if (trigger) trigger.setAttribute("aria-expanded", "false");
		var popover = pop.querySelector("[data-popover]");
		if (popover) popover.setAttribute("aria-hidden", "true");
	}

	function renderComprasTable() {
		var container = document.getElementById("compras-table-container");
		if (!container) return;

		if (!compras.length) {
			container.innerHTML = `
<section class="empty">
	<div class="empty-media">
		<img src="/assets/gris/images/gris-character/gris-search.png" alt="Personagem Gris procurando" class="empty-image empty-image--sm" loading="lazy" decoding="async" />
	</div>
	<h2>Nenhuma compra</h2>
	<p>${canEdit ? "Adicione o primeiro item usando o botão acima." : "Nenhuma compra cadastrada."}</p>
</section>`;
			return;
		}

		var rows = compras.map(function (c, i) {
			var qtd = Number(c.quantidade_compra_final) || 0;
			var valor = Number(c.valor_total_compra) || 0;
			var nCot = (c.cotacoes || []).length;
			var nUso = (c.usos_em_produto || []).length;
			return `
<tr data-compra-idx="${i}">
	<td>${escHtml(c.nome_item)}</td>
	<td data-sort-value="${qtd}">${fmtNum(c.quantidade_compra_final)} ${escHtml(c.unidade_compra || "")}</td>
	<td data-sort-value="${valor}">${fmtCurrency(c.valor_total_compra)}</td>
	<td data-sort-value="${nCot}"><span class="badge">${nCot}</span></td>
	<td data-sort-value="${nUso}"><span class="badge">${nUso}</span></td>
	${canEdit ? `
	<td class="festa-table-actions">
		<div class="popover" id="compra-pop-${i}">
			<button type="button" class="btn-sm-ghost festa-actions-btn" aria-expanded="false" aria-controls="compra-pop-${i}-popover">…</button>
			<div id="compra-pop-${i}-popover" data-popover data-align="end" aria-hidden="true" class="festa-popover-menu">
				<button type="button" class="festa-popover-item" data-compra-action="edit" data-compra-idx="${i}">Editar</button>
				<button type="button" class="festa-popover-item festa-popover-item--destructive" data-compra-action="delete" data-compra-idx="${i}">Excluir</button>
			</div>
		</div>
	</td>` : ""}
</tr>`;
		}).join("");

		var headers = [
			{ label: "Item", sortType: "text" },
			{ label: "Quantidade", sortType: "number" },
			{ label: "Valor total", sortType: "number" },
			{ label: "Cotações", sortType: "number" },
			{ label: "Produtos", sortType: "number" },
		];
		if (canEdit) headers.push({ label: "", sortable: false });
		container.innerHTML = buildSortableTable(headers, rows);

		notifyDesignSystem();
		if (!canEdit) return;

		container.querySelectorAll("[data-compra-action]").forEach(function (btn) {
			btn.addEventListener("click", function () {
				var idx = parseInt(btn.dataset.compraIdx, 10);
				closeActionPopover("compra", idx);
				if (btn.dataset.compraAction === "edit") openCompraDialog(idx);
				else if (btn.dataset.compraAction === "delete") deleteCompra(idx);
			});
		});
	}

	function compraTemplate() {
		return {
			name: "",
			area: "",
			nome_area: "",
			nome_item: "",
			varia_com_publico: false,
			usado_em_produtos: false,
			unidade_compra: "unidade",
			quantidade_compra: 0,
			quantidade_compra_final: 0,
			valor_total_compra: 0,
			cotacoes: [],
			usos_em_produto: [],
		};
	}

	function openCompraDialog(idx) {
		var dlg = document.getElementById("dialog-compra");
		if (!dlg) return;
		var compra = idx >= 0 ? compras[idx] : compraTemplate();
		dlg.dataset.compraIdx = String(idx);

		var title = document.getElementById("dialog-compra-title");
		if (title) title.textContent = idx >= 0 ? "Editar compra" : "Adicionar compra";
		document.getElementById("compra-nome-item").value = compra.nome_item || "";
		setSelectValue("compra-area", compra.area || "", compra.nome_area || selectLabelFor(areasItems, "", "Sem área"));
		setSelectValue("compra-unidade", compra.unidade_compra || "unidade", compra.unidade_compra || "unidade");
		document.getElementById("compra-quantidade-sugerida").value = fmtNum(compra.quantidade_compra);
		var finalEl = document.getElementById("compra-quantidade-final");
		finalEl.value = compra.quantidade_compra_final || "";
		finalEl.dataset.autoFinal = idx >= 0 ? "0" : "1";
		document.getElementById("compra-valor-total").value = fmtCurrency(compra.valor_total_compra);
		setSwitchChecked("compra-varia-publico", compra.varia_com_publico);
		setSwitchChecked("compra-usado-produtos", compra.usado_em_produtos);

		compraDraftCotacoes = (compra.cotacoes || []).map(function (c) { return Object.assign({}, c); });
		compraDraftUsos = (compra.usos_em_produto || []).map(function (u) { return Object.assign({}, u); });
		renderCompraCotacoes();
		renderCompraUsos();
		updateCompraUsosVisibility();
		syncCompraCalculatedFields();
		dlg.showModal();
	}

	function readCompraDrafts() {
		compraDraftCotacoes = [];
		document.querySelectorAll("[data-compra-cotacao-row]").forEach(function (row, idx) {
			compraDraftCotacoes.push({
				fornecedor: (row.querySelector("[data-field='fornecedor']").value || "").trim(),
				valor: parseFloat(row.querySelector("[data-field='valor']").value || "0") || 0,
				quantidade: parseFloat(row.querySelector("[data-field='quantidade']").value || "0") || 0,
				unidade_medida: (row.querySelector("[data-field='unidade_medida']") || {}).value || "unidade",
				escolhida: !!row.querySelector("[data-field='escolhida']").checked,
				doacao: !!row.querySelector("[data-field='doacao']").checked,
			});
		});

		compraDraftUsos = [];
		document.querySelectorAll("[data-compra-uso-row]").forEach(function (row) {
			var produtoVal = (row.querySelector("[data-field='produto']") || {}).value || "";
			compraDraftUsos.push({
				produto: produtoVal,
				produto_label: selectLabelFor(produtosItems, produtoVal, ""),
				quantidade_usada: parseFloat(row.querySelector("[data-field='quantidade_usada']").value || "0") || 0,
				unidade_medida_uso: (row.querySelector("[data-field='unidade_medida_uso']") || {}).value || "unidade",
			});
		});
	}

	function renderCompraCotacoes() {
		var container = document.getElementById("compra-cotacoes-container");
		if (!container) return;
		if (!compraDraftCotacoes.length) {
			container.innerHTML = '<p class="text-sm text-muted-foreground festa-equipe-empty">Nenhuma cotação adicionada.</p>';
			return;
		}
		var rows = compraDraftCotacoes.map(function (c, idx) {
			var valUnit = (c.quantidade > 0 && !c.doacao)
				? (new Intl.NumberFormat("pt-BR", { style: "currency", currency: "BRL" }).format((c.valor || 0) / c.quantidade)
					+ " / " + (c.unidade_medida || "unidade"))
				: "—";
			return `
<tr data-compra-cotacao-row>
	<td><input class="input festa-compact-input" data-field="fornecedor" value="${escHtml(c.fornecedor || "")}" placeholder="Fornecedor"></td>
	<td><input class="input festa-compact-input" data-field="valor" type="number" min="0" step="0.01" value="${escHtml(c.valor || "")}"></td>
	<td><input class="input festa-compact-input" data-field="quantidade" type="number" min="0" step="0.001" value="${escHtml(c.quantidade || "")}"></td>
	<td>${renderNativeSelect("unidade_medida", unidadesItems, c.unidade_medida || "unidade")}</td>
	<td class="text-sm text-muted-foreground" data-valor-unitario>${escHtml(valUnit)}</td>
	<td class="festa-switch-cell"><label class="switch" aria-label="Cotação escolhida"><input type="checkbox" role="switch" class="input" data-field="escolhida"${c.escolhida ? " checked" : ""}></label></td>
	<td class="festa-switch-cell"><label class="switch" aria-label="Doação"><input type="checkbox" role="switch" class="input" data-field="doacao"${c.doacao ? " checked" : ""}></label></td>
	<td class="festa-table-actions"><button type="button" class="btn-sm-ghost festa-actions-btn" data-compra-remove-cotacao="${idx}" aria-label="Remover cotação">×</button></td>
</tr>`;
		}).join("");
		container.innerHTML = `
<div class="festa-table-scroll">
<table class="festa-table festa-edit-table">
	<thead>
		<tr>
			<th>Fornecedor</th>
			<th>Valor</th>
			<th>Quantidade</th>
			<th>Unidade</th>
			<th>Valor unitário</th>
			<th>Escolhida</th>
			<th>Doação</th>
			<th></th>
		</tr>
	</thead>
	<tbody>${rows}</tbody>
</table>
</div>`;
		document.dispatchEvent(new CustomEvent("gris:design-system:init"));
		container.querySelectorAll("input, select").forEach(function (el) {
			el.addEventListener("input", syncCompraCalculatedFields);
			el.addEventListener("change", syncCompraCalculatedFields);
		});
		container.querySelectorAll("[data-field='escolhida']").forEach(function (el) {
			el.addEventListener("change", function () {
				if (!el.checked) return;
				container.querySelectorAll("[data-field='escolhida']").forEach(function (other) {
					if (other !== el) other.checked = false;
				});
				syncCompraCalculatedFields();
			});
		});
		container.querySelectorAll("[data-compra-remove-cotacao]").forEach(function (btn) {
			btn.addEventListener("click", function () {
				readCompraDrafts();
				compraDraftCotacoes.splice(parseInt(btn.dataset.compraRemoveCotacao, 10), 1);
				renderCompraCotacoes();
				syncCompraCalculatedFields();
			});
		});
	}

	function renderCompraUsos() {
		var container = document.getElementById("compra-usos-container");
		if (!container) return;
		if (!compraDraftUsos.length) {
			container.innerHTML = '<p class="text-sm text-muted-foreground festa-equipe-empty">Nenhum produto vinculado.</p>';
			return;
		}
		var rows = compraDraftUsos.map(function (u, idx) {
			return `
<tr data-compra-uso-row>
	<td>${renderNativeSelect("produto", produtosItems, u.produto || "", "compra-select-produto")}</td>
	<td><input class="input festa-compact-input" data-field="quantidade_usada" type="number" min="0" step="0.001" value="${escHtml(u.quantidade_usada || "")}"></td>
	<td>${renderNativeSelect("unidade_medida_uso", unidadesItems, u.unidade_medida_uso || "unidade")}</td>
	<td class="festa-table-actions"><button type="button" class="btn-sm-ghost festa-actions-btn" data-compra-remove-uso="${idx}" aria-label="Remover uso">×</button></td>
</tr>`;
		}).join("");
		container.innerHTML = `
<div class="festa-table-scroll">
<table class="festa-table festa-edit-table">
	<thead>
		<tr>
			<th>Produto</th>
			<th>Quantidade usada</th>
			<th>Unidade</th>
			<th></th>
		</tr>
	</thead>
	<tbody>${rows}</tbody>
</table>
</div>`;
		document.dispatchEvent(new CustomEvent("gris:design-system:init"));
		container.querySelectorAll("input, select").forEach(function (el) {
			el.addEventListener("input", syncCompraCalculatedFields);
			el.addEventListener("change", syncCompraCalculatedFields);
		});
		container.querySelectorAll("[data-compra-remove-uso]").forEach(function (btn) {
			btn.addEventListener("click", function () {
				readCompraDrafts();
				compraDraftUsos.splice(parseInt(btn.dataset.compraRemoveUso, 10), 1);
				renderCompraUsos();
				syncCompraCalculatedFields();
			});
		});
	}

	function updateCompraUsosVisibility() {
		var section = document.getElementById("compra-usos-section");
		if (section) section.hidden = !getSwitchChecked("compra-usado-produtos");
	}

	function syncCompraCalculatedFields() {
		readCompraDrafts();
		var unidadeCompra = getSelectValue("compra-unidade") || "unidade";

		// Update valor unitário cells reactively
		var cotacaoContainer = document.getElementById("compra-cotacoes-container");
		if (cotacaoContainer) {
			cotacaoContainer.querySelectorAll("[data-compra-cotacao-row]").forEach(function (row, idx) {
				var cell = row.querySelector("[data-valor-unitario]");
				if (!cell) return;
				var draft = compraDraftCotacoes[idx];
				if (!draft) return;
				var qty = Number(draft.quantidade) || 0;
				var val = Number(draft.valor) || 0;
				var unit = draft.unidade_medida || "unidade";
				cell.textContent = (qty > 0 && !draft.doacao)
					? (new Intl.NumberFormat("pt-BR", { style: "currency", currency: "BRL" }).format(val / qty) + " / " + unit)
					: "—";
			});
		}

		var cen = calcCompraCenarios();
		var cenarioKey = { "Mínimo": "min", "Intermediário": "intermediario", "Máximo": "max" }[cenarioSimulacao] || "intermediario";
		var qtdSugeridaCenario = cen[cenarioKey].qtd_sugerida;

		var sugeridaEl = document.getElementById("compra-quantidade-sugerida");
		if (sugeridaEl) sugeridaEl.value = fmtNum(qtdSugeridaCenario);

		if (getSwitchChecked("compra-usado-produtos")) {
			var finalEl = document.getElementById("compra-quantidade-final");
			if (finalEl && finalEl.dataset.autoFinal === "1") {
				finalEl.value = qtdSugeridaCenario ? String(qtdSugeridaCenario) : "";
			}
		}

		var cenFields = [
			{ min: "compra-cen-qtd-min", int: "compra-cen-qtd-int", max: "compra-cen-qtd-max",
			  vMin: fmtNum(cen.min.qtd_sugerida), vInt: fmtNum(cen.intermediario.qtd_sugerida), vMax: fmtNum(cen.max.qtd_sugerida) },
			{ min: "compra-cen-valor-min", int: "compra-cen-valor-int", max: "compra-cen-valor-max",
			  vMin: fmtCurrency(cen.min.valor_total), vInt: fmtCurrency(cen.intermediario.valor_total), vMax: fmtCurrency(cen.max.valor_total) },
			{ min: "compra-cen-sobra-qtd-min", int: "compra-cen-sobra-qtd-int", max: "compra-cen-sobra-qtd-max",
			  vMin: fmtNum(cen.min.qtd_sobra_individual), vInt: fmtNum(cen.intermediario.qtd_sobra_individual), vMax: fmtNum(cen.max.qtd_sobra_individual) },
			{ min: "compra-cen-sobra-valor-min", int: "compra-cen-sobra-valor-int", max: "compra-cen-sobra-valor-max",
			  vMin: fmtCurrency(cen.min.valor_sobra), vInt: fmtCurrency(cen.intermediario.valor_sobra), vMax: fmtCurrency(cen.max.valor_sobra) },
		];
		cenFields.forEach(function (f) {
			var elMin = document.getElementById(f.min);
			var elInt = document.getElementById(f.int);
			var elMax = document.getElementById(f.max);
			if (elMin) elMin.textContent = f.vMin;
			if (elInt) elInt.textContent = f.vInt;
			if (elMax) elMax.textContent = f.vMax;
		});

		var finalQty = parseFloat((document.getElementById("compra-quantidade-final") || {}).value || "0") || 0;
		var escolhida = compraDraftCotacoes.find(function (c) { return c.escolhida; });
		var total = 0;
		if (escolhida && !escolhida.doacao && finalQty > 0) {
			total = finalQty * (escolhida.valor || 0);
		}
		var totalEl = document.getElementById("compra-valor-total");
		if (totalEl) totalEl.value = fmtCurrency(total);
	}

	function collectCompraDados() {
		readCompraDrafts();
		var nome = (document.getElementById("compra-nome-item").value || "").trim();
		if (!nome) { toast("Informe o nome do item.", "error"); return null; }
		var finalQty = parseFloat((document.getElementById("compra-quantidade-final").value || "0").trim()) || 0;
		if (finalQty < 0) { toast("A quantidade final deve ser não-negativa.", "error"); return null; }
		return {
			nome_item: nome,
			area: getSelectValue("compra-area"),
			unidade_compra: getSelectValue("compra-unidade") || "unidade",
			quantidade_compra_final: finalQty,
			varia_com_publico: getSwitchChecked("compra-varia-publico"),
			usado_em_produtos: getSwitchChecked("compra-usado-produtos"),
			cotacoes: compraDraftCotacoes,
			usos_em_produto: getSwitchChecked("compra-usado-produtos") ? compraDraftUsos : [],
		};
	}

	function deleteCompra(idx) {
		var compra = compras[idx];
		confirmDialog({
			title: "Excluir compra",
			message: "Excluir a compra \"" + compra.nome_item + "\"? Esta ação não pode ser desfeita.",
			confirmLabel: "Excluir",
		}).then(function (ok) {
			if (!ok) return;
			api("gris.api.festas.excluir_compra", { compra_name: compra.name, festa_name: festaName })
				.then(function () { return refreshFestaData(); })
				.then(function () { toast("Compra removida.", "success"); })
				.catch(function (err) {
					toast(err.message || "Erro ao remover compra.", "error");
				});
		});
	}

	function initCompras() {
		renderComprasTable();
		if (!canEdit) return;

		document.querySelectorAll("[data-action='add-compra']").forEach(function (btn) {
			btn.addEventListener("click", function () { openCompraDialog(-1); });
		});

		var usadoEl = document.querySelector("#compra-usado-produtos input[type='checkbox']");
		if (usadoEl) usadoEl.addEventListener("change", function () {
			updateCompraUsosVisibility();
			syncCompraCalculatedFields();
		});
		var variaEl = document.querySelector("#compra-varia-publico input[type='checkbox']");
		if (variaEl) variaEl.addEventListener("change", syncCompraCalculatedFields);
		var unidadeEl = document.getElementById("compra-unidade");
		if (unidadeEl) unidadeEl.addEventListener("change", syncCompraCalculatedFields);
		var finalEl = document.getElementById("compra-quantidade-final");
		if (finalEl) finalEl.addEventListener("input", function () {
			finalEl.dataset.autoFinal = "0";
			syncCompraCalculatedFields();
		});

		var addCotacao = document.getElementById("btn-compra-add-cotacao");
		if (addCotacao) addCotacao.addEventListener("click", function () {
			readCompraDrafts();
			compraDraftCotacoes.push({
				fornecedor: "",
				valor: 0,
				quantidade: 0,
				unidade_medida: getSelectValue("compra-unidade") || "unidade",
				escolhida: compraDraftCotacoes.length === 0,
				doacao: false,
			});
			renderCompraCotacoes();
			syncCompraCalculatedFields();
		});

		var addUso = document.getElementById("btn-compra-add-uso");
		if (addUso) addUso.addEventListener("click", function () {
			readCompraDrafts();
			compraDraftUsos.push({
				produto: "",
				produto_label: "",
				quantidade_usada: 0,
				unidade_medida_uso: getSelectValue("compra-unidade") || "unidade",
			});
			renderCompraUsos();
			syncCompraCalculatedFields();
		});

		var btnSalvar = document.getElementById("btn-compra-salvar");
		if (!btnSalvar) return;
		btnSalvar.addEventListener("click", function () {
			var dlg = document.getElementById("dialog-compra");
			var idx = parseInt(dlg.dataset.compraIdx, 10);
			var dados = collectCompraDados();
			if (!dados) return;

			btnSalvar.disabled = true;
			var request = idx >= 0
				? api("gris.api.festas.salvar_compra", { compra_name: compras[idx].name, dados_json: JSON.stringify(dados) })
				: api("gris.api.festas.criar_compra", { festa_name: festaName, dados_json: JSON.stringify(dados) });
			request
				.then(function () {
					dlg.close();
					return refreshFestaData();
				})
				.then(function () {
					toast(idx >= 0 ? "Compra salva." : "Compra criada.", "success");
				})
				.catch(function (err) {
					toast(err.message || "Erro ao salvar compra.", "error");
				})
				.finally(function () { btnSalvar.disabled = false; });
		});
	}

	// ─── Contratações ───────────────────────────────────────────────────────────

	function contratacaoTemplate() {
		return {
			name: "",
			area: "",
			nome_area: "",
			nome_item: "",
			valor_total_contratacao: 0,
			cotacoes: [],
		};
	}

	function renderContratacoesTable() {
		var container = document.getElementById("contratacoes-table-container");
		if (!container) return;

		if (!contratacoes.length) {
			container.innerHTML = `
<section class="empty">
	<div class="empty-media">
		<img src="/assets/gris/images/gris-character/gris-search.png" alt="Personagem Gris procurando" class="empty-image empty-image--sm" loading="lazy" decoding="async" />
	</div>
	<h2>Nenhuma contratação</h2>
	<p>${canEdit ? "Adicione a primeira contratação usando o botão acima." : "Nenhuma contratação cadastrada."}</p>
</section>`;
			return;
		}

		var rows = contratacoes.map(function (c, i) {
			var valor = Number(c.valor_total_contratacao) || 0;
			var nCot = (c.cotacoes || []).length;
			return `
<tr data-contratacao-idx="${i}">
	<td>${escHtml(c.nome_item)}</td>
	<td data-sort-value="${valor}">${fmtCurrency(c.valor_total_contratacao)}</td>
	<td data-sort-value="${nCot}"><span class="badge">${nCot}</span></td>
	${canEdit ? `
	<td class="festa-table-actions">
		<div class="popover" id="contratacao-pop-${i}">
			<button type="button" class="btn-sm-ghost festa-actions-btn" aria-expanded="false" aria-controls="contratacao-pop-${i}-popover">…</button>
			<div id="contratacao-pop-${i}-popover" data-popover data-align="end" aria-hidden="true" class="festa-popover-menu">
				<button type="button" class="festa-popover-item" data-contratacao-action="edit" data-contratacao-idx="${i}">Editar</button>
				<button type="button" class="festa-popover-item festa-popover-item--destructive" data-contratacao-action="delete" data-contratacao-idx="${i}">Excluir</button>
			</div>
		</div>
	</td>` : ""}
</tr>`;
		}).join("");

		var headers = [
			{ label: "Item", sortType: "text" },
			{ label: "Valor da contratação", sortType: "number" },
			{ label: "Cotações", sortType: "number" },
		];
		if (canEdit) headers.push({ label: "", sortable: false });
		container.innerHTML = buildSortableTable(headers, rows);

		notifyDesignSystem();
		if (!canEdit) return;

		container.querySelectorAll("[data-contratacao-action]").forEach(function (btn) {
			btn.addEventListener("click", function () {
				var idx = parseInt(btn.dataset.contratacaoIdx, 10);
				closeActionPopover("contratacao", idx);
				if (btn.dataset.contratacaoAction === "edit") openContratacaoDialog(idx);
				else if (btn.dataset.contratacaoAction === "delete") deleteContratacao(idx);
			});
		});
	}

	function openContratacaoDialog(idx) {
		var dlg = document.getElementById("dialog-contratacao");
		if (!dlg) return;
		var contratacao = idx >= 0 ? contratacoes[idx] : contratacaoTemplate();
		dlg.dataset.contratacaoIdx = String(idx);

		var title = document.getElementById("dialog-contratacao-title");
		if (title) title.textContent = idx >= 0 ? "Editar contratação" : "Adicionar contratação";
		document.getElementById("contratacao-nome-item").value = contratacao.nome_item || "";
		setSelectValue("contratacao-area", contratacao.area || "", contratacao.nome_area || selectLabelFor(areasItems, "", "Sem área"));
		document.getElementById("contratacao-valor-total").value = fmtCurrency(contratacao.valor_total_contratacao);

		contratacaoDraftCotacoes = (contratacao.cotacoes || []).map(function (c) { return Object.assign({}, c); });
		renderContratacaoCotacoes();
		syncContratacaoValorTotal();
		dlg.showModal();
	}

	function readContratacaoDrafts() {
		contratacaoDraftCotacoes = [];
		document.querySelectorAll("[data-contratacao-cotacao-row]").forEach(function (row) {
			contratacaoDraftCotacoes.push({
				fornecedor: (row.querySelector("[data-field='fornecedor']").value || "").trim(),
				valor: parseFloat(row.querySelector("[data-field='valor']").value || "0") || 0,
				escolhida: !!row.querySelector("[data-field='escolhida']").checked,
			});
		});
	}

	function renderContratacaoCotacoes() {
		var container = document.getElementById("contratacao-cotacoes-container");
		if (!container) return;
		if (!contratacaoDraftCotacoes.length) {
			container.innerHTML = '<p class="text-sm text-muted-foreground festa-equipe-empty">Nenhuma cotação adicionada.</p>';
			return;
		}
		var rows = contratacaoDraftCotacoes.map(function (c, idx) {
			return `
<tr data-contratacao-cotacao-row>
	<td><input class="input festa-compact-input" data-field="fornecedor" value="${escHtml(c.fornecedor || "")}" placeholder="Fornecedor"></td>
	<td><input class="input festa-compact-input" data-field="valor" type="number" min="0" step="0.01" value="${escHtml(c.valor || "")}"></td>
	<td class="festa-switch-cell"><label class="switch" aria-label="Cotação escolhida"><input type="checkbox" role="switch" class="input" data-field="escolhida"${c.escolhida ? " checked" : ""}></label></td>
	<td class="festa-table-actions"><button type="button" class="btn-sm-ghost festa-actions-btn" data-contratacao-remove-cotacao="${idx}" aria-label="Remover cotação">×</button></td>
</tr>`;
		}).join("");
		container.innerHTML = `
<div class="festa-table-scroll">
<table class="festa-table festa-edit-table">
	<thead>
		<tr>
			<th>Fornecedor</th>
			<th>Valor</th>
			<th>Escolhida</th>
			<th></th>
		</tr>
	</thead>
	<tbody>${rows}</tbody>
</table>
</div>`;
		document.dispatchEvent(new CustomEvent("gris:design-system:init"));
		container.querySelectorAll("input").forEach(function (el) {
			el.addEventListener("input", syncContratacaoValorTotal);
			el.addEventListener("change", syncContratacaoValorTotal);
		});
		container.querySelectorAll("[data-field='escolhida']").forEach(function (el) {
			el.addEventListener("change", function () {
				if (!el.checked) return;
				container.querySelectorAll("[data-field='escolhida']").forEach(function (other) {
					if (other !== el) other.checked = false;
				});
				syncContratacaoValorTotal();
			});
		});
		container.querySelectorAll("[data-contratacao-remove-cotacao]").forEach(function (btn) {
			btn.addEventListener("click", function () {
				readContratacaoDrafts();
				contratacaoDraftCotacoes.splice(parseInt(btn.dataset.contratacaoRemoveCotacao, 10), 1);
				renderContratacaoCotacoes();
				syncContratacaoValorTotal();
			});
		});
	}

	function syncContratacaoValorTotal() {
		readContratacaoDrafts();
		var escolhida = contratacaoDraftCotacoes.find(function (c) { return c.escolhida; });
		var total = escolhida ? (Number(escolhida.valor) || 0) : 0;
		var totalEl = document.getElementById("contratacao-valor-total");
		if (totalEl) totalEl.value = fmtCurrency(total);
	}

	function collectContratacaoDados() {
		readContratacaoDrafts();
		var nome = (document.getElementById("contratacao-nome-item").value || "").trim();
		if (!nome) { toast("Informe o nome do item.", "error"); return null; }
		return {
			nome_item: nome,
			area: getSelectValue("contratacao-area"),
			cotacoes: contratacaoDraftCotacoes,
		};
	}

	function deleteContratacao(idx) {
		var contratacao = contratacoes[idx];
		confirmDialog({
			title: "Excluir contratação",
			message: "Excluir a contratação \"" + contratacao.nome_item + "\"? Esta ação não pode ser desfeita.",
			confirmLabel: "Excluir",
		}).then(function (ok) {
			if (!ok) return;
			api("gris.api.festas.excluir_contratacao", { contratacao_name: contratacao.name, festa_name: festaName })
				.then(function () { return refreshFestaData(); })
				.then(function () { toast("Contratação removida.", "success"); })
				.catch(function (err) {
					toast(err.message || "Erro ao remover contratação.", "error");
				});
		});
	}

	function initContratacoes() {
		renderContratacoesTable();
		if (!canEdit) return;

		document.querySelectorAll("[data-action='add-contratacao']").forEach(function (btn) {
			btn.addEventListener("click", function () { openContratacaoDialog(-1); });
		});

		var addCotacao = document.getElementById("btn-contratacao-add-cotacao");
		if (addCotacao) addCotacao.addEventListener("click", function () {
			readContratacaoDrafts();
			contratacaoDraftCotacoes.push({
				fornecedor: "",
				valor: 0,
				escolhida: contratacaoDraftCotacoes.length === 0,
			});
			renderContratacaoCotacoes();
			syncContratacaoValorTotal();
		});

		var btnSalvar = document.getElementById("btn-contratacao-salvar");
		if (!btnSalvar) return;
		btnSalvar.addEventListener("click", function () {
			var dlg = document.getElementById("dialog-contratacao");
			var idx = parseInt(dlg.dataset.contratacaoIdx, 10);
			var dados = collectContratacaoDados();
			if (!dados) return;

			btnSalvar.disabled = true;
			var request = idx >= 0
				? api("gris.api.festas.salvar_contratacao", { contratacao_name: contratacoes[idx].name, dados_json: JSON.stringify(dados) })
				: api("gris.api.festas.criar_contratacao", { festa_name: festaName, dados_json: JSON.stringify(dados) });
			request
				.then(function () {
					dlg.close();
					return refreshFestaData();
				})
				.then(function () {
					toast(idx >= 0 ? "Contratação salva." : "Contratação criada.", "success");
				})
				.catch(function (err) {
					toast(err.message || "Erro ao salvar contratação.", "error");
				})
				.finally(function () { btnSalvar.disabled = false; });
		});
	}

	// ─── Orçamento ───────────────────────────────────────────────────────────────

	function buildCenarioTable(rows, opts) {
		opts = opts || {};
		const headerLabel = opts.headerLabel || "";
		let html = '<table class="festa-cenarios-table"><thead><tr>';
		html += "<th>" + escapeHtml(headerLabel) + "</th>";
		html += "<th>Mínimo</th><th>Intermediário</th><th>Máximo</th>";
		html += "</tr></thead><tbody>";
		rows.forEach(function (r) {
			const cls = r.total ? ' class="festa-cenarios-row--total"' : "";
			html += "<tr" + cls + ">";
			html += '<td class="festa-cenarios-label">' + escapeHtml(r.label) + "</td>";
			["min", "intermediario", "max"].forEach(function (key) {
				const value = r[key];
				let cellCls = r.cellClass || "";
				if (r.negativeIsDanger && Number(value) < 0) {
					cellCls = "festa-cenarios-cell--danger";
				}
				const attr = cellCls ? ' class="' + cellCls + '"' : "";
				html += "<td" + attr + ">" + fmtCurrency(value) + "</td>";
			});
			html += "</tr>";
		});
		html += "</tbody></table>";
		return html;
	}

	function escapeHtml(str) {
		const div = document.createElement("div");
		div.textContent = String(str == null ? "" : str);
		return div.innerHTML;
	}

	function renderOrcamentoCenarios() {
		const totais = window._festaData.totais || {};
		const min = totais.min || {}, inter = totais.intermediario || {}, max = totais.max || {};

		const resultado = [
			{ label: "Receita de convites", min: min.receita_convite, intermediario: inter.receita_convite, max: max.receita_convite },
			{ label: "Receita de produtos", min: min.receita_produtos, intermediario: inter.receita_produtos, max: max.receita_produtos },
			{ label: "Receita total", min: min.receita, intermediario: inter.receita, max: max.receita, cellClass: "festa-cenarios-cell--success" },
			{ label: "Despesa total", min: min.despesa, intermediario: inter.despesa, max: max.despesa, cellClass: "festa-cenarios-cell--danger" },
			{ label: "Saldo", min: min.saldo, intermediario: inter.saldo, max: max.saldo, total: true, negativeIsDanger: true },
		];
		document.getElementById("orc-resultado-table").innerHTML = buildCenarioTable(resultado, { headerLabel: "" });

		const margem = [
			{ label: "Margem de segurança", min: min.margem, intermediario: inter.margem, max: max.margem },
		];
		document.getElementById("orc-margem-table").innerHTML = buildCenarioTable(margem, { headerLabel: "" });
	}

	function renderBreakdownTable(selector, items, headerLabel) {
		const rows = [];
		const totals = { min: 0, intermediario: 0, max: 0 };
		(items || []).forEach(function (it) {
			rows.push({
				label: it.label,
				min: it.esperado_min,
				intermediario: it.esperado_intermediario,
				max: it.esperado_max,
			});
			totals.min += it.esperado_min || 0;
			totals.intermediario += it.esperado_intermediario || 0;
			totals.max += it.esperado_max || 0;
		});
		rows.push({ label: "Total", min: totals.min, intermediario: totals.intermediario, max: totals.max, total: true });
		const target = document.querySelector(selector);
		if (!target) return;
		if (!items || !items.length) {
			target.innerHTML = '<p class="text-sm text-muted-foreground festa-equipe-empty">Nenhum registro.</p>';
			return;
		}
		target.innerHTML = buildCenarioTable(rows, { headerLabel: headerLabel || "" });
	}

	function renderOrcamentoBreakdowns() {
		renderBreakdownTable("#orc-receitas-area-table", window._festaData.receitasPorArea, "Área");
		renderBreakdownTable("#orc-despesas-area-table", window._festaData.despesasPorArea, "Área");
		renderBreakdownTable("#orc-receitas-barraca-table", window._festaData.receitasPorBarraca, "Barraca");
		renderBreakdownTable("#orc-despesas-barraca-table", window._festaData.despesasPorBarraca, "Barraca");
	}

	function renderOrcamentoTab() {
		renderOrcamentoCenarios();
		renderOrcamentoBreakdowns();
	}

	function initOrcamento() {
		const precoMin = document.getElementById("preco-min-convite");
		const precoSug = document.getElementById("preco-sugerido-convite");
		const precoInput = document.getElementById("preco-convite");
		if (precoMin) precoMin.value = fmtCurrency(window._festaData.precoMinConvite);
		if (precoSug) precoSug.value = fmtCurrency(window._festaData.precoSugeridoConvite);

		renderOrcamentoTab();

		if (!precoInput || precoInput.readOnly) return;

		precoInput.addEventListener("change", function () {
			const valor = precoInput.value;
			precoInput.disabled = true;
			api("gris.api.festas.update_preco_convite", { festa_name: festaName, preco: valor })
				.then(function () { return refreshFestaData(); })
				.then(function () {
					precoInput.value = window._festaData.precoConvite;
					toast("Preço do convite atualizado.", "success");
				})
				.catch(function (err) {
					toast(err.message || "Erro ao atualizar preço do convite.", "error");
				})
				.finally(function () { precoInput.disabled = false; });
		});

		const margemInput = document.getElementById("margem-seguranca");
		if (margemInput && !margemInput.readOnly) {
			margemInput.addEventListener("change", function () {
				const valor = margemInput.value;
				margemInput.disabled = true;
				api("gris.api.festas.update_margem_seguranca", { festa_name: festaName, margem: valor })
					.then(function () { return refreshFestaData(); })
					.then(function () {
						margemInput.value = window._festaData.margemSeguranca;
						toast("Margem de segurança atualizada.", "success");
					})
					.catch(function (err) {
						toast(err.message || "Erro ao atualizar margem de segurança.", "error");
					})
					.finally(function () { margemInput.disabled = false; });
			});
		}
	}

	document.addEventListener("DOMContentLoaded", function () {
		renderAreasTable();
		renderBarracasTable();
		renderProdutosTable();
		initCompras();
		initContratacoes();
		initCoordEdit();
		initEstimativasEdit();
		initCenarioSimulacao();
		initAddArea();
		initEditArea();
		initAddBarraca();
		initEditBarraca();
		initAddProduto();
		initEditProduto();
		initOrcamento();
	});
})();
