#!/usr/bin/env bash
# 仅在隔离的 Ubuntu 26.04 构建容器中安装依赖；禁止在桌面主机上误执行。
set -euo pipefail
[[ ${CI:-} == true ]] || { printf '请在 CI 隔离容器中构建。\n' >&2; exit 2; }
component=${1:?组件}; plan=${2:?解析后的清单}; output=${3:?输出目录}
root=$(realpath "$(dirname "$0")/..")
plan=$(realpath "$plan")
output=$(realpath -m "$output")
export PATH=/usr/bin:/bin:/usr/sbin:/sbin
export DEBIAN_FRONTEND=noninteractive
export DEBEMAIL=altarscn2@gmail.com DEBFULLNAME=AltarsCN
DEB_BUILD_OPTIONS="parallel=$(nproc) nocheck"
export DEB_BUILD_OPTIONS
export DEB_BUILD_PROFILES=nocheck
work=$(mktemp -d)
# prepare-source 要求目的目录全新。
python3 -I "$root/ci/prepare-source.py" "$component" --plan "$plan" --work "$work/package"
IFS= read -r source < "$work/package/source-path"
# 构建组的依赖通过 artifact 传入，不使用宿主机的私有 AMD 库或既有 apt 源。
if [[ -d dependencies ]]; then
  mapfile -d '' debs < <(find dependencies -type f -name '*.deb' ! -name '*dbgsym*' -print0)
  if ((${#debs[@]})); then
    # 容器中不能启动 GDM/GRD；安装的依赖包原则上只有库与开发文件。
    printf '#!/bin/sh\nexit 101\n' > /usr/sbin/policy-rc.d
    chmod 755 /usr/sbin/policy-rc.d
    apt-get install -y --no-install-recommends "${debs[@]/#/./}"
  fi
fi
apt-get build-dep -y --no-install-recommends "$source"
if [[ $component == grd ]]; then
  # 打包使用 nocheck，下面的独立回归仍需要这些运行工具。
  apt-get install -y --no-install-recommends dbus-daemon python3-gi python3-dbus openssl pipewire wireplumber mutter
fi
(
  cd "$source"
  # 先封装固定源码；dh_translations 等构建步骤会重写源树中的生成文件。
  dpkg-buildpackage -S -d -uc -us
  dpkg-source --before-build .
  dpkg-buildpackage -b -uc -us
  # dpkg-buildpackage 的 --after-build 会弹出 quilt 补丁；回归前恢复同一份下游代码。
  dpkg-source --before-build .
  python3 -I "$root/ci/verify-component.py" "$component" "$source" "$work/package"
)
mkdir -p "$output"
find "$work/package" -maxdepth 1 -type f \( -name '*.deb' -o -name '*.dsc' -o -name '*.tar.xz' -o -name '*.buildinfo' -o -name '*.changes' \) -exec cp -t "$output" -- {} +
cp "$plan" "$output/build-plan.json"
if [[ $component == grd ]]; then
  mapfile -d '' freerdp_debs < <(find dependencies -type f -name '*.deb' -print0)
  printf '已使用本次 FreeRDP artifact 构建 GRD（%s 个依赖包）。\n' "${#freerdp_debs[@]}"
fi
