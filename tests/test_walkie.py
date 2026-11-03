import json

import pytest

from walkie import bounties, index
from walkie.redact import redact


def line(kind, text, **extra):
    return json.dumps({"type": kind, "timestamp": "2026-01-02T03:04:05Z", "cwd": "/work/app",
                       "message": {"role": kind, "content": text}, **extra})


@pytest.fixture
def env(tmp_path, monkeypatch):
    claude = tmp_path / "claude"
    monkeypatch.setenv("WALKIE_CLAUDE_DIR", str(claude))
    monkeypatch.setenv("WALKIE_HOME", str(tmp_path / "walkie"))
    project = claude / "projects" / "-work-app"
    (project / "memory").mkdir(parents=True)
    (project / "s1.jsonl").write_text("\n".join([
        json.dumps({"type": "custom-title", "customTitle": "Payment bug"}),
        line("user", "<system-reminder>injected zebra</system-reminder>fix the payment retry"),
        line("assistant", [{"type": "thinking", "thinking": "hidden giraffe"},
                           {"type": "text", "text": "Retry fixed in billing.py"}]),
        line("user", "subagent walrus", isSidechain=True),
        "not json at all",
    ]))
    (project / "memory" / "prefs.md").write_text("Prefers short replies about kayaks")
    index.update()
    return project


def test_only_the_conversation_is_indexed(env):
    assert index.search("payment")[0]["ref"] == "session:s1"
    for hidden in ("zebra", "giraffe", "walrus"):
        assert index.search(hidden) == []


def test_session_summary_and_read(env):
    session = index.sessions()[0]
    assert session["title"] == "Payment bug"
    assert session["last_reply"] == "Retry fixed in billing.py"
    assert [t["role"] for t in index.session_turns("s1")["messages"]] == ["user", "assistant"]


def test_memory_is_read_by_id_only(env):
    hit = index.search("kayaks")[0]
    assert index.memory_file(hit["ref"].removeprefix("memory:"))["name"] == "prefs.md"
    assert index.memory_file("../../etc/passwd") is None


def test_update_handles_change_and_deletion(env):
    assert index.update()["changed"] == 0
    with open(env / "s1.jsonl", "a") as f:
        f.write("\n" + line("user", "now about lighthouses"))
    assert index.update()["changed"] == 1
    assert index.search("lighthouses")
    assert len(index.search("payment")) == 1
    (env / "s1.jsonl").unlink()
    index.update()
    assert index.search("payment") == [] and index.sessions() == []


def test_search_survives_hostile_query(env):
    assert index.search('"; DROP TABLE search; --') == []
    assert index.search("") == []


def test_redact():
    key = "sk-ant-" + "a1" * 12
    assert key not in redact(f"key {key} end")
    assert "hunter2hunter2" not in redact("PASSWORD=hunter2hunter2")
    assert "abcdefghijklmnopqrstuv" not in redact({"a": ["Authorization: Bearer abcdefghijklmnopqrstuv"]})["a"][0]
    assert redact("the token is fine") == "the token is fine"


def test_bounty_lifecycle(env):
    bid = bounties.write("Add dark mode!", "Make it dark", priority="high")["id"]
    assert bounties.listing()[0]["priority"] == "high"
    bounties.move(bid, "claimed")
    with pytest.raises(ValueError):
        bounties.move(bid, "claimed")
    bounties.log(bid, "halfway")
    bounties.move(bid, "done", "shipped")
    found = bounties.read(bid)
    assert found["status"] == "done" and "halfway" in found["text"] and "status: done" in found["text"]
    assert bounties.listing() == []


def test_bounty_ids_cannot_escape(env):
    bounties.write("safe", "x")
    assert bounties.read("../../secret") is None
    with pytest.raises(ValueError):
        bounties.write("  ", "x")
