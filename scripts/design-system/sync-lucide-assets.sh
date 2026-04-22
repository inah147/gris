#!/usr/bin/env bash

set -euo pipefail

ROOT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/../.." && pwd)"
SRC_DIR="$ROOT_DIR/node_modules/lucide-static"
TARGET_DIR="$ROOT_DIR/gris/public/design_system/icons/lucide"

mkdir -p "$TARGET_DIR"

cp "$SRC_DIR/sprite.svg" "$TARGET_DIR/sprite.svg"
cp "$SRC_DIR/LICENSE" "$TARGET_DIR/LICENSE"

echo "Lucide static sprite synchronized to gris/public/design_system/icons/lucide."
