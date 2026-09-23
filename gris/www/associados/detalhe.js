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

// ---------------------------------------------------------------------------
// Funções no organograma
//
// Card à parte do acumulador `changed` acima: cada ação grava na hora, pelos
// endpoints próprios, e devolve a lista já atualizada. Misturar com a allowlist
// de `update_member` obrigaria a mexer em duas camadas sem ganho nenhum.
// ---------------------------------------------------------------------------
(function () {
	document.addEventListener("DOMContentLoaded", function () {
		const raiz = document.querySelector(".funcoes-organograma");
		if (!raiz) return;

		const associado = raiz.dataset.associado || "";
		const corpo = document.getElementById("funcoes-organograma-corpo");
		const botaoAdicionar = document.getElementById("btn-adicionar-funcao");

		let areas = [];
		try {
			areas = JSON.parse(raiz.dataset.areas || "[]");
		} catch (e) {
			areas = [];
		}

		function toast(categoria, titulo) {
			document.dispatchEvent(
				new CustomEvent("basecoat:toast", {
					detail: { config: { category: categoria, title: titulo, duration: 4000 } },
				})
			);
		}

		function escapeHtml(valor) {
			const div = document.createElement("div");
			div.textContent = valor == null ? "" : String(valor);
			return div.innerHTML;
		}

		function valorDoSelect(id) {
			const elemento = document.getElementById(id);
			if (!elemento) return "";
			const hidden = elemento.querySelector('input[type="hidden"]');
			return hidden ? hidden.value : "";
		}

		// Troca as opções do listbox e força o Basecoat a reinicializar o componente:
		// sem o clone, o select continua respondendo com a lista antiga.
		//
		// A primeira opção é sempre um placeholder de valor vazio, e não é decoração:
		// ao inicializar, o select seleciona sozinho a primeira opção — e em silêncio,
		// sem disparar `change`. Sem a opção vazia, a área sairia escolhida sem
		// ninguém ter escolhido, e clicar nela depois não dispararia evento nenhum
		// (o componente ignora o clique quando o valor não muda), então a cascata
		// nunca rodaria.
		function repopularSelect(id, itens, placeholder) {
			const antigo = document.getElementById(id);
			if (!antigo) return;
			const listbox = antigo.querySelector('[role="listbox"]');
			const hidden = antigo.querySelector('input[type="hidden"]');
			const rotulo = antigo.querySelector(":scope > button > span");
			if (!listbox || !hidden || !rotulo) return;

			const textoPlaceholder = placeholder == null ? "Selecione…" : placeholder;
			antigo.dataset.placeholder = textoPlaceholder;

			listbox.innerHTML = "";
			[{ value: "", label: textoPlaceholder }, ...(itens || [])].forEach((item, indice) => {
				const opcao = document.createElement("div");
				opcao.id = `${id}-items-${indice + 1}`;
				opcao.setAttribute("role", "option");
				opcao.dataset.value = item.value;
				opcao.textContent = item.label;
				listbox.appendChild(opcao);
			});

			hidden.value = "";
			rotulo.textContent = textoPlaceholder;

			const novo = antigo.cloneNode(true);
			novo.removeAttribute("data-select-initialized");
			antigo.parentNode.replaceChild(novo, antigo);
		}

		function periodoDaLinha(linha) {
			const inicio = linha.data_inicio ? frappe.datetime.str_to_user(linha.data_inicio) : "";
			if (!linha.data_fim) return inicio ? `Desde ${inicio}` : "Atual";
			const fim = frappe.datetime.str_to_user(linha.data_fim);
			return inicio ? `${inicio} – ${fim}` : `Até ${fim}`;
		}

		function renderizar(linhas) {
			if (!corpo) return;
			if (!linhas.length) {
				corpo.innerHTML =
					'<tr><td colspan="4" class="text-muted-foreground text-sm">Nenhuma função atribuída.</td></tr>';
				return;
			}

			corpo.innerHTML = linhas
				.map((linha) => {
					// O que manda na ação é ter ou não data de fim, e não `atual`: uma
					// função encerrada hoje ainda vale hoje, então continuaria "atual" e
					// o botão Encerrar reapareceria como se o clique não tivesse surtido
					// efeito.
					const emAberto = !linha.data_fim;
					const principal = linha.principal
						? '<span class="badge">Principal</span>'
						: emAberto
						? `<button type="button" class="btn-sm-ghost" data-acao="principal" data-linha="${escapeHtml(
								linha.linha
						  )}">Tornar principal</button>`
						: "";
					const acao = emAberto
						? `<button type="button" class="btn-sm-outline" data-acao="encerrar" data-linha="${escapeHtml(
								linha.linha
						  )}">Encerrar</button>`
						: `<span class="text-muted-foreground text-sm">Encerrada em ${escapeHtml(
								frappe.datetime.str_to_user(linha.data_fim)
						  )}</span>`;
					return `<tr${emAberto ? "" : ' class="funcoes-organograma__encerrada"'}>
						<td>${escapeHtml(linha.area || "—")}</td>
						<td>${escapeHtml(linha.funcao)} ${principal}</td>
						<td>${escapeHtml(periodoDaLinha(linha))}</td>
						<td class="funcoes-organograma__acoes">${acao}</td>
					</tr>`;
				})
				.join("");
		}

		// `frappe.call` no portal não chama `error` e dispara `always` antes do
		// `callback`: a mensagem do `frappe.throw` se perderia, e é ela que explica
		// por que o par função+área foi recusado.
		async function chamar(metodo, argumentos) {
			const resposta = await fetch(`/api/method/${metodo}`, {
				method: "POST",
				headers: {
					"Content-Type": "application/json",
					Accept: "application/json",
					"X-Frappe-CSRF-Token": frappe.csrf_token || "",
				},
				credentials: "same-origin",
				body: JSON.stringify(argumentos),
			});

			const corpoJson = await resposta.json().catch(() => ({}));
			if (!resposta.ok) {
				let mensagem = "Não foi possível salvar.";
				try {
					const lista = JSON.parse(corpoJson._server_messages || "[]");
					if (lista.length) mensagem = JSON.parse(lista[0]).message;
				} catch (e) {
					/* fica a mensagem genérica */
				}
				throw new Error(mensagem);
			}
			return corpoJson.message;
		}

		async function executar(botao, metodo, argumentos, sucesso) {
			botao.disabled = true;
			try {
				const resultado = await chamar(metodo, argumentos);
				renderizar((resultado && resultado.funcoes) || []);
				toast("success", sucesso);
			} catch (erro) {
				// A mensagem vem do servidor e é o que explica o bloqueio; o HTML dela é
				// removido para caber no toast.
				toast("error", String(erro.message || erro).replace(/<[^>]*>/g, ""));
			} finally {
				botao.disabled = false;
			}
		}

		// A área escolhida define quais funções existem.
		function sincronizarFuncoes() {
			const escolhida = areas.find((a) => a.value === valorDoSelect("funcao-area"));
			if (!escolhida) {
				repopularSelect("funcao-funcao", [], "Escolha a área primeiro");
				return;
			}
			repopularSelect(
				"funcao-funcao",
				escolhida.funcoes,
				escolhida.funcoes.length ? "Selecione a função…" : "Nenhuma função nesta área"
			);
		}

		document.addEventListener("change", function (evento) {
			if (!evento.target.closest || !evento.target.closest("#funcao-area")) return;
			sincronizarFuncoes();
		});

		if (botaoAdicionar) {
			botaoAdicionar.addEventListener("click", function () {
				const area = valorDoSelect("funcao-area");
				const funcao = valorDoSelect("funcao-funcao");
				if (!area || !funcao) {
					toast("error", "Escolha a área e a função.");
					return;
				}
				executar(
					botaoAdicionar,
					"gris.api.gestao_adultos.atribuir_funcao",
					{
						payload: JSON.stringify({
							associado: associado,
							area: area,
							funcao: funcao,
						}),
					},
					"Função atribuída."
					// Recarrega as funções da mesma área em vez de só limpar: re-clicar a
					// área já escolhida não dispara `change`, então limpar deixaria o
					// seletor vazio e sem jeito de voltar a preencher.
				).then(sincronizarFuncoes);
			});
		}

		raiz.addEventListener("click", function (evento) {
			const botao = evento.target.closest("[data-acao]");
			if (!botao) return;
			const argumentos = {
				payload: JSON.stringify({ associado: associado, linha: botao.dataset.linha }),
			};
			if (botao.dataset.acao === "encerrar") {
				executar(
					botao,
					"gris.api.gestao_adultos.encerrar_funcao",
					argumentos,
					"Função encerrada."
				);
			} else if (botao.dataset.acao === "principal") {
				executar(
					botao,
					"gris.api.gestao_adultos.definir_principal",
					argumentos,
					"Função principal definida."
				);
			}
		});

		repopularSelect(
			"funcao-area",
			areas.map((a) => ({ value: a.value, label: a.label })),
			"Selecione a área…"
		);
		renderizar(JSON.parse(raiz.dataset.linhas || "[]"));
	});
})();
