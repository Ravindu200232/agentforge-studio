"""Keep a pasted secret out of the conversation.

What is typed in the chat is sent to a model and kept in the project's logs. A connection string with a
password, an access key or a private key does not belong there: it belongs in Settings, where it is kept
out of both and handed only to the run that needs it (`deploy_vars.py`). This looks for the shapes such
secrets have, and the studio says so and asks for them to be saved instead, rather than carrying on with
the secret in the conversation.
"""
from __future__ import annotations

import re

from . import prompts

# scheme://user:password@host — the password being anything but an obvious placeholder.
_URI_WITH_PASSWORD = re.compile(r"\b[a-z][a-z0-9+.\-]*://[^\s/:@]+:([^\s/@]+)@[^\s]+", re.IGNORECASE)
_PLACEHOLDER = re.compile(r"^(<.*>|\{\{.*\}\}|\*+|x+|password|pass|secret|yourpassword|your[-_ ]?password|"
                          r"changeme|example|pwd)$", re.IGNORECASE)
_KNOWN = (
    re.compile(r"\bgh[pousr]_[A-Za-z0-9]{30,}"),                    # GitHub tokens
    re.compile(r"\bgithub_pat_[A-Za-z0-9_]{40,}"),
    re.compile(r"\b(?:AKIA|ASIA)[0-9A-Z]{16}\b"),                   # AWS access key ids
    re.compile(r"\bsk-[A-Za-z0-9_\-]{20,}"),                        # API keys of the sk- kind
    re.compile(r"\bxox[baprs]-[A-Za-z0-9\-]{10,}"),                 # Slack
    re.compile(r"-----BEGIN [A-Z ]*PRIVATE KEY-----"),
    re.compile(r"\beyJ[A-Za-z0-9_\-]{15,}\.[A-Za-z0-9_\-]{15,}\.[A-Za-z0-9_\-]{10,}"),   # a signed token
)


def looks_secret(text: str) -> bool:
    """Whether the text seems to contain a credential."""
    body = str(text or "")
    for match in _URI_WITH_PASSWORD.finditer(body):
        if not _PLACEHOLDER.match(match.group(1)):
            return True
    return any(pattern.search(body) for pattern in _KNOWN)


def mask(text: str) -> str:
    """The text with anything that looks like a credential hidden (what a tool printed, before it is shown)."""
    hidden = _URI_WITH_PASSWORD.sub(lambda m: m.group(0).replace(m.group(1), "<hidden>", 1)
                                    if not _PLACEHOLDER.match(m.group(1)) else m.group(0), str(text or ""))
    for pattern in _KNOWN:
        hidden = pattern.sub("<hidden>", hidden)
    return hidden


def refusal(text: str) -> str:
    """What to tell the person when their message holds a credential, or an empty string when it does not."""
    return prompts.load("chat/secret-refused").strip() if looks_secret(text) else ""
