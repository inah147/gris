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
