# Copyright (c) 2025, Grupo Escoteiro Professora Inah de Mello - 47/SP and contributors
# For license information, please see license.txt

import frappe
from frappe import _
from frappe.model.document import Document
from frappe.utils import getdate

from gris.api.gestao_adultos.identidade import DOCTYPE_ASSOCIADO, DOCTYPE_RESPONSAVEL

# Categoria que nunca pode liderar uma área: beneficiário é assistido, não voluntário.
CATEGORIA_NAO_VOLUNTARIA = "Beneficiário"


class UnidadeOrganizacional(Document):
	def validate(self):
		self._validar_raiz_fixa()
		self._validar_ciclo()
		self._normalizar_responsavel()
		self._validar_responsavel()
		self._validar_funcoes_duplicadas()
		self._validar_desvinculo_de_funcao()

	def _validar_raiz_fixa(self):
		"""O Conselho de Responsáveis não responde para nenhuma outra área.

		A tela de administração permite arrastar uma área para dentro de outra
		(`mover_unidade`), e a proteção de área automática que existe lá cobre só o nome
		e o `ativa`. Sem esta guarda, um arraste acidental penduraria o conselho na
		diretoria e mudaria em silêncio o que o organograma afirma sobre ele.
		"""
		from gris.api.gestao_adultos.responsaveis import AREA_CONSELHO

		if self.name == AREA_CONSELHO and self.responde_para:
			frappe.throw(
				_("{0} é uma área de topo e não responde para nenhuma outra.").format(
					frappe.bold(AREA_CONSELHO)
				)
			)

	def _validar_ciclo(self):
		"""Impede que a cadeia de `responde_para` volte para esta mesma área.

		O organograma percorre essa cadeia recursivamente; um ciclo trava a
		montagem da árvore, então barramos na gravação.
		"""
		if not self.responde_para:
			return

		if self.responde_para == self.name:
			frappe.throw(_("Uma área não pode responder para ela mesma."))

		visitados = {self.name}
		atual = self.responde_para
		while atual:
			if atual in visitados:
				frappe.throw(
					_("Hierarquia circular: {0} já responde, direta ou indiretamente, para {1}.").format(
						atual, self.name
					)
				)
			visitados.add(atual)
			atual = frappe.db.get_value("Unidade Organizacional", atual, "responde_para")

	def _normalizar_responsavel(self):
		"""Garante o par (tipo, nome) coerente antes de qualquer validação.

		Duas coisas acontecem aqui. A primeira é o default, que vale mesmo sem líder: o
		`_validate_links` do framework roda **antes** deste `validate()`, então uma área com
		o tipo em branco no banco recusaria a gravação em que alguém fosse escolhido — antes
		de qualquer código daqui rodar. Deixar o campo sempre preenchido é o que mantém a
		área editável.

		A segunda é a identidade única. Quem é responsável legal **e** associado tem um
		cadastro só que vale — o de associado (ver `gris.api.pessoas`). Gravar essa pessoa
		como `Responsavel` produziria a chave `responsavel:<id>`, que não casa com o card
		`associado:<id>` que o organograma desenha, e a área apareceria sem líder. Então o
		ponteiro é trazido para o lado certo em vez de recusado: para quem edita, escolher
		a pessoa é o que importa, não de qual cadastro ela veio.
		"""
		if self.tipo_responsavel not in (DOCTYPE_ASSOCIADO, DOCTYPE_RESPONSAVEL):
			self.tipo_responsavel = DOCTYPE_ASSOCIADO

		if not self.responsavel or self.tipo_responsavel != DOCTYPE_RESPONSAVEL:
			return

		from gris.api.pessoas import associado_do_responsavel

		associado = associado_do_responsavel(self.responsavel)
		if associado:
			self.responsavel = associado
			self.tipo_responsavel = DOCTYPE_ASSOCIADO

	def _validar_responsavel(self):
		if not self.responsavel:
			return

		# Só valida quando o responsável entra ou muda. `_definir_responsavel` da
		# sincronização grava por `db.set_value`, que pula o `validate()`, então o
		# banco pode já conter responsável que hoje seria recusado — e isso não pode
		# impedir de editar o resto da área.
		if not self.is_new() and not (
			self.has_value_changed("responsavel") or self.has_value_changed("tipo_responsavel")
		):
			return

		# O responsável legal sem cadastro de associado não tem categoria nem status no
		# grupo: ele não é do quadro de voluntários, e o que o habilita a liderar é o
		# próprio cadastro existir — o que o Dynamic Link já confere.
		if self.tipo_responsavel == DOCTYPE_RESPONSAVEL:
			return

		categoria, status_no_grupo = frappe.db.get_value(
			"Associado", self.responsavel, ["categoria", "status_no_grupo"]
		) or (None, None)

		if categoria == CATEGORIA_NAO_VOLUNTARIA:
			frappe.throw(
				_("{0} tem categoria {1} e não pode ser responsável por uma área.").format(
					frappe.bold(self.responsavel), CATEGORIA_NAO_VOLUNTARIA
				)
			)

		if status_no_grupo == "Inativo":
			frappe.throw(
				_("{0} está inativo no grupo e não pode ser responsável por uma área.").format(
					frappe.bold(self.responsavel)
				)
			)

	def _validar_funcoes_duplicadas(self):
		"""A mesma função duas vezes na lista não diz nada e envenena o resto.

		Com a duplicata no lugar, a checagem de desvínculo compara conjuntos que não
		batem e a área fica insalvável sem ninguém entender por quê.
		"""
		vistas = set()
		for linha in self.funcoes or []:
			if not linha.funcao:
				continue
			if linha.funcao in vistas:
				frappe.throw(
					_("A função {0} está repetida na lista de funções (linha {1}).").format(
						frappe.bold(linha.funcao), linha.idx
					)
				)
			vistas.add(linha.funcao)

	def _validar_desvinculo_de_funcao(self):
		"""Barra tirar da área uma função que alguém ainda exerce aqui.

		Sem isto, a pessoa continuaria no organograma com um par função+área que já
		não existe no cadastro — e o vínculo é justamente o que valida esse par.
		"""
		anterior = self.get_doc_before_save()
		if not anterior:
			return

		antes = {linha.funcao for linha in (anterior.funcoes or []) if linha.funcao}
		agora = {linha.funcao for linha in (self.funcoes or []) if linha.funcao}
		for funcao in sorted(antes - agora):
			pessoas = _pessoas_com_funcao_ativa(funcao, self.name)
			if pessoas:
				frappe.throw(
					_(
						"Não dá para tirar a função {0} desta área: {1} pessoa(s) ainda a exercem aqui. "
						"Encerre a função interna dessas pessoas primeiro."
					).format(frappe.bold(funcao), pessoas)
				)


def _pessoas_com_funcao_ativa(funcao: str, area: str) -> int:
	"""Quantas pessoas distintas exercem este par hoje.

	O corte segue o mesmo do organograma (`lotacoes_atuais`): só está encerrada a
	linha cuja `data_fim` já passou. Se divergir, a área bloquearia por alguém que o
	desenho já não mostra.

	Devolve contagem, nunca nomes: `frappe.get_all` ignora permissão e as funções
	internas do Associado vivem em permlevel 2.
	"""
	linhas = frappe.get_all(
		"Funcao do Associado",
		filters={"parenttype": "Associado", "funcao": funcao, "area": area},
		fields=["parent", "data_fim"],
	)
	hoje = getdate()
	return len(
		{
			linha["parent"]
			for linha in linhas
			if not linha.get("data_fim") or getdate(linha["data_fim"]) >= hoje
		}
	)
