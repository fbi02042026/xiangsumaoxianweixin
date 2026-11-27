#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""一次性设置微信小游戏公网 CDN（换域名只跑这一条命令，四处全对齐）。

用法：
    python Tools/SetWeChatCDN.py https://<bucket>-<appid>.cos.<region>.myqcloud.com
    python Tools/SetWeChatCDN.py --check          # 只体检，不写入
    python Tools/SetWeChatCDN.py --current        # 只看当前四处的值

同时改写并校验 4 处 CDN 配置：
    1. Assets/WX-WASM-SDK-V2/Editor/MiniGameConfig.asset        (CDN:)
    2. Assets/Settings/Build Profiles/New WeChat Profile.asset   (CDN:)
    3. Assets/Settings/Build Profiles/New WeChat Profile 1.asset (CDN:)
    4. minigame/minigame/game.js                                (DATA_CDN:)

设计目的：避免「改了源头忘了产物」「改了产物下次出包又被覆盖」这类返工。
注意：脚本同步当前产物 game.js 是为了立即能测；正式出包时团结引擎会从
    上面 3 个源头重新生成产物，届时的值就是本脚本写入的值，不会回退。
"""

import re
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent

TARGETS = [
    ("Assets/WX-WASM-SDK-V2/Editor/MiniGameConfig.asset", re.compile(r"^(\s*CDN:\s*).*$")),
    ("Assets/Settings/Build Profiles/New WeChat Profile.asset", re.compile(r"^(\s*CDN:\s*).*$")),
    ("Assets/Settings/Build Profiles/New WeChat Profile 1.asset", re.compile(r"^(\s*CDN:\s*).*$")),
    ("minigame/minigame/game.js", re.compile(r"^(\s*DATA_CDN:\s*)'[^']*'(,?)\s*$")),
]


def validate(cdn: str) -> None:
    if not cdn.startswith("https://"):
        raise ValueError("域名必须以 https:// 开头（微信合法域名不接受 http，也不接受 IP）")
    rest = cdn[len("https://"):]
    if not rest or "/" in rest:
        raise ValueError("只填域名本身，不要带路径或结尾斜杠，例如 https://x.cos.ap-guangzhou.myqcloud.com")
    if ":" in rest:
        raise ValueError("不要带端口（微信合法域名不接受端口号）")
    if " " in cdn:
        raise ValueError("域名中不能有空格")
    # 常见误填：把对象 key 或文件名也贴进来
    if ".br" in cdn or ".data" in cdn:
        raise ValueError("这里只填域名，不要填数据文件名")


def render(pattern: re.Pattern, line: str, cdn: str) -> str:
    """返回替换后的整行；game.js 需要保留引号与行尾逗号。"""
    if "DATA_CDN" in pattern.pattern:
        return pattern.sub(lambda m: f"{m.group(1)}'{cdn}'{m.group(2)}", line)
    return pattern.sub(lambda m: f"{m.group(1)}{cdn}", line)


def read_value(pattern: re.Pattern, path: Path) -> str:
    for line in path.read_text(encoding="utf-8").splitlines():
        if pattern.match(line):
            m = pattern.match(line)
            if "DATA_CDN" in pattern.pattern:
                return m.group(0).split("'")[1]
            return line.split(":", 1)[1].strip()
    return "<未找到>"


def check_only() -> None:
    print("当前四处 CDN 值：")
    ok = True
    for rel, pattern in TARGETS:
        path = ROOT / rel
        if not path.exists():
            print(f"  [缺失] {rel}")
            ok = False
            continue
        value = read_value(pattern, path)
        flag = "OK" if value.startswith("https://") else "待换"
        print(f"  [{flag}] {rel}\n         {value}")
        ok = ok and value.startswith("https://")
    print("\n结论：" + ("四处均为公网 HTTPS，已对齐" if ok else "仍有内网/未配置地址，需换域名"))


def apply(cdn: str) -> None:
    validate(cdn)
    print(f"目标域名：{cdn}\n")
    changed = 0
    for rel, pattern in TARGETS:
        path = ROOT / rel
        if not path.exists():
            raise FileNotFoundError(f"找不到目标文件：{path}")
        text = path.read_text(encoding="utf-8")
        lines = text.splitlines(keepends=True)
        hits = [i for i, line in enumerate(lines) if pattern.match(line.rstrip("\r\n"))]
        if len(hits) != 1:
            raise RuntimeError(f"{rel} 匹配到 {len(hits)} 处 CDN 配置（期望恰好 1 处），已跳过写入以防误改")
        idx = hits[0]
        raw = lines[idx].rstrip("\r\n")
        eol = lines[idx][len(raw):]
        old = read_value(pattern, path)
        new_line = render(pattern, raw, cdn)
        if new_line == raw:
            print(f"  [相同] {rel}")
            continue
        lines[idx] = new_line + eol
        path.write_text("".join(lines), encoding="utf-8")
        changed += 1
        print(f"  [已改] {rel}\n         {old}  ->  {cdn}")
    print(f"\n完成：{changed} 处已更新。下一步：重新构建小游戏包，并在 MP 后台配 downloadFile 合法域名。")


def main() -> None:
    args = sys.argv[1:]
    if args == ["--check"]:
        check_only()
        return
    if args == ["--current"]:
        check_only()
        return
    if len(args) == 1 and not args[0].startswith("-"):
        apply(args[0])
        return
    print(__doc__)


if __name__ == "__main__":
    try:
        main()
    except (ValueError, FileNotFoundError, RuntimeError) as exc:
        print(f"错误：{exc}", file=sys.stderr)
        sys.exit(1)
