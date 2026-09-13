#!/usr/bin/env python3
"""
make-apk.py - OpenWrt / Alpine compatible APK package generator for esp-linux.

Creates a standard .apk package containing .PKGINFO metadata, optional
install scripts (.post-install, etc.), and target filesystem files.
"""

import argparse
import hashlib
import io
import os
import sys
import tarfile
import time


def calculate_dir_stats(data_dir):
    total_size = 0
    file_list = []
    for root, dirs, files in os.walk(data_dir):
        for f in files:
            full_path = os.path.join(root, f)
            rel_path = os.path.relpath(full_path, data_dir)
            st = os.stat(full_path)
            total_size += st.st_size
            file_list.append((full_path, rel_path, st))
    return total_size, file_list


def create_pkginfo(args, installed_size, datahash=None):
    lines = [
        f"pkgname = {args.name}",
        f"pkgver = {args.version}",
        f"pkgdesc = {args.desc}",
        f"url = {args.url}",
        f"builddate = {int(time.time())}",
        f"packager = {args.packager}",
        f"size = {installed_size}",
        f"arch = {args.arch}",
        f"license = {args.license}",
    ]
    for dep in args.depends:
        lines.append(f"depend = {dep}")
    if datahash:
        lines.append(f"datahash = {datahash}")
    lines.append("")  # Trailing newline
    return "\n".join(lines).encode("utf-8")


def main():
    parser = argparse.ArgumentParser(description="Build an OpenWrt/Alpine APK package")
    parser.add_argument("--name", "-n", required=True, help="Package name")
    parser.add_argument("--version", "-v", required=True, help="Package version (e.g. 1.0-r1)")
    parser.add_argument("--desc", "-d", default="Package for esp32s3 Linux", help="Package description")
    parser.add_argument("--arch", "-a", default="xtensa", help="Target architecture (default: xtensa)")
    parser.add_argument("--url", default="https://github.com/canusdev/esp-linux", help="Package homepage/url")
    parser.add_argument("--license", default="GPL", help="License")
    parser.add_argument("--packager", default="esp-linux build system", help="Packager name")
    parser.add_argument("--depend", action="append", dest="depends", default=[], help="Package dependency")
    parser.add_argument("--data-dir", required=True, help="Directory containing target filesystem tree")
    parser.add_argument("--pre-install", default=None, help="Pre-install script path")
    parser.add_argument("--post-install", default=None, help="Post-install script path")
    parser.add_argument("--pre-deinstall", default=None, help="Pre-deinstall script path")
    parser.add_argument("--post-deinstall", default=None, help="Post-deinstall script path")
    parser.add_argument("--output", "-o", required=True, help="Output .apk path")

    args = parser.parse_args()

    if not os.path.isdir(args.data_dir):
        print(f"Error: data directory '{args.data_dir}' does not exist", file=sys.stderr)
        sys.exit(1)

    os.makedirs(os.path.dirname(os.path.abspath(args.output)), exist_ok=True)

    installed_size, file_list = calculate_dir_stats(args.data_dir)

    # Compute data hash
    hasher = hashlib.sha256()
    for full_path, _, _ in sorted(file_list, key=lambda x: x[1]):
        with open(full_path, "rb") as f:
            while chunk := f.read(65536):
                hasher.update(chunk)
    datahash = hasher.hexdigest()

    pkginfo_bytes = create_pkginfo(args, installed_size, datahash)

    # Build tar.gz archive
    with tarfile.open(args.output, "w:gz", format=tarfile.PAX_FORMAT) as tar:
        # 1. Add .PKGINFO as first entry
        ti = tarfile.TarInfo(".PKGINFO")
        ti.size = len(pkginfo_bytes)
        ti.mtime = int(time.time())
        ti.mode = 0o644
        ti.uname = "root"
        ti.gname = "root"
        tar.addfile(ti, io.BytesIO(pkginfo_bytes))

        # 2. Add install scripts if provided
        scripts = [
            (".pre-install", args.pre_install),
            (".post-install", args.post_install),
            (".pre-deinstall", args.pre_deinstall),
            (".post-deinstall", args.post_deinstall),
        ]
        for name, path in scripts:
            if path and os.path.isfile(path):
                with open(path, "rb") as sf:
                    s_bytes = sf.read()
                sti = tarfile.TarInfo(name)
                sti.size = len(s_bytes)
                sti.mtime = int(time.time())
                sti.mode = 0o755
                sti.uname = "root"
                sti.gname = "root"
                tar.addfile(sti, io.BytesIO(s_bytes))

        # 3. Add data files
        for full_path, rel_path, st in sorted(file_list, key=lambda x: x[1]):
            arcname = rel_path.lstrip("/")
            tar.add(full_path, arcname=arcname, recursive=False)

    print(f"Created package: {args.output} ({os.path.getsize(args.output)} bytes, installed: {installed_size} bytes)")


if __name__ == "__main__":
    main()
