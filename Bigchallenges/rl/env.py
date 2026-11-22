"""Среда Gymnasium для обучения агента (PPO с маской действий).

Наблюдение: признаки K=8 лучших по формуле ячеек + общие признаки (app/agent/features.py).
Действие: номер ячейки среди K кандидатов. Маска: только существующие кандидаты, а все они
уже допустимы по правилам штабелирования и правилам размещения (placement.py) — поставить
контейнер «в воздух» или на другой размер агент не может в принципе.
Награда: app/agent/reward.py (пишет автор) по событиям между двумя решениями.
Эпизод: N суток работы площадки со случайной загрузкой и ошибкой прогноза даты.
"""
import json, os, random, sys
from dataclasses import replace

import gymnasium as gym
import numpy as np

sys.path.insert(0, os.path.dirname(__file__)); sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))
from app import placement as P
from app.agent import features as Fe
from app.agent.reward import StepEvents, RewardConfig, reward
from yard_sim import YardSim

HERE = os.path.dirname(__file__)


def load_scoring(path=os.path.join(HERE, "formula_v2.json")):
    """Формула, по которой отбираются K кандидатов: v2, если подобрана, иначе исходная v1."""
    if not os.path.exists(path):
        return P.DEFAULT_SCORING
    p = json.load(open(path))["params"]
    return replace(P.DEFAULT_SCORING, w_urgent=(p["u_d"], p["u_l"], p["u_c"]), w_medium=(p["m_d"], p["m_l"], p["m_c"]),
                   w_long=(p["l_d"], p["l_l"], p["l_c"]), long_target_rows=p["target"], lower_penalty=p["penalty"],
                   urgent_hours=p["urgent"], medium_hours=p["medium"])


class YardEnv(gym.Env):
    metadata = {}

    def __init__(self, days=60, lams=(0.5, 0.6, 0.75, 0.9), noises=(0, 12, 24), sc=None, rcfg=RewardConfig()):
        self.days, self.lams, self.noises = days, lams, noises
        self.sc, self.rcfg = sc or load_scoring(), rcfg
        self.observation_space = gym.spaces.Box(-2, 2, (Fe.K * Fe.F + Fe.G,), np.float32)
        self.action_space = gym.spaces.Discrete(Fe.K)
        self._mask = np.ones(Fe.K, bool)

    def _obs(self):
        d = self.d
        obs, self._mask = Fe.observation(P, self.sim.cfg, self.sim.cells, d["cont"], d["now"], d["top"],
                                         relocation=d["kind"] == "relocate", sc=self.sc)
        return obs

    def action_masks(self):
        return self._mask

    def reset(self, seed=None, options=None):
        super().reset(seed=seed)
        rng = random.Random(seed)
        self.sim = YardSim(rng.randrange(10**9), lam=rng.choice(self.lams), noise_h=rng.choice(self.noises),
                           days=self.days, warmup_days=0, sc=self.sc)
        self.gen = self.sim.run()
        self.d = next(self.gen)
        self._clear()
        return self._obs(), {}

    def _clear(self):
        self.sim.ev.update(rehandles=0, cost=0.0, rejected=False, placed=False)

    def step(self, action):
        a = int(action)
        if not self._mask[a]:
            a = 0                                   # подстраховка: маска и так не даст выбрать
        relocation = self.d["kind"] == "relocate"
        try:
            self.d = self.gen.send(a)
            done = False
        except StopIteration:
            done = True
        ev = self.sim.ev
        r = reward(StepEvents(placed=ev["placed"], rejected=ev["rejected"], rehandles=ev["rehandles"],
                              move_cost=ev["cost"], premarshal_moves=0, relocation=relocation), self.rcfg)
        self._clear()
        obs = np.zeros(self.observation_space.shape, np.float32) if done else self._obs()
        return obs, float(r), done, False, {}
