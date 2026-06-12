"""Renderer adapter — self-contained interactive HTML.

Emits a single file with the graph embedded as JSON and a dependency-free,
offline force-directed visualization (vanilla JS + canvas). Features: search,
confidence filter, community coloring, drag, and zoom. No CDN, no build step.
"""

from __future__ import annotations

import json

from ..domain.models import GraphSnapshot

_TEMPLATE = """<!doctype html>
<html lang="en">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>Lattice graph</title>
<style>
  :root {{ color-scheme: dark; }}
  * {{ box-sizing: border-box; }}
  body {{ margin: 0; font: 13px system-ui, sans-serif; background: #0e1116;
         color: #e6edf3; }}
  #bar {{ position: fixed; top: 0; left: 0; right: 0; display: flex; gap: 8px;
         align-items: center; padding: 8px 12px; background: #161b22;
         border-bottom: 1px solid #30363d; z-index: 2; }}
  #bar input, #bar select {{ background: #0e1116; color: #e6edf3;
         border: 1px solid #30363d; border-radius: 6px; padding: 5px 8px; }}
  #bar .stat {{ margin-left: auto; opacity: .7; }}
  canvas {{ display: block; }}
  #tip {{ position: fixed; pointer-events: none; background: #161b22;
         border: 1px solid #30363d; border-radius: 6px; padding: 4px 8px;
         font-size: 12px; display: none; z-index: 3; }}
</style>
</head>
<body>
<div id="bar">
  <input id="q" placeholder="search nodes…" autocomplete="off">
  <select id="conf">
    <option value="all">all confidences</option>
    <option value="extracted">extracted</option>
    <option value="inferred">inferred</option>
    <option value="ambiguous">ambiguous</option>
  </select>
  <span class="stat" id="stat"></span>
</div>
<div id="tip"></div>
<canvas id="c"></canvas>
<script id="data" type="application/json">{data}</script>
<script>
const G = JSON.parse(document.getElementById('data').textContent);
const canvas = document.getElementById('c'), ctx = canvas.getContext('2d');
const tip = document.getElementById('tip');
let W, H, DPR = window.devicePixelRatio || 1;
function resize() {{
  W = innerWidth; H = innerHeight;
  canvas.width = W * DPR; canvas.height = H * DPR;
  canvas.style.width = W + 'px'; canvas.style.height = H + 'px';
  ctx.setTransform(DPR, 0, 0, DPR, 0, 0);
}}
addEventListener('resize', resize); resize();

const idx = new Map(G.nodes.map((n, i) => [n.id, i]));
const N = G.nodes.map(n => ({{
  ...n, x: Math.random() * W, y: Math.random() * H, vx: 0, vy: 0
}}));
const E = G.edges
  .filter(e => idx.has(e.source) && idx.has(e.target))
  .map(e => ({{ ...e, s: idx.get(e.source), t: idx.get(e.target) }}));

// Degree → node radius.
const deg = new Array(N.length).fill(0);
E.forEach(e => {{ deg[e.s]++; deg[e.t]++; }});

const PALETTE = ['#58a6ff','#3fb950','#f778ba','#d29922','#a371f7',
                 '#ff7b72','#56d4dd','#e3b341','#79c0ff','#7ee787'];
const color = n => n.meta && n.meta.community >= 0
  ? PALETTE[n.meta.community % PALETTE.length] : '#8b949e';

// View transform (pan/zoom).
let scale = 1, ox = 0, oy = 0;
let view = {{ q: '', conf: 'all' }};

function visibleNode(n) {{
  if (view.q && !n.label.toLowerCase().includes(view.q)) return false;
  return true;
}}
function visibleEdge(e) {{
  if (view.conf !== 'all' && e.confidence !== view.conf) return false;
  return visibleNode(N[e.s]) && visibleNode(N[e.t]);
}}

// Barnes-Hut-free O(n^2) repulsion is fine for these graph sizes.
function step() {{
  const k = 0.02, rep = 1400;
  for (let i = 0; i < N.length; i++) {{
    let fx = 0, fy = 0;
    for (let j = 0; j < N.length; j++) {{
      if (i === j) continue;
      let dx = N[i].x - N[j].x, dy = N[i].y - N[j].y;
      let d2 = dx * dx + dy * dy + 0.01;
      let f = rep / d2;
      fx += dx * f; fy += dy * f;
    }}
    N[i].vx = (N[i].vx + fx) * 0.85;
    N[i].vy = (N[i].vy + fy) * 0.85;
  }}
  for (const e of E) {{
    let a = N[e.s], b = N[e.t];
    let dx = b.x - a.x, dy = b.y - a.y;
    a.vx += dx * k; a.vy += dy * k;
    b.vx -= dx * k; b.vy -= dy * k;
  }}
  for (const n of N) {{
    n.x += Math.max(-8, Math.min(8, n.vx));
    n.y += Math.max(-8, Math.min(8, n.vy));
  }}
}}

function draw() {{
  ctx.clearRect(0, 0, W, H);
  ctx.save(); ctx.translate(ox, oy); ctx.scale(scale, scale);
  ctx.lineWidth = 0.6 / scale;
  for (const e of E) {{
    if (!visibleEdge(e)) continue;
    ctx.strokeStyle = e.confidence === 'extracted' ? '#3a4654' : '#2b333d';
    ctx.beginPath();
    ctx.moveTo(N[e.s].x, N[e.s].y); ctx.lineTo(N[e.t].x, N[e.t].y); ctx.stroke();
  }}
  for (let i = 0; i < N.length; i++) {{
    const n = N[i]; if (!visibleNode(n)) continue;
    const r = 2.5 + Math.min(9, deg[i] * 0.7);
    ctx.fillStyle = color(n);
    ctx.beginPath(); ctx.arc(n.x, n.y, r, 0, 6.2832); ctx.fill();
  }}
  ctx.restore();
}}

let shown = 0;
function tick() {{ step(); draw(); requestAnimationFrame(tick); }}
tick();

// Interaction: pan, zoom, hover.
let drag = null;
canvas.addEventListener('mousedown', e => drag = {{ x: e.clientX, y: e.clientY }});
addEventListener('mouseup', () => drag = null);
addEventListener('mousemove', e => {{
  if (drag) {{ ox += e.clientX - drag.x; oy += e.clientY - drag.y;
               drag = {{ x: e.clientX, y: e.clientY }}; return; }}
  const mx = (e.clientX - ox) / scale, my = (e.clientY - oy) / scale;
  let hit = null;
  for (let i = 0; i < N.length; i++) {{
    if (!visibleNode(N[i])) continue;
    const dx = N[i].x - mx, dy = N[i].y - my;
    if (dx * dx + dy * dy < 80) {{ hit = N[i]; break; }}
  }}
  if (hit) {{ tip.style.display = 'block'; tip.style.left = (e.clientX + 12) + 'px';
    tip.style.top = (e.clientY + 12) + 'px';
    tip.textContent = hit.label + '  ·  ' + hit.kind; }}
  else tip.style.display = 'none';
}});
canvas.addEventListener('wheel', e => {{
  e.preventDefault();
  const f = e.deltaY < 0 ? 1.1 : 0.9;
  ox = e.clientX - (e.clientX - ox) * f;
  oy = e.clientY - (e.clientY - oy) * f;
  scale *= f;
}}, {{ passive: false }});

function refreshStat() {{
  shown = N.filter(visibleNode).length;
  document.getElementById('stat').textContent =
    shown + '/' + N.length + ' nodes · ' + E.length + ' edges';
}}
document.getElementById('q').addEventListener('input', e => {{
  view.q = e.target.value.toLowerCase(); refreshStat();
}});
document.getElementById('conf').addEventListener('change', e => {{
  view.conf = e.target.value; refreshStat();
}});
refreshStat();
</script>
</body>
</html>
"""


class HtmlRenderer:
    def render(self, snapshot: GraphSnapshot, out_path: str) -> str:
        data = {
            "nodes": [
                {"id": n.id, "label": n.label, "kind": n.kind, "meta": n.meta}
                for n in snapshot.nodes.values()
            ],
            "edges": [
                {"source": e.source, "target": e.target,
                 "relation": e.relation, "confidence": e.confidence.value}
                for e in snapshot.edges
            ],
        }
        html = _TEMPLATE.format(data=json.dumps(data))
        with open(out_path, "w", encoding="utf-8") as fh:
            fh.write(html)
        return out_path
