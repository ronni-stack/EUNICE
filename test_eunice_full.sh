#!/bin/bash
# EUNICE Full Test — wrapper for unified CLI
# Legacy: use ./eunice.sh test
"$(cd "$(dirname "$0")" && pwd)/eunice.sh" test "$@"
