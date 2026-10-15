#!/usr/bin/python3
"""校验源码哈希并恢复可分发的 quilt 源包；不安装依赖。"""
import argparse
import hashlib
import json
from pathlib import Path
import shutil
import subprocess
import tarfile


def unpack(archive, directory):
    directory.mkdir(parents=True, exist_ok=False)
    with tarfile.open(archive) as tf:
        tf.extractall(directory, filter="data")
        # Python 3.14 会删去链接末尾的 /，quilt 却需要原始文本一致。
        # 只恢复安全过滤后语义完全相同的末尾 /，仍拒绝越界链接。
        for member in tf.getmembers():
            if member.issym() and member.linkname.endswith("/"):
                safe = tarfile.data_filter(member, str(directory))
                path = directory / safe.name
                if safe.linkname == member.linkname.rstrip("/") and path.is_symlink():
                    path.unlink()
                    path.symlink_to(member.linkname)
    roots = list(directory.iterdir())
    if len(roots) != 1 or not roots[0].is_dir():
        raise ValueError("源码档案必须仅有一个顶层目录")
    return roots[0]


def fetch(url, path, expected=None):
    subprocess.run(["curl", "--fail", "--location", "--retry", "3", "--proto", "=https", "--proto-redir", "=https", "--output", str(path), url], check=True)
    if expected and hashlib.sha256(path.read_bytes()).hexdigest() != expected:
        raise ValueError(f"源码 SHA256 不符：{path.name}")


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("component")
    parser.add_argument("--plan", type=Path, required=True)
    parser.add_argument("--work", type=Path, required=True)
    parser.add_argument("--local-source", type=Path)
    parser.add_argument("--orig-dir", type=Path)
    args = parser.parse_args()
    plan = json.loads(args.plan.read_text())
    comp = plan["components"][args.component]
    work = args.work.resolve()
    work.mkdir(parents=True, exist_ok=False)
    orig = work / comp["orig"]["filename"]
    if args.orig_dir:
        shutil.copy2(args.orig_dir / orig.name, orig)
        if hashlib.sha256(orig.read_bytes()).hexdigest() != comp["orig"]["sha256"]:
            raise ValueError("本地原版源码 SHA256 不符")
    else:
        fetch(comp["orig"]["url"], orig, comp["orig"]["sha256"])
    if args.local_source:
        checkout = work / "checkout"
        shutil.copytree(args.local_source, checkout, symlinks=True, ignore=shutil.ignore_patterns(".git", ".pc", "__pycache__"))
    else:
        archive = work / "checkout.tar.gz"
        fetch(f'https://codeload.github.com/{comp["repository"]}/tar.gz/{comp["commit"]}', archive)
        checkout = unpack(archive, work / "checkout-extract")
    src = work / (comp["package"] + "-source")
    if comp["model"] == "git-fork":
        baseline = unpack(orig, work / "upstream-extract")
        baseline.rename(work / "a")
        shutil.copytree(checkout, work / "b", symlinks=True, ignore=shutil.ignore_patterns(".git", "debian", "SOURCE_PROVENANCE.json", "README.altarscn.md"))
        diff = subprocess.run(["diff", "-Naur", "--exclude=.github", "--exclude=debian", "a", "b"], cwd=work, stdout=subprocess.PIPE)
        if diff.returncode not in (0, 1):
            raise RuntimeError("生成 fork 补丁失败")
        if b"Binary files " in diff.stdout:
            raise ValueError("fork 中存在无法用 quilt 分发的二进制差异")
        (work / "a").rename(src)
        shutil.copytree(checkout / "debian", src / "debian", symlinks=True)
        patches = src / "debian/patches"
        patches.mkdir(exist_ok=True)
        (patches / "altarscn-fork.patch").write_bytes(diff.stdout)
        (patches / "series").write_text("altarscn-fork.patch\n")
    else:
        checkout.rename(src)
    options = src / "debian/source/options"
    options.parent.mkdir(parents=True, exist_ok=True)
    with options.open("a") as stream:
        stream.write('\nextend-diff-ignore = "(^|/)(\\.github(/.*)?|SOURCE_PROVENANCE\\.json|README\\.altarscn\\.md)$"\n')
    provenance = {"component": args.component, "repository": comp["repository"], "commit": comp.get("commit", "local"), "orig_sha256": comp["orig"]["sha256"]}
    (src / "debian/altarscn-source.json").write_text(json.dumps(provenance, indent=2) + "\n")
    version = comp.get("build_version", comp["version"] + "+ghlocal1")
    subprocess.run(["dch", "--changelog", str(src / "debian/changelog"), "--newversion", version, "--distribution", plan["suite"], "--force-distribution", "固定源码提交并构建 AltarsCN GRD 软件栈。"], check=True)
    subprocess.run(["dpkg-source", "--before-build", str(src)], check=True)
    (work / "source-path").write_text(str(src) + "\n")
    print(src)


if __name__ == "__main__":
    main()
