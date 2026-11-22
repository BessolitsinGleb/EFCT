"""Политика агента в работающей программе: маленькая нейросеть (MLP) на numpy, без torch.

Веса экспортируются из обученной модели PPO (rl/export.py) в файл agent_policy.npz.
Если файла нет или он не подходит — агент выключен, программа работает по формуле.
"""
import hashlib, os
import numpy as np

from . import features as Fe

DEFAULT_PATH = os.path.join(os.path.dirname(__file__), "agent_policy.npz")


class Policy:
    def __init__(self, path=DEFAULT_PATH):
        z = np.load(path)
        self.layers = [(z[f"W{i}"], z[f"b{i}"]) for i in range(int(z["n_hidden"]))]
        self.Wa, self.ba = z["Wa"], z["ba"]
        if self.layers[0][0].shape[0] != Fe.K * Fe.F + Fe.G:
            raise ValueError("веса не соответствуют признакам")
        self.sha256 = hashlib.sha256(open(path, "rb").read()).hexdigest()

    def logits(self, obs):
        h = np.asarray(obs, np.float32)
        for W, b in self.layers:
            h = np.tanh(h @ W + b)                    # как в PPO stable-baselines3 (Tanh)
        return h @ self.Wa + self.ba

    def act(self, obs, mask):
        lg = self.logits(obs)
        lg = np.where(mask, lg, -np.inf)
        return int(np.argmax(lg))                     # в программе — детерминированный выбор


def load(path=DEFAULT_PATH):
    try:
        return Policy(path)
    except Exception:
        return None
