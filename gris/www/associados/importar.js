(function () {
	if (window.__importar_associados_inited) return;
	window.__importar_associados_inited = true;

	window._uploadedFileUrl = null;

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
					detail: {
						config: {
							category,
							title,
							description,
						},
					},
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

	function checkShowImportBtn() {
		const btn = document.getElementById("btnImportar");
		const hasFile = !!window._uploadedFileUrl;
		if (btn) {
			btn.classList.toggle("hidden", !hasFile);
			btn.disabled = !hasFile;
		}
	}

	function setupUploader() {
		const uploader = document.getElementById("associadosImportUpload");
		if (!uploader) return;

		uploader.addEventListener("gris:file-upload:success", function (event) {
			const file = event.detail?.files?.[0];
			if (!file) return;

			const fileInfo = document.getElementById("file-info");
			const fileName = document.getElementById("file-name");

			if (fileName) {
				fileName.textContent = file.file_name || file.name || file.file_url;
			}
			if (fileInfo) {
				fileInfo.classList.remove("hidden");
			}

			window._uploadedFileUrl = file.file_url;
			checkShowImportBtn();

			const resultsDiv = document.getElementById("import-results");
			if (resultsDiv) {
				resultsDiv.classList.add("hidden");
			}
		});
	}

	// Cabeçalho e alerta de erros mudam de texto conforme o desfecho: importação parcial
	// (linhas com erro, o resto gravado) ou relatório ilegível (nada gravado).
	function prepareResults(title, subtitle) {
		const resultsDiv = document.getElementById("import-results");
		const resultsGrid = document.getElementById("results-grid");
		const errorsContainer = document.getElementById("errors-container");
		const errorsList = document.getElementById("errors-list");
		const resultsTitle = document.getElementById("results-title");
		const resultsSubtitle = document.getElementById("results-subtitle");

		if (!resultsDiv || !resultsGrid) return false;

		resultsGrid.innerHTML = "";
		resultsGrid.classList.remove("hidden");
		if (errorsContainer) errorsContainer.classList.add("hidden");
		if (errorsList) errorsList.innerHTML = "";
		if (resultsTitle) resultsTitle.textContent = title;
		if (resultsSubtitle) resultsSubtitle.textContent = subtitle;

		resultsDiv.classList.remove("hidden");
		return true;
	}

	function showErrors(title, description, items) {
		const errorsContainer = document.getElementById("errors-container");
		const errorsList = document.getElementById("errors-list");
		if (!errorsContainer || !errorsList || !items || !items.length) return;

		const errorItems = items
			.slice(0, 50)
			.map((err) => {
				const [mainLine, ...extraLines] = String(err || "").split("\n");
				const extra = extraLines
					.map((l) => l.replace(/^\s+/, ""))
					.filter(Boolean)
					.map((l) => `<span class="import-error-detail">${escapeHtml(l)}</span>`)
					.join("");
				return `<li>${escapeHtml(mainLine)}${extra ? `<br>${extra}` : ""}</li>`;
			})
			.join("");

		const moreText =
			items.length > 50
				? `<p class="import-errors__more">+${escapeHtml(
						items.length - 50
				  )} erros adicionais. Consulte o Error Log para ver a lista completa.</p>`
				: "";

		errorsList.innerHTML = `<ul>${errorItems}</ul>${moreText}`;

		const alertTitle = errorsContainer.querySelector(".alert h2");
		if (alertTitle) alertTitle.textContent = title;
		const alertSection = errorsContainer.querySelector(".alert section");
		if (alertSection) alertSection.textContent = description;

		errorsContainer.classList.remove("hidden");
	}

	function renderInvalid(data) {
		if (
			!prepareResults(
				"Relatório não importado",
				"O arquivo foi lido, mas os dados não puderam ser extraídos por completo."
			)
		)
			return;
		document.getElementById("results-grid").classList.add("hidden");

		const lidos = data.total || 0;
		showErrors(
			"Não foi possível ler o relatório",
			`Nada foi importado (${lidos} ${
				lidos === 1 ? "registro lido" : "registros lidos"
			}). ` +
				"Confira se o PDF é o Relatório Customizável do SIGUE e corrija os itens abaixo antes de importar de novo.",
			data.validation_errors || []
		);
	}

	function renderResults(data) {
		if (
			!prepareResults(
				"Resultados da importação",
				"Resumo dos dados processados no relatório."
			)
		)
			return;
		const resultsGrid = document.getElementById("results-grid");

		const stats = [
			{ label: "Total de registros", value: data.total || 0, tone: "primary" },
			{ label: "Criados", value: data.created || 0, tone: "success" },
			{ label: "Atualizados", value: data.updated || 0, tone: "info" },
			{ label: "Sem alteração", value: data.skipped || 0, tone: "muted" },
			{
				label: "Responsáveis criados",
				value: data.responsavel_created || 0,
				tone: "success",
			},
			{
				label: "Responsáveis atualizados",
				value: data.responsavel_updated || 0,
				tone: "info",
			},
			{ label: "Vínculos criados", value: data.vinculo_created || 0, tone: "success" },
			{ label: "Vínculos atualizados", value: data.vinculo_updated || 0, tone: "info" },
			{ label: "Erros", value: data.errors || 0, tone: "error" },
		];

		stats.forEach((stat) => {
			const card = document.createElement("article");
			card.className = "card import-stat-card";
			card.dataset.tone = stat.tone;
			card.innerHTML = `
        <section>
          <p class="import-stat-card__value">${escapeHtml(stat.value)}</p>
          <p class="import-stat-card__label">${escapeHtml(stat.label)}</p>
        </section>
      `;
			resultsGrid.appendChild(card);
		});

		if (data.error_details && data.error_details.length > 0) {
			showErrors(
				"Erros encontrados",
				"As linhas sem erros foram atualizadas com sucesso. Revise os itens abaixo e tente importar novamente após corrigir o relatório.",
				data.error_details
			);
		}
	}

	function plainText(html) {
		const div = document.createElement("div");
		div.innerHTML = String(html ?? "");
		return (div.textContent || "").trim();
	}

	// `fetch` direto em vez de `frappe.call`: no portal o `frappe.call` nunca chama `error`,
	// e uma falha no servidor deixava o indicador de carregamento girando para sempre.
	async function callImporter(fileUrl) {
		const response = await fetch(
			"/api/method/gris.api.associate.importer.parse_associates_report",
			{
				method: "POST",
				headers: {
					"Content-Type": "application/json",
					Accept: "application/json",
					"X-Frappe-CSRF-Token": (window.frappe && frappe.csrf_token) || "",
				},
				credentials: "same-origin",
				body: JSON.stringify({ path_pdf: fileUrl }),
			}
		);
		const json = await response.json().catch(() => ({}));
		if (!response.ok) {
			let message = "Ocorreu um erro ao processar o arquivo.";
			try {
				const list = JSON.parse(json._server_messages || "[]");
				if (list.length) message = JSON.parse(list[0]).message || message;
			} catch (_) {
				/* fica a mensagem genérica */
			}
			throw new Error(plainText(message));
		}
		return json.message || {};
	}

	async function importAssociates() {
		if (!window._uploadedFileUrl) {
			showToast("error", "Nenhum arquivo", "Selecione um arquivo antes de importar.");
			return;
		}

		const loadingIndicator = document.getElementById("loading-indicator");
		const btnImportar = document.getElementById("btnImportar");

		if (loadingIndicator) loadingIndicator.classList.remove("hidden");
		if (btnImportar) btnImportar.disabled = true;

		try {
			const data = await callImporter(window._uploadedFileUrl);

			if (data.status === "invalido") {
				renderInvalid(data);
				showToast(
					"error",
					"Relatório não importado",
					"Os dados do PDF não puderam ser extraídos. Nada foi alterado."
				);
			} else {
				renderResults(data);
				const comErros = (data.errors || 0) > 0;
				showToast(
					comErros ? "warning" : "success",
					comErros ? "Importação concluída com erros" : "Importação concluída",
					comErros
						? "Algumas linhas não foram importadas. Veja os detalhes abaixo."
						: "Os dados dos associados foram processados com sucesso."
				);
			}
		} catch (err) {
			if (
				prepareResults(
					"Relatório não importado",
					"O servidor não conseguiu processar o arquivo."
				)
			) {
				document.getElementById("results-grid").classList.add("hidden");
				showErrors(
					"Erro na importação",
					"Nada foi confirmado como importado. Tente novamente; se o erro continuar, consulte o Error Log.",
					[err.message || "Erro desconhecido."]
				);
			}
			showToast("error", "Erro na importação", err.message || "Erro desconhecido.");
		} finally {
			if (loadingIndicator) loadingIndicator.classList.add("hidden");
			if (btnImportar) btnImportar.disabled = false;
			const resultsDiv = document.getElementById("import-results");
			if (resultsDiv && !resultsDiv.classList.contains("hidden")) {
				resultsDiv.scrollIntoView({ behavior: "smooth", block: "start" });
			}
		}
	}

	setupUploader();
	checkShowImportBtn();

	const btnImportar = document.getElementById("btnImportar");
	if (btnImportar) {
		btnImportar.addEventListener("click", importAssociates);
	}
})();
