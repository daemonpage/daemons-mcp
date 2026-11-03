import json
import threading
import time
import urllib.error
import urllib.request

import pytest
import uvicorn

PORT = 18765


def post(path, method, params=None):
    body = json.dumps({"jsonrpc": "2.0", "id": 1, "method": method, "params": params or {}}).encode()
    req = urllib.request.Request(f"http://127.0.0.1:{PORT}{path}", body, {
        "Content-Type": "application/json", "Accept": "application/json, text/event-stream"})
    with urllib.request.urlopen(req, timeout=10) as r:
        raw = r.read().decode()
    return json.loads(next(l[6:] for l in raw.splitlines() if l.startswith("data: ")))["result"]


@pytest.fixture(scope="module")
def secret(tmp_path_factory):
    tmp = tmp_path_factory.mktemp("w")
    mp = pytest.MonkeyPatch()
    mp.setenv("DAEMONS_CLAUDE_DIR", str(tmp / "claude"))
    mp.setenv("DAEMONS_HOME", str(tmp / "daemons"))
    project = tmp / "claude" / "projects" / "p"
    project.mkdir(parents=True)
    (project / "s.jsonl").write_text(json.dumps({
        "type": "user", "cwd": "/p", "timestamp": "2026-01-01T00:00:00Z",
        "message": {"content": "my key is sk-ant-abcdefghijklmnopqrstuvwxyz about otters"}}))
    from daemons_mcp import config, index, server
    index.update()
    srv = uvicorn.Server(uvicorn.Config(server.app(), host="127.0.0.1", port=PORT, log_level="error"))
    threading.Thread(target=srv.run, daemon=True).start()
    while not srv.started:
        time.sleep(0.05)
    yield config.secret()
    srv.should_exit = True
    mp.undo()


def call(secret, name, **arguments):
    result = post(f"/{secret}", "tools/call", {"name": name, "arguments": arguments})
    assert not result.get("isError"), result
    return [json.loads(c["text"]) for c in result["content"]]


@pytest.mark.parametrize("path", ["/mcp", "/", "/wrong", "/.well-known/oauth-protected-resource"])
def test_wrong_paths_get_404(secret, path):
    with pytest.raises(urllib.error.HTTPError) as e:
        post(path, "tools/list")
    assert e.value.code == 404


def test_tools_cannot_run_anything(secret):
    names = {t["name"] for t in post(f"/{secret}", "tools/list")["tools"]}
    assert names == {"get_current_context", "search_memory", "list_sessions", "read_session", "read_memory_file",
                     "write_bounty", "list_bounties", "read_bounty", "save_note"}


def test_results_are_redacted(secret):
    hit = call(secret, "search_memory", query="otters")[0]
    assert "sk-ant" not in json.dumps(hit)
    assert "sk-ant" not in json.dumps(call(secret, "read_session", session=hit["ref"]))
    assert "sk-ant" not in json.dumps(call(secret, "get_current_context"))


def test_write_paths_round_trip(secret):
    bid = call(secret, "write_bounty", title="Build it", what="Do the thing")[0]["id"]
    assert call(secret, "list_bounties")[0]["id"] == bid
    assert "Do the thing" in call(secret, "read_bounty", bounty_id=bid)[0]["text"]
    call(secret, "save_note", text="the walrus plan")
    ref = call(secret, "search_memory", query="walrus")[0]["ref"]
    assert "walrus" in call(secret, "read_memory_file", ref=ref)[0]["text"]


def test_client_handshake(secret):
    result = post(f"/{secret}", "initialize", {
        "protocolVersion": "2025-06-18", "capabilities": {}, "clientInfo": {"name": "t", "version": "1"}})
    assert result["serverInfo"]["name"] == "daemons"
    assert "get_current_context" in result["instructions"]
