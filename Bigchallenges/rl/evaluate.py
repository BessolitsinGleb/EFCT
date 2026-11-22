"""Проверка на НЕвиденных при обучении seed (100–114): случайная ячейка, ближайшая к пути,
формула v1 (автор), формула v2 (подобранные веса), агент. Среднее ± 95 % ДИ (t, 14 ст. св.).
Запуск: python rl/evaluate.py --policy app/agent/agent_policy.npz --out rl/eval.json
"""
import argparse, json, os, random, statistics, sys
from concurrent.futures import ProcessPoolExecutor

sys.path.insert(0, os.path.dirname(__file__)); sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))
from app import placement as P
from app.agent import features as Fe
from app.agent.policy import Policy
from env import load_scoring
from yard_sim import YardSim, play, greedy

SEEDS = range(100, 115)
POL = None


def nearest(d, sim):
    pr = sim.cfg.path_row(d["cont"]["path"])
    best = min(d["cands"], key=lambda t: (abs(int(t[0][1:] if False else t[0][2:]) - pr), sim.cfg.layer_idx(t[0][0])))
    # «ближайшая» выбирается среди всех допустимых; переводим в индекс top, добавив её как кандидата
    for i, (_, c, _) in enumerate(d["top"]):
        if c == best[0]:
            return i
    d["top"].append((0, best[0], best[1]))
    return len(d["top"]) - 1


def agent(d, sim):
    obs, mask = Fe.observation(P, sim.cfg, sim.cells, d["cont"], d["now"], d["top"], d["kind"] == "relocate", sim.sc)
    return POL.act(obs, mask)


def one(args):
    name, seed, lam, noise, pol_path = args
    global POL
    if name == "agent" and POL is None:
        POL = Policy(pol_path)
    sc = P.DEFAULT_SCORING if name in ("formula_v1", "random", "nearest") else load_scoring()
    sim = YardSim(seed, lam=lam, noise_h=noise, sc=sc)
    if name == "random":
        r = random.Random(seed); f = lambda d, s: r.randrange(len(d["cands"])) if False else _rand(d, r)
    else:
        f = {"nearest": nearest, "formula_v1": greedy, "formula_v2": greedy, "agent": agent}[name]
    return name, lam, noise, play(sim, f)


def _rand(d, r):
    c = r.choice(d["cands"])
    for i, (_, cc, _) in enumerate(d["top"]):
        if cc == c[0]:
            return i
    d["top"].append((0, c[0], c[1]))
    return len(d["top"]) - 1


def ci(xs):
    return 2.145 * statistics.stdev(xs) / len(xs) ** 0.5


if __name__ == "__main__":
    ap = argparse.ArgumentParser()
    ap.add_argument("--policy", default=os.path.join(os.path.dirname(__file__), "..", "app", "agent", "agent_policy.npz"))
    ap.add_argument("--lams", default="0.6,0.75,0.9"); ap.add_argument("--noise", type=float, default=12)
    ap.add_argument("--names", default="random,nearest,formula_v1,formula_v2,agent")
    ap.add_argument("--out", default=os.path.join(os.path.dirname(__file__), "eval.json"))
    a = ap.parse_args()
    names = [n for n in a.names.split(",") if n != "agent" or os.path.exists(a.policy)]
    jobs = [(n, s, float(l), a.noise, a.policy) for n in names for l in a.lams.split(",") for s in SEEDS]
    res = {}
    with ProcessPoolExecutor() as pool:
        for n, l, nz, m in pool.map(one, jobs):
            res.setdefault(f"{n}|lam={l}", []).append(m)
    out = {}
    for k, rows in res.items():
        out[k] = {m: [statistics.mean(r[m] for r in rows), ci([r[m] for r in rows])] for m in rows[0]}
        o = out[k]
        print(f"{k:22s} перестановок {o['rehandle_rate'][0]:.3f}±{o['rehandle_rate'][1]:.3f}  отказов {o['reject_rate'][0]:.3f}  "
              f"у.е./конт {o['cost_per_cont'][0]:.0f}  цель {o['objective'][0]:.3f}±{o['objective'][1]:.3f}", flush=True)
    json.dump(out, open(a.out, "w"), ensure_ascii=False, indent=1)
