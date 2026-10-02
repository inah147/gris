"""Validação ponta a ponta da busca global do Portal (spec: docs/specs/busca-global/spec.md).

Roda contra o site vivo, com navegador de verdade — não entra na suíte do `bench run-tests`,
que não sobe servidor nem browser. Uso:

    cd /workspace/frappe-bench && env/bin/python apps/gris/gris/tests/e2e/test_busca_global.py

Cada cenário cita os critérios de aceite (CA) que prova. O que é regra de servidor (termo,
ranking, autorização por papel) já está nos testes de unidade em
`gris/tests/test_busca_global.py`; aqui fica o que só o navegador mostra.

Três detalhes deste devcontainer, todos obrigatórios e nenhum óbvio pelo sintoma:

1. `HOME=/workspace`, então o Playwright procura o browser no caminho errado — o
   `executable_path` vai explícito.
2. `dev.gris` não está em `/etc/hosts`; sem `--host-resolver-rules` o `goto` dá `ERR_ABORTED`.
   O bench serve na porta 80.
3. O formulário de `/login` roda no shell do Desk e termina em "Acesso negado": a sessão vem
   do cookie da API, injetado no contexto.

E um do componente: o `<dialog>` aberto reporta altura 0 ao Playwright, então o estado
dele é lido pelo atributo `open` e a espera é feita nos filhos.
"""

import json
import pathlib
import sys
import urllib.request

CHROME = "/workspace/.cache/ms-playwright/chromium-1234/chrome-linux64/chrome"
BASE = "http://dev.gris"
API = "http://127.0.0.1"
SITE = "dev.gris"

ADMIN = ("Administrator", "admin")
RESTRITO = ("e2e.busca.restrito@example.com", "E2e-Busca-Restrito-2026!")

SHOTS = pathlib.Path(__file__).parent / "shots" / "busca_global"
DESKTOP = {"width": 1440, "height": 900}
MOBILE = {"width": 390, "height": 844}

PREFIXO = "E2E Busca"
ASSOCIADO = f"{PREFIXO} Fulana Teste"
RESPONSAVEL = f"{PREFIXO} Responsavel Solo"
FESTA = f"{PREFIXO} Festa Junina"
CPF_ASSOCIADO = "39200000001"
CPF_RESPONSAVEL = "39200000002"

METODO = "gris.api.busca_global.buscar"

falhas = []


def checa(rotulo, obtido, esperado):
	if obtido != esperado:
		falhas.append(f"{rotulo}: {obtido!r} != {esperado!r}")
	print(f"  {rotulo}: {obtido!r}")


def verdade(rotulo, condicao):
	checa(rotulo, bool(condicao), True)


# ---------------------------------------------------------------------------
# Semeadura
# ---------------------------------------------------------------------------


def semear():
	import frappe

	limpar()
	frappe.get_doc(
		{
			"doctype": "Associado",
			"nome_completo": ASSOCIADO,
			"cpf": CPF_ASSOCIADO,
			"data_de_nascimento": "1990-01-01",
			"categoria": "Dirigente",
			"status_no_grupo": "Ativo",
			"historico_no_grupo": [{"data_de_ingresso": "2020-01-01"}],
		}
	).insert(ignore_permissions=True)
	frappe.get_doc(
		{
			"doctype": "Responsavel",
			"nome_completo": RESPONSAVEL,
			"cpf": CPF_RESPONSAVEL,
			"celular": "11999990000",
		}
	).insert(ignore_permissions=True)
	frappe.get_doc(
		{
			"doctype": "Festa",
			"nome_festa": FESTA,
			"data": "2026-06-20",
			"data_limite_vendas": "2026-06-19",
			"status": frappe.get_meta("Festa").get_field("status").options.split("\n")[0],
		}
	).insert(ignore_permissions=True)

	# Usuário logado sem papel nenhum: abre o Início, não abre fichas nem o Financeiro.
	usuario = frappe.get_doc(
		{
			"doctype": "User",
			"email": RESTRITO[0],
			"first_name": "E2E Busca Restrito",
			"send_welcome_email": 0,
			"user_type": "Website User",
		}
	)
	usuario.insert(ignore_permissions=True)
	from frappe.utils.password import update_password

	update_password(RESTRITO[0], RESTRITO[1])
	frappe.db.commit()


def limpar():
	import frappe

	for doctype, campo in (
		("Associado", "nome_completo"),
		("Responsavel", "nome_completo"),
		("Festa", "nome_festa"),
	):
		for nome in frappe.get_all(doctype, filters={campo: ["like", f"{PREFIXO}%"]}, pluck="name"):
			frappe.delete_doc(doctype, nome, force=True, ignore_permissions=True)
	if frappe.db.exists("User", RESTRITO[0]):
		frappe.delete_doc("User", RESTRITO[0], force=True, ignore_permissions=True)
	frappe.db.commit()


def pegar_sid(usuario, senha):
	requisicao = urllib.request.Request(
		f"{API}/api/method/login",
		data=json.dumps({"usr": usuario, "pwd": senha}).encode(),
		headers={"Content-Type": "application/json", "Host": SITE},
	)
	with urllib.request.urlopen(requisicao) as resposta:
		cookies = resposta.headers.get_all("Set-Cookie") or []
	for cookie in cookies:
		if cookie.startswith("sid="):
			return cookie.split(";")[0][4:]
	raise RuntimeError("login não devolveu o cookie de sessão")


# ---------------------------------------------------------------------------
# Auxiliares de interface
# ---------------------------------------------------------------------------


def dialog_aberto(page):
	return page.locator("#portal-busca").get_attribute("open") is not None


def abrir_pelo_gatilho(page):
	page.locator("[data-portal-busca-abrir]").click()
	page.wait_for_selector("#portal-busca-input", state="visible")


def digitar(page, texto, espera=700):
	campo = page.locator("#portal-busca-input")
	campo.fill("")
	campo.press_sequentially(texto, delay=25)
	page.wait_for_timeout(espera)


def grupos(page):
	"""{rótulo do grupo: [título dos itens]} como está na tela."""
	return page.evaluate(
		"""() => Object.fromEntries(
			[...document.querySelectorAll('#portal-busca-resultados [role=group]')].map((g) => [
				g.querySelector('[role=heading]').textContent,
				[...g.querySelectorAll('.portal-busca__item-titulo')].map((t) => t.textContent),
			])
		)"""
	)


def item_ativo(page):
	return page.evaluate(
		"() => document.querySelector('#portal-busca-resultados [role=menuitem].active .portal-busca__item-titulo')?.textContent"
	)


def novo_contexto(browser, sid, viewport=DESKTOP):
	contexto = browser.new_context(viewport=viewport, service_workers="block")
	if sid:
		contexto.add_cookies([{"name": "sid", "value": sid, "domain": SITE, "path": "/"}])
	page = contexto.new_page()
	page.on("pageerror", lambda erro: falhas.append(f"erro de JS na página: {erro}"))
	return contexto, page


def requisicoes_de_busca(page):
	lista = []
	page.on("request", lambda req: METODO in req.url and lista.append(req.url))
	return lista


# ---------------------------------------------------------------------------
# Cenários
# ---------------------------------------------------------------------------


def cenario_gatilho_centralizado(page):
	print("\n[1] Gatilho centralizado na topbar (CA-01.1)")
	page.goto(f"{BASE}/financeiro/contribuicoes", wait_until="networkidle")
	gatilho = page.locator("[data-portal-busca-abrir]")
	verdade("gatilho visível", gatilho.is_visible())
	checa("texto do gatilho", page.locator(".portal-busca-gatilho__texto").inner_text(), "Buscar no portal…")
	checa("atalho visível", page.locator("[data-portal-busca-atalho]").inner_text(), "Ctrl K")
	caixa = gatilho.bounding_box()
	barra = page.locator(".portal-topbar__inner").bounding_box()
	desvio = abs((caixa["x"] + caixa["width"] / 2) - (barra["x"] + barra["width"] / 2))
	verdade(f"centro do gatilho a {desvio:.1f}px do centro da topbar", desvio <= 2)
	page.screenshot(
		path=str(SHOTS / "01-topbar.png"), clip={"x": 0, "y": 0, "width": DESKTOP["width"], "height": 80}
	)


def cenario_abrir_e_estado_inicial(page):
	print("\n[2] Abrir pelo clique e estado inicial (CA-02.1, CA-03.1, CA-05.4)")
	abrir_pelo_gatilho(page)
	verdade("dialog aberto", dialog_aberto(page))
	checa("foco no campo", page.evaluate("() => document.activeElement.id"), "portal-busca-input")
	tela = grupos(page)
	checa("grupos iniciais", list(tela), ["Páginas", "Ações"])
	verdade("módulos em Páginas", {"Início", "Financeiro", "Associados"} <= set(tela["Páginas"]))
	verdade("nenhum filho no estado inicial", "Contribuições Mensais" not in tela["Páginas"])
	checa("primeiro item já destacado", item_ativo(page), "Início")
	verdade("rodapé com a legenda", "Navegar" in page.locator(".portal-busca__rodape").inner_text())
	page.wait_for_timeout(250)
	page.locator("#portal-busca > div").screenshot(path=str(SHOTS / "02-estado-inicial.png"))


def cenario_filtro_local(page):
	print("\n[3] Páginas filtram no navegador, com acento e plural (CA-04.1)")
	# Servidor "parado": se a página aparecer, foi o filtro local.
	page.route(f"**/{METODO}*", lambda rota: None)
	digitar(page, "contribuicao", espera=150)
	paginas = grupos(page).get("Páginas", [])
	verdade(f"'contribuicao' acha 'Contribuições Mensais' ({paginas})", "Contribuições Mensais" in paginas)
	verdade("spinner da busca remota ligado", page.locator("[data-portal-busca-carregando]").is_visible())
	digitar(page, "mensal", espera=150)
	verdade(
		"'mensal' acha 'Contribuições Mensais'", "Contribuições Mensais" in grupos(page).get("Páginas", [])
	)
	digitar(page, "configuracoes", espera=150)
	verdade("sinônimo 'configurações' acha Administração", "Administração" in grupos(page).get("Páginas", []))
	page.unroute(f"**/{METODO}*")


def cenario_registros(page, requisicoes):
	print("\n[4] Registros do servidor, agrupados e com debounce (CA-04.2, CA-04.4, CA-04.5)")
	requisicoes.clear()
	digitar(page, "e", espera=500)
	checa("1 caractere não vai ao servidor", len(requisicoes), 0)
	digitar(page, "e2e busca", espera=1200)
	verdade(f"debounce: {len(requisicoes)} requisição(ões) para 9 teclas", 1 <= len(requisicoes) <= 2)
	tela = grupos(page)
	checa("associado semeado", tela.get("Associados"), [ASSOCIADO])
	checa("responsável semeado", tela.get("Responsáveis"), [RESPONSAVEL])
	checa("festa semeada", tela.get("Festas"), [FESTA])
	ordem = list(tela)
	verdade(f"ordem dos grupos {ordem}", ordem.index("Associados") < ordem.index("Festas"))
	metas = page.evaluate(
		"() => [...document.querySelectorAll('[data-tipo=registro] .portal-busca__item-meta')].map((m) => m.textContent)"
	)
	verdade("linha de contexto do responsável", "Responsável legal" in metas)
	verdade("linha de contexto da festa traz a data", any(m.startswith("20/06/2026") for m in metas))
	verdade(
		f"nenhuma linha de contexto com CPF ou celular ({metas})",
		not any(CPF_ASSOCIADO in m or CPF_RESPONSAVEL in m or "11999990000" in m for m in metas),
	)
	page.locator("#portal-busca > div").screenshot(path=str(SHOTS / "03-registros.png"))


def cenario_resposta_fora_de_ordem(page):
	print("\n[5] Resposta atrasada de termo antigo é descartada (CA-04.2)")

	def corpo(rotulo):
		return json.dumps(
			{
				"message": {
					"ok": True,
					"data": {
						"termo": rotulo,
						"grupos": [
							{
								"chave": rotulo.lower(),
								"rotulo": rotulo,
								"icone": "users",
								"itens": [{"titulo": rotulo, "subtitulo": "", "url": "/inicio"}],
							}
						],
					},
				}
			}
		)

	# A resposta de "zz1" fica retida e só é entregue depois que "zz12" já respondeu.
	retidas = []

	def responder(rota):
		if rota.request.url.endswith("termo=zz1"):
			retidas.append(rota)
		else:
			rota.fulfill(status=200, content_type="application/json", body=corpo("Novo"))

	page.route(f"**/{METODO}*", responder)
	digitar(page, "zz1", espera=400)
	checa("requisição de 'zz1' em curso", len(retidas), 1)
	page.locator("#portal-busca-input").press_sequentially("2")
	page.wait_for_timeout(700)
	for rota in retidas:
		try:
			rota.fulfill(status=200, content_type="application/json", body=corpo("Velho"))
		except Exception:
			pass  # o cliente já cancelou a requisição (AbortController)
	page.wait_for_timeout(500)
	tela = grupos(page)
	verdade("resultado do termo atual na tela", "Novo" in tela)
	verdade("resposta do termo antigo descartada", "Velho" not in tela)
	page.unroute(f"**/{METODO}*")


def cenario_vazio_e_erro(page):
	print("\n[6] Sem resultado: mascote; falha: aviso e páginas seguem (CA-04.6, CA-04.7)")
	digitar(page, "xqzwvkj", espera=1000)
	verdade("estado vazio visível", page.locator("[data-portal-busca-vazio]").is_visible())
	checa(
		"mascote gris-search",
		page.locator("[data-portal-busca-vazio] img").get_attribute("src"),
		"/assets/gris/images/gris-character/gris-search.png",
	)
	page.locator("#portal-busca > div").screenshot(path=str(SHOTS / "04-vazio.png"))

	page.route(f"**/{METODO}*", lambda rota: rota.fulfill(status=500, body="erro"))
	digitar(page, "financeiro", espera=1000)
	verdade("aviso de erro visível", page.locator("[data-portal-busca-erro]").is_visible())
	verdade("páginas continuam filtrando", "Financeiro" in grupos(page).get("Páginas", []))
	page.unroute(f"**/{METODO}*")
	digitar(page, "financeiro", espera=1000)
	verdade("aviso some quando o servidor volta", not page.locator("[data-portal-busca-erro]").is_visible())


def cenario_xss(page):
	print("\n[7] Texto do servidor entra como texto (CA-S6)")
	malicioso = '<img src=x onerror="window.__xss_busca=1">'
	corpo = {
		"message": {
			"ok": True,
			"data": {
				"termo": "xss",
				"grupos": [
					{
						"chave": "associados",
						"rotulo": "Associados",
						"icone": "users",
						"itens": [
							{"titulo": malicioso, "subtitulo": malicioso, "url": "/inicio"},
							{"titulo": "Link perigoso", "subtitulo": "", "url": "javascript:alert(1)"},
						],
					}
				],
			},
		}
	}
	page.route(
		f"**/{METODO}*",
		lambda rota: rota.fulfill(status=200, content_type="application/json", body=json.dumps(corpo)),
	)
	digitar(page, "xss", espera=900)
	checa("script não executou", page.evaluate("() => window.__xss_busca"), None)
	checa("tag aparece como texto", grupos(page).get("Associados"), [malicioso])
	checa("nenhuma <img> injetada", page.locator("#portal-busca-resultados img").count(), 0)
	page.unroute(f"**/{METODO}*")


def cenario_teclado_e_mouse(page):
	print("\n[8] Setas, mouse e Enter (CA-05.1, CA-05.2, CA-05.3)")
	digitar(page, "projetos", espera=900)
	primeiro = item_ativo(page)
	page.keyboard.press("ArrowDown")
	segundo = item_ativo(page)
	verdade(f"seta desce ({primeiro!r} → {segundo!r})", primeiro != segundo and segundo)
	page.keyboard.press("ArrowUp")
	checa("seta sobe", item_ativo(page), primeiro)
	page.keyboard.press("End")
	ultimo = page.locator("#portal-busca-resultados [role=menuitem]").last
	verdade("End vai ao último", "active" in (ultimo.get_attribute("class") or ""))
	page.keyboard.press("Home")
	checa("Home volta ao primeiro", item_ativo(page), primeiro)

	terceiro = page.locator("#portal-busca-resultados [role=menuitem]").nth(2)
	terceiro.hover()
	checa("mouse destaca", item_ativo(page), terceiro.locator(".portal-busca__item-titulo").inner_text())

	digitar(page, "contribuicoes mensais", espera=900)
	checa("primeiro resultado", item_ativo(page), "Contribuições Mensais")
	with page.context.expect_page() as nova_aba:
		page.keyboard.press("Control+Enter")
	aba = nova_aba.value
	aba.wait_for_load_state()
	checa("Ctrl+Enter abre em nova aba", aba.url.split("?")[0], f"{BASE}/financeiro/contribuicoes")
	aba.close()
	verdade("dialog continua aberto após nova aba", dialog_aberto(page))

	page.goto(f"{BASE}/inicio", wait_until="networkidle")
	abrir_pelo_gatilho(page)
	digitar(page, "contribuicoes mensais", espera=900)
	with page.expect_navigation():
		page.keyboard.press("Enter")
	checa("Enter navega", page.url.split("?")[0], f"{BASE}/financeiro/contribuicoes")


def cenario_atalhos_e_fechar(page):
	print("\n[9] Atalhos e formas de fechar (CA-02.2, CA-02.3)")
	page.goto(f"{BASE}/inicio", wait_until="networkidle")
	page.keyboard.press("Control+k")
	page.wait_for_selector("#portal-busca-input", state="visible")
	verdade("Ctrl+K abre", dialog_aberto(page))
	page.keyboard.type("algo")
	page.keyboard.press("Control+k")
	page.wait_for_timeout(200)
	verdade("Ctrl+K fecha", not dialog_aberto(page))

	page.evaluate("() => document.activeElement && document.activeElement.blur()")
	page.keyboard.press("/")
	page.wait_for_selector("#portal-busca-input", state="visible")
	verdade("'/' abre", dialog_aberto(page))
	checa("reabre com o campo vazio", page.locator("#portal-busca-input").input_value(), "")
	page.keyboard.press("Escape")
	page.wait_for_timeout(200)
	verdade("Esc fecha", not dialog_aberto(page))
	checa("foco volta ao que estava antes", page.evaluate("() => document.activeElement.tagName"), "BODY")

	page.evaluate(
		"""() => { const i = document.createElement('input'); i.id = 'campo-e2e'; document.querySelector('.page-container').prepend(i); }"""
	)
	page.locator("#campo-e2e").click()
	page.keyboard.press("/")
	page.wait_for_timeout(200)
	verdade("'/' num campo digita a barra e não abre", not dialog_aberto(page))
	checa("a barra foi para o campo", page.locator("#campo-e2e").input_value(), "/")

	abrir_pelo_gatilho(page)
	page.mouse.click(10, DESKTOP["height"] - 10)
	page.wait_for_timeout(200)
	verdade("clique fora fecha", not dialog_aberto(page))
	checa(
		"foco volta ao gatilho",
		page.evaluate("() => document.activeElement.hasAttribute('data-portal-busca-abrir')"),
		True,
	)

	abrir_pelo_gatilho(page)
	page.locator("[data-portal-busca-fechar]").click()
	page.wait_for_timeout(200)
	verdade("botão fechar fecha", not dialog_aberto(page))


def cenario_acao_tema(page):
	print("\n[10] Ação de tema (CA-06.1, CA-D1)")
	page.goto(f"{BASE}/inicio", wait_until="networkidle")
	escuro_antes = page.evaluate("() => document.documentElement.classList.contains('dark')")
	abrir_pelo_gatilho(page)
	digitar(page, "tema", espera=300)
	checa(
		"ação oferecida",
		grupos(page).get("Ações"),
		["Usar tema claro" if escuro_antes else "Usar tema escuro"],
	)
	page.keyboard.press("Enter")
	page.wait_for_timeout(400)
	verdade(
		"tema alternou",
		page.evaluate("() => document.documentElement.classList.contains('dark')") != escuro_antes,
	)
	verdade("dialog fechou", not dialog_aberto(page))

	abrir_pelo_gatilho(page)
	digitar(page, "e2e busca", espera=1200)
	# Só o painel: a página inteira traria o nome e o e-mail do usuário no rodapé da sidebar.
	page.wait_for_timeout(250)
	page.locator("#portal-busca > div").screenshot(path=str(SHOTS / "05-tema-escuro.png"))
	digitar(page, "tema", espera=300)
	checa(
		"rótulo invertido",
		grupos(page).get("Ações"),
		["Usar tema escuro" if escuro_antes else "Usar tema claro"],
	)
	page.keyboard.press("Enter")
	page.wait_for_timeout(400)
	checa(
		"tema voltou",
		page.evaluate("() => document.documentElement.classList.contains('dark')"),
		escuro_antes,
	)


def cenario_mobile(browser, sid):
	print("\n[11] Mobile 390px (CA-01.2, CA-D2)")
	contexto, page = novo_contexto(browser, sid, MOBILE)
	page.goto(f"{BASE}/financeiro/contribuicoes", wait_until="networkidle")
	verdade("texto do gatilho escondido", not page.locator(".portal-busca-gatilho__texto").is_visible())
	verdade("gatilho (lupa) visível", page.locator("[data-portal-busca-abrir]").is_visible())
	# Mede a topbar, que é o que a busca muda: as abas desta página já passam de 390px
	# por conta própria.
	largura = page.evaluate("() => document.querySelector('.portal-topbar').scrollWidth")
	verdade(f"topbar sem rolagem horizontal ({largura}px)", largura <= MOBILE["width"])
	direita = page.evaluate(
		"() => Math.max(...[...document.querySelectorAll('.portal-topbar__inner > *')].map((e) => e.getBoundingClientRect().right))"
	)
	verdade(f"nada da topbar passa da borda ({direita:.0f}px)", direita <= MOBILE["width"])
	page.screenshot(
		path=str(SHOTS / "06-mobile-topbar.png"),
		clip={"x": 0, "y": 0, "width": MOBILE["width"], "height": 80},
	)
	abrir_pelo_gatilho(page)
	digitar(page, "e2e busca", espera=1200)
	painel = page.locator("#portal-busca > div").bounding_box()
	verdade(
		f"painel dentro da tela (x={painel['x']:.0f}, largura={painel['width']:.0f})",
		painel["x"] >= 0 and painel["x"] + painel["width"] <= MOBILE["width"],
	)
	verdade(f"painel no topo (y={painel['y']:.0f})", painel["y"] <= 24)
	verdade("rodapé de atalhos escondido", not page.locator(".portal-busca__rodape").is_visible())
	page.wait_for_timeout(250)
	page.locator("#portal-busca > div").screenshot(path=str(SHOTS / "07-mobile-aberto.png"))
	contexto.close()


def cenario_usuario_restrito(browser):
	print("\n[12] Usuário sem papel não vê o que não abriria (CA-S1, CA-S2, CA-03.1)")
	contexto, page = novo_contexto(browser, pegar_sid(*RESTRITO))
	page.goto(f"{BASE}/inicio", wait_until="networkidle")
	abrir_pelo_gatilho(page)
	paginas = grupos(page).get("Páginas", [])
	verdade(f"só módulos acessíveis ({len(paginas)})", "Início" in paginas and "Financeiro" not in paginas)
	digitar(page, "e2e busca", espera=1200)
	tela = grupos(page)
	verdade(
		f"sem associados/responsáveis/festas ({list(tela)})",
		not {"Associados", "Responsáveis", "Festas"} & set(tela),
	)
	contexto.close()


def cenario_visitante(browser):
	print("\n[13] Visitante não tem busca (CA-01.3)")
	contexto, page = novo_contexto(browser, None)
	for rota in ("/portal_transparencia", "/403"):
		page.goto(f"{BASE}{rota}", wait_until="networkidle")
		checa(f"{rota}: sem gatilho", page.locator("[data-portal-busca-abrir]").count(), 0)
		checa(f"{rota}: sem dialog", page.locator("#portal-busca").count(), 0)
	contexto.close()


# ---------------------------------------------------------------------------


def rodar_no_navegador():
	from playwright.sync_api import sync_playwright

	with sync_playwright() as p:
		browser = p.chromium.launch(
			executable_path=CHROME,
			args=["--no-sandbox", f"--host-resolver-rules=MAP {SITE} 127.0.0.1"],
		)
		sid = pegar_sid(*ADMIN)
		contexto, page = novo_contexto(browser, sid)
		requisicoes = requisicoes_de_busca(page)

		cenario_gatilho_centralizado(page)
		cenario_abrir_e_estado_inicial(page)
		cenario_filtro_local(page)
		cenario_registros(page, requisicoes)
		cenario_resposta_fora_de_ordem(page)
		cenario_vazio_e_erro(page)
		cenario_xss(page)
		cenario_teclado_e_mouse(page)
		cenario_atalhos_e_fechar(page)
		cenario_acao_tema(page)
		contexto.close()

		cenario_mobile(browser, sid)
		cenario_usuario_restrito(browser)
		cenario_visitante(browser)
		browser.close()


def main():
	import frappe

	SHOTS.mkdir(parents=True, exist_ok=True)
	frappe.init(site=SITE, sites_path="/workspace/frappe-bench/sites")
	frappe.connect()
	try:
		semear()
		rodar_no_navegador()
	finally:
		limpar()
		frappe.destroy()

	if falhas:
		print("\nFALHOU:\n- " + "\n- ".join(falhas))
		return 1
	print("\nTUDO OK")
	return 0


if __name__ == "__main__":
	sys.exit(main())
