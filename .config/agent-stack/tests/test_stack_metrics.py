import importlib.util
import json
from datetime import datetime, timedelta, timezone
from importlib.machinery import SourceFileLoader
from pathlib import Path

STACK = Path(__file__).resolve().parents[1]
_loader = SourceFileLoader("stack_metrics", str(STACK / "bin" / "stack-metrics"))
_spec = importlib.util.spec_from_loader(_loader.name, _loader)
metrics = importlib.util.module_from_spec(_spec)
_loader.exec_module(metrics)

NOW = datetime(2026, 11, 20, 12, tzinfo=timezone.utc)


def _record(metric, value, hours_ago, host="host-a", definition="d1"):
    at = (NOW - timedelta(hours=hours_ago)).isoformat(timespec="seconds")
    return {"host": host, "metric": metric, "def": definition, "at": at, "value": value}


def _pi_session(home: Path, lines: list[dict]) -> None:
    path = home / ".pi/agent/sessions/project/2026-11-20T10-00-00-000Z_x.jsonl"
    path.parent.mkdir(parents=True)
    path.write_text("\n".join(json.dumps(line) for line in lines))


def test_collect_counts_human_corrections_skills_guards_and_compactions(tmp_path, monkeypatch):
    monkeypatch.setattr(metrics, "HOME", tmp_path)
    user = lambda text: {"type": "message", "message": {"role": "user", "content": [{"type": "text", "text": text}]}}
    _pi_session(tmp_path, [
        {"type": "session"},
        user("please add the flag"),
        user("no, that's not what I asked, again"),
        user("New task: bring PR 1 up to date, do not rebase"),
        {"type": "message", "message": {"role": "assistant", "content": [
            {"type": "toolCall", "name": "read", "arguments": {"path": "/x/skills/ci-red-triage/SKILL.md"}}]}},
        {"type": "message", "message": {"role": "toolResult", "content": [
            {"type": "text", "text": "Blocked destructive shell command. Use a narrower command."}]}},
        {"type": "compaction", "summary": "s"},
    ])

    records = {r["metric"]: r for r in metrics.collect("host-a", datetime(2026, 1, 1, tzinfo=timezone.utc))}

    assert (records["correction_rate"]["n"], records["correction_rate"]["hits"]) == (2, 1)
    assert records["correction_rate"]["value"] == 50.0
    assert records["skill_loads"]["value"] == {"ci-red-triage": 1}
    assert sum(records["guard_denies"]["value"].values()) == 1
    assert records["compactions"]["value"] == 1


def test_subagent_sessions_do_not_count_as_human_turns(tmp_path, monkeypatch):
    monkeypatch.setattr(metrics, "HOME", tmp_path)
    _pi_session(tmp_path, [
        {"type": "session", "parentSession": "/parent.jsonl"},
        {"type": "message", "message": {"role": "user", "content": "you forgot the tests again"}},
    ])

    record = metrics.collect("host-a", datetime(2026, 1, 1, tzinfo=timezone.utc))[0]

    assert record["n"] == 0 and record["value"] is None


def test_check_flags_stale_flat_and_unused():
    records = [_record("compactions", 3, hours_ago=30)]
    records += [_record("correction_rate", 1.0, hours_ago=h, host="host-b") for h in (1, 25, 49, 73, 97)]
    records += [_record("skill_loads", {"ci-red-triage": 4}, hours_ago=2)]

    problems = metrics.check(records, NOW, installed_skills={"ci-red-triage", "unslop"})

    assert any(p.startswith("STALE host-a/compactions") for p in problems)
    assert any(p.startswith("FLAT host-b/correction_rate") for p in problems)
    assert [p for p in problems if p.startswith("UNUSED")] == [
        "UNUSED skill unslop: 0 loads in 14 days on any host (deletion candidate)"
    ]


def test_a_changed_definition_starts_a_new_series_instead_of_hiding_staleness():
    records = [_record("compactions", 3, hours_ago=40, definition="old"),
               _record("compactions", 3, hours_ago=1, definition="new")]

    problems = metrics.check(records, NOW, installed_skills=set())

    assert problems == ["STALE host-a/compactions: last value 1d 16h ago"]


def test_a_tool_result_that_quotes_a_denial_is_not_a_denial(tmp_path, monkeypatch):
    monkeypatch.setattr(metrics, "HOME", tmp_path)
    quoted = "Report: the hook printed 'Blocked destructive shell command.' 674 times."
    _pi_session(tmp_path, [
        {"type": "session"},
        {"type": "message", "message": {"role": "toolResult", "content": [{"type": "text", "text": quoted}]}},
    ])

    record = {r["metric"]: r for r in metrics.collect("host-a", datetime(2026, 1, 1, tzinfo=timezone.utc))}

    assert record["guard_denies"]["value"] == {}
