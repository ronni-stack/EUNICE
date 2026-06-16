#!/bin/bash
# EUNICE Launcher — wrapper for unified CLI
# Legacy: use ./eunice.sh launch
"$(cd "$(dirname "$0")" && pwd)/eunice.sh" launch "$@"
