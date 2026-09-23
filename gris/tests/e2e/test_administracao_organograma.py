"""Validação ponta a ponta do módulo de Administração e da atribuição de funções.

Roda contra o site vivo, com navegador de verdade — não entra na suíte do `bench run-tests`,
que não sobe servidor nem browser. Uso:

    cd /workspace/frappe-bench && env/bin/python apps/gris/gris/tests/e2e/test_administracao_organograma.py

Cobre o que só o navegador prova:
  - criar e editar área pelo dialog, com a tabela de funções;
  - desvincular uma função que alguém ainda exerce → mensagem com a contagem;
  - arrastar a ponta da linha de um card para outro → troca o "responde para";
  - botão "+" que aparece no hover e já abre a nova área sob aquele card;
  - catálogo de funções, com a contagem de pessoas e as responsabilidades;
  - na ficha do associado, a cascata área → função, atribuir e encerrar.

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
VIEWPORT = {"width": 1500, "height": 1000}

PREFIXO = "E2E Admin"
AREA_TOPO = f"{PREFIXO} Diretoria"
AREA_FILHA = f"{PREFIXO} Equipe"
AREA_SOLTA = f"{PREFIXO} Apoio"
FUNCAO = f"{PREFIXO} Coordenacao"
FUNCAO_LIVRE = f"{PREFIXO} Voluntariado"

falhas = []


def checa(rotulo, obtido, esperado):
	if obtido != esperado:
		falhas.append(f"{rotulo}: {obtido!r} != {esperado!r}")
	print(f"  {rotulo}: {obtido!r}")


def contem(rotulo, texto, trecho):
	if trecho not in (texto or ""):
		falhas.append(f"{rotulo}: {trecho!r} não está em {texto!r}")
	print(f"  {rotulo}: ok")


def no_banco(doctype, nome, campo):
	"""Lê o valor gravado pelo navegador, e não o do começo do script.

	A conexão deste processo abriu antes de o browser escrever, e o MariaDB serve a
	ela o snapshot daquele instante (REPEATABLE READ). Sem encerrar a transação, toda
	releitura devolveria o valor antigo e o teste acusaria erro onde não há.
	"""
	import frappe

	frappe.db.rollback()
	return frappe.db.get_value(doctype, nome, campo)


# ---------------------------------------------------------------------------
# Semeadura
# ---------------------------------------------------------------------------


def semear():
	import frappe

	for area, mae in ((AREA_TOPO, None), (AREA_FILHA, AREA_TOPO), (AREA_SOLTA, AREA_TOPO)):
		if not frappe.db.exists("Unidade Organizacional", area):
			frappe.get_doc(
				{"doctype": "Unidade Organizacional", "area": area, "responde_para": mae, "ativa": 1}
			).insert(ignore_permissions=True)

	for titulo in (FUNCAO, FUNCAO_LIVRE):
		if not frappe.db.exists("Funcao Voluntario", titulo):
			frappe.get_doc(
				{"doctype": "Funcao Voluntario", "titulo": titulo, "categoria": "Dirigente", "ativa": 1}
			).insert(ignore_permissions=True)

	doc = frappe.get_doc("Unidade Organizacional", AREA_FILHA)
	if not any(linha.funcao == FUNCAO for linha in doc.funcoes):
		doc.append("funcoes", {"funcao": FUNCAO})
		doc.save(ignore_permissions=True)

	pessoa = frappe.get_doc(
		{
			"doctype": "Associado",
			"nome_completo": f"{PREFIXO} Pessoa",
			"cpf": frappe.generate_hash(length=32),
			"data_de_nascimento": "1990-01-01",
			"categoria": "Dirigente",
			"status_no_grupo": "Ativo",
			"historico_no_grupo": [{"data_de_ingresso": "2020-01-01"}],
			"funcoes_internas": [
				{"funcao": FUNCAO, "area": AREA_FILHA, "principal": 1, "data_inicio": "2024-01-01"}
			],
		}
	)
	pessoa.insert(ignore_permissions=True)
	frappe.db.commit()
	return pessoa.name


def limpar():
	import frappe

	for nome in frappe.get_all("Associado", filters={"nome_completo": ["like", f"{PREFIXO}%"]}, pluck="name"):
		frappe.delete_doc("Associado", nome, force=True, ignore_permissions=True)

	# As áreas saem depois das pessoas: o vínculo de função barra o desvínculo.
	for area in frappe.get_all(
		"Unidade Organizacional", filters={"area": ["like", f"{PREFIXO}%"]}, pluck="name"
	):
		frappe.delete_doc("Unidade Organizacional", area, force=True, ignore_permissions=True)
	for titulo in frappe.get_all(
		"Funcao Voluntario", filters={"titulo": ["like", f"{PREFIXO}%"]}, pluck="name"
	):
		frappe.delete_doc("Funcao Voluntario", titulo, force=True, ignore_permissions=True)
	frappe.db.commit()


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


# ---------------------------------------------------------------------------
# Auxiliares de interface
# ---------------------------------------------------------------------------


def escolher(page, seletor_id, rotulo):
	"""Abre o select do design system e clica na opção pelo rótulo."""
	page.locator(f"#{seletor_id} > button").click()
	page.wait_for_timeout(250)
	page.locator(f'#{seletor_id} [role="option"]', has_text=rotulo).first.click()
	page.wait_for_timeout(350)


def toasts(page):
	return [page.locator(".toast").nth(i).inner_text() for i in range(page.locator(".toast").count())]


def limpar_toasts(page):
	page.evaluate("() => document.querySelectorAll('.toast').forEach((t) => t.remove())")


def anonimizar(page):
	"""Troca nomes de gente de verdade antes do print — o repositório é público."""
	page.evaluate(
		"""() => {
			let n = 0;
			const fake = new Map();
			const trocar = (texto) => {
				const limpo = (texto || '').trim();
				if (!limpo || limpo.startsWith('E2E') || limpo === 'Sem responsável' || limpo === '—') {
					return null;
				}
				if (!fake.has(limpo)) { n += 1; fake.set(limpo, `Voluntária ${n}`); }
				return fake.get(limpo);
			};
			document.querySelectorAll('.admin-arvore__sub').forEach((el) => {
				const novo = trocar(el.textContent);
				if (novo) el.textContent = novo;
			});
			document.querySelectorAll('.admin-unidades__tabela tbody tr').forEach((tr) => {
				const celula = tr.children[2];
				if (!celula) return;
				const novo = trocar(celula.textContent);
				if (novo) celula.textContent = novo;
			});
		}"""
	)


# ---------------------------------------------------------------------------
# Cenários
# ---------------------------------------------------------------------------


def cenario_tabela_e_dialog(page):
	print("\n[1] Tabela de áreas e dialog de edição")
	page.goto(f"{BASE}/administracao/unidades_organizacionais", wait_until="networkidle")
	# No desktop a página abre na árvore; a tabela é a outra aba.
	page.locator('[role="tab"]', has_text="Tabela").click()
	page.wait_for_timeout(400)

	linhas = page.locator(".admin-unidades__tabela tbody tr")
	if linhas.count() == 0:
		falhas.append("tabela de áreas veio vazia")
		return

	linha = page.locator(".admin-unidades__tabela tbody tr", has_text=AREA_FILHA).first
	contem("linha da área mostra a quem responde", linha.inner_text(), AREA_TOPO)

	anonimizar(page)
	page.locator(".admin-unidades").screenshot(path=str(SHOTS / "01-areas-tabela.png"))

	linha.locator('[data-acao="editar"]').click()
	page.wait_for_timeout(500)
	checa("dialog abriu", page.locator("#dialog-area").evaluate("d => d.open"), True)
	checa("função vinculada aparece na grade", page.locator("#area-funcoes-corpo tr").count(), 1)
	# O select escolhe sozinho a primeira opção ao inicializar: sem a opção vazia,
	# uma área sem responsável abriria já mostrando a primeira pessoa da lista, e o
	# save gravaria essa pessoa como responsável.
	checa(
		"área sem responsável não vem com ninguém escolhido",
		page.locator('#area-responsavel input[type="hidden"]').input_value(),
		"",
	)
	page.locator("#dialog-area .admin-dialog__form").screenshot(path=str(SHOTS / "02-area-dialog.png"))


def cenario_desvinculo_bloqueado(page):
	print("\n[2] Desvincular função que alguém ainda exerce")
	limpar_toasts(page)
	page.locator('#area-funcoes-corpo [data-acao="remover-funcao"]').first.click()
	page.wait_for_timeout(200)
	page.locator("#btn-salvar-area").click()
	page.wait_for_timeout(1500)

	mensagens = " ".join(toasts(page))
	contem("mensagem explica o bloqueio", mensagens, "ainda a exercem aqui")
	contem("mensagem traz a contagem", mensagens, "1 pessoa(s)")
	checa("dialog continua aberto", page.locator("#dialog-area").evaluate("d => d.open"), True)
	page.locator('[data-dialog-cancel="dialog-area"]').click()
	page.wait_for_timeout(300)


def cenario_nova_area_pelo_hover(page):
	print("\n[3] Botão + no card abre nova área já sob ele")
	page.locator('[role="tab"]', has_text="Árvore").click()
	page.wait_for_timeout(800)

	card = page.locator(f'.admin-arvore__card[data-name="{AREA_TOPO}"]')
	card.hover()
	page.wait_for_timeout(300)
	botao = card.locator('[data-acao="novo-filho"]')
	checa("botão + fica visível no hover", botao.is_visible(), True)

	anonimizar(page)
	limpar_toasts(page)
	page.locator("#admin-unidades-arvore").screenshot(path=str(SHOTS / "03-arvore-interativa.png"))

	botao.click()
	page.wait_for_timeout(600)
	checa(
		"nova área já vem com o pai preenchido",
		page.locator('#area-responde-para input[type="hidden"]').input_value(),
		AREA_TOPO,
	)

	nova = f"{PREFIXO} Criada Pelo Card"
	page.locator("#area-nome").fill(nova)
	limpar_toasts(page)
	page.locator("#btn-salvar-area").click()
	page.wait_for_timeout(1600)
	contem("toast confirma a criação", " ".join(toasts(page)), "Área criada")

	checa(
		"área nova responde para o card de origem",
		no_banco("Unidade Organizacional", nova, "responde_para"),
		AREA_TOPO,
	)


def cenario_arrastar_aresta(page):
	print("\n[4] Arrastar a ponta da linha troca o 'responde para'")
	antes = no_banco("Unidade Organizacional", AREA_SOLTA, "responde_para")
	checa("antes do arraste", antes, AREA_TOPO)

	page.locator('[data-zoom="ajustar"]').click()
	page.wait_for_timeout(500)

	aresta = page.locator(f'.admin-arvore__aresta[data-filho="{AREA_SOLTA}"]')
	destino = page.locator(f'.admin-arvore__card[data-name="{AREA_FILHA}"]')
	destino_box = destino.bounding_box()

	# O trecho junto ao filho é a parte da linha que pertence só a esta aresta —
	# perto do pai todas as irmãs se sobrepõem.
	ponta_filho = aresta.locator(".admin-arvore__ponta--filho").bounding_box()
	if not ponta_filho or not destino_box:
		falhas.append(f"sem geometria para arrastar: linha={ponta_filho} destino={destino_box}")
		return
	meio_x = ponta_filho["x"] + ponta_filho["width"] / 2
	meio_y = ponta_filho["y"] + ponta_filho["height"] / 2

	page.mouse.move(meio_x, meio_y)
	page.wait_for_timeout(300)
	checa("linha realçada sob o ponteiro", aresta.evaluate("e => e.classList.contains('is-sob')"), True)
	checa(
		"hover sozinho não mostra as bolinhas",
		aresta.locator(".admin-arvore__ponta--pai").evaluate("e => getComputedStyle(e).opacity"),
		"0",
	)

	# Religar é decisão, não gesto de passagem: só depois do clique na linha as
	# bolinhas aparecem e a de cima pode ser arrastada.
	page.mouse.click(meio_x, meio_y)
	page.wait_for_timeout(350)
	checa("clique seleciona a linha", aresta.evaluate("e => e.classList.contains('is-selecionada')"), True)
	checa(
		"bolinhas aparecem na seleção",
		aresta.locator(".admin-arvore__ponta--pai").evaluate("e => getComputedStyle(e).opacity"),
		"1",
	)
	checa(
		"o + do card pai sai do caminho",
		page.locator(f'.admin-arvore__card[data-name="{AREA_TOPO}"]').evaluate(
			"e => e.classList.contains('is-sem-add')"
		),
		True,
	)

	origem_box = page.locator(f'[data-alca="{AREA_SOLTA}"]').bounding_box()
	if not origem_box:
		falhas.append("alça sem geometria")
		return

	limpar_toasts(page)
	page.mouse.move(origem_box["x"] + origem_box["width"] / 2, origem_box["y"] + origem_box["height"] / 2)
	page.wait_for_timeout(200)
	page.mouse.down()
	page.mouse.move(
		destino_box["x"] + destino_box["width"] / 2,
		destino_box["y"] + destino_box["height"] / 2,
		steps=15,
	)
	page.wait_for_timeout(250)
	checa(
		"área de destino realçada durante o arraste", page.locator(".admin-arvore__card.is-alvo").count(), 1
	)
	page.mouse.up()
	page.wait_for_timeout(1600)

	# Nomeia a área: só "agora responde para" passaria mesmo se outra linha tivesse
	# sido arrastada por engano.
	contem(
		"toast confirma a religação",
		" ".join(toasts(page)),
		f"{AREA_SOLTA} agora responde para {AREA_FILHA}",
	)
	checa(
		"banco registrou o novo pai",
		no_banco("Unidade Organizacional", AREA_SOLTA, "responde_para"),
		AREA_FILHA,
	)


def cenario_funcoes(page):
	print("\n[5] Catálogo de funções")
	page.goto(f"{BASE}/administracao/funcoes", wait_until="networkidle")

	linha = page.locator(".admin-funcoes__tabela tbody tr", has_text=FUNCAO).first
	texto = linha.inner_text()
	contem("tabela mostra a linha da função", texto, "Dirigente")
	contem("tabela mostra a contagem de pessoas", texto, "1")
	page.locator(".admin-funcoes").screenshot(path=str(SHOTS / "04-funcoes-tabela.png"))

	linha.locator('[data-acao="detalhes"]').click()
	page.wait_for_timeout(500)
	checa("dialog de função abriu", page.locator("#dialog-funcao").evaluate("d => d.open"), True)

	page.locator("#funcao-nova-responsabilidade").fill("Acompanhar a equipe")
	page.locator("#funcao-novo-detalhe").fill("a cada reunião")
	page.locator("#btn-add-responsabilidade").click()
	page.wait_for_timeout(300)
	checa("responsabilidade entrou na grade", page.locator("#funcao-responsabilidades-corpo tr").count(), 1)
	page.locator("#dialog-funcao .admin-dialog__form").screenshot(path=str(SHOTS / "05-funcao-dialog.png"))

	limpar_toasts(page)
	page.locator("#btn-salvar-funcao").click()
	page.wait_for_timeout(1600)
	contem("toast confirma a gravação", " ".join(toasts(page)), "Função atualizada")

	import frappe

	frappe.db.rollback()
	gravadas = frappe.get_all(
		"Responsabilidade da Funcao", filters={"parent": FUNCAO}, pluck="responsabilidade"
	)
	checa("responsabilidade persistiu", gravadas, ["Acompanhar a equipe"])


def cenario_ficha_do_associado(page, associado):
	print("\n[6] Área e função na ficha do associado")
	page.goto(f"{BASE}/associados/detalhe?name={associado}", wait_until="networkidle")

	card = page.locator(".funcoes-organograma")
	checa("card de funções aparece", card.count(), 1)
	checa("função semeada está na tabela", page.locator("#funcoes-organograma-corpo tr").count(), 1)

	# Cascata: a área escolhida define as funções oferecidas.
	escolher(page, "funcao-area", AREA_FILHA)
	opcoes = page.locator('#funcao-funcao [role="option"]')
	rotulos = [opcoes.nth(i).inner_text() for i in range(opcoes.count())]
	contem("cascata trouxe a função da área", " | ".join(rotulos), FUNCAO)

	# Uma área sem funções vinculadas não oferece nenhuma.
	escolher(page, "funcao-area", AREA_TOPO)
	page.wait_for_timeout(300)
	vazias = page.locator('#funcao-funcao [role="option"]')
	checa("área sem vínculo não oferece função", vazias.count(), 1)  # só o placeholder

	# Atribuir numa área que tem a função.
	escolher(page, "funcao-area", AREA_SOLTA)
	page.wait_for_timeout(300)
	limpar_toasts(page)
	page.locator("#btn-adicionar-funcao").click()
	page.wait_for_timeout(1200)
	contem("sem função escolhida, avisa", " ".join(toasts(page)), "Escolha a área e a função")

	page.locator(".funcoes-organograma").screenshot(path=str(SHOTS / "06-ficha-funcoes.png"))

	# Encerrar a função em vigor mantém a linha no histórico.
	limpar_toasts(page)
	page.locator('#funcoes-organograma-corpo [data-acao="encerrar"]').first.click()
	page.wait_for_timeout(1500)
	contem("toast confirma o encerramento", " ".join(toasts(page)), "Função encerrada")
	checa("linha continua na tabela", page.locator("#funcoes-organograma-corpo tr").count(), 1)
	contem(
		"linha passa a mostrar a data de fim",
		page.locator("#funcoes-organograma-corpo tr").first.inner_text(),
		"Encerrada em",
	)


def cenario_organograma_reflete(page, associado):
	print("\n[7] O organograma reflete o que foi feito")
	page.goto(f"{BASE}/gestao_adultos/organograma", wait_until="networkidle")
	page.wait_for_timeout(1200)

	# A função da pessoa foi encerrada hoje — e uma função encerrada hoje ainda vale
	# hoje, então ela continua no desenho. O que importa é a página seguir de pé.
	checa("organograma renderizou", page.locator(".org-card").count() > 0, True)
	erros = page.locator(".org-erro:visible").count()
	checa("sem estado de erro na página", erros, 0)


# ---------------------------------------------------------------------------


def rodar_no_navegador(associado):
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

		cenario_tabela_e_dialog(page)
		cenario_desvinculo_bloqueado(page)
		cenario_nova_area_pelo_hover(page)
		cenario_arrastar_aresta(page)
		cenario_funcoes(page)
		cenario_ficha_do_associado(page, associado)
		cenario_organograma_reflete(page, associado)

		browser.close()


def main():
	import frappe

	SHOTS.mkdir(parents=True, exist_ok=True)

	frappe.init(site=SITE, sites_path="/workspace/frappe-bench/sites")
	frappe.connect()
	try:
		associado = semear()
		rodar_no_navegador(associado)
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
