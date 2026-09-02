# Copyright (c) 2026, Grupo Escoteiro Professora Inah de Mello - 47/SP and contributors
# For license information, please see license.txt

"""Testes do módulo Sugestões e Problemas e da ponte com Gestão de Tarefas."""

from __future__ import annotations

import frappe
from frappe.tests.utils import FrappeTestCase

from gris.api.gestao_de_tarefas.minhas_tarefas import (
	_listar_tarefas_do_usuario,
)
from gris.api.gestao_de_tarefas.minhas_tarefas import (
	atualizar_status as atualizar_status_tarefa,
)
from gris.api.sugestoes import constantes as c
from gris.api.sugestoes.portal import (
	CARD_ORDER_BY,
	atualizar_descricao,
	atualizar_status,
	detalhes,
	get_comentarios,
	listar_board,
	reclassificar,
	reordenar,
	submeter_solicitacao,
)
from gris.gestao_de_tarefas import board_sync_sugestoes as board_sync
from gris.gestao_de_tarefas.board_sync_sugestoes import (
	ensure_board_desenvolvimento,
	sincronizar_desenvolvedores_no_board,
)

DEV_EMAIL = "dev.sugestoes@teste.gris"
NAO_DEV_EMAIL = "leigo.sugestoes@teste.gris"


def _criar_user(email: str, roles: list[str]) -> str:
	if frappe.db.exists("User", email):
		user = frappe.get_doc("User", email)
		user.enabled = 1
		user.set("roles", [])
		for role in roles:
			user.append("roles", {"role": role})
		user.save(ignore_permissions=True)
		return email

	user = frappe.get_doc(
		{
			"doctype": "User",
			"email": email,
			"first_name": email.split("@")[0],
			"send_welcome_email": 0,
			"roles": [{"role": role} for role in roles],
		}
	)
	user.insert(ignore_permissions=True)
	return user.name


class TestSugestaoOuProblema(FrappeTestCase):
	@classmethod
	def setUpClass(cls):
		super().setUpClass()
		if not frappe.db.exists("Role", c.ROLE_DESENVOLVEDOR):
			frappe.get_doc({"doctype": "Role", "role_name": c.ROLE_DESENVOLVEDOR, "desk_access": 0}).insert(
				ignore_permissions=True
			)
		ensure_board_desenvolvimento()
		frappe.db.commit()

	def setUp(self):
		self.dev = _criar_user(DEV_EMAIL, [c.ROLE_DESENVOLVEDOR])
		self.nao_dev = _criar_user(NAO_DEV_EMAIL, [])
		self.board = ensure_board_desenvolvimento()

	def tearDown(self):
		# FrappeTestCase só faz rollback por classe: sem isto os documentos de um
		# teste vazam para o próximo e quebram com DuplicateEntryError.
		frappe.db.rollback()

	def _nova(self, **kwargs):
		dados = {
			"doctype": "Sugestao ou Problema",
			"titulo": "Erro ao salvar contribuição",
			"tipo": c.TIPO_PROBLEMA,
			"modulo": "Financeiro",
			"descricao": "Ao clicar em salvar aparece uma tela branca.",
		}
		dados.update(kwargs)
		return frappe.get_doc(dados).insert(ignore_permissions=True)

	# ───────────────────────── validação ─────────────────────────

	def test_submissao_cai_na_coluna_de_triagem_do_tipo(self):
		problema = self._nova()
		self.assertEqual(problema.status, c.COLUNA_PROBLEMAS)

		funcionalidade = self._nova(tipo=c.TIPO_FUNCIONALIDADE, modulo="Projetos")
		self.assertEqual(funcionalidade.status, c.COLUNA_FUNCIONALIDADES)

	def test_registra_solicitante_e_data_de_submissao(self):
		doc = self._nova()
		self.assertEqual(doc.solicitante, frappe.session.user)
		self.assertTrue(doc.solicitante_nome)
		self.assertTrue(doc.data_submissao)

	def test_tipo_invalido_e_rejeitado(self):
		with self.assertRaises(frappe.ValidationError):
			self._nova(tipo="Reclamação")

	def test_modulo_invalido_e_rejeitado(self):
		with self.assertRaises(frappe.ValidationError):
			self._nova(modulo="Almoxarifado")

	def test_novo_modulo_nao_vale_para_problema(self):
		"""Não dá para relatar um bug em algo que ainda não existe."""
		with self.assertRaises(frappe.ValidationError):
			self._nova(tipo=c.TIPO_PROBLEMA, modulo=c.MODULO_NOVO)

		doc = self._nova(tipo=c.TIPO_FUNCIONALIDADE, modulo=c.MODULO_NOVO)
		self.assertEqual(doc.modulo, c.MODULO_NOVO)

	def test_coluna_de_triagem_precisa_bater_com_o_tipo(self):
		"""Na inserção o status é corrigido em silêncio; na edição, recusado.

		São comportamentos diferentes de propósito: o Select preenche a primeira
		opção sozinho, então throw no insert quebraria toda "Nova funcionalidade".
		"""
		doc = self._nova(tipo=c.TIPO_PROBLEMA, status=c.COLUNA_FUNCIONALIDADES)
		self.assertEqual(doc.status, c.COLUNA_PROBLEMAS)

		doc.status = c.COLUNA_FUNCIONALIDADES
		with self.assertRaises(frappe.ValidationError):
			doc.save(ignore_permissions=True)

	def test_responsavel_sem_role_desenvolvedor_e_rejeitado(self):
		doc = self._nova()
		doc.responsavel = self.nao_dev
		with self.assertRaises(frappe.ValidationError):
			doc.save(ignore_permissions=True)

	def test_opcoes_do_doctype_batem_com_as_constantes(self):
		"""O Select do JSON e as constantes são duas listas escritas à mão.

		Divergir faz a validação recusar um valor que o formulário oferece.
		"""
		meta = frappe.get_meta("Sugestao ou Problema")

		def opcoes(fieldname: str) -> list[str]:
			bruto = meta.get_field(fieldname).options or ""
			return [linha for linha in bruto.split("\n") if linha]

		self.assertEqual(opcoes("tipo"), list(c.TIPOS))
		self.assertEqual(opcoes("modulo"), list(c.MODULOS))
		self.assertEqual(opcoes("status"), list(c.COLUNAS))

	def test_modulos_cobrem_o_sidebar(self):
		from gris.api.portal_access import SIDEBAR_STRUCTURE

		faltando = [str(item["label"]) for item in SIDEBAR_STRUCTURE if str(item["label"]) not in c.MODULOS]
		self.assertEqual(faltando, [], f"Módulos do sidebar ausentes em MODULOS: {faltando}")

	# ─────────────────────── tarefa espelho ───────────────────────

	def test_sem_responsavel_nao_cria_tarefa(self):
		doc = self._nova()
		self.assertFalse(doc.tarefa)

	def test_alocar_responsavel_cria_tarefa_no_quadro_certo(self):
		doc = self._nova()
		doc.responsavel = self.dev
		doc.save(ignore_permissions=True)
		doc.reload()

		self.assertTrue(doc.tarefa)
		tarefa = frappe.get_doc("Gestao de Tarefas", doc.tarefa)
		self.assertEqual(tarefa.board, self.board)
		self.assertEqual(tarefa.responsavel, self.dev)
		self.assertIn(doc.titulo, tarefa.descricao)

	def test_tarefa_aparece_em_minhas_tarefas_do_responsavel(self):
		"""É o requisito central: o item tem que chegar na fila do desenvolvedor."""
		doc = self._nova()
		doc.responsavel = self.dev
		doc.save(ignore_permissions=True)
		doc.reload()

		nomes = {t["name"] for t in _listar_tarefas_do_usuario(self.dev, apenas_urgentes=False)}
		self.assertIn(doc.tarefa, nomes)

	def test_status_da_sugestao_empurra_a_tarefa(self):
		doc = self._nova()
		doc.responsavel = self.dev
		doc.save(ignore_permissions=True)
		doc.reload()

		doc.status = c.COLUNA_EM_DESENVOLVIMENTO
		doc.save(ignore_permissions=True)
		self.assertEqual(
			frappe.db.get_value("Gestao de Tarefas", doc.tarefa, "status"), c.TAREFA_EM_ANDAMENTO
		)

	def test_status_da_tarefa_volta_para_a_sugestao(self):
		doc = self._nova()
		doc.responsavel = self.dev
		doc.save(ignore_permissions=True)
		doc.reload()

		tarefa = frappe.get_doc("Gestao de Tarefas", doc.tarefa)
		tarefa.status = c.TAREFA_CONCLUIDO
		tarefa.save(ignore_permissions=True)

		doc.reload()
		self.assertEqual(doc.status, c.COLUNA_CONCLUIDO)

	def test_concluir_pelo_endpoint_de_minhas_tarefas_volta_para_a_sugestao(self):
		"""O caminho que a interface realmente usa, não `doc.save()`.

		`atualizar_status` gravava com `frappe.db.set_value`, que não dispara
		`on_update` — o sync passava no teste com `save()` e não funcionava na
		tela. Este teste cobre o endpoint de ponta a ponta.
		"""
		doc = self._nova()
		doc.responsavel = self.dev
		doc.save(ignore_permissions=True)
		doc.reload()

		usuario_original = frappe.session.user
		frappe.set_user(self.dev)
		try:
			atualizar_status_tarefa(doc.tarefa, c.TAREFA_CONCLUIDO)
		finally:
			frappe.set_user(usuario_original)

		doc.reload()
		self.assertEqual(doc.status, c.COLUNA_CONCLUIDO)
		self.assertEqual(frappe.db.get_value("Gestao de Tarefas", doc.tarefa, "status"), c.TAREFA_CONCLUIDO)

	# ─────────────────── datas da linha do tempo ───────────────────

	def test_datas_do_fluxo_nascem_vazias(self):
		doc = self._nova()
		self.assertTrue(doc.data_submissao)
		self.assertFalse(doc.data_inicio_desenvolvimento)
		self.assertFalse(doc.data_conclusao)

	def test_entrar_em_desenvolvimento_carimba_o_inicio(self):
		doc = self._nova()
		doc.status = c.COLUNA_EM_DESENVOLVIMENTO
		doc.save(ignore_permissions=True)
		self.assertTrue(doc.data_inicio_desenvolvimento)
		self.assertFalse(doc.data_conclusao)

	def test_inicio_nao_e_reescrito_ao_voltar_e_avancar(self):
		"""A data que interessa é a primeira vez que o trabalho começou."""
		doc = self._nova()
		doc.status = c.COLUNA_EM_DESENVOLVIMENTO
		doc.save(ignore_permissions=True)
		primeiro_inicio = doc.data_inicio_desenvolvimento

		doc.status = c.COLUNA_SELECIONADO
		doc.save(ignore_permissions=True)
		doc.status = c.COLUNA_EM_DESENVOLVIMENTO
		doc.save(ignore_permissions=True)

		self.assertEqual(doc.data_inicio_desenvolvimento, primeiro_inicio)

	def test_concluir_direto_preenche_inicio_e_conclusao(self):
		"""Item resolvido sem passar por "Em desenvolvimento" não pode deixar
		um buraco no meio da linha do tempo."""
		doc = self._nova()
		doc.status = c.COLUNA_CONCLUIDO
		doc.save(ignore_permissions=True)

		self.assertTrue(doc.data_conclusao)
		self.assertEqual(doc.data_inicio_desenvolvimento, doc.data_conclusao)

	def test_reabrir_limpa_a_conclusao(self):
		doc = self._nova()
		doc.status = c.COLUNA_CONCLUIDO
		doc.save(ignore_permissions=True)
		self.assertTrue(doc.data_conclusao)

		doc.status = c.COLUNA_EM_DESENVOLVIMENTO
		doc.save(ignore_permissions=True)
		self.assertFalse(doc.data_conclusao)

	# ───────────────── edição da descrição ─────────────────

	def test_solicitante_pode_editar_a_propria_descricao(self):
		doc = self._nova()
		atualizar_descricao(doc.name, "<p>Agora com o passo a passo.</p>")
		doc.reload()
		self.assertIn("passo a passo", doc.descricao)

	def test_terceiro_sem_triagem_nao_edita_descricao(self):
		doc = self._nova()
		usuario_original = frappe.session.user
		frappe.set_user(self.nao_dev)
		try:
			with self.assertRaises(frappe.PermissionError):
				atualizar_descricao(doc.name, "<p>Invadindo o relato alheio.</p>")
		finally:
			frappe.set_user(usuario_original)

	# ────────────────────── níveis de acesso ──────────────────────

	def test_qualquer_autenticado_pode_submeter(self):
		"""Sem papel nenhum: reportar é aberto a quem tem login."""
		usuario_original = frappe.session.user
		frappe.set_user(self.nao_dev)
		try:
			resposta = submeter_solicitacao(
				{
					"tipo": c.TIPO_PROBLEMA,
					"modulo": "Festas",
					"titulo": "Não consigo abrir o boleto",
					"descricao": "<p>A tela fica girando.</p>",
				}
			)
			self.assertTrue(resposta["ok"])
			# Sem o papel de acompanhamento, não faz sentido mandá-lo ao quadro.
			self.assertFalse(resposta["pode_acompanhar"])
		finally:
			frappe.set_user(usuario_original)

	def test_sem_papel_nao_ve_o_quadro(self):
		"""O papel `All` do Frappe incluiria Website User (os responsáveis)."""
		doc = self._nova()
		usuario_original = frappe.session.user
		frappe.set_user(self.nao_dev)
		try:
			with self.assertRaises(frappe.PermissionError):
				listar_board()
			with self.assertRaises(frappe.PermissionError):
				detalhes(doc.name)
		finally:
			frappe.set_user(usuario_original)

	def test_papel_de_acompanhamento_ve_mas_nao_tria(self):
		observador = _criar_user("observador.sugestoes@teste.gris", [c.ROLE_ACOMPANHAMENTO])
		doc = self._nova()

		usuario_original = frappe.session.user
		frappe.set_user(observador)
		try:
			self.assertTrue(listar_board()["ok"])
			self.assertFalse(listar_board()["pode_triar"])
			with self.assertRaises(frappe.PermissionError):
				atualizar_status(doc.name, c.COLUNA_SELECIONADO)
		finally:
			frappe.set_user(usuario_original)

	def test_doctype_nao_concede_papel_all(self):
		"""Guarda contra a regressão que o semgrep pegou: `All` inclui Website
		User, e daria a qualquer responsável leitura do quadro interno."""
		papeis = {linha.role for linha in frappe.get_meta("Sugestao ou Problema").permissions}
		self.assertNotIn("All", papeis)
		self.assertIn(c.ROLE_ACOMPANHAMENTO, papeis)

	# ────────────────────── ordenação ──────────────────────

	def _nomes_na_coluna(self, status):
		return [
			linha["status"] and linha["name"]
			for linha in frappe.get_all(
				"Sugestao ou Problema",
				filters={"status": status},
				fields=["name", "status"],
				order_by=CARD_ORDER_BY,
				limit_page_length=0,
			)
		]

	def test_reordenar_grava_a_prioridade_da_coluna(self):
		a = self._nova(titulo="Primeira")
		b = self._nova(titulo="Segunda")
		cc = self._nova(titulo="Terceira")

		reordenar(c.COLUNA_PROBLEMAS, [cc.name, a.name, b.name])

		self.assertEqual(self._nomes_na_coluna(c.COLUNA_PROBLEMAS), [cc.name, a.name, b.name])

	def test_reordenar_ignora_nomes_de_fora_da_coluna(self):
		"""Quadro defasado não pode reordenar item que já saiu da coluna."""
		a = self._nova(titulo="Fica")
		outro = self._nova(titulo="Foi embora")
		outro.status = c.COLUNA_EM_DESENVOLVIMENTO
		outro.save(ignore_permissions=True)

		reordenar(c.COLUNA_PROBLEMAS, [outro.name, a.name, "SUG-99999"])

		self.assertEqual(self._nomes_na_coluna(c.COLUNA_PROBLEMAS), [a.name])
		# O de fora não teve a ordem tocada.
		self.assertEqual(frappe.db.get_value("Sugestao ou Problema", outro.name, "ordem"), 0)

	def test_reordenar_nao_dispara_o_sync_com_a_tarefa(self):
		"""Prioridade é apresentação: não deve mexer em `modified` nem na tarefa."""
		doc = self._nova()
		doc.responsavel = self.dev
		doc.save(ignore_permissions=True)
		doc.reload()

		modificado_antes = frappe.db.get_value("Sugestao ou Problema", doc.name, "modified")
		tarefa_antes = frappe.db.get_value("Gestao de Tarefas", doc.tarefa, "modified")

		reordenar(doc.status, [doc.name])

		self.assertEqual(frappe.db.get_value("Sugestao ou Problema", doc.name, "modified"), modificado_antes)
		self.assertEqual(frappe.db.get_value("Gestao de Tarefas", doc.tarefa, "modified"), tarefa_antes)

	def test_reordenar_exige_papel_de_triagem(self):
		doc = self._nova()
		usuario_original = frappe.session.user
		frappe.set_user(self.nao_dev)
		try:
			with self.assertRaises(frappe.PermissionError):
				reordenar(doc.status, [doc.name])
		finally:
			frappe.set_user(usuario_original)

	def test_submissao_nova_entra_no_topo_da_coluna(self):
		"""Entre itens de mesma ordem, o mais recente vem primeiro — senão uma
		solicitação nova se enterra embaixo das antigas."""
		antiga = self._nova(titulo="Antiga")
		nova = self._nova(titulo="Nova")
		self.assertEqual(self._nomes_na_coluna(c.COLUNA_PROBLEMAS), [nova.name, antiga.name])

	# ───────────────────── reclassificação ─────────────────────

	def test_reclassificar_troca_tipo_e_coluna(self):
		doc = self._nova(tipo=c.TIPO_FUNCIONALIDADE, modulo="Projetos")
		self.assertEqual(doc.status, c.COLUNA_FUNCIONALIDADES)

		reclassificar(doc.name, c.TIPO_PROBLEMA)

		doc.reload()
		self.assertEqual(doc.tipo, c.TIPO_PROBLEMA)
		self.assertEqual(doc.status, c.COLUNA_PROBLEMAS)

	def test_reclassificar_com_novo_modulo_explica_o_bloqueio(self):
		"""'Novo módulo' só vale para funcionalidade: reclassificar sem avisar
		deixaria o item num estado que a validação recusa no próximo save."""
		doc = self._nova(tipo=c.TIPO_FUNCIONALIDADE, modulo=c.MODULO_NOVO)

		with self.assertRaises(frappe.ValidationError) as ctx:
			reclassificar(doc.name, c.TIPO_PROBLEMA)
		self.assertIn("Troque o módulo", str(ctx.exception))

		doc.reload()
		self.assertEqual(doc.tipo, c.TIPO_FUNCIONALIDADE)

	def test_reclassificar_para_o_mesmo_tipo_e_no_op(self):
		doc = self._nova(tipo=c.TIPO_PROBLEMA)
		reclassificar(doc.name, c.TIPO_PROBLEMA)
		doc.reload()
		self.assertEqual(doc.status, c.COLUNA_PROBLEMAS)

	def test_reclassificar_exige_papel_de_triagem(self):
		doc = self._nova(tipo=c.TIPO_FUNCIONALIDADE, modulo="Projetos")
		usuario_original = frappe.session.user
		frappe.set_user(self.nao_dev)
		try:
			with self.assertRaises(frappe.PermissionError):
				reclassificar(doc.name, c.TIPO_PROBLEMA)
		finally:
			frappe.set_user(usuario_original)

	def test_item_inexistente_nao_gera_404(self):
		"""404 dispara `frappe.msgprint` no request.js mesmo com `silent: true`,
		e no portal isso vira um modal sem estilo que trava a tela. O erro tem
		que ser ValidationError (417), que o cliente transforma em toast."""
		with self.assertRaises(frappe.ValidationError) as ctx:
			detalhes("SUG-99999")
		self.assertNotIsInstance(ctx.exception, frappe.DoesNotExistError)

		for chamada in (
			lambda: atualizar_descricao("SUG-99999", "<p>x</p>"),
			lambda: get_comentarios("SUG-99999"),
		):
			with self.assertRaises(frappe.ValidationError) as ctx:
				chamada()
			self.assertNotIsInstance(ctx.exception, frappe.DoesNotExistError)

	def test_descricao_vazia_do_editor_e_recusada(self):
		doc = self._nova()
		with self.assertRaises(frappe.ValidationError):
			atualizar_descricao(doc.name, "<p><br></p>")

	def test_tarefa_atrasada_nao_move_a_sugestao(self):
		"""`Atrasado` vem do cron das 03:00 e não é um passo do fluxo."""
		doc = self._nova()
		doc.responsavel = self.dev
		doc.status = c.COLUNA_SELECIONADO
		doc.save(ignore_permissions=True)
		doc.reload()

		tarefa = frappe.get_doc("Gestao de Tarefas", doc.tarefa)
		tarefa.status = c.TAREFA_ATRASADO
		tarefa.save(ignore_permissions=True)

		doc.reload()
		self.assertEqual(doc.status, c.COLUNA_SELECIONADO)

	def test_desalocar_mantem_a_tarefa_e_limpa_o_responsavel(self):
		doc = self._nova()
		doc.responsavel = self.dev
		doc.save(ignore_permissions=True)
		doc.reload()
		tarefa_name = doc.tarefa

		doc.responsavel = None
		doc.save(ignore_permissions=True)

		self.assertTrue(frappe.db.exists("Gestao de Tarefas", tarefa_name))
		self.assertFalse(frappe.db.get_value("Gestao de Tarefas", tarefa_name, "responsavel"))
		nomes = {t["name"] for t in _listar_tarefas_do_usuario(self.dev, apenas_urgentes=False)}
		self.assertNotIn(tarefa_name, nomes)

	def test_sync_nao_entra_em_loop(self):
		"""Cada lado escreve no outro no `on_update`; sem trava isso não terminaria.

		Conta as invocações reais dos dois handlers: mover a tarefa deve disparar
		o sentido tarefa→sugestão uma vez, e o sentido de volta deve sair cedo
		pela flag em vez de reentrar.
		"""
		doc = self._nova()
		doc.responsavel = self.dev
		doc.save(ignore_permissions=True)
		doc.reload()

		chamadas = {"para_tarefa": 0, "para_sugestao": 0}
		original_tarefa = board_sync.sincronizar_tarefa_da_sugestao
		original_sugestao = board_sync.sincronizar_sugestao_da_tarefa

		def contar_tarefa(*args, **kwargs):
			chamadas["para_tarefa"] += 1
			return original_tarefa(*args, **kwargs)

		def contar_sugestao(*args, **kwargs):
			chamadas["para_sugestao"] += 1
			return original_sugestao(*args, **kwargs)

		# Os hooks resolvem a função pelo caminho pontilhado a cada chamada, então
		# trocar o atributo do módulo intercepta de verdade.
		board_sync.sincronizar_tarefa_da_sugestao = contar_tarefa
		board_sync.sincronizar_sugestao_da_tarefa = contar_sugestao
		try:
			tarefa = frappe.get_doc("Gestao de Tarefas", doc.tarefa)
			tarefa.status = c.TAREFA_EM_ANDAMENTO
			tarefa.save(ignore_permissions=True)
		finally:
			board_sync.sincronizar_tarefa_da_sugestao = original_tarefa
			board_sync.sincronizar_sugestao_da_tarefa = original_sugestao

		self.assertEqual(chamadas["para_sugestao"], 1)
		# O save da sugestão reentra no sentido oposto exatamente uma vez, e ali a
		# flag faz sair cedo. Mais que isso seria o ciclo se realimentando.
		self.assertEqual(chamadas["para_tarefa"], 1)
		doc.reload()
		self.assertEqual(doc.status, c.COLUNA_EM_DESENVOLVIMENTO)

	def test_tarefa_apagada_e_recriada_no_proximo_save(self):
		doc = self._nova()
		doc.responsavel = self.dev
		doc.save(ignore_permissions=True)
		doc.reload()

		frappe.delete_doc("Gestao de Tarefas", doc.tarefa, force=True, ignore_permissions=True)
		doc.reload()
		doc.save(ignore_permissions=True)
		doc.reload()

		self.assertTrue(doc.tarefa)
		self.assertTrue(frappe.db.exists("Gestao de Tarefas", doc.tarefa))

	# ──────────────────── membros do quadro ────────────────────

	def test_desenvolvedor_entra_e_sai_do_quadro_pelo_role(self):
		sincronizar_desenvolvedores_no_board()
		membros = {linha.user for linha in frappe.get_doc("Board", self.board).usuarios_autorizados or []}
		self.assertIn(self.dev, membros)
		self.assertNotIn(self.nao_dev, membros)

		user = frappe.get_doc("User", self.dev)
		user.set("roles", [])
		user.save(ignore_permissions=True)

		membros = {linha.user for linha in frappe.get_doc("Board", self.board).usuarios_autorizados or []}
		self.assertNotIn(self.dev, membros)
