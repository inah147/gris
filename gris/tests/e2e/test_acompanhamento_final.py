"""Validação ponta a ponta das colunas de acompanhamento em `/recepcao/visao_geral`.

Roda contra o site vivo, com navegador de verdade — não entra na suíte do `bench run-tests`,
que não sobe servidor nem browser. Uso:

    cd /workspace/frappe-bench && env/bin/python apps/gris/gris/tests/e2e/test_acompanhamento_final.py

O roteiro cobre o que só se enxerga no navegador: as três listas de acompanhamento no kanban,
a timeline de cada tipo de registro na ordem certa (boleto provisório entre o Paxtu e a
efetivação provisória; no definitivo, boleto e efetivação logo depois do Paxtu), o card
migrando para "Acompanhamento Final" quando o registro definitivo é efetivado pela timeline,
voltando quando a efetivação é desmarcada, e o infográfico da ficha de registro. As regras em
si estão cobertas por `gris/tests/test_recepcao_funil.py`.

O seed cria os jovens e o `finally` os remove: `dev.gris` tem dados restaurados de produção e
resíduo de teste ali muda o cenário de quem rodar a suíte depois. Os CPFs são exclusivos
deste arquivo. Os nomes começam com "E2E" para o filtro de nome do kanban isolar os cards do
roteiro — as screenshots não mostram ninguém de verdade.

Três detalhes deste devcontainer, todos obrigatórios e nenhum óbvio pelo sintoma:

1. `HOME=/workspace`, então o Playwright procura o browser no caminho errado — o
   `executable_path` vai explícito.
2. `dev.gris` não está em `/etc/hosts`; sem `--host-resolver-rules` o `goto` dá `ERR_ABORTED`.
   O bench serve na porta 80.
3. O formulário de `/login` roda no shell do Desk e termina em "Acesso negado": a sessão vem
   do cookie da API, injetado no contexto.
"""

import json
import pathlib
import sys
import urllib.request

CHROME = "/workspace/.cache/ms-playwright/chromium-1234/chrome-linux64/chrome"
BASE = "http://dev.gris"
API = "http://127.0.0.1"
SITE = "dev.gris"

USUARIO = "Administrator"
SENHA = "admin"

SHOTS = pathlib.Path(__file__).parent / "shots"

VIEWPORT = {"width": 1600, "height": 1000}

COLUNA_PROVISORIO = "Acompanhamento Provisório"
COLUNA_DEFINITIVO = "Acompanhamento Definitivo"
COLUNA_FINAL = "Acompanhamento Final"

falhas = []


def _cpf(base9: str) -> str:
	"""CPF fictício com dígitos verificadores corretos, a partir de 9 dígitos."""
	digitos = [int(d) for d in base9]
	for posicao in (9, 10):
		soma = sum(d * (posicao + 1 - i) for i, d in enumerate(digitos))
		resto = 11 - (soma % 11)
		digitos.append(0 if resto >= 10 else resto)
	return "".join(str(d) for d in digitos)


# chave -> (nome, CPF, campos próprios). Todos já têm o registro criado no Paxtu, que é o
# que põe o card em "Acompanhamento"; a lista de acompanhamento sai do resto.
JOVENS = {
	"prov_boleto": (
		"E2E Provisório Aguardando Boleto",
		_cpf("314159265"),
		{"tipo_de_registro": "Provisório"},
	),
	"prov_efetivado": (
		"E2E Provisório Efetivado",
		_cpf("271828182"),
		{"tipo_de_registro": "Provisório", "registro_provisorio_efetivado": 1},
	),
	# Com número de registro: a efetivação pela timeline não precisa do diálogo dos números.
	"def_registro": (
		"E2E Definitivo Aguardando Registro",
		_cpf("141421356"),
		{"tipo_de_registro": "Definitivo", "numero_de_registro": "E2E-0001"},
	),
	"def_final": (
		"E2E Definitivo Registrado",
		_cpf("173205080"),
		{
			"tipo_de_registro": "Definitivo",
			"numero_de_registro": "E2E-0002",
			"registro_definitivo_efetivado": 1,
			"pesquisa_de_novos_associados_respondida": 1,
		},
	),
}

ORDEM_PROVISORIO = [
	"Visita Agendada",
	"Primeira Visita Realizada",
	"Dados Enviados",
	"Registro no Paxtu",
	"Boleto Provisório Gerado",
	"Registro Provisório Efetivado",
	"Pesquisa Respondida",
	"Ficha Médica",
	"ID Escoteiros Criado",
	"Boleto Definitivo Gerado",
	"Registro Definitivo Efetivado",
	"Reunião de Acolhida",
]

ORDEM_DEFINITIVO = [
	"Visita Agendada",
	"Primeira Visita Realizada",
	"Dados Enviados",
	"Registro no Paxtu",
	"Boleto Definitivo Gerado",
	"Registro Definitivo Efetivado",
	"Pesquisa Respondida",
	"Ficha Médica",
	"ID Escoteiros Criado",
	"Reunião de Acolhida",
]

FICHA_PROVISORIO = [
	"Visita Agendada",
	"Primeira Visita",
	"Dados Enviados",
	"Registro Paxtu",
	"Boleto Prov.",
	"Prov. Efetivado",
	"Pesquisa Respondida",
	"Ficha Médica",
	"ID Criado",
	"Boleto Def.",
	"Def. Efetivado",
	"Acolhida",
]

FICHA_DEFINITIVO = [
	"Visita Agendada",
	"Primeira Visita",
	"Dados Enviados",
	"Registro Paxtu",
	"Boleto Def.",
	"Def. Efetivado",
	"Pesquisa Respondida",
	"Ficha Médica",
	"ID Criado",
	"Acolhida",
]


def checa(rotulo, obtido, esperado):
	ok = obtido == esperado
	print(f"  [{'ok  ' if ok else 'FALHA'}] {rotulo}: {obtido!r}" + ("" if ok else f" != {esperado!r}"))
	if not ok:
		falhas.append(f"{rotulo}: {obtido!r} != {esperado!r}")


# --------------------------------------------------------------------------------------
# Seed e limpeza
# --------------------------------------------------------------------------------------


def _nomes_dos_docs():
	from gris.utils.documento import id_por_cpf

	return {chave: id_por_cpf(cpf) for chave, (_nome, cpf, _campos) in JOVENS.items()}


def semear():
	import frappe
	from frappe.utils import add_years, nowdate

	frappe.set_user("Administrator")
	limpar_jovens()

	docs = {}
	for chave, (nome, cpf, campos) in JOVENS.items():
		doc = frappe.new_doc("Novo Associado")
		doc.update(
			{
				"nome_completo": nome,
				"cpf": cpf,
				# 12 anos: fora do ramo Filhotes, onde responsáveis também tiram registro.
				"data_de_nascimento": add_years(nowdate(), -12),
				"status": "Acompanhamento",
				"visita_agendada": 1,
				"primeira_visita_realizada": 1,
				"dados_para_registro_enviados": 1,
				"registro_criado_no_paxtu": 1,
				**campos,
			}
		)
		doc.insert(ignore_permissions=True)
		docs[chave] = doc.name

	frappe.db.commit()
	return docs


def limpar_jovens():
	import frappe

	for name in _nomes_dos_docs().values():
		if frappe.db.exists("Novo Associado", name):
			frappe.delete_doc("Novo Associado", name, force=True, ignore_permissions=True)
	frappe.db.commit()


# --------------------------------------------------------------------------------------
# Roteiro no navegador
# --------------------------------------------------------------------------------------


def pegar_sid():
	requisicao = urllib.request.Request(
		f"{API}/api/method/login",
		data=json.dumps({"usr": USUARIO, "pwd": SENHA}).encode(),
		headers={"Content-Type": "application/json", "Host": SITE},
	)
	with urllib.request.urlopen(requisicao) as resposta:
		cookies = resposta.headers.get_all("Set-Cookie") or []
	for cookie in cookies:
		if cookie.startswith("sid="):
			return cookie.split(";")[0][4:]
	raise RuntimeError("login não devolveu o cookie de sessão")


def abrir_kanban(page):
	page.goto(f"{BASE}/recepcao/visao_geral")
	page.wait_for_selector(".kanban-container")
	# O filtro de nome fica no sessionStorage e sobrevive aos reloads que as etapas disparam.
	page.fill("#filtroNome", "e2e")
	page.wait_for_timeout(200)


def anonimizar(page):
	"""Tira nomes de gente de verdade do que a screenshot pode mostrar.

	O filtro já esconde os cards reais, mas o repositório é público: a troca garante que nem
	um card que escape do filtro nem o rodapé com a recepção apareçam no print.
	"""
	page.evaluate(
		"""() => {
			let n = 0;
			document.querySelectorAll('.kanban-card').forEach((card) => {
				const titulo = card.querySelector('.kanban-card__title');
				if (titulo && !titulo.textContent.trim().startsWith('E2E')) {
					n += 1;
					titulo.textContent = `Jovem ${n}`;
				}
				const subtitulo = card.querySelector('.kanban-card__subtitle');
				if (subtitulo) subtitulo.textContent = 'Responsável';
				const avatar = card.querySelector('.kanban-card__avatar');
				if (avatar) {
					avatar.textContent = 'R';
					avatar.removeAttribute('title');
				}
				const meta = card.querySelector('.kanban-card__meta > span:not(.kanban-card__avatar)');
				if (meta) meta.textContent = 'Recepção';
			});
		}"""
	)


def rolar_ate_o_fim(page):
	page.eval_on_selector(".kanban-container", "el => { el.scrollLeft = el.scrollWidth; }")
	page.wait_for_timeout(200)


def coluna_do_card(page, name):
	return page.locator(f'.kanban-card[data-id="{name}"]').get_attribute("data-status")


def abrir_card(page, name):
	page.click(f'.kanban-card[data-id="{name}"] .kanban-card__title')
	# Um <dialog> aberto reporta altura 0 ao Playwright: espera-se num filho com caixa.
	page.wait_for_selector("#ac_timeline .timeline-item", state="visible")
	page.wait_for_timeout(400)


def etapas_da_timeline(page):
	# O primeiro nó do rótulo é o texto da etapa; depois vêm a data prevista e o ícone.
	return page.eval_on_selector_all(
		"#ac_timeline .timeline-label",
		"els => els.map((el) => el.childNodes[0].textContent.trim())",
	)


def item_da_timeline(page, rotulo):
	return page.locator("#ac_timeline .timeline-item").filter(
		has=page.locator(".timeline-label", has_text=rotulo)
	)


def clicar_na_etapa(page, rotulo):
	"""Clica na etapa pelo texto de ajuda, longe do ícone de informação que só mostra a dica."""
	item_da_timeline(page, rotulo).locator(".timeline-helper").click()


def print_do_modal(page, arquivo):
	"""Só o painel do modal, numa janela alta o bastante para a timeline caber sem rolar."""
	page.set_viewport_size({"width": VIEWPORT["width"], "height": 1600})
	page.wait_for_timeout(300)
	page.locator("#modalAcompanhamento > div").screenshot(path=str(SHOTS / arquivo))
	page.set_viewport_size(VIEWPORT)


def cenario_colunas(page, docs):
	print("\n== Kanban: as três listas de acompanhamento ==")
	abrir_kanban(page)

	colunas = page.eval_on_selector_all(".kanban-column", "cols => cols.map((c) => c.dataset.status)")
	checa("últimas colunas", colunas[-3:], [COLUNA_PROVISORIO, COLUNA_DEFINITIVO, COLUNA_FINAL])

	titulos = page.eval_on_selector_all(
		".kanban-column__title", "els => els.map((el) => el.textContent.trim())"
	)
	checa("títulos das colunas", titulos[-3:], ["Acomp. Provisório", "Acomp. Definitivo", "Acomp. Final"])

	checa("provisório aguardando boleto", coluna_do_card(page, docs["prov_boleto"]), COLUNA_PROVISORIO)
	checa("provisório efetivado", coluna_do_card(page, docs["prov_efetivado"]), COLUNA_DEFINITIVO)
	checa("definitivo aguardando registro", coluna_do_card(page, docs["def_registro"]), COLUNA_DEFINITIVO)
	checa("definitivo registrado", coluna_do_card(page, docs["def_final"]), COLUNA_FINAL)

	anonimizar(page)
	rolar_ate_o_fim(page)
	page.screenshot(path=str(SHOTS / "01-kanban-acompanhamentos.png"))


def cenario_timeline_provisorio(page, docs):
	print("\n== Timeline do registro provisório ==")
	abrir_card(page, docs["prov_boleto"])

	checa("título do modal", page.inner_text("#modalAcompanhamento-title").strip(), COLUNA_PROVISORIO)
	checa("ordem das etapas", etapas_da_timeline(page), ORDEM_PROVISORIO)
	checa(
		"boleto provisório pendente",
		"completed" in (item_da_timeline(page, "Boleto Provisório Gerado").get_attribute("class") or ""),
		False,
	)
	print_do_modal(page, "02-timeline-provisorio.png")
	page.keyboard.press("Escape")

	# O controller marca o boleto de quem já teve o provisório efetivado.
	abrir_card(page, docs["prov_efetivado"])
	checa(
		"efetivação provisória implica o boleto",
		"completed" in (item_da_timeline(page, "Boleto Provisório Gerado").get_attribute("class") or ""),
		True,
	)
	page.keyboard.press("Escape")


def cenario_definitivo_ate_o_final(page, docs):
	print("\n== Timeline do registro definitivo até o Acompanhamento Final ==")
	jovem = docs["def_registro"]
	abrir_card(page, jovem)

	checa("título do modal", page.inner_text("#modalAcompanhamento-title").strip(), COLUNA_DEFINITIVO)
	checa("ordem das etapas", etapas_da_timeline(page), ORDEM_DEFINITIVO)
	print_do_modal(page, "03-timeline-definitivo.png")

	# Boleto emitido não tira o card da lista definitiva: falta o pagamento.
	with page.expect_navigation():
		clicar_na_etapa(page, "Boleto Definitivo Gerado")
	page.wait_for_selector(".kanban-container")
	checa("boleto marcado, card continua", coluna_do_card(page, jovem), COLUNA_DEFINITIVO)

	abrir_card(page, jovem)
	with page.expect_navigation():
		clicar_na_etapa(page, "Registro Definitivo Efetivado")
	page.wait_for_selector(".kanban-container")
	checa("registro efetivado, card vai para a final", coluna_do_card(page, jovem), COLUNA_FINAL)

	anonimizar(page)
	rolar_ate_o_fim(page)
	page.screenshot(path=str(SHOTS / "04-card-no-acompanhamento-final.png"))

	abrir_card(page, jovem)
	checa("título do modal", page.inner_text("#modalAcompanhamento-title").strip(), COLUNA_FINAL)
	pendentes = page.eval_on_selector_all(
		"#ac_timeline .timeline-item:not(.completed) .timeline-label",
		"els => els.map((el) => el.childNodes[0].textContent.trim())",
	)
	checa(
		"pendências do acompanhamento final",
		pendentes,
		["Pesquisa Respondida", "Ficha Médica", "ID Escoteiros Criado", "Reunião de Acolhida"],
	)
	print_do_modal(page, "05-modal-acompanhamento-final.png")


def cenario_desmarcar(page, docs):
	print("\n== Desmarcar a efetivação devolve o card à lista definitiva ==")
	jovem = docs["def_registro"]

	clicar_na_etapa(page, "Registro Definitivo Efetivado")
	page.wait_for_selector("#btnConfirmarDesmarcar", state="visible")
	page.wait_for_timeout(400)
	checa(
		"aviso do diálogo",
		page.inner_text("#de_efeitos").strip(),
		f"O card pode voltar para {COLUNA_DEFINITIVO}.",
	)
	page.screenshot(path=str(SHOTS / "06-desmarcar-efetivacao.png"))

	with page.expect_navigation():
		page.click("#btnConfirmarDesmarcar")
	page.wait_for_selector(".kanban-container")
	checa("efetivação desmarcada, card volta", coluna_do_card(page, jovem), COLUNA_DEFINITIVO)


def conferir_ficha(page, novo_associado, passo, esperado):
	print(f"\n== Ficha de registro ({passo}) ==")
	# O infográfico rola na horizontal quando não cabe; em tela cheia as 12 etapas do
	# provisório aparecem juntas no print.
	page.set_viewport_size({"width": 1920, "height": VIEWPORT["height"]})
	page.goto(f"{BASE}/recepcao/ficha_registro?name={novo_associado}")
	page.wait_for_selector(".flow-steps-container")

	rotulos = page.eval_on_selector_all(".flow-step__label", "els => els.map((el) => el.textContent.trim())")
	checa("ordem do infográfico", rotulos, esperado)
	page.locator(".flow-steps-container").screenshot(path=str(SHOTS / f"07-ficha-{passo}.png"))
	page.set_viewport_size(VIEWPORT)


def rodar_no_navegador(docs):
	from playwright.sync_api import sync_playwright

	with sync_playwright() as p:
		browser = p.chromium.launch(
			executable_path=CHROME,
			args=["--no-sandbox", f"--host-resolver-rules=MAP {SITE} 127.0.0.1"],
		)
		contexto = browser.new_context(viewport=VIEWPORT, service_workers="block")
		contexto.add_cookies([{"name": "sid", "value": pegar_sid(), "domain": SITE, "path": "/"}])
		page = contexto.new_page()
		page.on("pageerror", lambda erro: falhas.append(f"erro de JS na página: {erro}"))

		cenario_colunas(page, docs)
		cenario_timeline_provisorio(page, docs)
		cenario_definitivo_ate_o_final(page, docs)
		cenario_desmarcar(page, docs)
		conferir_ficha(page, docs["def_registro"], "definitivo", FICHA_DEFINITIVO)
		conferir_ficha(page, docs["prov_boleto"], "provisorio", FICHA_PROVISORIO)

		browser.close()


def main():
	import frappe

	SHOTS.mkdir(parents=True, exist_ok=True)

	frappe.init(site=SITE, sites_path="/workspace/frappe-bench/sites")
	frappe.connect()
	try:
		docs = semear()
		rodar_no_navegador(docs)
	finally:
		limpar_jovens()
		frappe.destroy()

	if falhas:
		print("\nFALHOU:\n- " + "\n- ".join(falhas))
		return 1

	print("\nTUDO OK")
	return 0


if __name__ == "__main__":
	sys.exit(main())
