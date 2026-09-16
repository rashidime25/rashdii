#!/usr/bin/env python3
"""Download Xray-core for local testing (Linux x64)."""
import os
import shutil
import sys
import urllib.request
import zipfile

# Keep this in sync with the Dockerfile's ARG XRAY_VERSION (pinned on purpose:
# `latest` is what silently broke REALITY once). Pass a version to override:
#   python3 scripts/fetch_xray.py 26.7.28
DEFAULT_VERSION = os.environ.get("TITAN_XRAY_VERSION", "26.9.9")
DEST = os.environ.get("XRAY_DEST", "/usr/local/bin")
ASSETS = os.environ.get("XRAY_ASSETS", "/usr/local/share/xray")


def main(version: str | None = None):
    version = version or DEFAULT_VERSION
    url = f"https://github.com/XTLS/Xray-core/releases/download/v{version}/Xray-linux-64.zip"
    os.makedirs(DEST, exist_ok=True)
    os.makedirs(ASSETS, exist_ok=True)
    print(f"Downloading Xray-core v{version} …")
    zip_path = "/tmp/xray.zip"
    urllib.request.urlretrieve(url, zip_path)
    with zipfile.ZipFile(zip_path) as z:
        z.extractall("/tmp/xray-extract")
    for name in ("geoip.dat", "geosite.dat"):
        shutil.move(f"/tmp/xray-extract/{name}", os.path.join(ASSETS, name))
    shutil.move("/tmp/xray-extract/xray", os.path.join(DEST, "xray"))
    os.chmod(os.path.join(DEST, "xray"), 0o755)
    shutil.rmtree("/tmp/xray-extract", ignore_errors=True)
    print("Xray installed at", os.path.join(DEST, "xray"), "| assets:", ASSETS)
    print("Set XRAY_LOCATION_ASSET=" + ASSETS + " so geosite/geoip rules resolve.")

if __name__ == "__main__":
    main(sys.argv[1] if len(sys.argv) > 1 else None)
