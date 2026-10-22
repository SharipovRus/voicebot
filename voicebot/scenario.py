"""Загрузка сценария звонка из YAML.

Сценарий — единственный источник правды о том, что бот говорит и что собирает.
Здесь он читается, проверяется и в нём подставляются переменные {{имя}}.
"""

import re
from dataclasses import dataclass, field
from pathlib import Path

import yaml

from .texts import TEXTS

QUESTION_TYPES = {"string", "number", "boolean", "enum"}
_ID_RE = re.compile(r"^[a-z][a-z0-9_]*$")
_VAR_RE = re.compile(r"\{\{\s*(\w+)\s*\}\}")


class ScenarioError(ValueError):
    """Ошибка в файле сценария. Сообщение объясняет, что исправить."""


@dataclass
class Question:
    id: str
    ask: str
    type: str = "string"
    options: list[str] = field(default_factory=list)
    required: bool = False
    ask_if: str | None = None
    note: str | None = None


@dataclass
class Scenario:
    name: str
    persona: str
    first_message: str
    questions: list[Question]
    rules: list[str]
    end_message: str
    vapi: dict
    variables: dict[str, str]
    language: str = "ru"
    demo_hint: str | None = None  # кого играет человек на демо-странице


def load_scenario(path: str | Path, overrides: dict[str, str] | None = None) -> Scenario:
    """Читает YAML, подставляет переменные и проверяет сценарий.

    overrides — значения переменных из командной строки, они важнее файла.
    """
    raw = yaml.safe_load(Path(path).read_text(encoding="utf-8")) or {}

    variables = {k: str(v) for k, v in (raw.get("variables") or {}).items()}
    variables.update(overrides or {})

    def render(text: str | None) -> str | None:
        return None if text is None else _render(str(text).strip(), variables)

    for key in ("name", "persona", "first_message", "questions", "end_message"):
        if not raw.get(key):
            raise ScenarioError(f"В сценарии нет обязательного поля '{key}'")

    vapi = raw.get("vapi") or {}
    for key in ("model", "voice", "transcriber"):
        if not isinstance(vapi.get(key), dict):
            raise ScenarioError(f"В блоке vapi не заполнено '{key}'")

    language = raw.get("language", "ru")
    if language not in TEXTS:
        raise ScenarioError(f"Язык '{language}' не поддерживается, можно: {', '.join(TEXTS)} (см. voicebot/texts.py)")

    rules = raw.get("rules") or []
    for rule in rules:
        # «Текст: ещё текст» без кавычек YAML читает как словарь, а не как строку.
        if not isinstance(rule, str):
            raise ScenarioError(f"Правило прочиталось не как текст: {rule!r}. Если в нём есть «: », возьмите его в кавычки")

    questions = [_parse_question(q, render) for q in raw["questions"]]
    ids = [q.id for q in questions]
    duplicates = {i for i in ids if ids.count(i) > 1}
    if duplicates:
        raise ScenarioError(f"Повторяются id вопросов: {', '.join(sorted(duplicates))}")

    return Scenario(
        name=raw["name"],
        persona=render(raw["persona"]),
        first_message=render(raw["first_message"]),
        questions=questions,
        rules=[render(r) for r in rules],
        end_message=render(raw["end_message"]),
        vapi=vapi,
        variables=variables,
        language=language,
        demo_hint=render(raw.get("demo_hint")),
    )


def _parse_question(raw: dict, render) -> Question:
    q = Question(
        id=raw.get("id", ""),
        ask=render(raw.get("ask")) or "",
        type=raw.get("type", "string"),
        options=[str(o) for o in raw.get("options") or []],
        required=bool(raw.get("required", False)),
        ask_if=render(raw.get("ask_if")),
        note=render(raw.get("note")),
    )
    where = f"вопрос '{q.id or '?'}'"
    if not _ID_RE.match(q.id):
        raise ScenarioError(f"{where}: id должен быть латиницей в нижнем регистре, например price_total")
    if not q.ask:
        raise ScenarioError(f"{where}: не заполнено поле ask")
    if q.type not in QUESTION_TYPES:
        raise ScenarioError(f"{where}: тип '{q.type}' не поддерживается, можно: {', '.join(sorted(QUESTION_TYPES))}")
    if q.type == "enum" and not q.options:
        raise ScenarioError(f"{where}: для типа enum нужен список options")
    return q


def _render(text: str, variables: dict[str, str]) -> str:
    def replace(match: re.Match) -> str:
        name = match.group(1)
        if name not in variables:
            raise ScenarioError(f"Переменная {{{{{name}}}}} не задана в блоке variables")
        return variables[name]

    return _VAR_RE.sub(replace, text)
