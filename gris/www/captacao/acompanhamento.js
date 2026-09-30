// Kanban do banco de projetos de captação.
//
// Só as colunas de captação (Pronto, Em andamento, Finalizada, Cancelado) aceitam
// arraste: as anteriores mudam pelas decisões na página do projeto. O servidor
// confere tudo de novo em `mover_card`.
(function () {
	const raiz = document.querySelector(".captacao-kanban-raiz");
	if (!raiz || !window.grisCaptacao) return;
	const { chamar, escapeHtml, icone, toast, moeda, lerJson } = window.grisCaptacao;

	const container = document.getElementById("captacao-kanban");
	const inicial = lerJson(raiz.dataset.kanbanInicial, {}) || {};
	const podeMover = Boolean(inicial.pode_mover);
	let colunas = inicial.colunas || [];
	let arrastando = "";

	function arrastavel(status) {
		const coluna = colunas.find((c) => c.status === status);
		return podeMover && coluna && coluna.aceita_arraste;
	}

	function cardHtml(card, status) {
		const pendencias = card.pendencias
			? `<span class="badge-destructive" title="Pedidos de alteração em aberto">${icone(
					"message-square",
					"xs"
			  )} ${card.pendencias}</span>`
			: "";
		const valor = card.valor_total
			? `<span class="captacao-card__valor">${escapeHtml(moeda(card.valor_total))}</span>`
			: "";
		return `<a class="task-card captacao-card" href="/captacao/projeto?name=${encodeURIComponent(
			card.name
		)}" data-item="${escapeHtml(card.name)}" draggable="${
			arrastavel(status) ? "true" : "false"
		}">
			<h4 class="task-card__title" title="${escapeHtml(card.titulo)}">${escapeHtml(card.titulo)}</h4>
			<div class="captacao-card__badges">
				${card.tipo ? `<span class="badge-outline">${escapeHtml(card.tipo)}</span>` : ""}
				${pendencias}
			</div>
			<div class="task-card__footer">
				<span class="captacao-card__meta">${escapeHtml(card.proponente || "")}</span>
				${valor}
			</div>
		</a>`;
	}

	function renderizar() {
		container.innerHTML = colunas
			.map((coluna) => {
				const cards = coluna.cards || [];
				const corpo = cards.length
					? cards.map((c) => cardHtml(c, coluna.status)).join("")
					: '<p class="captacao-coluna-vazia">Nenhum projeto.</p>';
				const trava =
					podeMover && !coluna.aceita_arraste
						? `<span class="captacao-coluna__trava" title="Esta etapa muda pelas decisões no projeto">${icone(
								"lock",
								"xs"
						  )}</span>`
						: "";
				return `<section class="task-column" data-coluna="${escapeHtml(coluna.status)}">
					<header class="task-column__header">
						<div class="task-column__heading">
							<h4 class="task-column__title">${escapeHtml(coluna.status)} ${trava}</h4>
							<p class="task-column__subtitle">${cards.length} ${cards.length === 1 ? "projeto" : "projetos"}</p>
						</div>
					</header>
					<div class="task-column__body" data-status="${escapeHtml(coluna.status)}">${corpo}</div>
				</section>`;
			})
			.join("");
	}

	async function recarregar() {
		try {
			const dados = await chamar("listar_kanban");
			colunas = dados.colunas || [];
			renderizar();
		} catch (erro) {
			toast("error", erro.message);
		}
	}

	async function mover(nome, novoStatus) {
		const origem = colunas.find((c) => (c.cards || []).some((card) => card.name === nome));
		const destino = colunas.find((c) => c.status === novoStatus);
		if (!origem || !destino || origem.status === novoStatus) return;

		// Move otimista: o card acompanha o gesto e volta se o servidor recusar.
		const indice = origem.cards.findIndex((card) => card.name === nome);
		const [card] = origem.cards.splice(indice, 1);
		destino.cards.unshift(card);
		renderizar();

		try {
			await chamar("mover_card", { name: nome, status: novoStatus });
			toast("success", `Movido para “${novoStatus}”.`);
		} catch (erro) {
			toast("error", erro.message);
			recarregar();
		}
	}

	function limparIndicadores() {
		container
			.querySelectorAll(".task-column__body.is-drop-target")
			.forEach((el) => el.classList.remove("is-drop-target"));
	}

	container.addEventListener("dragstart", (evento) => {
		const card = evento.target.closest(".task-card");
		if (!card || card.getAttribute("draggable") !== "true") return;
		arrastando = card.dataset.item || "";
		card.classList.add("is-dragging");
		if (evento.dataTransfer) {
			evento.dataTransfer.effectAllowed = "move";
			evento.dataTransfer.setData("text/plain", arrastando);
		}
	});

	container.addEventListener("dragend", (evento) => {
		const card = evento.target.closest(".task-card");
		if (card) card.classList.remove("is-dragging");
		limparIndicadores();
		arrastando = "";
	});

	container.addEventListener("dragover", (evento) => {
		const coluna = evento.target.closest(".task-column__body");
		if (!coluna || !arrastando || !arrastavel(coluna.dataset.status)) return;
		evento.preventDefault();
		coluna.classList.add("is-drop-target");
	});

	container.addEventListener("dragleave", (evento) => {
		const coluna = evento.target.closest(".task-column__body");
		if (!coluna || coluna.contains(evento.relatedTarget)) return;
		coluna.classList.remove("is-drop-target");
	});

	container.addEventListener("drop", (evento) => {
		const coluna = evento.target.closest(".task-column__body");
		if (!coluna || !arrastavel(coluna.dataset.status)) return;
		evento.preventDefault();
		const nome =
			arrastando || (evento.dataTransfer && evento.dataTransfer.getData("text/plain")) || "";
		limparIndicadores();
		// Zera antes de mover: renderizar() troca o innerHTML e o `dragend` do card
		// de origem, já desanexado, não dispara.
		arrastando = "";
		if (nome) mover(nome, coluna.dataset.status);
	});

	renderizar();
})();
