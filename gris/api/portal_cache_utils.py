import frappe


def make_file_public(file_url: str) -> str:
	"""Torna um arquivo público e retorna a URL."""
	if not file_url:
		return None
	try:
		# Tenta buscar o registro do arquivo de duas formas
		file_doc = None

		# Primeiro tenta por file_url
		files = frappe.get_all("File", filters={"file_url": file_url}, limit=1)
		if files:
			file_doc = frappe.get_doc("File", files[0].name, ignore_permissions=True)

		# Se não encontrou, tenta buscar pelo nome (pode estar como /files/nome.ext)
		if not file_doc and file_url.startswith("/"):
			files = frappe.get_all(
				"File", filters={"file_url": ["like", f"%{file_url.split('/')[-1]}%"]}, limit=1
			)
			if files:
				file_doc = frappe.get_doc("File", files[0].name, ignore_permissions=True)

		if not file_doc:
			frappe.logger().warning(f"Arquivo não encontrado no DocType File: {file_url}")
			return file_url

		# Marca como público se ainda não estiver
		if file_doc.is_private:
			file_doc.is_private = 0
			file_doc.save(ignore_permissions=True)
			frappe.db.commit()
			frappe.logger().info(f"Arquivo tornado público: {file_url}")

		return file_url
	except Exception as e:
		frappe.logger().error(f"Erro ao tornar arquivo público {file_url}: {e!s}")
		return file_url


def get_uel_cached(ttl: int = 300, use_cache: bool = True) -> dict:
	cache = frappe.cache() if use_cache else None
	key = "uel_cached_v3"  # Mudou para v3 - Single DocType
	if use_cache:
		data = cache.get_value(key)
		if data:
			return data
	try:
		# Single DocType - usa get_single ao invés de get_all
		uel = frappe.get_single("Definicao da UEL")

		logo_url = getattr(uel, "logo", None)

		# Torna o logo público se existir
		if logo_url:
			logo_url = make_file_public(logo_url)

		# Busca documentos da child table
		documentos_list = []
		for d in getattr(uel, "documentos", []) or []:
			doc_dict = {
				"publico": getattr(d, "publico", 0),  # 0 ou 1 (int)
				"nome_do_documento": getattr(d, "nome_do_documento", "Documento"),
				"arquivo": getattr(d, "arquivo", None),
			}

			# Torna arquivo público se marcado como público
			if doc_dict["publico"] and doc_dict["arquivo"]:
				doc_dict["arquivo"] = make_file_public(doc_dict["arquivo"])

			documentos_list.append(doc_dict)

		data = {
			"logo": logo_url,
			"tipo_uel": getattr(uel, "tipo_uel", ""),
			"nome_da_uel": getattr(uel, "nome_da_uel", ""),
			"numeral": getattr(uel, "numeral", ""),
			"regiao": getattr(uel, "regiao", ""),
			"documentos": documentos_list,
		}

	except Exception as e:
		frappe.logger().error(f"Erro ao buscar Definicao da UEL: {e!s}")
		data = {}
	if use_cache:
		cache.set_value(key, data, expires_in_sec=ttl)
	return data


def get_transparency_years_cached(ttl: int = 300, use_cache: bool = True):
	"""Public list of available transparency years (cached)."""
	cache = frappe.cache() if use_cache else None
	key = "transparency_years_v1"
	if use_cache:
		years = cache.get_value(key)
		if years:
			return years
	try:
		rows = frappe.get_all(
			"Transparencia",
			fields=["ano_referencia"],
			filters={"publicado": 1},
			distinct=True,
			order_by="ano_referencia desc",
			ignore_permissions=True,
		)
		years = [r.ano_referencia for r in rows if r.ano_referencia]
	except Exception:
		years = []
	if use_cache:
		cache.set_value(key, years, expires_in_sec=ttl)
	return years
