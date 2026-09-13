#!/bin/bash
set -euo pipefail
pkg_dir=$(cd -- "$(dirname -- "$0")" && pwd)
repo_dir=$(cd -- "$pkg_dir/../.." && pwd)
dest_dir="$pkg_dir/files"

prebuilt="$repo_dir/experiments/mmu-poc/out/real-bins/make"
if [ -f "$prebuilt" ]; then
    echo "Using prebuilt binary from $prebuilt"
    mkdir -p "$dest_dir/usr/bin"
    cp -a "$prebuilt" "$dest_dir/usr/bin/make"
    exit 0
fi

echo "Source build required: run experiments/mmu-poc/fork/real/build.sh make"
exit 1
