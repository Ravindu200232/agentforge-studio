"""Signing in to GitHub in the browser, instead of pasting a token.

The same shape as the AWS Identity Center flow the deployment agent already
drives (`deployment_agent/aws_sso.py`): ask GitHub for a short code, send the
person to a page to approve it, then poll until they have. Nobody copies a
token out of a settings page and nobody types one in here, which matters
because a personal access token pasted into a field is a long-lived secret that
has been through a clipboard.

GitHub's device flow needs no client secret and no redirect URI, which is why
it suits a program running on someone's own machine. It does need the client id
of an OAuth app with "Device flow" enabled - a public value, and the one thing
this cannot supply for itself.
"""
from __future__ import annotations

import secrets
import threading
import time
from dataclasses import dataclass, field

import httpx

DEVICE_CODE_URL = "https://github.com/login/device/code"
ACCESS_TOKEN_URL = "https://github.com/login/oauth/access_token"

# What a deployment does with the account: create the repository it pushes to,
# and let Actions run the workflow it writes. Nothing wider.
SCOPES = "repo workflow"

# GitHub expires a device code after fifteen minutes; nothing is kept past that.
TTL_SECONDS = 900


@dataclass
class DeviceFlow:
    flow_id: str
    device_code: str
    user_code: str
    verification_uri: str
    client_id: str
    interval: int = 5
    expires_at: float = 0.0
    created_at: float = field(default_factory=time.time)


class GithubDeviceFlows:
    """Starts and polls device sign-ins, one per person who asks."""

    def __init__(self) -> None:
        self._flows: dict[str, DeviceFlow] = {}
        self._lock = threading.RLock()

    def _prune(self) -> None:
        now = time.time()
        for key in [k for k, f in self._flows.items() if f.expires_at and f.expires_at < now]:
            self._flows.pop(key, None)

    def start(self, client_id: str) -> dict:
        client_id = str(client_id or "").strip()
        if not client_id:
            raise ValueError(
                "A GitHub OAuth app client id is needed before anyone can sign in. "
                "Make one at github.com/settings/developers - New OAuth App, any "
                "callback URL, then tick Enable Device Flow - and save its Client "
                "ID under Deploy. It is a public value, not a secret.")
        try:
            answer = httpx.post(
                DEVICE_CODE_URL,
                data={"client_id": client_id, "scope": SCOPES},
                headers={"Accept": "application/json"}, timeout=30)
        except httpx.HTTPError as exc:
            raise ValueError(f"GitHub could not be reached: {exc}") from exc
        body = _json(answer)
        if body.get("error") or not body.get("device_code"):
            raise ValueError(_why(body, answer.status_code))

        flow = DeviceFlow(
            flow_id="ghd_" + secrets.token_urlsafe(18),
            device_code=str(body["device_code"]),
            user_code=str(body.get("user_code", "")),
            verification_uri=str(body.get("verification_uri")
                                 or "https://github.com/login/device"),
            client_id=client_id,
            interval=max(1, int(body.get("interval", 5) or 5)),
            expires_at=time.time() + min(TTL_SECONDS, int(body.get("expires_in", 900) or 900)),
        )
        with self._lock:
            self._prune()
            self._flows[flow.flow_id] = flow
        return {
            "flow_id": flow.flow_id,
            "user_code": flow.user_code,
            "verification_uri": flow.verification_uri,
            # What the person is actually approving, so the studio can say so.
            "scopes": SCOPES,
            "interval": flow.interval,
            "expires_in": int(flow.expires_at - time.time()),
        }

    def poll(self, flow_id: str) -> dict:
        """`pending` until they approve it, then the token, once."""
        with self._lock:
            self._prune()
            flow = self._flows.get(str(flow_id or ""))
        if not flow:
            raise ValueError("That sign-in has expired. Start it again.")
        try:
            answer = httpx.post(
                ACCESS_TOKEN_URL,
                data={"client_id": flow.client_id, "device_code": flow.device_code,
                      "grant_type": "urn:ietf:params:oauth:grant-type:device_code"},
                headers={"Accept": "application/json"}, timeout=30)
        except httpx.HTTPError as exc:
            raise ValueError(f"GitHub could not be reached: {exc}") from exc
        body = _json(answer)

        token = str(body.get("access_token") or "")
        if token:
            # Handed over once. Keeping it here as well would mean a second
            # copy of a live credential in memory for no reason.
            with self._lock:
                self._flows.pop(flow.flow_id, None)
            return {"status": "ready", "token": token,
                    "scopes": str(body.get("scope") or SCOPES)}

        error = str(body.get("error") or "")
        if error == "authorization_pending":
            return {"status": "pending", "interval": flow.interval}
        if error == "slow_down":
            # GitHub is asking to be polled less often, and says how much less.
            flow.interval = max(flow.interval + 5, int(body.get("interval", 0) or 0))
            return {"status": "pending", "interval": flow.interval}
        with self._lock:
            self._flows.pop(flow.flow_id, None)
        if error == "expired_token":
            raise ValueError("That sign-in expired before it was approved. Start it again.")
        if error == "access_denied":
            raise ValueError("The sign-in was declined on GitHub.")
        raise ValueError(_why(body, answer.status_code))


def _json(answer) -> dict:
    try:
        body = answer.json()
    except ValueError:
        return {}
    return body if isinstance(body, dict) else {}


def _why(body: dict, status: int) -> str:
    """GitHub's own words where they help, and something useful where they do not."""
    error = str(body.get("error") or "").strip()
    if error == "device_flow_disabled":
        return ("That OAuth app does not have Device Flow enabled. Turn it on in "
                "its settings on GitHub and try again.")
    # GitHub answers an unknown client id with a bare "Not Found", which reads
    # as though the page were missing rather than the id being wrong.
    if status == 404 or error in ("Not Found", "not_found"):
        return ("GitHub does not recognise that Client ID. Check it against the "
                "OAuth app at github.com/settings/developers - it is the Client "
                "ID, not the app name or the secret.")
    if error == "incorrect_client_credentials":
        return "GitHub rejected that Client ID."
    said = str(body.get("error_description") or error).strip()
    return said or f"GitHub refused the sign-in (HTTP {status})."


FLOWS = GithubDeviceFlows()
