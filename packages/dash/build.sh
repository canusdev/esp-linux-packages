#!/bin/bash
set -euo pipefail
pkg_dir=$(cd -- "$(dirname -- "$0")" && pwd)
repo_dir=$(cd -- "$pkg_dir/../.." && pwd)
dest_dir="$pkg_dir/files"

# Check if already compiled in experiments
prebuilt="$repo_dir/experiments/mmu-poc/out/real-bins/dash"
if [ -f "$prebuilt" ]; then
    echo "Using prebuilt binary from $prebuilt"
    mkdir -p "$dest_dir/usr/bin"
    cp -a "$prebuilt" "$dest_dir/usr/bin/dash"
    exit 0
fi

echo "Source build required: run experiments/mmu-poc/fork/real/build.sh dash"
exit 1
