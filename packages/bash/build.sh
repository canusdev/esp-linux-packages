#!/bin/bash
set -euo pipefail
pkg_dir=$(cd -- "$(dirname -- "$0")" && pwd)
repo_dir=$(cd -- "$pkg_dir/../.." && pwd)
dest_dir="$pkg_dir/files"

prebuilt="$repo_dir/experiments/mmu-poc/out/programs/bash"
if [ -f "$prebuilt" ]; then
    echo "Using prebuilt binary from $prebuilt"
    mkdir -p "$dest_dir/bin"
    cp -a "$prebuilt" "$dest_dir/bin/bash"
    exit 0
fi

echo "Source build required: run experiments/mmu-poc/programs/build-bash.sh"
exit 1
