"""Формула v2: автоматический подбор весов формулы оценки ячейки (Optuna, TPE).

Структура формулы та же, что у автора (раздел 4.6): три класса срочности, слагаемые
«близость к пути», «ярус», «колонна», штраф за нижний контейнер, уезжающий раньше.
Подбираются только числа. Цель — та же, что у агента: перестановки + 5·отказы + стоимость/200
в расчёте на одну выдачу (меньше — лучше).

Обучающие seed: 0–3, проверочные (evaluate.py): 100–114 — формула не видит их при подборе.
Запуск: python rl/tune_formula.py --trials 80 --out rl/formula_v2.json
"""
import argparse, json, os, sys
from concurrent.futures import ProcessPoolExecutor
from dataclasses import replace

sys.path.insert(0, os.path.dirname(__file__)); sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))
import optuna
from app import placement as P
from yard_sim import YardSim, play, greedy

TRAIN = [(s, lam) for s in range(4) for lam in (0.6, 0.9)]


def one(args):
    sc, seed, lam = args
    return play(YardSim(seed, lam=lam, noise_h=12, sc=sc), greedy)["objective"]


def make_sc(p):
    return replace(P.DEFAULT_SCORING,
                   w_urgent=(p["u_d"], p["u_l"], p["u_c"]), w_medium=(p["m_d"], p["m_l"], p["m_c"]),
                   w_long=(p["l_d"], p["l_l"], p["l_c"]), long_target_rows=p["target"],
                   lower_penalty=p["penalty"], urgent_hours=p["urgent"], medium_hours=p["medium"])


def evaluate(sc, pool):
    vals = list(pool.map(one, [(sc, s, l) for s, l in TRAIN]))
    return sum(vals) / len(vals)


if __name__ == "__main__":
    ap = argparse.ArgumentParser(); ap.add_argument("--trials", type=int, default=80)
    ap.add_argument("--out", default=os.path.join(os.path.dirname(__file__), "formula_v2.json"))
    a = ap.parse_args()
    with ProcessPoolExecutor() as pool:
        base = evaluate(P.DEFAULT_SCORING, pool)
        print(f"формула v1 (автор): цель = {base:.4f}", flush=True)

        def objective(trial):
            p = {k: trial.suggest_float(k, 1, 100) for k in ("u_d", "u_l", "u_c", "m_d", "m_l", "m_c", "l_d", "l_l", "l_c")}
            p["target"] = trial.suggest_int("target", 0, 12)
            p["penalty"] = trial.suggest_float("penalty", 0.05, 1.0)
            p["urgent"] = trial.suggest_float("urgent", 48, 144)
            p["medium"] = trial.suggest_float("medium", 168, 360)
            return evaluate(make_sc(p), pool)

        study = optuna.create_study(direction="minimize", sampler=optuna.samplers.TPESampler(seed=42))
        study.enqueue_trial({"u_d": 100, "u_l": 60, "u_c": 20, "m_d": 60, "m_l": 40, "m_c": 10, "l_d": 30, "l_l": 70,
                             "l_c": 5, "target": 5, "penalty": 0.5, "urgent": 96, "medium": 240})   # старт — формула автора
        optuna.logging.set_verbosity(optuna.logging.WARNING)
        study.optimize(objective, n_trials=a.trials, callbacks=[lambda s, t: print(
            f"trial {t.number:3d}: {t.value:.4f} (лучшее {s.best_value:.4f})", flush=True)])
    json.dump({"v1_objective": base, "best_objective": study.best_value, "params": study.best_params,
               "seed": 42, "trials": a.trials, "train": TRAIN}, open(a.out, "w"), ensure_ascii=False, indent=1)
    print("лучшие параметры:", study.best_params)
