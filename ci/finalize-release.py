#!/usr/bin/python3
"""Pages 部署成功后，才把本次 draft 提升为正式 latest Release。"""
import json
from pathlib import Path
import subprocess
import sys

plan = json.loads(Path(sys.argv[1]).read_text())
if plan["changed"]:
    subprocess.run(["gh", "release", "edit", plan["release_tag"], "--repo", "Altars3668/altarscn-debs", "--draft=false", "--latest"], check=True)
print("签名 APT 源已部署；正式 Release 状态已更新。")
