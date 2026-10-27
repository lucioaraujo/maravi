#!/bin/sh
set -eu

project_dir=$(CDPATH= cd -- "$(dirname -- "$0")" && pwd)
local_audiveris="$project_dir/.local-build/audiveris-5.11.0/root/opt/audiveris/bin/Audiveris"

# Use the local extracted official package when present; otherwise let Maravi
# discover a system installation or honor an explicit MARAVI_AUDIVERIS_BIN.
if [ -z "${MARAVI_AUDIVERIS_BIN:-}" ] && [ -x "$local_audiveris" ]; then
  MARAVI_AUDIVERIS_BIN="$local_audiveris"
  export MARAVI_AUDIVERIS_BIN
fi

exec "$project_dir/.venv/bin/python" -B "$project_dir/run_maravi.py"
