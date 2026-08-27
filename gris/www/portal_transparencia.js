frappe.ready(() => {
	const page = document.querySelector("[data-transparencia-root]");
	const yearFilter = document.getElementById("transparency-year-filter");
	const areasContainer = document.getElementById("areas-container");

	if (!page || !yearFilter || !areasContainer) {
		return;
	}

	const endpoint =
		page.dataset.annualEndpoint || "/api/method/gris.api.transparencia.get_arquivos_por_ano";
	const yearTrigger = document.getElementById(`${yearFilter.id}-trigger`);

	const escapeHtml = (value) => {
		const div = document.createElement("div");
		div.textContent = value == null ? "" : String(value);
		return div.innerHTML;
	};

	const icon = (name, size = "md", className = "") => `
		<svg class="ds-lucide ds-lucide--${size} ${className}" aria-hidden="true" focusable="false" viewBox="0 0 24 24">
			<use href="/assets/gris/design_system/icons/lucide/sprite.svg#${name}"></use>
		</svg>
	`;

	const renderDocumentCard = (doc, eyebrow) => `
		<article class="card transparencia-doc-card">
			<section>
				<div class="transparencia-doc-card__body">
					<div class="transparencia-doc-card__icon" aria-hidden="true">
						${icon("file-text", "lg")}
					</div>
					<div class="transparencia-doc-card__copy">
						<p class="transparencia-doc-card__eyebrow">${escapeHtml(eyebrow)}</p>
						<h3 class="transparencia-doc-card__title">${escapeHtml(doc.title || "Documento")}</h3>
					</div>
				</div>
			</section>
			<footer>
				<a href="${escapeHtml(
					doc.arquivo || "#"
				)}" target="_blank" rel="noopener" class="btn-sm-primary transparencia-doc-card__action">
					${icon("arrow-up-right", "sm")}
					<span>Abrir arquivo</span>
				</a>
			</footer>
		</article>
	`;

	const renderEmptyState = () => `
		<section class="empty transparencia-empty">
			<div class="empty-icon">${icon("folder-search", "lg")}</div>
			<h2>Nenhum documento encontrado</h2>
			<p>Ainda não há publicações disponíveis para o ano selecionado.</p>
		</section>
	`;

	const renderLoadingState = () => `
		<div class="transparencia-loading" role="status" aria-live="polite">
			<span class="spinner" aria-hidden="true"></span>
			<p>Carregando publicações do ano selecionado...</p>
		</div>
	`;

	const renderErrorState = () => `
		<div class="alert alert-warning transparencia-feedback" role="status">
			${icon("triangle-alert", "sm")}
			<section>
				<h2>Não foi possível atualizar a listagem</h2>
				<p>Tente novamente em alguns instantes.</p>
			</section>
		</div>
	`;

	const renderAreas = (areas) => {
		const entries = Object.entries(areas || {});
		if (!entries.length) {
			areasContainer.innerHTML = renderEmptyState();
			return;
		}

		areasContainer.innerHTML = `
			<div class="transparencia-area-list">
				${entries
					.map(
						([area, arquivos]) => `
						<section class="transparencia-area">
							<div class="transparencia-area__header">
								<div>
									<h3 class="transparencia-area__title">${escapeHtml(area)}</h3>
									<p class="transparencia-area__meta">${arquivos.length} documento${
							arquivos.length === 1 ? "" : "s"
						} publicado${arquivos.length === 1 ? "" : "s"}.</p>
								</div>
								<span class="badge badge-secondary">${arquivos.length} item${
							arquivos.length === 1 ? "" : "s"
						}</span>
							</div>
							<div class="transparencia-doc-grid">
								${arquivos.map((doc) => renderDocumentCard(doc, "Documento anual")).join("")}
							</div>
						</section>
					`
					)
					.join("")}
			</div>
		`;
	};

	const setFilterBusy = (busy) => {
		if (yearTrigger) {
			yearTrigger.disabled = busy;
			yearTrigger.setAttribute("aria-busy", busy ? "true" : "false");
		}
	};

	const syncUrl = (year) => {
		const url = new URL(window.location.href);
		if (year) {
			url.searchParams.set("ano_referencia", year);
		} else {
			url.searchParams.delete("ano_referencia");
		}
		window.history.replaceState({}, "", url);
	};

	const loadYear = async (year) => {
		if (!year) {
			renderAreas({});
			return;
		}

		setFilterBusy(true);
		areasContainer.innerHTML = renderLoadingState();

		try {
			const response = await fetch(
				`${endpoint}?ano_referencia=${encodeURIComponent(year)}`,
				{
					headers: { Accept: "application/json" },
				}
			);

			if (!response.ok) {
				throw new Error(`Falha ao carregar documentos: ${response.status}`);
			}

			const data = await response.json();
			renderAreas(data.message?.areas || {});
			syncUrl(year);
			document.dispatchEvent(new CustomEvent("gris:design-system:init"));
		} catch (error) {
			console.error(error);
			areasContainer.innerHTML = renderErrorState();
		} finally {
			setFilterBusy(false);
		}
	};

	yearFilter.addEventListener("change", () => {
		loadYear(yearFilter.value || "");
	});
});
