(function () {
	if (window.__btg_import_page_inited) return;
	window.__btg_import_page_inited = true;

	const CAN_RECONCILE = window.frappe && frappe.boot && frappe.boot.can_reconcile_btg_empresas;

	window._btgFileUrl = null;

	function escapeHtml(value) {
		if (window.frappe && frappe.utils && frappe.utils.escape_html) {
			return frappe.utils.escape_html(String(value ?? ""));
		}
		const div = document.createElement("div");
		div.textContent = String(value ?? "");
		return div.innerHTML;
	}

	function showToast(category, title, description) {
		const toaster = document.getElementById("toaster");
		if (toaster) {
			document.dispatchEvent(
				new CustomEvent("basecoat:toast", {
					detail: { config: { category, title, description } },
				})
			);
			return;
		}
		if (window.frappe && frappe.show_alert) {
			frappe.show_alert({
				message: description || title,
				indicator: category === "error" ? "red" : "green",
			});
		}
	}

	function checkShowConciliarBtn() {
		const btn = document.getElementById("btnConciliarBtg");
		const ok = !!window._btgFileUrl;
		if (btn) {
			btn.classList.toggle("hidden", !ok);
			btn.disabled = !ok || CAN_RECONCILE === false;
		}
	}

	function setupUploader() {
		const uploader = document.getElementById("btgImportUpload");
		if (!uploader) return;

		uploader.addEventListener("gris:file-upload:success", function (event) {
			const file = event.detail && event.detail.files && event.detail.files[0];
			if (!file) return;

			const fileInfo = document.getElementById("file-info-btg");
			const fileName = document.getElementById("nomeBtg");

			if (fileName) {
				fileName.textContent = file.file_name || file.name || file.file_url || "";
			}
			if (fileInfo) {
				fileInfo.classList.remove("hidden");
			}

			window._btgFileUrl = file.file_url;
			checkShowConciliarBtn();

			const resultsDiv = document.getElementById("btg-results");
			if (resultsDiv) resultsDiv.classList.add("hidden");
		});
	}

	function renderResults(payload) {
		const resultsDiv = document.getElementById("btg-results");
		const grid = document.getElementById("btg-stat-card");
		const errWrap = document.getElementById("btg-errors-card");
		const errList = document.getElementById("btg-errors-list");
		if (!resultsDiv || !grid || !errWrap || !errList) return;

		grid.innerHTML = "";
		errList.innerHTML = "";
		errWrap.classList.add("hidden");
		resultsDiv.classList.remove("hidden");

		const stats = (payload && payload.stats) || {
			total: 0,
			inserted: 0,
			skipped_exist: 0,
			failed: 0,
		};
		const cards = [
			{ label: "Total de transações", value: stats.total || 0, tone: "primary" },
			{ label: "Inseridos", value: stats.inserted || 0, tone: "success" },
			{ label: "Repetidos", value: stats.skipped_exist || 0, tone: "muted" },
			{ label: "Erros", value: stats.failed || 0, tone: "error" },
		];

		cards.forEach(function (stat) {
			const article = document.createElement("article");
			article.className = "card import-stat-card";
			article.dataset.tone = stat.tone;
			article.innerHTML = `
        <section>
          <p class="import-stat-card__value">${escapeHtml(stat.value)}</p>
          <p class="import-stat-card__label">${escapeHtml(stat.label)}</p>
        </section>
      `;
			grid.appendChild(article);
		});

		const errors = (payload && payload.errors) || [];
		if (errors.length) {
			const items = errors
				.slice(0, 50)
				.map(function (e) {
					return `<li>${escapeHtml(e || "")}</li>`;
				})
				.join("");
			const more =
				errors.length > 50
					? `<p class="import-errors__more">+${escapeHtml(
							errors.length - 50
					  )} erros adicionais. Consulte o Error Log para a lista completa.</p>`
					: "";
			errList.innerHTML = `<ul>${items}</ul>${more}`;
			errWrap.classList.remove("hidden");
		}
	}

	window.sendBtgFile = function () {
		if (CAN_RECONCILE === false) {
			showToast("error", "Permissão negada", "Você não tem permissão para conciliar.");
			return;
		}
		if (!window._btgFileUrl) {
			showToast("error", "Arquivo ausente", "Selecione um arquivo antes de enviar.");
			return;
		}

		const loadingIndicator = document.getElementById("btg-loading-indicator");
		const btnConciliar = document.getElementById("btnConciliarBtg");
		const resultsDiv = document.getElementById("btg-results");

		if (loadingIndicator) loadingIndicator.classList.remove("hidden");
		if (btnConciliar) btnConciliar.disabled = true;
		if (resultsDiv) resultsDiv.classList.add("hidden");

		frappe.call({
			method: "gris.www.financeiro.import_btg_empresas.process_uploaded_btg_file",
			args: { file_url: window._btgFileUrl },
			callback: function (r) {
				if (loadingIndicator) loadingIndicator.classList.add("hidden");
				if (btnConciliar) btnConciliar.disabled = false;

				if (r && r.exc) {
					console.error("Erro process_uploaded_btg_file", r.exc);
					showToast(
						"error",
						"Erro ao processar",
						"Verifique o console e os logs do sistema."
					);
					return;
				}
				const payload = r && r.message ? r.message : r;
				renderResults(payload);
				window.scrollTo({ top: 0, behavior: "smooth" });
				showToast(
					"success",
					"Conciliação concluída",
					"O extrato foi processado com sucesso."
				);
			},
			error: function (err) {
				if (loadingIndicator) loadingIndicator.classList.add("hidden");
				if (btnConciliar) btnConciliar.disabled = false;
				console.error("Erro ao processar BTG Empresas:", err);
				showToast(
					"error",
					"Erro na conciliação",
					"Ocorreu um erro ao processar o arquivo."
				);
			},
		});
	};

	setupUploader();
	checkShowConciliarBtn();

	const btnConciliar = document.getElementById("btnConciliarBtg");
	if (btnConciliar) {
		btnConciliar.addEventListener("click", window.sendBtgFile);
	}
})();
