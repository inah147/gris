"""Validação ponta a ponta da Captação de Recursos e dos documentos que os editais pedem.

Roda contra o site vivo, com navegador de verdade — não entra na suíte do `bench run-tests`,
que não sobe servidor nem browser. Uso:

    cd /workspace/frappe-bench && env/bin/python apps/gris/gris/tests/e2e/test_captacao_fluxo.py

Percorre o fluxo com três pessoas fictícias, cada uma na própria sessão:
  - proponente envia a ideia; Diretoria pede alteração; proponente reenvia;
  - Diretoria aprova a ideia; proponente detalha e envia para revisão;
  - RI pede alteração numa seção; proponente marca como atendido e reenvia;
  - RI altera manualmente com motivo e aprova; Diretoria dá a aprovação final;
  - RI arrasta o card para "Captação em andamento";
  - comentário: criar, editar e apagar; outro usuário não vê os botões;
  - Administração: seletor de Diretoria no catálogo e envio de documento, que a
    consulta da Captação mostra em dia.

Detalhes do devcontainer (ver `test_administracao_organograma.py`): browser por
`executable_path`, `dev.gris` mapeado no resolver e sessão pelo cookie da API.
"""

import json
import pathlib
import sys
import urllib.request

CHROME = "/workspace/.cache/ms-playwright/chromium-1234/chrome-linux64/chrome"
BASE = "http://dev.gris"
API = "http://127.0.0.1"
SITE = "dev.gris"

SHOTS = pathlib.Path(__file__).parent / "shots"
VIEWPORT = {"width": 1500, "height": 1000}
CELULAR = {"width": 390, "height": 844}

PREFIXO = "E2E Captacao"
DOMINIO = "e2e-captacao.teste.gris"
SENHA = "E2e-Captacao-2026!"
DIRETOR = f"diretor@{DOMINIO}"
RI = f"ri@{DOMINIO}"
PROPONENTE = f"proponente@{DOMINIO}"
AREA_DIRETORIA = f"{PREFIXO} Diretoria"
AREA_RI = f"{PREFIXO} Relacoes Institucionais"
FUNCAO_DIRETOR = f"{PREFIXO} Diretor"
FUNCAO_RI = f"{PREFIXO} Equipe RI"
TITULO = f"{PREFIXO} Reforma da cozinha"

falhas = []


def checa(rotulo, obtido, esperado):
	if obtido != esperado:
		falhas.append(f"{rotulo}: {obtido!r} != {esperado!r}")
	print(f"  {rotulo}: {obtido!r}")


def no_banco(doctype, nome, campo):
	"""Relê o que o navegador gravou (sem rollback, a conexão vê o snapshot antigo)."""
	import frappe

	frappe.db.rollback()
	return frappe.db.get_value(doctype, nome, campo)


# ---------------------------------------------------------------------------
# Semeadura
# ---------------------------------------------------------------------------


def semear():
	import frappe
	from frappe.utils.password import update_password

	for area in (AREA_DIRETORIA, AREA_RI):
		if not frappe.db.exists("Unidade Organizacional", area):
			frappe.get_doc({"doctype": "Unidade Organizacional", "area": area, "ativa": 1}).insert(
				ignore_permissions=True
			)
	for titulo, diretoria, area in ((FUNCAO_DIRETOR, "Nomeada", AREA_DIRETORIA), (FUNCAO_RI, None, AREA_RI)):
		if not frappe.db.exists("Funcao Voluntario", titulo):
			frappe.get_doc(
				{
					"doctype": "Funcao Voluntario",
					"titulo": titulo,
					"categoria": "Dirigente",
					"diretoria": diretoria,
					"ativa": 1,
				}
			).insert(ignore_permissions=True)
		doc = frappe.get_doc("Unidade Organizacional", area)
		if not any(linha.funcao == titulo for linha in doc.funcoes):
			doc.append("funcoes", {"funcao": titulo})
			doc.save(ignore_permissions=True)

	for email, area, funcao in (
		(DIRETOR, AREA_DIRETORIA, FUNCAO_DIRETOR),
		(RI, AREA_RI, FUNCAO_RI),
		(PROPONENTE, None, None),
	):
		if not frappe.db.exists("User", email):
			frappe.get_doc(
				{
					"doctype": "User",
					"email": email,
					"first_name": f"E2E {email.split('@')[0]}",
					"send_welcome_email": 0,
				}
			).insert(ignore_permissions=True)
		update_password(email, SENHA)
		pessoa = frappe.get_doc(
			{
				"doctype": "Associado",
				"nome_completo": f"{PREFIXO} {email.split('@')[0].title()}",
				"cpf": frappe.generate_hash(length=32),
				"data_de_nascimento": "1990-01-01",
				"categoria": "Dirigente",
				"status_no_grupo": "Ativo",
				"historico_no_grupo": [{"data_de_ingresso": "2020-01-01"}],
				"funcoes_internas": (
					[{"funcao": funcao, "area": area, "principal": 1, "data_inicio": "2024-01-01"}]
					if funcao
					else []
				),
			}
		)
		pessoa.insert(ignore_permissions=True)
		frappe.db.set_value("Associado", pessoa.name, "id_escoteiros", email, update_modified=False)

	config = frappe.get_single("Configuracoes de Captacao")
	anterior = {
		"area_relacoes_institucionais": config.area_relacoes_institucionais,
		"somente_presidente_aprova": config.somente_presidente_aprova,
	}
	frappe.db.set_single_value("Configuracoes de Captacao", "area_relacoes_institucionais", AREA_RI)
	frappe.db.set_single_value("Configuracoes de Captacao", "somente_presidente_aprova", 0)
	frappe.db.commit()
	return anterior


def limpar(config_anterior=None):
	import frappe

	frappe.db.rollback()
	for name in frappe.get_all(
		"Projeto de Captacao", filters={"titulo": ["like", f"{PREFIXO}%"]}, pluck="name"
	):
		frappe.db.delete("Comment", {"reference_doctype": "Projeto de Captacao", "reference_name": name})
		frappe.db.delete("Version", {"ref_doctype": "Projeto de Captacao", "docname": name})
		frappe.delete_doc("Projeto de Captacao", name, force=True, ignore_permissions=True)
	for nome in frappe.get_all("Associado", filters={"nome_completo": ["like", f"{PREFIXO}%"]}, pluck="name"):
		frappe.delete_doc("Associado", nome, force=True, ignore_permissions=True)
	for area in (AREA_DIRETORIA, AREA_RI):
		if frappe.db.exists("Unidade Organizacional", area):
			frappe.delete_doc("Unidade Organizacional", area, force=True, ignore_permissions=True)
	for titulo in (FUNCAO_DIRETOR, FUNCAO_RI):
		if frappe.db.exists("Funcao Voluntario", titulo):
			frappe.delete_doc("Funcao Voluntario", titulo, force=True, ignore_permissions=True)
	for email in (DIRETOR, RI, PROPONENTE):
		if frappe.db.exists("User", email):
			frappe.delete_doc("User", email, force=True, ignore_permissions=True)
	for name in frappe.get_all(
		"Transparencia", filters={"arquivo": ["like", "%e2e-captacao%"]}, pluck="name"
	):
		frappe.delete_doc("Transparencia", name, force=True, ignore_permissions=True)
	for name in frappe.get_all(
		"File", filters={"file_name": ["like", "historia-e2e-captacao%"]}, pluck="name"
	):
		frappe.delete_doc("File", name, force=True, ignore_permissions=True)
	if config_anterior is not None:
		for campo, valor in config_anterior.items():
			frappe.db.set_single_value("Configuracoes de Captacao", campo, valor)
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
	raise RuntimeError(f"login de {usuario} não devolveu o cookie de sessão")


# ---------------------------------------------------------------------------
# Interface
# ---------------------------------------------------------------------------


def toasts(page):
	return " | ".join(
		page.locator(".toast").nth(i).inner_text() for i in range(page.locator(".toast").count())
	)


def esperar_toast(page, trecho):
	page.wait_for_function(
		"(t) => Array.from(document.querySelectorAll('.toast')).some((el) => el.innerText.includes(t))",
		arg=trecho,
		timeout=10000,
	)
	page.evaluate("() => document.querySelectorAll('.toast').forEach((t) => t.remove())")


def escolher(page, seletor_id, rotulo):
	page.locator(f"#{seletor_id} > button").click()
	page.wait_for_timeout(250)
	page.locator(f'#{seletor_id} [role="option"]', has_text=rotulo).first.click()
	page.wait_for_timeout(300)


def abrir_projeto(page, name):
	page.goto(f"{BASE}/captacao/projeto?name={name}")
	page.wait_for_selector("#projeto-secoes .captacao-bloco")


def status_na_tela(page):
	return page.locator("#projeto-meta span").first.inner_text().strip()


def preencher_atividade(page, indice, titulo, termino, inicio=None):
	"""Preenche a linha `indice` da tabela de atividades, em dias do projeto.

	Sem `inicio`, fica o que a linha já trouxe: a atividade nova começa onde a última
	termina.
	"""
	linha = page.locator(f'[data-tabela="atividades"] [data-indice="{indice}"]')
	linha.locator('[data-campo="atividade"]').fill(titulo)
	if inicio is not None:
		linha.locator('[data-campo="dia_inicio"]').fill(str(inicio))
	linha.locator('[data-campo="dia_termino"]').fill(str(termino))
	return linha


def arrastar_barra(page, indice, pixels):
	"""Arrasta a barra do Gantt pelo meio (mouse vira pointer event no Chromium)."""
	barra = page.locator(f'[data-gantt-atividades] .captacao-gantt__barra[data-indice="{indice}"]')
	caixa = barra.bounding_box()
	x = caixa["x"] + caixa["width"] / 2
	y = caixa["y"] + caixa["height"] / 2
	page.mouse.move(x, y)
	page.mouse.down()
	page.mouse.move(x + pixels, y, steps=8)
	page.mouse.up()
	page.wait_for_timeout(200)


def sem_rolagem_lateral(page):
	return page.evaluate("() => document.documentElement.scrollWidth <= window.innerWidth + 1")


def foto_no_celular(page, arquivo, rotulo):
	"""Print em largura de celular, conferindo que a página não rola para o lado."""
	page.set_viewport_size(CELULAR)
	page.wait_for_timeout(400)
	checa(f"{rotulo}: sem rolagem lateral no celular", sem_rolagem_lateral(page), True)
	page.screenshot(path=str(SHOTS / arquivo), full_page=True)
	page.set_viewport_size(VIEWPORT)
	page.wait_for_timeout(200)


def rodar(pw, config_anterior):
	import frappe

	browser = pw.chromium.launch(
		executable_path=CHROME,
		args=["--no-sandbox", "--host-resolver-rules=MAP dev.gris 127.0.0.1"],
	)

	def sessao(usuario, senha=SENHA):
		ctx = browser.new_context(viewport=VIEWPORT, service_workers="block")
		ctx.add_cookies([{"name": "sid", "value": pegar_sid(usuario, senha), "domain": SITE, "path": "/"}])
		pagina = ctx.new_page()
		pagina.on("pageerror", lambda erro: falhas.append(f"erro de JS ({usuario}): {erro}"))
		return pagina

	proponente = sessao(PROPONENTE)
	diretor = sessao(DIRETOR)
	ri = sessao(RI)

	print("1. Proponente envia a ideia")
	p = proponente
	p.goto(f"{BASE}/captacao/nova_ideia")
	checa(
		"proponente mostrado no formulário",
		"E2E Captacao Proponente" in p.locator(".captacao-proponente").inner_text(),
		True,
	)
	foto_no_celular(p, "captacao-01b-nova-ideia-celular.png", "nova ideia")
	p.fill("#ideia-titulo", TITULO)
	escolher(p, "ideia-tipo", "Infraestrutura e sede")
	p.fill("#ideia-resumo", "Reformar a cozinha da sede para atender às normas sanitárias.")
	p.locator('#ideia-objetivos textarea[data-campo="objetivo"]').first.fill("Cozinha dentro das normas")
	p.click("#btn-enviar-ideia")
	p.wait_for_url("**/captacao/projeto?name=*")
	name = p.url.split("name=")[1]
	checa("status após envio", no_banco("Projeto de Captacao", name, "status"), "Preliminar")
	checa("proponente gravado", no_banco("Projeto de Captacao", name, "proponente_user"), PROPONENTE)
	checa(
		"proponente na página do projeto",
		"Proponente: E2E Captacao Proponente" in p.locator("#projeto-meta").inner_text().replace("\n", " "),
		True,
	)
	checa("bloco do proponente na aba Projeto", p.locator("#secao-proponente").count(), 1)
	p.screenshot(path=str(SHOTS / "captacao-01-ideia-enviada.png"), full_page=True)

	print("2. Diretoria pede alteração; proponente reenvia")
	d = diretor
	abrir_projeto(d, name)
	d.click('[data-abrir="dialog-decisao-preliminar"]')
	d.wait_for_selector("#comentario-preliminar", state="visible")
	d.check('input[name="decisao_preliminar"][value="Solicitar alteração"]')
	d.fill("#comentario-preliminar", "Conte quantas pessoas usam a cozinha.")
	d.click('[data-confirmar="decidir_preliminar"]')
	esperar_toast(d, "Decisão registrada")
	checa("status após pedido", no_banco("Projeto de Captacao", name, "status"), "Preliminar")

	p.goto(f"{BASE}/captacao/nova_ideia?name={name}")
	checa("pedido visível ao proponente", p.locator(".captacao-lista-pedidos li").count(), 1)
	p.fill("#ideia-resumo", "Reformar a cozinha da sede, usada por 120 jovens e famílias.")
	p.click("#btn-enviar-ideia")
	p.wait_for_url("**/captacao/projeto?name=*")

	print("3. Diretoria envia para detalhamento")
	abrir_projeto(d, name)
	d.click('[data-abrir="dialog-decisao-preliminar"]')
	d.wait_for_selector("#comentario-preliminar", state="visible")
	d.check('input[name="decisao_preliminar"][value="Enviar para detalhamento"]')
	d.click('[data-confirmar="decidir_preliminar"]')
	esperar_toast(d, "Decisão registrada")
	checa(
		"status após aprovar ideia", no_banco("Projeto de Captacao", name, "status"), "Aprovado inicialmente"
	)

	print("4. Proponente detalha e envia para revisão")
	p.goto(f"{BASE}/captacao/detalhamento?name={name}")
	p.wait_for_selector('[data-tabela="equipe"]')
	checa(
		"proponente no detalhamento",
		"E2E Captacao Proponente" in p.locator("#secao-proponente").inner_text(),
		True,
	)
	checa(
		"proponente já é a 1ª pessoa da equipe",
		p.locator('[data-tabela="equipe"] [data-campo="nome"]').first.input_value(),
		"E2E Captacao Proponente",
	)
	p.locator('[data-tabela="equipe"] [data-campo="nome"]').first.fill("E2E Fulana")
	p.locator('[data-tabela="equipe"] [data-campo="papel"]').first.fill("Coordenação")
	p.locator('[data-tabela="equipe"] [data-campo="apresentacao"]').first.fill(
		"Engenheira civil, voluntária há 5 anos."
	)
	for campo, texto in (
		("descricao", "Troca de piso, azulejos e bancadas."),
		("publico_alvo", "120 jovens e suas famílias."),
		("justificativa", "A cozinha não atende às normas."),
		("metodologia", "Mutirões com as famílias."),
		("impacto_social", "Espaço aberto à comunidade do bairro."),
	):
		p.fill(f'[data-texto="{campo}"]', texto)
	p.locator('[data-tabela="recursos"] input[value="Material"]').first.check()
	p.locator('[data-tabela="recursos"] [data-campo="descricao"]').first.fill("Azulejos (m²)")
	p.locator('[data-tabela="recursos"] [data-campo="quantidade"]').first.fill("40")
	p.locator('[data-tabela="recursos"] [data-campo="valor_unitario"]').first.fill("25,50")
	p.wait_for_timeout(200)
	checa("total ao vivo", p.locator("[data-total]").inner_text().replace("\xa0", " "), "R$ 1.020,00")
	preencher_atividade(p, 0, "Orçamentos", 10, inicio=0)
	p.click('[data-adicionar="atividades"]')
	segunda = preencher_atividade(p, 1, "Compra dos azulejos", 24)
	checa(
		"atividade nova começa onde a anterior termina",
		segunda.locator('[data-campo="dia_inicio"]').input_value(),
		"10",
	)
	p.click('[data-adicionar="atividades"]')
	preencher_atividade(p, 2, "Obra", 54)
	p.wait_for_timeout(300)
	checa(
		"barras no Gantt do detalhamento",
		p.locator("[data-gantt-atividades] .captacao-gantt__barra").count(),
		3,
	)
	checa(
		"régua em dias do projeto",
		"dia 0" in p.locator("[data-gantt-atividades] .captacao-gantt__regua").inner_text(),
		True,
	)

	# Arrastar a barra de "Orçamentos" para a direita adia o início e mantém a duração.
	arrastar_barra(p, 0, 80)
	linha = p.locator('[data-tabela="atividades"] [data-indice="0"]')
	inicio_novo = int(linha.locator('[data-campo="dia_inicio"]').input_value())
	termino_novo = int(linha.locator('[data-campo="dia_termino"]').input_value())
	checa("arrastar a barra adia o início", inicio_novo > 0, True)
	checa("e mantém a duração de 10 dias", termino_novo - inicio_novo, 10)

	p.click("#btn-salvar-rascunho")
	esperar_toast(p, "Detalhamento salvo")
	checa(
		"status após salvar o detalhamento",
		no_banco("Projeto de Captacao", name, "status"),
		"Em detalhamento",
	)
	p.locator("[data-gantt-atividades]").scroll_into_view_if_needed()
	p.screenshot(path=str(SHOTS / "captacao-02-detalhamento.png"), full_page=True)
	foto_no_celular(p, "captacao-02b-detalhamento-celular.png", "detalhamento")
	p.click("#btn-enviar-revisao")
	p.wait_for_selector("#btn-confirmar-envio", state="visible")
	p.click("#btn-confirmar-envio")
	p.wait_for_url("**/captacao/projeto?name=*")
	checa("status após enviar", no_banco("Projeto de Captacao", name, "status"), "Revisão técnica")
	checa("valor total gravado", no_banco("Projeto de Captacao", name, "valor_total"), 1020.0)

	print("5. RI pede alteração na metodologia; proponente atende e reenvia")
	r = ri
	abrir_projeto(r, name)
	r.click('[data-abrir="dialog-pedidos"]')
	r.wait_for_selector("#pedido-metodologia", state="visible")
	r.fill("#pedido-metodologia", "Detalhe quantos mutirões e em que datas.")
	r.click('[data-confirmar="solicitar_alteracoes"]')
	esperar_toast(r, "Pedidos enviados")
	checa("status após pedido da RI", no_banco("Projeto de Captacao", name, "status"), "Em detalhamento")

	abrir_projeto(p, name)
	checa("pendência na seção", p.locator("#secao-metodologia .captacao-pendencia").count(), 1)
	p.screenshot(path=str(SHOTS / "captacao-03-pendencia-na-secao.png"), full_page=True)
	p.click("#secao-metodologia [data-resolver]")
	esperar_toast(p, "atendido")
	p.click('[data-acao="enviar_para_revisao"]')
	p.wait_for_selector("#btn-confirmar-generico", state="visible")
	p.click("#btn-confirmar-generico")
	esperar_toast(p, "revisão técnica")
	checa("status após reenviar", no_banco("Projeto de Captacao", name, "status"), "Revisão técnica")

	print("6. RI altera manualmente e aprova")
	r.goto(f"{BASE}/captacao/detalhamento?name={name}")
	r.wait_for_selector('[data-texto="metodologia"]')
	r.fill('[data-texto="metodologia"]', "Quatro mutirões aos sábados de outubro.")
	r.click("#btn-salvar-alteracao")
	esperar_toast(r, "motivo")
	r.fill("#motivo-alteracao", "Datas combinadas com o proponente por telefone.")
	r.click("#btn-salvar-alteracao")
	r.wait_for_url("**/captacao/projeto?name=*")
	r.wait_for_selector("#projeto-secoes .captacao-bloco")
	r.click("#aba-historico")
	r.wait_for_timeout(300)
	checa(
		"alteração manual na linha do tempo",
		"Alteração manual" in r.locator("#projeto-decisoes").inner_text(),
		True,
	)
	r.screenshot(path=str(SHOTS / "captacao-04-historico.png"), full_page=True)
	r.click('[data-abrir="dialog-aprovar-revisao"]')
	r.wait_for_selector("#comentario-revisao", state="visible")
	r.click('[data-confirmar="aprovar_revisao"]')
	esperar_toast(r, "Revisão aprovada")
	checa("status após revisão", no_banco("Projeto de Captacao", name, "status"), "Aprovação final")

	print("7. Diretoria dá a aprovação final")
	abrir_projeto(d, name)
	d.click('[data-abrir="dialog-aprovacao-final"]')
	d.wait_for_selector("#comentario-final", state="visible")
	d.click('[data-confirmar="decidir_aprovacao_final"]')
	esperar_toast(d, "Decisão registrada")
	checa(
		"status após aprovação final", no_banco("Projeto de Captacao", name, "status"), "Pronto para captação"
	)

	print("8. RI arrasta para captação em andamento")
	r.goto(f"{BASE}/captacao/acompanhamento")
	card = r.locator(f'.captacao-card[data-item="{name}"]')
	card.wait_for()
	r.drag_and_drop(
		f'.captacao-card[data-item="{name}"]',
		'.task-column__body[data-status="Captação em andamento"]',
	)
	esperar_toast(r, "Movido")
	checa("status após arraste", no_banco("Projeto de Captacao", name, "status"), "Captação em andamento")
	r.screenshot(path=str(SHOTS / "captacao-05-kanban.png"))

	print("8b. Cronograma do projeto em Gantt, só leitura")
	abrir_projeto(r, name)
	r.wait_for_selector("#secao-atividades .captacao-gantt__barra")
	checa("barras no Gantt do projeto", r.locator("#secao-atividades .captacao-gantt__barra").count(), 3)
	checa(
		"Gantt do projeto sem alças de edição",
		r.locator("#secao-atividades .captacao-gantt__alca").count(),
		0,
	)
	r.locator("#secao-atividades").scroll_into_view_if_needed()
	r.locator("#secao-atividades").screenshot(path=str(SHOTS / "captacao-05b-gantt.png"))
	r.set_viewport_size(CELULAR)
	r.wait_for_timeout(500)
	checa("Gantt do projeto: sem rolagem lateral no celular", sem_rolagem_lateral(r), True)
	r.locator("#secao-atividades").screenshot(path=str(SHOTS / "captacao-05c-gantt-celular.png"))
	r.set_viewport_size(VIEWPORT)

	print("9. Comentários")
	abrir_projeto(p, name)
	p.click("#aba-comentarios")
	p.fill("#novo-comentario", "Já tenho três orçamentos.")
	p.click("#btn-comentar")
	p.wait_for_selector("[data-editar-comentario]")
	p.click("[data-editar-comentario]")
	p.fill(".task-comment-item__bubble textarea", "Já tenho quatro orçamentos.")
	p.click("[data-salvar-comentario]")
	esperar_toast(p, "Comentário editado")
	checa("comentário editado", "quatro" in p.locator("#projeto-comentarios").inner_text(), True)
	abrir_projeto(d, name)
	d.click("#aba-comentarios")
	checa("diretor não edita comentário alheio", d.locator("[data-editar-comentario]").count(), 0)
	p.click("[data-apagar-comentario]")
	p.wait_for_selector("#btn-confirmar-generico", state="visible")
	p.click("#btn-confirmar-generico")
	esperar_toast(p, "Comentário apagado")
	checa("comentários restantes", p.locator("[data-comentario]").count(), 0)

	print("10. Administração: Diretoria no catálogo e documento")
	admin_senha = frappe.conf.get("admin_password") or "admin"
	a = sessao("Administrator", admin_senha)
	a.goto(f"{BASE}/administracao/funcoes")
	a.wait_for_selector(".admin-funcoes__tabela")
	checa(
		"coluna Diretoria no catálogo",
		"Nomeada" in a.locator(".admin-funcoes__tabela").inner_text(),
		True,
	)
	a.goto(f"{BASE}/administracao/transparencia")
	a.click('[data-acao="novo"]')
	a.wait_for_selector("#btn-salvar-transparencia", state="visible")
	a.click("#transparencia-tipo button")
	a.click('#transparencia-tipo [role="option"][data-value="História do grupo"]')
	a.click("#transparencia-arquivo-upload [data-file-upload-open]")
	# PNG, e não texto: o dialog só aceita PDF, imagem e DOC.
	from PIL import Image

	arquivo = pathlib.Path("/tmp") / "historia-e2e-captacao.png"
	Image.new("RGB", (40, 40), "white").save(arquivo)
	a.set_input_files("#transparencia-arquivo-upload [data-file-upload-input]", str(arquivo))
	a.click("#transparencia-arquivo-upload [data-file-upload-submit]")
	a.wait_for_selector("#transparencia-arquivo-novo:not([hidden])")
	# Emissão pelo calendário: o campo abre vazio e "Hoje" preenche.
	a.click("#transparencia-emissao .datepicker-trigger")
	a.click("#transparencia-emissao [data-datepicker-today]")
	a.click("#btn-salvar-transparencia")
	esperar_toast(a, "Documento cadastrado")
	a.wait_for_timeout(400)  # o dialog ainda está sumindo
	checa(
		"documento aparece na lista",
		"História do grupo" in a.locator("#transparencia-lista").inner_text(),
		True,
	)
	a.screenshot(path=str(SHOTS / "captacao-06-documentos.png"), full_page=True)
	a.goto(f"{BASE}/captacao/documentos")
	a.wait_for_selector(".captacao-documentos table")
	checa(
		"consulta da Captação mostra o documento em dia",
		"Em dia"
		in a.locator('.captacao-documentos tr:has(strong:text-is("História do grupo"))').inner_text(),
		True,
	)
	a.screenshot(path=str(SHOTS / "captacao-07-documentos-consulta.png"), full_page=True)

	browser.close()


def main():
	import frappe

	frappe.init(site=SITE, sites_path="/workspace/frappe-bench/sites")
	frappe.connect()
	frappe.set_user("Administrator")
	SHOTS.mkdir(exist_ok=True)

	from playwright.sync_api import sync_playwright

	limpar()
	config_anterior = semear()
	try:
		with sync_playwright() as pw:
			rodar(pw, config_anterior)
	finally:
		limpar(config_anterior)
		frappe.destroy()

	if falhas:
		print("\nFALHAS:")
		for falha in falhas:
			print(f"  - {falha}")
		sys.exit(1)
	print("\nOK")


if __name__ == "__main__":
	main()
