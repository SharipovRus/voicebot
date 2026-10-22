"""Проверяем путь «YAML → промпт / схема / настройки ассистента» без звонков."""

from pathlib import Path

import pytest

from voicebot.assistant import OUTPUT_NAME, build_assistant
from voicebot.prompt import build_system_prompt
from voicebot.scenario import ScenarioError, load_scenario
from voicebot.schema import build_output_schema, standard_fields

ROOT = Path(__file__).resolve().parents[1]
SCENARIO = ROOT / "scenarios" / "sto_service.yaml"
SCENARIO_EN = ROOT / "scenarios" / "car_service_en.yaml"


@pytest.fixture
def scenario():
    return load_scenario(SCENARIO)


def write_yaml(tmp_path, text: str) -> Path:
    path = tmp_path / "s.yaml"
    path.write_text(text, encoding="utf-8")
    return path


MINIMAL = """
name: t
persona: Ты бот. {extra}
first_message: Привет
end_message: Пока
questions:
  - id: q1
    ask: Вопрос?
    type: {qtype}
vapi:
  model: {{provider: openai, model: gpt-4.1-mini}}
  voice: {{provider: azure, voiceId: ru-RU-SvetlanaNeural}}
  transcriber: {{provider: deepgram, model: nova-2, language: ru}}
"""


def test_variables_are_substituted(scenario):
    assert "{{" not in scenario.persona + scenario.first_message
    assert "Toyota Camry" in scenario.persona


def test_cli_variable_overrides_file():
    s = load_scenario(SCENARIO, {"car": "Kia Rio 2020"})
    assert "Kia Rio 2020" in s.persona
    assert "Toyota" not in s.persona


def test_unknown_variable_is_an_error(tmp_path):
    path = write_yaml(tmp_path, MINIMAL.format(extra="{{missing}}", qtype="string"))
    with pytest.raises(ScenarioError, match="missing"):
        load_scenario(path)


def test_bad_question_type_is_an_error(tmp_path):
    path = write_yaml(tmp_path, MINIMAL.format(extra="", qtype="date"))
    with pytest.raises(ScenarioError, match="date"):
        load_scenario(path)


def test_prompt_contains_every_question_and_rule(scenario):
    prompt = build_system_prompt(scenario)
    for q in scenario.questions:
        assert q.ask in prompt
    for rule in scenario.rules:
        assert rule in prompt
    assert "[обязательный]" in prompt
    assert "Задавай, только если" in prompt
    assert "endCall" in prompt


def test_schema_has_question_and_standard_fields(scenario):
    schema = build_output_schema(scenario)
    props = schema["properties"]
    assert [q.id for q in scenario.questions] == list(props)[: len(scenario.questions)]
    assert set(standard_fields("ru")) <= set(props)
    assert props["price_total"]["type"] == "number"
    assert props["does_service"]["type"] == "boolean"


def test_enum_question_becomes_enum_field(tmp_path):
    text = MINIMAL.format(extra="", qtype="enum").replace(
        "type: enum", "type: enum\n    options: [да, нет, не знаю]"
    )
    s = load_scenario(write_yaml(tmp_path, text))
    assert build_output_schema(s)["properties"]["q1"]["enum"] == ["да", "нет", "не знаю"]


def test_english_scenario_gets_english_scaffolding():
    s = load_scenario(SCENARIO_EN)
    prompt = build_system_prompt(s)
    assert "[required]" in prompt and "Ask only if" in prompt
    assert "Вопросы" not in prompt  # ни одной русской служебной фразы
    schema = build_output_schema(s)
    assert "in English" in schema["properties"]["summary"]["description"]
    # те же вопросы, что в русском сценарии: аналитика и CSV устроены одинаково
    assert list(schema["properties"]) == list(build_output_schema(load_scenario(SCENARIO))["properties"])


def test_unknown_language_is_an_error(tmp_path):
    text = MINIMAL.format(extra="", qtype="string").replace("name: t", "name: t\nlanguage: de")
    with pytest.raises(ScenarioError, match="de"):
        load_scenario(write_yaml(tmp_path, text))


def test_assistant_payload(scenario):
    a = build_assistant(scenario)
    assert a["firstMessage"] == scenario.first_message
    assert a["model"]["messages"][0]["role"] == "system"
    assert {t["type"] for t in a["model"]["tools"]} == {"endCall", "dtmf"}
    assert a["artifactPlan"]["structuredOutputs"][0]["name"] == OUTPUT_NAME
    # overrides из YAML попадают в ассистента как есть
    assert a["backgroundSound"] == "off"
