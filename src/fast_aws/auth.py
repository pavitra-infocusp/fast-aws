"""AWS profile discovery, region resolution, and session creation.

Parses ~/.aws/config and ~/.aws/credentials the same way botocore does, with
SSO awareness so the app can offer SSO profiles and trigger `aws sso login`.
"""

from __future__ import annotations

import configparser
import hashlib
import json
from datetime import datetime, timezone
import os
from dataclasses import dataclass, field

DEFAULT_REGION = "us-east-1"


@dataclass
class ProfileInfo:
    name: str
    region: str = ""
    is_sso: bool = False
    sso_start_url: str = ""
    sso_session: str = ""
    sso_account_id: str = ""
    sso_role_name: str = ""
    credential_process: str = ""
    source_profile: str = ""
    description: str = field(default="")


def aws_config_path() -> str:
    return os.path.expanduser("~/.aws/config")


def list_profiles() -> list[ProfileInfo]:
    path = aws_config_path()
    profiles: list[ProfileInfo] = []
    if not os.path.exists(path):
        return profiles
    cp = configparser.ConfigParser(interpolation=None)
    try:
        cp.read(path)
    except configparser.Error:
        return profiles

    for section in cp.sections():
        if section == "default":
            name = "default"
        elif section.startswith("profile "):
            name = section[len("profile ") :]
        else:
            # sso-session, assume-role chains, etc. — not directly selectable
            continue
        opts = dict(cp.items(section))
        profiles.append(
            ProfileInfo(
                name=name,
                region=opts.get("region", ""),
                is_sso=bool(opts.get("sso_session") or opts.get("sso_start_url")),
                sso_start_url=opts.get("sso_start_url", ""),
                sso_session=opts.get("sso_session", ""),
                sso_account_id=opts.get("sso_account_id", ""),
                sso_role_name=opts.get("sso_role_name", ""),
                credential_process=opts.get("credential_process", ""),
                source_profile=opts.get("source_profile", ""),
            )
        )
    # Sort so `default` comes first, then alphabetically
    profiles.sort(key=lambda p: (p.name != "default", p.name.lower()))
    return profiles


def profile_names() -> list[str]:
    return [p.name for p in list_profiles()]


def resolve_region(profile: str | None, cli_region: str | None = None) -> str:
    if cli_region:
        return cli_region
    env = os.environ.get("AWS_REGION") or os.environ.get("AWS_DEFAULT_REGION")
    if env:
        return env
    if profile:
        for p in list_profiles():
            if p.name == profile and p.region:
                return p.region
    return DEFAULT_REGION


def identity_label_from_arn(arn: str) -> str:
    """Short display name from a GetCallerIdentity Arn.

    ``arn:aws:sts::123:assumed-role/Admin/session`` → ``Admin``
    ``arn:aws:iam::123:role/Admin`` → ``Admin``
    ``arn:aws:iam::123:user/alice`` → ``alice``
    ``arn:aws:iam::123:root`` → ``root``
    """
    if not arn:
        return ""
    # arn:partition:service:region:account:resource
    parts = arn.split(":", 5)
    resource = parts[5] if len(parts) == 6 else arn
    if resource.startswith("assumed-role/"):
        return resource[len("assumed-role/") :].split("/", 1)[0]
    if resource.startswith("federated-user/"):
        return resource[len("federated-user/") :]
    if "/" in resource:
        return resource.split("/", 1)[1]
    return resource


def make_session(profile: str | None, region: str):
    """Create a boto3 Session for the given profile. Returns None-able."""
    import boto3

    kwargs: dict = {"region_name": region}
    if profile and profile != "default":
        kwargs["profile_name"] = profile
    return boto3.Session(**kwargs)


def sso_session_expiry(profile: ProfileInfo) -> datetime | None:
    """Expiry of the cached SSO access token for a profile, or None if unknown."""
    key = profile.sso_session or profile.sso_start_url
    if not key:
        return None
    # For sso-session profiles the sso-session section may hold the start url
    # and the cache file is keyed by the session name; legacy by start url.
    fname = hashlib.sha1(key.encode("utf-8")).hexdigest() + ".json"
    path = os.path.expanduser(os.path.join("~/.aws/sso/cache", fname))
    try:
        with open(path) as f:
            raw = json.load(f).get("expiresAt")
        if not raw:
            return None
        return datetime.fromisoformat(str(raw).replace("Z", "+00:00").replace("UTC", "+00:00")).astimezone(
            timezone.utc
        )
    except (OSError, ValueError, AttributeError):
        return None


def format_expiry(expiry: datetime | None, now: datetime | None = None) -> str:
    """Human label like ``expires 18:30 (in 2h 5m)`` / ``expired`` / ``not logged in``."""
    if expiry is None:
        return "not logged in"
    now = now or datetime.now(timezone.utc)
    secs = int((expiry - now).total_seconds())
    if secs <= 0:
        return "expired"
    h, rem = divmod(secs, 3600)
    m = rem // 60
    left = f"{h}h {m}m" if h else f"{m}m"
    return f"expires {expiry.astimezone():%H:%M} (in {left})"
