"""Куда сохранять результат звонка.

Каждый «приёмник» (sink) — функция, которая получает CallResult. Чтобы
отправлять результат ещё куда-то (Telegram, Google Sheets, CRM), напиши
функцию с такой же сигнатурой и добавь её в SINKS.
"""

import csv
import json
from pathlib import Path

from .result import CallResult

RESULTS_DIR = Path("results")


def save_json(result: CallResult) -> None:
    """Полный результат одного звонка: ответы, транскрипт, ссылка на запись."""
    path = RESULTS_DIR / "calls" / f"{result.call_id}.json"
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(result.to_dict(), ensure_ascii=False, indent=2), encoding="utf-8")


def append_csv(result: CallResult) -> None:
    """Таблица по сценарию: одна строка = один звонок, столбцы = ответы.

    Если в сценарий добавили вопрос, появится новый столбец, старые строки сохранятся.
    """
    path = RESULTS_DIR / f"{result.scenario}.csv"
    row = {
        "call_id": result.call_id,
        "phone": result.phone,
        "started_at": result.started_at,
        "ended_reason": result.ended_reason,
        **result.answers,
        "recording_url": result.recording_url,
    }

    rows, columns = [], list(row)
    if path.exists():
        with path.open(encoding="utf-8-sig", newline="") as f:
            reader = csv.DictReader(f)
            rows = list(reader)
            columns = list(reader.fieldnames or []) + [c for c in row if c not in (reader.fieldnames or [])]
    rows.append(row)

    path.parent.mkdir(parents=True, exist_ok=True)
    # utf-8-sig — чтобы Excel правильно открыл кириллицу.
    with path.open("w", encoding="utf-8-sig", newline="") as f:
        writer = csv.DictWriter(f, fieldnames=columns)
        writer.writeheader()
        writer.writerows(rows)


SINKS = [save_json, append_csv]


def publish(result: CallResult) -> None:
    for sink in SINKS:
        sink(result)
