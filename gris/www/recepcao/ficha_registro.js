(function() {
    document.addEventListener('DOMContentLoaded', function() {
        const container = document.querySelector('.flow-steps-container');
        if (container) {
            const doneSteps = container.querySelectorAll('.flow-step.done');
            if (doneSteps.length > 0) {
                const lastDoneStep = doneSteps[doneSteps.length - 1];
                const scrollPos =
                    lastDoneStep.offsetLeft + lastDoneStep.offsetWidth / 2 - container.offsetWidth / 2;
                container.scrollTo({ left: scrollPos, behavior: 'smooth' });
            }
        }

        const commentForm = document.getElementById('comment-form');
        const commentTextarea = document.getElementById('comment-text');
        const commentList = document.getElementById('comment-list');
        const emptyState = document.getElementById('comment-empty');
        const errorBox = document.getElementById('comment-error');
        const submitBtn = document.getElementById('comment-submit');
        const modal = document.getElementById('comment-modal');
        const openBtn = document.getElementById('comment-modal-open');
        const modalBackdrop = modal ? modal.querySelector('.comment-modal__backdrop') : null;
        const closeButtons = modal ? modal.querySelectorAll('[data-close="comment-modal"]') : [];
        const editCancelBtn = document.getElementById('comment-cancel-edit');
        let editingCommentName = null;

        function escapeHtml(str) {
            return str
                .replace(/&/g, '&amp;')
                .replace(/</g, '&lt;')
                .replace(/>/g, '&gt;')
                .replace(/"/g, '&quot;')
                .replace(/'/g, '&#39;');
        }

        function openModal() {
            if (!modal) return;
            modal.classList.add('is-open');
            modal.setAttribute('aria-hidden', 'false');
            document.body.style.overflow = 'hidden';
        }

        function closeModal() {
            if (!modal) return;
            modal.classList.remove('is-open');
            modal.setAttribute('aria-hidden', 'true');
            document.body.style.overflow = '';
            clearEditingState();
        }

        function incrementCommentCount() {
            const badge = document.getElementById('comment-count');
            const badgeModal = document.getElementById('comment-count-modal');
            const current = Number((badge && badge.textContent) || 0) || 0;
            if (badge) badge.textContent = current + 1;
            if (badgeModal) badgeModal.textContent = current + 1;
        }

        if (openBtn && modal) {
            openBtn.addEventListener('click', openModal);
        }

        if (modalBackdrop) {
            modalBackdrop.addEventListener('click', closeModal);
        }

        if (closeButtons && closeButtons.length > 0) {
            closeButtons.forEach((btn) => btn.addEventListener('click', closeModal));
        }

        document.addEventListener('keydown', function(ev) {
            if (ev.key === 'Escape' && modal && modal.classList.contains('is-open')) {
                ev.preventDefault();
                closeModal();
            }
        });

        if (commentForm && commentTextarea && submitBtn) {
            const docName = commentForm.dataset.docname;

            commentForm.addEventListener('submit', async function(e) {
                e.preventDefault();
                if (!docName && !editingCommentName) return;

                const content = commentTextarea.value.trim();
                if (!content) return;

                submitBtn.textContent = editingCommentName ? 'Salvando...' : 'Enviando...';
                submitBtn.disabled = true;
                if (errorBox) errorBox.style.display = 'none';

                const endpoint = editingCommentName
                    ? '/api/method/gris.api.recepcao.editar_comentario'
                    : '/api/method/gris.api.recepcao.adicionar_comentario';
                const payload = editingCommentName
                    ? { comment_name: editingCommentName, content }
                    : { novo_associado_name: docName, content };

                try {
                    const resp = await fetch(endpoint, {
                        method: 'POST',
                        headers: {
                            'Content-Type': 'application/json',
                            'X-Frappe-CSRF-Token': (window.frappe && window.frappe.csrf_token) || '',
                        },
                        credentials: 'same-origin',
                        body: JSON.stringify(payload),
                    });
                    const data = await resp.json();
                    if (!resp.ok || data.exc) {
                        throw new Error((data && data._server_messages) || data.message || 'Erro ao salvar.');
                    }

                    const comment = data.message;
                    const contentText = comment.content_text || comment.content || '';

                    if (editingCommentName) {
                        const target =
                            (commentList && commentList.querySelector(`.comment-item[data-comment-name="${editingCommentName}"]`)) ||
                            (commentList
                                && commentList
                                    .querySelector(`button[data-comment-name="${editingCommentName}"]`)
                                    ?.closest('.comment-item'));

                        if (target) {
                            const contentEl = target.querySelector('.comment-item__content');
                            const editBtn = target.querySelector('.comment-item__edit');
                            if (contentEl) contentEl.innerHTML = escapeHtml(contentText).replace(/\n/g, '<br>');
                            if (editBtn) editBtn.dataset.commentContent = contentText;
                        }
                    } else if (commentList) {
                        const item = document.createElement('div');
                        item.className = 'comment-item';
                        item.dataset.commentName = comment.name;
                        const initial = (comment.owner_fullname || '?').trim().charAt(0).toUpperCase();
                        item.innerHTML = `
                            <div class="comment-item__avatar"><span>${initial}</span></div>
                            <div class="comment-item__body">
                                <div class="comment-item__meta">
                                    <div class="comment-item__meta-left">
                                        <span class="comment-item__author">${comment.owner_fullname}</span>
                                        <span class="comment-item__dot">•</span>
                                        <span class="comment-item__date">${comment.creation}</span>
                                    </div>
                                    <button
                                        type="button"
                                        class="comment-item__edit btn-modern btn-modern--ghost btn-modern--xs"
                                        data-comment-name="${comment.name}"
                                        data-comment-content="${escapeHtml(contentText)}"
                                    >
                                        Editar
                                    </button>
                                </div>
                                <div class="comment-item__content">${escapeHtml(contentText).replace(/\n/g, '<br>')}</div>
                            </div>
                        `;
                        commentList.prepend(item);
                        if (emptyState) emptyState.style.display = 'none';
                        incrementCommentCount();
                    }

                    commentTextarea.value = '';
                    clearEditingState();
                } catch (err) {
                    if (errorBox) {
                        errorBox.textContent = err.message || 'Não foi possível adicionar o comentário.';
                        errorBox.style.display = 'inline';
                    }
                } finally {
                    submitBtn.disabled = false;
                    submitBtn.textContent = editingCommentName ? 'Salvar' : 'Adicionar';
                }
            });

            commentTextarea.addEventListener('keydown', function(ev) {
                if (ev.key === 'Enter' && !ev.shiftKey) {
                    ev.preventDefault();
                    submitBtn.click();
                }
            });
        }

        if (commentList) {
            commentList.addEventListener('click', function(ev) {
                const target = ev.target.closest('.comment-item__edit');
                if (!target) return;
                ev.preventDefault();
                const name = target.dataset.commentName;
                const content = target.dataset.commentContent || '';
                startEditing(name, content);
            });
        }

        if (editCancelBtn) {
            editCancelBtn.addEventListener('click', function(ev) {
                ev.preventDefault();
                clearEditingState();
            });
        }

        function startEditing(name, content) {
            if (!name || !commentTextarea || !submitBtn) return;
            openModal();
            editingCommentName = name;
            commentTextarea.value = content.replace(/<br\s*\/>/gi, '\n').replace(/<br>/gi, '\n');
            commentTextarea.focus();
            submitBtn.textContent = 'Salvar';
            if (editCancelBtn) editCancelBtn.style.display = 'inline-flex';
        }

        function clearEditingState() {
            editingCommentName = null;
            if (submitBtn) submitBtn.textContent = 'Adicionar';
            if (editCancelBtn) editCancelBtn.style.display = 'none';
        }
    });
})();
