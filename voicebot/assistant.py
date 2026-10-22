"""Сборка настроек голосового ассистента Vapi из сценария.

Ассистент создаётся «на лету» для каждого звонка (transient assistant): все
настройки уходят в запросе на звонок, в дашборде Vapi ничего не хранится.
Поэтому сценарий в git — это полное описание поведения бота.
"""

from .prompt import build_system_prompt
from .scenario import Scenario
from .schema import build_output_schema

# Имя structured output: по нему ищем ответы в результатах звонка.
OUTPUT_NAME = "call_answers"


def build_assistant(scenario: Scenario) -> dict:
    vapi = scenario.vapi

    model = dict(vapi["model"])
    model["messages"] = [{"role": "system", "content": build_system_prompt(scenario)}]
    # Инструменты, которые LLM может вызвать во время разговора:
    # endCall — положить трубку, dtmf — нажать кнопки в голосовом меню.
    model["tools"] = [{"type": "endCall"}, {"type": "dtmf"}]

    assistant = {
        "name": scenario.name[:40],
        "firstMessage": scenario.first_message,
        "firstMessageMode": "assistant-speaks-first",
        "endCallMessage": scenario.end_message,
        "model": model,
        "voice": vapi["voice"],
        "transcriber": vapi["transcriber"],
        "maxDurationSeconds": vapi.get("max_duration_seconds", 300),
        "silenceTimeoutSeconds": vapi.get("silence_timeout_seconds", 30),
        "artifactPlan": {
            "recordingEnabled": True,
            # После звонка Vapi извлечёт из транскрипта ответы по нашей схеме.
            "structuredOutputs": [
                {
                    "name": OUTPUT_NAME,
                    "type": "ai",
                    "description": "Ответы на вопросы сценария из телефонного разговора",
                    "schema": build_output_schema(scenario),
                }
            ],
        },
    }
    return _deep_merge(assistant, vapi.get("overrides") or {})


def _deep_merge(base: dict, extra: dict) -> dict:
    """Накладывает extra поверх base, вложенные словари сливаются."""
    for key, value in extra.items():
        if isinstance(value, dict) and isinstance(base.get(key), dict):
            _deep_merge(base[key], value)
        else:
            base[key] = value
    return base
