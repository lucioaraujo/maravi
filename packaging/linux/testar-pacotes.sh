#!/usr/bin/env bash
# Start every distributed Linux package and check its local HTTP interface.
set -euo pipefail
PACKAGES=$(cd "${1:?package directory required}" && pwd -P)
(cd "$PACKAGES" && sha256sum -c SHA256SUMS)
APPIMAGE=$(find "$PACKAGES" -maxdepth 1 -name '*.AppImage' -print -quit)
ARCHIVE=$(find "$PACKAGES" -maxdepth 1 -name '*.tar.gz' -print -quit)
[[ -n "$APPIMAGE" && -n "$ARCHIVE" ]] || { echo 'missing Linux package format' >&2; exit 1; }
chmod +x "$APPIMAGE"

WORK=$(mktemp -d)
trap 'rm -rf "$WORK"' EXIT
tar -xzf "$ARCHIVE" -C "$WORK"
PACKAGE="$WORK/$(basename "$ARCHIVE" .tar.gz)"
PREFIX="$WORK/home/.local"
mkdir -p "$WORK/home"

check_server() {
  label=$1 port=$2; shift 2
  MARAVI_NO_BROWSER=1 MARAVI_PORT="$port" "$@" >"$WORK/$label.log" 2>&1 &
  pid=$!
  trap 'kill "$pid" 2>/dev/null || true; wait "$pid" 2>/dev/null || true' RETURN
  ready=0
  for _ in $(seq 1 60); do
    if curl -fsS "http://127.0.0.1:$port/" -o "$WORK/$label.html"; then ready=1; break; fi
    if ! kill -0 "$pid" 2>/dev/null; then break; fi
    sleep 1
  done
  test "$ready" = 1 || { cat "$WORK/$label.log"; echo "$label did not serve its local page" >&2; return 1; }
  grep -q Maravi "$WORK/$label.html"
  curl -fsS "http://127.0.0.1:$port/partitura" >/dev/null
  kill "$pid"
  wait "$pid" 2>/dev/null || true
  trap - RETURN
}

if test -x /usr/bin/maravi; then
  check_server deb 5077 /usr/bin/maravi
fi
check_server appimage 5078 env APPIMAGE_EXTRACT_AND_RUN=1 "$APPIMAGE"
"$PACKAGE/install.sh" --prefix "$PREFIX"
test -x "$PREFIX/bin/maravi"
check_server portable 5079 "$PREFIX/bin/maravi"
"$PACKAGE/install.sh" --remove --prefix "$PREFIX"
test ! -e "$PREFIX/bin/maravi"
echo 'Debian/AppImage/user-local package startup checks: passed where applicable'
