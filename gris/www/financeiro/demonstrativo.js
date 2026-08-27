document.addEventListener("DOMContentLoaded", () => {
	const form = document.getElementById("demonstrativo-filter");
	const yearInput = document.getElementById("ano");
	const yearSelect = yearInput ? yearInput.closest(".select") : null;

	if (!form || !yearInput) {
		return;
	}

	// Basecoat select dispatches `change` on the wrapper element.
	const eventTarget = yearSelect || yearInput;
	eventTarget.addEventListener("change", () => {
		form.submit();
	});
});
