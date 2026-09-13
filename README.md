# 📦 ESP32-S3 Linux APK Packages Repository

An automated package repository for **Linux on ESP32-S3** (Xtensa NOMMU), providing binary `.apk` packages compatible with OpenWrt and Alpine Linux `apk-tools`.

Packages are defined modularly folder-by-folder under [`packages/`](packages/), automatically compiled/packaged via **GitHub Actions CI**, and hosted via **GitHub Pages**.

---

## 🚀 Quick Start: Using on ESP32-S3

### 1. Configure the Repository
Ensure your ESP32-S3 is connected to Wi-Fi or Ethernet, then add this repository to `/etc/apk/repositories`:

```sh
echo "https://<your-username>.github.io/esp-linux-packages/xtensa" >> /etc/apk/repositories
```

### 2. Update and Install Packages
```sh
# Update package index from GitHub Pages
apk update

# List available packages
apk list

# Install packages
apk add espctl sysinfo esp32-web-dashboard

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
│       └── build-and-deploy.yml    # CI/CD pipeline building & publishing to Pages
├── packages/                       # Package definitions (folder by folder)
│   ├── espctl/
│   │   ├── package.conf            # Metadata (name, version, arch, description)
│   │   └── files/                  # Target filesystem files
│   │       └── usr/bin/espctl
│   ├── sysinfo/
│   │   ├── package.conf
│   │   └── files/
│   │       └── usr/bin/sysinfo
│   ├── web-dashboard/
│   │   ├── package.conf
│   │   └── files/
│   │       └── home/root/www/...
│   ├── dash/                       # Source-built package recipe
│   │   ├── package.conf
│   │   └── build.sh
│   └── ...
├── tools/
│   ├── make-apk.py                 # Generates .apk packages with .PKGINFO
│   ├── make-apkindex.py            # Generates APKINDEX.tar.gz
│   ├── generate-index-html.py      # Generates GitHub Pages dashboard
│   └── build-repo.py               # Master repository builder
├── build.sh                        # Local build script
└── README.md
```

---

## 🛠️ How to Add a New Package

Adding a new package to the repository is as simple as creating a new folder under `packages/`:

### Step 1: Create the Package Directory
```bash
mkdir -p packages/my-app/files/usr/bin
```

### Step 2: Create `package.conf`
Create `packages/my-app/package.conf`:
```ini
PKG_NAME="my-app"
PKG_VER="1.0-r1"
PKG_DESC="My awesome utility for ESP32-S3 Linux"
PKG_ARCH="xtensa"                  # or "noarch" for scripts/web files
PKG_URL="https://github.com/myuser/my-app"
PKG_LICENSE="MIT"
PKG_DEPS=""                        # Optional: space-separated dependencies
```

### Step 3: Add Files
Place your pre-compiled executable, script, or configuration files in `packages/my-app/files/`:
```bash
cp /path/to/my-binary packages/my-app/files/usr/bin/my-app
chmod +x packages/my-app/files/usr/bin/my-app
```

*(Optional)* You can also provide `pre-install.sh`, `post-install.sh`, `pre-deinstall.sh`, or `post-deinstall.sh` scripts in `packages/my-app/`.

### Step 4: Test Locally
```bash
./build.sh
```
This will compile/package all packages and generate the static site in `_site/`.

### Step 5: Push to GitHub
```bash
git add packages/my-app/
git commit -m "feat(pkg): add my-app package"
git push origin main
```
GitHub Actions will automatically build the package, update `APKINDEX.tar.gz`, and deploy to GitHub Pages!

---

## 🌐 GitHub Pages Configuration

To activate GitHub Pages for your repository:
1. Go to your repository on GitHub -> **Settings** -> **Pages**.
2. Under **Build and deployment** -> **Source**, select **GitHub Actions**.
3. Every push to the `main` branch will automatically build and publish the packages to:
   `https://<username>.github.io/esp-linux-packages/`

---

## 💻 Local Testing & Preview

To build and preview the repository web dashboard locally:
```bash
./build.sh
python3 -m http.server -d _site 8080
```
Open `http://localhost:8080` in your browser to view the generated repository dashboard.
