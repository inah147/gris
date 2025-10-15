#!/usr/bin/env python3
"""
Cria ícones placeholder para PWA para teste rápido.
Não requer dependências externas, usa apenas bibliotecas padrão.
"""

import os

# SVG template
SVG_TEMPLATE = """<?xml version="1.0" encoding="UTF-8"?>
<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 {size} {size}" width="{size}" height="{size}">
  <!-- Background gradient -->
  <defs>
    <linearGradient id="grad" x1="0%" y1="0%" x2="100%" y2="100%">
      <stop offset="0%" style="stop-color:#667EEA;stop-opacity:1" />
      <stop offset="100%" style="stop-color:#764BA2;stop-opacity:1" />
    </linearGradient>
  </defs>
  <rect width="{size}" height="{size}" fill="url(#grad)" rx="64"/>
  
  <!-- Icon content -->
  <g transform="translate({size}/2, {size}/2)">
    <!-- Flor de Lis estilizada -->
    <path d="M 0,-{scale} L {scale2},-{scale3} L {scale4},-{scale5} L {scale4},0 L {scale6},{scale3} L {scale6},{scale5} L 0,{scale7} L -{scale6},{scale5} L -{scale6},{scale3} L -{scale4},0 L -{scale4},-{scale5} L -{scale2},-{scale3} Z" 
          fill="white" opacity="0.95"/>
    
    <!-- Texto -->
    <text y="{text_y}" font-family="Arial, sans-serif" font-size="{font_size}" font-weight="bold" fill="white" text-anchor="middle">
      GRIS
    </text>
  </g>
</svg>
"""

SIZES = [72, 96, 128, 144, 152, 192, 384, 512]


def create_placeholder_svg(size, output_path):
	"""Cria um SVG placeholder."""
	# Calcula proporções
	scale = size * 0.2
	scale2 = size * 0.05
	scale3 = size * 0.15
	scale4 = size * 0.08
	scale5 = size * 0.25
	scale6 = size * 0.12
	scale7 = size * 0.3
	text_y = size * 0.25
	font_size = size * 0.15

	svg_content = SVG_TEMPLATE.format(
		size=size,
		scale=scale,
		scale2=scale2,
		scale3=scale3,
		scale4=scale4,
		scale5=scale5,
		scale6=scale6,
		scale7=scale7,
		text_y=text_y,
		font_size=font_size,
	)

	with open(output_path, "w") as f:
		f.write(svg_content)


def main():
	script_dir = os.path.dirname(os.path.abspath(__file__))
	icons_dir = os.path.join(script_dir, "icons")

	# Cria diretório se não existir
	os.makedirs(icons_dir, exist_ok=True)

	print("🎨 Gerando ícones placeholder PWA...")
	print("⚠️  ATENÇÃO: Estes são apenas placeholders para teste!")
	print("   Substitua por ícones profissionais assim que possível.\n")

	for size in SIZES:
		output_path = os.path.join(icons_dir, f"icon-{size}x{size}.svg")
		create_placeholder_svg(size, output_path)
		print(f"✅ Criado: icon-{size}x{size}.svg")

	print("\n✨ Ícones placeholder criados com sucesso!")
	print(f"📁 Localização: {icons_dir}")
	print("\n📝 Próximos passos:")
	print("   1. Teste o PWA com estes ícones")
	print("   2. Substitua por ícones PNG reais assim que possível")
	print("   3. Use: python generate_icons.py seu_logo.png")


if __name__ == "__main__":
	main()
