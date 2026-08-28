// Página /financeiro/contas — modais HTML5 <dialog>, conciliação Infinitepay e CRUD de carteiras
// Tudo encapsulado em um único IIFE para evitar redeclaração de const caso o script seja carregado mais de uma vez.
(function () {
	"use strict";

	function qs(id) {
		return document.getElementById(id);
	}
	function openDialog(id) {
		const dlg = qs(id);
		if (dlg && typeof dlg.showModal === "function" && !dlg.open) dlg.showModal();
	}
	function closeDialog(id) {
		const dlg = qs(id);
		if (dlg && dlg.open) dlg.close();
	}

	// ----- helpers para o select do design system (basecoat) -----
	// Lê o valor atual de um select do design system; também aceita <select>/<input> nativo.
	function selectValue(id) {
		const root = qs(id);
		if (!root) return "";
		if (root.tagName === "SELECT" || root.tagName === "INPUT") return root.value || "";
		const input = root.querySelector('input[type="hidden"][name]');
		return input ? input.value || "" : "";
	}

	// Reconstrói as options de um select do design system e força o basecoat a re-inicializar.
	// Necessário para selects cujas opções vêm de chamada assíncrona (ex.: usuários, centros de custo).
	function rebuildSelect(selectId, items, currentValue) {
		const root = qs(selectId);
		if (!root) return;
		const listbox = root.querySelector('[role="listbox"]');
		const labelSpan = root.querySelector('button[aria-haspopup="listbox"] .truncate');
		const hidden = root.querySelector('input[type="hidden"][name]');
		if (!listbox) return;
		listbox.innerHTML = items
			.map((it, i) => {
				const isSel = currentValue && it.value === currentValue;
				const sel = isSel ? ' aria-selected="true"' : "";
				return `<div id="${selectId}-items-${i + 1}" role="option" data-value="${
					it.value || ""
				}"${sel}>${it.label || ""}</div>`;
			})
			.join("");
		const selected = items.find((it) => it.value === currentValue) ||
			items[0] || { label: "", value: "" };
		if (labelSpan) labelSpan.textContent = selected.label || "";
		if (hidden) hidden.value = currentValue || selected.value || "";
		// Remove flag de inicializado e clona o nó para que o MutationObserver do basecoat re-init.
		root.removeAttribute("data-select-initialized");
		const clone = root.cloneNode(true);
		root.replaceWith(clone);
	}

	// ===== Conciliação Infinitepay =====
	window._extratoFileUrl = null;
	window._vendasFileUrl = null;
	window._recebimentosFileUrl = null;

	function checkShowConciliarBtn() {
		const btn = qs("btnConciliarInfinitepay");
		if (!btn) return;
		if (window._extratoFileUrl && window._vendasFileUrl && window._recebimentosFileUrl) {
			btn.classList.remove("hidden");
			btn.disabled = false;
		} else {
			btn.classList.add("hidden");
			btn.disabled = true;
		}
	}

	window.enviarArquivosImportados = function () {
		if (!window._extratoFileUrl || !window._vendasFileUrl || !window._recebimentosFileUrl) {
			frappe.msgprint(__("Faça o upload dos três arquivos antes de enviar."));
			return;
		}
		const loadingIndicator = qs("contas-infinitepay-loading-indicator");
		const btnConciliar = qs("btnConciliarInfinitepay");
		if (loadingIndicator) loadingIndicator.classList.remove("hidden");
		if (btnConciliar) btnConciliar.disabled = true;

		frappe.call({
			method: "gris.www.financeiro.contas.process_uploaded_files",
			args: {
				extrato_file_url: window._extratoFileUrl,
				vendas_file_url: window._vendasFileUrl,
				recebimentos_file_url: window._recebimentosFileUrl,
			},
			callback: function (r) {
				if (loadingIndicator) loadingIndicator.classList.add("hidden");
				if (btnConciliar) btnConciliar.disabled = false;
				if (r && r.exc) {
					console.error("Erro process_uploaded_files", r.exc);
					frappe.msgprint(__("Erro ao processar: ver console."));
				} else {
					frappe.msgprint(r.message || "Arquivos enviados e processados!");
					frappe.show_alert({ message: "Conciliação concluída", indicator: "green" }, 5);
				}
			},
		});
	};

	function setupUploader(btnId, nomeId, checkId, allowedExt) {
		document.addEventListener("click", function (e) {
			const btn = e.target.closest("#" + btnId);
			if (!btn) return;
			if (typeof frappe === "undefined" || !frappe.ui || !frappe.ui.FileUploader) {
				frappe.msgprint(__("Uploader indisponível."));
				return;
			}
			new frappe.ui.FileUploader({
				allow_multiple: false,
				restrictions: { allowed_file_extensions: allowedExt, max_number_of_files: 1 },
				is_private: 0,
				options: ["Local"],
				on_success(file) {
					const nomeSpan = qs(nomeId);
					const checkSpan = qs(checkId);
					if (nomeSpan) {
						nomeSpan.textContent = file.file_name || file.name;
						nomeSpan.classList.remove("hidden");
					}
					if (checkSpan) {
						checkSpan.classList.remove("hidden");
					}
					if (btnId === "uploadExtratoBtn") window._extratoFileUrl = file.file_url;
					if (btnId === "uploadVendasBtn") window._vendasFileUrl = file.file_url;
					if (btnId === "uploadRecebimentosBtn")
						window._recebimentosFileUrl = file.file_url;
					checkShowConciliarBtn();
				},
			});
		});
	}

	const isImportInfinitepayPage =
		typeof window !== "undefined" &&
		window.location &&
		window.location.pathname &&
		window.location.pathname.startsWith("/financeiro/import_intinitepay");
	if (!isImportInfinitepayPage) {
		setupUploader("uploadExtratoBtn", "nomeExtratoInfinitepay", "checkExtratoInfinitepay", [
			"ofx",
		]);
		setupUploader("uploadVendasBtn", "nomeVendasInfinitepay", "checkVendasInfinitepay", [
			"csv",
		]);
		setupUploader(
			"uploadRecebimentosBtn",
			"nomeRecebimentosInfinitepay",
			"checkRecebimentosInfinitepay",
			["csv"],
		);
	}

	// ===== Modal de detalhe / nova carteira / nova instituição =====
	window.fecharNovaInstituicaoModal = function () {
		closeDialog("novaInstituicaoModal");
	};
	window.fecharNovaCarteiraModal = function () {
		closeDialog("novaCarteiraModal");
	};
	window.fecharCarteiraModal = function () {
		closeDialog("carteiraDetalheModal");
	};
	window.fecharImportarDadosModal = function () {
		closeDialog("importarDadosModal");
	};

	const carteiraModal = qs("carteiraDetalheModal");

	function fillAndOpen(btn) {
		const nome = btn.dataset.nome || "";
		const inst = btn.dataset.instituicao || "";
		const descricao = btn.dataset.descricao || "";
		const responsavel = btn.dataset.responsavel || "—";
		const centro = btn.dataset.centroCusto || "—";
		const pix = btn.dataset.chavePix || "—";
		const saldo = btn.dataset.saldo || "—";
		const dataAtualizacao = btn.dataset.dataAtualizacao || "—";

		qs("carteiraModalTitulo").textContent = nome;
		const instSpan = qs("carteiraModalInstituicao");
		instSpan.className = "badge";
		instSpan.textContent = inst || "—";
		qs("carteiraModalDescricao").textContent = descricao || "Sem descrição.";
		qs("carteiraModalResponsavel").textContent = responsavel || "—";
		qs("carteiraModalCentro").textContent = centro || "—";
		qs("carteiraModalPix").textContent = pix || "—";
		qs("carteiraModalSaldo").textContent = saldo || "—";
		qs("carteiraModalData").textContent = dataAtualizacao || "—";
		openDialog("carteiraDetalheModal");
	}

	function setEditMode(on) {
		const campos = qs("carteiraEdicaoCampos");
		if (campos) campos.classList.toggle("hidden", !on);
		qs("btnEditarCarteira").classList.toggle("hidden", on);
		qs("btnSalvarCarteira").classList.toggle("hidden", !on);
		qs("btnCancelarEdicaoCarteira").classList.toggle("hidden", !on);
	}

	let _cacheCentro = null,
		_cacheUsers = null;

	function extractResults(r) {
		if (!r) return [];
		if (Array.isArray(r.results)) return r.results;
		if (r.message) {
			if (Array.isArray(r.message)) return r.message;
			if (Array.isArray(r.message.results)) return r.message.results;
		}
		return [];
	}

	async function fetchCentroCustoOptions() {
		if (_cacheCentro) return _cacheCentro;
		try {
			const r = await frappe.call({
				method: "frappe.desk.search.search_link",
				args: { doctype: "Centro de Custo", txt: "", page_length: 500 },
			});
			const raw = extractResults(r);
			_cacheCentro = raw
				.map((it) => ({
					value: it.value || it.name || "",
					label: it.value || it.name || "",
				}))
				.filter((it) => it.value);
		} catch (e) {
			console.warn("Erro centros de custo", e);
			_cacheCentro = [];
		}
		return _cacheCentro;
	}

	async function fetchUsers() {
		if (_cacheUsers) return _cacheUsers;
		try {
			const r = await frappe.call({
				method: "frappe.desk.search.search_link",
				args: { doctype: "User", txt: "", page_length: 500 },
			});
			const raw = extractResults(r);
			_cacheUsers = raw
				.map((it) => ({
					value: it.value || it.name || "",
					label: (it.description || it.value || it.name || "").replace(/<.*?>/g, ""),
				}))
				.filter((it) => it.value && !["Guest", "Administrator"].includes(it.value));
		} catch (e) {
			console.warn("Erro usuários", e);
			_cacheUsers = [];
		}
		return _cacheUsers;
	}

	function buildItems(list, placeholder) {
		const items = [{ label: placeholder || "—", value: "" }];
		return items.concat(list.map((it) => ({ label: it.label || it.value, value: it.value })));
	}

	async function salvarCampos() {
		const name = carteiraModal && carteiraModal.dataset.carteiraName;
		if (!name) return;
		const updates = {
			responsavel: selectValue("carteiraInputResponsavel") || "",
			centro_de_custo: selectValue("carteiraInputCentro") || "",
			chave_pix: qs("carteiraInputPix").value || "",
			descricao: qs("carteiraInputDescricao").value || "",
		};
		for (const [field, value] of Object.entries(updates)) {
			try {
				await frappe.call({
					method: "frappe.client.set_value",
					args: { doctype: "Carteira", name, fieldname: field, value },
				});
			} catch (e) {
				frappe.msgprint("Erro ao salvar " + field);
				console.error(e);
			}
		}
		qs("carteiraModalResponsavel").textContent = updates.responsavel || "—";
		qs("carteiraModalCentro").textContent = updates.centro_de_custo || "—";
		qs("carteiraModalPix").textContent = updates.chave_pix || "—";
		qs("carteiraModalDescricao").textContent = updates.descricao || "Sem descrição.";
		setEditMode(false);
	}

	document.addEventListener("click", function (e) {
		// Botões com filhos (SVG/span): usar closest para encontrar o ID-alvo
		const importarBtn = e.target.closest(".importar-dados-btn");
		if (importarBtn) {
			const nome = (importarBtn.dataset.nome || "").trim().toLowerCase();
			if (nome === "infinitepay") {
				window.location.href = "/financeiro/import_intinitepay";
				return;
			}
			if (nome === "portão 3" || nome === "portao 3") {
				window.location.href = "/financeiro/import_portao3";
				return;
			}
			if (nome === "btg empresas" || nome === "btgempresas" || nome === "btg") {
				window.location.href = "/financeiro/import_btg_empresas";
				return;
			}
			frappe.msgprint(__("Funcionalidade em construção."));
			return;
		}

		const detalhesBtn = e.target.closest(".carteira-detalhes-btn");
		if (detalhesBtn) {
			fillAndOpen(detalhesBtn);
			if (carteiraModal) carteiraModal.dataset.carteiraName = detalhesBtn.dataset.name;
			qs("carteiraInputPix").value =
				detalhesBtn.dataset.chavePix && detalhesBtn.dataset.chavePix !== "—"
					? detalhesBtn.dataset.chavePix
					: "";
			qs("carteiraInputDescricao").value =
				detalhesBtn.dataset.descricao && detalhesBtn.dataset.descricao !== "Sem descrição."
					? detalhesBtn.dataset.descricao
					: "";
			setEditMode(false);
			return;
		}

		if (e.target.closest("#btnSalvarInstituicao")) {
			(async function () {
				const nome = qs("novaInstituicaoNome").value.trim();
				if (!nome) {
					frappe.msgprint(__("Informe o nome."));
					return;
				}
				try {
					const r = await frappe.call({
						method: "frappe.client.insert",
						args: { doc: { doctype: "Instituicao Financeira", nome: nome } },
					});
					const doc = (r && r.message) || r;
					if (doc && doc.name) {
						closeDialog("novaInstituicaoModal");
						frappe.show_alert({ message: "Instituição criada", indicator: "green" });
						setTimeout(() => window.location.reload(), 600);
					}
				} catch (err) {
					console.error(err);
					frappe.msgprint(__("Erro ao criar instituição."));
				}
			})();
			return;
		}

		if (e.target.closest("#btnNovaCarteira")) {
			["nc_nome", "nc_pix", "nc_descricao"].forEach((id) => {
				const el = qs(id);
				if (el) el.value = "";
			});
			Promise.all([fetchCentroCustoOptions(), fetchUsers()]).then(([centros, users]) => {
				rebuildSelect("nc_centro", buildItems(centros, "Selecione…"), "");
				rebuildSelect("nc_responsavel", buildItems(users, "Selecione…"), "");
			});
			openDialog("novaCarteiraModal");
			return;
		}

		if (e.target.closest("#btnSalvarCarteiraNova")) {
			(async function () {
				const nome = qs("nc_nome").value.trim();
				const instituicao = (selectValue("nc_instituicao") || "").trim();
				const descricao = qs("nc_descricao").value.trim();
				const responsavel = (selectValue("nc_responsavel") || "").trim();
				const centro = (selectValue("nc_centro") || "").trim();
				const pix = qs("nc_pix").value.trim();
				if (!nome || !instituicao || !descricao || !responsavel || !centro) {
					frappe.msgprint(__("Preencha todos os campos obrigatórios."));
					return;
				}
				try {
					const r = await frappe.call({
						method: "frappe.client.insert",
						args: {
							doc: {
								doctype: "Carteira",
								nome,
								instituicao_financeira: instituicao,
								descricao,
								responsavel,
								centro_de_custo: centro,
								chave_pix: pix,
							},
						},
					});
					const doc = (r && r.message) || r;
					if (doc && doc.name) {
						closeDialog("novaCarteiraModal");
						frappe.show_alert({ message: "Carteira criada", indicator: "green" });
						setTimeout(() => window.location.reload(), 600);
					}
				} catch (err) {
					console.error(err);
					frappe.msgprint(__("Erro ao criar carteira."));
				}
			})();
			return;
		}

		if (e.target.closest("#btnEditarCarteira")) {
			setEditMode(true);
			Promise.all([fetchCentroCustoOptions(), fetchUsers()]).then(([centros, users]) => {
				const curCentro = qs("carteiraModalCentro").textContent.trim();
				const curResp = qs("carteiraModalResponsavel").textContent.trim();
				rebuildSelect(
					"carteiraInputCentro",
					buildItems(centros, "—"),
					curCentro === "—" ? "" : curCentro,
				);
				rebuildSelect(
					"carteiraInputResponsavel",
					buildItems(users, "—"),
					curResp === "—" ? "" : curResp,
				);
			});
			return;
		}
		if (e.target.closest("#btnCancelarEdicaoCarteira")) {
			setEditMode(false);
			return;
		}
		if (e.target.closest("#btnSalvarCarteira")) {
			salvarCampos();
			return;
		}

		// Desativar carteira
		if (e.target.closest("#btnDesativarCarteira")) {
			const name = carteiraModal && carteiraModal.dataset.carteiraName;
			const nomeTitulo = qs("carteiraModalTitulo")
				? qs("carteiraModalTitulo").textContent.trim()
				: name;
			if (!name) return;
			if (
				!confirm(
					`Desativar a carteira "${nomeTitulo}"?\n\nEla deixará de aparecer no portal. É possível reativá-la pelo Desk.`,
				)
			)
				return;
			frappe.call({
				method: "gris.api.financeiro.contas.desativar",
				args: { doctype: "Carteira", name },
				callback: function (r) {
					if (r && r.exc) {
						frappe.msgprint(__("Erro ao desativar carteira."));
						return;
					}
					closeDialog("carteiraDetalheModal");
					frappe.show_alert({ message: "Carteira desativada", indicator: "orange" }, 4);
					setTimeout(() => window.location.reload(), 600);
				},
			});
			return;
		}

		// Desativar instituição financeira
		const desativarInstBtn = e.target.closest(".desativar-instituicao-btn");
		if (desativarInstBtn) {
			const name = desativarInstBtn.dataset.name;
			const nome = desativarInstBtn.dataset.nome || name;
			if (!name) return;
			if (
				!confirm(
					`Desativar a instituição "${nome}"?\n\nEla deixará de aparecer no portal. É possível reativá-la pelo Desk.`,
				)
			)
				return;
			frappe.call({
				method: "gris.api.financeiro.contas.desativar",
				args: { doctype: "Instituicao Financeira", name },
				callback: function (r) {
					if (r && r.exc) {
						frappe.msgprint(__("Erro ao desativar instituição."));
						return;
					}
					frappe.show_alert(
						{ message: "Instituição desativada", indicator: "orange" },
						4,
					);
					setTimeout(() => window.location.reload(), 600);
				},
			});
			return;
		}
	});
})();
