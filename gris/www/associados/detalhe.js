// detalhe.js - lógica JS da página detalhe do Associado
(function () {
	document.addEventListener("DOMContentLoaded", function () {
		const editableSelectors = "input[name], select[name]";
		const changed = {}; // field -> value
		const saveBtn = document.getElementById("btn-salvar");
		const afastarBtn = document.getElementById("btn-afastar");
		const createUserBtn = document.getElementById("btn-criar-usuario");
		const flagsEl = document.getElementById("assoc-flags");
		const associadoName = flagsEl?.dataset.name || "";
		const CAN_EDIT = flagsEl?.dataset.canEdit === "1";
		const HAS_OPEN_HIST = flagsEl?.dataset.hasOpen === "1";

		// Guardian visibility - read values from hidden inputs or native inputs
		function getFieldValue(name) {
			return (
				document.querySelector(`input[type="hidden"][name="${name}"]`)?.value ||
				document.querySelector(`input[name="${name}"]:not([type="hidden"])`)?.value ||
				""
			).trim();
		}

		function updateGuardianVisibility() {
			const paisDivVal = getFieldValue("pais_divorciados");
			const tipoGuardaVal = getFieldValue("tipo_guarda");
			const show =
				paisDivVal === "Sim" &&
				tipoGuardaVal &&
				tipoGuardaVal.toLowerCase() === "unilateral";
			document.querySelectorAll("[data-guardian-field]").forEach((el) => {
				el.style.display = show ? "" : "none";
			});
		}

		// Attach change listeners to native selects (for non-Basecoat selects)
		["pais_divorciados", "tipo_guarda"].forEach((n) => {
			const el = document.querySelector(`select[name="${n}"]`);
			if (el) {
				el.addEventListener("change", updateGuardianVisibility);
			}
		});
		updateGuardianVisibility();

		function markChanged(field, value) {
			if (!CAN_EDIT) return;
			changed[field] = value;
			if (saveBtn && saveBtn.hidden) saveBtn.hidden = false;
		}

		// Configure form fields
		if (!CAN_EDIT) {
			document.querySelectorAll(editableSelectors).forEach((el) => {
				el.setAttribute("disabled", "disabled");
			});
			if (saveBtn) saveBtn.remove();
		} else {
			// Listen to native inputs and selects
			document.querySelectorAll(editableSelectors).forEach((el) => {
				if (el.disabled) return;
				el.addEventListener("change", () => {
					let val;
					if (el.type === "checkbox") val = el.checked ? 1 : 0;
					else val = el.value;
					markChanged(el.name, val);
				});
			});
		}

		// Listen to Basecoat select changes via delegated click on [role="option"]
		document.addEventListener("click", (e) => {
			const opt = e.target.closest('[role="option"]');
			if (!opt) return;
			const selectEl = opt.closest(".select");
			if (!selectEl) return;
			// Await select.js to update the hidden input
			setTimeout(() => {
				const hidden = selectEl.querySelector('input[type="hidden"]');
				if (hidden?.name) markChanged(hidden.name, hidden.value);
				updateGuardianVisibility(); // re-evaluate guardian visibility
			}, 0);
		});

		function notify(msg, cls = "info") {
			if (window.frappe?.show_alert) {
				frappe.show_alert({ message: msg, indicator: cls });
			} else {
				console.log(msg);
			}
		}

		const createUserConfirmDlg = document.getElementById("modalCreateUserConfirm");
		const createUserResultDlg = document.getElementById("modalCreateUserResult");
		const confirmCreateUserBtn = document.getElementById("btn-confirm-create-user");
		const createUserResultBody = document.getElementById("create-user-result-body");

		function showCreateUserResult(bodyHtml) {
			if (!createUserResultDlg || !createUserResultBody) return;
			createUserResultBody.innerHTML = bodyHtml;
			createUserResultDlg.showModal();
		}

		if (createUserBtn) {
			createUserBtn.onclick = () => createUserConfirmDlg?.showModal();

			// Listener para confirmar criação
			if (confirmCreateUserBtn) {
				confirmCreateUserBtn.onclick = async () => {
					const originalConfirmText = confirmCreateUserBtn.textContent;
					const originalButtonText = createUserBtn.textContent;

					confirmCreateUserBtn.disabled = true;
					confirmCreateUserBtn.textContent = "Processando...";
					createUserBtn.disabled = true;
					createUserBtn.textContent = "Processando...";

					try {
						const response = await frappe.call({
							method: "gris.api.users.user_manager.create_associate_user_manually",
							args: { associate_name: associadoName },
						});

						createUserConfirmDlg?.close();

						const result = response.message || {};
						if (result.created) {
							showCreateUserResult(
								`<p style="margin: 0; color: hsl(var(--muted-foreground));">Usuário criado para <strong>${frappe.utils.escape_html(
									result.email || ""
								)}</strong>.</p>`
							);
							createUserBtn.remove();
						} else {
							showCreateUserResult(
								`<p style="margin: 0; color: hsl(var(--muted-foreground));">Já existe usuário para <strong>${frappe.utils.escape_html(
									result.email || ""
								)}</strong>.</p>`
							);
							createUserBtn.remove();
						}
					} catch (error) {
						createUserConfirmDlg?.close();
						showCreateUserResult(
							'<p style="margin: 0; color: hsl(var(--muted-foreground));">Não foi possível concluir a criação do usuário deste associado.</p>'
						);
					} finally {
						confirmCreateUserBtn.disabled = false;
						confirmCreateUserBtn.textContent = originalConfirmText;
						if (document.getElementById("btn-criar-usuario")) {
							createUserBtn.disabled = false;
							createUserBtn.textContent = originalButtonText;
						}
					}
				};
			}

			// Listener para botões de cancelar no dialog de criar usuário
			if (createUserConfirmDlg) {
				createUserConfirmDlg.querySelectorAll("[data-dialog-close]").forEach((btn) => {
					btn.addEventListener("click", () => createUserConfirmDlg?.close());
				});
			}
		}

		saveBtn?.addEventListener("click", () => {
			if (Object.keys(changed).length === 0) return;
			saveBtn.disabled = true;
			saveBtn.textContent = "Salvando...";
			frappe
				.call({
					method: "gris.api.members_portal.update_member",
					args: { name: associadoName, changes: JSON.stringify(changed) },
				})
				.then((r) => {
					saveBtn.disabled = false;
					saveBtn.textContent = "Salvar";
					if (r.message && r.message.success) {
						notify("Alterações salvas", "green");
						for (const k in changed) delete changed[k];
						saveBtn.hidden = true;
					} else {
						notify("Falha ao salvar", "red");
					}
				})
				.catch(() => {
					saveBtn.disabled = false;
					saveBtn.textContent = "Salvar";
					notify("Erro de comunicação", "red");
				});
		});

		// Afastar dialog
		const confirmAfastarDlg = document.getElementById("confirmAfastarDialog");
		const btnConfirmAfastar = document.getElementById("btn-confirm-afastar");

		afastarBtn?.addEventListener("click", () => {
			confirmAfastarDlg?.showModal();
		});

		btnConfirmAfastar?.addEventListener("click", () => {
			afastarBtn.disabled = true;
			afastarBtn.textContent = "Processando...";
			confirmAfastarDlg?.close();
			frappe
				.call({
					method: "gris.api.members_portal.set_member_leave",
					args: { name: associadoName },
				})
				.then((r) => {
					afastarBtn.disabled = false;
					afastarBtn.textContent = "Afastar Associado";
					if (r.message && r.message.success) {
						notify("Afastamento registrado", "orange");
						window.location.reload();
					} else {
						notify(
							r.message && r.message.message ? r.message.message : "Nada a afastar",
							"yellow"
						);
					}
				})
				.catch(() => {
					afastarBtn.disabled = false;
					afastarBtn.textContent = "Afastar Associado";
					notify("Erro ao afastar", "red");
				});
		});

		// Adicionar listeners para botões de cancelar nos diálogos
		confirmAfastarDlg?.querySelectorAll("[data-dialog-close]").forEach((btn) => {
			btn.addEventListener("click", () => confirmAfastarDlg?.close());
		});

		// ========== GERENCIAMENTO DE HISTÓRICO ==========
		const modalHistorico = document.getElementById("modalHistorico");
		const btnEditHistorico = document.getElementById("btn-edit-historico");
		const btnAddHistorico = document.getElementById("btn-add-historico");
		const btnSaveHistorico = document.getElementById("btn-save-historico");
		const historicoList = document.getElementById("historico-list");
		const confirmRemoveHistoricoDlg = document.getElementById("confirmRemoveHistoricoDialog");
		const btnConfirmRemoveHistorico = document.getElementById("btn-confirm-remove-historico");
		let historicoData = [];
		let pendingRemoveIdx = null;

		function openHistoricoModal() {
			if (!modalHistorico) return;
			frappe
				.call({
					method: "gris.api.members_portal.get_member_history",
					args: { name: associadoName },
				})
				.then((r) => {
					if (r.message && r.message.success) {
						historicoData = r.message.history || [];
						renderHistoricoList();
						modalHistorico.showModal();
					} else {
						notify("Erro ao carregar histórico", "red");
					}
				})
				.catch((err) => {
					console.error("Erro ao carregar histórico:", err);
					notify("Erro ao carregar histórico", "red");
				});
		}

		function closeHistoricoModal() {
			if (modalHistorico) modalHistorico.close();
		}

		function renderHistoricoList() {
			if (!historicoList) return;
			if (historicoData.length === 0) {
				historicoList.innerHTML =
					'<div style="padding: calc(var(--spacing) * 4); text-align: center; color: hsl(var(--muted-foreground)); font-size: 0.875rem;">Nenhum período registrado. Clique em "Adicionar Período" para criar o primeiro.</div>';
				return;
			}

			let html = "";
			historicoData.forEach((item, idx) => {
				html += `
          <div class="historico-item" data-idx="${idx}">
            <div class="detalhe-historico-row">
              <div class="field">
                <label class="label">Data de Ingresso</label>
                <input type="date" class="input" data-field="ingresso" value="${
					item.ingresso || ""
				}" required>
              </div>
              <div class="field">
                <label class="label">Data de Desligamento</label>
                <input type="date" class="input" data-field="desligamento" value="${
					item.desligamento || ""
				}">
              </div>
              <div class="detalhe-historico-row__action">
                <button type="button" class="btn-destructive btn-sm w-100" data-remove="${idx}">
                  Remover
                </button>
              </div>
            </div>
          </div>
        `;
			});
			historicoList.innerHTML = html;

			// Event listeners para campos
			historicoList.querySelectorAll("input[data-field]").forEach((input) => {
				input.addEventListener("change", (e) => {
					const item = e.target.closest(".historico-item");
					const idx = parseInt(item.dataset.idx);
					const field = e.target.dataset.field;
					historicoData[idx][field] = e.target.value;
				});
			});

			// Event listeners para botões remover
			historicoList.querySelectorAll("[data-remove]").forEach((btn) => {
				btn.addEventListener("click", (e) => {
					pendingRemoveIdx = parseInt(e.currentTarget.dataset.remove);
					confirmRemoveHistoricoDlg?.showModal();
				});
			});
		}

		btnEditHistorico?.addEventListener("click", openHistoricoModal);

		btnAddHistorico?.addEventListener("click", () => {
			historicoData.push({ ingresso: "", desligamento: "" });
			renderHistoricoList();
		});

		btnConfirmRemoveHistorico?.addEventListener("click", () => {
			if (pendingRemoveIdx !== null) {
				historicoData.splice(pendingRemoveIdx, 1);
				renderHistoricoList();
				pendingRemoveIdx = null;
				confirmRemoveHistoricoDlg?.close();
			}
		});

		// Adicionar listeners para botões de cancelar nos diálogos de histórico
		confirmRemoveHistoricoDlg?.querySelectorAll("[data-dialog-close]").forEach((btn) => {
			btn.addEventListener("click", () => {
				pendingRemoveIdx = null;
				confirmRemoveHistoricoDlg?.close();
			});
		});

		btnSaveHistorico?.addEventListener("click", () => {
			// Valida dados
			for (let i = 0; i < historicoData.length; i++) {
				if (!historicoData[i].ingresso) {
					notify("Todos os períodos devem ter data de ingresso", "red");
					return;
				}
			}

			btnSaveHistorico.disabled = true;
			btnSaveHistorico.textContent = "Salvando...";

			frappe
				.call({
					method: "gris.api.members_portal.update_member_history",
					args: {
						name: associadoName,
						history: JSON.stringify(historicoData),
					},
				})
				.then((r) => {
					btnSaveHistorico.disabled = false;
					btnSaveHistorico.textContent = "Salvar Alterações";
					if (r.message && r.message.success) {
						notify("Histórico atualizado com sucesso", "green");
						closeHistoricoModal();
						window.location.reload();
					} else {
						notify(r.message?.message || "Erro ao salvar histórico", "red");
					}
				})
				.catch(() => {
					btnSaveHistorico.disabled = false;
					btnSaveHistorico.textContent = "Salvar Alterações";
					notify("Erro ao salvar histórico", "red");
				});
		});
	});
})();
