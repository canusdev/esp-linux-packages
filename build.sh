#!/usr/bin/env bash
#
# build.sh - Build the APK repository and GitHub Pages site.
# Usage:
#   ./build.sh                     # Build all packages
#   ./build.sh espctl mqtt-server  # Build specific packages
#   ./build.sh --changed           # Build only modified or added packages (git diff)
#   ./build.sh clean               # Clean compiled binaries from packages/
#
set -euo pipefail
REPO_ROOT=$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")" && pwd)
cd "$REPO_ROOT"

if [ "${1:-}" = "clean" ]; then
    python3 tools/build-repo.py --clean
    exit 0
fi

if [ "${1:-}" = "--changed" ] || [ "${1:-}" = "-c" ]; then
    shift
    python3 tools/build-repo.py --changed-only "$@"
elif [ $# -gt 0 ] && [[ ! "$1" =~ ^- ]]; then
    python3 tools/build-repo.py --packages "$@"
else
    python3 tools/build-repo.py "$@"
fi

echo ""
echo "To preview the GitHub Pages site locally:"
echo "  python3 -m http.server -d _site 8080"
echo "Then open: http://localhost:8080"
