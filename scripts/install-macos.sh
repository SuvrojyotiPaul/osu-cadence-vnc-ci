#!/usr/bin/env bash
set -euo pipefail
mkdir -p reports
version=3.3.1
arch="$(uname -m)"
case "$arch" in
arm64) file="TurboVNC-${version}-arm64.dmg"; expected="8d285f7bc00d30c0ace104b1d71b5ba4eb8bc2a561c71d8b7a26f2798f7d5db3" ;;
x86_64) file="TurboVNC-${version}-x86_64.dmg"; expected="7fc670c9110e05661c7be14438c919f44cb1515124f7daa47f5d7166b53f666d" ;;
*) echo "Unsupported architecture: $arch"; exit 1 ;;
esac
url="https://github.com/TurboVNC/turbovnc/releases/download/${version}/${file}"
dest="${RUNNER_TEMP:-/tmp}/${file}"
{
curl --fail --location --retry 3 --silent --show-error "$url" -o "$dest"
echo "$expected  $dest" | shasum -a 256 --check -
mountpoint="${RUNNER_TEMP:-/tmp}/turbovnc-mount"
mkdir -p "$mountpoint"
hdiutil attach -readonly -nobrowse -mountpoint "$mountpoint" "$dest"
trap 'hdiutil detach "$mountpoint" -quiet || true' EXIT
sudo installer -pkg "$mountpoint/TurboVNC.pkg" -target /
test -e /opt/TurboVNC/bin/vncviewer
} 2>&1 | tee reports/install.log
