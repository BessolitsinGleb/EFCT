"""Отчётность терминала: журнал операций, реестр услуг к оплате, остатки на площадке.

Расчёт хранения: контейнер прибывает операцией «размещение» и уходит операцией «выдача».
Первые free_days суток бесплатны, далее — ставка за TEU в сутки (40 фут. = 2 TEU),
неполные сутки считаются как полные. В отчёт за период попадают только сутки внутри периода.
"""
import io, math, re
from collections import defaultdict
from dataclasses import dataclass
from datetime import datetime, timedelta

import pandas as pd

OP_NAMES = {"adding": "размещение", "loading": "выдача", "rearrangement": "перестановка"}


@dataclass
class Stay:
    value: str
    company: str
    size: int | None
    arrived: datetime
    left: datetime | None      # None — ещё на площадке


def teu(size) -> int:
    return 2 if size == 40 else 1


def build_stays(moves: list[dict]) -> list[Stay]:
    """Пары «размещение → выдача» по номеру контейнера (контейнер может приходить несколько раз)."""
    stays, open_ = [], {}
    for m in sorted(moves, key=lambda m: m["movement_time"]):
        if m["moove_type"] == "adding":
            open_[m["value"]] = Stay(m["value"], m["company"], m.get("size"), m["movement_time"], None)
        elif m["moove_type"] == "loading" and m["value"] in open_:
            st = open_.pop(m["value"]); st.left = m["movement_time"]; stays.append(st)
    return stays + list(open_.values())


def billable_days(st: Stay, start: datetime, end: datetime, free_days: int, now: datetime) -> int:
    """Платные сутки хранения внутри периода [start, end]."""
    left = st.left or now
    a = max(st.arrived + timedelta(days=free_days), start)
    b = min(left, end)
    if b <= a:
        return 0
    return math.ceil((b - a).total_seconds() / 86400)


def operations_report(moves: list[dict], company: str | None, start, end) -> pd.DataFrame:
    rows = [m for m in moves if start <= m["movement_time"] <= end and (not company or m["company"] == company)]
    rows.sort(key=lambda m: m["movement_time"])
    return pd.DataFrame([{
        "Время (UTC)": m["movement_time"].strftime("%d.%m.%Y %H:%M"), "Компания": m["company"],
        "Контейнер": m["value"], "Операция": OP_NAMES.get(m["moove_type"], m["moove_type"]),
        "Размер, фут": m.get("size") or "", "Откуда": m.get("cell_from") or m.get("path_num_from") or "",
        "Куда": m.get("cell_to") or m.get("path_num_to") or "", "Стоимость, у. е.": m["price"] or 0,
    } for m in rows], columns=["Время (UTC)", "Компания", "Контейнер", "Операция", "Размер, фут",
                               "Откуда", "Куда", "Стоимость, у. е."])


def summary_report(moves: list[dict], company: str | None, start, end, free_days: int,
                   rate: float, now: datetime) -> pd.DataFrame:
    """Реестр услуг к оплате по компаниям за период: операции + платное хранение."""
    acc = defaultdict(lambda: {"размещение": 0, "выдача": 0, "перестановка": 0, "ops": 0.0, "teu_days": 0})
    for m in moves:
        if start <= m["movement_time"] <= end and (not company or m["company"] == company):
            a = acc[m["company"]]; a[OP_NAMES[m["moove_type"]]] += 1; a["ops"] += m["price"] or 0
    for st in build_stays(moves):
        if company and st.company != company:
            continue
        d = billable_days(st, start, end, free_days, now)
        if d:
            acc[st.company]["teu_days"] += d * teu(st.size)
    out = []
    for comp in sorted(acc):
        a = acc[comp]; storage = a["teu_days"] * rate
        out.append({"Компания": comp, "Размещений": a["размещение"], "Выдач": a["выдача"],
                    "Перестановок": a["перестановка"], "За операции, у. е.": round(a["ops"], 2),
                    "Платных TEU-суток хранения": a["teu_days"], "За хранение, у. е.": round(storage, 2),
                    "Итого к оплате, у. е.": round(a["ops"] + storage, 2)})
    df = pd.DataFrame(out, columns=["Компания", "Размещений", "Выдач", "Перестановок", "За операции, у. е.",
                                    "Платных TEU-суток хранения", "За хранение, у. е.", "Итого к оплате, у. е."])
    if len(df):
        total = {c: df[c].sum() for c in df.columns[1:]}
        df.loc[len(df)] = {"Компания": "ИТОГО", **total}
    return df


def inventory_report(cells: list[dict], moves: list[dict], company: str | None, free_days: int,
                     now: datetime) -> pd.DataFrame:
    """Остатки: какие контейнеры сейчас на площадке, сколько суток стоят и не просрочена ли отправка."""
    arrived = {st.value: st.arrived for st in build_stays(moves) if st.left is None}
    by_value = defaultdict(list)
    for c in cells:
        if c["value"] != "0" and (not company or c["company"] == company):
            by_value[c["value"]].append(c)
    out = []
    for value, cs in sorted(by_value.items(), key=lambda kv: kv[1][0]["company"]):
        c = cs[0]; arr = arrived.get(value)
        days = math.ceil((now - arr).total_seconds() / 86400) if arr else None
        sent = c.get("sent_date")
        out.append({"Компания": c["company"], "Контейнер": value, "Размер, фут": c.get("size") or "",
                    "Тип": c.get("cont_type") or "", "Ячейки": " + ".join(sorted(x["cell_id"] for x in cs)),
                    "Прибыл (UTC)": arr.strftime("%d.%m.%Y %H:%M") if arr else "",
                    "Суток на терминале": days if days is not None else "",
                    "Платных суток": max(0, days - free_days) if days is not None else "",
                    "Плановая отправка (UTC)": sent.strftime("%d.%m.%Y %H:%M") if sent else "",
                    "Просрочена отправка": "да" if sent and sent < now else "нет"})
    return pd.DataFrame(out, columns=["Компания", "Контейнер", "Размер, фут", "Тип", "Ячейки", "Прибыл (UTC)",
                                      "Суток на терминале", "Платных суток", "Плановая отправка (UTC)",
                                      "Просрочена отправка"])


def to_csv_bytes(df: pd.DataFrame) -> bytes:
    """CSV для Excel в русской локали: разделитель «;», кодировка с BOM."""
    return df.to_csv(index=False, sep=";", decimal=",").encode("utf-8-sig")


def safe_name(s: str) -> str:
    """Имя для заголовка HTTP — только латиница (кириллицу заголовок не пропускает)."""
    return re.sub(r"[^A-Za-z0-9_\-]", "_", s or "all")
