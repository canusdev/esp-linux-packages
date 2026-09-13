# 📦 ESP32-S3 Linux APK Packages Repository

An automated package repository for **Linux on ESP32-S3** (Xtensa NOMMU), providing binary `.apk` packages compatible with OpenWrt and Alpine Linux `apk-tools`.

Packages are defined modularly folder-by-folder under [`packages/`](packages/), containing **only source code and build recipes** (no compiled binaries in git). Compilation is handled automatically and incrementally via **GitHub Actions CI**, and served via **GitHub Pages**.

---

## 🚀 Quick Start: Using on ESP32-S3

### 1. Configure the Repository
Ensure your ESP32-S3 is connected to Wi-Fi or Ethernet, then add this repository to `/etc/apk/repositories`:

```sh
echo "https://canusdev.github.io/esp-linux-packages/xtensa" >> /etc/apk/repositories
```

### 2. Update and Install Packages
```sh
# Update package index from GitHub Pages
apk update

# List available packages
apk list

# Install packages
apk add espctl sysinfo web-dashboard mqtt-server mqtt-client

# Check installed package status
apk info espctl
```

> [!TIP]
> When booted from internal SPI Flash (`cramfs`), rootfs is read-only. `apk` automatically detects this and installs packages into `/opt` (SD card storage), which is already added to `$PATH`!

---

## 📁 Repository Structure

```
esp-linux-packages/
├── .github/
│   └── workflows/
│       └── build-and-deploy.yml    # CI/CD pipeline: incremental build & publish to Pages
├── packages/                       # Package definitions (folder by folder)
│   ├── espctl/
│   │   ├── package.conf            # Metadata (name, version, arch, description)
│   │   ├── src/espctl.c            # Source code
│   │   └── build.sh                # Compilation recipe
│   ├── mqtt-server/
│   │   ├── package.conf
│   │   ├── src/mqtt_server.c
│   │   ├── files/etc/...           # Configs & init scripts
│   │   └── build.sh
│   ├── mqtt-client/
│   │   ├── package.conf
│   │   ├── src/                    # mqtt_pub.c, mqtt_sub.c
│   │   └── build.sh
│   ├── sysinfo/                    # Architecture-independent (noarch) script
│   │   ├── package.conf
│   │   └── files/usr/bin/sysinfo
│   └── web-dashboard/              # HTML/CGI dashboard (noarch)
│       ├── package.conf
│       └── files/home/root/www/...
├── tools/
│   ├── make-apk.py                 # Generates .apk packages with .PKGINFO
│   ├── make-apkindex.py            # Generates APKINDEX.tar.gz
│   ├── generate-index-html.py      # Generates modern GitHub Pages dashboard
│   └── build-repo.py               # Master repository builder with incremental detection
├── build.sh                        # Local build script with selective & changed-only support
└── README.md
```

---

## ⚙️ Incremental CI & Source-Only Architecture

- **Zero Binaries in Git:** All binary ELFs and `.apk` archives are excluded from git tracking. Only C sources, scripts, and build configurations are stored.
- **Incremental Compilation:** GitHub Actions CI detects which packages are modified or newly added (via `git diff`). Only those changed packages are compiled. Unchanged packages are preserved on GitHub Pages.
- **Automated Toolchain:** The Xtensa uClibc FDPIC toolchain is hosted on GitHub Releases (`toolchain-v1`) and cached in GitHub Actions.

---

## 🛠️ How to Add a New Package

Adding a new package to the repository is as simple as creating a new folder under `packages/`:

### Step 1: Create the Package Directory
```bash
mkdir -p packages/my-app/src
```

### Step 2: Create `package.conf`
Create `packages/my-app/package.conf`:
```ini
PKG_NAME="my-app"
PKG_VER="1.0-r1"
PKG_DESC="My awesome utility for ESP32-S3 Linux"
PKG_ARCH="xtensa"                  # or "noarch" for scripts/web files
PKG_URL="https://github.com/canusdev/esp-linux"
PKG_LICENSE="MIT"
PKG_DEPS=""                        # Optional: space-separated dependencies
```

### Step 3: Add Source Code and `build.sh`
For C/C++ applications, place source files in `packages/my-app/src/` and create `packages/my-app/build.sh`:
```bash
#!/usr/bin/env bash
set -euo pipefail
pkg_dir=$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")" && pwd)
tc_gcc="${CROSS_COMPILE:-}gcc"

mkdir -p "$pkg_dir/files/usr/bin"
"$tc_gcc" -Os -mfdpic -mauto-litpools -fPIC -ffunction-sections -fdata-sections -Wl,--gc-sections \
    "$pkg_dir/src/my_app.c" -o "$pkg_dir/files/usr/bin/my-app"

# Strip binary
tc_strip="${tc_gcc%gcc}strip"
if command -v "$tc_strip" >/dev/null 2>&1; then
    "$tc_strip" "$pkg_dir/files/usr/bin/my-app"
fi
```
*(For shell scripts or web assets (`PKG_ARCH="noarch"`), simply place the files in `packages/my-app/files/` directly without a `build.sh`.)*

### Step 4: Test Locally
```bash
# Build only your new package
./build.sh my-app

# Or build all changed packages
./build.sh --changed
```

### Step 5: Push to GitHub
```bash
git add packages/my-app/
git commit -m "feat(pkg): add my-app package"
git push origin main
```
GitHub Actions will automatically compile **only `my-app`**, add it to `APKINDEX.tar.gz`, and deploy to GitHub Pages!

---

## 🌐 GitHub Pages Configuration

To activate GitHub Pages for your repository:
1. Go to your repository on GitHub -> **Settings** -> **Pages**.
2. Under **Build and deployment** -> **Source**, select **GitHub Actions**.
3. Every push to the `main` branch will automatically compile changed packages and publish the repository to:
   `https://canusdev.github.io/esp-linux-packages/`

---

## 💻 Local Testing & Preview

To build and preview the repository web dashboard locally:
```bash
# Build specific packages
./build.sh espctl mqtt-server

# Build only changed packages
./build.sh --changed

# Clean compiled binaries from files/
./build.sh clean

# Preview locally
python3 -m http.server -d _site 8080
```
Open `http://localhost:8080` in your browser to view the generated repository dashboard.

---

## 📡 MQTT Packages Usage Example

### 1. Install MQTT Server and Client
```sh
apk add mqtt-server mqtt-client
```

### 2. Start the MQTT Broker
```sh
# Run in background
mqtt-server -d -p 1883

# Or via init script
/etc/init.d/S50mqtt-server start
/etc/init.d/S50mqtt-server status
```

### 3. Subscribe & Publish
```sh
# Stream messages
mqtt-sub -t "esp32/#" -v &

# Publish data
mqtt-pub -t "esp32/sensors/temp" -m "24.5"
```
