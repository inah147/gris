(function () {
	document.addEventListener("DOMContentLoaded", function () {
		const container = document.querySelector(".flow-steps-container");
		if (container) {
			const doneSteps = container.querySelectorAll(".flow-step--done");
			if (doneSteps.length > 0) {
				const lastDoneStep = doneSteps[doneSteps.length - 1];
				const scrollPos =
					lastDoneStep.offsetLeft +
					lastDoneStep.offsetWidth / 2 -
					container.offsetWidth / 2;
				container.scrollTo({ left: scrollPos, behavior: "smooth" });
			}
		}

		const commentForm = document.getElementById("comment-form");
		const commentTextarea = document.getElementById("comment-text");
		const commentList = document.getElementById("comment-list");
		const emptyState = document.getElementById("comment-empty");
		const errorBox = document.getElementById("comment-error");
		const submitBtn = document.getElementById("comment-submit");
		const dialogEl = document.getElementById("comment-modal");
		const openBtn = document.getElementById("comment-modal-open");
		const editCancelBtn = document.getElementById("comment-cancel-edit");
		const PENCIL_ICON_HTML =
			'<svg class="ds-lucide ds-lucide--sm" viewBox="0 0 24 24" aria-hidden="true">' +
			'<use href="/assets/gris/design_system/icons/lucide/sprite.svg#pencil" />' +
			"</svg>";
		let editingCommentName = null;

		function escapeHtml(str) {
			return str
				.replace(/&/g, "&amp;")
				.replace(/</g, "&lt;")
				.replace(/>/g, "&gt;")
				.replace(/"/g, "&quot;")
				.replace(/'/g, "&#39;");
		}

		function openModal() {
			if (!dialogEl || typeof dialogEl.showModal !== "function") return;
			if (!dialogEl.open) dialogEl.showModal();
		}

		function closeModal() {
			if (!dialogEl || typeof dialogEl.close !== "function") return;
			if (dialogEl.open) dialogEl.close();
		}

		function incrementCommentCount() {
			const badge = document.getElementById("comment-count");
			const badgeModal = document.getElementById("comment-count-modal");
			const current = Number((badge && badge.textContent) || 0) || 0;
			if (badge) badge.textContent = current + 1;
			if (badgeModal) badgeModal.textContent = current + 1;
		}

		if (openBtn && dialogEl) {
			openBtn.addEventListener("click", openModal);
		}

		if (dialogEl) {
			dialogEl.addEventListener("close", clearEditingState);
		}

		if (commentForm && commentTextarea && submitBtn) {
			const docName = commentForm.dataset.docname;

			commentForm.addEventListener("submit", async function (e) {
				e.preventDefault();
				if (!docName && !editingCommentName) return;

				const content = commentTextarea.value.trim();
				if (!content) return;

				submitBtn.textContent = editingCommentName ? "Salvando..." : "Enviando...";
				submitBtn.disabled = true;
				if (errorBox) errorBox.hidden = true;

				const endpoint = editingCommentName
					? "/api/method/gris.api.recepcao.editar_comentario"
					: "/api/method/gris.api.recepcao.adicionar_comentario";
				const payload = editingCommentName
					? { comment_name: editingCommentName, content }
					: { novo_associado_name: docName, content };

				try {
					const resp = await fetch(endpoint, {
						method: "POST",
						headers: {
							"Content-Type": "application/json",
							"X-Frappe-CSRF-Token":
								(window.frappe && window.frappe.csrf_token) || "",
						},
						credentials: "same-origin",
						body: JSON.stringify(payload),
					});
					const data = await resp.json();
					if (!resp.ok || data.exc) {
						throw new Error(
							(data && data._server_messages) || data.message || "Erro ao salvar."
						);
					}

					const comment = data.message;
					const contentText = comment.content_text || comment.content || "";

					if (editingCommentName) {
						const target =
							(commentList &&
								commentList.querySelector(
									`.comment-item[data-comment-name="${editingCommentName}"]`
								)) ||
							(commentList &&
								commentList
									.querySelector(
										`button[data-comment-name="${editingCommentName}"]`
									)
									?.closest(".comment-item"));

						if (target) {
							const contentEl = target.querySelector(".comment-item__content");
							const editBtn = target.querySelector(".comment-item__edit");
							if (contentEl)
								contentEl.innerHTML = escapeHtml(contentText).replace(
									/\n/g,
									"<br>"
								);
							if (editBtn) editBtn.dataset.commentContent = contentText;
						}
					} else if (commentList) {
						const item = document.createElement("div");
						item.className = "comment-item";
						item.dataset.commentName = comment.name;
						const initial = (comment.owner_fullname || "?")
							.trim()
							.charAt(0)
							.toUpperCase();
						item.innerHTML = `
                            <span class="avatar"><span aria-hidden="true">${escapeHtml(
								initial
							)}</span></span>
                            <div class="comment-item__body">
                                <div class="comment-item__meta">
                                    <div class="comment-item__meta-left">
                                        <span class="comment-item__author">${escapeHtml(
											comment.owner_fullname || ""
										)}</span>
                                        <span class="comment-item__dot">•</span>
                                        <span class="comment-item__date">${escapeHtml(
											comment.creation || ""
										)}</span>
                                    </div>
                                    <button
                                        type="button"
                                        class="btn-sm-ghost comment-item__edit"
                                        data-comment-name="${escapeHtml(comment.name)}"
                                        data-comment-content="${escapeHtml(contentText)}"
                                    >
                                        ${PENCIL_ICON_HTML} Editar
                                    </button>
                                </div>
                                <div class="comment-item__content">${escapeHtml(
									contentText
								).replace(/\n/g, "<br>")}</div>
                            </div>
                        `;
						commentList.prepend(item);
						if (emptyState) emptyState.hidden = true;
						incrementCommentCount();
					}

					commentTextarea.value = "";
					clearEditingState();
				} catch (err) {
					if (errorBox) {
						errorBox.textContent =
							err.message || "Não foi possível adicionar o comentário.";
						errorBox.hidden = false;
					}
				} finally {
					submitBtn.disabled = false;
					submitBtn.textContent = editingCommentName ? "Salvar" : "Adicionar";
				}
			});

			commentTextarea.addEventListener("keydown", function (ev) {
				if (ev.key === "Enter" && !ev.shiftKey) {
					ev.preventDefault();
					submitBtn.click();
				}
			});
		}

		if (commentList) {
			commentList.addEventListener("click", function (ev) {
				const target = ev.target.closest(".comment-item__edit");
				if (!target) return;
				ev.preventDefault();
				const name = target.dataset.commentName;
				const content = target.dataset.commentContent || "";
				startEditing(name, content);
			});
		}

		if (editCancelBtn) {
			editCancelBtn.addEventListener("click", function (ev) {
				ev.preventDefault();
				clearEditingState();
			});
		}

		// Documentos do responsável: os arquivos ficam num drive de acesso restrito, então o
		// download passa pelo GRIS. Buscamos por fetch (e não abrindo a URL numa aba) para
		// que uma falha apareça como mensagem, e não como JSON cru numa aba nova.
		document.addEventListener("click", function (event) {
			const botao = event.target.closest("[data-baixar-documento]");
			if (!botao) return;

			event.preventDefault();
			baixarDocumento(botao);
		});

		async function baixarDocumento(botao) {
			const lista = botao.closest(".ficha-documentos");
			const novoAssociado = lista ? lista.dataset.novoAssociado : "";
			// Só o rótulo muda: trocar o textContent do botão apagaria o ícone junto.
			const rotulo = botao.querySelector("span");
			const rotuloOriginal = rotulo ? rotulo.textContent : "";

			botao.disabled = true;
			botao.setAttribute("aria-busy", "true");
			if (rotulo) rotulo.textContent = "Baixando...";

			try {
				const resposta = await fetch(
					"/api/method/gris.www.recepcao.ficha_registro.baixar_documento_do_responsavel",
					{
						method: "POST",
						headers: {
							"Content-Type": "application/json",
							"X-Frappe-CSRF-Token": frappe.csrf_token || "",
						},
						credentials: "same-origin",
						body: JSON.stringify({
							novo_associado_name: novoAssociado,
							responsavel_name: botao.dataset.responsavel,
							tipo: botao.dataset.baixarDocumento,
						}),
					}
				);

				const tipo = resposta.headers.get("Content-Type") || "";
				if (!resposta.ok || tipo.includes("application/json")) {
					window.alert("Não foi possível baixar o documento.");
					return;
				}

				const blob = await resposta.blob();
				const url = URL.createObjectURL(blob);
				const link = document.createElement("a");
				link.href = url;
				link.download = nomeDoArquivo(resposta) || "documento";
				document.body.appendChild(link);
				link.click();
				link.remove();
				window.setTimeout(function () {
					URL.revokeObjectURL(url);
				}, 60000);
			} catch (erro) {
				window.alert("Não foi possível baixar o documento.");
			} finally {
				botao.disabled = false;
				botao.removeAttribute("aria-busy");
				if (rotulo) rotulo.textContent = rotuloOriginal;
			}
		}

		function nomeDoArquivo(resposta) {
			const header = resposta.headers.get("Content-Disposition") || "";
			const match = /filename\*?=(?:UTF-8'')?"?([^";]+)"?/i.exec(header);
			if (!match) return "";
			try {
				return decodeURIComponent(match[1]);
			} catch (e) {
				return match[1];
			}
		}

		// ---- Números de registro (jovem e responsáveis) --------------------
		//
		// Seção própria com o jovem e cada responsável que também será registrado.
		// Um botão só grava todos, e fica desabilitado enquanto nada muda: numa
		// página que é de leitura, um botão sempre ativo convidaria a salvar sem
		// ter editado nada.
		const registroSalvarBtn = document.getElementById("registro-salvar");
		const registroFeedback = document.getElementById("registro-feedback");

		function camposDeRegistro() {
			return Array.from(
				document.querySelectorAll("[data-registro-jovem], [data-registro-responsavel]")
			);
		}

		function registrosAlterados() {
			return camposDeRegistro().filter(
				(campo) => campo.value.trim() !== (campo.dataset.valorOriginal || "")
			);
		}

		function sincronizarBotaoDeRegistro() {
			if (!registroSalvarBtn) return;
			registroSalvarBtn.disabled = registrosAlterados().length === 0;
		}

		function mostrarFeedbackDeRegistro(texto, erro) {
			if (!registroFeedback) return;
			registroFeedback.textContent = texto;
			registroFeedback.hidden = !texto;
			registroFeedback.classList.toggle("ficha-registro__feedback--erro", Boolean(erro));
		}

		if (registroSalvarBtn) {
			camposDeRegistro().forEach(function (campo) {
				campo.addEventListener("input", function () {
					mostrarFeedbackDeRegistro("");
					sincronizarBotaoDeRegistro();
				});
			});

			registroSalvarBtn.addEventListener("click", salvarNumerosDeRegistro);
		}

		async function salvarNumerosDeRegistro() {
			const novoAssociado = registroSalvarBtn.dataset.novoAssociado;
			if (!novoAssociado) return;

			const jovem = document.querySelector("[data-registro-jovem]");
			const responsaveis = {};
			document.querySelectorAll("[data-registro-responsavel]").forEach(function (campo) {
				responsaveis[campo.dataset.registroResponsavel] = campo.value.trim();
			});

			registroSalvarBtn.disabled = true;
			mostrarFeedbackDeRegistro("");

			try {
				const resposta = await fetch(
					"/api/method/gris.api.recepcao.salvar_numeros_de_registro",
					{
						method: "POST",
						headers: {
							"Content-Type": "application/json",
							"X-Frappe-CSRF-Token":
								(window.frappe && window.frappe.csrf_token) || "",
						},
						credentials: "same-origin",
						body: JSON.stringify({
							novo_associado_name: novoAssociado,
							numero_jovem: jovem ? jovem.value.trim() : "",
							responsaveis: JSON.stringify(responsaveis),
						}),
					}
				);

				const dados = await resposta.json();
				if (!resposta.ok || dados.exc) {
					throw new Error("Não foi possível salvar os números de registro.");
				}

				// O valor gravado passa a ser o novo "original", senão o botão
				// continuaria aceso depois de um salvamento bem-sucedido.
				camposDeRegistro().forEach(function (campo) {
					campo.value = campo.value.trim();
					campo.dataset.valorOriginal = campo.value;
				});
				sincronizarBotaoDeRegistro();
				mostrarFeedbackDeRegistro("Números de registro salvos.");
			} catch (erro) {
				mostrarFeedbackDeRegistro(erro.message || "Erro ao salvar.", true);
			} finally {
				// Depois de gravar não há mais alteração pendente, então quem decide
				// se o botão volta a ficar ativo é o estado dos campos.
				sincronizarBotaoDeRegistro();
			}
		}

		function startEditing(name, content) {
			if (!name || !commentTextarea || !submitBtn) return;
			openModal();
			editingCommentName = name;
			commentTextarea.value = content.replace(/<br\s*\/?>/gi, "\n");
			commentTextarea.focus();
			submitBtn.textContent = "Salvar";
			if (editCancelBtn) editCancelBtn.hidden = false;
		}

		function clearEditingState() {
			editingCommentName = null;
			if (submitBtn) submitBtn.textContent = "Adicionar";
			if (editCancelBtn) editCancelBtn.hidden = true;
		}
	});
})();
