"""Командная строка.

  python -m voicebot preview                 — показать промпт и поля, которые соберёт бот
  python -m voicebot check                   — проверить ключ Vapi и номер для звонков
  python -m voicebot publish                 — загрузить сценарий в Vapi, чтобы поговорить с ботом в браузере
  python -m voicebot call <номер>            — позвонить и сохранить результат
  python -m voicebot call 87011234567 --dry-run   — показать запрос в Vapi, не звоня
  python -m voicebot fetch <call_id>         — забрать результат уже прошедшего звонка
  python -m voicebot report                  — сводка по всем звонкам сценария + HTML-страница
  python -m voicebot site                    — пересобрать демо-страницу в docs/ (GitHub Pages)
"""

import argparse
import json
import os
import re
import sys
from pathlib import Path

import requests
from dotenv import load_dotenv

from .analytics import OUTCOME_LABELS, build_report, load_results
from .assistant import build_assistant
from .prompt import build_system_prompt
from .report import build_html
from .result import CallResult, parse_call
from .scenario import Scenario, ScenarioError, load_scenario
from .schema import build_output_schema
from .sinks import RESULTS_DIR, publish
from .vapi import VapiClient, VapiError

DEFAULT_SCENARIO = "scenarios/abandoned_application.yaml"
SCENARIOS_DIR = Path("scenarios")
SITE_DIR = Path("docs")


def main(argv: list[str] | None = None) -> int:
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")
    load_dotenv()
    args = _parse_args(argv)
    try:
        scenario = load_scenario(args.scenario, dict(args.var))
        return args.handler(args, scenario)
    except (ScenarioError, VapiError, ValueError, requests.RequestException) as e:
        print(f"Ошибка: {e}", file=sys.stderr)
        return 1


def cmd_preview(args, scenario: Scenario) -> int:
    if args.json:
        print(json.dumps(build_assistant(scenario), ensure_ascii=False, indent=2))
        return 0
    print("=== Первая фраза ===\n" + scenario.first_message)
    print("\n=== Системный промпт ===\n" + build_system_prompt(scenario))
    print("\n=== Что соберём после звонка ===")
    for name, prop in build_output_schema(scenario)["properties"].items():
        print(f"  {name:<18} {prop['type']:<8} {prop['description'][:80]}")
    return 0


def cmd_check(args, scenario: Scenario) -> int:
    client = _client()
    client.ping()
    print("Ключ VAPI_API_KEY работает.")
    phone_number_id = os.getenv("VAPI_PHONE_NUMBER_ID")
    if not phone_number_id:
        print("VAPI_PHONE_NUMBER_ID не задан: в браузере поговорить можно, позвонить на телефон — нет.")
        return 0
    number = client.get_phone_number(phone_number_id)
    print(f"Номер для звонков: {number.get('number')} (провайдер: {number.get('provider')})")
    return 0


def cmd_publish(args, scenario: Scenario) -> int:
    saved, created = _client().save_assistant(build_assistant(scenario))
    print(f"Ассистент {scenario.name} {'создан' if created else 'обновлён'}.")
    print(f"\nОткройте https://dashboard.vapi.ai/assistants/{saved['id']} и нажмите Talk to Assistant.")
    print("После разговора результат: python -m voicebot fetch <id звонка из раздела Calls>")
    return 0


def cmd_site(args, scenario: Scenario) -> int:
    """Собирает демо-страницу в docs/ (её показывает GitHub Pages).

    Для каждого сценария из scenarios/: обновляет ассистента в Vapi, чтобы с ним можно
    было поговорить из браузера, и пересобирает страницу аналитики. Всё, что нужно
    странице, пишется в docs/config.js.
    """
    client = _client()
    entries = []
    for path in sorted(SCENARIOS_DIR.glob("*.yaml")):
        s = load_scenario(path)
        saved, created = client.save_assistant(build_assistant(s))
        report = build_report(s, load_results(RESULTS_DIR, s.name))
        page = f"analytics/{s.name}.html"
        (SITE_DIR / page).parent.mkdir(parents=True, exist_ok=True)
        (SITE_DIR / page).write_text(build_html(report), encoding="utf-8")
        entries.append(
            {
                "name": s.name,
                "language": s.language,
                "assistantId": saved["id"],
                "firstMessage": s.first_message,
                "demoHint": s.demo_hint or "",
                "questions": [q.ask for q in s.questions],
                "analytics": page,
                "calls": len(report.calls),
            }
        )
        print(f"  {s.name} ({s.language}): ассистент {'создан' if created else 'обновлён'}, звонков в аналитике: {len(report.calls)}")

    public_key = os.getenv("VAPI_PUBLIC_KEY", "")
    config = json.dumps({"publicKey": public_key, "scenarios": entries}, ensure_ascii=False, indent=2)
    (SITE_DIR / "config.js").write_text(
        f"// Собирается командой `python -m voicebot site`, руками не править.\nwindow.VOICEBOT = {config};\n",
        encoding="utf-8",
    )
    print(f"\nГотово: {SITE_DIR / 'index.html'}. На сайт уходит после git push.")
    if not public_key:
        print("VAPI_PUBLIC_KEY не задан: кнопка разговора на странице работать не будет (см. README).")
    return 0


def cmd_call(args, scenario: Scenario) -> int:
    phone = normalize_phone(args.phone)
    assistant = build_assistant(scenario)
    if args.dry_run:
        payload = {"assistant": assistant, "phoneNumberId": "<VAPI_PHONE_NUMBER_ID>", "customer": {"number": phone}}
        print(json.dumps(payload, ensure_ascii=False, indent=2))
        return 0

    client = _client()
    call = client.create_call(assistant, _env("VAPI_PHONE_NUMBER_ID"), phone)
    print(f"Звонок создан: {call['id']} → {phone}")
    if args.no_wait:
        print(f"Результат потом: python -m voicebot fetch {call['id']}")
        return 0

    call = client.wait_for_result(call["id"], on_status=lambda s: print(f"  статус: {s}", flush=True))
    _finish(parse_call(call, scenario))
    return 0


def cmd_fetch(args, scenario: Scenario) -> int:
    call = _client().get_call(args.call_id)
    if call.get("status") != "ended":
        print(f"Звонок ещё идёт (статус: {call.get('status')}), попробуйте позже.")
        return 1
    _finish(parse_call(call, scenario))
    return 0


def cmd_report(args, scenario: Scenario) -> int:
    calls = load_results(RESULTS_DIR, scenario.name)
    report = build_report(scenario, calls)
    out = Path(args.out or RESULTS_DIR / f"{scenario.name}_report.html")
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(build_html(report), encoding="utf-8")

    if not calls:
        print(f"Звонков по сценарию {scenario.name} пока нет. Страница-заготовка: {out}")
        return 0
    n = len(calls)
    print(f"Звонков: {n}")
    print("Воронка: " + " → ".join(f"{stage} {count} ({round(100 * count / n)}%)" for stage, count in report.funnel))
    print("Итоги: " + ", ".join(f"{OUTCOME_LABELS.get(k, k)} {v}" for k, v in report.outcomes.most_common()))
    print(
        f"Деньги: всего ${report.total_cost:.2f}, за звонок {_usd(report.cost_per_call)}, "
        f"за успешный звонок {_usd(report.cost_per_completed)}, за минуту {_usd(report.cost_per_minute)}"
    )
    gaps = [q for q in report.questions if q.fill_rate is not None and q.answered < q.conversations]
    for q in sorted(gaps, key=lambda q: q.fill_rate)[:3]:
        print(f"  без ответа чаще всего: {q.question.id} — ответ в {q.answered} из {q.conversations} разговоров")
    if report.callbacks:
        print(f"Просили перезвонить: {len(report.callbacks)}")
    print(f"\nСтраница с аналитикой: {out}")
    return 0


def _finish(result: CallResult) -> None:
    publish(result)
    _print_result(result)
    print(f"\nСохранено: {RESULTS_DIR / 'calls' / (result.call_id + '.json')}, {RESULTS_DIR / (result.scenario + '.csv')}")
    print("Сводка по всем звонкам: python -m voicebot report")


def _print_result(r: CallResult) -> None:
    cost = f", ${r.cost_usd:.2f}" if r.cost_usd is not None else ""
    print(f"\nЗвонок завершён: {r.ended_reason}, длительность {_duration(r)}{cost}")
    print(f"Итог: {r.answers.get('outcome') or 'нет данных'} — {r.answers.get('summary') or ''}")
    for key, value in r.answers.items():
        if key not in ("outcome", "summary"):
            print(f"  {key:<18} {_fmt(value)}")
    if r.missing_required:
        print(f"Нет ответа на обязательные вопросы: {', '.join(r.missing_required)}")
    if r.recording_url:
        print(f"Запись: {r.recording_url}")


def normalize_phone(raw: str) -> str:
    """'8 (701) 123-45-67', '7011234567', '+77011234567' → '+77011234567'.

    Без «+» номер считается казахстанским. Номера других стран — с кодом страны:
    '+49 151 2345 6789'.
    """
    digits = re.sub(r"\D", "", raw)
    if raw.strip().startswith("+"):
        phone = "+" + digits
    elif len(digits) == 11 and digits[0] in "78":
        phone = "+7" + digits[1:]
    elif len(digits) == 10:
        phone = "+7" + digits
    else:
        phone = "+" + digits
    # Код страны не начинается с 0: '+0151…' — это местный номер без кода страны.
    if not re.fullmatch(r"\+[1-9]\d{9,14}", phone):
        raise ValueError(f"Не похоже на номер телефона: {raw}. Номер другой страны пишите с кодом: +49 151 2345 6789")
    return phone


def _duration(r: CallResult) -> str:
    seconds = r.duration_seconds
    if seconds is None:
        return "—"
    return f"{seconds // 60}:{seconds % 60:02d}"


def _usd(value: float | None) -> str:
    return f"${value:.2f}" if value is not None else "—"


def _fmt(value) -> str:
    if value is None:
        return "—"
    if isinstance(value, bool):
        return "да" if value else "нет"
    return str(value)


def _client() -> VapiClient:
    return VapiClient(_env("VAPI_API_KEY"))


def _env(name: str) -> str:
    value = os.getenv(name)
    if not value:
        raise ValueError(f"Не задана переменная окружения {name} (см. .env.example)")
    return value


def _parse_var(text: str) -> tuple[str, str]:
    if "=" not in text:
        raise argparse.ArgumentTypeError("формат: --var имя=значение")
    key, value = text.split("=", 1)
    return key.strip(), value.strip()


def _parse_args(argv):
    parser = argparse.ArgumentParser(prog="voicebot", description="Голосовой бот: звонит и собирает ответы")
    common = argparse.ArgumentParser(add_help=False)
    common.add_argument("--scenario", default=DEFAULT_SCENARIO, help="путь к YAML сценария")
    common.add_argument("--var", type=_parse_var, action="append", default=[], help="переопределить переменную: --var car='Kia Rio'")
    sub = parser.add_subparsers(required=True)

    p = sub.add_parser("preview", parents=[common], help="показать промпт и поля результата")
    p.add_argument("--json", action="store_true", help="полный JSON ассистента для Vapi")
    p.set_defaults(handler=cmd_preview)

    p = sub.add_parser("check", parents=[common], help="проверить ключ Vapi и номер")
    p.set_defaults(handler=cmd_check)

    p = sub.add_parser("publish", parents=[common], help="загрузить сценарий в Vapi для теста в браузере")
    p.set_defaults(handler=cmd_publish)

    p = sub.add_parser("call", parents=[common], help="позвонить на номер")
    p.add_argument("phone")
    p.add_argument("--dry-run", action="store_true", help="только показать запрос, не звонить")
    p.add_argument("--no-wait", action="store_true", help="не ждать окончания звонка")
    p.set_defaults(handler=cmd_call)

    p = sub.add_parser("fetch", parents=[common], help="забрать результат звонка по id")
    p.add_argument("call_id")
    p.set_defaults(handler=cmd_fetch)

    p = sub.add_parser("report", parents=[common], help="аналитика по всем звонкам сценария")
    p.add_argument("--out", help="куда сохранить HTML (по умолчанию results/<сценарий>_report.html)")
    p.set_defaults(handler=cmd_report)

    p = sub.add_parser("site", parents=[common], help="пересобрать демо-страницу в docs/")
    p.set_defaults(handler=cmd_site)

    return parser.parse_args(argv)
