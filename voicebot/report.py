"""HTML-страница с аналитикой звонков.

Один самодостаточный файл без внешних библиотек: его можно открыть локально
или выложить на GitHub Pages. Номера телефонов маскируются, записи и
транскрипты на страницу не попадают — они остаются только в results/calls.
"""

import statistics
from datetime import datetime, timezone
from html import escape

from .analytics import ENDED_REASON_LABELS, OUTCOME_LABELS, QuestionStats, Report
from .result import CallResult


def build_html(report: Report) -> str:
    generated = datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M UTC")
    if not report.calls:
        body = '<p class="empty">Звонков по этому сценарию пока нет.</p>'
    else:
        body = "\n".join(
            [
                _tiles(report),
                _section("Воронка", _bars(report.funnel, total=len(report.calls))),
                '<div class="two-col">'
                + _section("Чем закончились разговоры", _bars(_labeled(report.outcomes, OUTCOME_LABELS)))
                + _section("Почему закончился звонок", _bars(_labeled(report.ended_reasons, ENDED_REASON_LABELS)))
                + "</div>",
                _section("Ответы по вопросам", "".join(_question(q) for q in report.questions)),
                _callbacks(report.callbacks),
                _section("Все звонки", _calls_table(report.calls)),
            ]
        )
    return _PAGE.format(
        scenario=escape(report.scenario),
        generated=generated,
        count=len(report.calls),
        body=body,
    )


def mask_phone(phone: str) -> str:
    """+77011234567 → +7701•••••67: видно страну и оператора, но не сам номер."""
    if len(phone) < 8:
        return "•" * len(phone)
    return phone[:5] + "•" * (len(phone) - 7) + phone[-2:]


def _tiles(r: Report) -> str:
    n = len(r.calls)
    reached = r.funnel[1][1]
    tiles = [
        ("Звонков", str(n), ""),
        ("Взяли трубку", _pct(reached, n), f"{reached} из {n}"),
        ("Собрали все ответы", _pct(r.completed, n), f"{r.completed} из {n}"),
        ("Цена успешного звонка", _money(r.cost_per_completed), "все траты ÷ полные анкеты"),
        ("Средняя длительность", _duration(r.avg_duration_seconds), "где взяли трубку"),
    ]
    cells = "".join(
        f'<div class="tile"><div class="tile-label">{escape(label)}</div>'
        f'<div class="tile-value">{escape(value)}</div>'
        f'<div class="tile-note">{escape(note)}</div></div>'
        for label, value, note in tiles
    )
    spend = (
        f"Всего потрачено {_money(r.total_cost)} · {_money(r.cost_per_call)} за звонок · "
        f"{_money(r.cost_per_minute)} за минуту разговора"
    )
    return f'<div class="tiles">{cells}</div><p class="spend">{escape(spend)}</p>'


def _section(title: str, content: str) -> str:
    return f"<section><h2>{escape(title)}</h2>{content}</section>"


def _labeled(counter, labels: dict) -> list[tuple[str, int]]:
    return [(labels.get(key, key or "нет данных"), count) for key, count in counter.most_common()]


def _bars(rows: list[tuple[str, int]], total: int | None = None) -> str:
    """Горизонтальные столбики. total задан — подпись с долей от него (для воронки)."""
    if not rows:
        return '<p class="muted">Нет данных</p>'
    top = total or max(count for _, count in rows) or 1
    html = []
    for label, count in rows:
        value = f"{count} · {_pct(count, total)}" if total else str(count)
        html.append(
            f'<div class="bar-row" data-tip="{escape(label)}: {escape(value)}">'
            f'<span class="bar-label">{escape(label)}</span>'
            f'<span class="bar-track"><span class="bar" style="width:{100 * count / top:.1f}%"></span></span>'
            f'<span class="bar-value">{escape(value)}</span></div>'
        )
    return "".join(html)


def _question(s: QuestionStats) -> str:
    q = s.question
    badges = '<span class="badge">обязательный</span>' if q.required else ""
    condition = f'<div class="muted small">Задаётся, если: {escape(q.ask_if)}</div>' if q.ask_if else ""
    rate = s.fill_rate
    meter = (
        f'<div class="meter-row" data-tip="Ответ есть в {s.answered} из {s.conversations} разговоров">'
        f'<span class="meter"><span style="width:{100 * (rate or 0):.1f}%"></span></span>'
        f'<span class="small">ответ в {s.answered} из {s.conversations} разговоров</span></div>'
    )
    return (
        f'<div class="question"><div class="q-head"><span>{escape(q.ask)}</span>'
        f"<code>{escape(q.id)}</code>{badges}</div>{condition}{meter}{_answers(s)}</div>"
    )


def _answers(s: QuestionStats) -> str:
    q = s.question
    if q.type == "number" and s.numbers:
        parts = [
            ("мин", min(s.numbers)),
            ("медиана", statistics.median(s.numbers)),
            ("макс", max(s.numbers)),
        ]
        return '<div class="answers">' + " · ".join(f"{k} <b>{_num(v)}</b>" for k, v in parts) + "</div>"
    if q.type == "boolean" and s.counts:
        return _split([("да", s.counts["да"]), ("нет", s.counts["нет"])])
    if q.type == "enum" and s.counts:
        ordered = [(o, s.counts[o]) for o in q.options if s.counts[o]]
        ordered += [(k, v) for k, v in s.counts.most_common() if k not in q.options]
        return _bars(ordered)
    if s.examples:
        items = "".join(f"<li>{escape(e)}</li>" for e in reversed(s.examples))
        return f'<ul class="examples">{items}</ul>'
    return ""


def _split(parts: list[tuple[str, int]]) -> str:
    """Доли «да / нет» одной полосой, с легендой: цвет не единственный способ различить."""
    total = sum(count for _, count in parts) or 1
    segments = "".join(
        f'<span class="seg seg-{i}" style="flex:{count}" data-tip="{escape(label)}: {count} ({_pct(count, total)})"></span>'
        for i, (label, count) in enumerate(parts, 1)
        if count
    )
    legend = "".join(
        f'<span class="key"><span class="swatch seg-{i}"></span>{escape(label)} <b>{count}</b></span>'
        for i, (label, count) in enumerate(parts, 1)
    )
    return f'<div class="split">{segments}</div><div class="legend">{legend}</div>'


def _callbacks(calls: list[CallResult]) -> str:
    if not calls:
        return ""
    rows = "".join(
        f"<tr><td>{escape(mask_phone(c.phone))}</td><td>{escape(str(c.answers.get('callback_time') or '—'))}</td>"
        f"<td>{escape(str(c.answers.get('summary') or ''))}</td></tr>"
        for c in calls
    )
    return _section(
        "Кому перезвонить",
        f"<table><thead><tr><th>Номер</th><th>Когда</th><th>Резюме</th></tr></thead><tbody>{rows}</tbody></table>",
    )


def _calls_table(calls: list[CallResult]) -> str:
    rows = []
    for c in sorted(calls, key=lambda c: c.started_at or "", reverse=True):
        outcome = c.answers.get("outcome")
        # Нет итога разговора (не взяли трубку и т.п.) — показываем, почему закончился звонок.
        label = OUTCOME_LABELS.get(outcome, outcome) if outcome else ENDED_REASON_LABELS.get(c.ended_reason, c.ended_reason)
        rows.append(
            f"<tr><td class='num'>{escape(_time(c.started_at))}</td>"
            f"<td class='num'>{escape(mask_phone(c.phone))}</td>"
            f"<td>{escape(str(label or '—'))}</td>"
            f"<td class='num'>{escape(_duration(c.duration_seconds))}</td>"
            f"<td class='num'>{escape(_money(c.cost_usd))}</td>"
            f"<td>{escape(str(c.answers.get('summary') or ''))}</td></tr>"
        )
    return (
        '<div class="table-wrap"><table><thead><tr><th>Когда (UTC)</th><th>Номер</th><th>Итог</th>'
        "<th>Длит.</th><th>Цена</th><th>Резюме</th></tr></thead><tbody>"
        + "".join(rows)
        + "</tbody></table></div>"
    )


def _pct(part: int, total: int | None) -> str:
    return f"{round(100 * part / total)}%" if total else "—"


def _money(value: float | None) -> str:
    return f"${value:.2f}" if value is not None else "—"


def _num(value: float) -> str:
    text = f"{value:,.0f}" if value == int(value) else f"{value:,.1f}"
    return text.replace(",", " ")


def _duration(seconds: float | None) -> str:
    if seconds is None:
        return "—"
    seconds = int(round(seconds))
    return f"{seconds // 60}:{seconds % 60:02d}"


def _time(iso: str | None) -> str:
    if not iso:
        return "—"
    return iso.replace("T", " ")[:16]


_PAGE = """<!doctype html>
<html lang="ru">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>Аналитика звонков</title>
<style>
:root {{
  color-scheme: light;
  --page: #f9f9f7; --surface: #fcfcfb; --border: rgba(11,11,11,0.10);
  --text: #0b0b0b; --text-2: #52514e; --muted: #898781; --grid: #e1e0d9;
  --series-1: #2a78d6; --series-2: #eb6834; --track: #cde2fb;
}}
@media (prefers-color-scheme: dark) {{
  :root:not([data-theme="light"]) {{
    color-scheme: dark;
    --page: #0d0d0d; --surface: #1a1a19; --border: rgba(255,255,255,0.10);
    --text: #f0efec; --text-2: #c3c2b7; --muted: #898781; --grid: #2c2c2a;
    --series-1: #3987e5; --series-2: #d95926; --track: #184f95;
  }}
}}
:root[data-theme="dark"] {{
  color-scheme: dark;
  --page: #0d0d0d; --surface: #1a1a19; --border: rgba(255,255,255,0.10);
  --text: #f0efec; --text-2: #c3c2b7; --muted: #898781; --grid: #2c2c2a;
  --series-1: #3987e5; --series-2: #d95926; --track: #184f95;
}}
* {{ box-sizing: border-box; }}
body {{ margin: 0; background: var(--page); color: var(--text);
  font: 15px/1.5 system-ui, -apple-system, "Segoe UI", sans-serif; }}
main {{ max-width: 960px; margin: 0 auto; padding: 32px 16px 48px; }}
h1 {{ font-size: 24px; margin: 0 0 4px; }}
h2 {{ font-size: 16px; margin: 0 0 12px; }}
.sub, .muted {{ color: var(--muted); }}
.small {{ font-size: 13px; }}
section {{ background: var(--surface); border: 1px solid var(--border); border-radius: 12px;
  padding: 20px; margin-top: 16px; min-width: 0; }}
.two-col {{ display: grid; grid-template-columns: 1fr 1fr; gap: 16px; }}
.two-col section {{ margin-top: 16px; }}
.tiles {{ display: grid; grid-template-columns: repeat(auto-fit, minmax(160px, 1fr)); gap: 12px; margin-top: 24px; }}
.tile {{ background: var(--surface); border: 1px solid var(--border); border-radius: 12px; padding: 14px 16px; }}
.tile-label {{ color: var(--text-2); font-size: 13px; }}
.tile-value {{ font-size: 28px; font-weight: 600; margin: 2px 0; }}
.tile-note {{ color: var(--muted); font-size: 12px; min-height: 18px; }}
.spend {{ color: var(--text-2); font-size: 13px; margin: 10px 0 0; }}
.bar-row {{ display: grid; grid-template-columns: minmax(120px, 34%) 1fr auto; align-items: center;
  gap: 12px; padding: 4px 0; }}
.bar-label {{ color: var(--text-2); font-size: 14px; }}
.bar-track {{ height: 16px; border-left: 1px solid var(--grid); }}
.bar {{ display: block; height: 100%; background: var(--series-1); border-radius: 0 4px 4px 0; min-width: 0; }}
.bar-value {{ font-variant-numeric: tabular-nums; font-size: 14px; white-space: nowrap; }}
.question {{ padding: 14px 0; border-top: 1px solid var(--grid); }}
.question:first-of-type {{ border-top: 0; padding-top: 0; }}
.q-head {{ display: flex; flex-wrap: wrap; gap: 8px; align-items: baseline; font-weight: 500; }}
code {{ color: var(--muted); font-size: 12px; }}
.badge {{ font-size: 11px; color: var(--text-2); border: 1px solid var(--border); border-radius: 6px; padding: 0 6px; }}
.meter-row {{ display: flex; align-items: center; gap: 10px; margin: 8px 0 6px; }}
.meter {{ flex: 0 0 160px; height: 8px; background: var(--track); border-radius: 4px; overflow: hidden; }}
.meter span {{ display: block; height: 100%; background: var(--series-1); }}
.answers {{ color: var(--text-2); font-size: 14px; }}
.answers b, .legend b {{ color: var(--text); font-weight: 600; }}
.split {{ display: flex; gap: 2px; height: 16px; max-width: 420px; }}
.seg:last-child {{ border-radius: 0 4px 4px 0; }}
.seg-1 {{ background: var(--series-1); }}
.seg-2 {{ background: var(--series-2); }}
.legend {{ display: flex; gap: 16px; margin-top: 6px; font-size: 13px; color: var(--text-2); }}
.key {{ display: inline-flex; align-items: center; gap: 6px; }}
.swatch {{ width: 10px; height: 10px; border-radius: 2px; display: inline-block; }}
.examples {{ margin: 4px 0 0; padding-left: 18px; color: var(--text-2); font-size: 14px; }}
.table-wrap {{ overflow-x: auto; }}
table {{ width: 100%; border-collapse: collapse; font-size: 14px; }}
th {{ text-align: left; color: var(--muted); font-weight: 500; font-size: 13px; }}
th, td {{ padding: 8px 10px 8px 0; border-bottom: 1px solid var(--grid); vertical-align: top; }}
td.num {{ font-variant-numeric: tabular-nums; white-space: nowrap; }}
.empty {{ margin-top: 24px; color: var(--text-2); }}
footer {{ margin-top: 24px; color: var(--muted); font-size: 13px; }}
.tip {{ position: fixed; pointer-events: none; background: var(--text); color: var(--surface);
  font-size: 13px; padding: 4px 8px; border-radius: 6px; display: none; z-index: 10; max-width: 280px; }}
@media (max-width: 640px) {{
  .two-col {{ grid-template-columns: 1fr; gap: 0; }}
  .bar-row {{ grid-template-columns: 1fr auto; }}
  .bar-track {{ grid-column: 1 / -1; grid-row: 2; }}
  .meter {{ flex-basis: 100px; }}
}}
</style>
</head>
<body>
<main>
<h1>Аналитика звонков</h1>
<div class="sub">Сценарий <b>{scenario}</b> · {count} звонков · обновлено {generated}</div>
{body}
<footer>Номера телефонов скрыты. Записи разговоров и транскрипты на эту страницу не попадают.</footer>
</main>
<div class="tip" id="tip"></div>
<script>
const tip = document.getElementById("tip");
document.addEventListener("mousemove", (e) => {{
  const el = e.target.closest("[data-tip]");
  if (!el) {{ tip.style.display = "none"; return; }}
  tip.textContent = el.dataset.tip;
  tip.style.display = "block";
  tip.style.left = Math.min(e.clientX + 12, window.innerWidth - tip.offsetWidth - 8) + "px";
  tip.style.top = (e.clientY + 14) + "px";
}});
</script>
</body>
</html>
"""
