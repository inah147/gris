function renderExtratoPagination(container, totalPages, current, buildUrl) {
	container.innerHTML = "";
	container.classList.add("btn-group");
	const addItem = (label, page, disabled = false, active = false) => {
		const baseClass = active ? "btn-sm-primary" : "btn-sm-outline";
		if (disabled || active) {
			const btn = document.createElement("button");
			btn.type = "button";
			btn.textContent = label;
			btn.className = baseClass;
			if (active) btn.setAttribute("aria-current", "page");
			if (disabled) {
				btn.disabled = true;
				btn.setAttribute("aria-disabled", "true");
			}
			container.appendChild(btn);
		} else {
			const a = document.createElement("a");
			a.textContent = label;
			a.className = baseClass;
			a.href = buildUrl(page);
			container.appendChild(a);
		}
	};
	addItem("«", 1, current === 1);
	addItem("‹", current - 1, current === 1);
	const windowSize = 5;
	let start = Math.max(1, current - Math.floor(windowSize / 2));
	let end = start + windowSize - 1;
	if (end > totalPages) {
		end = totalPages;
		start = Math.max(1, end - windowSize + 1);
	}
	for (let p = start; p <= end; p++) addItem(String(p), p, false, p === current);
	addItem("›", current + 1, current === totalPages);
	addItem("»", totalPages, current === totalPages);
}

document.addEventListener("DOMContentLoaded", function () {
	const pagDiv = document.getElementById("extrato-pagination");
	if (!pagDiv) return;
	const total = parseInt(pagDiv.dataset.total, 10);
	const page = parseInt(pagDiv.dataset.page, 10);
	const pageSize = parseInt(pagDiv.dataset.pagesize, 10);
	const totalPages = Math.ceil(total / pageSize);
	if (totalPages <= 1) return;
	function buildUrl(p) {
		const params = new URLSearchParams(window.location.search);
		params.set("page", p);
		return window.location.pathname + "?" + params.toString();
	}
	renderExtratoPagination(pagDiv, totalPages, page, buildUrl);
});
