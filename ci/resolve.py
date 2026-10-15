#!/usr/bin/python3
"""固定本次五个源码提交，避免跨组件构建期间分支漂移。"""
import argparse
from datetime import datetime, timezone
import json
import os
from pathlib import Path
import re
import subprocess
import tempfile


def gh(*args):
    return subprocess.check_output(["gh", *args], text=True)


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--override-component", default="")
    parser.add_argument("--override-ref", default="")
    parser.add_argument("--force", action="store_true")
    args = parser.parse_args()
    root = Path(__file__).resolve().parents[1]
    config = json.loads((root / "stack.json").read_text())
    if args.override_component and args.override_component not in config["components"]:
        parser.error("组件不在发布清单中")
    if args.override_ref and not re.fullmatch(r"[0-9a-f]{40}", args.override_ref):
        parser.error("覆盖版本必须为完整提交 SHA")
    config["control_commit"] = subprocess.check_output(["git", "-C", str(root), "rev-parse", "HEAD"], text=True).strip()
    for name, comp in config["components"].items():
        ref = args.override_ref if name == args.override_component else comp["ref"]
        comp["commit"] = json.loads(gh("api", f'repos/{comp["repository"]}/commits/{ref}'))["sha"]
        if not re.fullmatch(r"[0-9a-f]{40}", comp["commit"]):
            raise ValueError("无效的源码 SHA")
    previous = None
    # 只将“还没有正式 Release”视为首次运行；网络、权限和下载错误必须失败。
    releases = json.loads(gh("api", "repos/Altars3668/altarscn-debs/releases?per_page=100"))
    releases = [r for r in releases if not r["draft"] and not r["prerelease"] and r["tag_name"].startswith("stack-")]
    if releases:
        with tempfile.TemporaryDirectory(prefix="grd-previous-plan-") as directory:
            gh("release", "download", releases[0]["tag_name"], "--repo", "Altars3668/altarscn-debs", "--pattern", "resolved.json", "--dir", directory)
            previous = json.loads((Path(directory) / "resolved.json").read_text())
    identity = lambda plan: (plan["control_commit"], {k: v["commit"] for k, v in plan["components"].items()})
    changed = args.force or args.override_component != "" or previous is None or identity(config) != identity(previous)
    stamp = datetime.now(timezone.utc).strftime("%Y%m%d%H%M%S")
    run = os.environ.get("GITHUB_RUN_ID", "0")
    attempt = os.environ.get("GITHUB_RUN_ATTEMPT", "1")
    config["release_tag"] = f"stack-{stamp}-{run}-{attempt}"
    config["changed"] = changed
    config["previous_tag"] = releases[0]["tag_name"] if releases else ""
    for comp in config["components"].values():
        comp["build_version"] = f'{comp["version"]}+gh{stamp}.{run}.{attempt}'
    args.output.write_text(json.dumps(config, ensure_ascii=False, indent=2) + "\n")
    output = os.environ.get("GITHUB_OUTPUT")
    if output:
        with open(output, "a") as stream:
            stream.write(f'changed={str(changed).lower()}\ncontrol_commit={config["control_commit"]}\nrelease_tag={config["release_tag"]}\nprevious_tag={config["previous_tag"]}\n')
    print(json.dumps({"changed": changed, "commits": {k: v["commit"] for k, v in config["components"].items()}}, indent=2))


if __name__ == "__main__":
    main()
