#!/bin/sh
# SPDX-License-Identifier: AGPL-3.0-or-later
set -eu
package_dir=$(CDPATH= cd -- "$(dirname -- "$0")" && pwd -P)
command -v python3 >/dev/null 2>&1 || { echo 'The installer requires Python 3.' >&2; exit 1; }
exec python3 -B "$package_dir/install_portable.py" "$@"
