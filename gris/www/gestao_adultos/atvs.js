// ATVs da Gestão de Adultos: uma linha por função em vigor, com a validade do acordo.
// A edição (período da função, acordos, exclusão) fica no dialog compartilhado com a
// ficha do associado — ver public/js/funcao_organograma.js.
(function () {
	const raiz = document.querySelector(".atvs");
	if (!raiz) return;

	const PODE_EDITAR = raiz.dataset.podeEditar === "1";

	let linhas = lerJson(raiz.dataset.linhas);

	function lerJson(texto) {
		try {
			return JSON.parse(texto || "[]");
		} catch (e) {
			return [];
		}
	}

	function escapeHtml(valor) {
		const div = document.createElement("div");
		div.textContent = valor == null ? "" : String(valor);
		return div.innerHTML;
	}

	function icone(nome, tamanho) {
		return `<svg class="ds-lucide ds-lucide--${
			tamanho || "sm"
		}" aria-hidden="true" focusable="false" viewBox="0 0 24 24"><use href="/assets/gris/design_system/icons/lucide/sprite.svg#${nome}" /></svg>`;
	}

	function cabecalhoOrdenavel(rotulo, classe) {
		return `<th${
			classe ? ` class="${classe}"` : ""
		} aria-sort="none" data-sortable><button type="button" class="table-sort-trigger"><span>${rotulo}</span><svg class="ds-lucide ds-lucide--xs table-sort-icon" viewBox="0 0 24 24" aria-hidden="true"><use href="/assets/gris/design_system/icons/lucide/sprite.svg#chevrons-up-down" /></svg></button></th>`;
	}

	function data(iso) {
		return iso ? frappe.datetime.str_to_user(iso) : "—";
	}

	function assinaturaHtml(item) {
		if (item.situacao === "sem_atv") {
			return '<span class="badge-destructive">Sem ATV</span>';
		}
		return item.assinado
			? '<span class="badge">Assinado</span>'
			: '<span class="badge-destructive">Não assinado</span>';
	}

	/** Bolinha de status da linha, no mesmo padrão de /associados/lista.
	 *
	 * Vermelho é pendência que já custa (sem acordo ou vencido); amarelo é o acordo que
	 * vale mas ninguém assinou; verde é o que está em ordem.
	 */
	function statusDot(item) {
		if (item.situacao === "sem_atv") {
			return dot("danger", "Sem ATV");
		}
		if (item.situacao === "vencido") {
			return dot("danger", "ATV vencido");
		}
		if (!item.assinado) {
			return dot("warn", "ATV não assinado");
		}
		return dot("ok", "ATV em dia");
	}

	function dot(variante, rotulo) {
		return `<span class="atvs-status-dot atvs-status-dot--${variante}" aria-label="${escapeHtml(
			rotulo
		)}" title="${escapeHtml(rotulo)}"></span>`;
	}

	/** Ordena a coluna da bolinha da pior pendência para a melhor. */
	function ordemDoStatus(item) {
		if (item.situacao === "sem_atv") return 0;
		if (item.situacao === "vencido") return 1;
		return item.assinado ? 3 : 2;
	}

	/** "Dias até o vencimento" em texto, e o número cru para a ordenação da coluna.
	 *
	 * Sem `data-sort-value` numérico, o design system ordenaria "vencido há 10 dias"
	 * como texto e a coluna deixaria de responder à pergunta que ela faz.
	 */
	function vencimentoHtml(item) {
		if (item.dias_para_vencer === null || item.dias_para_vencer === undefined) {
			// Sem acordo nenhum: ordena antes de qualquer prazo real. O traço fica
			// neutro — a pendência já está dita na coluna do selo.
			return `<td data-sort-value="-999999" class="atvs__numero text-muted-foreground">—</td>`;
		}
		const dias = item.dias_para_vencer;
		if (dias < 0) {
			const n = Math.abs(dias);
			return `<td data-sort-value="${dias}" class="atvs__numero"><span class="text-destructive">vencido há ${n} ${
				n === 1 ? "dia" : "dias"
			}</span></td>`;
		}
		return `<td data-sort-value="${dias}" class="atvs__numero">${dias} ${
			dias === 1 ? "dia" : "dias"
		}</td>`;
	}

	function renderizarResumo() {
		const alvo = document.getElementById("atvs-resumo");
		if (!alvo) return;

		const sem = linhas.filter((item) => item.situacao === "sem_atv").length;
		const vencidos = linhas.filter((item) => item.situacao === "vencido").length;
		const naoAssinados = linhas.filter(
			(item) => item.situacao !== "sem_atv" && !item.assinado
		).length;

		if (!sem && !vencidos && !naoAssinados) {
			alvo.hidden = true;
			alvo.innerHTML = "";
			return;
		}

		const partes = [];
		if (sem) partes.push(`${sem} sem ATV`);
		if (vencidos) partes.push(`${vencidos} ${vencidos === 1 ? "vencido" : "vencidos"}`);
		if (naoAssinados)
			partes.push(
				`${naoAssinados} ${naoAssinados === 1 ? "não assinado" : "não assinados"}`
			);

		alvo.hidden = false;
		alvo.innerHTML = `
			<div class="alert" role="status">
				<h2>Acordos pendentes</h2>
				<section>${escapeHtml(partes.join(" · "))} de ${linhas.length} ${
			linhas.length === 1 ? "função" : "funções"
		} em vigor.</section>
			</div>`;
	}

	function renderizarTabela() {
		const alvo = document.getElementById("atvs-tabela");
		if (!alvo) return;

		const corpo = linhas
			.map((item) => {
				const acoes = PODE_EDITAR
					? `<button type="button" class="btn-sm-ghost" data-acao="detalhes" data-linha="${escapeHtml(
							item.linha
					  )}" aria-label="Detalhes de ${escapeHtml(item.funcao)} de ${escapeHtml(
							item.nome
					  )}">${icone("ellipsis")}</button>`
					: "";
				const area = item.area
					? `<span class="atvs__area">${escapeHtml(item.area)}</span>`
					: "";
				return `<tr data-linha="${escapeHtml(item.linha)}">
					<td class="atvs__status" data-sort-value="${ordemDoStatus(item)}">${statusDot(item)}</td>
					<td data-sort-value="${escapeHtml(item.nome)}">${escapeHtml(item.nome)}</td>
					<td data-sort-value="${escapeHtml(item.funcao)}">${escapeHtml(item.funcao)} ${area}</td>
					<td data-sort-value="${item.situacao === "sem_atv" ? 0 : item.assinado ? 2 : 1}">${assinaturaHtml(
					item
				)}</td>
					<td data-sort-value="${escapeHtml(item.data_inicio || "")}">${escapeHtml(
					data(item.data_inicio)
				)}</td>
					<td data-sort-value="${escapeHtml(item.data_fim || "")}">${escapeHtml(data(item.data_fim))}</td>
					${vencimentoHtml(item)}
					<td class="atvs__acoes">${acoes}</td>
				</tr>`;
			})
			.join("");

		alvo.innerHTML = `<table class="table table-sortable atvs__tabela" data-table-sortable>
			<thead>
				<tr>
					${cabecalhoOrdenavel("Situação", "atvs__status")}
					${cabecalhoOrdenavel("Nome")}
					${cabecalhoOrdenavel("Função")}
					${cabecalhoOrdenavel("ATV assinado")}
					${cabecalhoOrdenavel("Data de início")}
					${cabecalhoOrdenavel("Data de término")}
					${cabecalhoOrdenavel("Dias até o vencimento", "atvs__numero")}
					<th class="atvs__acoes"></th>
				</tr>
			</thead>
			<tbody>${corpo}</tbody>
		</table>`;
	}

	function renderizar() {
		renderizarResumo();
		renderizarTabela();
	}

	/** A linha continua na tabela; o que mudou foi só o acordo que vale para ela. */
	function aplicarValidade(linhaId, validade) {
		const item = linhas.find((linha) => linha.linha === linhaId);
		if (!item) return;
		Object.assign(item, validade);
		renderizar();
	}

	/** Encerrar ou apagar a função tira a linha da lista de "em vigor".
	 *
	 * A resposta traz as funções da pessoa toda, então a reconciliação é por associado:
	 * some quem saiu de vigor e atualizam-se as datas de quem ficou.
	 */
	function aplicarFuncoes(funcoes) {
		const daPessoa = new Set(funcoes.map((f) => f.linha));
		const emVigor = new Map(funcoes.filter((f) => f.atual).map((f) => [f.linha, f]));

		linhas = linhas
			.map((item) => {
				if (!daPessoa.has(item.linha)) return item;
				const nova = emVigor.get(item.linha);
				if (!nova) return null;
				return Object.assign({}, item, {
					funcao: nova.funcao,
					area: nova.area,
					principal: nova.principal,
					funcao_inicio: nova.data_inicio,
					funcao_fim: nova.data_fim,
				});
			})
			.filter(Boolean);
		renderizar();
	}

	document.addEventListener("click", (evento) => {
		const botao = evento.target.closest('[data-acao="detalhes"]');
		if (!botao || !raiz.contains(botao) || !window.grisFuncaoOrganograma) return;

		const item = linhas.find((linha) => linha.linha === botao.dataset.linha);
		if (!item) return;

		window.grisFuncaoOrganograma.abrir(
			{
				associado: item.associado,
				nome: item.nome,
				linha: item.linha,
				funcao: item.funcao,
				area: item.area,
				principal: item.principal,
				data_inicio: item.funcao_inicio,
				data_fim: item.funcao_fim,
			},
			{ aoMudar: aplicarFuncoes, aoMudarValidade: aplicarValidade }
		);
	});

	renderizar();
})();
