#!/usr/bin/python3
"""用真实 dpkg 构建验证：翻译模板再生成不能污染对应源码包。"""
import os
from pathlib import Path
import subprocess
import tarfile
import tempfile


root = Path(__file__).resolve().parents[1]
script = (root / "ci/build-component.sh").read_text()
block = script.split('(\n  cd "$source"\n', 1)[1].split('\n)\n', 1)[0]

with tempfile.TemporaryDirectory(prefix="grd-build-order-") as directory:
    work = Path(directory)
    source = work / "package" / "grd-ci-order-1.0"
    (source / "po").mkdir(parents=True)
    original = '# 原版翻译模板\n'
    (source / "po/example.pot").write_text(original)
    with tarfile.open(work / "package/grd-ci-order_1.0.orig.tar.xz", "w:xz") as archive:
        archive.add(source, arcname=source.name)
    debian = source / "debian"
    (debian / "source").mkdir(parents=True)
    (debian / "source/format").write_text("3.0 (quilt)\n")
    (debian / "control").write_text(
        "Source: grd-ci-order\nSection: misc\nPriority: optional\n"
        "Maintainer: AltarsCN <altarscn2@gmail.com>\n"
        "Build-Depends: debhelper-compat (= 13)\nRules-Requires-Root: no\n\n"
        "Package: grd-ci-order\nArchitecture: all\n"
        "Depends: ${misc:Depends}\nDescription: CI build order fixture\n"
        " Local regression fixture; not published or installed.\n"
    )
    (debian / "changelog").write_text(
        "grd-ci-order (1.0-1) unstable; urgency=medium\n\n"
        "  * 本地构建顺序回归。\n\n"
        " -- AltarsCN <altarscn2@gmail.com>  Thu, 15 Oct 2026 12:00:00 +0000\n"
    )
    # 模拟 dh_translations 更新源树中的 POT，而 dh clean 不恢复该文件。
    (debian / "rules").write_text(
        "#!/usr/bin/make -f\n%:\n\tdh $@\n\n"
        "override_dh_auto_build:\n"
        "\tprintf '# 构建时再生成的模板\\n' >> po/example.pot\n"
    )
    (debian / "rules").chmod(0o755)
    environment = dict(os.environ, PATH="/usr/bin:/bin:/usr/sbin:/sbin",
                       source=str(source), root=str(root), component="gdm",
                       work=str(work), DEB_BUILD_OPTIONS="nocheck",
                       DEB_BUILD_PROFILES="nocheck")
    subprocess.run(["bash", "-euo", "pipefail", "-c", 'cd "$source"\n' + block],
                   env=environment, check=True)
    sources = list((work / "package").glob("*.dsc"))
    binaries = list((work / "package").glob("*.deb"))
    assert len(sources) == len(binaries) == 1, "必须同时交付源码包与二进制包"
    assert (source / "po/example.pot").read_text() != original, "fixture 未再生成模板"
    extracted = work / "extracted"
    subprocess.run(["dpkg-source", "-x", str(sources[0]), str(extracted)], check=True)
    assert (extracted / "po/example.pot").read_text() == original, "源码包受到构建副作用污染"
    assert extracted.joinpath("debian/rules").read_text() == (debian / "rules").read_text()
    print("通过：先封装源码，后运行会再生成 POT 的二进制构建及成品检查。")
