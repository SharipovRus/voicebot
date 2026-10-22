"""Проверяем путь «завершённый звонок Vapi → результат → файлы» на записанном примере."""

import csv
import json
from pathlib import Path

import pytest

from voicebot import sinks
from voicebot.cli import main, normalize_phone
from voicebot.result import parse_call
from voicebot.scenario import load_scenario
from voicebot.vapi import VapiClient

ROOT = Path(__file__).resolve().parents[1]
SCENARIO = ROOT / "scenarios" / "abandoned_application.yaml"
CALL = json.loads((ROOT / "tests" / "fixtures" / "ended_call.json").read_text(encoding="utf-8"))
CSV_NAME = "abandoned_application.csv"


@pytest.fixture
def scenario():
    return load_scenario(SCENARIO)


@pytest.fixture(autouse=True)
def results_in_tmp(tmp_path, monkeypatch):
    monkeypatch.setattr(sinks, "RESULTS_DIR", tmp_path)
    return tmp_path


def test_parse_call(scenario):
    r = parse_call(CALL, scenario)
    assert r.phone == "+77011234567"
    assert r.answers["drop_reason"] == "техническая ошибка"
    assert r.answers["link_consent"] is True
    assert r.answers["outcome"] == "completed"
    assert list(r.answers)[0] == "drop_reason"  # порядок как в сценарии
    assert r.answers["specialist_time"] is None  # вопрос с условием, его не задавали
    assert r.missing_required == []
    assert "паспорта" in r.transcript


def test_missing_answers_are_none_and_reported(scenario):
    call = json.loads(json.dumps(CALL))
    result = next(iter(call["artifact"]["structuredOutputs"].values()))["result"]
    del result["link_consent"]
    r = parse_call(call, scenario)
    assert r.answers["link_consent"] is None
    assert r.missing_required == ["link_consent"]


def test_call_without_outputs_still_parses(scenario):
    call = {**CALL, "artifact": {"transcript": "AI: Алло?"}}
    r = parse_call(call, scenario)
    assert all(r.answers[q.id] is None for q in scenario.questions)


def test_sinks_write_json_and_csv(scenario, results_in_tmp):
    sinks.publish(parse_call(CALL, scenario))
    saved = json.loads((results_in_tmp / "calls" / f"{CALL['id']}.json").read_text(encoding="utf-8"))
    assert saved["answers"]["still_interested"] is True
    with (results_in_tmp / CSV_NAME).open(encoding="utf-8-sig") as f:
        rows = list(csv.DictReader(f))
    assert rows[0]["drop_reason"] == "техническая ошибка"


def test_csv_gets_new_column_when_question_added(scenario, results_in_tmp):
    sinks.publish(parse_call(CALL, scenario))
    r = parse_call(CALL, scenario)
    r.call_id = "second"
    r.answers["app_platform"] = "android"  # как будто в сценарий добавили вопрос
    sinks.publish(r)
    with (results_in_tmp / CSV_NAME).open(encoding="utf-8-sig") as f:
        rows = list(csv.DictReader(f))
    assert len(rows) == 2
    assert rows[0]["app_platform"] == ""
    assert rows[1]["app_platform"] == "android"


def test_fetching_same_call_twice_keeps_one_csv_row(scenario, results_in_tmp):
    sinks.publish(parse_call(CALL, scenario))
    sinks.publish(parse_call(CALL, scenario))
    with (results_in_tmp / CSV_NAME).open(encoding="utf-8-sig") as f:
        assert len(list(csv.DictReader(f))) == 1


class FakeFetchClient:
    """Vapi с одним разговором в браузере, ответы появляются со второго запроса."""

    def __init__(self, calls_by_assistant):
        self.calls_by_assistant = calls_by_assistant
        self.waited = False

    def find_assistant(self, name):
        return {"id": f"id-{name}"}

    def last_call(self, assistant_id):
        return self.calls_by_assistant.get(assistant_id)

    def get_call(self, call_id):
        return {**CALL, "artifact": {"transcript": "..."}}  # ответы ещё не извлечены

    def wait_for_result(self, call_id, **kwargs):
        self.waited = True
        return CALL


def test_fetch_without_id_takes_last_call_and_waits_for_answers(monkeypatch, results_in_tmp, capsys):
    from voicebot import cli

    fake = FakeFetchClient({"id-abandoned_application": {"id": CALL["id"]}})
    monkeypatch.setattr(cli, "_client", lambda: fake)
    monkeypatch.setattr(cli, "RESULTS_DIR", results_in_tmp)
    assert main(["fetch", "--scenario", str(SCENARIO)]) == 0
    assert fake.waited
    assert (results_in_tmp / "calls" / f"{CALL['id']}.json").exists()
    assert "техническая ошибка" in capsys.readouterr().out


def test_fetch_without_calls_explains_what_to_do(monkeypatch, capsys):
    from voicebot import cli

    monkeypatch.setattr(cli, "_client", lambda: FakeFetchClient({}))
    assert main(["fetch", "--scenario", str(SCENARIO)]) == 1
    assert "демо-странице" in capsys.readouterr().out


def fake_client(responses):
    client = VapiClient("test-key")
    calls = iter(responses)
    client.get_call = lambda call_id: next(calls)
    return client


def test_wait_returns_when_answers_are_ready():
    ended_no_outputs = {**CALL, "artifact": {"transcript": "..."}}
    client = fake_client([{"status": "queued"}, {"status": "in-progress"}, ended_no_outputs, CALL])
    seen = []
    call = client.wait_for_result("id", poll_seconds=0, on_status=seen.append)
    assert call is CALL
    assert seen == ["queued", "in-progress", "ended"]


def test_wait_does_not_wait_for_answers_if_nobody_picked_up():
    no_answer = {"status": "ended", "endedReason": "customer-did-not-answer"}
    client = fake_client([{"status": "ringing"}, no_answer])
    assert client.wait_for_result("id", poll_seconds=0) is no_answer


@pytest.mark.parametrize(
    "raw",
    ["+77011234567", "87011234567", "8 (701) 123-45-67", "7011234567", "+7 701 123 45 67"],
)
def test_normalize_phone(raw):
    assert normalize_phone(raw) == "+77011234567"


def test_normalize_phone_rejects_garbage():
    with pytest.raises(ValueError):
        normalize_phone("123")


def test_save_assistant_finds_existing_by_name():
    client = VapiClient("test-key")
    sent = []

    def fake_request(method, path, **kwargs):
        sent.append((method, path))
        if method == "GET":
            return [{"id": "a1", "name": "other"}, {"id": "a2", "name": "abandoned_application"}]
        return {"id": "a2" if method == "PATCH" else "new"}

    client._request = fake_request
    assert client.save_assistant({"name": "abandoned_application"}) == ({"id": "a2"}, False)
    assert sent[-1] == ("PATCH", "/assistant/a2")  # такой уже есть — обновляем, а не плодим копии
    assert client.save_assistant({"name": "abandoned_application_en"}) == ({"id": "new"}, True)
    assert sent[-1] == ("POST", "/assistant")


class FakeAssistantClient:
    def save_assistant(self, assistant):
        return {"id": f"id-{assistant['name']}"}, False


def test_site_builds_config_and_analytics_for_every_scenario(tmp_path, monkeypatch, capsys):
    from voicebot import cli

    monkeypatch.setattr(cli, "_client", lambda: FakeAssistantClient())
    monkeypatch.setattr(cli, "load_dotenv", lambda: None)  # не читать настоящий .env
    monkeypatch.setattr(cli, "SCENARIOS_DIR", ROOT / "scenarios")
    monkeypatch.setattr(cli, "SITE_DIR", tmp_path / "docs")
    monkeypatch.setenv("VAPI_PUBLIC_KEY", "pk-test")

    assert main(["site"]) == 0
    data = json.loads((tmp_path / "docs" / "config.json").read_text(encoding="utf-8"))
    assert data["publicKey"] == "pk-test"
    assert {s["language"]: s["assistantId"] for s in data["scenarios"]} == {
        "en": "id-abandoned_application_en",
        "ru": "id-abandoned_application",
    }
    assert all(s["demoHint"] for s in data["scenarios"])  # подсказка для демо берётся из YAML
    for s in data["scenarios"]:
        assert (tmp_path / "docs" / s["analytics"]).exists()


def test_dry_run_prints_payload_without_calling(capsys):
    code = main(["call", "87011234567", "--dry-run", "--scenario", str(SCENARIO)])
    payload = json.loads(capsys.readouterr().out)
    assert code == 0
    assert payload["customer"]["number"] == "+77011234567"
    assert payload["assistant"]["firstMessage"].startswith("Здравствуйте")
