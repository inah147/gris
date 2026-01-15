import importlib.util
import sys

import frappe

# Import module from path since it's in www
file_path = "/workspace/frappe-bench/apps/gris/gris/www/manifestacao_interesse/index.py"
spec = importlib.util.spec_from_file_location("manifestacao_index", file_path)
module = importlib.util.module_from_spec(spec)
sys.modules["manifestacao_index"] = module
spec.loader.exec_module(module)
submit_interest = module.submit_interest


def test_submit():
	# Use unique emails to avoid "User exists" error
	import random

	suffix = random.randint(1000, 99999)
	email = f"test_{suffix}@example.com"
	mobile = f"119{suffix:04d}0"

	jovens = [
		{
			"nome_jovem": f"Jovem {suffix}",
			"data_nascimento_jovem": "2010-01-01",
			"cpf_jovem": f"111222333{suffix % 100:02d}",
		}
	]

	print(f"Testing with email: {email}")

	try:
		result = submit_interest(
			nome_responsavel=f"Responsavel {suffix}",
			email_responsavel=email,
			celular_responsavel=mobile,
			cpf_responsavel=f"999888777{suffix % 100:02d}",
			jovens=jovens,
		)
		print("Result:", result)

		# Check Error Log
		logs = frappe.get_all(
			"Error Log",
			filters={"method": ["like", "DEBUG EMAIL%"]},
			fields=["method", "error", "creation"],
			order_by="creation desc",
			limit=1,
		)
		if logs:
			print("\nDebug Log:")
			print("Method:", logs[0].method)
			print("Error:\n", logs[0].error)

	except Exception:
		import traceback

		traceback.print_exc()
