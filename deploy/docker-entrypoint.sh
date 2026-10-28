#!/bin/sh
# Apply migrations, then start Keel. Any other command is run as given
# so operators can use the CLI against the same database volume.
set -eu

if [ "$#" -eq 0 ]; then
  set -- keel serve
fi

if [ "$1" = "keel" ] && [ "${2:-}" = "serve" ]; then
  keel db upgrade
fi

exec "$@"
