#!/usr/bin/python3
"""生成 deb/deb-src 索引、by-hash 和签名；保留旧 pool 防止升级中途 404。"""
import argparse
from datetime import datetime, timedelta, timezone
import gzip
import hashlib
import json
import lzma
from pathlib import Path
import shutil
import subprocess


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--packages", type=Path, required=True)
    parser.add_argument("--site", type=Path, required=True)
    parser.add_argument("--fingerprint", required=True)
    args = parser.parse_args()
    root = Path(__file__).resolve().parents[1]
    config = json.loads((root / "stack.json").read_text())
    site = args.site.resolve()
    site.mkdir(parents=True, exist_ok=True)
    pool = site / "pool/main"
    pool.mkdir(parents=True, exist_ok=True)
    accepted = {".deb", ".dsc"}
    count = 0
    for file in args.packages.rglob("*"):
        if not file.is_file() or file.is_symlink() or not (file.suffix in accepted or file.name.endswith(".tar.xz")):
            continue
        source = file.name.split("_", 1)[0]
        if source not in {c["package"] for c in config["components"].values()} | {"grd-handover-stack"} and file.suffix != ".deb":
            raise ValueError(f"意外的源码包 {file.name}")
        if file.suffix == ".deb":
            fields = subprocess.check_output(["dpkg-deb", "-f", str(file), "Source"], text=True).strip()
            source = fields.split()[0] if fields else subprocess.check_output(["dpkg-deb", "-f", str(file), "Package"], text=True).strip()
        dest = pool / source[0] / source / file.name
        dest.parent.mkdir(parents=True, exist_ok=True)
        if dest.exists() and hashlib.sha256(dest.read_bytes()).digest() != hashlib.sha256(file.read_bytes()).digest():
            raise ValueError(f"拒绝覆盖同版本但内容不同的包 {file.name}")
        shutil.copy2(file, dest)
        count += 1
    if not list(pool.rglob("*.deb")) or not list(pool.rglob("*.dsc")):
        raise ValueError("APT 源必须同时包含二进制与对应源码")
    # 初期保留所有已发布文件；容量达到 Pages 上限前失败，而不偷偷删除客户端正在使用的包。
    size = sum(p.stat().st_size for p in site.rglob("*") if p.is_file() and not p.is_symlink())
    if size > 900 * 1024 * 1024:
        raise ValueError("APT 源超过 900 MiB；请先规划历史包归档，避免 GitHub Pages 超限")
    dist = site / "dists" / config["suite"]
    for folder, name, command in (("main/binary-amd64", "Packages", "packages"), ("main/source", "Sources", "sources")):
        directory = dist / folder
        directory.mkdir(parents=True, exist_ok=True)
        data = subprocess.check_output(["apt-ftparchive", command, "pool"], cwd=site)
        (directory / name).write_bytes(data)
        (directory / (name + ".gz")).write_bytes(gzip.compress(data, mtime=0))
        (directory / (name + ".xz")).write_bytes(lzma.compress(data))
        for filename in (name, name + ".gz", name + ".xz"):
            file = directory / filename
            for algorithm in ("SHA256", "SHA512"):
                digest = hashlib.new(algorithm.lower(), file.read_bytes()).hexdigest()
                target = directory / "by-hash" / algorithm / digest
                target.parent.mkdir(parents=True, exist_ok=True)
                shutil.copy2(file, target)
    now = datetime.now(timezone.utc)
    settings = {"Origin": "AltarsCN-GRD", "Label": "AltarsCN GRD stack", "Suite": config["suite"],
                "Codename": config["suite"], "Architectures": "amd64", "Components": "main",
                "Description": "Patched GNOME remote desktop stack for Ubuntu 26.04", "Acquire-By-Hash": "yes"}
    command = ["apt-ftparchive"]
    for key, value in settings.items():
        command += ["-o", f"APT::FTPArchive::Release::{key}={value}"]
    command += ["release", str(dist.relative_to(site))]
    # 避免将前一轮签名文件或 Release 本身列入新 Release 的哈希清单。
    for filename in ("Release", "InRelease", "Release.gpg"):
        (dist / filename).unlink(missing_ok=True)
    release = subprocess.check_output(command, cwd=site)
    # 明确列出可过期的发布索引；每日 Action 即使源码不变也刷新签名。
    expires = (now + timedelta(days=30)).strftime("%a, %d %b %Y %H:%M:%S +0000")
    release = b"\n".join(line for line in release.split(b"\n") if not line.startswith(b"Date:"))
    release = f'Date: {now.strftime("%a, %d %b %Y %H:%M:%S +0000")}\nValid-Until: {expires}\n'.encode() + release
    (dist / "Release").write_bytes(release)
    for target, mode in (("InRelease", "--clearsign"), ("Release.gpg", "--detach-sign")):
        subprocess.run(["gpg", "--batch", "--yes", "--armor", "--local-user", args.fingerprint, "--output", str(dist / target), mode, str(dist / "Release")], check=True)
    for file in (root / "apt").iterdir():
        if file.is_file():
            shutil.copy2(file, site / file.name)
    (site / ".nojekyll").touch()
    print(f"APT 索引已签名：本次复制 {count} 个文件，pool 包括历史版本。")


if __name__ == "__main__":
    main()
