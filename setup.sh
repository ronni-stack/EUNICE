#!/bin/bash
# EUNICE Setup — wrapper for unified CLI
# Legacy: use ./eunice.sh setup
"$(cd "$(dirname "$0")" && pwd)/eunice.sh" setup "$@"
