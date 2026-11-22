"""Обучение агента: PPO с маской действий (sb3-contrib MaskablePPO).

Воспроизводимость: фиксированный seed, все параметры пишутся в train_info.json вместе с хешем весов.
Запуск: python rl/train.py --steps 1000000 --envs 4 --seed 7
"""
import argparse, hashlib, json, os, sys, time

sys.path.insert(0, os.path.dirname(__file__)); sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))
import torch
from sb3_contrib import MaskablePPO
from sb3_contrib.common.wrappers import ActionMasker
from stable_baselines3.common.vec_env import SubprocVecEnv, DummyVecEnv
from stable_baselines3.common.utils import set_random_seed

from env import YardEnv
from export import export

HERE = os.path.dirname(__file__)


def make(rank, seed):
    def _f():
        e = YardEnv()
        e.reset(seed=seed * 1000 + rank)
        return ActionMasker(e, lambda env: env.action_masks())
    return _f


if __name__ == "__main__":
    ap = argparse.ArgumentParser()
    ap.add_argument("--steps", type=int, default=1_000_000)
    ap.add_argument("--envs", type=int, default=4)
    ap.add_argument("--seed", type=int, default=7)
    ap.add_argument("--out", default=os.path.join(HERE, "out"))
    a = ap.parse_args()
    os.makedirs(a.out, exist_ok=True)
    set_random_seed(a.seed); torch.set_num_threads(1)
    Vec = SubprocVecEnv if a.envs > 1 else DummyVecEnv
    venv = Vec([make(i, a.seed) for i in range(a.envs)])
    hp = dict(learning_rate=3e-4, n_steps=1024, batch_size=256, n_epochs=10, gamma=0.995, gae_lambda=0.95,
              clip_range=0.2, ent_coef=0.01, policy_kwargs=dict(net_arch=dict(pi=[128, 128], vf=[128, 128])))
    model = MaskablePPO("MlpPolicy", venv, seed=a.seed, verbose=1, device="cpu", **hp)
    t0 = time.time()
    model.learn(total_timesteps=a.steps)
    zp = os.path.join(a.out, "maskable_ppo.zip"); model.save(zp)
    npz = os.path.join(a.out, "agent_policy.npz"); sha = export(zp, npz)
    info = dict(seed=a.seed, steps=a.steps, envs=a.envs, hyperparams={k: str(v) for k, v in hp.items()},
                minutes=round((time.time() - t0) / 60, 1), policy_sha256=sha,
                reward_sha256=hashlib.sha256(open(os.path.join(HERE, "..", "app", "agent", "reward.py"), "rb").read()).hexdigest(),
                torch=torch.__version__)
    json.dump(info, open(os.path.join(a.out, "train_info.json"), "w"), indent=1)
    print(json.dumps(info, indent=1))
