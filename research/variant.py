"""One rule variant against the base agent: python research/variant.py '{"SEMIS_MAX": 2}' >> results/variants.jsonl"""
import json, sys
from pathlib import Path; ROOT = Path(__file__).resolve().parents[1]; sys.path.insert(0, str(ROOT)); sys.path.insert(0, str(ROOT / 'research'))
import backtest as bt
from engine.sim import Market, run_live
ov = json.loads(sys.argv[1])
m = Market(json.load(open(ROOT / 'data' / 'bars5y.json')))
RA = ROOT / 'research' / 'agent_research.py'
rr = bt.rolling(m, lambda: bt.fresh(RA, **ov), "2022-03-01", "2026-10-09")
st = bt.stats([w['ret'] for w in rr])
# conditional on starting in ATTACK
import importlib.util
spec = importlib.util.spec_from_file_location('a', ROOT / 'research' / 'agent_research.py'); A = importlib.util.module_from_spec(spec); spec.loader.exec_module(A)
for k, v in ov.items(): setattr(A, k, v)
att = [w['ret'] for w in rr if A.regime([b['close'] for b in m.before(w['start'], 80)['QQQ']]) == A.ATTACK]
st['attack_start'] = bt.stats(att)
pre = [w['ret'] for w in rr if w['start'] < '2026-01-01']
st['pre2026'] = bt.stats(pre)
r7 = run_live(bt.fresh(RA, **ov), m, '2026-07-07', '2026-10-09', history=80)['ret']
ds = [d for d in m.dates if d <= "2026-07-02"][-16:]
r1 = run_live(bt.fresh(RA, **ov), m, ds[0], ds[-1], history=80)['ret']
print(json.dumps({'ov': ov, 'p6': st['p_ge_6pct'], 'p85': st['p_ge_8_5pct'], 'pgate': st['p_gt_arnav_gate'], 'med': st['median'], 'worst': st['worst'],
  'att_n': st['attack_start']['n'], 'att_p6': st['attack_start']['p_ge_6pct'], 'att_p85': st['attack_start']['p_ge_8_5pct'], 'att_gate': st['attack_start']['p_gt_arnav_gate'],
  'pre_p6': st['pre2026']['p_ge_6pct'], 'pre_gate': st['pre2026']['p_gt_arnav_gate'], 'r2': r7, 'r1': r1}))
