class WhatsAppConfigurationError(Exception):
	pass


class WhatsAppRequestError(Exception):
	"""Falha ao falar com a Evolution API.

	``status_code`` vem preenchido quando a Evolution respondeu com erro HTTP; fica ``None``
	quando a falha foi antes disso (rede, tempo esgotado, fila de envio ocupada).
	"""

	def __init__(self, mensagem: str = "", *, status_code: int | None = None):
		super().__init__(mensagem)
		self.status_code = status_code


class WhatsAppDesconectadoError(WhatsAppRequestError):
	"""A instância da Evolution está sem sessão com o WhatsApp: nada sai até alguém reconectá-la."""


class WhatsAppNumberNotFoundError(Exception):
	"""Raised when the destination number is not registered on WhatsApp."""

	pass
