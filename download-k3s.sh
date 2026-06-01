#!/bin/bash
# Pobiera pliki k3s (amd64) potrzebne do instalacji air-gap.
# Uruchom raz lokalnie przed ansible-playbook site.yml

set -euo pipefail

DEST="$(dirname "$0")/files"
mkdir -p "$DEST"

echo "Pobieranie najnowszej wersji k3s..."
VERSION=$(curl -sI https://github.com/k3s-io/k3s/releases/latest \
  | grep -i location | awk -F/ '{print $NF}' | tr -d '\r\n')
echo "Wersja: $VERSION"

echo "→ k3s binary (amd64)"
curl -L --progress-bar \
  "https://github.com/k3s-io/k3s/releases/download/${VERSION}/k3s" \
  -o "$DEST/k3s"
chmod +x "$DEST/k3s"

echo "→ airgap images (amd64, ~250MB)"
curl -L --progress-bar \
  "https://github.com/k3s-io/k3s/releases/download/${VERSION}/k3s-airgap-images-amd64.tar.zst" \
  -o "$DEST/k3s-airgap-images-amd64.tar.zst"

echo "→ install script"
curl -sfL https://get.k3s.io -o "$DEST/install.sh"
chmod +x "$DEST/install.sh"

echo ""
echo "Gotowe! Pliki w $DEST:"
ls -lh "$DEST"
echo ""
echo "Teraz uruchom: ansible-playbook site.yml"
