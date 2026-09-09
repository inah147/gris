"""Registro das mensagens enviadas e a leitura que a ficha de registro faz dele.

O log existe porque não havia registro nenhum de envio: ``Configuracoes WhatsApp`` guarda só
o último envio e o último erro, globais. Sem ele, "quais mensagens este jovem já recebeu?"
não tinha resposta.
"""

from unittest import TestCase
from unittest.mock import patch

import frappe
from frappe.tests.utils import FrappeTestCase

from gris.utils import whatsapp
from gris.www.recepcao import ficha_registro

CONFIG_FALSA = {"nome_instancia": "instancia", "api_key": "chave", "base_url": "http://exemplo"}


class TestRegistrarLog(TestCase):
	"""``_registrar_log`` monta a linha; o insert é observado pelo dublê de ``get_doc``."""

	def _registrar(self, **kwargs):
		with (
			patch.object(whatsapp.frappe, "get_doc") as get_doc,
			patch.object(whatsapp, "listar_grupos_whatsapp", return_value=[]),
		):
			whatsapp._registrar_log(**kwargs)
		return get_doc.call_args[0][0] if get_doc.call_args else None

	def test_grava_o_que_a_ficha_mostra(self):
		linha = self._registrar(
			contexto={
				"assunto": "Lembrete de ficha médica",
				"destinatario_tipo": "Responsável",
				"novo_associado": "NA-1",
				"destinatario_nome": "Maria",
			},
			numero="5511999998888",
			conteudo="Preencha a ficha médica.",
			status="Enviada",
		)

		self.assertEqual(linha["doctype"], "Log de Mensagem")
		self.assertEqual(linha["status"], "Enviada")
		self.assertEqual(linha["assunto"], "Lembrete de ficha médica")
		self.assertEqual(linha["destinatario_tipo"], "Responsável")
		self.assertEqual(linha["destinatario_nome"], "Maria")
		self.assertEqual(linha["destinatario_numero"], "5511999998888")
		self.assertEqual(linha["novo_associado"], "NA-1")
		self.assertEqual(linha["conteudo"], "Preencha a ficha médica.")

	def test_sem_contexto_ainda_registra_numero_texto_e_status(self):
		"""Nem todo envio do GRIS nasce no funil; a linha não pode se perder por isso."""
		linha = self._registrar(numero="5511999998888", conteudo="Oi", status="Enviada", contexto=None)

		self.assertEqual(linha["destinatario_tipo"], whatsapp.TIPO_NAO_IDENTIFICADO)
		self.assertIsNone(linha["novo_associado"])
		self.assertEqual(linha["conteudo"], "Oi")

	def test_falha_guarda_o_erro(self):
		linha = self._registrar(
			contexto=None,
			numero="5511999998888",
			conteudo="Oi",
			status="Falhou",
			erro="timeout na Evolution API",
		)

		self.assertEqual(linha["status"], "Falhou")
		self.assertEqual(linha["erro"], "timeout na Evolution API")

	def test_envio_para_grupo_nao_consulta_a_evolution(self):
		"""O nome do grupo é resolvido na leitura: no envio seria uma chamada de rede por mensagem."""
		with (
			patch.object(whatsapp.frappe, "get_doc") as get_doc,
			patch.object(whatsapp, "listar_grupos_whatsapp") as listar,
		):
			whatsapp._registrar_log(
				{"assunto": "Acolhida", "destinatario_tipo": "Grupo de chefes de seção"},
				numero="123@g.us",
				conteudo="Aviso",
				status="Enviada",
			)

		listar.assert_not_called()
		self.assertEqual(get_doc.call_args[0][0]["destinatario_numero"], "123@g.us")

	def test_falha_do_log_nao_derruba_o_envio(self):
		"""A mensagem já foi (ou não foi) entregue: perder o registro é o mal menor."""
		with (
			patch.object(whatsapp.frappe, "get_doc", side_effect=RuntimeError("banco fora")),
			patch.object(whatsapp, "_logger"),
		):
			whatsapp._registrar_log(None, numero="5511999998888", conteudo="Oi", status="Enviada")


class TestEnvioRegistraLog(TestCase):
	"""O log é escrito nos dois desfechos do envio, e não só no caminho feliz."""

	def test_sucesso_registra_enviada(self):
		with (
			patch.object(whatsapp, "_get_config", return_value=CONFIG_FALSA),
			patch.object(whatsapp, "_post", return_value={"key": {"id": "X"}}),
			patch.object(whatsapp, "_registrar_sucesso"),
			patch.object(whatsapp, "_logger"),
			patch.object(whatsapp, "_registrar_log") as registrar,
		):
			whatsapp._enviar_texto_sync("5511999998888", "Oi", contexto={"assunto": "Teste"})

		self.assertEqual(registrar.call_args.kwargs["status"], "Enviada")
		self.assertEqual(registrar.call_args[0][0], {"assunto": "Teste"})

	def test_falha_registra_falhou_com_o_erro(self):
		with (
			patch.object(whatsapp, "_get_config", return_value=CONFIG_FALSA),
			patch.object(whatsapp, "_post", side_effect=RuntimeError("timeout")),
			patch.object(whatsapp, "_registrar_erro"),
			patch.object(whatsapp, "_logger"),
			patch.object(whatsapp, "_registrar_log") as registrar,
		):
			with self.assertRaises(RuntimeError):
				whatsapp._enviar_texto_sync("5511999998888", "Oi")

		self.assertEqual(registrar.call_args.kwargs["status"], "Falhou")
		self.assertIn("timeout", registrar.call_args.kwargs["erro"])

	def test_grupo_registra_o_jid_como_numero(self):
		with (
			patch.object(whatsapp, "_get_config", return_value=CONFIG_FALSA),
			patch.object(whatsapp, "_post", return_value={}),
			patch.object(whatsapp, "_registrar_sucesso"),
			patch.object(whatsapp, "_logger"),
			patch.object(whatsapp, "_registrar_log") as registrar,
		):
			whatsapp._enviar_para_grupo_sync("123@g.us", "Aviso")

		self.assertEqual(registrar.call_args.kwargs["numero"], "123@g.us")

	def test_contexto_atravessa_a_fila(self):
		"""O envio real roda num job; sem isto o contexto se perderia no enqueue."""
		with patch.object(whatsapp.frappe, "enqueue") as enfileirar:
			whatsapp.enviar_texto("5511999998888", "Oi", contexto={"assunto": "Teste"})

		self.assertEqual(enfileirar.call_args.kwargs["contexto"], {"assunto": "Teste"})


class TestListarMensagensEnviadas(FrappeTestCase):
	def tearDown(self):
		frappe.db.rollback()

	def _criar_jovem(self, cpf="529.982.247-25"):
		doc = frappe.get_doc(
			{
				"doctype": "Novo Associado",
				"nome_completo": "Jovem de Teste",
				"cpf": cpf,
				"data_de_nascimento": "2016-04-14",
				"status": "Conversa Inicial",
			}
		)
		doc.insert(ignore_permissions=True)
		return doc

	def _criar_log(self, jovem, **kwargs):
		doc = frappe.get_doc(
			{
				"doctype": "Log de Mensagem",
				"enviada_em": kwargs.pop("enviada_em", "2026-09-09 10:30:00"),
				"status": kwargs.pop("status", "Enviada"),
				"novo_associado": jovem,
				"conteudo": kwargs.pop("conteudo", "Mensagem"),
				**kwargs,
			}
		)
		doc.insert(ignore_permissions=True)
		return doc

	def test_traz_so_as_mensagens_do_jovem_pedido(self):
		jovem = self._criar_jovem()
		outro = self._criar_jovem(cpf="111.444.777-35")
		self._criar_log(jovem.name, conteudo="Do jovem")
		self._criar_log(outro.name, conteudo="Do outro")

		mensagens = ficha_registro.listar_mensagens_enviadas(jovem.name)

		self.assertEqual([m["conteudo"] for m in mensagens], ["Do jovem"])

	def test_separa_data_e_hora_para_a_tela(self):
		jovem = self._criar_jovem()
		self._criar_log(jovem.name, enviada_em="2026-09-09 10:30:00")

		mensagem = ficha_registro.listar_mensagens_enviadas(jovem.name)[0]

		self.assertEqual(mensagem["data"], "09/09/2026")
		self.assertEqual(mensagem["hora"], "10:30")

	def test_mais_recente_primeiro(self):
		jovem = self._criar_jovem()
		self._criar_log(jovem.name, enviada_em="2026-09-01 09:00:00", conteudo="Antiga")
		self._criar_log(jovem.name, enviada_em="2026-09-08 09:00:00", conteudo="Nova")

		mensagens = ficha_registro.listar_mensagens_enviadas(jovem.name)

		self.assertEqual([m["conteudo"] for m in mensagens], ["Nova", "Antiga"])

	def test_jovem_sem_mensagem_devolve_lista_vazia(self):
		jovem = self._criar_jovem()

		self.assertEqual(ficha_registro.listar_mensagens_enviadas(jovem.name), [])

	def test_sem_jovem_informado_e_recusado(self):
		with self.assertRaises(frappe.ValidationError):
			ficha_registro.listar_mensagens_enviadas("")

	def test_exige_permissao_de_leitura_no_jovem(self):
		jovem = self._criar_jovem()
		with patch.object(ficha_registro.frappe, "has_permission", return_value=False):
			with self.assertRaises(frappe.PermissionError):
				ficha_registro.listar_mensagens_enviadas(jovem.name)

	def test_grupo_aparece_pelo_nome_e_nao_pelo_jid(self):
		jovem = self._criar_jovem()
		self._criar_log(jovem.name, destinatario_numero="123@g.us")

		with patch(
			"gris.utils.whatsapp.listar_grupos_whatsapp",
			return_value=[{"id": "123@g.us", "subject": "Chefes de Seção"}],
		):
			mensagem = ficha_registro.listar_mensagens_enviadas(jovem.name)[0]

		self.assertEqual(mensagem["destinatario_nome"], "Chefes de Seção")

	def test_evolution_fora_do_ar_deixa_o_jid_no_lugar_do_nome(self):
		jovem = self._criar_jovem()
		self._criar_log(jovem.name, destinatario_numero="123@g.us")

		with patch("gris.utils.whatsapp.listar_grupos_whatsapp", side_effect=RuntimeError("api fora")):
			mensagem = ficha_registro.listar_mensagens_enviadas(jovem.name)[0]

		self.assertEqual(mensagem["destinatario_nome"], "123@g.us")

	def test_mensagem_de_pessoa_nao_dispara_consulta_de_grupos(self):
		jovem = self._criar_jovem()
		self._criar_log(jovem.name, destinatario_numero="5511999998888", destinatario_nome="Maria")

		with patch("gris.utils.whatsapp.listar_grupos_whatsapp") as listar:
			ficha_registro.listar_mensagens_enviadas(jovem.name)

		listar.assert_not_called()

	def test_apagar_o_jovem_leva_o_log_junto(self):
		"""LGPD: o log guarda o texto das mensagens, com nome e telefone de quem recebeu."""
		jovem = self._criar_jovem()
		self._criar_log(jovem.name)

		frappe.delete_doc("Novo Associado", jovem.name, ignore_permissions=True, force=True)

		self.assertEqual(frappe.db.count("Log de Mensagem", {"novo_associado": jovem.name}), 0)
