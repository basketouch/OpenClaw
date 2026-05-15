import json
import logging
import os

log = logging.getLogger(__name__)

_DATA_DIR = "/data"
_VAPID_FILE = os.path.join(_DATA_DIR, "vapid.json")
_SUBS_FILE = os.path.join(_DATA_DIR, "push_subscriptions.json")


def _load_vapid() -> dict:
    try:
        with open(_VAPID_FILE) as f:
            return json.load(f)
    except (FileNotFoundError, json.JSONDecodeError):
        return {}


def get_or_create_vapid() -> tuple[str, str]:
    """Returns (public_key_base64url, private_key_pem)."""
    data = _load_vapid()
    if data.get("public") and data.get("private"):
        return data["public"], data["private"]

    from py_vapid import Vapid
    from cryptography.hazmat.primitives.serialization import (
        Encoding, PrivateFormat, PublicFormat, NoEncryption
    )
    import base64

    vapid = Vapid()
    vapid.generate_keys()
    priv_pem = vapid.private_key.private_bytes(
        Encoding.PEM, PrivateFormat.TraditionalOpenSSL, NoEncryption()
    ).decode()
    pub_raw = vapid.public_key.public_bytes(Encoding.X962, PublicFormat.UncompressedPoint)
    pub_b64 = base64.urlsafe_b64encode(pub_raw).rstrip(b"=").decode()

    os.makedirs(_DATA_DIR, exist_ok=True)
    with open(_VAPID_FILE, "w") as f:
        json.dump({"public": pub_b64, "private": priv_pem}, f)
    log.info("VAPID keys generated")
    return pub_b64, priv_pem


def load_subscriptions() -> list[dict]:
    try:
        with open(_SUBS_FILE) as f:
            return json.load(f)
    except (FileNotFoundError, json.JSONDecodeError):
        return []


def save_subscription(sub: dict):
    endpoint = sub.get("endpoint", "")
    clean = {"endpoint": endpoint, "keys": sub.get("keys", {})}
    subs = [s for s in load_subscriptions() if s.get("endpoint") != endpoint]
    subs.append(clean)
    os.makedirs(_DATA_DIR, exist_ok=True)
    with open(_SUBS_FILE, "w") as f:
        json.dump(subs, f)


def remove_subscription(endpoint: str):
    subs = [s for s in load_subscriptions() if s.get("endpoint") != endpoint]
    os.makedirs(_DATA_DIR, exist_ok=True)
    with open(_SUBS_FILE, "w") as f:
        json.dump(subs, f)


def send_notification(title: str, body: str):
    """Synchronous — call via asyncio.to_thread from async context."""
    from pywebpush import webpush, WebPushException
    _, priv_pem = get_or_create_vapid()
    dead = []
    for sub in load_subscriptions():
        try:
            webpush(
                subscription_info=sub,
                data=json.dumps({"title": title, "body": body}),
                vapid_private_key=priv_pem,
                vapid_claims={"sub": "mailto:alex@openclaw.local"},
            )
        except WebPushException as e:
            resp = getattr(e, "response", None)
            if resp is not None and resp.status_code in (404, 410):
                dead.append(sub.get("endpoint", ""))
            else:
                log.warning("Push error: %s", e)
        except Exception as e:
            log.warning("Push error: %s", e)
    for ep in dead:
        remove_subscription(ep)
