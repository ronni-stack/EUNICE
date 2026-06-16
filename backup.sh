#!/bin/bash
# EUNICE Backup — wrapper for unified CLI
# Legacy: use ./eunice.sh backup
"$(cd "$(dirname "$0")" && pwd)/eunice.sh" backup "$@"
