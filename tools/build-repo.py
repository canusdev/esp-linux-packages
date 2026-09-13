#!/usr/bin/env python3
"""
build-repo.py - Master repository builder for esp-linux-packages.
Supports:
  - Building all packages or only specific/changed packages
  - Automatic change detection via git diff
  - Syncing/retaining existing packages from remote GitHub Pages
  - Building only newly added or modified packages
  - Generating APKINDEX.tar.gz and GitHub Pages index.html
"""

import argparse
import glob
import io
import os
import shutil
import subprocess
import sys
import tarfile
import urllib.request

SCRIPT_DIR = os.path.dirname(os.path.abspath(__file__))
REPO_ROOT = os.path.abspath(os.path.join(SCRIPT_DIR, ".."))
MAKE_APK = os.path.join(SCRIPT_DIR, "make-apk.py")
MAKE_INDEX = os.path.join(SCRIPT_DIR, "make-apkindex.py")
GEN_HTML = os.path.join(SCRIPT_DIR, "generate-index-html.py")


def load_conf(conf_path):
    conf = {}
    with open(conf_path, "r", encoding="utf-8") as f:
        for line in f:
            line = line.strip()
            if not line or line.startswith("#"):
                continue
            if "=" in line:
                k, v = line.split("=", 1)
                k = k.strip()
                v = v.strip().strip('"').strip("'")
                conf[k] = v
    return conf


def get_changed_packages(packages_dir, base_ref=None):
    """
    Detect modified or newly added packages using git diff or status.
    """
    lines = []
    if base_ref and base_ref != "0000000000000000000000000000000000000000":
        res = subprocess.run(["git", "diff", "--name-only", base_ref, "HEAD", "--", "packages/"],
                             stdout=subprocess.PIPE, text=True)
        if res.returncode == 0 and res.stdout.strip():
            lines.extend(res.stdout.splitlines())
    else:
        res_diff = subprocess.run(["git", "diff", "--name-only", "HEAD", "--", "packages/"],
                                  stdout=subprocess.PIPE, text=True)
        if res_diff.returncode == 0:
            lines.extend(res_diff.stdout.splitlines())

        res_status = subprocess.run(["git", "status", "--porcelain", "packages/"],
                                    stdout=subprocess.PIPE, text=True)
        for s in res_status.stdout.splitlines():
            if len(s) > 3:
                lines.append(s[3:].strip())

        if not lines:
            res_last = subprocess.run(["git", "diff", "--name-only", "HEAD~1", "HEAD", "--", "packages/"],
                                      stdout=subprocess.PIPE, text=True)
            if res_last.returncode == 0:
                lines.extend(res_last.stdout.splitlines())

    changed = set()
    for line in lines:
        line = line.strip()
        if not line.startswith("packages/"):
            continue
        parts = line.split("/")
        if len(parts) >= 2:
            pkg_name = parts[1]
            if os.path.isfile(os.path.join(packages_dir, pkg_name, "package.conf")):
                changed.add(pkg_name)
    return sorted(list(changed))


def sync_remote_packages(remote_url, arch, arch_dir, skip_pkgs=None):
    """
    Download existing packages from remote URL (e.g. GitHub Pages) if available,
    skipping any packages that are slated to be rebuilt.
    """
    if skip_pkgs is None:
        skip_pkgs = set()

    index_url = f"{remote_url.rstrip('/')}/{arch}/APKINDEX.tar.gz"
    print(f">>> Checking remote package index: {index_url}")
    try:
        req = urllib.request.Request(index_url, headers={"User-Agent": "esp-linux-packages-builder/1.0"})
        with urllib.request.urlopen(req, timeout=10) as resp:
            data = resp.read()
    except Exception as e:
        print(f"  Notice: Remote index not reachable or empty ({e}), using local state.")
        return

    try:
        with tarfile.open(fileobj=io.BytesIO(data), mode="r:gz") as tar:
            apkindex_file = tar.extractfile("APKINDEX")
            if not apkindex_file:
                return
            content = apkindex_file.read().decode("utf-8", errors="ignore")
    except Exception as e:
        print(f"  Warning: Failed to parse remote APKINDEX: {e}")
        return

    current_pkg = {}
    remote_pkgs = []
    for line in content.splitlines():
        line = line.strip()
        if not line:
            if "P" in current_pkg and "V" in current_pkg:
                remote_pkgs.append(current_pkg)
            current_pkg = {}
            continue
        if ":" in line:
            prefix, val = line.split(":", 1)
            current_pkg[prefix] = val

    if "P" in current_pkg and "V" in current_pkg:
        remote_pkgs.append(current_pkg)

    print(f"  Found {len(remote_pkgs)} packages in remote index.")
    for pkg in remote_pkgs:
        pname = pkg.get("P")
        pver = pkg.get("V")
        if not pname or not pver:
            continue
        if pname in skip_pkgs:
            print(f"  Skipping remote {pname} (queued for rebuild)")
            continue

        apk_name = f"{pname}-{pver}.apk"
        local_apk = os.path.join(arch_dir, apk_name)
        if os.path.isfile(local_apk):
            continue

        pkg_url = f"{remote_url.rstrip('/')}/{arch}/{apk_name}"
        print(f"  Fetching existing package: {apk_name} ...")
        try:
            req = urllib.request.Request(pkg_url, headers={"User-Agent": "esp-linux-packages-builder/1.0"})
            with urllib.request.urlopen(req, timeout=15) as resp, open(local_apk, "wb") as f:
                f.write(resp.read())
        except Exception as e:
            print(f"  Warning: Failed to download {pkg_url}: {e}")


def clean_package_files(pkg_dir):
    """
    Remove compiled binaries from package files/ directory.
    """
    files_dir = os.path.join(pkg_dir, "files")
    if not os.path.isdir(files_dir):
        return
    # Check for known binary targets
    for sub in ["usr/bin", "usr/sbin", "bin", "sbin"]:
        d = os.path.join(files_dir, sub)
        if os.path.isdir(d):
            for fname in os.listdir(d):
                fpath = os.path.join(d, fname)
                if os.path.isfile(fpath):
                    with open(fpath, "rb") as test_f:
                        magic = test_f.read(4)
                        if magic == b"\x7fELF":
                            print(f"  Cleaned binary: {fpath}")
                            os.remove(fpath)


def main():
    parser = argparse.ArgumentParser(description="Build APK repository and GitHub Pages site")
    parser.add_argument("--packages-dir", default=os.path.join(REPO_ROOT, "packages"), help="Packages directory")
    parser.add_argument("--out-dir", default=os.path.join(REPO_ROOT, "_site"), help="Output directory for site")
    parser.add_argument("--arch", default="xtensa", help="Target architecture")
    parser.add_argument("--packages", nargs="*", default=None, help="Explicit list of packages to build")
    parser.add_argument("--changed-only", action="store_true", help="Build only modified or newly added packages")
    parser.add_argument("--base-ref", default=None, help="Git base ref for change detection (e.g. origin/main, HEAD~1)")
    parser.add_argument("--sync-remote", default=None, help="Remote repository URL to sync existing packages from")
    parser.add_argument("--clean", action="store_true", help="Clean compiled binaries from package files/ dirs")

    args = parser.parse_args()

    arch_dir = os.path.join(args.out_dir, args.arch)
    os.makedirs(arch_dir, exist_ok=True)

    all_available = sorted([
        p for p in os.listdir(args.packages_dir)
        if os.path.isdir(os.path.join(args.packages_dir, p))
        and os.path.isfile(os.path.join(args.packages_dir, p, "package.conf"))
    ])

    if args.clean:
        print(">>> Cleaning compiled binaries from packages/...")
        for p in all_available:
            clean_package_files(os.path.join(args.packages_dir, p))
        if not args.packages and not args.changed_only:
            return

    # Determine which packages to build
    targets = []
    if args.packages is not None and len(args.packages) > 0:
        targets = [p for p in args.packages if p in all_available]
        print(f">>> Targeted package build requested: {targets}")
    elif args.changed_only:
        changed = get_changed_packages(args.packages_dir, args.base_ref)
        targets = [p for p in changed if p in all_available]
        print(f">>> Detected changed packages via git diff ({args.base_ref or 'HEAD~1'}..HEAD): {targets}")
    else:
        targets = all_available
        print(f">>> Full build requested ({len(targets)} packages)")

    # Sync existing remote packages to prevent losing previously built packages
    if args.sync_remote:
        sync_remote_packages(args.sync_remote, args.arch, arch_dir, skip_pkgs=set(targets))

    built_count = 0
    failed_pkgs = []

    for name in targets:
        p_dir = os.path.join(args.packages_dir, name)
        conf_file = os.path.join(p_dir, "package.conf")
        conf = load_conf(conf_file)

        ver = conf.get("PKG_VER", "1.0-r1")
        desc = conf.get("PKG_DESC", "ESP32 package")
        arch = conf.get("PKG_ARCH", args.arch)
        url = conf.get("PKG_URL", "https://github.com/canusdev/esp-linux")
        license_str = conf.get("PKG_LICENSE", "GPL")
        deps = conf.get("PKG_DEPS", "").split()

        files_dir = os.path.join(p_dir, "files")
        build_sh = os.path.join(p_dir, "build.sh")

        print(f"\n==========================================")
        print(f"📦 Processing: {name} (version {ver}, arch {arch})")
        print(f"==========================================")

        # Run build.sh if it exists
        if os.path.isfile(build_sh):
            print(f">>> Executing build.sh for {name}...")
            res = subprocess.run(["bash", "build.sh"], cwd=p_dir)
            if res.returncode != 0:
                print(f"❌ Error: build.sh for {name} failed with exit code {res.returncode}")
                failed_pkgs.append(name)
                continue

        if not os.path.isdir(files_dir) or not os.listdir(files_dir):
            print(f"⚠️  Notice: No files in {files_dir} to package, skipping {name}")
            continue

        # Remove any older versions of this package in arch_dir
        for old_apk in glob.glob(os.path.join(arch_dir, f"{name}-*.apk")):
            print(f"  Removing older/existing package: {os.path.basename(old_apk)}")
            os.remove(old_apk)

        out_apk = os.path.join(arch_dir, f"{name}-{ver}.apk")
        print(f">>> Packaging {name} ({ver}) -> {out_apk}")

        cmd = [
            sys.executable, MAKE_APK,
            "--name", name,
            "--version", ver,
            "--desc", desc,
            "--arch", arch,
            "--url", url,
            "--license", license_str,
            "--data-dir", files_dir,
            "--output", out_apk
        ]
        for d in deps:
            cmd.extend(["--depend", d])

        pre_inst = os.path.join(p_dir, "pre-install.sh")
        post_inst = os.path.join(p_dir, "post-install.sh")
        if os.path.isfile(pre_inst): cmd.extend(["--pre-install", pre_inst])
        if os.path.isfile(post_inst): cmd.extend(["--post-install", post_inst])

        subprocess.check_call(cmd)
        built_count += 1

        # Clean binary from files/ after packaging to ensure working tree stays clean
        clean_package_files(p_dir)

    print(f"\n>>> Rebuilding repository index and site...")
    # Generate APKINDEX across all packages currently in arch_dir
    apkindex_path = os.path.join(arch_dir, "APKINDEX.tar.gz")
    subprocess.check_call([sys.executable, MAKE_INDEX, "--dir", arch_dir, "--output", apkindex_path])

    # Generate index.html dashboard
    index_html_path = os.path.join(args.out_dir, "index.html")
    subprocess.check_call([sys.executable, GEN_HTML, "--index", apkindex_path, "--output", index_html_path])

    print(f"\n✨ Summary: {built_count} package(s) built/updated.")
    total_apks = len(glob.glob(os.path.join(arch_dir, "*.apk")))
    print(f"   Total packages available in {args.arch}: {total_apks}")
    print(f"   Index ready at: {apkindex_path}")
    print(f"   Site ready at:  {index_html_path}")

    if failed_pkgs:
        print(f"❌ Failed packages: {', '.join(failed_pkgs)}")
        sys.exit(1)


if __name__ == "__main__":
    main()
