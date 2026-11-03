"""Where daemons reads from and writes to. Both can be overridden for testing."""

from __future__ import annotations

import os
import secrets
import string
from pathlib import Path


def claude_dir() -> Path:
    return Path(os.environ.get("DAEMONS_CLAUDE_DIR", Path.home() / ".claude"))


def home() -> Path:
    path = Path(os.environ.get("DAEMONS_HOME", Path.home() / ".daemon" / "mcp"))
    path.mkdir(parents=True, exist_ok=True, mode=0o700)
    return path


def secret() -> str:
    """The secret in the connector URL. Created once; delete the file to rotate it."""
    path = home() / "secret"
    if path.exists():
        return path.read_text().strip()
    alphabet = string.ascii_lowercase + string.digits
    value = "".join(secrets.choice(alphabet) for _ in range(32))
    fd = os.open(path, os.O_WRONLY | os.O_CREAT | os.O_TRUNC, 0o600)
    with os.fdopen(fd, "w") as f:
        f.write(value)
    return value
