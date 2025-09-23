import frappe
from frappe.utils import fmt_money, formatdate

from gris.api.portal_access import enrich_context, user_has_access
from gris.api.portal_cache_utils import get_uel_cached

no_cache = 1


def get_context(context):
	# Bloqueio para usuários não autenticados
	if frappe.session.user == "Guest":
		frappe.local.flags.redirect_location = "/login?redirect_to=/financeiro/contas"
		raise frappe.Redirect
	# Recupera logo e define para sidebar
	uel_data = get_uel_cached()
	if uel_data:
		context.portal_logo = uel_data.get("logo")
		if uel_data.get("nome_da_uel"):
			context.sidebar_title = f"{uel_data.get('tipo_uel')} {uel_data.get('nome_da_uel')}"
		else:
			context.sidebar_title = "Portal"
	else:
		context.sidebar_title = "Portal"
	context.active_link = "/financeiro/contas"
	enrich_context(context, "/financeiro/contas")

	# Dados de Contas (Instituições Financeiras)
	try:
		context.can_create_instituicao = frappe.has_permission("Instituicao Financeira", "create")
	except Exception:
		context.can_create_instituicao = False
	try:
		context.can_create_carteira = frappe.has_permission("Carteira", "create")
	except Exception:
		context.can_create_carteira = False
	contas_raw = frappe.get_all(
		"Instituicao Financeira",
		fields=["name", "nome"],
		order_by="nome asc",
	)
	context.contas = [
		{
			"name": c.get("name"),
			"display_name": c.get("nome") or c.get("name"),
		}
		for c in contas_raw
	]

	# Dados de Carteiras
	carteiras_raw = frappe.get_all(
		"Carteira",
		fields=[
			"name",
			"nome",
			"saldo",
			"data_atualizacao",
			# Tentamos ambos possíveis nomes (sem e com acento) se existirem
			"instituicao_financeira",
			"descricao",
			"responsavel",
			"chave_pix",
			"centro_de_custo",
		],
		order_by="nome asc",
	)
	carteiras = []
	# Mapeamento simples instituição -> variante de badge
	# variant_map agora mapeia substring -> (variant, outline_bool)
	variant_map = {
		"btg empresas": ("primary", False),
		"btg investimentos": ("primary", True),
		"portão 3": ("purple", False),
		"portao 3": ("purple", False),
		"inifinitepay": ("success", False),  # grafia presente no fixture
		"infinitepay": ("success", False),  # grafia alternativa
		"pagbank": ("warning", False),
	}
	for cart in carteiras_raw:
		saldo = cart.get("saldo") or 0
		# Campo pode ter sido criado com ou sem acento; fazemos fallback
		inst = cart.get("instituicao_financeira") or ""
		inst_slug = inst.lower()
		variant = None
		outline = False
		for key, v in variant_map.items():
			if key in inst_slug:
				variant, outline = v
				break
		if not variant:
			variant = "neutral"
		badge_classes = f"g-badge g-badge--{variant} g-badge--small"
		if outline:
			badge_classes = f"{badge_classes} g-badge--outline"
		carteiras.append(
			{
				"name": cart.get("name"),
				"display_name": cart.get("nome") or cart.get("name"),
				"instituicao_financeira": cart.get("instituicao_financeira"),
				"instituicao_variant": variant,
				"instituicao_badge_classes": badge_classes,
				"instituicao_badge_outline": outline,
				"descricao": cart.get("descricao") or "",
				"responsavel": cart.get("responsavel") or "",
				"chave_pix": cart.get("chave_pix") or "",
				"centro_de_custo": cart.get("centro_de_custo") or "",
				"saldo": saldo,
				"saldo_formatado": fmt_money(saldo) if saldo is not None else fmt_money(0),
				"data_atualizacao": cart.get("data_atualizacao"),
				"data_atualizacao_formatada": formatdate(cart.get("data_atualizacao"))
				if cart.get("data_atualizacao")
				else None,
			}
		)
	context.carteiras = carteiras
	return context
