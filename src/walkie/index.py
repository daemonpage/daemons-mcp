"""Searchable index of Claude Code sessions and memory files, in SQLite.

Reads the transcripts Claude Code keeps under ~/.claude/projects and never
writes there. Only what you and Claude said is indexed: no tool output, no
subagents, no injected system text.
"""

from __future__ import annotations

import hashlib
import json
import os
import re
import sqlite3
from contextlib import contextmanager
from datetime import datetime, timezone
from pathlib import Path

from . import config

SCHEMA = """
CREATE TABLE IF NOT EXISTS sessions (
    id TEXT PRIMARY KEY, path TEXT NOT NULL, mtime REAL NOT NULL, size INTEGER NOT NULL,
    cwd TEXT, title TEXT, first_prompt TEXT, last_prompt TEXT, last_reply TEXT,
    started TEXT, updated TEXT, messages INTEGER
);
CREATE TABLE IF NOT EXISTS files (
    id TEXT PRIMARY KEY, path TEXT NOT NULL, mtime REAL NOT NULL, name TEXT
);
CREATE VIRTUAL TABLE IF NOT EXISTS search USING fts5(
    ref UNINDEXED, kind UNINDEXED, title, role UNINDEXED, at UNINDEXED, text
);
"""

_INJECTED = re.compile(
    r"<(system-reminder|command-name|command-message|command-args|local-command-stdout|"
    r"local-command-caveat|task-notification)\b.*?(</\1>|\Z)",
    re.S,
)
_CONTINUED = "This session is being continued"


@contextmanager
def connect():
    conn = sqlite3.connect(config.home() / "index.db", timeout=30)
    conn.row_factory = sqlite3.Row
    conn.executescript(SCHEMA)
    try:
        yield conn
        conn.commit()
    finally:
        conn.close()


def _text_of(message) -> str:
    content = message.get("content") if isinstance(message, dict) else None
    if isinstance(content, str):
        text = content
    elif isinstance(content, list):
        text = "\n".join(b.get("text", "") for b in content if isinstance(b, dict) and b.get("type") == "text")
    else:
        return ""
    return _INJECTED.sub("", text).strip()


def parse_session(path: Path) -> dict:
    """Returns the conversation in a transcript, skipping lines it cannot read."""
    turns, cwd, title = [], None, None
    with open(path, errors="replace") as f:
        for line in f:
            try:
                entry = json.loads(line)
            except ValueError:
                continue
            kind = entry.get("type")
            if kind == "custom-title":
                title = entry.get("customTitle") or title
            elif kind == "ai-title" and not title:
                title = entry.get("aiTitle")
            if kind not in ("user", "assistant") or entry.get("isSidechain") or entry.get("isMeta"):
                continue
            cwd = cwd or entry.get("cwd")
            text = _text_of(entry.get("message"))
            if text and not text.startswith(_CONTINUED):
                turns.append({"role": kind, "at": entry.get("timestamp"), "text": text})
    return {"turns": turns, "cwd": cwd, "title": title}


def _included(path: Path, only: list[str]) -> bool:
    return not only or any(term.lower() in str(path).lower() for term in only)


def _memory_files(root: Path, only: list[str]) -> list[Path]:
    found = [p for p in root.glob("projects/*/memory/*.md") if _included(p, only)]
    if not only and (root / "CLAUDE.md").exists():
        found.append(root / "CLAUDE.md")
    notes = config.home() / "notes"
    if notes.exists():
        found.extend(notes.glob("*.md"))
    return found


def update(only: list[str] | None = None) -> dict:
    """Indexes whatever changed since the last run. Safe to run repeatedly."""
    only = only or []
    root = config.claude_dir()
    changed = 0
    with connect() as conn:
        known = {r["id"]: (r["mtime"], r["size"]) for r in conn.execute("SELECT id, mtime, size FROM sessions")}
        live_sessions = set()
        for path in root.glob("projects/*/*.jsonl"):
            if path.name.startswith("agent-") or not _included(path, only):
                continue
            sid, stat = path.stem, path.stat()
            live_sessions.add(sid)
            if known.get(sid) == (stat.st_mtime, stat.st_size):
                continue
            parsed = parse_session(path)
            conn.execute("DELETE FROM search WHERE ref = ?", (f"session:{sid}",))
            turns = parsed["turns"]
            prompts = [t["text"] for t in turns if t["role"] == "user"]
            replies = [t["text"] for t in turns if t["role"] == "assistant"]
            title = parsed["title"] or (prompts[0][:80] if prompts else sid[:8])
            conn.execute(
                "INSERT OR REPLACE INTO sessions VALUES (?,?,?,?,?,?,?,?,?,?,?,?)",
                (sid, str(path), stat.st_mtime, stat.st_size, parsed["cwd"], title,
                 prompts[0][:500] if prompts else None, prompts[-1][:500] if prompts else None,
                 replies[-1][:800] if replies else None,
                 turns[0]["at"] if turns else None,
                 datetime.fromtimestamp(stat.st_mtime, timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ"),
                 len(turns)),
            )
            conn.executemany(
                "INSERT INTO search (ref, kind, title, role, at, text) VALUES (?,?,?,?,?,?)",
                [(f"session:{sid}", "session", title, t["role"], t["at"], t["text"]) for t in turns],
            )
            changed += 1
        for sid in set(known) - live_sessions:
            conn.execute("DELETE FROM sessions WHERE id = ?", (sid,))
            conn.execute("DELETE FROM search WHERE ref = ?", (f"session:{sid}",))

        known_files = {r["id"]: r["mtime"] for r in conn.execute("SELECT id, mtime FROM files")}
        live_files = set()
        for path in _memory_files(root, only):
            fid = hashlib.sha256(str(path).encode()).hexdigest()[:12]
            live_files.add(fid)
            mtime = path.stat().st_mtime
            if known_files.get(fid) == mtime:
                continue
            ref = f"memory:{fid}"
            conn.execute("DELETE FROM search WHERE ref = ?", (ref,))
            conn.execute("INSERT OR REPLACE INTO files VALUES (?,?,?,?)", (fid, str(path), mtime, path.name))
            conn.execute(
                "INSERT INTO search (ref, kind, title, role, at, text) VALUES (?,?,?,?,?,?)",
                (ref, "memory", path.name, None,
                 datetime.fromtimestamp(mtime, timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ"),
                 path.read_text(errors="replace")),
            )
            changed += 1
        for fid in set(known_files) - live_files:
            conn.execute("DELETE FROM files WHERE id = ?", (fid,))
            conn.execute("DELETE FROM search WHERE ref = ?", (f"memory:{fid}",))
    return {"changed": changed}


def _fts_query(query: str) -> str:
    terms = re.findall(r"\w[\w'-]*", query, re.UNICODE)
    return " OR ".join('"' + t.replace('"', "") + '"' for t in terms)


def search(query: str, limit: int = 10) -> list[dict]:
    """Best match per session or file, so a long chat cannot fill the results."""
    match = _fts_query(query)
    if not match:
        return []
    with connect() as conn:
        rows = conn.execute(
            "SELECT ref, kind, title, role, at, snippet(search, 5, '', '', ' … ', 40) AS snippet "
            "FROM search WHERE search MATCH ? ORDER BY bm25(search, 0, 0, 2.0, 0, 0, 1.0) LIMIT ?",
            (match, max(limit * 30, 200)),
        ).fetchall()
    seen, hits = set(), []
    for row in rows:
        if row["ref"] not in seen:
            seen.add(row["ref"])
            hits.append(dict(row))
        if len(hits) == limit:
            break
    return hits


def sessions(query: str = "", limit: int = 15) -> list[dict]:
    with connect() as conn:
        rows = conn.execute(
            "SELECT id, cwd, title, first_prompt, last_prompt, last_reply, started, updated, messages "
            "FROM sessions WHERE messages > 0 ORDER BY mtime DESC"
        ).fetchall()
    terms = query.lower().split()
    out = []
    for row in rows:
        haystack = f"{row['title']} {row['cwd']} {row['first_prompt']} {row['last_prompt']}".lower()
        if all(t in haystack for t in terms):
            out.append(dict(row))
            if len(out) == limit:
                break
    return out


def session_turns(session_id: str, last: int = 20) -> dict | None:
    with connect() as conn:
        row = conn.execute("SELECT * FROM sessions WHERE id = ?", (session_id,)).fetchone()
    if not row:
        return None
    turns = parse_session(Path(row["path"]))["turns"]
    return {"id": row["id"], "title": row["title"], "cwd": row["cwd"], "updated": row["updated"],
            "total_messages": len(turns), "messages": turns[-last:]}


def memory_file(file_id: str) -> dict | None:
    """Only files in the index can be read, by id: a ref can never name a path."""
    with connect() as conn:
        row = conn.execute("SELECT * FROM files WHERE id = ?", (file_id,)).fetchone()
    if not row or not os.path.isfile(row["path"]):
        return None
    return {"name": row["name"], "text": Path(row["path"]).read_text(errors="replace")}
