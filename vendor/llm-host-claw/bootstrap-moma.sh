#!/usr/bin/env sh
set -eu

SCRIPT_DIR=$(CDPATH= cd -- "$(dirname -- "$0")" && pwd)
export PYTHONPATH="src"

ARGS="run python -u -m moma_cli init"

for arg in "$@"; do
  case "$arg" in
    --dev|-Dev)
      ARGS="$ARGS --dev"
      ;;
    --with-browsers|-WithBrowsers)
      ARGS="$ARGS --with-browsers"
      ;;
    *)
      echo "Unknown argument: $arg" >&2
      exit 2
      ;;
  esac
done

cd "$SCRIPT_DIR"
exec uv $ARGS
