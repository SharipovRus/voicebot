"""JSON-схема результата звонка.

После разговора Vapi прогоняет транскрипт через LLM и заполняет поля по этой
схеме (structured output). Поля = вопросы из сценария + служебные поля,
одинаковые для любого сценария (чем кончился звонок, резюме и т.п.).
"""

from .scenario import Question, Scenario
from .texts import texts

_JSON_TYPES = {"string": "string", "number": "number", "boolean": "boolean", "enum": "string"}

# Чем может закончиться звонок. Описания на языке сценария — в texts.py.
OUTCOMES = ["completed", "partial", "not_relevant", "callback_requested", "refused", "wrong_number", "no_human"]
REQUIRED_STANDARD = ["outcome", "summary"]


def standard_fields(language: str) -> dict:
    """Служебные поля: есть в любом звонке, не зависят от вопросов сценария."""
    t = texts(language)
    return {
        "outcome": {
            "type": "string",
            "enum": OUTCOMES,
            "description": t["outcome"] + "; ".join(f"{k} — {t['outcomes'][k]}" for k in OUTCOMES),
        },
        "callback_time": {"type": "string", "description": t["callback_time"]},
        "comment": {"type": "string", "description": t["comment"]},
        "summary": {"type": "string", "description": t["summary"]},
    }


def build_output_schema(scenario: Scenario) -> dict:
    properties = {q.id: _question_property(q) for q in scenario.questions}
    properties.update(standard_fields(scenario.language))
    return {
        "type": "object",
        "description": texts(scenario.language)["schema"],
        "properties": properties,
        "required": REQUIRED_STANDARD,
    }


def _question_property(q: Question) -> dict:
    prop = {"type": _JSON_TYPES[q.type], "description": q.ask}
    if q.note:
        prop["description"] += f" ({q.note})"
    if q.type == "enum":
        prop["enum"] = q.options
    return prop
