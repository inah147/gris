(function () {
	"use strict";

	const POLL_INTERVAL_MS = 5000;
	const MAX_ATTEMPTS = 60; // ~5 min total

	const root = document.querySelector(".cc-page");
	if (!root) return;
	if (root.dataset.estado !== "pendente") return;

	const convite = root.dataset.convite || "";
	const token = root.dataset.token || "";
	if (!convite || !token) return;

	let attempts = 0;
	let timer = null;
	let stopped = false;

	function stop() {
		stopped = true;
		if (timer) {
			clearTimeout(timer);
			timer = null;
		}
	}

	function scheduleNext() {
		if (stopped || attempts >= MAX_ATTEMPTS) return;
		timer = setTimeout(poll, POLL_INTERVAL_MS);
	}

	async function poll() {
		if (stopped) return;
		attempts += 1;
		try {
			const url =
				"/api/method/gris.api.festas.convite_confirmado.get_status" +
				"?c=" +
				encodeURIComponent(convite) +
				"&t=" +
				encodeURIComponent(token);
			const response = await fetch(url, {
				method: "GET",
				headers: { "X-Requested-With": "XMLHttpRequest" },
				credentials: "same-origin",
			});
			if (response.status === 404) {
				stop();
				return;
			}
			if (response.status === 429) {
				scheduleNext();
				return;
			}
			if (!response.ok) {
				scheduleNext();
				return;
			}
			const payload = await response.json();
			const status = (payload && payload.message && payload.message.status) || "";
			if (status === "Pago") {
				stop();
				window.location.reload();
				return;
			}
			if (
				status === "Erro" ||
				status === "Cancelado" ||
				status === "Estornado" ||
				status === "Expirado"
			) {
				stop();
				window.location.reload();
				return;
			}
			scheduleNext();
		} catch (_err) {
			scheduleNext();
		}
	}

	document.addEventListener("visibilitychange", function () {
		if (document.hidden) {
			if (timer) {
				clearTimeout(timer);
				timer = null;
			}
		} else if (!stopped && attempts < MAX_ATTEMPTS) {
			scheduleNext();
		}
	});

	scheduleNext();
})();
