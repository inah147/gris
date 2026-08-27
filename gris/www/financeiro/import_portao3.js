(function () {
	if (window.__portao3_import_page_inited) return;
	window.__portao3_import_page_inited = true;

	const CAN_RECONCILE = window.frappe && frappe.boot && frappe.boot.can_reconcile_portao3;

	window._portao3FileUrl = null;

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
		const btn = document.getElementById("btnConciliarPortao3");
		const ok = !!window._portao3FileUrl;
		if (btn) {
			btn.classList.toggle("hidden", !ok);
			btn.disabled = !ok || CAN_RECONCILE === false;
		}
	}

	function setupUploader() {
		const uploader = document.getElementById("portao3ImportUpload");
		if (!uploader) return;

		uploader.addEventListener("gris:file-upload:success", function (event) {
			const file = event.detail && event.detail.files && event.detail.files[0];
			if (!file) return;

			const fileInfo = document.getElementById("file-info-portao3");
			const fileName = document.getElementById("nomePortao3");

			if (fileName) {
				fileName.textContent = file.file_name || file.name || file.file_url || "";
			}
			if (fileInfo) fileInfo.classList.remove("hidden");

			window._portao3FileUrl = file.file_url;
			checkShowConciliarBtn();

			const resultsDiv = document.getElementById("portao3-results");
			if (resultsDiv) resultsDiv.classList.add("hidden");
		});
	}

	function renderResults(payload) {
		const resultsDiv = document.getElementById("portao3-results");
		const grid = document.getElementById("portao3-stat-card");
		const errWrap = document.getElementById("portao3-errors-card");
		const errList = document.getElementById("portao3-errors-list");
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

	window.enviarArquivoPortao3 = function () {
		if (CAN_RECONCILE === false) {
			showToast("error", "Permissão negada", "Você não tem permissão para conciliar.");
			return;
		}
		if (!window._portao3FileUrl) {
			showToast("error", "Arquivo ausente", "Faça o upload do arquivo antes de enviar.");
			return;
		}

		const loadingIndicator = document.getElementById("portao3-loading-indicator");
		const btnConciliar = document.getElementById("btnConciliarPortao3");
		const resultsDiv = document.getElementById("portao3-results");

		if (loadingIndicator) loadingIndicator.classList.remove("hidden");
		if (btnConciliar) btnConciliar.disabled = true;
		if (resultsDiv) resultsDiv.classList.add("hidden");

		frappe.call({
			method: "gris.www.financeiro.import_portao3.process_uploaded_file_portao3",
			args: { file_url: window._portao3FileUrl },
			callback: function (r) {
				if (loadingIndicator) loadingIndicator.classList.add("hidden");
				if (btnConciliar) btnConciliar.disabled = false;

				if (r && r.exc) {
					console.error("Erro process_uploaded_file_portao3", r.exc);
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
				console.error("Erro ao processar Portão 3:", err);
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

	const btnConciliar = document.getElementById("btnConciliarPortao3");
	if (btnConciliar) {
		btnConciliar.addEventListener("click", window.enviarArquivoPortao3);
	}
})();
