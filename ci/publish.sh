#!/usr/bin/env bash
# 签名密钥只存在于发布作业的临时 GNUPGHOME，不进入源码、artifact 或站点。
set -euo pipefail
plan=$(realpath "${1:?发布计划}")
root=$(realpath "$(dirname "$0")/..")
[[ ${GITHUB_REPOSITORY:-} == Altars3668/altarscn-debs && ${GITHUB_REF:-} == refs/heads/main ]] || exit 2
[[ -n ${APT_SIGNING_KEY:-} && ${APT_SIGNING_FINGERPRINT:-} =~ ^[A-Fa-f0-9]{40}$ ]] || { printf '缺少 APT 签名密钥或指纹。\n' >&2; exit 2; }
export GNUPGHOME
GNUPGHOME=$(mktemp -d)
chmod 700 "$GNUPGHOME"
trap 'gpgconf --kill all || true; rm -rf -- "$GNUPGHOME"' EXIT
printf '%s' "$APT_SIGNING_KEY" | gpg --batch --import
unset APT_SIGNING_KEY
mapfile -t values < <(python3 -I -c 'import json,sys; p=json.load(open(sys.argv[1])); print(str(p["changed"]).lower()); print(p["release_tag"]); print(p["previous_tag"]); print(p["control_commit"])' "$plan")
changed=${values[0]}; tag=${values[1]}; previous=${values[2]}; commit=${values[3]}
mkdir -p site previous-fetch
if [[ -n $previous ]]; then
  gh release download "$previous" --repo "$GITHUB_REPOSITORY" --pattern apt-repository.tar.xz --pattern SHA256SUMS --pattern SHA256SUMS.asc --dir previous-fetch
  gpg --batch --verify previous-fetch/SHA256SUMS.asc previous-fetch/SHA256SUMS
  python3 -I -c 'from pathlib import Path; import hashlib,sys,tarfile; root=Path(sys.argv[1]); archive=root/"apt-repository.tar.xz"; expected=next(line.split()[0] for line in (root/"SHA256SUMS").read_text().splitlines() if line.split()[-1]==archive.name); assert hashlib.sha256(archive.read_bytes()).hexdigest()==expected, "历史源快照校验失败"; tarfile.open(archive).extractall(sys.argv[2],filter="data")' previous-fetch site
fi
if [[ $changed == true ]]; then
  python3 -I "$root/ci/build-meta.py" "$plan" artifacts/meta
fi
mkdir -p artifacts
python3 -I "$root/ci/build-apt.py" --packages artifacts --site site --fingerprint "$APT_SIGNING_FINGERPRINT"
# APT 必须以提供的公钥验证，不能通过 trusted=yes 绕过信任链。
gpg --batch --verify site/dists/resolute/InRelease
rm -f apt-repository.tar.xz
tar -C site -cJf apt-repository.tar.xz .
if [[ $changed == true ]]; then
  mkdir release-files
  python3 -I -c 'from pathlib import Path; import hashlib,shutil,sys; root=Path(sys.argv[1]); out=Path(sys.argv[2]); files=[p for p in root.rglob("*") if p.is_file() and not p.is_symlink() and (p.suffix in (".deb",".dsc",".changes",".buildinfo") or p.name.endswith(".tar.xz"))];
for p in files:
 d=out/p.name
 if d.exists() and hashlib.sha256(d.read_bytes()).digest()!=hashlib.sha256(p.read_bytes()).digest(): raise ValueError("发布文件同名冲突："+p.name)
 shutil.copy2(p,d)' artifacts release-files
  cp "$plan" release-files/resolved.json
  cp apt-repository.tar.xz release-files/
  cp "$root/apt/repository.asc" release-files/
  (
    cd release-files
    sha256sum -- *.deb *.dsc *.tar.xz *.json *.asc > SHA256SUMS
    gpg --batch --yes --armor --local-user "$APT_SIGNING_FINGERPRINT" --output SHA256SUMS.asc --detach-sign SHA256SUMS
  )
  # shellcheck disable=SC2016 # Markdown 反引号是 Python 字符串内容。
  python3 -I -c 'import json,sys; p=json.load(open(sys.argv[1])); print("## AltarsCN GRD 软件栈\n\nUbuntu 26.04 resolute / amd64；包含二进制、对应源码与签名 APT 索引。\n\n安装说明：https://github.com/Altars3668/altarscn-debs\n\n|组件|版本|源码提交|\n|---|---|---|"); [print("|%s|`%s`|`%s`|"%(k,v["build_version"],v["commit"])) for k,v in p["components"].items()]; print("\nCI 验证构建成品及无显示器回归；没有 GPU/物理会话硬件验收。")' "$plan" > release-notes.md
  gh release create "$tag" --repo "$GITHUB_REPOSITORY" --target "$commit" --draft --title "GRD stack · $tag" --notes-file release-notes.md
  gh release upload "$tag" --repo "$GITHUB_REPOSITORY" release-files/*
else
  # 只刷新 Pages 签名；正式 Release 中的校验和及历史快照始终保持不可变。
  printf '源码未变：刷新 Pages 索引，保留正式 Release 的不可变快照。\n'
fi
