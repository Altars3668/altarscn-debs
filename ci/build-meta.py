#!/usr/bin/python3
"""生成具有源码包的整栈元包；不改变目标机器的服务启用状态。"""
import json
from pathlib import Path
import shutil
import subprocess
import sys

plan = json.loads(Path(sys.argv[1]).read_text())
output = Path(sys.argv[2]).resolve()
output.mkdir(parents=True, exist_ok=True)
source = output / "grd-handover-stack"
source.mkdir(exist_ok=False)
debian = source / "debian"
(debian / "source").mkdir(parents=True)
version = "1.0+" + plan["components"]["grd"]["build_version"].split("+gh", 1)[1]
versions = {k: v["build_version"] for k, v in plan["components"].items()}
deps = ", ".join(f"{package} (= {versions[component]})" for package, component in (
    ("gnome-remote-desktop", "grd"), ("libmutter-18-0", "mutter"), ("gdm3", "gdm"),
    ("gnome-shell", "gnome-shell"), ("libfreerdp3-3", "freerdp")))
(debian / "control").write_text(f"Source: grd-handover-stack\nSection: metapackages\nPriority: optional\nMaintainer: AltarsCN <altarscn2@gmail.com>\nBuild-Depends: debhelper-compat (= 13)\nStandards-Version: 4.7.3\nRules-Requires-Root: no\n\nPackage: grd-handover-stack\nArchitecture: all\nDepends: {deps}, ${{misc:Depends}}\nDescription: AltarsCN GNOME remote desktop handover stack\n Installs one consistent build of GRD, Mutter, GDM, GNOME Shell and FreeRDP.\n Does not enable remote access, set credentials or restart the session itself.\n")
(debian / "rules").write_text("#!/usr/bin/make -f\n%:\n\tdh $@\n")
(debian / "rules").chmod(0o755)
(debian / "source/format").write_text("3.0 (native)\n")
(debian / "changelog").write_text(f"grd-handover-stack ({version}) resolute; urgency=medium\n\n  * 固定完整远程会话接管软件栈的版本组合。\n\n -- AltarsCN <altarscn2@gmail.com>  Wed, 14 Oct 2026 12:00:00 +0000\n")
(debian / "copyright").write_text("Format: https://www.debian.org/doc/packaging-manuals/copyright-format/1.0/\n\nFiles: *\nCopyright: 2026 AltarsCN\nLicense: MIT\n Permission is hereby granted, free of charge, to any person obtaining a copy\n of this software and associated documentation files, to deal in the Software\n without restriction, including the rights to use, copy, modify, merge,\n publish, distribute, sublicense, and/or sell copies, subject to including\n this copyright and permission notice.\n .\n THE SOFTWARE IS PROVIDED AS IS, WITHOUT WARRANTY OF ANY KIND.\n")
(source / "README").write_text("使用说明：https://github.com/Altars3668/altarscn-debs\n")
(debian / "docs").write_text("README\n")
(source / "resolved.json").write_text(json.dumps(plan, indent=2) + "\n")
subprocess.run(["dpkg-buildpackage", "-b", "-uc", "-us"], cwd=source, check=True)
subprocess.run(["dpkg-buildpackage", "-S", "-uc", "-us"], cwd=source, check=True)
shutil.rmtree(source)
