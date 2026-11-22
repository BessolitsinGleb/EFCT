"""Имитационная модель площадки для обучения и проверки агента.

Та же модель, что в разделе 5 работы (simulate.py), но переписанная как генератор решений:
симулятор сам ведёт время (пуассоновский поток, выдачи по дате отправки с ошибкой прогноза),
а в моменты, когда нужно решение «куда поставить», отдаёт управление политике.

Решения двух видов: приём нового контейнера и перестановка мешающего контейнера при выдаче.
"""
import heapq, random, sys, os
from types import SimpleNamespace

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))
from app import placement as P                     # правила площадки и тариф — из программы
from app.agent import features as Fe


class YardSim:
    def __init__(self, seed, lam=0.6, noise_h=12.0, days=90, warmup_days=14,
                 cfg=P.DEFAULT_YARD, sc=P.DEFAULT_SCORING):
        self.rng = random.Random(seed)
        self.lam, self.noise_h, self.days, self.warmup = lam, noise_h, days, warmup_days * 24
        self.cfg, self.sc = cfg, sc
        self.cells = {c: SimpleNamespace(value=P.EMPTY, size=None, dep=None) for c in cfg.all_cells()}
        self.where, self.conts = {}, {}
        self.stats = dict(arrived=0, rejected=0, loaded=0, rehandles=0, cost=0.0)
        self._gen_arrivals()

    # ---------- поток контейнеров (как в разделе 5) ----------
    def _gen_arrivals(self):
        rng, t, horizon, nid, heap = self.rng, 0.0, self.days * 24, 0, []
        while t < horizon:
            t += rng.expovariate(self.lam)
            r = rng.random()
            dwell = rng.uniform(6, 96) if r < 0.3 else rng.uniform(96, 240) if r < 0.7 else rng.uniform(240, 480)
            c = dict(id=nid, size=20 if rng.random() < 0.6 else 40, path=rng.randint(1, 3), dep=t + dwell)
            c["real_dep"] = max(t + 1, c["dep"] + rng.gauss(0, self.noise_h)) if self.noise_h else c["dep"]
            self.conts[nid] = c
            heap.append((t, 0, nid)); nid += 1
        heapq.heapify(heap)
        self.heap, self.horizon = heap, horizon

    # ---------- площадка ----------
    def put(self, cont, fp):
        for c in fp:
            self.cells[c] = SimpleNamespace(value=str(cont["id"]), size=cont["size"], dep=cont["dep"])
        self.where[cont["id"]] = fp

    def take(self, cid):
        fp = self.where.pop(cid)
        for c in fp:
            self.cells[c] = SimpleNamespace(value=P.EMPTY, size=None, dep=None)
        return fp

    def blockers(self, fp):
        out, seen = [], set()
        for c in fp:
            a = self.cfg.above(c)
            while a is not None:
                v = self.cells[a].value
                if v != P.EMPTY and v not in seen:
                    seen.add(v); out.append(int(v))
                a = self.cfg.above(a)
        layer = {cid: max(self.cfg.layer_idx(x[0]) for x in self.where[cid]) for cid in out}
        return sorted(out, key=lambda cid: -layer[cid])

    def price(self, *a, **kw):
        return P.calculation_movement_price(*a, cfg=self.cfg, **kw)

    # ---------- главный цикл: генератор решений ----------
    def run(self):
        """yield dict(kind, cont, now, top, exclude) -> получает индекс в top (или None);
        после каждого решения накапливает события в self.ev (их забирает среда)."""
        self.ev = dict(rehandles=0, cost=0.0, rejected=False, placed=False)
        while self.heap:
            now, kind, cid = heapq.heappop(self.heap)
            if now > self.horizon:
                break
            m = now >= self.warmup
            cont = self.conts[cid]
            if kind == 0:                                           # приём
                cands = Fe.candidates(P, self.cfg, self.cells, cont["size"])
                self.stats["arrived"] += m
                if not cands:
                    self.stats["rejected"] += m
                    self.ev["rejected"] = True
                    continue
                top = Fe.top_k(P, self.cfg, self.sc, self.cells, cont, now, cands)
                i = yield dict(kind="arrival", cont=cont, now=now, top=top, cands=cands)
                fp = top[i][2] if i is not None else cands[i if i is not None else 0][1]
                self.put(cont, fp)
                self.ev["placed"] = True
                c = self.price("adding", cont["size"], fp[0], path=cont["path"])
                self.ev["cost"] += c
                if m:
                    self.stats["cost"] += c
                heapq.heappush(self.heap, (cont["real_dep"], 1, cid))
            else:                                                   # выдача
                fp = self.where[cid]
                excl = frozenset(x[1:] for x in fp)
                for b in self.blockers(fp):
                    old = self.take(self.conts[b]["id"])
                    cands = Fe.candidates(P, self.cfg, self.cells, self.conts[b]["size"], excl)
                    if cands:
                        top = Fe.top_k(P, self.cfg, self.sc, self.cells, self.conts[b], now, cands)
                        i = yield dict(kind="relocate", cont=self.conts[b], now=now, top=top, cands=cands)
                        new = top[i][2]
                    else:
                        new = old
                    self.put(self.conts[b], new)
                    self.ev["rehandles"] += 1
                    c = self.price("rearrangement", self.conts[b]["size"], old[0], cell_2=new[0]) if new != old else 0
                    self.ev["cost"] += c
                    if m:
                        self.stats["rehandles"] += 1; self.stats["cost"] += c
                self.take(cid)
                c = self.price("loading", cont["size"], fp[0], path=cont["path"])
                self.ev["cost"] += c
                if m:
                    self.stats["loaded"] += 1; self.stats["cost"] += c

    def metrics(self):
        s = self.stats; L = max(s["loaded"], 1)
        return dict(rehandle_rate=s["rehandles"] / L, reject_rate=s["rejected"] / max(s["arrived"], 1),
                    cost_per_cont=s["cost"] / L,
                    objective=(s["rehandles"] + 5 * s["rejected"] + s["cost"] / 200) / L)


def play(sim, policy):
    """Прогнать симуляцию с политикой policy(decision) -> индекс в top. Вернуть метрики."""
    gen = sim.run()
    try:
        d = next(gen)
        while True:
            d = gen.send(policy(d, sim))
    except StopIteration:
        pass
    return sim.metrics()


# ---------- базовые политики ----------
def greedy(d, sim):           # формула (v1 или v2 — зависит от sim.sc): лучшая по оценке
    return 0


def make_random(seed):
    r = random.Random(seed)
    return lambda d, sim: r.randrange(len(d["top"]))
