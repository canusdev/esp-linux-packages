#!/usr/bin/env bash
#
# build.sh - Build the APK repository and GitHub Pages site locally.
#
set -euo pipefail
REPO_ROOT=$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")" && pwd)
cd "$REPO_ROOT"

python3 tools/build-repo.py "$@"

echo ""
echo "To preview the GitHub Pages site locally:"
echo "  python3 -m http.server -d _site 8080"
echo "Then open: http://localhost:8080"
