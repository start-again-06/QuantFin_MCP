"""Generate docs/tools.md from the live MCP tool registry.

Run:  python scripts/generate_tool_docs.py
CI runs this and fails if docs/tools.md is out of date (see the docs-check job).
"""

from __future__ import annotations

import asyncio
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

from quant_mcp.server import mcp  # noqa: E402

OUT = ROOT / "docs" / "tools.md"


def render() -> str:
    tools = asyncio.run(mcp.list_tools())
    lines = [
        "# Tool reference",
        "",
        "Generated from the server's tool registry by `scripts/generate_tool_docs.py`. Do not edit by hand.",
        "",
        f"{len(tools)} tools.",
        "",
    ]
    for tool in sorted(tools, key=lambda t: t.name):
        lines.append(f"## `{tool.name}`")
        lines.append("")
        lines.append(tool.description or "")
        lines.append("")
        props = (tool.inputSchema or {}).get("properties", {})
        required = set((tool.inputSchema or {}).get("required", []))
        if props:
            lines.append("| Parameter | Type | Required | Default |")
            lines.append("| --- | --- | --- | --- |")
            for name, spec in props.items():
                typ = spec.get("type") or spec.get("anyOf") or "any"
                if isinstance(typ, list):
                    typ = " | ".join(x.get("type", "any") for x in typ)
                default = json.dumps(spec["default"]) if "default" in spec else "-"
                lines.append(f"| `{name}` | {typ} | {'yes' if name in required else 'no'} | {default} |")
            lines.append("")
    return "\n".join(lines).rstrip() + "\n"


if __name__ == "__main__":
    text = render()
    if "--check" in sys.argv:
        current = OUT.read_text() if OUT.exists() else ""
        if current != text:
            print("docs/tools.md is out of date. Run: python scripts/generate_tool_docs.py")
            raise SystemExit(1)
        print("docs/tools.md is up to date.")
    else:
        OUT.parent.mkdir(exist_ok=True)
        OUT.write_text(text)
        print(f"wrote {OUT}")
