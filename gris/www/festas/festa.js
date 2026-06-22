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

	// ─── Info dialog helper (exclusão bloqueada por vínculos) ────────────────────

	function infoDialog(opts) {
		opts = opts || {};
		return new Promise(function (resolve) {
			var dlg = document.getElementById("info-dialog");
			if (!dlg || typeof dlg.showModal !== "function") {
				var fallback = opts.message || opts.title || "";
				if (opts.items && opts.items.length) {
					fallback += "\n\n- " + opts.items.join("\n- ");
				}
				window.alert(fallback);
				resolve();
				return;
			}
			var titleEl = dlg.querySelector("header h2");
			var messageEl = dlg.querySelector("#info-dialog-message");
			var listEl = dlg.querySelector("#info-dialog-list");
			var okBtn = dlg.querySelector("#info-dialog-ok");
			if (titleEl) titleEl.textContent = opts.title || "Atenção";
			if (messageEl) messageEl.textContent = opts.message || "";
			if (listEl) {
				var itens = opts.items || [];
				listEl.innerHTML = itens
					.map(function (item) {
						return "<li>" + escHtml(item) + "</li>";
					})
					.join("");
				listEl.hidden = itens.length === 0;
			}

			function cleanup() {
				if (okBtn) okBtn.removeEventListener("click", onOk);
				dlg.removeEventListener("close", onClose);
			}
			function onOk() {
				cleanup();
				dlg.close();
			}
			function onClose() {
				cleanup();
				resolve();
			}
			if (okBtn) okBtn.addEventListener("click", onOk);
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
		refreshSelectOptions("fechamento-compra-area", areasItems);
		refreshSelectOptions("fechamento-contratacao-area", areasItems);
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
				renderFechamentoTab();
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

	// Gera o markup de um select do design system (Basecoat) para uso dinâmico
	// em tabelas/formulários. O valor selecionado fica no input hidden, que
	// carrega o `data-field` para que a leitura via `[data-field=...] .value`
	// continue funcionando como nos selects nativos. O Basecoat inicializa o
	// componente automaticamente (MutationObserver) ou via notifyDesignSystem().
	var _basecoatSelectSeq = 0;
	function renderBasecoatSelect(dataField, items, selectedValue) {
		_basecoatSelectSeq += 1;
		var id = "ds-sel-" + dataField + "-" + _basecoatSelectSeq;
		var selected = String(selectedValue == null ? "" : selectedValue);
		var matched = null;
		for (var i = 0; i < items.length; i++) {
			if (String(items[i].value == null ? "" : items[i].value) === selected) { matched = items[i]; break; }
		}
		var def = matched || items[0] || null;
		var defValue = def ? String(def.value == null ? "" : def.value) : "";
		var defLabel = def ? (def.label || defValue) : "";
		var optionsHtml = items.map(function (item, idx) {
			var value = item.value == null ? "" : String(item.value);
			var sel = (matched && value === selected) ? ' aria-selected="true"' : "";
			return '<div id="' + id + '-items-' + idx + '" role="option" data-value="' + escHtml(value) + '"' + sel + '>' + escHtml(item.label || value) + '</div>';
		}).join("");
		return '<div id="' + id + '" class="select">'
			+ '<button type="button" class="btn-outline w-full" id="' + id + '-trigger" aria-haspopup="listbox" aria-expanded="false" aria-controls="' + id + '-listbox">'
			+ '<span class="truncate">' + escHtml(defLabel) + '</span>'
			+ lucideSvg("chevron-down", "sm", "text-muted-foreground opacity-50 shrink-0")
			+ '</button>'
			+ '<div id="' + id + '-popover" data-popover aria-hidden="true">'
			+ '<div role="listbox" id="' + id + '-listbox" aria-orientation="vertical" aria-labelledby="' + id + '-trigger">'
			+ optionsHtml
			+ '</div></div>'
			+ '<input type="hidden" name="' + id + '-value" value="' + escHtml(defValue) + '" data-field="' + escHtml(dataField) + '">'
			+ '</div>';
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

	// Popula campos do form de equipe. N\u00c3O abre o popover \u2014 quem chama \u00e9
	// respons\u00e1vel por isso. A abertura \u00e9 delegada ao design system (Basecoat
	// popover) via trigger.click(); aqui s\u00f3 preparamos o conte\u00fado antes do
	// design system medir/posicionar.
	function populateEquipeForm(renderPrefix, equipe, container, editIdx) {
		const short = renderPrefix.replace("edit-", "");
		const popoverEl = document.getElementById("eq-" + short + "-popover");
		const trigger = document.getElementById("btn-add-" + short + "-membro");
		if (!popoverEl || !trigger) return;

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
	}

	// Abre o popover de equipe via design system, populando os campos antes
	// para que a medi\u00e7\u00e3o/posicionamento j\u00e1 considere o conte\u00fado final.
	// Se j\u00e1 est\u00e1 aberto, repopula e dispara `resize` para reposicionar.
	function openEquipeForm(renderPrefix, equipe, container, editIdx) {
		const short = renderPrefix.replace("edit-", "");
		const popoverEl = document.getElementById("eq-" + short + "-popover");
		const trigger = document.getElementById("btn-add-" + short + "-membro");
		if (!popoverEl || !trigger) return;

		if (trigger.getAttribute("aria-expanded") === "true") {
			// J\u00e1 aberto: s\u00f3 repopular e reposicionar.
			populateEquipeForm(renderPrefix, equipe, container, editIdx);
			window.dispatchEvent(new Event("resize"));
			return;
		}

		// Fechado: marca o \u00edndice pendente e clica no trigger. O listener de
		// captura em initEquipeTriggers() l\u00ea pendingEditIdx, popula os campos,
		// e em seguida o design system processa o click \u2192 showPopover + position.
		popoverEl.dataset.pendingEditIdx = String(editIdx);
		trigger.click();
	}

	// Listener em fase de captura no document: intercepta o clique no trigger
	// "Adicionar membro" ANTES do design system, popula os campos com base em
	// pendingEditIdx (default -1 = novo membro) e remove a flag.
	function initEquipeTriggers() {
		if (document._festaEqTriggers) return;
		document._festaEqTriggers = true;
		document.addEventListener("click", function (e) {
			const trigger = e.target.closest("#btn-add-area-membro, #btn-add-barraca-membro");
			if (!trigger) return;
			// Se est\u00e1 fechando (toggle off), n\u00e3o precisa popular.
			if (trigger.getAttribute("aria-expanded") === "true") return;

			const isArea = trigger.id === "btn-add-area-membro";
			const short = isArea ? "area" : "barraca";
			const dlg = document.getElementById("dialog-edit-" + short);
			if (!dlg) return;
			const idx = parseInt(dlg.dataset[isArea ? "areaIdx" : "barracaIdx"], 10);
			const item = (isArea ? areas : barracas)[idx];
			if (!item) return;
			if (!item._editEquipe) item._editEquipe = [];
			const container = dlg.querySelector("#edit-" + short + "-equipe-container");

			const popoverEl = document.getElementById("eq-" + short + "-popover");
			const editIdx = popoverEl ? parseInt(popoverEl.dataset.pendingEditIdx || "-1", 10) : -1;
			if (popoverEl) delete popoverEl.dataset.pendingEditIdx;

			populateEquipeForm("edit-" + short, item._editEquipe, container, editIdx);
		}, true);
	}

	function closeEquipeForm(renderPrefix) {
		const short = renderPrefix.replace("edit-", "");
		const trigger = document.getElementById("btn-add-" + short + "-membro");
		if (!trigger) return;
		// Delega o fechamento ao design system via toggle. O listener de
		// captura em initEquipeTriggers() retorna cedo quando aria-expanded
		// já é "true" (não repopula), e o design system trata aria/hidePopover/foco.
		if (trigger.getAttribute("aria-expanded") === "true") trigger.click();
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
				.then(function (res) {
					if (res && res.ok === false && res.bloqueado === "produtos") {
						infoDialog({
							title: "Não é possível excluir a barraca",
							message: "Existem produtos de venda vinculados a esta barraca. A barraca só pode ser apagada depois de desvincular os produtos abaixo:",
							items: res.itens,
						});
						return;
					}
					return refreshFestaData().then(function () {
						toast("Barraca removida.", "success");
					});
				})
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

		// Trigger "Adicionar membro" e click-outside são tratados pelo design
		// system (Basecoat popover) — popula via initEquipeTriggers() em fase
		// de captura antes do design system processar o click.

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

		// Trigger e click-outside delegados ao design system (initEquipeTriggers).

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

	// Converte uma string de moeda BRL (ex.: "R$ 1.234,56") de volta para número.
	function parseCurrencyBR(value) {
		if (value == null) return 0;
		if (typeof value === "number") return value;
		var s = String(value).trim().replace(/[^\d,.-]/g, "");
		if (!s) return 0;
		if (s.indexOf(",") !== -1) {
			s = s.replace(/\./g, "").replace(",", ".");
		}
		var n = parseFloat(s);
		return isNaN(n) ? 0 : n;
	}

	// SVG inline de um ícone Lucide a partir do sprite do design system.
	function lucideSvg(name, size, extraClass) {
		return '<svg class="ds-lucide ds-lucide--' + (size || "sm")
			+ (extraClass ? " " + extraClass : "")
			+ '" aria-hidden="true" focusable="false" viewBox="0 0 24 24">'
			+ '<use href="/assets/gris/design_system/icons/lucide/sprite.svg#' + name + '"></use>'
			+ '</svg>';
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
				.then(function (res) {
					if (res && res.ok === false && res.bloqueado === "compras") {
						infoDialog({
							title: "Não é possível excluir o produto",
							message: "Este produto de venda só pode ser excluído se não houver nenhum item de compra vinculado. Itens de compra vinculados:",
							items: res.itens,
						});
						return;
					}
					return refreshFestaData().then(function () {
						toast("Produto removido.", "success");
					});
				})
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

		// Aba de planejamento mostra apenas itens previstos; não previstos só no Fechamento.
		var comprasVisiveis = compras.filter(function (c) { return c.previsto !== false; });
		if (!comprasVisiveis.length) {
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
			if (c.previsto === false) return "";
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

		// Aba de planejamento mostra apenas itens previstos; não previstos só no Fechamento.
		var contratacoesVisiveis = contratacoes.filter(function (c) { return c.previsto !== false; });
		if (!contratacoesVisiveis.length) {
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
			if (c.previsto === false) return "";
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

	// ─── Convites tab ────────────────────────────────────────────────────────

	const CHART_PALETTE = [
		"#0072B2", "#E69F00", "#009E73", "#D55E00",
		"#56B4E9", "#CC79A7", "#F0E442", "#000000",
	];
	let convitesDashboard = window._festaData.convitesDashboard || {
		opcoes: [], convites: [], series_por_dia: [],
		aceitar_doacoes: false, data_limite_vendas: "",
		link_publico: "/festas/venda_convite",
		totais: { qtd_por_opcao: {}, valor_por_opcao: {}, total_doacoes_valor: 0 },
	};
	let convitesBarrasMode = "qtd";
	let convitesLinhaMode = "total";
	let chartBarrasInstance = null;
	let chartLinhaInstance = null;
	let chartConvitesPorRamoInstance = null;
	let chartFechamentoResumoInstance = null;
	const RAMOS_ORDEM = ["Filhotes", "Lobinho", "Escoteiro", "Sênior", "Pioneiro", "Diretoria"];
	let echartsLoading = null;
	let opcaoDraft = null;
	let opcaoLocalList = [];

	function ensureECharts() {
		if (window.echarts) return Promise.resolve();
		if (echartsLoading) return echartsLoading;
		echartsLoading = new Promise(function (resolve, reject) {
			const script = document.createElement("script");
			script.src = "/assets/gris/vendor/echarts/echarts.min.js";
			script.onload = function () {
				if (window.echarts) resolve();
				else reject(new Error("ECharts não carregou."));
			};
			script.onerror = function () { reject(new Error("Falha ao carregar ECharts.")); };
			document.head.appendChild(script);
		});
		return echartsLoading;
	}

	function fmtMoeda(valor) {
		return new Intl.NumberFormat("pt-BR", {
			style: "currency", currency: "BRL", minimumFractionDigits: 2,
		}).format(Number(valor) || 0);
	}

	function fmtInt(valor) {
		return new Intl.NumberFormat("pt-BR").format(Number(valor) || 0);
	}

	function badgeStatus(status) {
		const map = {
			"Pago": "success",
			"Pendente": "secondary",
			"Erro": "destructive",
		};
		const variant = map[status] || "secondary";
		return '<span class="badge badge-' + variant + '">' + (status || "Pendente") + "</span>";
	}

	function renderConvitesConfigSummary() {
		const container = document.getElementById("convites-config-summary");
		if (!container) return;
		const data = convitesDashboard.data_limite_vendas
			? new Date(convitesDashboard.data_limite_vendas + "T00:00:00").toLocaleDateString("pt-BR")
			: "—";
		const doacoes = convitesDashboard.aceitar_doacoes ? "Sim" : "Não";
		const tiposAtivos = (convitesDashboard.opcoes || []).filter(function (o) { return o.ativo; }).length;
		const tiposTotal = (convitesDashboard.opcoes || []).length;
		container.innerHTML =
			'<div><dt>Tipos cadastrados</dt><dd>' + tiposAtivos + " ativos / " + tiposTotal + " no total</dd></div>" +
			'<div><dt>Aceita doações</dt><dd>' + doacoes + "</dd></div>" +
			"<div><dt>Limite de vendas</dt><dd>" + data + "</dd></div>";
	}

	function renderConvitesBarras() {
		const el = document.getElementById("chart-convites-barras");
		if (!el) return;
		ensureECharts().then(function () {
			if (!chartBarrasInstance) {
				chartBarrasInstance = window.echarts.init(el);
				window.addEventListener("resize", function () {
					if (chartBarrasInstance) chartBarrasInstance.resize();
				});
			}
			const opcoes = convitesDashboard.opcoes || [];
			const isValor = convitesBarrasMode === "valor";
			const totais = convitesDashboard.totais || {};
			const dataMap = isValor ? (totais.valor_por_opcao || {}) : (totais.qtd_por_opcao || {});
			const categorias = opcoes.map(function (o) { return o.nome_convite || o.name; });
			const valores = opcoes.map(function (o) {
				return Number(dataMap[o.name] || 0);
			});
			if (isValor && convitesDashboard.aceitar_doacoes) {
				categorias.push("Doações");
				valores.push(Number(totais.total_doacoes_valor || 0));
			}
			const formatter = isValor ? fmtMoeda : fmtInt;
			chartBarrasInstance.setOption({
				aria: { enabled: true },
				color: CHART_PALETTE,
				tooltip: {
					trigger: "axis",
					axisPointer: { type: "shadow" },
					formatter: function (params) {
						const p = params[0];
						return p.name + "<br/>" + p.marker + " " + formatter(p.value);
					},
				},
				legend: { show: false },
				grid: { left: 16, right: 24, top: 24, bottom: 48, containLabel: true },
				xAxis: {
					type: "category",
					data: categorias,
					axisLabel: { interval: 0, rotate: categorias.length > 4 ? 20 : 0 },
				},
				yAxis: {
					type: "value",
					name: isValor ? "Valor (R$)" : "Quantidade",
					nameLocation: "middle",
					nameGap: 56,
					nameRotate: 90,
					nameTextStyle: { fontSize: 12 },
					axisLabel: {
						formatter: function (v) {
							return isValor ? "R$ " + Number(v).toLocaleString("pt-BR") : Number(v).toLocaleString("pt-BR");
						},
					},
				},
				series: [{
					name: isValor ? "Valor" : "Quantidade",
					type: "bar",
					data: valores,
					barMaxWidth: 64,
					itemStyle: { borderRadius: [4, 4, 0, 0] },
				}],
			}, true);
		}).catch(function (err) {
			toast(err.message || "Erro ao carregar gráficos.", "error");
		});
	}

	function renderChartConvitesPorRamo() {
		const card = document.getElementById("card-convites-por-ramo");
		const el = document.getElementById("chart-convites-por-ramo");
		if (!card || !el) return;
		if (!convitesDashboard.convites_por_ramo) {
			card.hidden = true;
			return;
		}
		card.hidden = false;
		ensureECharts().then(function () {
			if (!chartConvitesPorRamoInstance) {
				chartConvitesPorRamoInstance = window.echarts.init(el);
				window.addEventListener("resize", function () {
					if (chartConvitesPorRamoInstance) chartConvitesPorRamoInstance.resize();
				});
			}
			const porRamo = convitesDashboard.por_ramo || {};
			const media = Number(convitesDashboard.convites_por_associado || 0);
			const entries = RAMOS_ORDEM.map(function (ramo) {
				const info = porRamo[ramo] || {};
				const beneficiarios = Number(info.beneficiarios_ativos || 0);
				const vendidos = Number(info.qtd_vendida || 0);
				const esperado = Number(info.qtd_esperada || 0);
				return {
					ramo: ramo,
					valor: beneficiarios > 0 ? vendidos / beneficiarios : 0,
					pct: esperado > 0 ? (vendidos / esperado) * 100 : null,
				};
			});
			entries.sort(function (a, b) { return b.valor - a.valor; });
			const ramosOrdenados = entries.map(function (e) { return e.ramo; });
			const valores = entries.map(function (e) { return e.valor; });
			const pctVendido = entries.map(function (e) { return e.pct; });
			const markPointData = entries.map(function (e, idx) {
				if (e.pct === null) return null;
				return {
					name: e.ramo,
					value: Math.round(e.pct) + "%",
					xAxis: idx,
					yAxis: e.valor,
				};
			}).filter(function (d) { return d !== null; });
			el.setAttribute(
				"aria-label",
				"Convites vendidos por beneficiário em cada ramo; linha tracejada indica a média de " +
				media.toFixed(2) + " convites por associado. Cada gota indica o percentual vendido em relação ao esperado."
			);
			chartConvitesPorRamoInstance.setOption({
				aria: { enabled: true },
				color: [CHART_PALETTE[0]],
				tooltip: {
					trigger: "axis",
					axisPointer: { type: "shadow" },
					formatter: function (params) {
						const p = params[0];
						const ramo = p.name;
						const info = porRamo[ramo] || {};
						const esperado = Number(info.qtd_esperada || 0);
						const vendidos = Number(info.qtd_vendida || 0);
						const pct = esperado > 0 ? (vendidos / esperado) * 100 : null;
						const pctLine = pct === null
							? "Esperado: — · Vendidos: " + fmtInt(vendidos)
							: "Vendidos / esperado: " + fmtInt(vendidos) + " / " + fmtInt(esperado) +
								" (" + pct.toFixed(1) + "%)";
						return ramo + "<br/>" +
							p.marker + " " + Number(p.value).toFixed(2) + " convite(s) / beneficiário<br/>" +
							pctLine + "<br/>" +
							"Benef. ativos: " + fmtInt(info.beneficiarios_ativos || 0);
					},
				},
				legend: { show: false },
				grid: { left: 16, right: 32, top: 48, bottom: 48, containLabel: true },
				xAxis: {
					type: "category",
					data: ramosOrdenados,
					axisLabel: { interval: 0 },
				},
				yAxis: {
					type: "value",
					name: "Convites / beneficiário",
					nameLocation: "middle",
					nameGap: 48,
					nameRotate: 90,
					nameTextStyle: { fontSize: 12 },
				},
				series: [{
					name: "Convites por beneficiário",
					type: "bar",
					data: valores,
					barMaxWidth: 64,
					itemStyle: { borderRadius: [4, 4, 0, 0] },
					markPoint: {
						symbol: "pin",
						symbolSize: 52,
						itemStyle: { color: CHART_PALETTE[3] },
						label: {
							show: true,
							color: "#fff",
							fontSize: 11,
							fontWeight: 600,
							formatter: "{c}",
						},
						data: markPointData,
					},
					markLine: {
						symbol: "none",
						silent: true,
						lineStyle: { type: "dashed", color: CHART_PALETTE[7], width: 2 },
						label: {
							show: true,
							position: "end",
							formatter: "Média/assoc: " + media.toFixed(2),
						},
						data: [{ yAxis: media, name: "Média por associado" }],
					},
				}],
			}, true);
		}).catch(function (err) {
			toast(err.message || "Erro ao carregar gráfico de ramos.", "error");
		});
	}

	function updateConvitesPorRamoButtonVisibility() {
		const btn = document.getElementById("btn-convites-por-ramo");
		if (!btn) return;
		btn.hidden = opcaoLocalList.length > 0;
	}

	function renderConvitesLinha() {
		const el = document.getElementById("chart-convites-linha");
		if (!el) return;
		ensureECharts().then(function () {
			if (!chartLinhaInstance) {
				chartLinhaInstance = window.echarts.init(el);
				window.addEventListener("resize", function () {
					if (chartLinhaInstance) chartLinhaInstance.resize();
				});
			}
			const linhas = convitesDashboard.series_por_dia || [];
			const diasSet = new Set();
			const opcoesMap = new Map();
			linhas.forEach(function (row) {
				diasSet.add(row.dia);
				const key = row.opcao_convite || row.tipo_convite;
				if (!opcoesMap.has(key)) {
					opcoesMap.set(key, { label: row.tipo_convite || key, por_dia: {} });
				}
				opcoesMap.get(key).por_dia[row.dia] = Number(row.quantidade || 0);
			});
			const dias = Array.from(diasSet).sort();
			let series = [];
			if (convitesLinhaMode === "total") {
				const totalPorDia = dias.map(function (d) {
					return linhas
						.filter(function (l) { return l.dia === d; })
						.reduce(function (acc, l) { return acc + Number(l.quantidade || 0); }, 0);
				});
				series = [{
					name: "Total",
					type: "line",
					smooth: true,
					symbol: "circle",
					data: totalPorDia,
				}];
			} else {
				series = Array.from(opcoesMap.entries()).map(function (entry, idx) {
					const info = entry[1];
					return {
						name: info.label,
						type: "line",
						smooth: true,
						symbol: ["circle", "rect", "triangle", "diamond"][idx % 4],
						lineStyle: { type: ["solid", "dashed", "dotted"][idx % 3] },
						data: dias.map(function (d) { return Number(info.por_dia[d] || 0); }),
					};
				});
			}
			chartLinhaInstance.setOption({
				aria: { enabled: true },
				color: CHART_PALETTE,
				tooltip: { trigger: "axis" },
				legend: { show: convitesLinhaMode !== "total", bottom: 0 },
				grid: { left: 16, right: 24, top: 24, bottom: 48, containLabel: true },
				xAxis: {
					type: "category",
					boundaryGap: false,
					data: dias.map(function (d) {
						const parts = d.split("-");
						return parts.length === 3 ? parts[2] + "/" + parts[1] : d;
					}),
				},
				yAxis: {
					type: "value",
					name: "Convites",
					nameLocation: "middle",
					nameGap: 40,
					nameRotate: 90,
					nameTextStyle: { fontSize: 12 },
					minInterval: 1,
				},
				series: series,
			}, true);
		}).catch(function (err) {
			toast(err.message || "Erro ao carregar gráficos.", "error");
		});
	}

	function renderConvitesTable() {
		const container = document.getElementById("convites-table-container");
		if (!container) return;
		const linhas = convitesDashboard.convites || [];
		if (!linhas.length) {
			container.innerHTML = '<p class="text-sm text-muted-foreground">Nenhum convite registrado para esta festa ainda.</p>';
			return;
		}
		const headers = [
			{ label: "Pagador", sortType: "text" },
			{ label: "E-mail", sortType: "text" },
			{ label: "Tipo de convite", sortType: "text" },
			{ label: "Qtd.", sortType: "number" },
			{ label: "Status", sortType: "text" },
			{ label: '<span class="sr-only">Ações</span>', sortable: false },
		];
		const body = linhas.map(function (row) {
			const pedidoName = row.pedido_name || "";
			const actions = pedidoName
				? '<button type="button" class="btn-sm-outline" data-pedido-detalhes="' + escHtml(pedidoName) + '">Detalhes</button>'
				: "";
			return "<tr>" +
				"<td>" + frappe.utils.escape_html(row.nome_pagador || "—") + "</td>" +
				"<td>" + frappe.utils.escape_html(row.email_pagador || "—") + "</td>" +
				"<td>" + frappe.utils.escape_html(row.tipo_convite || "—") + "</td>" +
				"<td>" + fmtInt(row.quantidade) + "</td>" +
				"<td>" + badgeStatus(row.status_pagamento) + "</td>" +
				'<td class="festa-table-actions">' + actions + "</td>" +
				"</tr>";
		}).join("");
		container.innerHTML = buildSortableTable(headers, body);
		container.querySelectorAll("[data-pedido-detalhes]").forEach(function (btn) {
			btn.addEventListener("click", function () {
				abrirDetalhesPedido(btn.getAttribute("data-pedido-detalhes"));
			});
		});
		notifyDesignSystem();
	}

	// ─── Detalhes do pedido (dialog na aba Convites) ────────────────────────────

	let detalhesPedidoAtual = null;
	let detalhesEdicaoConvRow = null;

	function fmtDataHora(iso) {
		if (!iso) return "—";
		const d = new Date(iso);
		if (isNaN(d.getTime())) return iso;
		return d.toLocaleString("pt-BR");
	}

	function abrirDetalhesPedido(pedidoName) {
		if (!pedidoName) return;
		api("gris.api.festas.convites.get_detalhes_pedido", { pedido_name: pedidoName })
			.then(function (data) {
				detalhesPedidoAtual = data;
				detalhesEdicaoConvRow = null;
				preencherDialogDetalhes(data);
				const dlg = document.getElementById("dialog-detalhes-pedido");
				if (dlg && typeof dlg.showModal === "function") dlg.showModal();
			})
			.catch(function (err) {
				toast((err && err.message) || "Falha ao carregar detalhes do pedido.", "error");
			});
	}

	function preencherDialogDetalhes(data) {
		const set = function (id, val) {
			const el = document.getElementById(id);
			if (el) el.textContent = val || "—";
		};
		const hiddenName = document.getElementById("detalhes-pedido-name");
		if (hiddenName) hiddenName.value = data.pedido_name || "";

		const pagador = data.pagador || {};
		set("detalhes-pagador-nome", pagador.nome);
		set("detalhes-pagador-email", pagador.email);
		set("detalhes-pagador-telefone", pagador.telefone);

		set("detalhes-pedido-criacao", data.creation ? fmtDataHora(data.creation) : "—");
		const statusEl = document.getElementById("detalhes-pedido-status");
		if (statusEl) statusEl.innerHTML = badgeStatus(data.status_pagamento || "Pendente");

		renderDetalhesItens(data.itens || []);
		renderDetalhesConvidados(data.convidados || []);
	}

	function renderDetalhesItens(itens) {
		const container = document.getElementById("detalhes-pedido-itens-container");
		if (!container) return;
		if (!itens.length) {
			container.innerHTML = '<p class="text-sm text-muted-foreground">Nenhum item neste pedido.</p>';
			return;
		}
		const rows = itens.map(function (it) {
			return "<tr>" +
				"<td>" + escHtml(it.tipo_convite || "—") + "</td>" +
				"<td>" + fmtInt(it.quantidade) + "</td>" +
				"<td>" + fmtMoeda(it.valor) + "</td>" +
				"</tr>";
		}).join("");
		container.innerHTML =
			'<div class="festa-table-scroll">' +
			'<table class="festa-table">' +
			'<thead><tr><th>Item</th><th>Qtd.</th><th>Valor unit.</th></tr></thead>' +
			"<tbody>" + rows + "</tbody>" +
			"</table></div>";
	}

	function renderDetalhesConvidados(convidados) {
		const container = document.getElementById("detalhes-pedido-convidados-container");
		if (!container) return;
		if (!convidados.length) {
			container.innerHTML = '<p class="text-sm text-muted-foreground">Nenhum convidado registrado neste pedido.</p>';
			return;
		}
		const podePago = (detalhesPedidoAtual && detalhesPedidoAtual.status_pagamento === "Pago");
		const rows = convidados.map(function (c) {
			const convRow = c.convidado_row || "";
			const ja = !!c.ja_entrou;
			const statusBadge = ja
				? '<span class="badge badge-success">Entrou</span>'
				: '<span class="badge badge-secondary">Não entrou</span>';
			let acoes = "";
			if (canEdit && convRow) {
				if (detalhesEdicaoConvRow === convRow) {
					acoes =
						'<button type="button" class="btn-sm-primary" data-conv-salvar="' + escHtml(convRow) + '">Salvar</button> ' +
						'<button type="button" class="btn-sm-outline" data-conv-cancelar="' + escHtml(convRow) + '">Cancelar</button>';
				} else {
					acoes =
						'<button type="button" class="btn-sm-outline" data-conv-editar="' + escHtml(convRow) + '">Editar</button>';
					if (podePago) {
						acoes += ' <button type="button" class="btn-sm-outline" data-conv-reenviar="' + escHtml(convRow) + '">Reenviar QR</button>';
					}
				}
			}
			let emailCell;
			let telCell;
			if (detalhesEdicaoConvRow === convRow) {
				emailCell =
					'<input type="email" class="input festa-detalhes-edit-input" id="conv-edit-email-' + escHtml(convRow) +
					'" value="' + escHtml(c.email || "") + '" placeholder="email@exemplo.com" />';
				telCell =
					'<input type="tel" class="input festa-detalhes-edit-input" id="conv-edit-tel-' + escHtml(convRow) +
					'" value="' + escHtml(c.telefone || "") + '" placeholder="(00) 00000-0000" />';
			} else {
				emailCell = escHtml(c.email || "—");
				telCell = escHtml(c.telefone || "—");
			}
			return "<tr>" +
				"<td>" + escHtml(c.nome_convidado || "—") + "</td>" +
				"<td>" + emailCell + "</td>" +
				"<td>" + telCell + "</td>" +
				'<td><code class="festa-codigo-mono">' + escHtml(c.codigo_convite || "—") + "</code></td>" +
				"<td>" + statusBadge + "</td>" +
				'<td class="festa-table-actions">' + acoes + "</td>" +
				"</tr>";
		}).join("");
		const headers = canEdit
			? "<th>Nome</th><th>E-mail</th><th>Telefone</th><th>Código</th><th>Status</th><th>Ações</th>"
			: "<th>Nome</th><th>E-mail</th><th>Telefone</th><th>Código</th><th>Status</th><th></th>";
		container.innerHTML =
			'<div class="festa-table-scroll">' +
			'<table class="festa-table">' +
			"<thead><tr>" + headers + "</tr></thead>" +
			"<tbody>" + rows + "</tbody>" +
			"</table></div>";

		container.querySelectorAll("[data-conv-editar]").forEach(function (btn) {
			btn.addEventListener("click", function () {
				detalhesEdicaoConvRow = btn.getAttribute("data-conv-editar");
				renderDetalhesConvidados(detalhesPedidoAtual.convidados || []);
			});
		});
		container.querySelectorAll("[data-conv-cancelar]").forEach(function (btn) {
			btn.addEventListener("click", function () {
				detalhesEdicaoConvRow = null;
				renderDetalhesConvidados(detalhesPedidoAtual.convidados || []);
			});
		});
		container.querySelectorAll("[data-conv-salvar]").forEach(function (btn) {
			btn.addEventListener("click", function () {
				salvarEdicaoConvidado(btn.getAttribute("data-conv-salvar"), btn);
			});
		});
		container.querySelectorAll("[data-conv-reenviar]").forEach(function (btn) {
			btn.addEventListener("click", function () {
				reenviarConviteConvidado(btn.getAttribute("data-conv-reenviar"), btn);
			});
		});
	}

	function salvarEdicaoConvidado(convRow, btn) {
		if (!convRow) return;
		const emailEl = document.getElementById("conv-edit-email-" + convRow);
		const telEl = document.getElementById("conv-edit-tel-" + convRow);
		const email = emailEl ? emailEl.value : "";
		const telefone = telEl ? telEl.value : "";
		if (btn) btn.disabled = true;
		api("gris.api.festas.convites.editar_dados_convidado_pedido", {
			convidado_row: convRow,
			email: email,
			telefone: telefone,
		})
			.then(function (resp) {
				const atualizado = (resp && resp.convidado) || {};
				if (detalhesPedidoAtual && detalhesPedidoAtual.convidados) {
					detalhesPedidoAtual.convidados = detalhesPedidoAtual.convidados.map(function (c) {
						if (c.convidado_row !== convRow) return c;
						return Object.assign({}, c, {
							email: atualizado.email || "",
							telefone: atualizado.telefone || "",
						});
					});
				}
				detalhesEdicaoConvRow = null;
				renderDetalhesConvidados(detalhesPedidoAtual.convidados || []);
				toast("Dados do convidado atualizados.", "success");
			})
			.catch(function (err) {
				toast((err && err.message) || "Falha ao salvar dados.", "error");
				if (btn) btn.disabled = false;
			});
	}

	function reenviarConviteConvidado(convRow, btn) {
		if (!convRow) return;
		confirmDialog({
			title: "Reenviar QR code?",
			message: "O convidado receberá um novo e-mail com o QR code do convite.",
			confirmLabel: "Reenviar",
			variant: "primary",
		}).then(function (ok) {
			if (!ok) return;
			if (btn) btn.disabled = true;
			api("gris.api.festas.convites.reenviar_convite_convidado", { convidado_row: convRow })
				.then(function () {
					toast("Reenvio enfileirado. O e-mail será enviado em instantes.", "success");
				})
				.catch(function (err) {
					toast((err && err.message) || "Falha ao reenviar o convite.", "error");
				})
				.finally(function () {
					if (btn) btn.disabled = false;
				});
		});
	}

	function renderOpcoesTable() {
		const container = document.getElementById("opcoes-convite-table-container");
		if (!container) {
			updateConvitesPorRamoButtonVisibility();
			return;
		}
		if (!opcaoLocalList.length) {
			container.innerHTML = '<p class="text-sm text-muted-foreground">Nenhum tipo de convite cadastrado.</p>';
			updateConvitesPorRamoButtonVisibility();
			return;
		}
		const headers = ["Nome", "Valor", "Esperado", "Vendido", "Ativo", '<span class="sr-only">Ações</span>'];
		const body = opcaoLocalList.map(function (op, idx) {
			const actions = canEdit
				? '<button type="button" class="btn-sm-outline" data-opcao-edit="' + idx + '" aria-label="Editar">✎</button>' +
				  ' <button type="button" class="btn-sm-outline" data-opcao-delete="' + idx + '" aria-label="Excluir">🗑</button>'
				: "";
			return "<tr>" +
				"<td>" + frappe.utils.escape_html(op.nome_convite) + "</td>" +
				"<td>" + fmtMoeda(op.valor) + "</td>" +
				"<td>" + fmtInt(op.quantidade_esperada) + "</td>" +
				"<td>" + fmtInt(op.quantidade_vendida) + "</td>" +
				"<td>" + (op.ativo ? "Sim" : "Não") + "</td>" +
				"<td class=\"festa-table-actions\">" + actions + "</td>" +
				"</tr>";
		}).join("");
		container.innerHTML = '<div class="festa-table-scroll">' +
			'<table class="festa-table"><thead><tr>' +
			headers.map(function (h) { return "<th>" + h + "</th>"; }).join("") +
			"</tr></thead><tbody>" + body + "</tbody></table></div>";

		updateConvitesPorRamoButtonVisibility();

		if (!canEdit) return;
		container.querySelectorAll("[data-opcao-edit]").forEach(function (btn) {
			btn.addEventListener("click", function () {
				const idx = Number(btn.getAttribute("data-opcao-edit"));
				openOpcaoForm(opcaoLocalList[idx]);
			});
		});
		container.querySelectorAll("[data-opcao-delete]").forEach(function (btn) {
			btn.addEventListener("click", function () {
				const idx = Number(btn.getAttribute("data-opcao-delete"));
				const op = opcaoLocalList[idx];
				confirmDialog({
					title: "Excluir tipo de convite",
					message: "Tem certeza que deseja excluir '" + op.nome_convite + "'?",
					confirmLabel: "Excluir",
				}).then(function (ok) {
					if (!ok) return;
					api("gris.api.festas.convites.delete_opcao", { opcao_name: op.name })
						.then(function () {
							toast("Tipo de convite excluído.", "success");
							opcaoLocalList.splice(idx, 1);
							renderOpcoesTable();
						})
						.catch(function (err) {
							toast(err.message || "Não foi possível excluir.", "error");
						});
				});
			});
		});
	}

	function getSwitchInput(id) {
		const wrap = document.getElementById(id);
		if (!wrap) return null;
		// O macro `switch` envolve um <input type="checkbox"> dentro de um <label>;
		// o `id` fica no <label>, então é preciso buscar o input por dentro.
		if (wrap.tagName === "INPUT") return wrap;
		return wrap.querySelector('input[type="checkbox"]');
	}

	function setSwitchChecked(id, checked) {
		const input = getSwitchInput(id);
		if (input) input.checked = !!checked;
	}

	function getSwitchChecked(id) {
		const input = getSwitchInput(id);
		return input ? !!input.checked : false;
	}

	function renderOpcaoImagemPreview(url) {
		const preview = document.getElementById("opcao-imagem-preview");
		const removeBtn = document.getElementById("btn-opcao-imagem-remover");
		const triggerSpan = document.querySelector(
			"#opcao-imagem-upload [data-file-upload-open] span"
		);
		if (!preview) return;
		if (url) {
			preview.innerHTML = '<img class="opcao-imagem-thumb" alt="Capa do convite" />';
			preview.querySelector("img").src = url;
			if (removeBtn) removeBtn.hidden = false;
			if (triggerSpan) triggerSpan.textContent = "Substituir imagem";
		} else {
			preview.innerHTML = '<span class="opcao-imagem-empty">Nenhuma imagem selecionada.</span>';
			if (removeBtn) removeBtn.hidden = true;
			if (triggerSpan) triggerSpan.textContent = "Selecionar imagem";
		}
	}

	function openOpcaoForm(opcao) {
		const form = document.getElementById("opcao-convite-form");
		if (!form) return;
		opcaoDraft = opcao ? Object.assign({}, opcao) : { name: "", nome_convite: "", valor: 0, quantidade_esperada: 0, ativo: true, imagem_capa: "" };
		document.getElementById("opcao-nome-convite").value = opcaoDraft.nome_convite || "";
		document.getElementById("opcao-valor").value = opcaoDraft.valor || 0;
		document.getElementById("opcao-quantidade-esperada").value = opcaoDraft.quantidade_esperada || 0;
		const hiddenUrl = document.getElementById("opcao-imagem-capa");
		if (hiddenUrl) hiddenUrl.value = opcaoDraft.imagem_capa || "";
		renderOpcaoImagemPreview(opcaoDraft.imagem_capa || "");
		setSwitchChecked("opcao-ativo", !!opcaoDraft.ativo);
		form.hidden = false;
		form.scrollIntoView({ behavior: "smooth", block: "nearest" });
	}

	function closeOpcaoForm() {
		const form = document.getElementById("opcao-convite-form");
		if (form) form.hidden = true;
		opcaoDraft = null;
	}

	function syncDashboard(payload) {
		if (!payload) return;
		convitesDashboard = payload;
		window._festaData.convitesDashboard = payload;
		opcaoLocalList = (convitesDashboard.opcoes || []).slice();
		renderConvitesConfigSummary();
		renderConvitesBarras();
		renderChartConvitesPorRamo();
		renderConvitesLinha();
		renderConvitesTable();
		renderOpcoesTable();
	}

	function initConvitesTab() {
		opcaoLocalList = (convitesDashboard.opcoes || []).slice();
		renderConvitesConfigSummary();
		renderConvitesTable();
		renderOpcoesTable();

		// Os gráficos ECharts precisam ser inicializados com o container visível
		// (caso contrário, o canvas fica em 0x0). A aba de convites começa
		// escondida, então adiamos a renderização para o momento em que ela
		// aparece pela primeira vez, e apenas redimensionamos em reaberturas.
		let convitesChartsBootstrapped = false;
		const conviteChartEl = document.getElementById("chart-convites-barras");
		const convitesPanel = conviteChartEl ? conviteChartEl.closest("[role='tabpanel']") : null;
		const renderConvitesCharts = function () {
			renderConvitesBarras();
			renderChartConvitesPorRamo();
			renderConvitesLinha();
		};
		const onConvitesVisible = function () {
			if (!convitesChartsBootstrapped) {
				convitesChartsBootstrapped = true;
				renderConvitesCharts();
			} else {
				if (chartBarrasInstance) chartBarrasInstance.resize();
				if (chartLinhaInstance) chartLinhaInstance.resize();
				if (chartConvitesPorRamoInstance) chartConvitesPorRamoInstance.resize();
			}
		};
		if (convitesPanel) {
			if (!convitesPanel.hidden) {
				onConvitesVisible();
			}
			const observer = new MutationObserver(function () {
				if (!convitesPanel.hidden) onConvitesVisible();
			});
			observer.observe(convitesPanel, { attributes: true, attributeFilter: ["hidden"] });
		} else {
			renderConvitesCharts();
		}

		document.querySelectorAll('[data-chart="barras"]').forEach(function (btn) {
			btn.addEventListener("click", function () {
				convitesBarrasMode = btn.getAttribute("data-mode");
				document.querySelectorAll('[data-chart="barras"]').forEach(function (b) {
					b.setAttribute("aria-pressed", b === btn ? "true" : "false");
				});
				renderConvitesBarras();
			});
		});
		document.querySelectorAll('[data-chart="linha"]').forEach(function (btn) {
			btn.addEventListener("click", function () {
				convitesLinhaMode = btn.getAttribute("data-mode");
				document.querySelectorAll('[data-chart="linha"]').forEach(function (b) {
					b.setAttribute("aria-pressed", b === btn ? "true" : "false");
				});
				renderConvitesLinha();
			});
		});

		const copyBtn = document.getElementById("btn-copy-link-vendas");
		if (copyBtn) {
			copyBtn.addEventListener("click", function () {
				const url = window.location.origin + (convitesDashboard.link_publico || "/festas/venda_convite");
				if (navigator.clipboard && navigator.clipboard.writeText) {
					navigator.clipboard.writeText(url).then(function () {
						toast("Link copiado.", "success");
					}).catch(function () { toast("Não foi possível copiar.", "error"); });
				} else {
					toast(url, "info");
				}
			});
		}

		if (!canEdit) return;

		const dlg = document.getElementById("dialog-convites-config");
		if (!dlg) return;

		dlg.addEventListener("close", closeOpcaoForm);

		const addBtn = document.getElementById("btn-add-opcao-convite");
		if (addBtn) addBtn.addEventListener("click", function () { openOpcaoForm(null); });

		const porRamoBtn = document.getElementById("btn-convites-por-ramo");
		if (porRamoBtn) {
			porRamoBtn.addEventListener("click", function () {
				confirmDialog({
					title: "Criar convites por ramo",
					message: "Criar uma opção de convite para cada ramo com beneficiários ativos? Diretoria será sempre criada.",
					confirmLabel: "Criar",
				}).then(function (ok) {
					if (!ok) return;
					porRamoBtn.disabled = true;
					api("gris.api.festas.convites.criar_opcoes_por_ramo", {
						festa_name: festaName,
					})
						.then(function (resp) {
							syncDashboard(resp && resp.dashboard);
							toast("Opções criadas por ramo.", "success");
						})
						.catch(function (err) {
							toast(err.message || "Falha ao criar opções por ramo.", "error");
						})
						.finally(function () { porRamoBtn.disabled = false; });
				});
			});
		}

		const cancelBtn = document.getElementById("btn-opcao-cancelar");
		if (cancelBtn) cancelBtn.addEventListener("click", closeOpcaoForm);

		// Componente file_upload do design system dispara este evento com
		// detail.files[0].file_url quando o upload conclui.
		const fileUploadComp = document.getElementById("opcao-imagem-upload");
		if (fileUploadComp) {
			fileUploadComp.addEventListener("gris:file-upload:success", function (e) {
				const file = e && e.detail && e.detail.files && e.detail.files[0];
				const url = file && file.file_url ? file.file_url : "";
				if (!url) return;
				if (opcaoDraft) opcaoDraft.imagem_capa = url;
				const hidden = document.getElementById("opcao-imagem-capa");
				if (hidden) hidden.value = url;
				renderOpcaoImagemPreview(url);
			});
		}
		const removeImgBtn = document.getElementById("btn-opcao-imagem-remover");
		if (removeImgBtn) {
			removeImgBtn.addEventListener("click", function () {
				if (opcaoDraft) opcaoDraft.imagem_capa = "";
				const hidden = document.getElementById("opcao-imagem-capa");
				if (hidden) hidden.value = "";
				renderOpcaoImagemPreview("");
			});
		}

		const confirmBtn = document.getElementById("btn-opcao-confirmar");
		if (confirmBtn) {
			confirmBtn.addEventListener("click", function () {
				if (!opcaoDraft) return;
				const payload = {
					name: opcaoDraft.name || "",
					nome_convite: (document.getElementById("opcao-nome-convite").value || "").trim(),
					valor: Number(document.getElementById("opcao-valor").value || 0),
					quantidade_esperada: Number(document.getElementById("opcao-quantidade-esperada").value || 0),
					ativo: getSwitchChecked("opcao-ativo"),
					imagem_capa: (document.getElementById("opcao-imagem-capa").value || "").trim(),
				};
				confirmBtn.disabled = true;
				api("gris.api.festas.convites.upsert_opcao", {
					festa_name: festaName,
					payload: JSON.stringify(payload),
				})
					.then(function (resp) {
						const opcao = resp && resp.opcao;
						if (!opcao) return;
						const idx = opcaoLocalList.findIndex(function (o) { return o.name === opcao.name; });
						if (idx >= 0) opcaoLocalList[idx] = opcao;
						else opcaoLocalList.push(opcao);
						closeOpcaoForm();
						renderOpcoesTable();
						toast("Tipo salvo.", "success");
					})
					.catch(function (err) {
						toast(err.message || "Não foi possível salvar.", "error");
					})
					.finally(function () { confirmBtn.disabled = false; });
			});
		}

		// Inicializa os campos de config quando o dialog abre
		dlg.addEventListener("toggle", function () { hydrateConfigDialog(); });
		const triggerBtn = document.getElementById("btn-config-convites");
		if (triggerBtn) triggerBtn.addEventListener("click", hydrateConfigDialog);

		const saveCfgBtn = document.getElementById("btn-convites-config-salvar");
		if (saveCfgBtn) {
			saveCfgBtn.addEventListener("click", function () {
				const aceita = getSwitchChecked("cfg-aceitar-doacoes");
				const data = (document.getElementById("cfg-data-limite-vendas").value || "").trim();
				const vendaPortariaDesejado = getSwitchChecked("cfg-venda-portaria");
				const vendaPortariaAtual = !!convitesDashboard.venda_na_portaria;
				const mudouPortaria = vendaPortariaDesejado !== vendaPortariaAtual;

				const aplicar = function () {
					saveCfgBtn.disabled = true;
					const tarefas = [];
					if (mudouPortaria) {
						tarefas.push(
							api("gris.api.festas.convites.toggle_venda_portaria", {
								festa_name: festaName,
								ativo: vendaPortariaDesejado ? 1 : 0,
							}).then(function (resp) {
								if (resp && resp.dashboard) syncDashboard(resp.dashboard);
							})
						);
					}
					tarefas.push(
						api("gris.api.festas.convites.update_config", {
							festa_name: festaName,
							aceitar_doacoes: aceita ? 1 : 0,
							data_limite_vendas: data,
						}).then(function (resp) {
							convitesDashboard.aceitar_doacoes = !!resp.aceitar_doacoes;
							convitesDashboard.data_limite_vendas = resp.data_limite_vendas || "";
						})
					);
					Promise.all(tarefas)
						.then(function () {
							renderConvitesConfigSummary();
							renderConvitesBarras();
							toast("Configurações salvas.", "success");
							dlg.close();
						})
						.catch(function (err) {
							toast(err.message || "Não foi possível salvar.", "error");
						})
						.finally(function () { saveCfgBtn.disabled = false; });
				};

				if (mudouPortaria) {
					const msg = vendaPortariaDesejado
						? "Ativar 'Venda na portaria' irá desativar todos os outros tipos de convite ativos e habilitar apenas o tipo 'Portaria'. Continuar?"
						: "Desativar o modo 'Venda na portaria' irá desativar o tipo 'Portaria'. Os demais tipos permanecem como estão (você precisará reativá-los manualmente). Continuar?";
					confirmDialog({
						title: vendaPortariaDesejado ? "Ativar venda na portaria" : "Desativar venda na portaria",
						message: msg,
						confirmLabel: "Salvar e continuar",
						variant: vendaPortariaDesejado ? "primary" : undefined,
					}).then(function (ok) {
						if (ok) aplicar();
					});
				} else {
					aplicar();
				}
			});
		}
	}

	function hydrateConfigDialog() {
		setSwitchChecked("cfg-venda-portaria", !!convitesDashboard.venda_na_portaria);
		setSwitchChecked("cfg-aceitar-doacoes", !!convitesDashboard.aceitar_doacoes);
		const data = document.getElementById("cfg-data-limite-vendas");
		if (data) data.value = convitesDashboard.data_limite_vendas || "";
		opcaoLocalList = (convitesDashboard.opcoes || []).slice();
		renderOpcoesTable();
		closeOpcaoForm();
	}

	// ─── Fechamento ──────────────────────────────────────────────────────────────

	var fechamentoCompraUsos = [];

	function fechamentoCenarioKey() {
		return { "Mínimo": "min", "Intermediário": "intermediario", "Máximo": "max" }[cenarioSimulacao] || "intermediario";
	}

	function fechamentoSetText(id, text) {
		var el = document.getElementById(id);
		if (el) el.textContent = text;
	}

	function fechamentoEmpty(msg) {
		return '<p class="text-sm text-muted-foreground festa-equipe-empty">' + escHtml(msg) + '</p>';
	}

	function renderFechamentoTab() {
		renderFechamentoCompras();
		renderFechamentoContratacoes();
		renderFechamentoBarracas();
		renderFechamentoConvites();
		renderFechamentoResumo();
	}

	// ── Compras ──

	function renderFechamentoCompras() {
		var container = document.getElementById("fechamento-compras-container");
		if (!container) return;
		if (!compras.length) { container.innerHTML = fechamentoEmpty("Nenhuma compra cadastrada."); return; }

		var key = fechamentoCenarioKey();
		var rows = compras.map(function (c, i) {
			var tag = c.previsto === false ? ' <span class="badge">Sem previsão</span>' : "";
			var detalhes = canEdit
				? `<td class="festa-table-actions"><button type="button" class="btn-sm-outline" data-fechamento-compra="${i}">Detalhes</button></td>`
				: "";
			// Itens previstos: o valor cotado vem do cenário ativo (mesmo dado
			// exibido no diálogo de detalhes). Sem previsão não tem orçamento.
			var valorCotado = c.previsto !== false
				? (Number(c["valor_total_" + key]) || 0)
				: (Number(c.valor_total_compra) || 0);
			return `
<tr>
	<td>${escHtml(c.nome_item)}${tag}</td>
	<td>${fmtNum(c.quantidade_compra_final)} ${escHtml(c.unidade_compra || "")}</td>
	<td>${fmtCurrency(valorCotado)}</td>
	<td>${fmtCurrency(c.valor_total_realizado)}</td>
	${detalhes}
</tr>`;
		}).join("");

		var actionTh = canEdit ? "<th></th>" : "";
		container.innerHTML = `<div class="festa-table-scroll"><table class="festa-table"><thead><tr><th>Item</th><th>Quantidade</th><th>Valor cotado</th><th>Valor gasto</th>${actionTh}</tr></thead><tbody>${rows}</tbody></table></div>`;
		notifyDesignSystem();
		if (!canEdit) return;
		container.querySelectorAll("[data-fechamento-compra]").forEach(function (btn) {
			btn.addEventListener("click", function () { openCompraFechamentoDialog(parseInt(btn.dataset.fechamentoCompra, 10)); });
		});
	}

	function setRealizadoCompra(c) {
		document.getElementById("fechamento-compra-real-individual").value = c.valor_individual_realizado || "";
		setSelectValue("fechamento-compra-real-unidade", c.unidade_medida_realizado || "unidade", c.unidade_medida_realizado || "unidade");
		document.getElementById("fechamento-compra-real-qtd").value = c.quantidade_realizada || "";
		document.getElementById("fechamento-compra-real-total").value = c.valor_total_realizado || "";
		document.getElementById("fechamento-compra-real-fornecedor").value = c.fornecedor_realizado || "";
		document.getElementById("fechamento-compra-real-obs").value = c.observacoes_realizado || "";
	}

	function openCompraFechamentoDialog(idx) {
		var dlg = document.getElementById("dialog-compra-fechamento");
		if (!dlg) return;
		dlg.dataset.compraIdx = String(idx);
		var titleEl = document.getElementById("dialog-compra-fechamento-title");
		var blocoIdent = dlg.querySelector('[data-fechamento-block="identificacao"]');
		var blocoOrc = dlg.querySelector('[data-fechamento-block="orcamento"]');

		if (idx < 0) {
			titleEl.textContent = "Adicionar compra sem previsão";
			blocoIdent.hidden = false;
			blocoOrc.hidden = true;
			document.getElementById("fechamento-compra-nome-item").value = "";
			setSelectValue("fechamento-compra-area", "", selectLabelFor(areasItems, "", "Sem área"));
			setSwitchChecked("fechamento-compra-usado-produtos", false);
			fechamentoCompraUsos = [];
			renderFechamentoCompraUsos();
			updateFechamentoCompraUsosVisibility();
			setRealizadoCompra({});
		} else {
			var compra = compras[idx];
			titleEl.textContent = "Detalhes da compra — " + (compra.nome_item || "");
			blocoIdent.hidden = true;
			if (compra.previsto !== false) {
				blocoOrc.hidden = false;
				var key = fechamentoCenarioKey();
				var escolhida = (compra.cotacoes || []).find(function (x) { return x.escolhida; });
				var valIndividual = escolhida && Number(escolhida.quantidade) > 0 && !escolhida.doacao
					? (Number(escolhida.valor) || 0) / Number(escolhida.quantidade) : 0;
				fechamentoSetText("fechamento-compra-orc-individual",
					escolhida ? fmtCurrency(valIndividual) + " / " + (escolhida.unidade_medida || "unidade") : "—");
				fechamentoSetText("fechamento-compra-orc-qtd",
					fmtNum(compra["qtd_sugerida_" + key]) + " " + (compra.unidade_compra || ""));
				fechamentoSetText("fechamento-compra-orc-total", fmtCurrency(compra["valor_total_" + key]));
				fechamentoSetText("fechamento-compra-orc-fornecedor", escolhida ? (escolhida.fornecedor || "—") : "—");
			} else {
				blocoOrc.hidden = true;
			}
			setRealizadoCompra(compra);
		}
		dlg.showModal();
	}

	function readFechamentoCompraUsos() {
		fechamentoCompraUsos = [];
		document.querySelectorAll("#fechamento-compra-usos-container [data-fechamento-uso-row]").forEach(function (row) {
			fechamentoCompraUsos.push({
				produto: (row.querySelector("[data-field='produto']") || {}).value || "",
				quantidade_usada: parseFloat(row.querySelector("[data-field='quantidade_usada']").value || "0") || 0,
				unidade_medida_uso: (row.querySelector("[data-field='unidade_medida_uso']") || {}).value || "unidade",
			});
		});
	}

	function renderFechamentoCompraUsos() {
		var container = document.getElementById("fechamento-compra-usos-container");
		if (!container) return;
		if (!fechamentoCompraUsos.length) {
			container.innerHTML = '<p class="text-sm text-muted-foreground festa-equipe-empty">Nenhum produto vinculado.</p>';
			return;
		}
		var rows = fechamentoCompraUsos.map(function (u, idx) {
			return `
<tr data-fechamento-uso-row>
	<td>${renderBasecoatSelect("produto", produtosItems, u.produto || "")}</td>
	<td><input class="input festa-compact-input" data-field="quantidade_usada" type="number" min="0" step="0.001" value="${escHtml(u.quantidade_usada || "")}"></td>
	<td>${renderBasecoatSelect("unidade_medida_uso", unidadesItems, u.unidade_medida_uso || "unidade")}</td>
	<td class="festa-table-actions"><button type="button" class="btn-sm-ghost festa-actions-btn" data-fechamento-remove-uso="${idx}" aria-label="Remover uso">×</button></td>
</tr>`;
		}).join("");
		container.innerHTML = `<div class="festa-table-scroll"><table class="festa-table festa-edit-table"><thead><tr><th>Produto</th><th>Quantidade usada</th><th>Unidade</th><th></th></tr></thead><tbody>${rows}</tbody></table></div>`;
		notifyDesignSystem();
		container.querySelectorAll("[data-fechamento-remove-uso]").forEach(function (btn) {
			btn.addEventListener("click", function () {
				readFechamentoCompraUsos();
				fechamentoCompraUsos.splice(parseInt(btn.dataset.fechamentoRemoveUso, 10), 1);
				renderFechamentoCompraUsos();
			});
		});
	}

	function updateFechamentoCompraUsosVisibility() {
		var sec = document.getElementById("fechamento-compra-usos-section");
		if (sec) sec.hidden = !getSwitchChecked("fechamento-compra-usado-produtos");
	}

	function collectCompraRealizado() {
		return {
			valor_individual_realizado: parseFloat(document.getElementById("fechamento-compra-real-individual").value) || 0,
			unidade_medida_realizado: getSelectValue("fechamento-compra-real-unidade") || "unidade",
			quantidade_realizada: parseFloat(document.getElementById("fechamento-compra-real-qtd").value) || 0,
			valor_total_realizado: parseFloat(document.getElementById("fechamento-compra-real-total").value) || 0,
			fornecedor_realizado: (document.getElementById("fechamento-compra-real-fornecedor").value || "").trim(),
			observacoes_realizado: (document.getElementById("fechamento-compra-real-obs").value || "").trim(),
		};
	}

	function saveCompraFechamento() {
		var dlg = document.getElementById("dialog-compra-fechamento");
		var idx = parseInt(dlg.dataset.compraIdx, 10);
		var dados = collectCompraRealizado();
		var request;
		if (idx < 0) {
			var nome = (document.getElementById("fechamento-compra-nome-item").value || "").trim();
			if (!nome) { toast("Informe o nome do item.", "error"); return; }
			readFechamentoCompraUsos();
			dados.nome_item = nome;
			dados.area = getSelectValue("fechamento-compra-area");
			dados.usado_em_produtos = getSwitchChecked("fechamento-compra-usado-produtos");
			dados.usos_em_produto = dados.usado_em_produtos ? fechamentoCompraUsos : [];
			request = api("gris.api.festas.criar_compra_sem_previsao", { festa_name: festaName, dados_json: JSON.stringify(dados) });
		} else {
			request = api("gris.api.festas.salvar_realizado_compra", { compra_name: compras[idx].name, dados_json: JSON.stringify(dados) });
		}
		var btn = document.getElementById("btn-fechamento-compra-salvar");
		btn.disabled = true;
		request
			.then(function () { dlg.close(); return refreshFestaData(); })
			.then(function () { toast("Fechamento salvo.", "success"); })
			.catch(function (err) { toast(err.message || "Erro ao salvar.", "error"); })
			.finally(function () { btn.disabled = false; });
	}

	// ── Contratações ──

	function renderFechamentoContratacoes() {
		var container = document.getElementById("fechamento-contratacoes-container");
		if (!container) return;
		if (!contratacoes.length) { container.innerHTML = fechamentoEmpty("Nenhuma contratação cadastrada."); return; }

		var rows = contratacoes.map(function (c, i) {
			var tag = c.previsto === false ? ' <span class="badge">Sem previsão</span>' : "";
			var detalhes = canEdit
				? `<td class="festa-table-actions"><button type="button" class="btn-sm-outline" data-fechamento-contratacao="${i}">Detalhes</button></td>`
				: "";
			return `
<tr>
	<td>${escHtml(c.nome_item)}${tag}</td>
	<td>${fmtCurrency(c.valor_total_contratacao)}</td>
	<td>${fmtCurrency(c.valor_total_realizado)}</td>
	${detalhes}
</tr>`;
		}).join("");

		var actionTh = canEdit ? "<th></th>" : "";
		container.innerHTML = `<div class="festa-table-scroll"><table class="festa-table"><thead><tr><th>Item</th><th>Valor cotado</th><th>Valor gasto</th>${actionTh}</tr></thead><tbody>${rows}</tbody></table></div>`;
		notifyDesignSystem();
		if (!canEdit) return;
		container.querySelectorAll("[data-fechamento-contratacao]").forEach(function (btn) {
			btn.addEventListener("click", function () { openContratacaoFechamentoDialog(parseInt(btn.dataset.fechamentoContratacao, 10)); });
		});
	}

	function setRealizadoContratacao(c) {
		document.getElementById("fechamento-contratacao-real-total").value = c.valor_total_realizado || "";
		document.getElementById("fechamento-contratacao-real-fornecedor").value = c.fornecedor_realizado || "";
		document.getElementById("fechamento-contratacao-real-obs").value = c.observacoes_realizado || "";
	}

	function openContratacaoFechamentoDialog(idx) {
		var dlg = document.getElementById("dialog-contratacao-fechamento");
		if (!dlg) return;
		dlg.dataset.contratacaoIdx = String(idx);
		var titleEl = document.getElementById("dialog-contratacao-fechamento-title");
		var blocoIdent = dlg.querySelector('[data-fechamento-block="identificacao"]');
		var blocoOrc = dlg.querySelector('[data-fechamento-block="orcamento"]');

		if (idx < 0) {
			titleEl.textContent = "Adicionar contratação sem previsão";
			blocoIdent.hidden = false;
			blocoOrc.hidden = true;
			document.getElementById("fechamento-contratacao-nome-item").value = "";
			setSelectValue("fechamento-contratacao-area", "", selectLabelFor(areasItems, "", "Sem área"));
			setRealizadoContratacao({});
		} else {
			var c = contratacoes[idx];
			titleEl.textContent = "Detalhes da contratação — " + (c.nome_item || "");
			blocoIdent.hidden = true;
			if (c.previsto !== false) {
				blocoOrc.hidden = false;
				var escolhida = (c.cotacoes || []).find(function (x) { return x.escolhida; });
				fechamentoSetText("fechamento-contratacao-orc-total", fmtCurrency(c.valor_total_contratacao));
				fechamentoSetText("fechamento-contratacao-orc-fornecedor", escolhida ? (escolhida.fornecedor || "—") : "—");
			} else {
				blocoOrc.hidden = true;
			}
			setRealizadoContratacao(c);
		}
		dlg.showModal();
	}

	function saveContratacaoFechamento() {
		var dlg = document.getElementById("dialog-contratacao-fechamento");
		var idx = parseInt(dlg.dataset.contratacaoIdx, 10);
		var dados = {
			valor_total_realizado: parseFloat(document.getElementById("fechamento-contratacao-real-total").value) || 0,
			fornecedor_realizado: (document.getElementById("fechamento-contratacao-real-fornecedor").value || "").trim(),
			observacoes_realizado: (document.getElementById("fechamento-contratacao-real-obs").value || "").trim(),
		};
		var request;
		if (idx < 0) {
			var nome = (document.getElementById("fechamento-contratacao-nome-item").value || "").trim();
			if (!nome) { toast("Informe o nome do item.", "error"); return; }
			dados.nome_item = nome;
			dados.area = getSelectValue("fechamento-contratacao-area");
			request = api("gris.api.festas.criar_contratacao_sem_previsao", { festa_name: festaName, dados_json: JSON.stringify(dados) });
		} else {
			request = api("gris.api.festas.salvar_realizado_contratacao", { contratacao_name: contratacoes[idx].name, dados_json: JSON.stringify(dados) });
		}
		var btn = document.getElementById("btn-fechamento-contratacao-salvar");
		btn.disabled = true;
		request
			.then(function () { dlg.close(); return refreshFestaData(); })
			.then(function () { toast("Fechamento salvo.", "success"); })
			.catch(function (err) { toast(err.message || "Erro ao salvar.", "error"); })
			.finally(function () { btn.disabled = false; });
	}

	// ── Barracas ──

	function renderBarracaItens(produtosBarraca, bi, key) {
		if (!produtosBarraca.length) {
			return '<p class="text-sm text-muted-foreground festa-equipe-empty">Nenhum produto nesta barraca.</p>';
		}
		var itens = produtosBarraca.map(function (p, j) {
			var preco = Number(p.preco_venda) || 0;
			var qtdEsp = Number(p["qtd_" + key]) || 0;
			var qtdReal = Number(p.qtd_realizada_vendas) || 0;
			var qtdInput = canEdit
				? `<input class="input festa-compact-input" type="number" min="0" step="0.001" data-item-barraca="${bi}" data-item-idx="${j}" data-item-produto="${escHtml(p.name)}" data-item-preco="${preco}" value="${escHtml(p.qtd_realizada_vendas || "")}">`
				: fmtNum(qtdReal);
			return `
<tr>
	<td>${escHtml(p.nome_produto)}</td>
	<td>${fmtCurrency(preco)}</td>
	<td>${fmtNum(qtdEsp)}</td>
	<td>${fmtCurrency(qtdEsp * preco)}</td>
	<td>${qtdInput}</td>
	<td data-item-total="${bi}-${j}">${fmtCurrency(qtdReal * preco)}</td>
</tr>`;
		}).join("");
		return `<table class="festa-table festa-edit-table"><thead><tr><th>Item</th><th>Valor individual</th><th>Qtd esperada</th><th>Total esperado</th><th>Qtd realizada</th><th>Total arrecadado</th></tr></thead><tbody>${itens}</tbody></table>`;
	}

	function renderFechamentoBarracas() {
		var container = document.getElementById("fechamento-barracas-container");
		if (!container) return;
		if (!barracas.length) { container.innerHTML = fechamentoEmpty("Nenhuma barraca cadastrada."); return; }

		var key = fechamentoCenarioKey();
		var espMap = {};
		(window._festaData.receitasPorBarraca || []).forEach(function (r) { espMap[r.name] = r["esperado_" + key] || 0; });

		var rows = barracas.map(function (b, i) {
			var produtosBarraca = produtos.filter(function (p) { return p.barraca === b.name; });
			var realizadoCalc = produtosBarraca.reduce(function (s, p) { return s + (Number(p.valor_total_arrecadado) || 0); }, 0);
			var realVal = Number(b.valor_arrecadado_realizado_real) || 0;
			var realInput = canEdit
				? `<input class="input festa-compact-input" type="text" inputmode="decimal" data-barraca-real="${i}" value="${realVal ? escHtml(fmtCurrency(realVal)) : ""}">`
				: fmtCurrency(b.valor_arrecadado_realizado_real);
			var salvarBtn = canEdit ? `<button type="button" class="btn-sm-outline" data-barraca-salvar="${i}">Salvar</button>` : "";
			return `
<tr>
	<td><button type="button" class="btn-sm-ghost festa-actions-btn" data-barraca-toggle="${i}" aria-expanded="false" aria-label="Expandir itens">${lucideSvg("chevron-right")}</button></td>
	<td>${escHtml(b.nome_barraca)}</td>
	<td>${fmtCurrency(espMap[b.name] || 0)}</td>
	<td data-barraca-realizado="${i}">${fmtCurrency(realizadoCalc)}</td>
	<td>${realInput}</td>
	<td class="festa-table-actions">${salvarBtn}</td>
</tr>
<tr data-barraca-detail="${i}" hidden><td colspan="6">${renderBarracaItens(produtosBarraca, i, key)}</td></tr>`;
		}).join("");

		container.innerHTML = `<div class="festa-table-scroll"><table class="festa-table"><thead><tr><th></th><th>Barraca</th><th>Arrecadação esperada</th><th>Arrecadação realizada</th><th>Realizado real</th><th></th></tr></thead><tbody>${rows}</tbody></table></div>`;
		notifyDesignSystem();
		wireFechamentoBarracas(container);
	}

	function wireFechamentoBarracas(container) {
		container.querySelectorAll("[data-barraca-toggle]").forEach(function (btn) {
			btn.addEventListener("click", function () {
				var bi = btn.dataset.barracaToggle;
				var detail = container.querySelector('[data-barraca-detail="' + bi + '"]');
				if (!detail) return;
				var open = detail.hidden;
				detail.hidden = !open;
				btn.setAttribute("aria-expanded", open ? "true" : "false");
				btn.innerHTML = open ? lucideSvg("chevron-down") : lucideSvg("chevron-right");
			});
		});
		if (!canEdit) return;

		// "Realizado real": campo editável formatado como moeda (BRL). Mostra o
		// valor cru durante a edição e reformata como moeda ao perder o foco.
		container.querySelectorAll("[data-barraca-real]").forEach(function (inp) {
			inp.addEventListener("focus", function () {
				var n = parseCurrencyBR(inp.value);
				inp.value = n ? String(n).replace(".", ",") : "";
				inp.select();
			});
			inp.addEventListener("blur", function () {
				var n = parseCurrencyBR(inp.value);
				inp.value = n ? fmtCurrency(n) : "";
			});
		});

		container.querySelectorAll("[data-item-barraca]").forEach(function (inp) {
			inp.addEventListener("input", function () {
				var bi = inp.dataset.itemBarraca;
				var preco = Number(inp.dataset.itemPreco) || 0;
				var totalCell = container.querySelector('[data-item-total="' + bi + "-" + inp.dataset.itemIdx + '"]');
				if (totalCell) totalCell.textContent = fmtCurrency((parseFloat(inp.value) || 0) * preco);
				var sum = 0;
				container.querySelectorAll('[data-item-barraca="' + bi + '"]').forEach(function (o) {
					sum += (parseFloat(o.value) || 0) * (Number(o.dataset.itemPreco) || 0);
				});
				var realizadoCell = container.querySelector('[data-barraca-realizado="' + bi + '"]');
				if (realizadoCell) realizadoCell.textContent = fmtCurrency(sum);
			});
		});

		container.querySelectorAll("[data-barraca-salvar]").forEach(function (btn) {
			btn.addEventListener("click", function () {
				var bi = btn.dataset.barracaSalvar;
				var barraca = barracas[parseInt(bi, 10)];
				var itens = [];
				container.querySelectorAll('[data-item-barraca="' + bi + '"]').forEach(function (o) {
					itens.push({ produto: o.dataset.itemProduto, qtd_realizada: parseFloat(o.value) || 0 });
				});
				var realEl = container.querySelector('[data-barraca-real="' + bi + '"]');
				var dados = { valor_realizado_real: realEl ? parseCurrencyBR(realEl.value) : 0, itens: itens };
				btn.disabled = true;
				api("gris.api.festas.salvar_fechamento_barraca", { festa_name: festaName, barraca_name: barraca.name, dados_json: JSON.stringify(dados) })
					.then(function () { return refreshFestaData(); })
					.then(function () { toast("Barraca salva.", "success"); })
					.catch(function (err) { toast(err.message || "Erro ao salvar barraca.", "error"); })
					.finally(function () { btn.disabled = false; });
			});
		});
	}

	// ── Convites (resumo de fechamento) ──

	function renderFechamentoConvites() {
		var container = document.getElementById("fechamento-convites-container");
		if (!container) return;

		var opcoes = convitesDashboard.opcoes || [];
		var totais = convitesDashboard.totais || {};
		var qtdMap = totais.qtd_por_opcao || {};
		var valMap = totais.valor_por_opcao || {};
		var doacoes = Number(totais.total_doacoes_valor || 0);

		if (!opcoes.length && doacoes <= 0) {
			container.innerHTML = fechamentoEmpty("Nenhum convite cadastrado.");
			return;
		}

		var totalQtd = 0;
		var totalVal = 0;
		var rows = opcoes.map(function (o) {
			var qtd = Number(qtdMap[o.name] || 0);
			var val = Number(valMap[o.name] || 0);
			totalQtd += qtd;
			totalVal += val;
			return `
<tr>
	<td>${escHtml(o.nome_convite || o.name)}</td>
	<td>${fmtNum(qtd)}</td>
	<td>${fmtCurrency(val)}</td>
</tr>`;
		}).join("");

		var totalRow = `
<tr class="festa-fechamento-total-row">
	<td>Total</td>
	<td>${fmtNum(totalQtd)}</td>
	<td>${fmtCurrency(totalVal)}</td>
</tr>`;

		var doacoesRow = doacoes > 0 ? `
<tr>
	<td>Doações</td>
	<td>—</td>
	<td>${fmtCurrency(doacoes)}</td>
</tr>` : "";

		container.innerHTML = `<div class="festa-table-scroll"><table class="festa-table"><thead><tr><th>Tipo de convite</th><th>Qtd. (Pago)</th><th>Valor arrecadado</th></tr></thead><tbody>${rows}${totalRow}${doacoesRow}</tbody></table></div>`;
		notifyDesignSystem();
	}

	// ── Resumo (entradas × saídas × resultado) ──

	function computeFechamentoResumo() {
		var totais = convitesDashboard.totais || {};
		var valMap = totais.valor_por_opcao || {};
		var convitesTotal = (convitesDashboard.opcoes || []).reduce(function (s, o) {
			return s + Number(valMap[o.name] || 0);
		}, 0);
		var doacoes = Number(totais.total_doacoes_valor || 0);
		var barracasLinhas = barracas.map(function (b) {
			return { label: b.nome_barraca || b.name, valor: Number(b.valor_arrecadado_realizado_real) || 0 };
		});
		var barracasTotal = barracasLinhas.reduce(function (s, r) { return s + r.valor; }, 0);
		var comprasTotal = compras.reduce(function (s, c) { return s + (Number(c.valor_total_realizado) || 0); }, 0);
		var contratacoesTotal = contratacoes.reduce(function (s, c) { return s + (Number(c.valor_total_realizado) || 0); }, 0);
		var entradas = convitesTotal + doacoes + barracasTotal;
		var saidas = comprasTotal + contratacoesTotal;
		return {
			convitesTotal: convitesTotal,
			doacoes: doacoes,
			barracasLinhas: barracasLinhas,
			comprasTotal: comprasTotal,
			contratacoesTotal: contratacoesTotal,
			entradas: entradas,
			saidas: saidas,
			resultado: entradas - saidas,
		};
	}

	function fechamentoResumoGroup(label) {
		return '<tr class="festa-resumo-group"><td colspan="2">' + escHtml(label) + "</td></tr>";
	}

	function fechamentoResumoRow(label, valor, opts) {
		opts = opts || {};
		var rowCls = opts.total ? ' class="festa-cenarios-row--total"' : "";
		var cellCls = opts.cellClass || "";
		if (opts.negativeIsDanger) {
			cellCls = Number(valor) < 0 ? "festa-cenarios-cell--danger" : "festa-cenarios-cell--success";
		}
		var cellAttr = ' class="festa-resumo-value' + (cellCls ? " " + cellCls : "") + '"';
		return "<tr" + rowCls + '><td class="festa-cenarios-label">' + escHtml(label) +
			"</td><td" + cellAttr + ">" + fmtCurrency(valor) + "</td></tr>";
	}

	function renderFechamentoResumo() {
		var container = document.getElementById("fechamento-resumo-container");
		if (!container) return;
		var r = computeFechamentoResumo();

		var entradasRows =
			fechamentoResumoRow("Convites", r.convitesTotal) +
			(r.doacoes > 0 ? fechamentoResumoRow("Doações", r.doacoes) : "") +
			r.barracasLinhas.map(function (b) { return fechamentoResumoRow(b.label, b.valor); }).join("");

		var html = '<table class="festa-cenarios-table festa-resumo-table"><tbody>';
		html += fechamentoResumoGroup("Entradas");
		html += entradasRows;
		html += fechamentoResumoRow("Total de entradas", r.entradas, { total: true, cellClass: "festa-cenarios-cell--success" });
		html += fechamentoResumoGroup("Saídas");
		html += fechamentoResumoRow("Compras", r.comprasTotal);
		html += fechamentoResumoRow("Contratações", r.contratacoesTotal);
		html += fechamentoResumoRow("Total de saídas", r.saidas, { total: true, cellClass: "festa-cenarios-cell--danger" });
		html += fechamentoResumoRow("Resultado", r.resultado, { total: true, negativeIsDanger: true });
		html += "</tbody></table>";
		container.innerHTML = html;

		// Mantém o gráfico em sincronia quando já estiver inicializado/visível.
		if (chartFechamentoResumoInstance) renderFechamentoWaterfall();
	}

	function renderFechamentoWaterfall() {
		var el = document.getElementById("chart-fechamento-resumo");
		if (!el) return;
		ensureECharts().then(function () {
			if (!chartFechamentoResumoInstance) {
				chartFechamentoResumoInstance = window.echarts.init(el);
				window.addEventListener("resize", function () {
					if (chartFechamentoResumoInstance) chartFechamentoResumoInstance.resize();
				});
			}
			var r = computeFechamentoResumo();
			var E = r.entradas, S = r.saidas, R = r.resultado;
			var cats = ["Entradas", "Saídas", "Resultado"];
			var COR_ENTRADA = "#009E73";
			var COR_SAIDA = "#D55E00";
			var cores = [COR_ENTRADA, COR_SAIDA, R >= 0 ? COR_ENTRADA : COR_SAIDA];
			// Cada barra é desenhada como retângulo flutuante [início, fim] via custom
			// series — robusto inclusive quando o Resultado é negativo.
			// value = [índice da categoria, início, fim, valor exibido]
			var dados = [
				{ value: [0, 0, E, E] },
				{ value: [1, E, R, S] },
				{ value: [2, 0, R, R] },
			];

			chartFechamentoResumoInstance.setOption({
				aria: { enabled: true },
				tooltip: {
					trigger: "item",
					formatter: function (p) {
						var i = p.value[0];
						return cats[i] + "<br/>" + fmtMoeda(p.value[3]);
					},
				},
				grid: { left: 16, right: 24, top: 32, bottom: 48, containLabel: true },
				xAxis: { type: "category", data: cats },
				yAxis: {
					type: "value",
					name: "Valor (R$)",
					nameLocation: "middle",
					nameGap: 56,
					nameRotate: 90,
					nameTextStyle: { fontSize: 12 },
					axisLabel: {
						formatter: function (v) { return "R$ " + Number(v).toLocaleString("pt-BR"); },
					},
				},
				series: [{
					type: "custom",
					encode: { x: 0, y: [1, 2] },
					data: dados,
					renderItem: function (params, api) {
						var catIndex = api.value(0);
						var pStart = api.coord([catIndex, api.value(1)]);
						var pEnd = api.coord([catIndex, api.value(2)]);
						var bandWidth = api.size([1, 0])[0];
						var width = Math.min(bandWidth * 0.5, 64);
						var yTop = Math.min(pStart[1], pEnd[1]);
						var height = Math.abs(pStart[1] - pEnd[1]);
						return {
							type: "group",
							children: [
								{
									type: "rect",
									shape: { x: pStart[0] - width / 2, y: yTop, width: width, height: height, r: [4, 4, 0, 0] },
									style: { fill: cores[catIndex] },
								},
								{
									type: "text",
									style: {
										text: fmtMoeda(api.value(3)),
										x: pStart[0],
										y: yTop - 6,
										textAlign: "center",
										textVerticalAlign: "bottom",
										fontSize: 12,
										fontWeight: 600,
										fill: "#1f2937",
									},
								},
							],
						};
					},
				}],
			}, true);
		}).catch(function (err) {
			toast(err.message || "Erro ao carregar gráficos.", "error");
		});
	}

	function initFechamento() {
		renderFechamentoTab();

		// O gráfico do Resumo só é renderizado quando a seção é aberta — assim ele
		// nasce com largura correta (a aba Fechamento inicia oculta).
		var resumoDetails = document.getElementById("fechamento-resumo-details");
		if (resumoDetails) {
			resumoDetails.addEventListener("toggle", function () {
				if (resumoDetails.open) renderFechamentoWaterfall();
			});
		}

		if (!canEdit) return;

		document.querySelectorAll("[data-action='add-compra-sem-previsao']").forEach(function (btn) {
			btn.addEventListener("click", function () { openCompraFechamentoDialog(-1); });
		});
		document.querySelectorAll("[data-action='add-contratacao-sem-previsao']").forEach(function (btn) {
			btn.addEventListener("click", function () { openContratacaoFechamentoDialog(-1); });
		});

		var usadoEl = document.querySelector("#fechamento-compra-usado-produtos input[type='checkbox']");
		if (usadoEl) usadoEl.addEventListener("change", updateFechamentoCompraUsosVisibility);

		var addUso = document.getElementById("btn-fechamento-compra-add-uso");
		if (addUso) addUso.addEventListener("click", function () {
			readFechamentoCompraUsos();
			fechamentoCompraUsos.push({ produto: "", quantidade_usada: 0, unidade_medida_uso: "unidade" });
			renderFechamentoCompraUsos();
		});

		var btnCompra = document.getElementById("btn-fechamento-compra-salvar");
		if (btnCompra) btnCompra.addEventListener("click", saveCompraFechamento);
		var btnContr = document.getElementById("btn-fechamento-contratacao-salvar");
		if (btnContr) btnContr.addEventListener("click", saveContratacaoFechamento);
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
		initFechamento();
		initConvitesTab();
		initEquipeTriggers();
	});
})();

// ─── Kanban de tarefas da festa ─────────────────────────────────────────────
// Reutiliza a API genérica de quadros (gris.api.gestao_de_tarefas.*), que é
// keyed por Board e impõe a permissão de Board no backend: qualquer integrante
// da festa presente em `usuarios_autorizados` pode editar o quadro.
(function () {
	"use strict";

	const METHODS = {
		bootstrap: "gris.api.gestao_de_tarefas.quadros.bootstrap_quadro",
		saveTask: "gris.api.gestao_de_tarefas.quadros.salvar_tarefa_quadro",
		updateStatus: "gris.api.gestao_de_tarefas.quadros.atualizar_status_quadro",
		getComments: "gris.api.gestao_de_tarefas.minhas_tarefas.get_comentarios",
		addComment: "gris.api.gestao_de_tarefas.minhas_tarefas.adicionar_comentario",
		editComment: "gris.api.gestao_de_tarefas.minhas_tarefas.editar_comentario",
		deleteComment: "gris.api.gestao_de_tarefas.minhas_tarefas.apagar_comentario",
	};

	function callApi(method, args = {}) {
		return new Promise((resolve, reject) => {
			frappe.call({
				method,
				args,
				callback: (r) => resolve(r.message || {}),
				error: (err) => reject(err),
			});
		});
	}

	function $(id) {
		return document.getElementById(id);
	}

	function init() {
		const board = ($("userBoardName")?.value || "").trim();
		if (!board || !$("taskKanban")) return;
		if (typeof frappe === "undefined" || !frappe.call || !window.GrisKanbanTarefas) {
			setTimeout(init, 100);
			return;
		}

		const kanban = new window.GrisKanbanTarefas("#taskKanban", {
			mode: "projeto",
			currentUser: $("currentUser")?.value || "",
			currentUserFullName: $("currentUserFullName")?.value || "",
			canEdit: true,
			onLoad: async () => {
				const data = await callApi(METHODS.bootstrap, { board_name: board });
				return {
					tarefas: data.tarefas || [],
					responsavelOptions: data.responsavel_options || [],
				};
			},
			onSaveTask: async (payload) => {
				const data = await callApi(METHODS.saveTask, { tarefa: { ...payload, board } });
				return { tarefas: data.tarefas || [] };
			},
			onMoveTask: async (tarefaName, status) => {
				const data = await callApi(METHODS.updateStatus, { tarefa_name: tarefaName, status });
				return { tarefas: data.tarefas || [] };
			},
			onLoadComments: async (tarefaName) => {
				const data = await callApi(METHODS.getComments, { tarefa_name: tarefaName });
				return { comentarios: data.comentarios || [] };
			},
			onAddComment: async (tarefaName, texto) => {
				const data = await callApi(METHODS.addComment, { tarefa_name: tarefaName, texto });
				return { comentarios: data.comentarios || [] };
			},
			onEditComment: async (commentName, texto) => {
				const data = await callApi(METHODS.editComment, { comentario_name: commentName, texto });
				return { comentarios: data.comentarios || [] };
			},
			onDeleteComment: async (commentName) => {
				const data = await callApi(METHODS.deleteComment, { comentario_name: commentName });
				return { comentarios: data.comentarios || [] };
			},
		});

		kanban.refresh();
	}

	if (document.readyState === "loading") {
		document.addEventListener("DOMContentLoaded", init);
	} else {
		init();
	}
})();
