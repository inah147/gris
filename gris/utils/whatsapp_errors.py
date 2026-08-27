class WhatsAppConfigurationError(Exception):
	pass


class WhatsAppRequestError(Exception):
	pass


class WhatsAppNumberNotFoundError(Exception):
	"""Raised when the destination number is not registered on WhatsApp."""

	pass
