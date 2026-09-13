#!/usr/bin/env python3
"""
build-repo.py - Master repository builder for esp-linux-packages.
Builds all packages, generates APKINDEX.tar.gz, and creates GitHub Pages _site/index.html.
"""

import argparse
import os
import subprocess
import sys

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


def main():
    parser = argparse.ArgumentParser(description="Build APK repository and GitHub Pages site")
    parser.add_argument("--packages-dir", default=os.path.join(REPO_ROOT, "packages"), help="Packages directory")
    parser.add_argument("--out-dir", default=os.path.join(REPO_ROOT, "_site"), help="Output directory for site")
    parser.add_argument("--arch", default="xtensa", help="Target architecture")

    args = parser.parse_args()

    arch_dir = os.path.join(args.out_dir, args.arch)
    os.makedirs(arch_dir, exist_ok=True)

    pkgs = sorted(os.listdir(args.packages_dir))
    built_count = 0

    print(f"=== Building packages from {args.packages_dir} ===")
    for p in pkgs:
        p_dir = os.path.join(args.packages_dir, p)
        if not os.path.isdir(p_dir):
            continue
        conf_file = os.path.join(p_dir, "package.conf")
        if not os.path.isfile(conf_file):
            continue

        conf = load_conf(conf_file)
        name = conf.get("PKG_NAME", p)
        ver = conf.get("PKG_VER", "1.0-r1")
        desc = conf.get("PKG_DESC", "ESP32 package")
        arch = conf.get("PKG_ARCH", args.arch)
        url = conf.get("PKG_URL", "https://github.com/canusdev/esp-linux")
        license_str = conf.get("PKG_LICENSE", "GPL")
        deps = conf.get("PKG_DEPS", "").split()

        files_dir = os.path.join(p_dir, "files")
        build_sh = os.path.join(p_dir, "build.sh")

        # Run build.sh if present and files/ not populated
        if os.path.isfile(build_sh) and not os.path.isdir(files_dir):
            print(f">>> Running build.sh for {name}...")
            res = subprocess.run(["bash", build_sh], cwd=p_dir)
            if res.returncode != 0:
                print(f"  Warning: build.sh for {name} failed or needs toolchain, skipping packaging")
                continue

        if not os.path.isdir(files_dir) or not os.listdir(files_dir):
            print(f"  Notice: No files in {files_dir} to package, skipping {name}")
            continue

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

    # Generate APKINDEX
    print("\n>>> Generating APKINDEX.tar.gz...")
    apkindex_path = os.path.join(arch_dir, "APKINDEX.tar.gz")
    subprocess.check_call([sys.executable, MAKE_INDEX, "--dir", arch_dir, "--output", apkindex_path])

    # Generate index.html
    print("\n>>> Generating GitHub Pages dashboard...")
    index_html_path = os.path.join(args.out_dir, "index.html")
    subprocess.check_call([sys.executable, GEN_HTML, "--index", apkindex_path, "--output", index_html_path])

    print(f"\n✅ Build complete! {built_count} packages in {arch_dir}")
    print(f"   Site ready at: {args.out_dir}/index.html")


if __name__ == "__main__":
    main()
