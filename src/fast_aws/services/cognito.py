"""Cognito service: user pools (with nested subresources) and identity pools."""

from __future__ import annotations

from typing import Any

from botocore.exceptions import ClientError

from fast_aws.fmt import describe_fallback, detail_fallback, fmt_time, kv_block, section, truncate
from fast_aws.models import Item, Link, Page
from fast_aws.services.base import ResourceService

POOLS_DIR = "__pools"
IDENTITY_DIR = "__identity"
USERS_DIR = "__users"
GROUPS_DIR = "__groups"
CLIENTS_DIR = "__clients"
PROVIDERS_DIR = "__providers"
TRIGGERS_DIR = "__triggers"

# Friendly breadcrumb / table labels for synthetic path segments.
_DIR_LABELS = {
    POOLS_DIR: "User Pools",
    IDENTITY_DIR: "Identity Pools",
    USERS_DIR: "Users",
    GROUPS_DIR: "Groups",
    CLIENTS_DIR: "App clients",
    PROVIDERS_DIR: "Identity providers",
    TRIGGERS_DIR: "Triggers",
}


def _lambda_trigger_label(value: Any) -> str | None:
    """Short name from a LambdaConfig entry (ARN string or nested config dict)."""
    arn = _lambda_trigger_arn(value)
    if not arn:
        return None
    # arn:...:function:name or arn:...:function:name:version|alias
    if ":function:" in arn:
        return arn.split(":function:", 1)[1].split(":", 1)[0]
    return arn.split(":")[-1]


def _lambda_trigger_arn(value: Any) -> str | None:
    if isinstance(value, str) and value:
        return value
    if isinstance(value, dict):
        arn = value.get("LambdaArn") or ""
        if isinstance(arn, str) and arn:
            return arn
    return None


def _attr_map(attrs: list | None) -> dict[str, str]:
    out: dict[str, str] = {}
    for a in attrs or []:
        if isinstance(a, dict) and a.get("Name"):
            out[a["Name"]] = str(a.get("Value", ""))
    return out


def _attr(attrs: list | None, name: str) -> str:
    return _attr_map(attrs).get(name, "")


def _token_validity(d: dict, field: str, unit_key: str, default_unit: str) -> str | None:
    value = d.get(field)
    if value is None:
        return None
    units = (d.get("TokenValidityUnits") or {}).get(unit_key, default_unit)
    return f"{value} {units}"


def _yes_no(value: Any) -> str:
    return "yes" if value else "no"


def _join(values: Any, sep: str = ", ") -> str:
    if not values:
        return "—"
    if isinstance(values, list):
        return sep.join(str(v) for v in values) or "—"
    return str(values)


class CognitoService(ResourceService):
    key = "cognito"
    name = "Cognito"
    icon = "👤"

    def path_label(self, segment: str) -> str:
        return _DIR_LABELS.get(segment, segment)

    async def list_page(self, path: list[str]) -> Page:
        if not path:
            return Page(
                ["Section"],
                [
                    Item(
                        self.key,
                        POOLS_DIR,
                        "User Pools",
                        ("User Pools",),
                        kind="dir",
                        is_dir=True,
                        payload={},
                    ),
                    Item(
                        self.key,
                        IDENTITY_DIR,
                        "Identity Pools",
                        ("Identity Pools",),
                        kind="dir",
                        is_dir=True,
                        payload={},
                    ),
                ],
            )

        if path[0] == IDENTITY_DIR:
            return await self._list_identity_pools()

        if path[0] != POOLS_DIR:
            return Page(["Value"], [])

        if len(path) == 1:
            return await self._list_user_pools()

        pool_id = path[1]
        if len(path) == 2:
            return self._pool_hub(pool_id)

        section_id = path[2]
        if section_id == USERS_DIR:
            return await self._list_users(pool_id)
        if section_id == GROUPS_DIR:
            return await self._list_groups(pool_id)
        if section_id == CLIENTS_DIR:
            return await self._list_clients(pool_id)
        if section_id == PROVIDERS_DIR:
            return await self._list_providers(pool_id)
        if section_id == TRIGGERS_DIR:
            return await self._list_triggers(pool_id)
        return Page(["Value"], [])

    async def _list_user_pools(self) -> Page:
        resp = await self.exec.call("cognito-idp", "list_user_pools", MaxResults=60, ttl=60)
        items = [
            Item(
                self.key,
                p.get("Id", ""),
                p.get("Name", ""),
                (p.get("Name", ""), p.get("Id", ""), p.get("Status", "") or ""),
                kind="user_pool",
                is_dir=True,
                payload=p,
            )
            for p in resp.get("UserPools", [])
        ]
        return Page(["User pool", "ID", "Status"], items)

    def _pool_hub(self, pool_id: str) -> Page:
        base = {"UserPoolId": pool_id}
        return Page(
            ["Section", ""],
            [
                Item(
                    self.key,
                    pool_id,
                    "Overview",
                    ("Overview", "Pool configuration & policies"),
                    kind="user_pool",
                    is_dir=False,
                    payload={"Id": pool_id, **base},
                ),
                Item(
                    self.key,
                    USERS_DIR,
                    "Users",
                    ("Users", "List / search pool users"),
                    kind="dir",
                    is_dir=True,
                    payload=base,
                ),
                Item(
                    self.key,
                    GROUPS_DIR,
                    "Groups",
                    ("Groups", "Group membership & roles"),
                    kind="dir",
                    is_dir=True,
                    payload=base,
                ),
                Item(
                    self.key,
                    CLIENTS_DIR,
                    "App clients",
                    ("App clients", "OAuth / app credentials"),
                    kind="dir",
                    is_dir=True,
                    payload=base,
                ),
                Item(
                    self.key,
                    PROVIDERS_DIR,
                    "Identity providers",
                    ("Identity providers", "SAML / OIDC / social"),
                    kind="dir",
                    is_dir=True,
                    payload=base,
                ),
                Item(
                    self.key,
                    TRIGGERS_DIR,
                    "Triggers",
                    ("Triggers", "Lambda trigger configuration"),
                    kind="dir",
                    is_dir=True,
                    payload=base,
                ),
            ],
        )

    async def _list_users(self, pool_id: str) -> Page:
        resp = await self.exec.call(
            "cognito-idp", "list_users", UserPoolId=pool_id, Limit=60, ttl=30
        )
        items = []
        for u in resp.get("Users", []):
            attrs = u.get("Attributes") or []
            email = _attr(attrs, "email")
            items.append(
                Item(
                    self.key,
                    u.get("Username", ""),
                    u.get("Username", ""),
                    (
                        u.get("Username", ""),
                        u.get("UserStatus", "") or "",
                        email,
                        fmt_time(u.get("UserCreateDate")),
                    ),
                    kind="cognito_user",
                    payload={"UserPoolId": pool_id, **u},
                )
            )
        return Page(["Username", "Status", "Email", "Created"], items)

    async def _list_groups(self, pool_id: str) -> Page:
        resp = await self.exec.call(
            "cognito-idp", "list_groups", UserPoolId=pool_id, Limit=60, ttl=60
        )
        items = [
            Item(
                self.key,
                g.get("GroupName", ""),
                g.get("GroupName", ""),
                (
                    g.get("GroupName", ""),
                    truncate(g.get("Description", "") or "", 40),
                    str(g.get("Precedence", "")) if g.get("Precedence") is not None else "",
                ),
                kind="cognito_group",
                payload={"UserPoolId": pool_id, **g},
            )
            for g in resp.get("Groups", [])
        ]
        return Page(["Group", "Description", "Precedence"], items)

    async def _list_clients(self, pool_id: str) -> Page:
        resp = await self.exec.call(
            "cognito-idp",
            "list_user_pool_clients",
            UserPoolId=pool_id,
            MaxResults=60,
            ttl=60,
        )
        items = [
            Item(
                self.key,
                c.get("ClientId", ""),
                c.get("ClientName", "") or c.get("ClientId", ""),
                (c.get("ClientName", "") or "", c.get("ClientId", "") or ""),
                kind="cognito_client",
                payload={"UserPoolId": pool_id, **c},
            )
            for c in resp.get("UserPoolClients", [])
        ]
        return Page(["Client", "ID"], items)

    async def _list_providers(self, pool_id: str) -> Page:
        resp = await self.exec.call(
            "cognito-idp",
            "list_identity_providers",
            UserPoolId=pool_id,
            MaxResults=60,
            ttl=60,
        )
        items = [
            Item(
                self.key,
                p.get("ProviderName", ""),
                p.get("ProviderName", ""),
                (p.get("ProviderName", ""), p.get("ProviderType", "") or ""),
                kind="cognito_idp",
                payload={"UserPoolId": pool_id, **p},
            )
            for p in resp.get("Providers", [])
        ]
        return Page(["Provider", "Type"], items)

    async def _list_triggers(self, pool_id: str) -> Page:
        try:
            d = await self.exec.call(
                "cognito-idp", "describe_user_pool", UserPoolId=pool_id, ttl=60
            )
            cfg = d.get("UserPool", {}).get("LambdaConfig", {}) or {}
        except ClientError:
            cfg = {}
        items = []
        for trigger, value in cfg.items():
            fn = _lambda_trigger_label(value)
            arn = _lambda_trigger_arn(value)
            if not fn and not arn:
                continue
            items.append(
                Item(
                    self.key,
                    trigger,
                    trigger,
                    (trigger, fn or "—"),
                    kind="cognito_trigger",
                    payload={
                        "UserPoolId": pool_id,
                        "Trigger": trigger,
                        "Lambda": fn or "",
                        "LambdaArn": arn or "",
                        "Config": value,
                    },
                )
            )
        items.sort(key=lambda i: i.label.lower())
        return Page(["Trigger", "Lambda"], items)

    async def _list_identity_pools(self) -> Page:
        resp = await self.exec.call(
            "cognito-identity", "list_identity_pools", MaxResults=60, ttl=60
        )
        items = [
            Item(
                self.key,
                p.get("IdentityPoolId", ""),
                p.get("IdentityPoolName", ""),
                (p.get("IdentityPoolName", ""), p.get("IdentityPoolId", "") or ""),
                kind="identity_pool",
                is_dir=False,
                payload=p,
            )
            for p in resp.get("IdentityPools", [])
        ]
        return Page(["Identity pool", "ID"], items)

    async def detail(self, item: Item) -> dict:
        if item.kind == "user_pool":
            try:
                d = await self.exec.call(
                    "cognito-idp", "describe_user_pool", UserPoolId=item.id, ttl=60
                )
                return d.get("UserPool", d)
            except ClientError:
                return item.payload

        if item.kind == "cognito_user":
            pool_id = item.payload.get("UserPoolId", "")
            try:
                return await self.exec.call(
                    "cognito-idp",
                    "admin_get_user",
                    UserPoolId=pool_id,
                    Username=item.id,
                    ttl=30,
                )
            except ClientError:
                return item.payload

        if item.kind == "cognito_group":
            pool_id = item.payload.get("UserPoolId", "")
            try:
                d = await self.exec.call(
                    "cognito-idp",
                    "get_group",
                    UserPoolId=pool_id,
                    GroupName=item.id,
                    ttl=60,
                )
                return d.get("Group", d)
            except ClientError:
                return item.payload

        if item.kind == "cognito_client":
            pool_id = item.payload.get("UserPoolId", "")
            try:
                d = await self.exec.call(
                    "cognito-idp",
                    "describe_user_pool_client",
                    UserPoolId=pool_id,
                    ClientId=item.id,
                    ttl=60,
                )
                return d.get("UserPoolClient", d)
            except ClientError:
                return item.payload

        if item.kind == "cognito_idp":
            pool_id = item.payload.get("UserPoolId", "")
            try:
                d = await self.exec.call(
                    "cognito-idp",
                    "describe_identity_provider",
                    UserPoolId=pool_id,
                    ProviderName=item.id,
                    ttl=60,
                )
                return d.get("IdentityProvider", d)
            except ClientError:
                return item.payload

        if item.kind == "identity_pool":
            try:
                return await self.exec.call(
                    "cognito-identity",
                    "describe_identity_pool",
                    IdentityPoolId=item.id,
                    ttl=60,
                )
            except ClientError:
                return item.payload

        return item.payload

    def describe(self, item: Item, detail: Any) -> str:
        d = detail if isinstance(detail, dict) else {}
        if item.kind == "user_pool":
            triggers = d.get("LambdaConfig") or {}
            n_trig = sum(1 for v in triggers.values() if _lambda_trigger_label(v))
            return kv_block(
                [
                    ("Name", d.get("Name", item.label)),
                    ("ID", d.get("Id", item.id)),
                    ("Status", d.get("Status", "") or "—"),
                    ("Users (est.)", d.get("EstimatedNumberOfUsers", "") or "—"),
                    ("MFA", d.get("MfaConfiguration", "") or "—"),
                    ("Domain", d.get("Domain", "") or "—"),
                    ("Created", fmt_time(d.get("CreationDate"))),
                    ("Lambda triggers", str(n_trig) if n_trig else "none"),
                ]
            )
        if item.kind == "cognito_user":
            attrs = d.get("UserAttributes") or d.get("Attributes") or []
            return kv_block(
                [
                    ("Username", d.get("Username", item.label)),
                    ("Status", d.get("UserStatus", "") or "—"),
                    ("Enabled", _yes_no(d.get("Enabled", True))),
                    ("Email", _attr(attrs, "email") or "—"),
                    ("Email verified", _attr(attrs, "email_verified") or "—"),
                    ("Created", fmt_time(d.get("UserCreateDate"))),
                    ("Modified", fmt_time(d.get("UserLastModifiedDate"))),
                ]
            )
        if item.kind == "cognito_group":
            role = d.get("RoleArn", "") or ""
            return kv_block(
                [
                    ("Group", d.get("GroupName", item.label)),
                    (
                        "Precedence",
                        d.get("Precedence", "") if d.get("Precedence") is not None else "—",
                    ),
                    ("Role", truncate(role.split("/")[-1] if role else "—", 40)),
                    ("Description", truncate(d.get("Description", "") or "—", 50)),
                    ("Created", fmt_time(d.get("CreationDate"))),
                ]
            )
        if item.kind == "cognito_client":
            flows = d.get("ExplicitAuthFlows") or []
            return kv_block(
                [
                    ("Client", d.get("ClientName", item.label)),
                    ("ID", truncate(d.get("ClientId", item.id), 28)),
                    ("Auth flows", truncate(_join(flows), 50)),
                    ("Secret", "set" if d.get("ClientSecret") else "none"),
                    ("Created", fmt_time(d.get("CreationDate"))),
                ]
            )
        if item.kind == "cognito_idp":
            return kv_block(
                [
                    ("Provider", d.get("ProviderName", item.label)),
                    ("Type", d.get("ProviderType", "") or "—"),
                    ("Created", fmt_time(d.get("CreationDate"))),
                    ("Modified", fmt_time(d.get("LastModifiedDate"))),
                ]
            )
        if item.kind == "cognito_trigger":
            fn = d.get("Lambda") or _lambda_trigger_label(d.get("Config")) or "—"
            return kv_block(
                [
                    ("Trigger", d.get("Trigger", item.label)),
                    ("Lambda", fn),
                    ("Pool", d.get("UserPoolId", "") or "—"),
                ]
            )
        if item.kind == "identity_pool":
            return kv_block(
                [
                    ("Name", d.get("IdentityPoolName", item.label)),
                    ("ID", d.get("IdentityPoolId", item.id)),
                    (
                        "Unauth access",
                        _yes_no(d.get("AllowUnauthenticatedIdentities")),
                    ),
                ]
            )
        if item.kind == "dir":
            return kv_block([("Section", item.label)])
        return describe_fallback(d)

    def detail_body(self, item: Item, detail: Any) -> str:
        d = detail if isinstance(detail, dict) else {}
        if item.kind == "user_pool":
            return self._user_pool_body(item, d)
        if item.kind == "cognito_user":
            return self._user_body(item, d)
        if item.kind == "cognito_group":
            return self._group_body(item, d)
        if item.kind == "cognito_client":
            return self._client_body(item, d)
        if item.kind == "cognito_idp":
            return self._idp_body(item, d)
        if item.kind == "cognito_trigger":
            return self._trigger_body(item, d)
        if item.kind == "identity_pool":
            return self._identity_pool_body(item, d)
        return detail_fallback(d)

    def _user_pool_body(self, item: Item, d: dict) -> str:
        pwd = d.get("Policies", {}).get("PasswordPolicy") or {}
        recovery = d.get("AccountRecoverySetting", {}).get("RecoveryMechanisms") or []
        schema = d.get("SchemaAttributes") or []
        auto_verified = d.get("AutoVerifiedAttributes") or []
        username_attrs = d.get("UsernameAttributes") or []
        alias_attrs = d.get("AliasAttributes") or []

        parts = [
            kv_block(
                [
                    ("Name", d.get("Name", item.label)),
                    ("ID", d.get("Id", item.id)),
                    ("ARN", d.get("Arn", "") or "—"),
                    ("Status", d.get("Status", "") or "—"),
                    ("Created", fmt_time(d.get("CreationDate"))),
                    ("Last modified", fmt_time(d.get("LastModifiedDate"))),
                    ("Estimated users", d.get("EstimatedNumberOfUsers", "") or "—"),
                    ("MFA", d.get("MfaConfiguration", "") or "—"),
                    ("Domain", d.get("Domain", "") or "—"),
                    ("Custom domain", d.get("CustomDomain", "") or None),
                    ("Deletion protection", d.get("DeletionProtection", "") or "—"),
                ]
            ),
            section("Sign-in"),
            kv_block(
                [
                    ("Username attrs", _join(username_attrs)),
                    ("Alias attrs", _join(alias_attrs)),
                    ("Auto-verified", _join(auto_verified)),
                    (
                        "Recovery",
                        _join(
                            [
                                f"{m.get('Name')} (p{m.get('Priority')})"
                                for m in recovery
                                if isinstance(m, dict)
                            ]
                        ),
                    ),
                ]
            ),
            section("Password policy"),
            kv_block(
                [
                    ("Min length", pwd.get("MinimumLength", "") or "—"),
                    ("Uppercase", _yes_no(pwd.get("RequireUppercase"))),
                    ("Lowercase", _yes_no(pwd.get("RequireLowercase"))),
                    ("Numbers", _yes_no(pwd.get("RequireNumbers"))),
                    ("Symbols", _yes_no(pwd.get("RequireSymbols"))),
                    (
                        "Temp validity",
                        f"{pwd['TemporaryPasswordValidityDays']}d"
                        if pwd.get("TemporaryPasswordValidityDays") is not None
                        else None,
                    ),
                ]
            ),
        ]

        triggers = d.get("LambdaConfig") or {}
        trig_rows = [(k, label) for k, v in triggers.items() if (label := _lambda_trigger_label(v))]
        if trig_rows:
            parts.append(section("Lambda triggers"))
            parts.append(kv_block(trig_rows))

        required = [
            a.get("Name", "")
            for a in schema
            if isinstance(a, dict) and a.get("Required") and a.get("Name")
        ]
        custom = [
            a.get("Name", "")
            for a in schema
            if isinstance(a, dict) and str(a.get("Name", "")).startswith("custom:")
        ]
        if required or custom:
            parts.append(section("Schema"))
            parts.append(
                kv_block(
                    [
                        ("Required attrs", truncate(_join(required), 80)),
                        ("Custom attrs", truncate(_join(custom), 80) if custom else "—"),
                        ("Total attributes", len(schema)),
                    ]
                )
            )
        return "\n".join(parts)

    def _user_body(self, item: Item, d: dict) -> str:
        attrs = d.get("UserAttributes") or d.get("Attributes") or []
        amap = _attr_map(attrs)
        parts = [
            kv_block(
                [
                    ("Username", d.get("Username", item.label)),
                    ("Status", d.get("UserStatus", "") or "—"),
                    ("Enabled", _yes_no(d.get("Enabled", True))),
                    ("Created", fmt_time(d.get("UserCreateDate"))),
                    ("Modified", fmt_time(d.get("UserLastModifiedDate"))),
                    (
                        "MFA options",
                        _join(
                            [
                                m.get("AttributeName")
                                for m in (d.get("MFAOptions") or [])
                                if isinstance(m, dict)
                            ]
                        ),
                    ),
                    ("Preferred MFA", d.get("PreferredMfaSetting") or "—"),
                    ("MFA settings", _join(d.get("UserMFASettingList"))),
                ]
            )
        ]
        if amap:
            parts.append(section("Attributes"))
            parts.append(kv_block([(k, v or "—") for k, v in sorted(amap.items())]))
        return "\n".join(parts)

    def _group_body(self, item: Item, d: dict) -> str:
        return kv_block(
            [
                ("Group", d.get("GroupName", item.label)),
                ("Description", d.get("Description", "") or "—"),
                (
                    "Precedence",
                    d.get("Precedence", "") if d.get("Precedence") is not None else "—",
                ),
                ("Role ARN", d.get("RoleArn", "") or "—"),
                ("Created", fmt_time(d.get("CreationDate"))),
                ("Modified", fmt_time(d.get("LastModifiedDate"))),
                ("Pool", d.get("UserPoolId", item.payload.get("UserPoolId", "")) or "—"),
            ]
        )

    def _client_body(self, item: Item, d: dict) -> str:
        parts = [
            kv_block(
                [
                    ("Client", d.get("ClientName", item.label)),
                    ("Client ID", d.get("ClientId", item.id)),
                    ("Pool", d.get("UserPoolId", "") or "—"),
                    ("Secret", "set (hidden)" if d.get("ClientSecret") else "none"),
                    ("Created", fmt_time(d.get("CreationDate"))),
                    ("Modified", fmt_time(d.get("LastModifiedDate"))),
                    (
                        "Refresh token",
                        _token_validity(d, "RefreshTokenValidity", "RefreshToken", "days"),
                    ),
                    (
                        "Access token",
                        _token_validity(d, "AccessTokenValidity", "AccessToken", "minutes"),
                    ),
                    (
                        "ID token",
                        _token_validity(d, "IdTokenValidity", "IdToken", "minutes"),
                    ),
                    (
                        "Auth session",
                        f"{d['AuthSessionValidity']} min"
                        if d.get("AuthSessionValidity") is not None
                        else None,
                    ),
                ]
            ),
            section("Auth"),
            kv_block(
                [
                    ("Explicit flows", _join(d.get("ExplicitAuthFlows"))),
                    ("OAuth flows", _join(d.get("AllowedOAuthFlows"))),
                    ("OAuth scopes", _join(d.get("AllowedOAuthScopes"))),
                    ("OAuth code grant", _yes_no(d.get("AllowedOAuthFlowsUserPoolClient"))),
                    ("Supported IdPs", _join(d.get("SupportedIdentityProviders"))),
                    ("Prevent user existence", d.get("PreventUserExistenceErrors", "") or "—"),
                    ("Token revocation", _yes_no(d.get("EnableTokenRevocation"))),
                    (
                        "Propagate user context",
                        _yes_no(d.get("EnablePropagateAdditionalUserContextData")),
                    ),
                ]
            ),
        ]
        callbacks = d.get("CallbackURLs") or []
        logouts = d.get("LogoutURLs") or []
        if callbacks or logouts or d.get("DefaultRedirectURI"):
            parts.append(section("URLs"))
            rows = [("Default redirect", d.get("DefaultRedirectURI") or None)]
            for i, url in enumerate(callbacks, 1):
                rows.append((f"Callback {i}", url))
            for i, url in enumerate(logouts, 1):
                rows.append((f"Logout {i}", url))
            parts.append(kv_block(rows))

        read_attrs = d.get("ReadAttributes") or []
        write_attrs = d.get("WriteAttributes") or []
        if read_attrs or write_attrs:
            parts.append(section("Attribute access"))
            parts.append(
                kv_block(
                    [
                        ("Read", truncate(_join(read_attrs), 100)),
                        ("Write", truncate(_join(write_attrs), 100)),
                    ]
                )
            )
        return "\n".join(parts)

    def _idp_body(self, item: Item, d: dict) -> str:
        details = d.get("ProviderDetails") or {}
        mapping = d.get("AttributeMapping") or {}
        idp_ids = d.get("IdpIdentifiers") or []
        parts = [
            kv_block(
                [
                    ("Provider", d.get("ProviderName", item.label)),
                    ("Type", d.get("ProviderType", "") or "—"),
                    ("Pool", d.get("UserPoolId", "") or "—"),
                    ("Identifiers", _join(idp_ids)),
                    ("Created", fmt_time(d.get("CreationDate"))),
                    ("Modified", fmt_time(d.get("LastModifiedDate"))),
                ]
            )
        ]
        # Hide secrets from provider details.
        if details:
            safe = {
                k: ("••••" if "secret" in k.lower() or "key" in k.lower() else v)
                for k, v in details.items()
            }
            parts.append(section("Provider details"))
            parts.append(kv_block([(k, truncate(str(v), 80)) for k, v in sorted(safe.items())]))
        if mapping:
            parts.append(section("Attribute mapping"))
            parts.append(kv_block([(k, v) for k, v in sorted(mapping.items())]))
        return "\n".join(parts)

    def _trigger_body(self, item: Item, d: dict) -> str:
        cfg = d.get("Config")
        arn = d.get("LambdaArn") or _lambda_trigger_arn(cfg) or "—"
        fn = d.get("Lambda") or _lambda_trigger_label(cfg) or "—"
        rows: list[tuple[str, Any]] = [
            ("Trigger", d.get("Trigger", item.label)),
            ("Lambda", fn),
            ("ARN", arn),
            ("Pool", d.get("UserPoolId", "") or "—"),
        ]
        if isinstance(cfg, dict):
            for k, v in sorted(cfg.items()):
                if k == "LambdaArn":
                    continue
                rows.append((k, truncate(str(v), 80)))
        return kv_block(rows)

    def _identity_pool_body(self, item: Item, d: dict) -> str:
        parts = [
            kv_block(
                [
                    ("Name", d.get("IdentityPoolName", item.label)),
                    ("ID", d.get("IdentityPoolId", item.id)),
                    (
                        "Unauth access",
                        _yes_no(d.get("AllowUnauthenticatedIdentities")),
                    ),
                    ("Classic flow", _yes_no(d.get("AllowClassicFlow"))),
                    ("Auth role", (d.get("Roles") or {}).get("authenticated", "") or "—"),
                    ("Unauth role", (d.get("Roles") or {}).get("unauthenticated", "") or "—"),
                ]
            )
        ]
        mappings = d.get("RoleMappings") or {}
        if mappings:
            parts.append(section("Role mappings"))
            for key, m in mappings.items():
                if not isinstance(m, dict):
                    continue
                parts.append(
                    kv_block(
                        [
                            ("Provider", key),
                            ("Type", m.get("Type", "") or "—"),
                            ("Role ARN", m.get("RoleArn", "") or "—"),
                            ("Ambiguous role", m.get("AmbiguousRoleResolution", "") or None),
                        ]
                    )
                )
        return "\n".join(parts)

    async def links(self, item: Item) -> list[Link]:
        out: list[Link] = []
        if item.kind == "user_pool":
            # Quick jumps into this pool's sections (triggers live under their own section).
            for seg, title in (
                (USERS_DIR, "Users"),
                (GROUPS_DIR, "Groups"),
                (CLIENTS_DIR, "App clients"),
                (PROVIDERS_DIR, "Identity providers"),
                (TRIGGERS_DIR, "Triggers"),
            ):
                out.append(
                    Link(
                        "cognito",
                        title,
                        [POOLS_DIR, item.id, seg],
                        "",
                        kind="dir",
                    )
                )

        if item.kind == "cognito_trigger":
            fn = item.payload.get("Lambda") or _lambda_trigger_label(item.payload.get("Config"))
            if fn:
                out.append(Link("lambda", f"Lambda: {fn}", [], fn, kind="lambda"))

        if item.kind == "cognito_user":
            pool_id = item.payload.get("UserPoolId", "")
            try:
                resp = await self.exec.call(
                    "cognito-idp",
                    "admin_list_groups_for_user",
                    UserPoolId=pool_id,
                    Username=item.id,
                    Limit=60,
                    ttl=30,
                )
            except ClientError:
                resp = {}
            for g in resp.get("Groups", []):
                name = g.get("GroupName", "")
                if name:
                    out.append(
                        Link(
                            "cognito",
                            f"Group: {name}",
                            [POOLS_DIR, pool_id, GROUPS_DIR],
                            name,
                            kind="cognito_group",
                        )
                    )

        if item.kind == "cognito_group":
            role_arn = item.payload.get("RoleArn") or ""
            if role_arn:
                role_name = role_arn.split("/")[-1]
                out.append(Link("iam", f"Role: {role_name}", ["__roles"], role_name, kind="role"))

        if item.kind == "identity_pool":
            try:
                d = await self.exec.call(
                    "cognito-identity",
                    "describe_identity_pool",
                    IdentityPoolId=item.id,
                    ttl=60,
                )
            except ClientError:
                d = item.payload if isinstance(item.payload, dict) else {}
            roles = d.get("Roles") or {}
            for kind_label, arn in roles.items():
                if arn:
                    role_name = str(arn).split("/")[-1]
                    out.append(
                        Link(
                            "iam",
                            f"Role: {role_name} ({kind_label})",
                            ["__roles"],
                            role_name,
                            kind="role",
                        )
                    )
            for key, m in (d.get("RoleMappings") or {}).items():
                if not isinstance(m, dict):
                    continue
                role_arn = m.get("RoleArn")
                if role_arn:
                    role_name = role_arn.split("/")[-1]
                    out.append(
                        Link(
                            "iam",
                            f"Role: {role_name} ({key})",
                            ["__roles"],
                            role_name,
                            kind="role",
                        )
                    )
        return out
