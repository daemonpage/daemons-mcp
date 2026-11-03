"""Best-effort removal of credentials from text before it leaves your machine.

Transcripts often contain pasted keys. This catches common token formats and
KEY=value assignments, not every possible secret: see "Security" in the README.
"""

from __future__ import annotations

import re

_TOKENS = re.compile(
    r"sk-ant-[\w-]{10,}"
    r"|sk-[A-Za-z0-9_-]{20,}"
    r"|AIza[\w-]{30,}"
    r"|gh[pousr]_[A-Za-z0-9]{20,}"
    r"|github_pat_\w{20,}"
    r"|xox[abprs]-[\w-]{10,}"
    r"|ya29\.[\w.-]{20,}"
    r"|AKIA[0-9A-Z]{16}"
    r"|eyJ[\w-]{10,}\.eyJ[\w-]{10,}\.[\w-]{10,}"
    r"|-----BEGIN [A-Z ]*PRIVATE KEY-----.*?(?:-----END [A-Z ]*PRIVATE KEY-----|\Z)",
    re.S,
)
_ASSIGNMENTS = re.compile(
    r"(?i)\b([A-Z0-9_-]*(?:api[_-]?key|secret|token|password|passwd)[A-Z0-9_-]*)"
    r"(\s*[=:]\s*)[\"']?[^\s\"',;]{8,}[\"']?"
)
_BEARER = re.compile(r"(?i)\b(bearer\s+)[\w.~+/-]{16,}=*")


def redact(value):
    """Works on strings and on anything JSON-shaped containing them."""
    if isinstance(value, str):
        value = _TOKENS.sub("[REDACTED]", value)
        value = _ASSIGNMENTS.sub(r"\1\2[REDACTED]", value)
        return _BEARER.sub(r"\1[REDACTED]", value)
    if isinstance(value, list):
        return [redact(v) for v in value]
    if isinstance(value, dict):
        return {k: redact(v) for k, v in value.items()}
    return value
