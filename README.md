# AltarsCN GRD 修改版软件栈

[![构建与发布](https://github.com/Altars3668/altarscn-debs/actions/workflows/release.yml/badge.svg)](https://github.com/Altars3668/altarscn-debs/actions/workflows/release.yml)

面向 **Ubuntu 26.04 LTS（resolute），amd64，GNOME 50** 的下游远程桌面软件栈，包含控制台会话接管、多用户会话、虚拟视图后台渲染、光标/损伤修复、AMD VAAPI 编码及 RDP UDP/HEVC 扩展。

这不是 GNOME 或 Ubuntu 官方项目。请先在测试机验证，尤其是物理屏隐私、重新登录、多个用户与 GPU 编码。GitHub runner 不提供本项目使用的 GPU 和真实 GDM 会话；CI 的通过不等同于这些硬件场景通过。

## 源码仓库

| 组件 | 当前下游基线 | 公开源码 | 维护方式 |
|---|---|---|---|
| GNOME Remote Desktop | 50.0 / altarscn5 | [gnome-remote-desktop](https://github.com/Altars3668/gnome-remote-desktop) | 完整 git fork，构建时生成累计 quilt 补丁 |
| Mutter | 50.1-0ubuntu2.4 / altarscn3 | [mutter](https://github.com/Altars3668/mutter) | Ubuntu 源码 + 10 个下游 quilt 补丁，严格 ABI 检查 |
| FreeRDP | 3.30.0+dfsg-0ubuntu0.26.04.2 / altarscn15 | [FreeRDP](https://github.com/Altars3668/FreeRDP) | Ubuntu 源码 + VAAPI、RDPEUDP、HEVC 补丁 |
| GDM | 50.0-0ubuntu1 / altarscn1 | [gdm](https://github.com/Altars3668/gdm) | NLA 已认证用户名传入远程显示器 |
| GNOME Shell | 50.1-0ubuntu1.2 / altarscn1 | [gnome-shell](https://github.com/Altars3668/gnome-shell) | 无显示器后的 greeter 唤醒修复 |

首次公开导入使用可追溯的干净源码快照，不包含私有 Git 历史、凭据、运行配置或构建产物。每个源码仓库的 `SOURCE_PROVENANCE.json` 记录 Ubuntu 原版档案 SHA256；GRD 另记录原下游提交。依赖仓库中代码为原版内容，修改位于 `debian/patches/series`，运行 `dpkg-source --before-build .` 后得到修改版。

## 安装签名 APT 源

**仅适用于 Ubuntu 26.04 amd64。不要安装到 Ubuntu 24.04、其他 GNOME 大版本或任意 Debian 发行版。**

源地址：`https://altars3668.github.io/altarscn-debs`。

先下载公钥，在写入系统目录前核对指纹：

```bash
curl -fL https://altars3668.github.io/altarscn-debs/repository.asc -o /tmp/altarscn-grd.asc
gpg --show-keys --with-fingerprint /tmp/altarscn-grd.asc
```

期望指纹：

```text
5D2A A242 AE29 DA7C 3CD3 C434 7186 356F 0AC9 9497
```

核对无误后安装源与优先级文件：

```bash
sudo install -d -m755 /etc/apt/keyrings
sudo install -m644 /tmp/altarscn-grd.asc /etc/apt/keyrings/altarscn-grd.asc
curl -fL https://altars3668.github.io/altarscn-debs/altarscn-grd.sources -o /tmp/altarscn-grd.sources
curl -fL https://altars3668.github.io/altarscn-debs/altarscn-grd.pref -o /tmp/altarscn-grd.pref
sudo install -m644 /tmp/altarscn-grd.sources /etc/apt/sources.list.d/altarscn-grd.sources
sudo install -m644 /tmp/altarscn-grd.pref /etc/apt/preferences.d/altarscn-grd.pref
sudo apt-get update
apt-cache policy grd-handover-stack gnome-remote-desktop libmutter-18-0 gdm3 libfreerdp3-3
sudo apt-get -s install grd-handover-stack
```

确认模拟安装没有不期望的卸载或桌面组件冲突，再在有本地控制台或备用登录通道的维护窗口执行：

```bash
sudo apt-get install grd-handover-stack
```

元包精确依赖同一轮构建的五个组件。版本号保留 `+altarscnN`，再加唯一的 `+gh时间.运行号.重试号`。APT 的 `Pin-Priority: 1001` 只作用于此软件栈、且匹配 `Origin: AltarsCN-GRD`，不固定全部 Ubuntu 软件包。已有 Gitea 源不会被修改；同时启用两个定制源时，应先核对 `apt-cache policy`，避免无意切换版本。

**安装可能由发行版维护脚本重启服务并断开 RDP。不要在唯一的远程会话中直接升级。** 新库需要重新登录才能完整生效。本项目不会替你启用远程登录、生成凭据、打开防火墙或设置自动登录。

GRD 包携带会话接管所需的限定 D-Bus / Polkit 规则：仅 `gnome-remote-desktop` 服务账号可管理 GDM 用户显示器。该权限用于已经通过 NLA 认证的用户建立会话，不授予普通用户。仍须按源码仓库说明配置 TLS、认证与用户会话。

## 自动构建与发布

1. 中央 `main` 的构建相关提交、手动运行以及每日 UTC 03:17 触发。
2. 一次性解析五个仓库 `main` 的完整 SHA 并写入 `resolved.json`。构建固定使用这些 SHA，不在中途读取浮动分支。
3. 在干净 `ubuntu:26.04` 容器中先构建 FreeRDP、Mutter、GDM。GNOME Shell 使用同轮 Mutter 开发包，GRD 使用同轮 FreeRDP 开发包。
4. FreeRDP 检查成品 FFmpeg / VAAPI / H264 开关和 UDP 导出符号；Mutter 保留严格 ABI 门禁并检查新符号；GRD 跑无需 GPU / 活动显示器的定向回归。
5. 同时生成 `.deb` 和对应 `.dsc` / 原版 tar / Debian tar。只有整栈成功才生成元包、签名 APT 索引并创建 draft Release。
6. Pages 部署成功后将 draft 提升为正式 latest Release。附件包含源码、二进制、构建清单与签名 `SHA256SUMS`。
7. 源码未变时不重复编译，只刷新 Pages 的 30 天有效签名索引。历史 Release 与校验和保持不可变，保留 pool / by-hash 避免升级中途 404。

每个源码仓库另有调用中央只读可复用工作流的 CI：源码 push / PR 会构建整栈验证，但不能获取发布密钥、发布中央 Release 或修改 APT 源。中央每日检查将在源码更新后自动发布；需要立即发布时手动运行中央 `release.yml`。

**不自动重放未知 Ubuntu 安全更新。** `stack.json` 中发行版基线和补丁需要维护者审核更新。优先级 1001 会阻止这些包被未打补丁的 Ubuntu 版本替换，因此必须及时变基并发布安全更新，不能以 CI 自动化代替维护。

## 签名与权限

- 官方 Action 使用完整 SHA 固定版本。
- 构建作业只获得只读权限，不获取发布密钥。
- 只有中央 `main` 的 `apt-publish` 环境允许发布，私钥使用 `APT_SIGNING_KEY` 环境 Secret；公开指纹固定在工作流中，不存放为 Secret。
- 专用密钥不使用个人主密钥、Gitea 凭据或 GNOME 凭据；私钥永不进入仓库、artifact 或 Pages。
- 密钥于 2028-10-13 到期，必须提前滚动更新公钥与环境 Secret，并告知使用者新的可信指纹。
- 站点接近 900 MiB 时 CI 停止并要求规划历史归档，不会悄悄删除客户端可能仍使用的包。

## 获取和验证源码

Release 提供完整对应源码，也可使用：

```bash
apt-get source gnome-remote-desktop
apt-get source mutter
apt-get source freerdp3
apt-get source gdm3
apt-get source gnome-shell
```

检查 Release 附件：

```bash
gpg --import repository.asc
gpg --verify SHA256SUMS.asc SHA256SUMS
sha256sum -c SHA256SUMS
```

公钥须先与上面的可信指纹核对，不应仅因为下载文件附带一把公钥就信任它。

## 维护与旧渠道

`stack.json` 是构建基线，`ci/` 和 `.github/workflows/` 实现 GitHub 发布。各源码仓库的 `debian/` 是打包权威；中央仓库只包含本次新写的自动化、APT 配置和公开构建清单。

原 Gitea 控制仓库及 `grd-stack-sync`、`grd-upstream-watch` 独立保留在原处，**不复制到这个公开仓库，也不参与 GitHub Actions**。本次不修改现有 Gitea 发布源、主机凭据或部署状态。未知上游版本的补丁冲突仍须人工处理。

撤销此 GitHub 源时删除对应 `.sources` 和 `.pref`，执行 `apt-get update`，再明确选择发行版版本模拟降级。Gitea 源独立保留。切回发行版前应先卸载精确依赖版本的 `grd-handover-stack` 元包；卸载元包本身不会卸载依赖组件。

## 许可证

各组件和补丁遵循各自上游许可证，见源包的 `debian/copyright`。新写的 `ci/` 脚本按 MIT 发布，不改变上游版权归属。
