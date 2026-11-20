"""Régua de vencimento do registro: marcos, destinatário, chefes, resumo mensal e interruptores.

Spec: ``docs/specs/regua-vencimento-registro/spec.md``. Os nomes das classes seguem a matriz
de validação do plano (``plano.md``, seção 5).
"""

from __future__ import annotations

import datetime
from contextlib import ExitStack
from unittest.mock import patch

import frappe
from frappe.tests.utils import FrappeTestCase

from gris.api import associados_vencimento_modelos as modelos
from gris.api import associados_vencimento_notificacoes as regua

HOJE = datetime.date(2026, 11, 20)
CORTE = datetime.date(2026, 11, 1)


def _dia(delta: int) -> datetime.date:
	return HOJE + datetime.timedelta(days=delta)


def _associado(name="A1", *, dias=30, **campos) -> frappe._dict:
	base = {
		"name": name,
		"nome_completo": f"Pessoa {name} Exemplo",
		"sexo": "Feminino",
		"telefone": f"+551190000000{name[-1]}",
		"categoria": "Escotista",
		"data_de_nascimento": datetime.date(1990, 1, 1),
		"validade_registro": _dia(dias),
		"registro": "123",
		"secao": "",
		"ramo": "",
		"nome_responsavel_1": "",
		"telefone_responsavel_1": "",
		"regua_validade_referencia": None,
		"regua_ultimo_marco": None,
		"regua_ultimo_envio": None,
		"regua_chefe_ultimo_marco": None,
	}
	base.update(campos)
	return frappe._dict(base)


def _jovem(name="J1", *, dias=30, secao="Alcateia Exemplo", ramo="Lobinho", **campos) -> frappe._dict:
	dados = {
		"categoria": "Beneficiário",
		"data_de_nascimento": datetime.date(2016, 5, 5),
		"secao": secao,
		"ramo": ramo,
		**campos,
	}
	return _associado(name, dias=dias, **dados)


class _Ambiente:
	"""Roda ``executar_regua`` com banco, WhatsApp e configuração trocados por dublês."""

	def __init__(
		self,
		associados=(),
		*,
		config=None,
		interruptores=None,
		links=None,
		responsaveis=None,
		chefes=None,
		beneficiarios_do_mes=(),
		falhar_para=(),
		ativa=True,
	):
		self.associados = list(associados)
		self.config = {
			"cobrar_vencidos_desde": CORTE,
			"intervalo_recorrente_dias": 3,
			"grupo_chefes_whatsapp": "",
			"resumo_mensal_enviado_em": HOJE.strftime("%Y-%m"),
			**(config or {}),
		}
		self.interruptores = interruptores or {}
		self.links = links or {}
		self.responsaveis = responsaveis or {}
		self.chefes = chefes or {}
		self.beneficiarios_do_mes = list(beneficiarios_do_mes)
		self.falhar_para = set(falhar_para)
		self.ativa = ativa
		self.textos: list[dict] = []
		self.grupos: list[dict] = []
		self.gravacoes: list[tuple] = []
		self.singles: dict = {}
		self.resumos: list[str] = []
		self.filtros: list[dict] = []

	def _get_all(self, doctype, filters=None, fields=None, **_kwargs):
		self.filtros.append({"doctype": doctype, "filters": filters})
		if doctype == "Associado" and filters and filters.get("categoria") == "Beneficiário":
			return [dict(b) for b in self.beneficiarios_do_mes]
		return [dict(a) for a in self.associados]

	def _enviar_texto(self, numero, mensagem, *, enqueue=True, contexto=None):
		if numero in self.falhar_para:
			raise RuntimeError("Evolution fora do ar")
		self.textos.append({"numero": numero, "mensagem": mensagem, "contexto": contexto, "enqueue": enqueue})

	def _enviar_para_grupo(self, grupo, mensagem, *, mencionar=None, enqueue=True, contexto=None):
		self.grupos.append(
			{"grupo": grupo, "mensagem": mensagem, "mencionar": mencionar, "contexto": contexto}
		)

	def _set_value(self, doctype, name, valores, update_modified=True):
		self.gravacoes.append((doctype, name, dict(valores), update_modified))

	def _chefes(self, beneficiarios):
		return {b.get("name"): self.chefes.get(b.get("name"), []) for b in beneficiarios}

	def rodar(self, hoje=HOJE):
		alvo = "gris.api.associados_vencimento_notificacoes"
		with ExitStack() as pilha:
			pilha.enter_context(patch(f"{alvo}.regua_ativa", return_value=self.ativa))
			pilha.enter_context(patch(f"{alvo}._whatsapp_habilitado", return_value=True))
			pilha.enter_context(
				patch(f"{alvo}.interruptor_ligado", side_effect=lambda c: self.interruptores.get(c, True))
			)
			pilha.enter_context(
				patch.object(
					regua.frappe.db, "get_single_value", side_effect=lambda _d, c: self.config.get(c)
				)
			)
			pilha.enter_context(
				patch.object(
					regua.frappe.db,
					"set_single_value",
					side_effect=lambda _d, c, v=None: self.singles.__setitem__(c, v),
				)
			)
			pilha.enter_context(patch.object(regua.frappe.db, "set_value", side_effect=self._set_value))
			pilha.enter_context(patch.object(regua.frappe, "get_all", side_effect=self._get_all))
			pilha.enter_context(patch.object(regua.frappe, "log_error"))
			pilha.enter_context(patch(f"{alvo}._commit"))
			pilha.enter_context(patch(f"{alvo}.metrica"))
			pilha.enter_context(patch(f"{alvo}.definir_resumo", side_effect=self.resumos.append))
			pilha.enter_context(patch(f"{alvo}.enviar_texto", side_effect=self._enviar_texto))
			pilha.enter_context(patch(f"{alvo}.enviar_para_grupo", side_effect=self._enviar_para_grupo))
			pilha.enter_context(
				patch(f"{alvo}._buscar_links_responsavel", side_effect=lambda nomes: self.links)
			)
			pilha.enter_context(
				patch(f"{alvo}._buscar_contatos_responsavel", side_effect=lambda _l: self.responsaveis)
			)
			pilha.enter_context(patch(f"{alvo}.contatos_chefes_dos_beneficiarios", side_effect=self._chefes))
			pilha.enter_context(patch(f"{alvo}.contato_duvidas", return_value=""))
			pilha.enter_context(patch(f"{alvo}.instrucoes_renovacao", return_value="Renove pelo Paxtu."))
			pilha.enter_context(patch.object(modelos, "_valor_do_single", return_value=""))
			return regua.executar_regua(hoje)

	def gravacoes_de(self, name):
		return [valores for _dt, n, valores, _um in self.gravacoes if n == name]


# ─── Funções puras ────────────────────────────────────────────────────────────


class TestMarcoDevido(FrappeTestCase):
	def _marco(self, dias, ultimo=None, ultimo_envio=None, corte=CORTE, intervalo=3, validade=None):
		return regua.marco_devido(
			dias=dias,
			ultimo_marco=ultimo,
			ultimo_envio=ultimo_envio,
			hoje=HOJE,
			validade=validade or _dia(dias),
			corte=corte,
			intervalo=intervalo,
		)

	def test_janelas_de_cada_marco(self):
		casos = {
			31: None,
			30: "30",
			25: "30",
			8: "30",
			7: "7",
			2: "7",
			1: "1",
			0: "0",
			-1: None,
			-2: None,
			-3: "recorrente",
			-10: "recorrente",
		}
		for dias, esperado in casos.items():
			with self.subTest(dias=dias):
				self.assertEqual(self._marco(dias), esperado)

	def test_cada_marco_sai_uma_vez(self):
		self.assertIsNone(self._marco(25, ultimo="30"))
		self.assertIsNone(self._marco(5, ultimo="7"))
		self.assertIsNone(self._marco(0, ultimo="0"))

	def test_marco_perdido_manda_so_o_mais_recente(self):
		# Validade importada já a 5 dias: sai o de 7 dias, nunca o de 30 atrasado.
		self.assertEqual(self._marco(5, ultimo=None), "7")
		# Pulou o de 1 dia (job parado): o "no dia" ainda sai.
		self.assertEqual(self._marco(0, ultimo="7"), "0")

	def test_marco_anterior_nao_volta(self):
		self.assertIsNone(self._marco(20, ultimo="7"))

	def test_recorrente_a_cada_intervalo(self):
		self.assertEqual(self._marco(-3, ultimo="0", ultimo_envio=_dia(-3)), "recorrente")
		self.assertIsNone(self._marco(-5, ultimo="recorrente", ultimo_envio=_dia(-2)))
		self.assertEqual(self._marco(-6, ultimo="recorrente", ultimo_envio=_dia(-3)), "recorrente")
		self.assertEqual(
			self._marco(-10, ultimo="recorrente", ultimo_envio=_dia(-5), intervalo=5), "recorrente"
		)
		self.assertIsNone(self._marco(-4, ultimo="0", intervalo=5))

	def test_corte(self):
		antes_do_corte = CORTE - datetime.timedelta(days=1)
		dias = (antes_do_corte - HOJE).days
		self.assertIsNone(self._marco(dias, validade=antes_do_corte))
		self.assertEqual(self._marco(dias, validade=antes_do_corte, corte=None), "recorrente")
		self.assertEqual(self._marco(-3, validade=_dia(-3)), "recorrente")

	def test_validade_nova_recomeca(self):
		associado = _associado(
			dias=30,
			regua_validade_referencia=_dia(-400),
			regua_ultimo_marco="recorrente",
			regua_ultimo_envio=_dia(-1),
			regua_chefe_ultimo_marco="pos",
		)
		estado = regua.estado_vigente(associado)
		self.assertIsNone(estado.ultimo_marco)
		self.assertIsNone(estado.chefe_ultimo_marco)
		self.assertTrue(estado.recomecou)
		self.assertEqual(self._marco(30, ultimo=estado.ultimo_marco), "30")
		valores = estado.carimbar(regua_ultimo_marco="30")
		self.assertIsNone(valores["regua_chefe_ultimo_marco"])
		self.assertEqual(valores["regua_validade_referencia"], _dia(30))
		# Só a primeira gravação depois da troca zera os outros carimbos.
		self.assertNotIn("regua_ultimo_marco", estado.carimbar(regua_chefe_ultimo_marco="30"))

	def test_mais_de_30_dias(self):
		self.assertIsNone(self._marco(31))
		self.assertIsNone(self._marco(365))


class TestMarcoDoChefe(FrappeTestCase):
	def _marco(self, dias, ultimo=None, corte=CORTE, validade=None):
		return regua.marco_do_chefe(
			dias=dias, ultimo_marco=ultimo, validade=validade or _dia(dias), corte=corte
		)

	def test_janelas(self):
		casos = {31: None, 30: "30", 8: "30", 7: "7", 1: "7", 0: None, -1: "pos", -15: "pos"}
		for dias, esperado in casos.items():
			with self.subTest(dias=dias):
				self.assertEqual(self._marco(dias), esperado)

	def test_uma_vez_por_validade(self):
		self.assertIsNone(self._marco(20, ultimo="30"))
		self.assertEqual(self._marco(6, ultimo="30"), "7")
		self.assertIsNone(self._marco(-2, ultimo="pos"))

	def test_corte(self):
		antes_do_corte = CORTE - datetime.timedelta(days=10)
		self.assertIsNone(self._marco((antes_do_corte - HOJE).days, validade=antes_do_corte))


class TestDestinatario(FrappeTestCase):
	def test_adulto_recebe_no_proprio_telefone(self):
		destinatario = regua.resolver_destinatario(_associado(), {}, {}, HOJE)
		self.assertEqual(destinatario.telefone, "+5511900000001")
		self.assertEqual(destinatario.tipo, regua.DESTINATARIO_ASSOCIADO)

	def test_adulto_sem_telefone(self):
		self.assertIsNone(regua.resolver_destinatario(_associado(telefone=""), {}, {}, HOJE))

	def test_menor_com_guardiao_legal_tem_prioridade(self):
		jovem = _jovem()
		links = {
			"J1": [
				frappe._dict(responsavel="R1", é_guardiao_legal=0, primeiro_responsavel=1),
				frappe._dict(responsavel="R2", é_guardiao_legal=1, primeiro_responsavel=0),
			]
		}
		contatos = {
			"R1": frappe._dict(nome_completo="Primeiro Resp", celular="+5511911111111"),
			"R2": frappe._dict(nome_completo="Guardiã Legal", celular="+5511922222222"),
		}
		destinatario = regua.resolver_destinatario(jovem, links, contatos, HOJE)
		self.assertEqual(destinatario.telefone, "+5511922222222")
		self.assertEqual(destinatario.tipo, regua.DESTINATARIO_RESPONSAVEL)

	def test_menor_sem_vinculo_usa_responsavel_do_cadastro(self):
		jovem = _jovem(nome_responsavel_1="Mãe Exemplo", telefone_responsavel_1="+5511933333333")
		destinatario = regua.resolver_destinatario(jovem, {}, {}, HOJE)
		self.assertEqual(destinatario.telefone, "+5511933333333")
		self.assertEqual(destinatario.nome, "Mãe Exemplo")

	def test_menor_sem_responsavel_cai_no_proprio_telefone(self):
		destinatario = regua.resolver_destinatario(_jovem(), {}, {}, HOJE)
		self.assertEqual(destinatario.tipo, regua.DESTINATARIO_ASSOCIADO)

	def test_beneficiario_sem_data_de_nascimento_conta_como_menor(self):
		self.assertTrue(regua.eh_menor(_jovem(data_de_nascimento=None), HOJE))
		self.assertFalse(regua.eh_menor(_associado(data_de_nascimento=None), HOJE))

	def test_dezoito_anos_completos_e_adulto(self):
		self.assertFalse(regua.eh_menor(_associado(data_de_nascimento=datetime.date(2008, 11, 20)), HOJE))
		self.assertTrue(regua.eh_menor(_associado(data_de_nascimento=datetime.date(2008, 11, 21)), HOJE))

	def test_primeiro_nome_ignora_tratamento(self):
		self.assertEqual(regua._primeiro_nome("Dr. Cauã Cardoso"), "Cauã")
		self.assertEqual(regua._primeiro_nome("Sra. Maria Flor"), "Maria")
		self.assertEqual(regua._primeiro_nome("Ana"), "Ana")
		self.assertEqual(regua._primeiro_nome(""), "")

	def test_registro_de_conforme_destinatario(self):
		comum = {"como_renovar": "", "contato_duvidas": ""}
		adulto = regua.valores_do_associado(
			_associado(), frappe._dict(tipo=regua.DESTINATARIO_ASSOCIADO, nome="x"), dias=7, comum=comum
		)
		self.assertEqual(adulto["registro_de"], "seu registro escoteiro")
		menor = regua.valores_do_associado(
			_jovem(nome_completo="Ana Souza"),
			frappe._dict(tipo=regua.DESTINATARIO_RESPONSAVEL, nome="Mariana Souza"),
			dias=7,
			comum=comum,
		)
		self.assertEqual(menor["registro_de"], "o registro escoteiro de Ana")
		self.assertEqual(menor["primeiro_nome_destinatario"], "Mariana")


# ─── Rodada do job ────────────────────────────────────────────────────────────


class TestReguaDoAssociado(FrappeTestCase):
	def test_geral_desligado_nao_envia_nada(self):
		ambiente = _Ambiente([_associado(dias=30)], ativa=False)
		resultado = ambiente.rodar()
		self.assertFalse(resultado["executado"])
		self.assertEqual(ambiente.textos, [])
		self.assertEqual(ambiente.gravacoes, [])
		self.assertEqual(ambiente.resumos, [regua.REGUA_DESLIGADA])

	def test_agendamento_desligado_nao_enfileira(self):
		with (
			patch.object(regua, "regua_ativa", return_value=False),
			patch.object(regua.frappe, "enqueue") as enqueue,
			patch.object(regua, "definir_resumo") as resumo,
		):
			regua.enviar_lembretes_vencimento_registro_associados()
		enqueue.assert_not_called()
		resumo.assert_called_once_with(regua.REGUA_DESLIGADA)

	def test_agendamento_ligado_vai_para_a_fila_longa(self):
		with (
			patch.object(regua, "regua_ativa", return_value=True),
			patch.object(regua.frappe, "enqueue") as enqueue,
			patch.object(regua, "definir_resumo"),
		):
			regua.enviar_lembretes_vencimento_registro_associados()
		self.assertEqual(enqueue.call_args.kwargs["queue"], "long")

	def test_envia_o_marco_e_carimba_depois(self):
		ambiente = _Ambiente([_associado(dias=30)])
		ambiente.rodar()
		self.assertEqual(len(ambiente.textos), 1)
		texto = ambiente.textos[0]
		self.assertFalse(texto["enqueue"])
		self.assertIn("seu registro escoteiro vence em *20/12/2026*", texto["mensagem"])
		self.assertIn("daqui a 30 dias", texto["mensagem"])
		self.assertEqual(
			ambiente.gravacoes_de("A1"),
			[
				{
					"regua_validade_referencia": _dia(30),
					"regua_ultimo_marco": "30",
					"regua_ultimo_envio": HOJE,
				}
			],
		)
		self.assertFalse(ambiente.gravacoes[0][3], "carimbo não pode mexer no modified")

	def test_falha_no_envio_nao_carimba(self):
		ambiente = _Ambiente([_associado(dias=7)], falhar_para={"+5511900000001"})
		ambiente.rodar()
		self.assertEqual(ambiente.gravacoes, [])

	def test_segunda_rodada_no_dia_nao_reenvia(self):
		associado = _associado(dias=7)
		ambiente = _Ambiente([associado])
		ambiente.rodar()
		associado.update(ambiente.gravacoes_de("A1")[0])
		segunda = _Ambiente([associado])
		segunda.rodar()
		self.assertEqual(segunda.textos, [])

	def test_interruptor_do_marco_suspende_so_o_marco(self):
		ambiente = _Ambiente(
			[_associado("A1", dias=30), _associado("A2", dias=7)],
			interruptores={"msg_venc_30": False},
		)
		ambiente.rodar()
		self.assertEqual([t["numero"] for t in ambiente.textos], ["+5511900000002"])
		self.assertEqual(ambiente.gravacoes_de("A1"), [])

	def test_interruptor_ausente_conta_como_ligado(self):
		with patch.object(modelos, "valor_bruto", return_value=None):
			self.assertTrue(modelos.interruptor_ligado("msg_venc_30"))
			self.assertFalse(modelos.regua_ativa())
		with patch.object(modelos, "valor_bruto", return_value="0"):
			self.assertFalse(modelos.interruptor_ligado("msg_venc_30"))
		with patch.object(modelos, "valor_bruto", return_value="1"):
			self.assertTrue(modelos.interruptor_ligado("msg_venc_30"))
			self.assertTrue(modelos.regua_ativa())

	def test_sem_telefone_pula_sem_carimbar(self):
		ambiente = _Ambiente([_associado(dias=1, telefone="")])
		ambiente.rodar()
		self.assertEqual(ambiente.textos, [])
		self.assertEqual(ambiente.gravacoes, [])

	def test_consulta_so_ativos_e_na_janela(self):
		ambiente = _Ambiente([])
		ambiente.rodar()
		filtros = ambiente.filtros[0]["filters"]
		self.assertEqual(filtros["status_no_grupo"], "Ativo")
		self.assertEqual(filtros["validade_registro"], ["between", [CORTE, _dia(30)]])

	def test_contexto_do_log(self):
		jovem = _jovem(nome_responsavel_1="Mãe Exemplo", telefone_responsavel_1="+5511933333333", dias=0)
		ambiente = _Ambiente([jovem])
		ambiente.rodar()
		contexto = ambiente.textos[0]["contexto"]
		self.assertEqual(contexto["associado"], "J1")
		self.assertEqual(contexto["destinatario_tipo"], regua.DESTINATARIO_RESPONSAVEL)
		self.assertEqual(contexto["assunto"], "Vencimento do registro: no dia")

	def test_toda_mensagem_tem_o_rodape(self):
		ambiente = _Ambiente([_associado(f"A{i}", dias=d) for i, d in enumerate((30, 7, 1, 0, -3), 1)])
		ambiente.rodar()
		self.assertEqual(len(ambiente.textos), 5)
		for texto in ambiente.textos:
			mensagem = texto["mensagem"]
			self.assertIn(modelos.TEXTO_JA_RENOVADO_PADRAO, mensagem)
			self.assertTrue(mensagem.endswith(modelos.ASSINATURA_AUTOMATICA))

	def test_resumo_do_job(self):
		ambiente = _Ambiente([_associado(dias=30)])
		ambiente.rodar()
		self.assertIn("1 aviso(s) a associados/responsáveis", ambiente.resumos[-1])


class TestAvisoAosChefes(FrappeTestCase):
	CHEFE = frappe._dict(name="C1", nome_completo="Rafael Chefe", telefone="+5511977777777")
	CHEFE_2 = frappe._dict(name="C2", nome_completo="Paula Chefe", telefone="+5511966666666")

	def _textos_do_chefe(self, ambiente, telefone):
		return [t for t in ambiente.textos if t["numero"] == telefone]

	def test_uma_mensagem_por_chefe_com_um_bloco_por_marco(self):
		jovens = [_jovem("J1", dias=30), _jovem("J2", dias=7), _jovem("J3", dias=-1)]
		ambiente = _Ambiente(jovens, chefes={j.name: [self.CHEFE] for j in jovens})
		ambiente.rodar()
		do_chefe = self._textos_do_chefe(ambiente, self.CHEFE.telefone)
		self.assertEqual(len(do_chefe), 1)
		mensagem = do_chefe[0]["mensagem"]
		self.assertTrue(mensagem.startswith("Olá, Rafael!"))
		posicoes = [
			mensagem.index("cerca de 30 dias"),
			mensagem.index("próxima semana"),
			mensagem.index("registros vencidos"),
		]
		self.assertEqual(posicoes, sorted(posicoes))
		self.assertIn("• Pessoa J3 Exemplo (Lobinho) — venceu em 19/11/2026", mensagem)
		self.assertIn("não podem participar das atividades", mensagem)
		self.assertTrue(mensagem.endswith(modelos.ASSINATURA_AUTOMATICA))
		self.assertEqual(do_chefe[0]["contexto"]["destinatario_tipo"], regua.DESTINATARIO_CHEFE)

	def test_dois_chefes_recebem(self):
		ambiente = _Ambiente([_jovem(dias=7)], chefes={"J1": [self.CHEFE, self.CHEFE_2]})
		ambiente.rodar()
		self.assertEqual(len(self._textos_do_chefe(ambiente, self.CHEFE.telefone)), 1)
		self.assertEqual(len(self._textos_do_chefe(ambiente, self.CHEFE_2.telefone)), 1)

	def test_carimba_o_beneficiario_avisado(self):
		ambiente = _Ambiente([_jovem(dias=7)], chefes={"J1": [self.CHEFE]})
		ambiente.rodar()
		self.assertIn(
			{"regua_validade_referencia": _dia(7), "regua_chefe_ultimo_marco": "7"},
			ambiente.gravacoes_de("J1"),
		)

	def test_sem_chefe_nao_carimba(self):
		ambiente = _Ambiente([_jovem(dias=-1)])
		ambiente.rodar()
		self.assertFalse(any("regua_chefe_ultimo_marco" in g for g in ambiente.gravacoes_de("J1")))

	def test_falha_com_um_chefe_ainda_carimba_se_outro_recebeu(self):
		ambiente = _Ambiente(
			[_jovem(dias=7)],
			chefes={"J1": [self.CHEFE, self.CHEFE_2]},
			falhar_para={self.CHEFE.telefone},
		)
		ambiente.rodar()
		self.assertTrue(any(g.get("regua_chefe_ultimo_marco") == "7" for g in ambiente.gravacoes_de("J1")))

	def test_adulto_nao_vai_para_o_chefe(self):
		ambiente = _Ambiente([_associado(dias=7)], chefes={"A1": [self.CHEFE]})
		ambiente.rodar()
		self.assertEqual(self._textos_do_chefe(ambiente, self.CHEFE.telefone), [])

	def test_interruptor_do_marco_do_chefe(self):
		ambiente = _Ambiente(
			[_jovem("J1", dias=30), _jovem("J2", dias=-1)],
			chefes={"J1": [self.CHEFE], "J2": [self.CHEFE]},
			interruptores={"msg_venc_chefe_pos": False},
		)
		ambiente.rodar()
		mensagem = self._textos_do_chefe(ambiente, self.CHEFE.telefone)[0]["mensagem"]
		self.assertIn("cerca de 30 dias", mensagem)
		self.assertNotIn("registros vencidos", mensagem)


class TestResumoMensal(FrappeTestCase):
	CHEFE = frappe._dict(name="C1", nome_completo="Rafael Chefe", telefone="+5511977777777")

	def _ambiente(self, beneficiarios, **kwargs):
		config = {"grupo_chefes_whatsapp": "123@g.us", "resumo_mensal_enviado_em": "2026-10"}
		config.update(kwargs.pop("config", {}))
		return _Ambiente([], config=config, beneficiarios_do_mes=beneficiarios, **kwargs)

	def test_agrupa_por_secao_com_sem_secao_por_ultimo(self):
		beneficiarios = [
			_jovem("J1", dias=5, secao="Tropa Exemplo", nome_completo="Bruno"),
			_jovem("J2", dias=2, secao="alcateia exemplo", nome_completo="Ana"),
			_jovem("J3", dias=1, secao="Alcateia Exemplo", nome_completo="Carla"),
			_jovem("J4", dias=3, secao="", nome_completo="Davi"),
		]
		ambiente = self._ambiente(beneficiarios, chefes={"J2": [self.CHEFE], "J3": [self.CHEFE]})
		ambiente.rodar()
		self.assertEqual(len(ambiente.grupos), 1)
		mensagem = ambiente.grupos[0]["mensagem"]
		self.assertIn("novembro de 2026", mensagem)
		self.assertIn("*alcateia exemplo* @5511977777777\n• 21/11 — Carla\n• 22/11 — Ana", mensagem)
		self.assertLess(mensagem.index("alcateia exemplo"), mensagem.index("Tropa Exemplo"))
		self.assertLess(mensagem.index("Tropa Exemplo"), mensagem.index("*Sem seção*"))
		self.assertIn("Total: 4.", mensagem)
		self.assertEqual(ambiente.grupos[0]["mencionar"], ["+5511977777777"])
		self.assertEqual(ambiente.singles["resumo_mensal_enviado_em"], "2026-11")

	def test_uma_vez_por_mes(self):
		ambiente = self._ambiente([_jovem(dias=3)], config={"resumo_mensal_enviado_em": "2026-11"})
		ambiente.rodar()
		self.assertEqual(ambiente.grupos, [])

	def test_mes_vazio_nao_envia_mas_carimba(self):
		ambiente = self._ambiente([])
		ambiente.rodar()
		self.assertEqual(ambiente.grupos, [])
		self.assertEqual(ambiente.singles["resumo_mensal_enviado_em"], "2026-11")

	def test_sem_grupo(self):
		ambiente = self._ambiente([_jovem(dias=3)], config={"grupo_chefes_whatsapp": ""})
		resultado = ambiente.rodar()
		self.assertEqual(ambiente.grupos, [])
		self.assertEqual(resultado["resumo_mensal"]["situacao"], "sem grupo configurado")
		self.assertNotIn("resumo_mensal_enviado_em", ambiente.singles)

	def test_interruptor_desligado(self):
		ambiente = self._ambiente([_jovem(dias=3)], interruptores={"msg_venc_grupo_mensal": False})
		ambiente.rodar()
		self.assertEqual(ambiente.grupos, [])

	def test_rodape(self):
		ambiente = self._ambiente([_jovem(dias=3)])
		ambiente.rodar()
		self.assertTrue(ambiente.grupos[0]["mensagem"].endswith(modelos.ASSINATURA_AUTOMATICA))


class TestAvisoManual(FrappeTestCase):
	def _rodar(self, associado, gestores=()):
		enviados = []
		with (
			patch.object(regua.frappe, "has_permission", return_value=True),
			patch.object(regua.frappe.db, "get_value", return_value=dict(associado)),
			patch.object(regua, "today", return_value=HOJE.isoformat()),
			patch.object(regua, "_buscar_links_responsavel", return_value={}),
			patch.object(regua, "_buscar_contatos_responsavel", return_value={}),
			patch.object(regua, "contato_duvidas", return_value=""),
			patch.object(regua, "instrucoes_renovacao", return_value=""),
			patch.object(regua, "buscar_destinatarios_gestores", return_value=list(gestores)),
			patch.object(modelos, "_valor_do_single", return_value=""),
			patch.object(regua.frappe.db, "set_value") as set_value,
			patch.object(
				regua,
				"enviar_texto",
				side_effect=lambda numero, mensagem, **kw: enviados.append((numero, mensagem)),
			),
		):
			resultado = regua.notificar_vencimento_manual("A1")
		set_value.assert_not_called()
		return resultado, enviados

	def test_usa_o_modelo_do_marco_atual_sem_carimbar(self):
		resultado, enviados = self._rodar(_associado(dias=5))
		self.assertEqual(resultado["marco"], "7")
		self.assertIn("Falta uma semana", enviados[0][1])

	def test_mais_de_30_dias_usa_o_de_30(self):
		resultado, enviados = self._rodar(_associado(dias=90))
		self.assertEqual(resultado["marco"], "30")
		self.assertIn("daqui a 90 dias", enviados[0][1])

	def test_vencido_avisa_os_gestores(self):
		gestor = frappe._dict(nome="Gestora Exemplo", telefone="+5511955555555")
		_resultado, enviados = self._rodar(_associado(dias=-4), gestores=[gestor])
		self.assertEqual(len(enviados), 2)
		self.assertIn("venceu há 4 dia(s)", enviados[1][1])
		self.assertTrue(enviados[1][1].endswith(modelos.ASSINATURA_AUTOMATICA))
