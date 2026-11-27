# Copyright (c) 2026, Grupo Escoteiro Professora Inah de Mello - 47/SP and contributors
# For license information, please see license.txt
"""Formulários de candidatura e de assuntos gerais e a página pública (spec RF-09, RF-12, RF-13)."""

from __future__ import annotations

import json
import random

import frappe
from frappe.tests.utils import FrappeTestCase
from frappe.utils import add_days, add_years, getdate

from gris.api.assembleias import constantes as c
from gris.api.assembleias import formularios as f
from gris.tests.test_assembleias_criacao import _criar, _usuario

PREFIXO = "ZZ Teste Assembleia"


def _cpf() -> str:
	"""CPF válido aleatório, para não colidir com cadastros do site."""
	base = [random.randint(0, 9) for _ in range(9)]
	for _ in range(2):
		soma = sum(d * p for d, p in zip(base, range(len(base) + 1, 1, -1), strict=False))
		resto = (soma * 10) % 11
		base.append(0 if resto == 10 else resto)
	return "".join(map(str, base))


def _associado(sufixo, anos=30, categoria="Dirigente", status="Válido", ativo=True, usuario=None) -> str:
	doc = frappe.get_doc(
		{
			"doctype": "Associado",
			"nome_completo": f"{PREFIXO} {sufixo}",
			"cpf": _cpf(),
			"data_de_nascimento": add_years(getdate(), -anos),
			"categoria": categoria,
			"status_no_grupo": "Ativo" if ativo else "Inativo",
			"historico_no_grupo": [{"data_de_ingresso": "2020-01-01"}],
		}
	).insert(ignore_permissions=True)
	# Direto no banco: salvar id_escoteiros/registro pelo doc dispara integrações reais.
	frappe.db.set_value(
		"Associado",
		doc.name,
		{
			"status": status,
			"validade_registro": add_years(getdate(), 1),
			"registro": f"R{sufixo}",
			# O controller deriva a situação do histórico; o teste a força direto.
			"status_no_grupo": "Ativo" if ativo else "Inativo",
		},
	)
	if usuario:
		frappe.db.set_value("Associado", doc.name, "id_escoteiros", _usuario(usuario))
	return doc.name


def _responsavel(sufixo, usuario=None) -> str:
	doc = frappe.get_doc(
		{"doctype": "Responsavel", "nome_completo": f"{PREFIXO} Resp {sufixo}", "cpf": _cpf()}
	).insert(ignore_permissions=True)
	if usuario:
		frappe.db.set_value("Responsavel", doc.name, "email", _usuario(usuario))
	return doc.name


class _Base(FrappeTestCase):
	def setUp(self):
		frappe.set_user("Administrator")
		self.name = _criar(add_days(getdate(), 30))["name"]

	def tearDown(self):
		frappe.set_user("Administrator")
		frappe.db.rollback()

	def _como(self, usuario):
		frappe.set_user(usuario)


class TestPessoaEElegibilidade(_Base):
	def test_pessoa_do_usuario(self):
		associado = _associado("A1", usuario="zz-asm-a1@example.com")
		responsavel = _responsavel("R1", usuario="zz-asm-r1@example.com")
		_usuario("zz-asm-ninguem@example.com")

		self.assertEqual(f.pessoa_do_usuario("zz-asm-a1@example.com").name, associado)
		self.assertEqual(f.pessoa_do_usuario("zz-asm-r1@example.com").tipo, "Responsavel")
		self.assertEqual(f.pessoa_do_usuario("zz-asm-r1@example.com").name, responsavel)
		self.assertIsNone(f.pessoa_do_usuario("zz-asm-ninguem@example.com"))
		self.assertIsNone(f.pessoa_do_usuario("Guest"))

	def test_regras_por_cargo(self):
		data = getdate()
		jovem = f._pessoa("Associado", _associado("J17", anos=17, categoria="Beneficiário"))
		vencido = f._pessoa("Associado", _associado("V", status="Vencido"))
		inativo = f._pessoa("Associado", _associado("I", ativo=False))
		resp = f._pessoa("Responsavel", _responsavel("R2"))

		self.assertTrue(f.elegibilidade(c.FORMULARIO_MESA, jovem, data)["ok"])
		self.assertFalse(f.elegibilidade(c.FORMULARIO_DELEGADO, jovem, data)["ok"])
		self.assertFalse(f.elegibilidade(c.FORMULARIO_DELEGADO, vencido, data)["ok"])
		cf = f.elegibilidade(c.FORMULARIO_COMISSAO_FISCAL, vencido, data)
		self.assertTrue(cf["ok"])
		self.assertIn("até a posse", cf["aviso"])
		self.assertFalse(f.elegibilidade(c.FORMULARIO_MESA, inativo, data)["ok"])
		self.assertFalse(f.elegibilidade(c.FORMULARIO_DELEGADO, resp, data)["ok"])
		self.assertTrue(f.elegibilidade(c.FORMULARIO_DIRETORIA, resp, data)["aviso"])
		self.assertTrue(f.elegibilidade(c.FORMULARIO_MESA, resp, data)["ok"])
		self.assertFalse(f.elegibilidade(c.FORMULARIO_MESA, None, data)["ok"])


class TestEnvios(_Base):
	def test_candidatura_a_mesa_e_duplicidade(self):
		_associado("M", usuario="zz-asm-m@example.com")
		self._como("zz-asm-m@example.com")
		resposta = f.enviar_candidatura(self.name, c.CARGO_PRESIDENTE_MESA, 1, "Bio", "Quero ajudar")
		self.assertEqual(resposta["cargo"], c.CARGO_PRESIDENTE_MESA)
		with self.assertRaisesRegex(frappe.ValidationError, "já se candidatou"):
			f.enviar_candidatura(self.name, c.CARGO_PRESIDENTE_MESA, 1)
		# O mesmo pode concorrer a secretário.
		f.enviar_candidatura(self.name, c.CARGO_SECRETARIO_MESA, 1)
		frappe.set_user("Administrator")
		self.assertEqual(f.contar_inscricoes(self.name)[c.CARGO_SECRETARIO_MESA], 1)

	def test_sem_confirmacao(self):
		_associado("SC", usuario="zz-asm-sc@example.com")
		self._como("zz-asm-sc@example.com")
		with self.assertRaisesRegex(frappe.ValidationError, "Confirme"):
			f.enviar_candidatura(self.name, c.CARGO_DELEGADO, 0)

	def test_sem_cadastro_e_visitante(self):
		self._como(_usuario("zz-asm-sem@example.com"))
		with self.assertRaisesRegex(frappe.ValidationError, "não está ligado"):
			f.enviar_candidatura(self.name, c.CARGO_PRESIDENTE_MESA, 1)
		frappe.set_user("Guest")
		with self.assertRaises(frappe.ValidationError):
			f.enviar_assunto_geral(self.name, "Assunto", 1)

	def test_prazo_encerrado(self):
		# Diretoria e comissão fiscal fecham 8 dias antes; a assembleia é daqui a 5.
		frappe.db.set_value(c.DOCTYPE_ASSEMBLEIA, self.name, "data", add_days(getdate(), 5))
		config = frappe.get_single(c.DOCTYPE_CONFIGURACOES)
		config.manter_aberto_sem_candidatos = 0
		config.save()
		_associado("P", usuario="zz-asm-p@example.com")
		self._como("zz-asm-p@example.com")
		with self.assertRaisesRegex(frappe.ValidationError, "Inscrições encerradas"):
			f.enviar_candidatura(self.name, c.CARGO_COMISSAO_FISCAL, 1)

	def test_reaberto_sem_candidatos(self):
		frappe.db.set_value(c.DOCTYPE_ASSEMBLEIA, self.name, "data", add_days(getdate(), 5))
		_associado("RA", usuario="zz-asm-ra@example.com")
		self._como("zz-asm-ra@example.com")
		f.enviar_candidatura(self.name, c.CARGO_COMISSAO_FISCAL, 1)

	def test_fora_da_pauta(self):
		doc = frappe.get_doc(c.DOCTYPE_ASSEMBLEIA, self.name)
		doc.set("pauta", [i for i in doc.pauta if i.finalidade != c.FINALIDADE_DELEGADOS])
		doc.save()
		_associado("FP", usuario="zz-asm-fp@example.com")
		self._como("zz-asm-fp@example.com")
		with self.assertRaisesRegex(frappe.ValidationError, "não tem eleição"):
			f.enviar_candidatura(self.name, c.CARGO_DELEGADO, 1)

	def test_assunto_geral(self):
		_associado("AG", usuario="zz-asm-ag@example.com")
		self._como("zz-asm-ag@example.com")
		self.assertEqual(
			f.enviar_assunto_geral(self.name, "  Taxa do acampamento  ", 1)["conteudo"], "Taxa do acampamento"
		)
		with self.assertRaises(frappe.ValidationError):
			f.enviar_assunto_geral(self.name, "   ", 1)
		with self.assertRaisesRegex(frappe.ValidationError, "2000"):
			f.enviar_assunto_geral(self.name, "x" * 2001, 1)


class TestChapa(_Base):
	def _membros(self, pessoas, **extra):
		return json.dumps(
			[
				{"funcao": funcao, "pessoa": f"Associado::{pessoa}", **extra}
				for funcao, pessoa in zip(f.funcoes_eleitas(), pessoas, strict=False)
			]
		)

	def setUp(self):
		super().setUp()
		self.funcoes = f.funcoes_eleitas()
		if len(self.funcoes) < 2:
			self.skipTest("o site precisa de ao menos duas funções eleitas")
		self.pessoas = [_associado(f"CH{i}") for i in range(len(self.funcoes) * 2)]
		_associado("CHR", usuario="zz-asm-chapa@example.com")
		self._como("zz-asm-chapa@example.com")

	def test_chapa_completa(self):
		resposta = f.enviar_chapa(self.name, self._membros(self.pessoas), 1)
		self.assertEqual(resposta["titulo"], "Chapa 1")
		self.assertEqual(len(resposta["membros"]), len(self.funcoes))

	def test_chapa_incompleta(self):
		with self.assertRaisesRegex(frappe.ValidationError, "Preencha todas as funções"):
			f.enviar_chapa(self.name, self._membros(self.pessoas[:1]), 1)

	def test_pessoa_repetida_na_chapa(self):
		repetida = [self.pessoas[0]] * len(self.funcoes)
		with self.assertRaisesRegex(frappe.ValidationError, "mais de uma função"):
			f.enviar_chapa(self.name, self._membros(repetida), 1)

	def test_pessoa_em_duas_chapas(self):
		f.enviar_chapa(self.name, self._membros(self.pessoas), 1)
		outra = [self.pessoas[0], *self.pessoas[len(self.funcoes) + 1 :]]
		with self.assertRaisesRegex(frappe.ValidationError, "já está na Chapa 1"):
			f.enviar_chapa(self.name, self._membros(outra), 1)


class TestInscricoesEPublica(_Base):
	def test_retirar_e_pagina_publica(self):
		_associado("PB", usuario="zz-asm-pb@example.com")
		self._como("zz-asm-pb@example.com")
		f.enviar_candidatura(self.name, c.CARGO_DELEGADO, 1, "Bio <b>", "Motivo")
		frappe.set_user("Administrator")

		publica = f.dados_publicos(self.name)
		delegados = next(g for g in publica["cargos"] if g["cargo"] == c.CARGO_DELEGADO)
		self.assertEqual(set(delegados["candidaturas"][0]), {"nome", "registro", "biografia", "motivacao"})

		name = frappe.get_all(c.DOCTYPE_CANDIDATURA, filters={"assembleia": self.name}, pluck="name")[0]
		with self.assertRaises(frappe.ValidationError):
			f.retirar_inscricao("candidatura", name, "  ")
		f.retirar_inscricao("candidatura", name, "Desistência")
		publica = f.dados_publicos(self.name)
		self.assertFalse(next(g for g in publica["cargos"] if g["cargo"] == c.CARGO_DELEGADO)["candidaturas"])
		gestao = f.listar_inscricoes(self.name)
		self.assertEqual(
			next(g for g in gestao["cargos"] if g["cargo"] == c.CARGO_DELEGADO)["candidaturas"][0]["status"],
			"Retirada",
		)

	def test_retirar_exige_gestor(self):
		self._como(_usuario("zz-asm-x@example.com"))
		with self.assertRaises(frappe.PermissionError):
			f.retirar_inscricao("candidatura", "qualquer", "motivo")

	def test_pagina_publica_escapa_html(self):
		_associado("ESC", usuario="zz-asm-esc@example.com")
		self._como("zz-asm-esc@example.com")
		f.enviar_candidatura(self.name, c.CARGO_DELEGADO, 1, "<script>alert(1)</script>", "")
		frappe.set_user("Guest")
		html = self._renderizar(f"/assembleias/candidaturas?assembleia={self.name}")
		self.assertIn("Zz Teste Assembleia Esc", html)
		# O Frappe já guarda o texto escapado; o template escapa de novo. O que importa é
		# que nenhuma tag vinda do candidato chegue ao HTML.
		self.assertNotIn("<script>alert(1)</script>", html)
		self.assertIn("alert(1)", html)

	def _renderizar(self, caminho: str) -> str:
		import frappe.app
		from frappe.website.serve import get_response
		from werkzeug.test import EnvironBuilder

		anterior = getattr(frappe.local, "request", None)
		rota, _sep, consulta = caminho.partition("?")
		frappe.local.request = frappe.app.Request(
			EnvironBuilder(
				path=rota, query_string=consulta, headers={"Host": frappe.local.site}
			).get_environ()
		)
		frappe.local.form_dict = frappe._dict(
			dict(parte.split("=", 1) for parte in consulta.split("&") if "=" in parte)
		)
		try:
			return get_response(rota.lstrip("/")).get_data(as_text=True)
		finally:
			frappe.local.request = anterior
