"""Сборка системного промпта из сценария.

Промпт — это «инструкция» для LLM, которая ведёт разговор. Он целиком
собирается из YAML: персона → вопросы → правила → как завершать звонок.
Служебные фразы между ними — на языке сценария (texts.py).
"""

from .scenario import Question, Scenario
from .texts import texts


def build_system_prompt(scenario: Scenario) -> str:
    t = texts(scenario.language)
    parts = [
        scenario.persona,
        t["questions"] + "\n" + "\n".join(_format_question(i, q, t) for i, q in enumerate(scenario.questions, 1)),
    ]
    if scenario.rules:
        parts.append(t["rules"] + "\n" + "\n".join(f"- {r}" for r in scenario.rules))
    parts.append(t["end_call"].format(end_message=scenario.end_message))
    return "\n\n".join(parts)


def _format_question(index: int, q: Question, t: dict) -> str:
    line = f"{index}. {q.ask}"
    if q.required:
        line += " " + t["required"]
    if q.ask_if:
        line += "\n   " + t["ask_if"].format(q.ask_if)
    if q.type == "enum":
        line += "\n   " + t["enum"].format(", ".join(q.options))
    if q.note:
        line += "\n   " + t["note"].format(q.note)
    return line
