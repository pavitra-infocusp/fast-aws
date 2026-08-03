"""AWS profile discovery, region resolution, and session creation.

Parses ~/.aws/config and ~/.aws/credentials the same way botocore does, with
SSO awareness so the app can offer SSO profiles and trigger `aws sso login`.
"""

from __future__ import annotations

import configparser
import os
from dataclasses import dataclass, field

DEFAULT_REGION = "us-east-1"


@dataclass
class ProfileInfo:
    name: str
    region: str = ""
    is_sso: bool = False
    sso_start_url: str = ""
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


def make_session(profile: str | None, region: str):
    """Create a boto3 Session for the given profile. Returns None-able."""
    import boto3

    kwargs: dict = {"region_name": region}
    if profile and profile != "default":
        kwargs["profile_name"] = profile
    return boto3.Session(**kwargs)
