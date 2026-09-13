#!/usr/bin/env bash
set -euo pipefail
pkg_dir=$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")" && pwd)
tc_gcc="${CROSS_COMPILE:-}gcc"

if command -v xtensa-esp32s3-linux-uclibcfdpic-gcc >/dev/null 2>&1; then
    tc_gcc="xtensa-esp32s3-linux-uclibcfdpic-gcc"
elif [ -n "${XTENSA_GCC:-}" ]; then
    tc_gcc="$XTENSA_GCC"
fi

if [ -f "$pkg_dir/files/usr/sbin/mqtt-server" ]; then
    echo "Using pre-built binary for mqtt-server"
    exit 0
fi

if command -v "$tc_gcc" >/dev/null 2>&1; then
    echo "Cross-compiling mqtt_server.c with $tc_gcc..."
    mkdir -p "$pkg_dir/files/usr/sbin"
    "$tc_gcc" -Os -mfdpic -mauto-litpools -fPIC -ffunction-sections -fdata-sections -Wl,--gc-sections \
        "$pkg_dir/src/mqtt_server.c" -o "$pkg_dir/files/usr/sbin/mqtt-server"
    exit 0
fi

echo "Toolchain not found, skipping compile"
exit 1
