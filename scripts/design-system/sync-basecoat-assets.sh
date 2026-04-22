#!/usr/bin/env bash

set -euo pipefail

ROOT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/../.." && pwd)"
SRC_CSS="$ROOT_DIR/node_modules/basecoat-css/dist/basecoat.cdn.min.css"
SRC_JS_DIR="$ROOT_DIR/node_modules/basecoat-css/dist/js"

TARGET_CSS_DIR="$ROOT_DIR/gris/public/design_system/css"
TARGET_JS_DIR="$ROOT_DIR/gris/public/design_system/js/basecoat"

mkdir -p "$TARGET_CSS_DIR" "$TARGET_JS_DIR"

cp "$SRC_CSS" "$TARGET_CSS_DIR/basecoat.css"
cp "$SRC_JS_DIR"/*.js "$TARGET_JS_DIR/"
cp "$SRC_JS_DIR"/*.min.js "$TARGET_JS_DIR/"

echo "Basecoat CSS/JS synchronized to gris/public/design_system."
