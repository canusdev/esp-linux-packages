#!/usr/bin/env python3
"""
make-apkindex.py - Generate APKINDEX.tar.gz repository index for esp-linux.

Scans a directory of .apk files, reads each package's .PKGINFO,
and produces a standard OpenWrt/Alpine compatible APKINDEX.tar.gz.
"""

import argparse
import hashlib
import io
import os
import sys
import tarfile
import time


def parse_pkginfo(pkginfo_content):
    info = {
        "depends": []
    }
    for line in pkginfo_content.decode("utf-8", errors="ignore").splitlines():
        line = line.strip()
        if not line or line.startswith("#"):
            continue
        if "=" in line:
            k, v = line.split("=", 1)
            k = k.strip()
            v = v.strip()
            if k == "depend":
                info["depends"].append(v)
            else:
                info[k] = v
    return info


def compute_sha256(filepath):
    hasher = hashlib.sha256()
    with open(filepath, "rb") as f:
        while chunk := f.read(65536):
            hasher.update(chunk)
    return hasher.hexdigest()


def main():
    parser = argparse.ArgumentParser(description="Generate APKINDEX.tar.gz for an APK repository")
    parser.add_argument("--dir", "-d", required=True, help="Directory containing .apk files")
    parser.add_argument("--output", "-o", default=None, help="Output APKINDEX.tar.gz path (default: <dir>/APKINDEX.tar.gz)")
    parser.add_argument("--desc", default="esp-linux package repository", help="Repository description")

    args = parser.parse_args()

    repo_dir = os.path.abspath(args.dir)
    if not os.path.isdir(repo_dir):
        print(f"Error: directory '{repo_dir}' not found", file=sys.stderr)
        sys.exit(1)

    out_path = args.output if args.output else os.path.join(repo_dir, "APKINDEX.tar.gz")

    apk_files = sorted([f for f in os.listdir(repo_dir) if f.endswith(".apk")])
    if not apk_files:
        print(f"Warning: No .apk files found in {repo_dir}", file=sys.stderr)

    index_entries = []

    for fname in apk_files:
        fpath = os.path.join(repo_dir, fname)
        file_size = os.path.getsize(fpath)
        sha256_hash = compute_sha256(fpath)

        pkginfo_data = None
        try:
            with tarfile.open(fpath, "r:gz") as tar:
                for member in tar.getmembers():
                    if member.name == ".PKGINFO":
                        f = tar.extractfile(member)
                        if f:
                            pkginfo_data = f.read()
                        break
        except Exception as e:
            print(f"Warning: could not read {fname}: {e}", file=sys.stderr)
            continue

        if not pkginfo_data:
            print(f"Warning: {fname} has no .PKGINFO, skipping", file=sys.stderr)
            continue

        info = parse_pkginfo(pkginfo_data)

        # Construct APKINDEX paragraph
        # C: Checksum, P: Pkgname, V: Version, A: Arch, S: FileSize, I: InstalledSize
        # T: Description, U: Url, L: License, t: BuildTime, D: Depends
        lines = [
            f"C:Q1{sha256_hash[:20]}",
            f"P:{info.get('pkgname', os.path.splitext(fname)[0])}",
            f"V:{info.get('pkgver', '1.0')}",
            f"A:{info.get('arch', 'xtensa')}",
            f"S:{file_size}",
            f"I:{info.get('size', file_size)}",
            f"T:{info.get('pkgdesc', '')}",
            f"U:{info.get('url', '')}",
            f"L:{info.get('license', '')}",
            f"t:{info.get('builddate', int(time.time()))}",
        ]
        if info["depends"]:
            lines.append(f"D:{' '.join(info['depends'])}")

        index_entries.append("\n".join(lines))

    # Combine with double newlines
    index_content = "\n\n".join(index_entries)
    if index_content:
        index_content += "\n\n"
    index_bytes = index_content.encode("utf-8")

    # Write APKINDEX.tar.gz
    with tarfile.open(out_path, "w:gz", format=tarfile.PAX_FORMAT) as tar:
        ti = tarfile.TarInfo("APKINDEX")
        ti.size = len(index_bytes)
        ti.mtime = int(time.time())
        ti.mode = 0o644
        ti.uname = "root"
        ti.gname = "root"
        tar.addfile(ti, io.BytesIO(index_bytes))

    print(f"Generated index: {out_path} ({len(index_entries)} packages, {len(index_bytes)} bytes uncompressed)")


if __name__ == "__main__":
    main()
