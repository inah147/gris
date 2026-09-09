# Copyright (c) 2026, Grupo Escoteiro Professora Inah de Mello - 47/SP and contributors
# For license information, please see license.txt

from frappe.model.document import Document


class LogdeMensagem(Document):
	"""Uma linha por mensagem que o GRIS tentou entregar.

	Só existe porque não havia registro nenhum de envio: ``Configuracoes WhatsApp`` guarda
	apenas o último envio e o último erro, globais. Sem isto, "quais mensagens este jovem já
	recebeu?" não tinha resposta. Gravado por ``gris.utils.whatsapp`` no ponto em que o
	resultado do provedor é conhecido, e lido pela ficha de registro da recepção.
	"""

	pass
