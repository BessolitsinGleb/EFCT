"""Проверка функции награды автора на событиях симулятора (без обучения).

Прогоняет 30 суток площадки по формуле и печатает:
  - какие события встречаются и как часто;
  - какое значение даёт твоя reward() на каждом виде событий;
  - суммарную награду за эпизод у формулы и у случайного выбора — у формулы она должна быть ВЫШЕ.
Запуск: python rl/check_reward.py
"""
import os, random, sys

sys.path.insert(0, os.path.dirname(__file__)); sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))
from app.agent.reward import StepEvents, RewardConfig, reward
from env import YardEnv


def run(policy_name, seed=3):
    env = YardEnv(days=30, lams=(0.75,), noises=(12,))
    env.reset(seed=seed)
    rng, total, done = random.Random(seed), 0.0, False
    while not done:
        m = env.action_masks()
        a = 0 if policy_name == "формула" else rng.choice([i for i, v in enumerate(m) if v])
        _, r, done, _, _ = env.step(a)
        total += r
    return total


if __name__ == "__main__":
    cfg = RewardConfig()
    print("Значения твоей reward() на типичных событиях:")
    cases = {
        "поставили контейнер, ничего не случилось (стоимость 200)": StepEvents(True, False, 0, 200, 0, False),
        "поставили, а при выдаче была 1 перестановка (стоимость 450)": StepEvents(True, False, 1, 450, 0, False),
        "поставили, 3 перестановки (стоимость 900)": StepEvents(True, False, 3, 900, 0, False),
        "отказ в приёме": StepEvents(False, True, 0, 0, 0, False),
        "шаг перестановки мешающего контейнера (стоимость 250)": StepEvents(False, False, 0, 250, 0, True),
    }
    for name, ev in cases.items():
        print(f"  {name:62s} -> {reward(ev, cfg):8.3f}")
    f, r = run("формула"), run("случайно")
    print(f"\nСумма наград за 30 суток: формула {f:.1f}, случайный выбор {r:.1f}")
    print("OK: формула лучше случайного выбора" if f > r else "ВНИМАНИЕ: случайный выбор получил больше — награда поощряет не то")
