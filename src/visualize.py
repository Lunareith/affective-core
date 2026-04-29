#!/usr/bin/env python3
"""visualize.py — Terminal ASCII 雷达图 + HTML Dashboard（零外部依赖）"""

import json
import math
import os
import sys
from datetime import datetime, timezone
from pathlib import Path
from typing import Dict, List, Optional, Tuple

DIMENSIONS = [
    "valence", "arousal", "dominance",
    "trust", "intimacy", "respect", "forgiveness",
    "curiosity", "confusion", "certainty", "anticipation",
    "nostalgia", "impatience", "relief", "disappointment", "hope"
]

DIM_SHORT = {
    "valence": "V", "arousal": "A", "dominance": "D",
    "trust": "T", "intimacy": "I", "respect": "R", "forgiveness": "Fo",
    "curiosity": "Cu", "confusion": "Co", "certainty": "Ce", "anticipation": "An",
    "nostalgia": "N", "impatience": "Im", "relief": "Rl", "disappointment": "Di", "hope": "H"
}

DIM_COLORS = [
    "#FF6B6B", "#4ECDC4", "#45B7D1", "#96CEB4", "#FFEAA7", "#DDA0DD", "#98D8C8",
    "#F7DC6F", "#BB8FCE", "#85C1E9", "#F8C471", "#82E0AA", "#F1948A", "#AED6F1",
    "#D7BDE2", "#F9E79F"
]


class TerminalRadarChart:
    """终端 ASCII 雷达图。扫描线填充，60×28 字符网格。"""

    def __init__(self, width: int = 60, height: int = 28):
        self.width = width
        self.height = height
        self.cx = width // 2
        self.cy = height // 2
        self.radius = min(self.cx, self.cy) - 3

    def render(self, vec: dict, title: str = "Affective Core Radar") -> str:
        grid = [[" " for _ in range(self.width)] for _ in range(self.height)]
        n = len(DIMENSIONS)
        if n == 0:
            return ""

        def vertex(i: int, r: float) -> Tuple[int, int]:
            angle = math.pi / 2 - 2 * math.pi * i / n
            x = self.cx + int(r * math.cos(angle))
            y = self.cy - int(r * math.sin(angle) * 0.5)
            return max(0, min(self.width - 1, x)), max(0, min(self.height - 1, y))

        for ratio in (0.2, 0.4, 0.6, 0.8, 1.0):
            r = self.radius * ratio
            for i in range(n):
                x1, y1 = vertex(i, r)
                x2, y2 = vertex((i + 1) % n, r)
                self._draw_line(grid, x1, y1, x2, y2, "·" if ratio < 1.0 else "-")

        for i in range(n):
            x, y = vertex(i, self.radius)
            self._draw_line(grid, self.cx, self.cy, x, y, ".")

        poly = []
        for i, dim in enumerate(DIMENSIONS):
            val = abs(vec.get(dim, 0.0))
            poly.append(vertex(i, self.radius * val))

        self._fill_polygon(grid, poly, "█")

        for i, (x, y) in enumerate(poly):
            if 0 <= x < self.width and 0 <= y < self.height:
                grid[y][x] = "●"

        for i, dim in enumerate(DIMENSIONS):
            x, y = vertex(i, self.radius + 2)
            label = DIM_SHORT.get(dim, dim)
            if 0 <= x < self.width and 0 <= y < self.height:
                for j, ch in enumerate(label):
                    if x + j < self.width:
                        grid[y][x + j] = ch

        for i, ch in enumerate(title):
            if i < self.width:
                grid[0][i] = ch

        row = self.height - 3
        left = 0
        for i, dim in enumerate(DIMENSIONS):
            val = vec.get(dim, 0.0)
            text = f"{DIM_SHORT.get(dim, dim)}:{val:+.2f} "
            if left + len(text) > self.width:
                left = 0
                row += 1
                if row >= self.height:
                    break
            for j, ch in enumerate(text):
                if left + j < self.width:
                    grid[row][left + j] = ch
            left += len(text)

        return "\n".join("".join(row) for row in grid)

    @staticmethod
    def _draw_line(grid: List[List[str]], x0: int, y0: int, x1: int, y1: int, ch: str) -> None:
        dx = abs(x1 - x0)
        dy = abs(y1 - y0)
        sx = 1 if x0 < x1 else -1
        sy = 1 if y0 < y1 else -1
        err = dx - dy
        w, h = len(grid[0]), len(grid)
        while True:
            if 0 <= x0 < w and 0 <= y0 < h:
                grid[y0][x0] = ch
            if x0 == x1 and y0 == y1:
                break
            e2 = 2 * err
            if e2 > -dy:
                err -= dy
                x0 += sx
            if e2 < dx:
                err += dx
                y0 += sy

    @staticmethod
    def _fill_polygon(grid: List[List[str]], poly: List[Tuple[int, int]], ch: str) -> None:
        if not poly:
            return
        h = len(grid)
        w = len(grid[0]) if h else 0
        min_y = max(0, min(y for _, y in poly))
        max_y = min(h - 1, max(y for _, y in poly))
        for y in range(min_y, max_y + 1):
            xs = []
            n = len(poly)
            for i in range(n):
                x1, y1 = poly[i]
                x2, y2 = poly[(i + 1) % n]
                if (y1 <= y < y2) or (y2 <= y < y1):
                    if y2 != y1:
                        x = x1 + (y - y1) * (x2 - x1) / (y2 - y1)
                        xs.append(x)
            xs.sort()
            for i in range(0, len(xs) - 1, 2):
                x_start = max(0, int(math.ceil(xs[i])))
                x_end = min(w - 1, int(math.floor(xs[i + 1])))
                for x in range(x_start, x_end + 1):
                    grid[y][x] = ch

    @staticmethod
    def quick(vec: dict) -> str:
        return TerminalRadarChart().render(vec)


class HTMLDashboard:
    """零依赖单文件 HTML/CSS/JS：Canvas 2D 雷达图 + 情绪时间线 + 审计链浏览器。"""

    def __init__(self, config_path: str = "config.json"):
        with open(config_path, "r", encoding="utf-8") as f:
            cfg = json.load(f)
        vis = cfg.get("visualization", {})
        self.export_path = vis.get("html_export_path", "emotion-dashboard.html")
        mem = cfg.get("memory", {})
        self.state_path = Path(mem.get("state_path", "emotion-state.json"))
        self.journal_path = Path(mem.get("journal_path", "emotion-journal.jsonl"))
        self.audit_dir = Path(mem.get("audit_dir", "emotion-audit"))

    def _load_state(self) -> dict:
        if not self.state_path.exists():
            return {}
        try:
            with open(self.state_path, "r", encoding="utf-8") as f:
                return json.load(f)
        except (json.JSONDecodeError, OSError):
            return {}

    def _load_journal(self, limit: int = 50) -> List[dict]:
        entries = []
        if not self.journal_path.exists():
            return entries
        try:
            with open(self.journal_path, "r", encoding="utf-8") as f:
                for line in f:
                    line = line.strip()
                    if not line:
                        continue
                    try:
                        entries.append(json.loads(line))
                    except json.JSONDecodeError:
                        continue
        except OSError:
            pass
        return entries[-limit:]

    def _load_audit(self, limit: int = 100) -> List[dict]:
        entries = []
        if not self.audit_dir.exists():
            return entries
        files = sorted(self.audit_dir.glob("*.jsonl"), reverse=True)
        for filepath in files[:3]:
            try:
                with open(filepath, "r", encoding="utf-8") as f:
                    for line in f:
                        line = line.strip()
                        if not line:
                            continue
                        try:
                            entries.append(json.loads(line))
                        except json.JSONDecodeError:
                            continue
                        if len(entries) >= limit:
                            break
            except OSError:
                continue
            if len(entries) >= limit:
                break
        return entries

    def _build_html(self) -> str:
        state = self._load_state()
        journal = self._load_journal(50)
        audit = self._load_audit(100)
        vec = state.get("vec", {})
        baseline = state.get("baseline", {})

        radar_data = [{"dim": d, "value": round(vec.get(d, 0.0), 3), "baseline": round(baseline.get(d, 0.0), 3), "color": DIM_COLORS[i % len(DIM_COLORS)]} for i, d in enumerate(DIMENSIONS)]
        journal_data = []
        for entry in journal:
            ts = entry.get("ts", "")
            evec = entry.get("vec", {})
            journal_data.append({"ts": ts, "values": {d: round(evec.get(d, 0.0), 3) for d in DIMENSIONS}})
        audit_data = [{"ts": e.get("ts", ""), "type": e.get("event_type", ""), "data": json.dumps(e.get("data", {}), ensure_ascii=False)[:200]} for e in audit]

        radar_json = json.dumps(radar_data, ensure_ascii=False)
        journal_json = json.dumps(journal_data, ensure_ascii=False)
        audit_json = json.dumps(audit_data, ensure_ascii=False)
        dims_json = json.dumps(DIMENSIONS, ensure_ascii=False)
        colors_json = json.dumps(DIM_COLORS, ensure_ascii=False)
        ts_now = datetime.now(timezone.utc).isoformat()

        lines: List[str] = []
        lines.append('<!DOCTYPE html>')
        lines.append('<html lang="zh-CN">')
        lines.append('<head>')
        lines.append('<meta charset="UTF-8">')
        lines.append('<meta name="viewport" content="width=device-width, initial-scale=1.0">')
        lines.append('<title>Affective Core Dashboard</title>')
        lines.append('<style>')
        lines.append('body { font-family: -apple-system, BlinkMacSystemFont, "Segoe UI", Roboto, sans-serif; margin: 0; padding: 20px; background: #1a1a2e; color: #eee; }')
        lines.append('.container { max-width: 1200px; margin: 0 auto; }')
        lines.append('h1 { text-align: center; color: #e0e0e0; }')
        lines.append('.grid { display: grid; grid-template-columns: 1fr 1fr; gap: 20px; margin-top: 20px; }')
        lines.append('.panel { background: #16213e; border-radius: 12px; padding: 20px; }')
        lines.append('.panel h2 { margin-top: 0; color: #4ECDC4; font-size: 1.1em; }')
        lines.append('canvas { width: 100%; max-width: 500px; display: block; margin: 0 auto; }')
        lines.append('.timeline { max-height: 300px; overflow-y: auto; font-size: 0.85em; }')
        lines.append('.timeline-row { display: flex; gap: 10px; padding: 4px 0; border-bottom: 1px solid #2a2a4a; }')
        lines.append('.timeline-row .ts { color: #888; min-width: 160px; }')
        lines.append('.audit-row { display: flex; gap: 10px; padding: 4px 0; border-bottom: 1px solid #2a2a4a; font-size: 0.8em; }')
        lines.append('.audit-row .type { color: #FFEAA7; min-width: 80px; }')
        lines.append('@media (max-width: 800px) { .grid { grid-template-columns: 1fr; } }')
        lines.append('</style>')
        lines.append('</head>')
        lines.append('<body>')
        lines.append('<div class="container">')
        lines.append('<h1>🧠 Affective Core Dashboard</h1>')
        lines.append('<p style="text-align:center;color:#888;">生成时间: ' + ts_now + '</p>')
        lines.append('<div class="grid">')
        lines.append('<div class="panel"><h2>16维情绪雷达图</h2><canvas id="radar" width="500" height="400"></canvas></div>')
        lines.append('<div class="panel"><h2>数值面板</h2><div id="values" style="font-size:0.9em;line-height:1.8;"></div></div>')
        lines.append('<div class="panel"><h2>情绪日志时间线</h2><div class="timeline" id="timeline"></div></div>')
        lines.append('<div class="panel"><h2>审计链</h2><div class="timeline" id="audit"></div></div>')
        lines.append('</div>')
        lines.append('</div>')
        lines.append('<script>')
        lines.append('const DIMENSIONS = ' + dims_json + ';')
        lines.append('const COLORS = ' + colors_json + ';')
        lines.append('const RADAR_DATA = ' + radar_json + ';')
        lines.append('const JOURNAL_DATA = ' + journal_json + ';')
        lines.append('const AUDIT_DATA = ' + audit_json + ';')
        lines.append('')
        lines.append('function drawRadar() {')
        lines.append('  var canvas = document.getElementById("radar");')
        lines.append('  var ctx = canvas.getContext("2d");')
        lines.append('  var cx = canvas.width / 2, cy = canvas.height / 2;')
        lines.append('  var radius = Math.min(cx, cy) - 40;')
        lines.append('  var n = DIMENSIONS.length;')
        lines.append('  ctx.clearRect(0, 0, canvas.width, canvas.height);')
        lines.append('  for (var r = 0.2; r <= 1.0; r += 0.2) {')
        lines.append('    ctx.beginPath();')
        lines.append('    for (var i = 0; i <= n; i++) {')
        lines.append('      var angle = Math.PI / 2 - 2 * Math.PI * (i % n) / n;')
        lines.append('      var x = cx + radius * r * Math.cos(angle);')
        lines.append('      var y = cy - radius * r * Math.sin(angle);')
        lines.append('      if (i === 0) ctx.moveTo(x, y); else ctx.lineTo(x, y);')
        lines.append('    }')
        lines.append('    ctx.strokeStyle = (r === 1.0) ? "#4ECDC4" : "#333";')
        lines.append('    ctx.lineWidth = (r === 1.0) ? 2 : 1;')
        lines.append('    ctx.stroke();')
        lines.append('  }')
        lines.append('  ctx.font = "12px sans-serif";')
        lines.append('  ctx.fillStyle = "#ccc";')
        lines.append('  for (var i = 0; i < n; i++) {')
        lines.append('    var angle = Math.PI / 2 - 2 * Math.PI * i / n;')
        lines.append('    var x = cx + radius * Math.cos(angle);')
        lines.append('    var y = cy - radius * Math.sin(angle);')
        lines.append('    ctx.beginPath(); ctx.moveTo(cx, cy); ctx.lineTo(x, y); ctx.strokeStyle = "#444"; ctx.stroke();')
        lines.append('    var lx = cx + (radius + 25) * Math.cos(angle);')
        lines.append('    var ly = cy - (radius + 25) * Math.sin(angle);')
        lines.append('    ctx.textAlign = "center"; ctx.textBaseline = "middle";')
        lines.append('    ctx.fillText(DIMENSIONS[i].substring(0, 4), lx, ly);')
        lines.append('  }')
        lines.append('  ctx.beginPath();')
        lines.append('  for (var i = 0; i < n; i++) {')
        lines.append('    var angle = Math.PI / 2 - 2 * Math.PI * i / n;')
        lines.append('    var v = Math.abs(RADAR_DATA[i].value);')
        lines.append('    var x = cx + radius * v * Math.cos(angle);')
        lines.append('    var y = cy - radius * v * Math.sin(angle);')
        lines.append('    if (i === 0) ctx.moveTo(x, y); else ctx.lineTo(x, y);')
        lines.append('  }')
        lines.append('  ctx.closePath();')
        lines.append('  ctx.fillStyle = "rgba(78, 205, 196, 0.25)";')
        lines.append('  ctx.fill();')
        lines.append('  ctx.strokeStyle = "#4ECDC4"; ctx.lineWidth = 2; ctx.stroke();')
        lines.append('  for (var i = 0; i < n; i++) {')
        lines.append('    var angle = Math.PI / 2 - 2 * Math.PI * i / n;')
        lines.append('    var v = Math.abs(RADAR_DATA[i].value);')
        lines.append('    var x = cx + radius * v * Math.cos(angle);')
        lines.append('    var y = cy - radius * v * Math.sin(angle);')
        lines.append('    ctx.beginPath(); ctx.arc(x, y, 4, 0, Math.PI * 2); ctx.fillStyle = COLORS[i]; ctx.fill();')
        lines.append('  }')
        lines.append('}')
        lines.append('')
        lines.append('function renderValues() {')
        lines.append('  var div = document.getElementById("values");')
        lines.append('  div.innerHTML = RADAR_DATA.map(function(d) {')
        lines.append("    return '<span style=\"color:' + d.color + '\">●</span> ' + d.dim + ': <b>' + d.value + '</b> (基线 ' + d.baseline + ')';")
        lines.append('  }).join("<br>");')
        lines.append('}')
        lines.append('')
        lines.append('function renderTimeline() {')
        lines.append('  var div = document.getElementById("timeline");')
        lines.append('  if (!JOURNAL_DATA.length) { div.innerHTML = \'<div style="color:#666">暂无日志</div>\'; return; }')
        lines.append('  div.innerHTML = JOURNAL_DATA.slice(-20).map(function(e) {')
        lines.append('    var vals = Object.entries(e.values).filter(function(kv) { return Math.abs(kv[1]) > 0.1; });')
        lines.append('    var txt = vals.map(function(kv) { return kv[0] + ":" + kv[1]; }).join(", ");')
        lines.append("    return '<div class=\"timeline-row\"><span class=\"ts\">' + e.ts.substring(0,19) + '</span><span>' + txt + '</span></div>';")
        lines.append('  }).join("");')
        lines.append('}')
        lines.append('')
        lines.append('function renderAudit() {')
        lines.append('  var div = document.getElementById("audit");')
        lines.append('  if (!AUDIT_DATA.length) { div.innerHTML = \'<div style="color:#666">暂无审计记录</div>\'; return; }')
        lines.append('  div.innerHTML = AUDIT_DATA.slice(-20).reverse().map(function(e) {')
        lines.append("    return '<div class=\"audit-row\"><span class=\"type\">' + e.type + '</span><span>' + e.data + '</span></div>';")
        lines.append('  }).join("");')
        lines.append('}')
        lines.append('')
        lines.append('drawRadar(); renderValues(); renderTimeline(); renderAudit();')
        lines.append('</script>')
        lines.append('</body>')
        lines.append('</html>')
        return "\n".join(lines)

    def generate(self, output_path: Optional[str] = None) -> str:
        path = output_path or self.export_path
        content = self._build_html()
        with open(path, "w", encoding="utf-8") as f:
            f.write(content)
        return str(Path(path).absolute())

    @classmethod
    def quick(cls, output_path: str = "emotion-dashboard.html", config_path: str = "config.json") -> str:
        return cls(config_path).generate(output_path)


def main() -> int:
    if len(sys.argv) < 2:
        print("用法: python -m visualize <config.json> [output.html]", file=sys.stderr)
        return 1
    config_path = sys.argv[1]
    output_path = sys.argv[2] if len(sys.argv) > 2 else None
    dash = HTMLDashboard(config_path)
    state = dash._load_state()
    vec = state.get("vec", {})
    if vec:
        print(TerminalRadarChart.quick(vec))
        print()
    result = dash.generate(output_path)
    print(f"HTML Dashboard 已生成: {result}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
