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
SCENARIO = ROOT / "scenarios" / "sto_service.yaml"
CALL = json.loads((ROOT / "tests" / "fixtures" / "ended_call.json").read_text(encoding="utf-8"))


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
    assert r.answers["price_total"] == 27000
    assert r.answers["outcome"] == "completed"
    assert list(r.answers)[0] == "does_service"  # порядок как в сценарии
    assert r.missing_required == []
    assert "Абая" in r.transcript


def test_missing_answers_are_none_and_reported(scenario):
    call = json.loads(json.dumps(CALL))
    result = next(iter(call["artifact"]["structuredOutputs"].values()))["result"]
    del result["nearest_slot"]
    r = parse_call(call, scenario)
    assert r.answers["nearest_slot"] is None
    assert r.missing_required == ["nearest_slot"]


def test_call_without_outputs_still_parses(scenario):
    call = {**CALL, "artifact": {"transcript": "AI: Алло?"}}
    r = parse_call(call, scenario)
    assert all(r.answers[q.id] is None for q in scenario.questions)


def test_sinks_write_json_and_csv(scenario, results_in_tmp):
    sinks.publish(parse_call(CALL, scenario))
    saved = json.loads((results_in_tmp / "calls" / f"{CALL['id']}.json").read_text(encoding="utf-8"))
    assert saved["answers"]["nearest_slot"] == "завтра в 11:00"
    with (results_in_tmp / "sto_service.csv").open(encoding="utf-8-sig") as f:
        rows = list(csv.DictReader(f))
    assert rows[0]["price_total"] == "27000"


def test_csv_gets_new_column_when_question_added(scenario, results_in_tmp):
    sinks.publish(parse_call(CALL, scenario))
    r = parse_call(CALL, scenario)
    r.call_id = "second"
    r.answers["has_waiting_room"] = True  # как будто в сценарий добавили вопрос
    sinks.publish(r)
    with (results_in_tmp / "sto_service.csv").open(encoding="utf-8-sig") as f:
        rows = list(csv.DictReader(f))
    assert len(rows) == 2
    assert rows[0]["has_waiting_room"] == ""
    assert rows[1]["has_waiting_room"] == "True"


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
            return [{"id": "a1", "name": "other"}, {"id": "a2", "name": "sto_service"}]
        return {"id": "a2" if method == "PATCH" else "new"}

    client._request = fake_request
    assert client.save_assistant({"name": "sto_service"}) == ({"id": "a2"}, False)
    assert sent[-1] == ("PATCH", "/assistant/a2")  # такой уже есть — обновляем, а не плодим копии
    assert client.save_assistant({"name": "car_service_en"}) == ({"id": "new"}, True)
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
    config = (tmp_path / "docs" / "config.js").read_text(encoding="utf-8")
    data = json.loads(config.split("window.VOICEBOT = ", 1)[1].rstrip().rstrip(";"))
    assert data["publicKey"] == "pk-test"
    assert {s["language"]: s["assistantId"] for s in data["scenarios"]} == {
        "en": "id-car_service_en",
        "ru": "id-sto_service",
    }
    for s in data["scenarios"]:
        assert (tmp_path / "docs" / s["analytics"]).exists()


def test_dry_run_prints_payload_without_calling(capsys):
    code = main(["call", "87011234567", "--dry-run", "--scenario", str(SCENARIO)])
    payload = json.loads(capsys.readouterr().out)
    assert code == 0
    assert payload["customer"]["number"] == "+77011234567"
    assert payload["assistant"]["firstMessage"].startswith("Здравствуйте")
