#!/usr/bin/env python3
"""
Script para gerar ícones PWA em diferentes tamanhos.
Requer: Pillow (pip install Pillow)

Uso:
    python generate_icons.py /caminho/para/logo.png
"""

import os
import sys
from pathlib import Path

try:
	from PIL import Image
except ImportError:
	print("❌ Pillow não está instalado.")
	print("Execute: pip install Pillow")
	sys.exit(1)

# Tamanhos necessários para PWA
ICON_SIZES = [72, 96, 128, 144, 152, 192, 384, 512]


def generate_icons(source_image_path, output_dir=None):
	"""
	Gera ícones PWA em múltiplos tamanhos.

	Args:
	    source_image_path: Caminho para a imagem fonte (PNG, JPG, etc)
	    output_dir: Diretório de saída (padrão: mesmo diretório deste script)
	"""
	# Verifica se o arquivo existe
	if not os.path.exists(source_image_path):
		print(f"❌ Arquivo não encontrado: {source_image_path}")
		sys.exit(1)

	# Define diretório de saída
	if output_dir is None:
		script_dir = Path(__file__).parent
		output_dir = script_dir / "icons"
	else:
		output_dir = Path(output_dir)

	# Cria diretório se não existir
	output_dir.mkdir(parents=True, exist_ok=True)

	# Abre a imagem fonte
	try:
		img = Image.open(source_image_path)
		print(f"✅ Imagem carregada: {source_image_path}")
		print(f"   Tamanho original: {img.size}")
		print(f"   Formato: {img.format}")
		print()
	except Exception as e:
		print(f"❌ Erro ao abrir imagem: {e}")
		sys.exit(1)

	# Converte para RGBA se necessário
	if img.mode != "RGBA":
		img = img.convert("RGBA")

	# Gera cada tamanho
	for size in ICON_SIZES:
		output_path = output_dir / f"icon-{size}x{size}.png"

		try:
			# Redimensiona a imagem mantendo a qualidade
			resized = img.resize((size, size), Image.Resampling.LANCZOS)

			# Salva como PNG
			resized.save(output_path, "PNG", optimize=True)

			print(f"✅ Gerado: {output_path.name} ({size}x{size})")
		except Exception as e:
			print(f"❌ Erro ao gerar {size}x{size}: {e}")

	print()
	print("✨ Todos os ícones foram gerados com sucesso!")
	print(f"📁 Localização: {output_dir}")


def main():
	if len(sys.argv) < 2:
		print("Uso: python generate_icons.py <caminho_para_logo>")
		print()
		print("Exemplo:")
		print("  python generate_icons.py meu_logo.png")
		print("  python generate_icons.py /caminho/completo/logo.png")
		sys.exit(1)

	source_image = sys.argv[1]
	output_dir = sys.argv[2] if len(sys.argv) > 2 else None

	generate_icons(source_image, output_dir)


if __name__ == "__main__":
	main()
