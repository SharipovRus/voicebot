"""Проверяем путь «сохранённые звонки → сводная аналитика → HTML-страница»."""

import json
from pathlib import Path

import pytest

from voicebot import sinks
from voicebot.analytics import _question_stats, build_report, load_results
from voicebot.cli import main, normalize_phone
from voicebot.report import build_html, mask_phone
from voicebot.result import CallResult
from voicebot.scenario import Question, load_scenario

ROOT = Path(__file__).resolve().parents[1]
SCENARIO = ROOT / "scenarios" / "abandoned_application.yaml"


@pytest.fixture
def scenario():
    return load_scenario(SCENARIO)


def make_call(call_id, ended_reason="assistant-ended-call", seconds=120, cost=0.5, **answers) -> CallResult:
    return CallResult(
        call_id=call_id,
        scenario="abandoned_application",
        phone="+77011234567",
        status="ended",
        ended_reason=ended_reason,
        started_at="2026-10-20T10:00:00Z",
        ended_at=f"2026-10-20T10:{seconds // 60:02d}:{seconds % 60:02d}Z",
        cost_usd=cost,
        answers=answers,
        missing_required=[],
        transcript="AI: Здравствуйте!",
        recording_url="https://storage.vapi.ai/secret-recording.wav",
    )


@pytest.fixture
def calls():
    return [
        make_call("1", outcome="completed", drop_reason="техническая ошибка", drop_reason_details="не грузилось фото",
                  still_interested=True, link_consent=True),
        make_call("2", outcome="completed", drop_reason="отвлёкся и забыл", still_interested=True, link_consent=True),
        make_call("3", outcome="partial", drop_reason="сложно или долго", drop_reason_details="слишком много шагов"),
        make_call("4", outcome="not_relevant", drop_reason="выбрал другой банк", still_interested=False),
        make_call("5", outcome="callback_requested", callback_time="после 18:00"),
        make_call("6", ended_reason="voicemail", seconds=20, cost=0.1, outcome="no_human"),
        make_call("7", ended_reason="customer-did-not-answer", seconds=0, cost=0.02),
        make_call("8", ended_reason="customer-busy", seconds=0, cost=0.02),
    ]


def test_funnel(scenario, calls):
    r = build_report(scenario, calls)
    assert r.funnel == [
        ("набрали номер", 8),
        ("взяли трубку", 6),  # не взяли и занято — не дозвонились
        ("поговорили с человеком", 5),  # автоответчик — не разговор
        ("собрали все ответы", 2),
    ]
    assert r.outcomes["completed"] == 2
    assert r.ended_reasons["customer-busy"] == 1
    assert [c.call_id for c in r.callbacks] == ["5"]


def test_money_counts_every_call_including_failed(scenario, calls):
    r = build_report(scenario, calls)
    assert r.total_cost == pytest.approx(5 * 0.5 + 0.1 + 0.02 + 0.02)
    # одна полная анкета обходится во все траты, делённые на число полных анкет
    assert r.cost_per_completed == pytest.approx(r.total_cost / 2)
    assert r.avg_duration_seconds == pytest.approx((5 * 120 + 20) / 6)


def test_question_stats(scenario, calls):
    stats = {s.question.id: s for s in build_report(scenario, calls).questions}
    reason = stats["drop_reason"]
    assert (reason.answered, reason.conversations) == (4, 5)
    assert reason.counts["техническая ошибка"] == 1
    assert stats["still_interested"].counts == {"да": 2, "нет": 1}
    assert stats["link_consent"].counts == {"да": 2}
    assert stats["drop_reason_details"].examples == ["не грузилось фото", "слишком много шагов"]


def test_number_answers_accept_strings():
    amount = Question(id="amount", ask="Сколько?", type="number")
    talked = [make_call("1", amount=27000), make_call("2", amount="31 000"), make_call("3", amount="не помню")]
    stats = _question_stats(amount, talked)
    assert stats.answered == 3
    assert stats.numbers == [27000, 31000]  # строка «31 000» тоже стала числом, «не помню» — нет


def test_report_without_calls(scenario):
    r = build_report(scenario, [])
    assert r.cost_per_completed is None
    assert "пока нет" in build_html(r)


def test_load_results_filters_by_scenario_and_tolerates_new_fields(tmp_path, scenario):
    folder = tmp_path / "calls"
    folder.mkdir()
    ours = make_call("ours", outcome="completed").to_dict()
    ours["field_from_the_future"] = 1
    other = {**make_call("other").to_dict(), "scenario": "clinic"}
    for data in (ours, other):
        (folder / f"{data['call_id']}.json").write_text(json.dumps(data, ensure_ascii=False), encoding="utf-8")
    assert [c.call_id for c in load_results(tmp_path, scenario.name)] == ["ours"]


def test_mask_phone():
    assert mask_phone("+77011234567") == "+7701•••••67"
    assert mask_phone("+4915123456789") == "+4915•••••••89"


def test_html_hides_private_data_and_escapes_text(scenario, calls):
    calls[0].answers["summary"] = "<script>alert(1)</script>"
    html = build_html(build_report(scenario, calls))
    assert "+77011234567" not in html
    assert "secret-recording" not in html
    assert "<script>alert(1)" not in html
    assert "&lt;script&gt;" in html


def test_report_command_writes_page(tmp_path, monkeypatch, capsys, calls):
    monkeypatch.setattr(sinks, "RESULTS_DIR", tmp_path)
    monkeypatch.setattr("voicebot.cli.RESULTS_DIR", tmp_path)
    for call in calls:
        sinks.save_json(call)
    out = tmp_path / "page.html"
    assert main(["report", "--scenario", str(SCENARIO), "--out", str(out)]) == 0
    printed = capsys.readouterr().out
    assert "собрали все ответы 2 (25%)" in printed
    assert "без ответа чаще всего: still_interested" in printed  # 3 из 5, вопрос без условия
    assert "drop_reason_details" not in printed  # вопрос с условием — пропуск не считается проблемой
    assert "Воронка" in out.read_text(encoding="utf-8")


def test_international_numbers():
    assert normalize_phone("+49 151 2345 6789") == "+4915123456789"
    with pytest.raises(ValueError, match="кодом"):
        normalize_phone("0151 2345 6789")  # немецкий номер без кода страны
