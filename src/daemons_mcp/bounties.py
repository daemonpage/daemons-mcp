"""Bounties: tasks written from a conversation, kept as markdown files.

The folder a bounty sits in is its status. Nothing here starts an agent.
"""

from __future__ import annotations

import re
import shutil
from datetime import datetime, timezone
from pathlib import Path

from . import config

STATES = ("open", "claimed", "done", "dropped")


def root() -> Path:
    base = config.home() / "bounties"
    for state in STATES:
        (base / state).mkdir(parents=True, exist_ok=True)
    return base


def _now() -> str:
    return datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M UTC")


def _clean(text: str, limit: int) -> str:
    return " ".join(text.split())[:limit]


def _find(bounty_id: str) -> tuple[str, Path] | None:
    name = Path(bounty_id).name + ".md"
    for state in STATES:
        path = root() / state / name
        if path.exists():
            return state, path
    return None


def write(title: str, what: str, why: str = "", done_when: str = "", project: str = "",
          priority: str = "normal", origin: str = "connector") -> dict:
    title = _clean(title, 120)
    if not title or not what.strip():
        raise ValueError("a bounty needs a title and a description of what to build")
    priority = priority if priority in ("low", "normal", "high") else "normal"
    now = datetime.now(timezone.utc)
    slug = re.sub(r"[^a-z0-9]+", "-", title.lower()).strip("-")[:50] or "bounty"
    bounty_id = f"{now:%Y%m%d-%H%M%S}-{slug}"
    body = (
        f"---\nid: {bounty_id}\ntitle: {title}\nstatus: open\npriority: {priority}\n"
        f"project: {_clean(project, 80)}\norigin: {origin}\ncreated: {_now()}\n---\n\n"
        f"# {title}\n\n## What to build\n{what.strip()}\n\n"
        f"## Why\n{why.strip() or '(not stated)'}\n\n"
        f"## Done when\n{done_when.strip() or '(not stated: propose this before starting)'}\n\n## Log\n"
    )
    path = root() / "open" / f"{bounty_id}.md"
    with open(path, "x") as f:
        f.write(body)
    return {"id": bounty_id, "status": "open", "path": str(path)}


def _fields(text: str) -> dict:
    match = re.match(r"---\n(.*?)\n---", text, re.S)
    if not match:
        return {}
    return {k.strip(): v.strip() for k, v in (l.split(":", 1) for l in match.group(1).splitlines() if ":" in l)}


def listing(status: str = "open") -> list[dict]:
    if status != "all" and status not in STATES:
        raise ValueError(f"status must be one of {', '.join(STATES)} or all")
    out = []
    for state in STATES if status == "all" else (status,):
        for path in (root() / state).glob("*.md"):
            fields = _fields(path.read_text(errors="replace"))
            out.append({"id": path.stem, "title": fields.get("title"), "status": state,
                        "priority": fields.get("priority"), "project": fields.get("project"),
                        "created": fields.get("created")})
    rank = {"high": 0, "normal": 1, "low": 2}
    out.sort(key=lambda b: b["id"], reverse=True)
    out.sort(key=lambda b: rank.get(b["priority"], 1))
    return out


def read(bounty_id: str) -> dict | None:
    found = _find(bounty_id)
    return {"id": found[1].stem, "status": found[0], "text": found[1].read_text(errors="replace")} if found else None


def log(bounty_id: str, note: str) -> None:
    found = _find(bounty_id)
    if not found:
        raise ValueError(f"no bounty {bounty_id}")
    with open(found[1], "a") as f:
        f.write(f"- {_now()} {note}\n")


def move(bounty_id: str, to: str, note: str = "") -> None:
    found = _find(bounty_id)
    if not found:
        raise ValueError(f"no bounty {bounty_id}")
    state, path = found
    if to == "claimed" and state != "open":
        raise ValueError(f"{bounty_id} is {state}, not open")
    path.write_text(re.sub(r"^status: \w+", f"status: {to}", path.read_text(), count=1, flags=re.M))
    target = root() / to / path.name
    shutil.move(path, target)
    with open(target, "a") as f:
        f.write(f"- {_now()} {to}{': ' + note if note else ''}\n")
