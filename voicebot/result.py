"""Разбор завершённого звонка Vapi в наш формат результата."""

from dataclasses import asdict, dataclass, field, fields
from datetime import datetime

from .assistant import OUTPUT_NAME
from .scenario import Scenario


@dataclass
class CallResult:
    call_id: str
    scenario: str
    phone: str
    status: str
    ended_reason: str | None  # почему закончился: customer-ended-call, customer-did-not-answer, ...
    started_at: str | None
    ended_at: str | None
    cost_usd: float | None
    answers: dict  # ответы на вопросы сценария + служебные поля (outcome, summary, ...)
    missing_required: list[str]  # обязательные вопросы, на которые нет ответа
    transcript: str
    recording_url: str | None
    variables: dict = field(default_factory=dict)

    def to_dict(self) -> dict:
        return asdict(self)

    @classmethod
    def from_dict(cls, data: dict) -> "CallResult":
        """Обратно из сохранённого JSON. Незнакомые поля пропускаем, чтобы старые
        и новые файлы читались одинаково."""
        known = {f.name for f in fields(cls)}
        return cls(**{k: v for k, v in data.items() if k in known})

    @property
    def duration_seconds(self) -> int | None:
        if not (self.started_at and self.ended_at):
            return None
        return int((_parse_time(self.ended_at) - _parse_time(self.started_at)).total_seconds())


def parse_call(call: dict, scenario: Scenario) -> CallResult:
    artifact = call.get("artifact") or {}
    extracted = _find_output(artifact.get("structuredOutputs") or {}, OUTPUT_NAME)

    # Порядок полей = порядок вопросов, потом служебные. Нет ответа → None.
    answers = {q.id: extracted.get(q.id) for q in scenario.questions}
    answers.update({k: v for k, v in extracted.items() if k not in answers})

    return CallResult(
        call_id=call.get("id", ""),
        scenario=scenario.name,
        phone=(call.get("customer") or {}).get("number", ""),
        status=call.get("status", ""),
        ended_reason=call.get("endedReason"),
        started_at=call.get("startedAt"),
        ended_at=call.get("endedAt"),
        cost_usd=call.get("cost"),
        answers=answers,
        missing_required=[q.id for q in scenario.questions if q.required and answers.get(q.id) is None],
        transcript=artifact.get("transcript") or call.get("transcript") or "",
        recording_url=artifact.get("recordingUrl") or call.get("recordingUrl"),
        variables=scenario.variables,
    )


def _parse_time(value: str) -> datetime:
    return datetime.fromisoformat(value.replace("Z", "+00:00"))


def _find_output(outputs: dict, name: str) -> dict:
    """structuredOutputs приходят как {id: {name, result}} — ищем наш по имени."""
    for output in outputs.values():
        if output.get("name") == name and isinstance(output.get("result"), dict):
            return output["result"]
    return {}
