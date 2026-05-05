#!/usr/bin/env bash

set -euo pipefail

ROOT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/../.." && pwd)"
SRC_DIR="$ROOT_DIR/node_modules/@toast-ui/editor/dist"
ESBUILD="$ROOT_DIR/node_modules/.bin/esbuild"
ENTRY_JS="$ROOT_DIR/scripts/design-system/toastui-editor-entry.js"

TARGET_DIR="$ROOT_DIR/gris/public/vendor/toastui-editor"
TARGET_I18N_DIR="$TARGET_DIR/i18n"

if [ ! -x "$ESBUILD" ]; then
  echo "esbuild not found at $ESBUILD. Run 'npm install' first." >&2
  exit 1
fi

mkdir -p "$TARGET_DIR" "$TARGET_I18N_DIR"

"$ESBUILD" --bundle --minify --legal-comments=none \
  --platform=browser --format=iife \
  "$ENTRY_JS" \
  --outfile="$TARGET_DIR/toastui-editor-all.min.js"

"$ESBUILD" --minify --legal-comments=none \
  "$SRC_DIR/toastui-editor.css" \
  --outfile="$TARGET_DIR/toastui-editor.min.css"

"$ESBUILD" --minify --legal-comments=none \
  "$SRC_DIR/theme/toastui-editor-dark.css" \
  --outfile="$TARGET_DIR/toastui-editor-dark.min.css"

"$ESBUILD" --minify --legal-comments=none \
  "$SRC_DIR/i18n/pt-br.js" \
  --outfile="$TARGET_I18N_DIR/pt-br.min.js"

echo "Toast UI Editor assets synchronized to gris/public/vendor/toastui-editor."
