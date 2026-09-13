#!/usr/bin/env python3
"""
generate-index-html.py - Generate a sleek, modern GitHub Pages dashboard for esp-linux-packages.
"""

import argparse
import os
import sys
import tarfile
import time


def format_size(bytes_val):
    try:
        b = float(bytes_val)
        if b >= 1048576:
            return f"{b / 1048576:.1f} MB"
        if b >= 1024:
            return f"{b / 1024:.1f} KB"
        return f"{int(b)} B"
    except (ValueError, TypeError):
        return str(bytes_val)


def parse_apkindex(index_path):
    packages = []
    if not os.path.isfile(index_path):
        return packages

    with tarfile.open(index_path, "r:gz") as tar:
        for member in tar.getmembers():
            if member.name == "APKINDEX":
                f = tar.extractfile(member)
                if not f:
                    continue
                content = f.read().decode("utf-8", errors="ignore")
                for block in content.strip().split("\n\n"):
                    pkg = {}
                    for line in block.splitlines():
                        if line.startswith("P:"): pkg["name"] = line[2:].strip()
                        elif line.startswith("V:"): pkg["version"] = line[2:].strip()
                        elif line.startswith("A:"): pkg["arch"] = line[2:].strip()
                        elif line.startswith("S:"): pkg["size"] = line[2:].strip()
                        elif line.startswith("I:"): pkg["installed_size"] = line[2:].strip()
                        elif line.startswith("T:"): pkg["desc"] = line[2:].strip()
                        elif line.startswith("U:"): pkg["url"] = line[2:].strip()
                        elif line.startswith("L:"): pkg["license"] = line[2:].strip()
                        elif line.startswith("D:"): pkg["deps"] = line[2:].strip()
                    if "name" in pkg:
                        packages.append(pkg)
    return packages


def generate_html(packages, repo_name="esp-linux-packages"):
    build_time = time.strftime("%Y-%m-%d %H:%M:%S UTC", time.gmtime())

    rows_html = ""
    for p in packages:
        name = p.get("name", "")
        ver = p.get("version", "")
        arch = p.get("arch", "xtensa")
        size = format_size(p.get("size", 0))
        isize = format_size(p.get("installed_size", 0))
        desc = p.get("desc", "")
        pkg_file = f"xtensa/{name}-{ver}.apk"

        rows_html += f"""
        <tr>
            <td class="pkg-name"><strong>{name}</strong></td>
            <td><span class="badge badge-ver">{ver}</span></td>
            <td><span class="badge badge-arch">{arch}</span></td>
            <td>{size} <small class="text-muted">({isize} inst)</small></td>
            <td>{desc}</td>
            <td><a href="{pkg_file}" class="btn-download" download>Download</a></td>
        </tr>
        """

    if not rows_html:
        rows_html = '<tr><td colspan="6" style="text-align:center; padding: 2rem;">No packages found in repository.</td></tr>'

    html = f"""<!DOCTYPE html>
<html lang="en">
<head>
    <meta charset="UTF-8">
    <meta name="viewport" content="width=device-width, initial-scale=1.0">
    <title>ESP32-S3 Linux APK Package Repository</title>
    <style>
        :root {{
            --bg-color: #0f172a;
            --card-bg: #1e293b;
            --card-border: #334155;
            --text-color: #e2e8f0;
            --text-muted: #94a3b8;
            --accent-color: #38bdf8;
            --accent-hover: #0ea5e9;
            --badge-bg: #0369a1;
            --badge-text: #e0f2fe;
            --code-bg: #0b1120;
            --success: #10b981;
        }}
        * {{
            box-sizing: border-box;
            margin: 0;
            padding: 0;
        }}
        body {{
            font-family: -apple-system, BlinkMacSystemFont, "Segoe UI", Roboto, Oxygen, Ubuntu, Cantarell, sans-serif;
            background-color: var(--bg-color);
            color: var(--text-color);
            line-height: 1.6;
            padding: 2rem 1rem;
        }}
        .container {{
            max-width: 1100px;
            margin: 0 auto;
        }}
        header {{
            text-align: center;
            margin-bottom: 2.5rem;
        }}
        h1 {{
            font-size: 2.2rem;
            color: #fff;
            margin-bottom: 0.5rem;
            display: flex;
            align-items: center;
            justify-content: center;
            gap: 0.75rem;
        }}
        .header-desc {{
            color: var(--text-muted);
            font-size: 1.1rem;
            max-width: 700px;
            margin: 0 auto;
        }}
        .card {{
            background: var(--card-bg);
            border: 1px solid var(--card-border);
            border-radius: 12px;
            padding: 1.5rem;
            margin-bottom: 2rem;
            box-shadow: 0 4px 6px -1px rgba(0, 0, 0, 0.2);
        }}
        h2 {{
            font-size: 1.3rem;
            margin-bottom: 1rem;
            color: var(--accent-color);
        }}
        pre, code {{
            font-family: ui-monospace, SFMono-Regular, Menlo, Monaco, Consolas, monospace;
            font-size: 0.9rem;
        }}
        pre {{
            background: var(--code-bg);
            border: 1px solid var(--card-border);
            padding: 1rem;
            border-radius: 8px;
            overflow-x: auto;
            color: #38bdf8;
            margin: 0.5rem 0 1rem;
        }}
        .search-box {{
            width: 100%;
            padding: 0.75rem 1rem;
            background: var(--code-bg);
            border: 1px solid var(--card-border);
            border-radius: 8px;
            color: #fff;
            font-size: 1rem;
            margin-bottom: 1rem;
            outline: none;
        }}
        .search-box:focus {{
            border-color: var(--accent-color);
        }}
        table {{
            width: 100%;
            border-collapse: collapse;
            text-align: left;
        }}
        th, td {{
            padding: 0.85rem 1rem;
            border-bottom: 1px solid var(--card-border);
        }}
        th {{
            color: var(--text-muted);
            font-weight: 600;
            font-size: 0.85rem;
            text-transform: uppercase;
            letter-spacing: 0.05em;
        }}
        tr:hover td {{
            background: rgba(255, 255, 255, 0.02);
        }}
        .badge {{
            display: inline-block;
            padding: 0.2rem 0.6rem;
            border-radius: 9999px;
            font-size: 0.8rem;
            font-weight: 500;
        }}
        .badge-ver {{
            background: rgba(56, 189, 248, 0.15);
            color: #38bdf8;
            border: 1px solid rgba(56, 189, 248, 0.3);
        }}
        .badge-arch {{
            background: rgba(16, 185, 129, 0.15);
            color: #34d399;
            border: 1px solid rgba(16, 185, 129, 0.3);
        }}
        .btn-download {{
            display: inline-block;
            background: var(--accent-color);
            color: #0f172a;
            padding: 0.35rem 0.8rem;
            border-radius: 6px;
            text-decoration: none;
            font-weight: 600;
            font-size: 0.85rem;
            transition: background 0.15s;
        }}
        .btn-download:hover {{
            background: var(--accent-hover);
        }}
        .text-muted {{
            color: var(--text-muted);
        }}
        footer {{
            text-align: center;
            color: var(--text-muted);
            font-size: 0.85rem;
            margin-top: 3rem;
        }}
    </style>
</head>
<body>
    <div class="container">
        <header>
            <h1>⚡ ESP32-S3 Linux APK Repository</h1>
            <p class="header-desc">
                OpenWrt / Alpine compatible binary packages for Linux on ESP32-S3 (Xtensa NOMMU).
            </p>
        </header>

        <div class="card">
            <h2>🚀 Quick Setup on ESP32-S3 Board</h2>
            <p>1. Connect your ESP32-S3 to Wi-Fi or Ethernet, then add this repository to <code>/etc/apk/repositories</code>:</p>
            <pre><code id="repo-cmd">echo "$REPO_URL/xtensa" &gt;&gt; /etc/apk/repositories</code></pre>
            <p>2. Update package index and install packages:</p>
            <pre><code>apk update
apk add espctl sysinfo</code></pre>
            <small class="text-muted">Tip: If running from read-only SPI Flash (cramfs), <code>apk</code> automatically installs into <code>/opt</code> on your MicroSD card!</small>
        </div>

        <div class="card">
            <h2>📦 Available Packages ({len(packages)})</h2>
            <input type="text" id="search" class="search-box" placeholder="Filter packages by name, description, or keyword..." onkeyup="filterTable()">
            <div style="overflow-x: auto;">
                <table id="pkg-table">
                    <thead>
                        <tr>
                            <th>Package</th>
                            <th>Version</th>
                            <th>Arch</th>
                            <th>Size</th>
                            <th>Description</th>
                            <th>Action</th>
                        </tr>
                    </thead>
                    <tbody>
                        {rows_html}
                    </tbody>
                </table>
            </div>
        </div>

        <footer>
            <p>Generated automatically via GitHub Actions • Last updated: {build_time}</p>
            <p>Powered by <a href="https://github.com/canusdev/esp-linux" style="color: var(--accent-color);">esp-linux</a></p>
        </footer>
    </div>

    <script>
        // Set dynamic repository URL in quick setup code block
        const curUrl = window.location.href.split('?')[0].replace(/\\/index\\.html$/, '').replace(/\\/$/, '');
        const repoCmd = document.getElementById('repo-cmd');
        if (repoCmd && curUrl.startsWith('http')) {{
            repoCmd.innerText = `echo "${{curUrl}}/xtensa" >> /etc/apk/repositories`;
        }}

        function filterTable() {{
            const input = document.getElementById("search");
            const filter = input.value.toLowerCase();
            const table = document.getElementById("pkg-table");
            const tr = table.getElementsByTagName("tr");

            for (let i = 1; i < tr.length; i++) {{
                const text = tr[i].textContent || tr[i].innerText;
                if (text.toLowerCase().indexOf(filter) > -1) {{
                    tr[i].style.display = "";
                }} else {{
                    tr[i].style.display = "none";
                }}
            }}
        }}
    </script>
</body>
</html>
"""
    return html


def main():
    parser = argparse.ArgumentParser(description="Generate index.html for APK repository")
    parser.add_argument("--index", "-i", required=True, help="Path to APKINDEX.tar.gz")
    parser.add_argument("--output", "-o", required=True, help="Path to output index.html")
    parser.add_argument("--repo-name", default="esp-linux-packages", help="Repository title")

    args = parser.parse_args()

    packages = parse_apkindex(args.index)
    html_content = generate_html(packages, args.repo_name)

    os.makedirs(os.path.dirname(os.path.abspath(args.output)), exist_ok=True)
    with open(args.output, "w", encoding="utf-8") as f:
        f.write(html_content)

    print(f"Generated dashboard: {args.output} ({len(packages)} packages listed)")


if __name__ == "__main__":
    main()
