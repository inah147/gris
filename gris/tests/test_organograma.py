# Copyright (c) 2026, Grupo Escoteiro Professora Inah de Mello - 47/SP and contributors
# For license information, please see license.txt

"""Testes da montagem da árvore do organograma.

`montar_arvore` é pura de propósito: recebe as listas já lidas do banco e
devolve a árvore. Isso deixa as regras de hierarquia testáveis sem site nem HTTP.
"""

import datetime
from typing import ClassVar

from frappe.tests.utils import FrappeTestCase

from gris.api.gestao_adultos.organograma import (
	FILTRO_SEM_AREA,
	_recortar_por_area,
	montar_arvore,
	montar_detalhe,
)
from gris.api.portal_access import user_has_access


def _area(nome, mae=None, responsavel=None, ordem=0):
	return {
		"name": nome,
		"area": nome,
		"responde_para": mae,
		"responsavel": responsavel,
		"descricao": None,
		"ordem": ordem,
	}


def _pessoa(nome, area=None, categoria="Dirigente", ramo="Não se aplica"):
	return {
		"name": nome,
		"nome_completo": nome,
		"categoria": categoria,
		"ramo": ramo,
		"area": area,
		"id_escoteiros": None,
	}


def _montar(areas, pessoas, lotacoes=None, avatares=None):
	"""Deriva a lotação do `area` que `_pessoa` recebe.

	A área saiu do cadastro da pessoa e passou a vir da função; este atalho evita
	reescrever cada cenário só por causa disso.
	"""
	if lotacoes is None:
		lotacoes = [
			{"associado": p["name"], "area": p["area"], "funcao": p.get("funcao")}
			for p in pessoas
			if p.get("area")
		]
	return montar_arvore(areas, pessoas, lotacoes, avatares or {})


def _lotacoes(pessoas):
	return [{"associado": p["name"], "area": p["area"], "funcao": None} for p in pessoas if p.get("area")]


def _por_id(nos):
	achatado = {}

	def _visitar(lista):
		for no in lista:
			achatado[no.get("associado") or no["id"]] = no
			_visitar(no["children"])

	_visitar(nos)
	return achatado


class TestMontarArvore(FrappeTestCase):
	def test_lider_de_subarea_responde_ao_lider_da_area_mae(self):
		areas = [
			_area("Presidência", responsavel="Caio"),
			_area("Programa", mae="Presidência", responsavel="Mariana"),
		]
		pessoas = [_pessoa("Caio", "Presidência"), _pessoa("Mariana", "Programa")]

		arvore = _montar(areas, pessoas)

		self.assertEqual([r["associado"] for r in arvore["raizes"]], ["Caio"])
		caio = arvore["raizes"][0]
		self.assertEqual([f["associado"] for f in caio["children"]], ["Mariana"])

	def test_membro_responde_ao_lider_da_propria_area(self):
		areas = [_area("Programa", responsavel="Mariana")]
		pessoas = [_pessoa("Mariana", "Programa"), _pessoa("Juliana", "Programa")]

		arvore = _montar(areas, pessoas)
		mariana = arvore["raizes"][0]

		self.assertEqual(mariana["associado"], "Mariana")
		self.assertEqual([f["associado"] for f in mariana["children"]], ["Juliana"])

	def test_diretos_e_indiretos_do_exemplo_do_enunciado(self):
		"""Coordeno o Administrativo; Fernanda lidera Manutenção; Renan é da Manutenção."""
		areas = [
			_area("Administrativo", responsavel="Coordenador"),
			_area("Manutenção", mae="Administrativo", responsavel="Fernanda"),
		]
		pessoas = [
			_pessoa("Coordenador", "Administrativo"),
			_pessoa("Fernanda", "Manutenção"),
			_pessoa("Renan", "Manutenção"),
		]

		arvore = _montar(areas, pessoas)
		nos = _por_id(arvore["raizes"])

		self.assertEqual(nos["Coordenador"]["diretos"], 1)
		self.assertEqual(nos["Coordenador"]["indiretos"], 1)
		self.assertEqual(nos["Fernanda"]["diretos"], 1)
		self.assertEqual(nos["Fernanda"]["indiretos"], 0)
		self.assertEqual(nos["Renan"]["diretos"], 0)

	def test_area_sem_responsavel_vira_no_de_grupo(self):
		areas = [
			_area("Administrativo", responsavel="Coordenador"),
			_area("Manutenção", mae="Administrativo"),
		]
		pessoas = [_pessoa("Coordenador", "Administrativo"), _pessoa("Renan", "Manutenção")]

		arvore = _montar(areas, pessoas)
		coordenador = arvore["raizes"][0]
		grupo = coordenador["children"][0]

		self.assertEqual(grupo["tipo"], "grupo")
		self.assertEqual(grupo["id"], "area:Manutenção")
		self.assertEqual(grupo["membros"], 1)
		self.assertEqual([f["associado"] for f in grupo["children"]], ["Renan"])
		self.assertEqual(arvore["avisos"]["areas_sem_responsavel"], ["Manutenção"])

	def test_grupo_e_transparente_na_contagem_de_diretos(self):
		"""Sem líder na sub-área, quem está nela responde de fato a quem está acima."""
		areas = [
			_area("Administrativo", responsavel="Coordenador"),
			_area("Manutenção", mae="Administrativo"),
		]
		pessoas = [
			_pessoa("Coordenador", "Administrativo"),
			_pessoa("Renan", "Manutenção"),
			_pessoa("Ana", "Manutenção"),
		]

		arvore = _montar(areas, pessoas)
		coordenador = arvore["raizes"][0]

		self.assertEqual(coordenador["diretos"], 2)
		self.assertEqual(coordenador["indiretos"], 0)

	def test_lider_sobe_ate_achar_area_mae_com_lider(self):
		areas = [
			_area("Presidência", responsavel="Caio"),
			_area("Administrativo", mae="Presidência"),
			_area("Manutenção", mae="Administrativo", responsavel="Fernanda"),
		]
		pessoas = [_pessoa("Caio", "Presidência"), _pessoa("Fernanda", "Manutenção")]

		arvore = _montar(areas, pessoas)
		caio = arvore["raizes"][0]

		self.assertEqual([f["associado"] for f in caio["children"]], ["Fernanda"])

	def test_pessoa_sem_area_vai_para_bloco_separado(self):
		areas = [_area("Programa", responsavel="Mariana")]
		pessoas = [_pessoa("Mariana", "Programa"), _pessoa("Solta", None)]

		arvore = _montar(areas, pessoas)

		self.assertEqual([r["associado"] for r in arvore["raizes"]], ["Mariana"])
		self.assertIsNotNone(arvore["sem_area"])
		self.assertEqual([f["associado"] for f in arvore["sem_area"]["children"]], ["Solta"])
		self.assertEqual(arvore["avisos"]["pessoas_sem_area"], 1)

	def test_area_inexistente_no_associado_cai_em_sem_area(self):
		areas = [_area("Programa", responsavel="Mariana")]
		pessoas = [_pessoa("Mariana", "Programa"), _pessoa("Orfã", "Area Apagada")]

		arvore = _montar(areas, pessoas)

		self.assertEqual([f["associado"] for f in arvore["sem_area"]["children"]], ["Orfã"])

	def test_sem_area_e_none_quando_todo_mundo_tem_area(self):
		areas = [_area("Programa", responsavel="Mariana")]
		arvore = _montar(areas, [_pessoa("Mariana", "Programa")])

		self.assertIsNone(arvore["sem_area"])
		self.assertEqual(arvore["avisos"]["pessoas_sem_area"], 0)

	def test_ramo_so_aparece_para_escotista(self):
		areas = [_area("Escoteiro", responsavel="Pedro")]
		pessoas = [
			_pessoa("Pedro", "Escoteiro", categoria="Escotista", ramo="Sênior"),
			_pessoa("Rafael", "Escoteiro", categoria="Dirigente", ramo="Pioneiro"),
		]

		arvore = _montar(areas, pessoas)
		nos = _por_id(arvore["raizes"])

		self.assertEqual(nos["Pedro"]["ramo"], "Sênior")
		self.assertIsNone(nos["Rafael"]["ramo"])

	def test_ramo_nao_se_aplica_nao_vira_badge(self):
		areas = [_area("Escoteiro", responsavel="Pedro")]
		pessoas = [_pessoa("Pedro", "Escoteiro", categoria="Escotista", ramo="Não se aplica")]

		arvore = _montar(areas, pessoas)

		self.assertIsNone(arvore["raizes"][0]["ramo"])
		self.assertIsNone(arvore["raizes"][0]["ramo_slug"])

	def test_slug_do_ramo_alimenta_a_classe_badge_ramo(self):
		"""O slug sem acento é o sufixo de `badge-ramo-*` no design system."""
		esperado = {
			"Filhotes": "filhotes",
			"Lobinho": "lobinho",
			"Escoteiro": "escoteiro",
			"Sênior": "senior",
			"Pioneiro": "pioneiro",
		}
		areas = [_area("Seção")]
		for ramo, slug in esperado.items():
			pessoas = [_pessoa(f"P {ramo}", "Seção", categoria="Escotista", ramo=ramo)]
			no = _montar(areas, pessoas)["raizes"][0]["children"][0]

			self.assertEqual(no["ramo"], ramo)
			self.assertEqual(no["ramo_slug"], slug)

	def test_slug_fica_vazio_para_quem_nao_mostra_ramo(self):
		areas = [_area("Administrativo", responsavel="Rafael")]
		pessoas = [_pessoa("Rafael", "Administrativo", categoria="Dirigente", ramo="Pioneiro")]

		no = _montar(areas, pessoas)["raizes"][0]

		self.assertIsNone(no["ramo"])
		self.assertIsNone(no["ramo_slug"])

	def test_responsavel_fora_do_conjunto_deixa_a_area_sem_lider(self):
		"""Um responsável inativo (ou beneficiário) não chega em `pessoas`."""
		areas = [_area("Programa", responsavel="Desligado")]
		pessoas = [_pessoa("Juliana", "Programa")]

		arvore = _montar(areas, pessoas)

		self.assertEqual(arvore["avisos"]["areas_sem_responsavel"], ["Programa"])
		self.assertEqual(arvore["raizes"][0]["tipo"], "grupo")
		self.assertEqual([f["associado"] for f in arvore["raizes"][0]["children"]], ["Juliana"])

	def test_ciclo_na_hierarquia_nao_trava_a_montagem(self):
		areas = [
			_area("A", mae="B", responsavel="Ana"),
			_area("B", mae="A", responsavel="Bruno"),
		]
		pessoas = [_pessoa("Ana", "A"), _pessoa("Bruno", "B")]

		arvore = _montar(areas, pessoas)

		self.assertEqual(sorted(arvore["avisos"]["ciclos"]), ["A", "B"])
		self.assertEqual(sorted(r["associado"] for r in arvore["raizes"]), ["Ana", "Bruno"])

	def test_funcao_principal_vai_para_o_card(self):
		areas = [_area("Programa", responsavel="Mariana")]
		pessoas = [_pessoa("Mariana", "Programa")]

		arvore = _montar(
			areas,
			pessoas,
			lotacoes=[{"associado": "Mariana", "area": "Programa", "funcao": "Diretora de Programa"}],
		)

		self.assertEqual(arvore["raizes"][0]["funcao_interna"], "Diretora de Programa")
		self.assertEqual(arvore["raizes"][0]["lidera_area"], "Programa")

	def test_avatar_entra_quando_existe_e_iniciais_sempre(self):
		areas = [_area("Programa", responsavel="Mariana Silva")]
		pessoas = [_pessoa("Mariana Silva", "Programa")]

		arvore = _montar(areas, pessoas, avatares={"Mariana Silva": "/files/foto.png"})

		self.assertEqual(arvore["raizes"][0]["avatar_url"], "/files/foto.png")
		self.assertEqual(arvore["raizes"][0]["iniciais"], "MS")

	def test_irmaos_saem_com_lideres_primeiro_e_time_em_ordem_alfabetica(self):
		areas = [
			_area("Presidência", responsavel="Caio"),
			_area("Programa", mae="Presidência", responsavel="Mariana"),
		]
		pessoas = [
			_pessoa("Caio", "Presidência"),
			_pessoa("Mariana", "Programa"),
			_pessoa("Zeca", "Presidência"),
			_pessoa("Bia", "Presidência"),
		]

		arvore = _montar(areas, pessoas)
		caio = arvore["raizes"][0]

		self.assertEqual([f["associado"] for f in caio["children"]], ["Mariana", "Bia", "Zeca"])

	def test_total_de_pessoas_conta_todo_mundo_que_entrou(self):
		areas = [_area("Programa", responsavel="Mariana")]
		pessoas = [_pessoa("Mariana", "Programa"), _pessoa("Juliana", "Programa"), _pessoa("Solta")]

		arvore = _montar(areas, pessoas)

		self.assertEqual(arvore["total_pessoas"], 3)

	def test_arvore_vazia_nao_quebra(self):
		arvore = _montar([], [])

		self.assertEqual(arvore["raizes"], [])
		self.assertIsNone(arvore["sem_area"])
		self.assertEqual(arvore["total_pessoas"], 0)


class TestFiltroPorArea(FrappeTestCase):
	"""O recorte roda antes de `montar_arvore`, sobre as listas cruas."""

	def setUp(self):
		self.areas = [
			_area("Presidência", responsavel="Caio"),
			_area("Programa", mae="Presidência", responsavel="Mariana"),
			_area("Lobinho", mae="Programa", responsavel="Ana"),
			_area("Financeiro", mae="Presidência", responsavel="Thiago"),
		]
		self.pessoas = [
			_pessoa("Caio", "Presidência"),
			_pessoa("Mariana", "Programa"),
			_pessoa("Ana", "Lobinho"),
			_pessoa("Bia", "Lobinho"),
			_pessoa("Thiago", "Financeiro"),
			_pessoa("Solta", None),
		]

	def test_sem_filtro_devolve_tudo(self):
		areas, pessoas, _lot = _recortar_por_area("", self.areas, self.pessoas, _lotacoes(self.pessoas))

		self.assertEqual(len(areas), 4)
		self.assertEqual(len(pessoas), 6)

	def test_filtro_traz_a_area_e_as_que_respondem_para_ela(self):
		areas, pessoas, _lot = _recortar_por_area(
			"Programa", self.areas, self.pessoas, _lotacoes(self.pessoas)
		)

		self.assertEqual({a["name"] for a in areas}, {"Programa", "Lobinho"})
		self.assertEqual({p["name"] for p in pessoas}, {"Mariana", "Ana", "Bia"})

	def test_filtro_em_folha_traz_so_ela(self):
		areas, pessoas, _lot = _recortar_por_area(
			"Lobinho", self.areas, self.pessoas, _lotacoes(self.pessoas)
		)

		self.assertEqual({a["name"] for a in areas}, {"Lobinho"})
		self.assertEqual({p["name"] for p in pessoas}, {"Ana", "Bia"})

	def test_area_filtrada_vira_raiz_da_arvore(self):
		areas, pessoas, lot = _recortar_por_area(
			"Programa", self.areas, self.pessoas, _lotacoes(self.pessoas)
		)
		arvore = _montar(areas, pessoas, lotacoes=lot)

		self.assertEqual([r["associado"] for r in arvore["raizes"]], ["Mariana"])
		self.assertEqual(arvore["raizes"][0]["diretos"], 1)
		self.assertEqual(arvore["raizes"][0]["indiretos"], 1)

	def test_responsavel_lotado_fora_da_area_que_lidera_entra_no_recorte(self):
		"""Este é o caso que o recorte no servidor resolve e o recorte no nó perderia."""
		areas = [
			_area("Presidência", responsavel="Caio"),
			_area("Eventos", mae="Presidência", responsavel="Caio"),
		]
		pessoas = [_pessoa("Caio", "Presidência"), _pessoa("Bia", "Eventos")]

		_areas, recortadas, _lot = _recortar_por_area("Eventos", areas, pessoas, _lotacoes(pessoas))

		self.assertEqual({p["name"] for p in recortadas}, {"Caio", "Bia"})

	def test_filtro_sem_area_traz_so_quem_nao_tem_lotacao(self):
		areas, pessoas, _lot = _recortar_por_area(
			FILTRO_SEM_AREA, self.areas, self.pessoas, _lotacoes(self.pessoas)
		)

		self.assertEqual(areas, [])
		self.assertEqual({p["name"] for p in pessoas}, {"Solta"})

	def test_area_inexistente_nao_devolve_ninguem(self):
		areas, pessoas, _lot = _recortar_por_area(
			"Area Apagada", self.areas, self.pessoas, _lotacoes(self.pessoas)
		)

		self.assertEqual(areas, [])
		self.assertEqual(pessoas, [])

	def test_ciclo_entre_areas_nao_trava_o_recorte(self):
		areas = [_area("A", mae="B"), _area("B", mae="A")]
		pessoas = [_pessoa("Ana", "A"), _pessoa("Bruno", "B")]

		recortadas, _pessoas, _lot = _recortar_por_area("A", areas, pessoas, _lotacoes(pessoas))

		self.assertEqual({a["name"] for a in recortadas}, {"A", "B"})


def _linha_de_funcao(funcao, principal=0, inicio=None, fim=None):
	return {
		"funcao": funcao,
		"area": None,
		"principal": principal,
		"data_inicio": inicio,
		"data_fim": fim,
	}


class TestMontarDetalhe(FrappeTestCase):
	"""Painel lateral: o que cada card mostra quando é aberto."""

	def _pessoa(self, **extra):
		base = {
			"name": "assoc-1",
			"nome_completo": "Mariana Silva",
			"categoria": "Escotista",
			"ramo": "Pioneiro",
			"secao": "Clã Pioneiro",
			"telefone": "+5511999998888",
		}
		base.update(extra)
		return base

	def test_identidade_e_badges(self):
		detalhe = montar_detalhe(self._pessoa(), [], {}, {}, "/files/foto.png", ["Programa"])

		self.assertEqual(detalhe["nome"], "Mariana Silva")
		self.assertEqual(detalhe["iniciais"], "MS")
		self.assertEqual(detalhe["avatar_url"], "/files/foto.png")
		self.assertEqual(detalhe["areas"], ["Programa"])
		self.assertEqual(detalhe["linha"], "Escotista")
		self.assertEqual(detalhe["ramo"], "Pioneiro")
		self.assertEqual(detalhe["ramo_slug"], "pioneiro")
		self.assertEqual(detalhe["secao"], "Clã Pioneiro")

	def test_ramo_e_secao_somem_para_quem_nao_e_escotista(self):
		detalhe = montar_detalhe(self._pessoa(categoria="Dirigente"), [], {}, {}, None)

		self.assertIsNone(detalhe["ramo"])
		self.assertIsNone(detalhe["ramo_slug"])
		self.assertIsNone(detalhe["secao"])

	def test_periodo_de_funcao_atual(self):
		funcoes = [_linha_de_funcao("Diretora", principal=1, inicio="2024-01-15")]
		detalhe = montar_detalhe(self._pessoa(), funcoes, {}, {}, None)

		self.assertEqual(detalhe["funcoes"][0]["periodo"], "Atual · desde jan/2024")
		self.assertTrue(detalhe["funcoes"][0]["atual"])

	def test_periodo_fechado(self):
		funcoes = [_linha_de_funcao("Conselho", inicio="2022-02-01", fim="2023-12-31")]
		detalhe = montar_detalhe(self._pessoa(), funcoes, {}, {}, None)

		self.assertEqual(detalhe["funcoes"][0]["periodo"], "fev/2022 " + chr(0x2013) + " dez/2023")
		self.assertFalse(detalhe["funcoes"][0]["atual"])

	def test_periodo_sem_datas(self):
		detalhe = montar_detalhe(self._pessoa(), [_linha_de_funcao("Sem data")], {}, {}, None)

		self.assertEqual(detalhe["funcoes"][0]["periodo"], "Sem período informado")

	def test_periodo_aceita_objeto_date(self):
		"""O banco devolve `date`; os outros testes usam string ISO."""
		funcoes = [_linha_de_funcao("Diretora", inicio=datetime.date(2024, 3, 1))]
		detalhe = montar_detalhe(self._pessoa(), funcoes, {}, {}, None)

		self.assertEqual(detalhe["funcoes"][0]["periodo"], "Atual · desde mar/2024")

	def test_funcao_principal_e_a_primeira_da_lista(self):
		funcoes = [
			_linha_de_funcao("Diretora de Programa", principal=1, inicio="2024-01-01"),
			_linha_de_funcao("Conselho", inicio="2022-02-01", fim="2023-12-31"),
		]
		detalhe = montar_detalhe(self._pessoa(), funcoes, {}, {}, None)

		self.assertEqual(detalhe["funcao_principal"], "Diretora de Programa")
		self.assertEqual([f["titulo"] for f in detalhe["funcoes"]], ["Diretora de Programa", "Conselho"])

	def test_responsabilidades_vao_para_a_funcao_certa(self):
		funcoes = [_linha_de_funcao("Diretora", principal=1), _linha_de_funcao("Conselho")]
		responsabilidades = {
			"Diretora": [{"responsabilidade": "Coordenar seções", "detalhe": "com apoio"}],
			"Conselho": [{"responsabilidade": "Votar no conselho", "detalhe": ""}],
		}
		detalhe = montar_detalhe(self._pessoa(), funcoes, {}, responsabilidades, None)

		self.assertEqual(
			detalhe["funcoes"][0]["responsabilidades"],
			[{"responsabilidade": "Coordenar seções", "detalhe": "com apoio"}],
		)
		# Detalhe em branco vira None, para o front não renderizar linha vazia.
		self.assertEqual(
			detalhe["funcoes"][1]["responsabilidades"],
			[{"responsabilidade": "Votar no conselho", "detalhe": None}],
		)

	def test_descricao_vem_da_definicao_da_funcao(self):
		definicoes = {"Diretora": {"descricao": "Cuida do programa.", "area": "Programa"}}
		detalhe = montar_detalhe(self._pessoa(), [_linha_de_funcao("Diretora")], definicoes, {}, None)

		self.assertEqual(detalhe["funcoes"][0]["descricao"], "Cuida do programa.")
		self.assertEqual(detalhe["funcoes"][0]["area"], "Programa")

	def test_sem_funcao_nao_quebra(self):
		detalhe = montar_detalhe(self._pessoa(), [], {}, {}, None)

		self.assertIsNone(detalhe["funcao_principal"])
		self.assertEqual(detalhe["funcoes"], [])

	def test_telefone_vira_digitos_para_o_wa_me(self):
		detalhe = montar_detalhe(self._pessoa(telefone="(11) 99999-8888"), [], {}, {}, None)

		self.assertEqual(detalhe["whatsapp"], "5511999998888")

	def test_sem_telefone_nao_gera_link(self):
		for vazio in (None, "", "   "):
			detalhe = montar_detalhe(self._pessoa(telefone=vazio), [], {}, {}, None)
			self.assertIsNone(detalhe["whatsapp"], f"telefone {vazio!r} não deveria virar link")

	def test_telefone_impossivel_de_normalizar_nao_gera_link(self):
		detalhe = montar_detalhe(self._pessoa(telefone="123"), [], {}, {}, None)

		self.assertIsNone(detalhe["whatsapp"])

	def test_areas_saem_das_funcoes_em_vigor(self):
		funcoes = [
			_linha_de_funcao("Diretora", principal=1, inicio="2024-01-01"),
			_linha_de_funcao("Eventos", inicio="2023-01-01"),
			# Encerrada: a área dela não conta como lotação atual.
			_linha_de_funcao("Antiga", inicio="2020-01-01", fim="2021-01-01"),
		]
		definicoes = {
			"Diretora": {"area": "Programa"},
			"Eventos": {"area": "Eventos"},
			"Antiga": {"area": "Financeiro"},
		}
		detalhe = montar_detalhe(self._pessoa(), funcoes, definicoes, {}, None)

		self.assertEqual(detalhe["areas"], ["Eventos", "Programa"])

	def test_area_liderada_entra_mesmo_sem_funcao(self):
		detalhe = montar_detalhe(self._pessoa(), [], {}, {}, None, ["Manutenção"])

		self.assertEqual(detalhe["areas"], ["Manutenção"])
		self.assertEqual(detalhe["areas_lideradas"], ["Manutenção"])

	def test_ficha_url_aponta_para_o_associado(self):
		detalhe = montar_detalhe(self._pessoa(name="abc123"), [], {}, {}, None)

		self.assertEqual(detalhe["ficha_url"], "/associados/detalhe?name=abc123")


class TestPermissaoDaPagina(FrappeTestCase):
	"""O organograma é aberto a qualquer pessoa logada; Guest continua fora."""

	#: `user_has_access` trata lista vazia como "não informado" e cai nos papéis da
	#: sessão — que no test runner é Administrator. Um papel inexistente é a forma
	#: de dizer "alguém logado, sem papel nenhum que importe".
	SEM_PAPEL: ClassVar[list[str]] = ["ZZ Papel Inexistente"]

	def test_qualquer_autenticado_ve_o_organograma(self):
		self.assertTrue(user_has_access("/gestao_adultos/organograma", roles=self.SEM_PAPEL))
		self.assertTrue(user_has_access("/gestao_adultos", roles=self.SEM_PAPEL))

	def test_entrevistas_continua_restrito(self):
		self.assertFalse(user_has_access("/gestao_adultos/entrevista_competencias", roles=self.SEM_PAPEL))

	def test_ficha_liberada_para_gestor_de_adultos(self):
		self.assertTrue(user_has_access("/associados/detalhe", roles=["Gestor de Adultos"]))
		self.assertFalse(user_has_access("/associados/detalhe", roles=self.SEM_PAPEL))
