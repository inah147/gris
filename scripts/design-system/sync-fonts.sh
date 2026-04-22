#!/usr/bin/env bash

set -euo pipefail

ROOT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/../.." && pwd)"
SRC_DIR="$ROOT_DIR/node_modules/@fontsource-variable/figtree/files"
TARGET_DIR="$ROOT_DIR/gris/public/design_system/fonts/figtree"

mkdir -p "$TARGET_DIR"

cp "$SRC_DIR/figtree-latin-wght-normal.woff2" "$TARGET_DIR/"
cp "$SRC_DIR/figtree-latin-wght-italic.woff2" "$TARGET_DIR/"
cp "$SRC_DIR/figtree-latin-ext-wght-normal.woff2" "$TARGET_DIR/"
cp "$SRC_DIR/figtree-latin-ext-wght-italic.woff2" "$TARGET_DIR/"

echo "Figtree variable fonts synchronized to gris/public/design_system/fonts/figtree."
