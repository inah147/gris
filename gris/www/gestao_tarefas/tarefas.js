/* /gestao_tarefas/tarefas — bootstrap do kanban (pessoal ou de quadro). */
(() => {
	"use strict";

	const METHODS_PESSOAL = {
		bootstrap: "gris.api.gestao_de_tarefas.minhas_tarefas.bootstrap_gestao_tarefas",
		saveTask: "gris.api.gestao_de_tarefas.minhas_tarefas.salvar_tarefa_pessoal",
		updateStatus: "gris.api.gestao_de_tarefas.minhas_tarefas.atualizar_status",
	};

	const METHODS_QUADRO = {
		bootstrap: "gris.api.gestao_de_tarefas.quadros.bootstrap_quadro",
		saveTask: "gris.api.gestao_de_tarefas.quadros.salvar_tarefa_quadro",
		updateStatus: "gris.api.gestao_de_tarefas.quadros.atualizar_status_quadro",
	};

	const METHODS_COMUM = {
		getComments: "gris.api.gestao_de_tarefas.minhas_tarefas.get_comentarios",
		addComment: "gris.api.gestao_de_tarefas.minhas_tarefas.adicionar_comentario",
		editComment: "gris.api.gestao_de_tarefas.minhas_tarefas.editar_comentario",
		deleteComment: "gris.api.gestao_de_tarefas.minhas_tarefas.apagar_comentario",
	};

	const METHODS_MEMBROS = {
		list: "gris.api.gestao_de_tarefas.quadros.listar_membros",
		add: "gris.api.gestao_de_tarefas.quadros.adicionar_membro",
		update: "gris.api.gestao_de_tarefas.quadros.atualizar_nivel_membro",
		remove: "gris.api.gestao_de_tarefas.quadros.remover_membro",
		search: "gris.api.gestao_de_tarefas.quadros.buscar_usuarios",
	};

	function $(id) {
		return document.getElementById(id);
	}

	function callApi(method, args = {}) {
		return new Promise((resolve, reject) => {
			frappe.call({
				method,
				args,
				callback: (response) => {
					const data = response?.message;
					if (!data || data.ok === false) {
						reject(new Error(data?.error || "Erro na requisicao."));
						return;
					}
					resolve(data);
				},
				error: (err) => reject(err instanceof Error ? err : new Error(String(err))),
			});
		});
	}

	function htmlEscape(str) {
		return String(str || "").replace(
			/[&<>"']/g,
			(ch) =>
				({
					"&": "&amp;",
					"<": "&lt;",
					">": "&gt;",
					'"': "&quot;",
					"'": "&#39;",
				}[ch])
		);
	}

	// Toast do design system (Basecoat). Em paginas de portal nao se usa
	// frappe.msgprint/show_alert (do Desk), que renderizam uma faixa branca
	// sem estilo. O toaster do design system ja esta na pagina via {{ toaster() }}.
	function showToast(category, message) {
		document.dispatchEvent(
			new CustomEvent("basecoat:toast", {
				detail: { config: { category, description: message } },
			})
		);
	}

	function showError(err) {
		showToast("error", err?.message || String(err));
	}

	function showOk(msg) {
		showToast("success", msg);
	}

	// O toaster vive em z-index normal; um <dialog> aberto com showModal() fica no
	// top layer e cobriria o toast. Enquanto o dialog de membros estiver aberto,
	// promovemos o toaster ao top layer (Popover API) para que o toast apareca
	// acima dele. Os estilos do popover sao neutralizados em tarefas.css.
	function liftToaster() {
		const t = document.getElementById("toaster");
		if (!t || typeof t.showPopover !== "function") return;
		try {
			if (!t.hasAttribute("popover")) t.setAttribute("popover", "manual");
			if (!t.matches(":popover-open")) t.showPopover();
		} catch (e) {
			/* navegador sem suporte: toast aparece atras, mas nao quebra */
		}
	}

	function dropToaster() {
		const t = document.getElementById("toaster");
		if (!t) return;
		try {
			if (t.matches(":popover-open")) t.hidePopover();
		} catch (e) {
			/* noop */
		}
		t.removeAttribute("popover");
	}

	function debounce(fn, ms) {
		let timeoutId;
		return (...args) => {
			clearTimeout(timeoutId);
			timeoutId = setTimeout(() => fn(...args), ms);
		};
	}

	function basecoatSelectHtml(idBase, niveis, valorAtual, dataAttrs) {
		const dataAttrsStr = Object.entries(dataAttrs || {})
			.map(([k, v]) => `${k}="${htmlEscape(v)}"`)
			.join(" ");
		const opts = niveis
			.map((n, i) => {
				const selected = n === valorAtual ? ' aria-selected="true"' : "";
				return `<div id="${idBase}-items-${i + 1}" role="option" data-value="${htmlEscape(
					n
				)}"${selected}>${htmlEscape(n)}</div>`;
			})
			.join("");
		return `
            <div id="${idBase}" class="select membros-quadro__select" ${dataAttrsStr}>
                <button type="button" class="btn-outline" id="${idBase}-trigger" aria-haspopup="listbox" aria-expanded="false" aria-controls="${idBase}-listbox">
                    <span class="truncate">${htmlEscape(valorAtual)}</span>
                    <svg xmlns="http://www.w3.org/2000/svg" width="24" height="24" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round" class="lucide lucide-chevron-down-icon text-muted-foreground opacity-50 shrink-0"><path d="m6 9 6 6 6-6"/></svg>
                </button>
                <div id="${idBase}-popover" data-popover aria-hidden="true">
                    <div role="listbox" id="${idBase}-listbox" aria-orientation="vertical" aria-labelledby="${idBase}-trigger">
                        ${opts}
                    </div>
                </div>
                <input type="hidden" name="${idBase}-value" value="${htmlEscape(valorAtual)}">
            </div>
        `;
	}

	function badgeVariant(nivel) {
		if (nivel === "Gerenciar") return "default";
		if (nivel === "Editar") return "secondary";
		return "outline";
	}

	function renderMembros(membros, podeGerir, niveis) {
		const lista = $("lista-membros");
		if (!lista) return;
		if (!membros.length) {
			lista.innerHTML = '<li class="membros-quadro__empty">Nenhum membro neste quadro.</li>';
			return;
		}
		lista.innerHTML = membros
			.map((m, idx) => {
				const isOwner = m.is_owner;
				const selectId = `select-nivel-membro-${idx}`;
				const nivelControl =
					podeGerir && !isOwner
						? basecoatSelectHtml(selectId, niveis, m.nivel_acesso, {
								"data-member-update": "",
								"data-user": m.user,
						  })
						: `<span class="badge-${badgeVariant(m.nivel_acesso)}">${htmlEscape(
								m.nivel_acesso
						  )}</span>`;
				const removeBtn =
					podeGerir && !isOwner
						? `<button type="button" class="btn-sm-outline" data-member-remove data-user="${htmlEscape(
								m.user
						  )}" aria-label="Remover ${htmlEscape(m.full_name)}">Remover</button>`
						: "";
				return `
                <li class="membros-quadro__item" data-user="${htmlEscape(m.user)}">
                    <div class="membros-quadro__user">
                        <strong>${htmlEscape(m.full_name)}</strong>
                        <small>${htmlEscape(m.user)}${
					isOwner ? " &middot; <em>criador</em>" : ""
				}</small>
                    </div>
                    <div class="membros-quadro__actions">
                        ${nivelControl}
                        ${removeBtn}
                    </div>
                </li>
            `;
			})
			.join("");
	}

	function setComboValor(comboEl, valor) {
		if (!comboEl) return;
		// selectByValue() do design system so atua quando ha uma opcao
		// correspondente; para limpar (valor vazio) ele e no-op, entao
		// limpamos o estado manualmente.
		if (valor && typeof comboEl.selectByValue === "function") {
			comboEl.selectByValue(valor);
			return;
		}
		const input = comboEl.querySelector(':scope > input[type="hidden"]');
		const span = comboEl.querySelector(":scope > button > span");
		if (input) input.value = "";
		if (span) {
			span.textContent = "Selecione um usuario...";
			span.classList.add("text-muted-foreground");
		}
		comboEl
			.querySelectorAll('[role="option"][aria-selected="true"]')
			.forEach((opt) => opt.removeAttribute("aria-selected"));
	}

	// O combobox do design system copia o innerHTML da opcao (nome + email) para
	// o gatilho ao selecionar. No gatilho queremos exibir apenas o nome; o email
	// continua visivel na lista suspensa (label) e nos cards de membro.
	function aplicarRotuloNome(comboEl) {
		if (!comboEl) return;
		const input = comboEl.querySelector(':scope > input[type="hidden"]');
		const span = comboEl.querySelector(":scope > button > span");
		if (!input || !span) return;
		const valor = input.value || "";
		if (!valor) return;
		const opt = Array.from(comboEl.querySelectorAll('[role="option"]')).find(
			(o) => o.dataset.value === valor
		);
		if (opt?.dataset.nome) {
			span.textContent = opt.dataset.nome;
			span.classList.remove("text-muted-foreground");
		}
	}

	function atualizarOpcoesCombo(comboEl, membrosAtuais) {
		if (!comboEl) return;
		const listbox = comboEl.querySelector('[role="listbox"]');
		if (!listbox) return;
		const jaMembros = new Set(membrosAtuais.map((m) => m.user));
		listbox.querySelectorAll('[role="option"]').forEach((opt) => {
			const v = opt.dataset.value;
			if (jaMembros.has(v)) {
				opt.setAttribute("hidden", "");
				opt.setAttribute("aria-disabled", "true");
			} else {
				opt.removeAttribute("hidden");
				opt.removeAttribute("aria-disabled");
			}
		});
		const valor = comboEl.querySelector(':scope > input[type="hidden"]')?.value || "";
		if (valor && jaMembros.has(valor)) {
			setComboValor(comboEl, "");
		}
	}

	function initMembros(boardName, podeGerir) {
		const btnAbrir = $("btn-gerir-membros");
		const dialog = $("dialog-membros-quadro");
		if (!btnAbrir || !dialog) return;

		let niveis = ["Gerenciar", "Editar", "Visualizar"];
		let ultimosMembros = [];
		const comboUsuario = $("combo-buscar-usuario");
		const selectNivel = $("select-nivel-novo");
		const btnAdicionar = $("btn-adicionar-membro");

		async function refresh() {
			try {
				const data = await callApi(METHODS_MEMBROS.list, { board_name: boardName });
				niveis = data.niveis_disponiveis || niveis;
				ultimosMembros = data.membros || [];
				renderMembros(ultimosMembros, data.pode_gerir, niveis);
				atualizarOpcoesCombo(comboUsuario, ultimosMembros);
			} catch (err) {
				showError(err);
			}
		}

		btnAbrir.addEventListener("click", async () => {
			dialog.showModal();
			liftToaster();
			await refresh();
			aplicarRotuloNome(comboUsuario);
		});

		// Cobre todas as formas de fechar (botoes, ESC, clique no overlay).
		dialog.addEventListener("close", dropToaster);

		document.querySelectorAll("[data-dialog-close]").forEach((btn) => {
			btn.addEventListener("click", () => {
				const targetId = btn.getAttribute("data-dialog-close");
				const target = targetId && $(targetId);
				if (target && typeof target.close === "function") target.close();
			});
		});

		const lista = $("lista-membros");

		// Selects de nivel sao componentes basecoat: emitem evento "change" no input
		// hidden interno, mas tambem disparam o evento no proprio elemento .select.
		lista?.addEventListener("change", async (e) => {
			const selEl = e.target.closest("[data-member-update]");
			if (!selEl) return;
			const user = selEl.dataset.user;
			const valorInput = selEl.querySelector(':scope > input[type="hidden"]');
			const nivel = valorInput?.value || "";
			if (!nivel) return;
			try {
				await callApi(METHODS_MEMBROS.update, {
					board_name: boardName,
					user,
					nivel_acesso: nivel,
				});
				showOk("Nivel atualizado");
				await refresh();
			} catch (err) {
				showError(err);
				await refresh();
			}
		});

		lista?.addEventListener("click", async (e) => {
			const btn = e.target.closest("[data-member-remove]");
			if (!btn) return;
			const user = btn.dataset.user;
			if (!window.confirm(`Remover ${user} deste quadro?`)) return;
			try {
				await callApi(METHODS_MEMBROS.remove, { board_name: boardName, user });
				showOk("Membro removido");
				await refresh();
			} catch (err) {
				showError(err);
			}
		});

		if (comboUsuario) {
			comboUsuario.addEventListener("change", () => aplicarRotuloNome(comboUsuario));
		}

		if (btnAdicionar && comboUsuario && podeGerir) {
			btnAdicionar.addEventListener("click", async () => {
				const user =
					comboUsuario.querySelector(':scope > input[type="hidden"]')?.value || "";
				const nivel =
					selectNivel?.querySelector(':scope > input[type="hidden"]')?.value || "Editar";
				if (!user) {
					showError(new Error("Selecione um usuario."));
					return;
				}
				btnAdicionar.disabled = true;
				try {
					await callApi(METHODS_MEMBROS.add, {
						board_name: boardName,
						user,
						nivel_acesso: nivel,
					});
					showOk("Membro adicionado");
					setComboValor(comboUsuario, "");
					await refresh();
				} catch (err) {
					showError(err);
				} finally {
					btnAdicionar.disabled = false;
				}
			});
		}
	}

	function init() {
		if (typeof frappe === "undefined" || !frappe.call || !window.GrisKanbanTarefas) {
			setTimeout(init, 100);
			return;
		}

		const root = document.querySelector("[data-kanban-tarefas]");
		const modo = root?.dataset.modo === "projeto" ? "projeto" : "pessoal";
		const boardName = ($("userBoardName")?.value || "").trim();
		const methods = modo === "projeto" ? METHODS_QUADRO : METHODS_PESSOAL;

		const kanban = new window.GrisKanbanTarefas("#taskKanban", {
			mode: modo,
			currentUser: $("currentUser")?.value || "",
			currentUserFullName: $("currentUserFullName")?.value || "",
			canEdit: true,
			onLoad: async () => {
				const args = modo === "projeto" ? { board_name: boardName } : {};
				const data = await callApi(methods.bootstrap, args);
				return {
					tarefas: data.tarefas || [],
					responsavelOptions: data.responsavel_options || [],
				};
			},
			onSaveTask: async (payload) => {
				const taskPayload =
					modo === "projeto" ? { ...payload, board: boardName } : payload;
				const data = await callApi(methods.saveTask, { tarefa: taskPayload });
				return { tarefas: data.tarefas || [] };
			},
			onMoveTask: async (tarefaName, status) => {
				const data = await callApi(methods.updateStatus, {
					tarefa_name: tarefaName,
					status,
				});
				return { tarefas: data.tarefas || [] };
			},
			onLoadComments: async (tarefaName) => {
				const data = await callApi(METHODS_COMUM.getComments, { tarefa_name: tarefaName });
				return { comentarios: data.comentarios || [] };
			},
			onAddComment: async (tarefaName, texto) => {
				const data = await callApi(METHODS_COMUM.addComment, {
					tarefa_name: tarefaName,
					texto,
				});
				return { comentarios: data.comentarios || [] };
			},
			onEditComment: async (commentName, texto) => {
				const data = await callApi(METHODS_COMUM.editComment, {
					comentario_name: commentName,
					texto,
				});
				return { comentarios: data.comentarios || [] };
			},
			onDeleteComment: async (commentName) => {
				const data = await callApi(METHODS_COMUM.deleteComment, {
					comentario_name: commentName,
				});
				return { comentarios: data.comentarios || [] };
			},
		});

		// Em modo projeto o hint inicial e um placeholder ("Carregando
		// permissoes...") que depende do JS para ser substituido. Aqui a edicao
		// e sempre liberada (canEdit: true), entao definimos o hint final.
		if (modo === "projeto") {
			kanban.setHint(
				"Arraste cards entre colunas, clique para editar ou crie novas tarefas."
			);
		}

		kanban.refresh().then(() => {
			// Abre o dialog da tarefa quando a URL traz ?tarefa=<name> (ex.: vindo
			// do popover de tarefas da topbar).
			const tarefaParam = (
				new URLSearchParams(window.location.search).get("tarefa") || ""
			).trim();
			if (tarefaParam) kanban.openTask(tarefaParam);
		});

		const isSolto = ($("isQuadroSolto")?.value || "") === "1";
		const podeGerir = ($("podeGerirMembros")?.value || "") === "1";
		if (isSolto && boardName) {
			initMembros(boardName, podeGerir);
		}
	}

	if (document.readyState === "loading") {
		document.addEventListener("DOMContentLoaded", init);
	} else {
		init();
	}
})();
