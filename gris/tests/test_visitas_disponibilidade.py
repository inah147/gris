# Copyright (c) 2026, Grupo Escoteiro Professora Inah de Mello - 47/SP and contributors
# For license information, please see license.txt

"""Datas disponíveis para visita de novo associado.

A visita é sempre num sábado dos próximos 60 dias. Um sábado fica bloqueado quando há
atividade no Calendario cobrindo o dia cuja seção pertence ao ramo pretendido — a não ser
que a atividade libere a visitação, por ``abertura_geral`` (o dia inteiro, todos os ramos)
ou por ``permite_visita_novos_associados`` (só o ramo da seção daquela atividade).

A decisão é **por linha** de Calendario, não por dia: liberar a atividade da Alcateia não
libera o sábado para quem é do ramo Escoteiro.

Os testes criam o calendário que precisam e limpam o dia antes, porque o site de
desenvolvimento tem calendário semeado que bloquearia os sábados escolhidos.
"""

from itertools import count
from unittest.mock import patch

import frappe
from frappe.tests.utils import FrappeTestCase
from frappe.utils import add_days, getdate, today

from gris.api import recepcao_disponibilidade as disponibilidade
from gris.www.recepcao import agenda_visitas
from gris.www.responsavel import beneficiarios

_seq = count(1)

# Ramo inventado: não existe Associado com ele, então `secoes_dos_ramos` devolve só o
# próprio nome e nenhuma atividade semeada do site interfere na regra sob teste.
RAMO_ISOLADO = "RamoDeTeste"
OUTRO_RAMO_ISOLADO = "OutroRamoDeTeste"


def _gerar_cpf(base9: str) -> str:
	digitos = [int(d) for d in base9]
	primeiro = (sum(d * (10 - i) for i, d in enumerate(digitos)) * 10 % 11) % 10
	digitos.append(primeiro)
	segundo = (sum(d * (11 - i) for i, d in enumerate(digitos)) * 10 % 11) % 10
	return f"{base9[:3]}.{base9[3:6]}.{base9[6:9]}-{primeiro}{segundo}"


def _proximo_sabado(semanas: int = 0):
	"""Sábado contado a partir de hoje, para a data não apodrecer com o tempo.

	A janela é relativa a ``today()`` e só sábados entram: qualquer data literal sairia da
	janela em poucos meses, ou deixaria de cair num sábado.
	"""
	hoje = getdate(today())
	dias = (5 - hoje.weekday()) % 7 or 7
	return add_days(hoje, dias + 7 * semanas)


class _BaseDeDisponibilidade(FrappeTestCase):
	def setUp(self):
		# Salvar Calendario e Agenda de Visitas dispara WhatsApp; aqui só interessa a regra.
		for alvo in (
			"gris.api.calendario_notificacoes.notificar_alteracao_calendario",
			"gris.api.recepcao_notificacoes.notificar_visita_agendada",
			"gris.api.recepcao_mensagens.on_novo_associado_atualizado",
		):
			patcher = patch(alvo)
			self.addCleanup(patcher.stop)
			patcher.start()

	def tearDown(self):
		# FrappeTestCase faz rollback por classe: sem isto o `id` do Calendario e o CPF do
		# jovem vazam para o próximo teste e viram DuplicateEntryError.
		frappe.db.rollback()

	def _sabado_limpo(self, semanas: int = 0):
		"""Sábado dentro da janela, garantidamente sem atividade nenhuma."""
		dia = _proximo_sabado(semanas)
		nomes = frappe.get_all(
			"Calendario",
			filters={"inicio": ["<=", f"{dia} 23:59:59"], "termino": [">=", f"{dia} 00:00:00"]},
			pluck="name",
		)
		if nomes:
			frappe.db.delete("Calendario", {"name": ["in", nomes]})
		return dia

	def _criar_atividade(self, secao, dia, termino=None, **flags):
		doc = frappe.get_doc(
			{
				"doctype": "Calendario",
				"id": f"TST-DISP-{next(_seq):04d}",
				"atividade": flags.pop("atividade", "Atividade de teste"),
				"secao": secao,
				"inicio": f"{dia} 08:00:00",
				"termino": f"{termino or dia} 18:00:00",
				**flags,
			}
		)
		doc.insert(ignore_permissions=True)
		return doc

	def _criar_jovem(self, ramo="Lobinho", base_cpf=None):
		base_cpf = base_cpf or f"{next(_seq):09d}"
		doc = frappe.get_doc(
			{
				"doctype": "Novo Associado",
				"nome_completo": "Jovem de Teste",
				"cpf": _gerar_cpf(base_cpf),
				"data_de_nascimento": "2016-04-14",
				"status": "Conversa Inicial",
				"ramo": ramo,
			}
		)
		doc.insert(ignore_permissions=True)
		# O before_insert deriva o ramo da data de nascimento; o teste precisa do ramo que pediu.
		if doc.ramo != ramo:
			frappe.db.set_value("Novo Associado", doc.name, "ramo", ramo)
			doc.reload()
		return doc


class TestDisponibilidadeDeDatasParaVisita(_BaseDeDisponibilidade):
	def test_sabado_sem_atividade_esta_disponivel(self):
		sabado = self._sabado_limpo()

		self.assertIn(sabado, disponibilidade.datas_disponiveis_para_ramo(RAMO_ISOLADO))
		self.assertTrue(disponibilidade.data_disponivel_para_ramo(RAMO_ISOLADO, sabado))

	def test_sabado_com_atividade_do_ramo_fica_bloqueado(self):
		sabado = self._sabado_limpo()
		self._criar_atividade(RAMO_ISOLADO, sabado)

		self.assertNotIn(sabado, disponibilidade.datas_disponiveis_para_ramo(RAMO_ISOLADO))
		self.assertFalse(disponibilidade.data_disponivel_para_ramo(RAMO_ISOLADO, sabado))

	def test_flag_de_visitacao_libera_o_sabado_com_atividade(self):
		sabado = self._sabado_limpo()
		self._criar_atividade(RAMO_ISOLADO, sabado, permite_visita_novos_associados=1)

		self.assertIn(sabado, disponibilidade.datas_disponiveis_para_ramo(RAMO_ISOLADO))
		self.assertTrue(disponibilidade.data_disponivel_para_ramo(RAMO_ISOLADO, sabado))

	def test_abertura_geral_continua_liberando_o_sabado(self):
		sabado = self._sabado_limpo()
		self._criar_atividade(RAMO_ISOLADO, sabado, abertura_geral=1)

		self.assertIn(sabado, disponibilidade.datas_disponiveis_para_ramo(RAMO_ISOLADO))

	def test_flag_liberado_em_um_ramo_nao_libera_o_outro(self):
		# A liberação é da atividade, não do dia: no mesmo sábado, um ramo recebe visita e
		# o outro continua bloqueado.
		sabado = self._sabado_limpo()
		self._criar_atividade(RAMO_ISOLADO, sabado, permite_visita_novos_associados=1)
		self._criar_atividade(OUTRO_RAMO_ISOLADO, sabado)

		self.assertTrue(disponibilidade.data_disponivel_para_ramo(RAMO_ISOLADO, sabado))
		self.assertFalse(disponibilidade.data_disponivel_para_ramo(OUTRO_RAMO_ISOLADO, sabado))

	def test_atividade_de_varios_dias_com_flag_libera_os_sabados_cobertos(self):
		primeiro = self._sabado_limpo()
		segundo = self._sabado_limpo(semanas=1)
		self._criar_atividade(RAMO_ISOLADO, primeiro, termino=segundo, permite_visita_novos_associados=1)

		disponiveis = disponibilidade.datas_disponiveis_para_ramo(RAMO_ISOLADO)

		self.assertIn(primeiro, disponiveis)
		self.assertIn(segundo, disponiveis)

	def test_atividade_de_varios_dias_sem_flag_bloqueia_os_sabados_cobertos(self):
		primeiro = self._sabado_limpo()
		segundo = self._sabado_limpo(semanas=1)
		self._criar_atividade(RAMO_ISOLADO, primeiro, termino=segundo)

		disponiveis = disponibilidade.datas_disponiveis_para_ramo(RAMO_ISOLADO)

		self.assertNotIn(primeiro, disponiveis)
		self.assertNotIn(segundo, disponiveis)

	def test_secao_mapeada_pelo_associado_respeita_o_flag(self):
		# O Calendario guarda o nome real da seção ("Alcateia"), o jovem tem o ramo
		# ("Lobinho"): a ponte é feita pelos Associados já cadastrados.
		secao = "SecaoDeTeste"
		associado = frappe.get_doc(
			{
				"doctype": "Associado",
				"nome_completo": "Associado de Teste",
				"data_de_nascimento": "2010-01-01",
				"cpf": _gerar_cpf(f"{next(_seq):09d}"),
				"ramo": "Lobinho",
				"secao": secao,
			}
		)
		associado.insert(ignore_permissions=True)

		sabado = self._sabado_limpo()
		atividade = self._criar_atividade(secao, sabado)

		self.assertFalse(disponibilidade.data_disponivel_para_ramo("Lobinho", sabado))

		atividade.permite_visita_novos_associados = 1
		atividade.save(ignore_permissions=True)

		self.assertTrue(disponibilidade.data_disponivel_para_ramo("Lobinho", sabado))

	def test_dia_que_nao_e_sabado_nunca_esta_disponivel(self):
		sabado = self._sabado_limpo()
		sexta = add_days(sabado, -1)

		self.assertFalse(disponibilidade.data_disponivel_para_ramo(RAMO_ISOLADO, sexta))

	def test_sabado_fora_da_janela_de_60_dias_nao_entra(self):
		distante = _proximo_sabado(semanas=10)

		self.assertGreater((distante - getdate(today())).days, disponibilidade.JANELA_EM_DIAS)
		self.assertNotIn(distante, disponibilidade.datas_disponiveis_para_ramo(RAMO_ISOLADO))
		self.assertFalse(disponibilidade.data_disponivel_para_ramo(RAMO_ISOLADO, distante))

	def test_sem_ramo_nao_ha_data_disponivel(self):
		sabado = self._sabado_limpo()

		self.assertFalse(disponibilidade.data_disponivel_para_ramo(None, sabado))


class TestValidacaoNoAgendamentoDaRecepcao(_BaseDeDisponibilidade):
	def test_o_select_da_recepcao_sai_do_mesmo_calculo(self):
		sabado = self._sabado_limpo()
		self._criar_atividade("Lobinho", sabado, permite_visita_novos_associados=1)

		valores = {item["value"] for item in agenda_visitas._get_available_dates("Lobinho")}

		self.assertIn(sabado.strftime("%Y-%m-%d"), valores)

	def test_agendar_em_dia_liberado_pelo_flag_e_aceito(self):
		sabado = self._sabado_limpo()
		self._criar_atividade("Lobinho", sabado, permite_visita_novos_associados=1)
		jovem = self._criar_jovem()

		agenda_visitas.schedule_visit(jovem.name, sabado.strftime("%Y-%m-%d"))

		visita = frappe.get_all("Agenda de Visitas", filters={"jovem": jovem.name}, fields=["data_da_visita"])
		self.assertEqual(len(visita), 1)
		self.assertEqual(getdate(visita[0].data_da_visita), sabado)

	def test_agendar_em_dia_bloqueado_continua_recusado(self):
		sabado = self._sabado_limpo()
		self._criar_atividade("Lobinho", sabado)
		jovem = self._criar_jovem()

		with self.assertRaises(frappe.ValidationError):
			agenda_visitas.schedule_visit(jovem.name, sabado.strftime("%Y-%m-%d"))

	def test_remarcar_para_dia_liberado_pelo_flag_e_aceito(self):
		origem = self._sabado_limpo()
		destino = self._sabado_limpo(semanas=1)
		self._criar_atividade("Lobinho", destino, permite_visita_novos_associados=1)
		jovem = self._criar_jovem()
		agenda_visitas.schedule_visit(jovem.name, origem.strftime("%Y-%m-%d"))
		visita = frappe.get_all("Agenda de Visitas", filters={"jovem": jovem.name}, pluck="name")[0]

		agenda_visitas.reschedule_visit(visita, destino.strftime("%Y-%m-%d"))

		self.assertEqual(getdate(frappe.db.get_value("Agenda de Visitas", visita, "data_da_visita")), destino)


class TestValidacaoNoAgendamentoDoResponsavel(_BaseDeDisponibilidade):
	def _criar_responsavel_com_beneficiarios(self, *ramos):
		responsavel = frappe.get_doc(
			{
				"doctype": "Responsavel",
				"nome_completo": "Responsável de Teste",
				"email": f"resp-teste-{next(_seq)}@exemplo.test",
			}
		)
		responsavel.insert(ignore_permissions=True)

		jovens = []
		for ramo in ramos:
			jovem = self._criar_jovem(ramo=ramo)
			frappe.get_doc(
				{
					"doctype": "Responsavel Vinculo",
					"responsavel": responsavel.name,
					"beneficiario_novo_associado": jovem.name,
				}
			).insert(ignore_permissions=True)
			jovens.append(jovem)

		return responsavel, jovens

	def test_responsavel_ve_o_dia_liberado_pelo_flag(self):
		sabado = self._sabado_limpo()
		self._criar_atividade("Lobinho", sabado, permite_visita_novos_associados=1)
		responsavel, _ = self._criar_responsavel_com_beneficiarios("Lobinho")

		datas = beneficiarios._get_available_visit_dates_for_responsavel(responsavel.name)

		self.assertIn(sabado.strftime("%Y-%m-%d"), {item["value"] for item in datas})

	def test_responsavel_em_dia_bloqueado_continua_recusado(self):
		sabado = self._sabado_limpo()
		self._criar_atividade("Lobinho", sabado)
		responsavel, jovens = self._criar_responsavel_com_beneficiarios("Lobinho")

		datas = beneficiarios._get_available_visit_dates_for_responsavel(responsavel.name)
		self.assertNotIn(sabado.strftime("%Y-%m-%d"), {item["value"] for item in datas})

		with self.assertRaises(frappe.ValidationError):
			beneficiarios._marcar_visitas(jovens, sabado.strftime("%Y-%m-%d"))

	def test_dia_liberado_para_um_ramo_nao_entra_nas_opcoes_com_dois_ramos(self):
		# O select do responsável é único para todos os filhos, mas a gravação valida um por
		# um: oferecer a data bloqueada para um deles faria o submit recusar depois de
		# escolhida.
		sabado = self._sabado_limpo()
		self._criar_atividade("Lobinho", sabado, permite_visita_novos_associados=1)
		self._criar_atividade("Escoteiro", sabado)
		responsavel, _ = self._criar_responsavel_com_beneficiarios("Lobinho", "Escoteiro")

		datas = beneficiarios._get_available_visit_dates_for_responsavel(responsavel.name)

		self.assertNotIn(sabado.strftime("%Y-%m-%d"), {item["value"] for item in datas})

	def test_responsavel_agenda_em_dia_liberado_pelo_flag(self):
		sabado = self._sabado_limpo()
		self._criar_atividade("Lobinho", sabado, permite_visita_novos_associados=1)
		_, jovens = self._criar_responsavel_com_beneficiarios("Lobinho")

		beneficiarios._marcar_visitas(jovens, sabado.strftime("%Y-%m-%d"))

		self.assertEqual(
			getdate(frappe.db.get_value("Agenda de Visitas", {"jovem": jovens[0].name}, "data_da_visita")),
			sabado,
		)
