"""Сводная аналитика по всем звонкам сценария.

Один звонок — это одна строка ответов. Здесь звонки складываются в общую картину:
воронка (набрали → дозвонились → поговорили с человеком → собрали все ответы),
чем заканчивались звонки, на какие вопросы чаще нет ответа, что отвечали и
сколько стоит один успешный звонок.

Источник — JSON-файлы звонков в results/calls: в них есть всё, включая цену и время.
"""

import json
import statistics
from collections import Counter
from dataclasses import dataclass, field
from pathlib import Path

from .result import CallResult
from .scenario import Question, Scenario

# Трубку не взяли или не соединилось: разговора не было совсем.
NOT_REACHED = {"customer-did-not-answer", "customer-busy"}

# Короткие подписи для служебного поля outcome (полные описания — в schema.OUTCOMES).
OUTCOME_LABELS = {
    "completed": "собрали все ответы",
    "partial": "часть ответов",
    "not_relevant": "неактуально",
    "callback_requested": "просили перезвонить",
    "refused": "отказались говорить",
    "wrong_number": "не тот номер",
    "no_human": "не человек",
    None: "нет данных",
}

# Причины окончания звонка от Vapi (endedReason). Незнакомые показываем как есть.
ENDED_REASON_LABELS = {
    "assistant-ended-call": "бот завершил разговор",
    "customer-ended-call": "собеседник положил трубку",
    "customer-did-not-answer": "не взяли трубку",
    "customer-busy": "занято",
    "voicemail": "автоответчик",
    "silence-timed-out": "долгая тишина",
    "exceeded-max-duration": "кончилось время звонка",
}


@dataclass
class QuestionStats:
    question: Question
    answered: int  # в скольких разговорах есть ответ
    conversations: int  # из скольких разговоров с человеком
    counts: Counter = field(default_factory=Counter)  # boolean / enum: сколько раз какой ответ
    numbers: list[float] = field(default_factory=list)  # number: все ответы-числа
    examples: list[str] = field(default_factory=list)  # string: последние ответы

    @property
    def fill_rate(self) -> float | None:
        return self.answered / self.conversations if self.conversations else None


@dataclass
class Report:
    scenario: str
    calls: list[CallResult]
    funnel: list[tuple[str, int]]  # (этап, сколько звонков дошло)
    outcomes: Counter
    ended_reasons: Counter
    questions: list[QuestionStats]
    total_cost: float
    total_minutes: float
    avg_duration_seconds: float | None  # средняя длительность звонков, где взяли трубку
    callbacks: list[CallResult]  # кому перезвонить

    @property
    def completed(self) -> int:
        return self.funnel[-1][1]

    @property
    def cost_per_call(self) -> float | None:
        return self.total_cost / len(self.calls) if self.calls else None

    @property
    def cost_per_completed(self) -> float | None:
        """Главная цифра юнит-экономики: во сколько обходится одна полная анкета,
        включая звонки, где не дозвонились или не договорили."""
        return self.total_cost / self.completed if self.completed else None

    @property
    def cost_per_minute(self) -> float | None:
        return self.total_cost / self.total_minutes if self.total_minutes else None


def load_results(results_dir: Path, scenario_name: str) -> list[CallResult]:
    """Все сохранённые звонки сценария, от старых к новым."""
    results = []
    for path in (results_dir / "calls").glob("*.json"):
        data = json.loads(path.read_text(encoding="utf-8"))
        if data.get("scenario") == scenario_name:
            results.append(CallResult.from_dict(data))
    return sorted(results, key=lambda r: r.started_at or r.ended_at or "")


def build_report(scenario: Scenario, calls: list[CallResult]) -> Report:
    reached = [c for c in calls if is_reached(c)]
    talked = [c for c in reached if is_conversation(c)]
    completed = [c for c in talked if c.answers.get("outcome") == "completed"]

    durations = [c.duration_seconds for c in reached if c.duration_seconds is not None]
    return Report(
        scenario=scenario.name,
        calls=calls,
        funnel=[
            ("набрали номер", len(calls)),
            ("взяли трубку", len(reached)),
            ("поговорили с человеком", len(talked)),
            ("собрали все ответы", len(completed)),
        ],
        outcomes=Counter(c.answers.get("outcome") for c in calls if is_reached(c)),
        ended_reasons=Counter(c.ended_reason for c in calls),
        questions=[_question_stats(q, talked) for q in scenario.questions],
        total_cost=sum(c.cost_usd or 0 for c in calls),
        total_minutes=sum(durations) / 60,
        avg_duration_seconds=statistics.mean(durations) if durations else None,
        callbacks=[c for c in calls if c.answers.get("outcome") == "callback_requested"],
    )


def is_reached(call: CallResult) -> bool:
    reason = call.ended_reason or ""
    return reason not in NOT_REACHED and "failed-to-connect" not in reason and not reason.startswith("call.start.error")


def is_conversation(call: CallResult) -> bool:
    """Взяли трубку и говорил человек, а не автоответчик или голосовое меню."""
    return (
        is_reached(call)
        and call.ended_reason != "voicemail"
        and call.answers.get("outcome") not in (None, "no_human")
    )


def _question_stats(q: Question, talked: list[CallResult]) -> QuestionStats:
    stats = QuestionStats(question=q, answered=0, conversations=len(talked))
    for call in talked:
        value = call.answers.get(q.id)
        if value is None or value == "":
            continue
        stats.answered += 1
        if q.type == "number":
            number = _as_number(value)
            if number is not None:
                stats.numbers.append(number)
        elif q.type == "boolean":
            stats.counts["да" if _as_bool(value) else "нет"] += 1
        elif q.type == "enum":
            stats.counts[str(value)] += 1
        else:
            stats.examples.append(str(value))
    stats.examples = stats.examples[-3:]
    return stats


def _as_number(value) -> float | None:
    """LLM обычно отдаёт число, но иногда строку вроде «27 000»."""
    if isinstance(value, bool):
        return None
    if isinstance(value, (int, float)):
        return float(value)
    try:
        return float(str(value).replace(" ", "").replace(" ", "").replace(",", "."))
    except ValueError:
        return None


def _as_bool(value) -> bool:
    if isinstance(value, str):
        return value.strip().lower() in ("true", "да", "yes")
    return bool(value)
