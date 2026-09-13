#!/usr/bin/env bash
set -euo pipefail
pkg_dir=$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")" && pwd)
tc_gcc="${CROSS_COMPILE:-}gcc"

if command -v xtensa-esp32s3-linux-uclibcfdpic-gcc >/dev/null 2>&1; then
    tc_gcc="xtensa-esp32s3-linux-uclibcfdpic-gcc"
elif [ -n "${XTENSA_GCC:-}" ]; then
    tc_gcc="$XTENSA_GCC"
fi

if ! command -v "$tc_gcc" >/dev/null 2>&1; then
    echo "Error: Xtensa cross-compiler ($tc_gcc) not found in PATH or XTENSA_GCC!"
    exit 1
fi

# Auto-detect XTENSA_GNU_CONFIG if not set
if [ -z "${XTENSA_GNU_CONFIG:-}" ]; then
    gcc_path=$(command -v "$tc_gcc" || true)
    if [ -n "$gcc_path" ]; then
        tc_root=$(cd -- "$(dirname -- "$gcc_path")/.." && pwd)
        if [ -f "$tc_root/lib/esp32s3.so" ]; then
            export XTENSA_GNU_CONFIG="$tc_root/lib/esp32s3.so"
        fi
    fi
fi

echo "Cross-compiling espctl with $tc_gcc..."
mkdir -p "$pkg_dir/files/usr/bin"
"$tc_gcc" -Os -mfdpic -mauto-litpools -fPIC -ffunction-sections -fdata-sections -Wl,--gc-sections \
    "$pkg_dir/src/espctl.c" -o "$pkg_dir/files/usr/bin/espctl"

# Strip binary if strip is available
tc_strip="${tc_gcc%gcc}strip"
if command -v "$tc_strip" >/dev/null 2>&1; then
    "$tc_strip" "$pkg_dir/files/usr/bin/espctl"
fi

echo "Successfully built espctl"
