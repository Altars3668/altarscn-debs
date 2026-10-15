#!/usr/bin/python3
"""直接检查构建成品与无需 GPU 的下游回归；不声称硬件验收通过。"""
from pathlib import Path
import re
import subprocess
import sys
import tempfile

component, source_arg, output_arg = sys.argv[1:]
source, output = Path(source_arg), Path(output_arg)
root = Path(__file__).resolve().parents[1]


def run(*args, **kwargs):
    return subprocess.check_output(args, text=True, **kwargs)


packages = list(output.glob("*.deb"))
if not packages:
    raise RuntimeError("没有生成二进制包")
for deb in packages:
    deps = run("dpkg-deb", "-f", str(deb), "Depends")
    if re.search(r"(?<!\| )libdrm2-amdgpu", deps):
        raise RuntimeError("成品带入了本机专有 AMD 依赖")

if component in ("freerdp", "mutter"):
    package = "libfreerdp3-3" if component == "freerdp" else "libmutter-18-0"
    deb = next(p for p in packages if run("dpkg-deb", "-f", str(p), "Package").strip() == package)
    with tempfile.TemporaryDirectory(prefix="grd-verify-") as directory:
        subprocess.run(["dpkg-deb", "-x", str(deb), directory], check=True)
        files = list(Path(directory).rglob("*.so.*"))
        if component == "freerdp":
            library = next(p for p in files if p.name.startswith("libfreerdp3.so.") and not p.is_symlink())
            configuration = run("strings", str(library))
            for feature in ("WITH_FFMPEG", "WITH_VIDEO_FFMPEG", "WITH_VAAPI", "WITH_VAAPI_H264_ENCODING", "WITH_GFX_H264"):
                if f"{feature}=ON" not in configuration:
                    raise RuntimeError(f"成品缺少 {feature}=ON")
            symbols = run("nm", "-D", "--defined-only", str(library))
            for symbol in ("rdpeudp_server_get_fd", "rdpeudp_server_new"):
                if symbol not in symbols:
                    raise RuntimeError(f"成品缺少导出符号 {symbol}")
            print("FreeRDP：FFmpeg/VAAPI/H264 和 RDPEUDP 成品检查通过。")
        else:
            library = next(p for p in files if p.name.startswith("libmutter-clutter-18.so.") and not p.is_symlink())
            if "clutter_frame_clock_get_refresh_interval" not in run("nm", "-D", "--defined-only", str(library)):
                raise RuntimeError("Mutter 缺少 GRD 所需符号")
            print("Mutter：GRD 所需新增符号及严格 ABI 打包检查通过。")

if component == "grd":
    build = source / "ci-tests"
    subprocess.run(["meson", "setup", str(build), str(source), "-Dfdk_aac=false", "-Dtests=true"], check=True)
    # 不运行依赖活动显示器、DRM 设备或物理会话的测试。
    selected = ["damage-carry", "hevc-poc-wrap", "quality-controller", "rdp-sam-sweep", "gfx-frame-ack-policy", "one-time-credentials", "write-fd-to-file"]
    selected += ["gnome-remote-desktop/rdp-handover-" + name for name in (
        "system", "prepare", "take-client", "take-client-export", "start-handover", "redirected-connection", "local-session-redirect", "keyring-unlock", "physical-session", "watchdog", "watchdog-lifecycle", "monitor-layout", "monitor-layout-fallback", "initial-monitor-state")]
    selected += ["gnome-remote-desktop/secret-session", "gnome-remote-desktop/rdp-cursor-policy", "gnome-remote-desktop/pipewire-buffer-frame-data"]
    subprocess.run(["meson", "test", "-C", str(build), "--print-errorlogs", *selected], check=True)
    # 源包必须不包含此独立测试构建目录。
    import shutil
    shutil.rmtree(build)
    print(f"GRD：{len(selected)} 组无显示器回归全部通过；GPU/真实会话验收需测试机。")
