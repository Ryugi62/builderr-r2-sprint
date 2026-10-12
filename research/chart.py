"""Static SVG for the README: Round 2 window equity, this agent vs the Round 1 winner's official
curve vs QQQ (official market curve). Data: results/backtest.json + data/official_*.json."""
import json
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
res = json.load(open(ROOT / "results" / "backtest.json"))["S7_round2_same_period"]
off = json.load(open(ROOT / "data" / "official_round2_results_2026-10-09.json"))
hist = json.load(open(ROOT / "data" / "official_round2_history_2026-10-09.json"))
dates = hist["dates"]
series = [("This agent (backtest)", res["agent_curve"], "#2a78d6", ""),
          ("Round 1 winner (official)", off["arnav"]["curve"], "#eb6834", ""),
          ("QQQ buy and hold (official)", hist["market"]["curve"], "#1baf7a", "6 4")]
W, H, L, R, T, B = 820, 370, 56, 180, 44, 48
vals = [v for _, c, _, _ in series for v in c]
lo, hi = min(vals) * 0.995, max(vals) * 1.005
x = lambda i: L + i * (W - L - R) / (len(dates) - 1)
y = lambda v: T + (hi - v) * (H - T - B) / (hi - lo)
out = [f'<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 {W} {H}" font-family="system-ui,-apple-system,Segoe UI,sans-serif" font-size="12">',
       f'<rect width="{W}" height="{H}" fill="#fcfcfb"/>',
       f'<text x="{L}" y="22" font-size="14" font-weight="600" fill="#0b0b0b">$100k paper account, Round 2 window 2026-07-07 .. 2026-10-09 (68 sessions)</text>']
step = 2500
v = (int(lo) // step + 1) * step
while v < hi:
    out.append(f'<line x1="{L}" x2="{W-R}" y1="{y(v):.1f}" y2="{y(v):.1f}" stroke="#e6e5e0" stroke-width="1"/>')
    out.append(f'<text x="{L-6}" y="{y(v)+4:.1f}" text-anchor="end" fill="#52514e">${v/1000:.1f}k</text>')
    v += step
for i in range(0, len(dates), 17):
    out.append(f'<text x="{x(i):.1f}" y="{H-B+18}" text-anchor="middle" fill="#52514e">{dates[i][5:]}</text>')
for name, c, col, dash in series:
    pts = " ".join(f"{x(i):.1f},{y(val):.1f}" for i, val in enumerate(c))
    da = f' stroke-dasharray="{dash}"' if dash else ""
    out.append(f'<polyline points="{pts}" fill="none" stroke="{col}" stroke-width="2"{da} stroke-linejoin="round"/>')
    ret = c[-1] / 100000 - 1
    out.append(f'<circle cx="{x(len(c)-1):.1f}" cy="{y(c[-1]):.1f}" r="4" fill="{col}" stroke="#fcfcfb" stroke-width="2"/>')
    out.append(f'<text x="{x(len(c)-1)+8:.1f}" y="{y(c[-1])+4:.1f}" fill="#0b0b0b">{name.split(" (")[0]} {ret*100:+.2f}%</text>')
ly = H - 8
lx = L
for name, _, col, dash in series:
    da = f' stroke-dasharray="{dash}"' if dash else ""
    out.append(f'<line x1="{lx}" x2="{lx+18}" y1="{ly-4}" y2="{ly-4}" stroke="{col}" stroke-width="2"{da}/>')
    out.append(f'<text x="{lx+22}" y="{ly}" fill="#52514e" font-size="11">{name}</text>')
    lx += 22 + 6.0 * len(name) + 14
out.append("</svg>")
(ROOT / "docs").mkdir(exist_ok=True)
(ROOT / "docs" / "round2_window.svg").write_text("\n".join(out))
print("wrote docs/round2_window.svg")
