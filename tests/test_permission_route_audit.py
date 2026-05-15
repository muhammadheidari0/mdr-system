from __future__ import annotations

import re
from pathlib import Path

from app.core.permission_catalog import permission_keys


ROUTERS_DIR = Path("app/api/v1/routers")

ROUTE_DECORATOR_RE = re.compile(
    r"""@router\.(get|post|put|delete|patch)\(\s*["'](?P<path>[^"']+)["']""",
    re.MULTILINE,
)
ROUTER_RE = re.compile(r"router\s*=\s*APIRouter\((?P<body>[\s\S]*?)\)\s*\n")
DEF_RE = re.compile(r"^def\s+\w+\s*\(", re.MULTILINE)
REQUIRE_PERMISSION_RE = re.compile(r"""require_permission\(\s*["'](?P<key>[^"']+)["']\s*\)""")
INLINE_REQUIRE_PERMISSION_RE = re.compile(
    r"""_require_permission\([^\n]*?["'](?P<key>[^"']+)["']"""
)

PUBLIC_OR_TOKEN_ROUTE_WHITELIST = {
    "/api/v1/auth/login",
    "/api/v1/auth/logout",
    "/api/v1/auth/me",
    "/api/v1/auth/navigation",
    "/api/v1/auth/change-password",
    "/api/v1/init",
    "/api/v1/health",
    "/api/v1/healthz",
    "/api/v1/mdr/bulk-register-page",
    "/api/v1/storage/openproject/import/template",
    "/api/v1/storage/site-manifest",
    "/api/v1/storage/site-agent/download/{file_id}",
    "/api/v1/storage/site-agent/heartbeat",
}


def _router_prefix(text: str) -> str:
    match = ROUTER_RE.search(text)
    if not match:
        return ""
    body = match.group("body")
    prefix_match = re.search(r"""prefix\s*=\s*["']([^"']+)["']""", body)
    return str(prefix_match.group(1) if prefix_match else "")


def _router_has_permission_dependency(text: str) -> bool:
    match = ROUTER_RE.search(text)
    if not match:
        return False
    body = match.group("body")
    return "Depends(require_permission(" in body


def _iter_route_blocks(text: str):
    matches = list(ROUTE_DECORATOR_RE.finditer(text))
    for idx, match in enumerate(matches):
        route_path = str(match.group("path") or "")
        block_start = match.start()

        def_match = DEF_RE.search(text, match.end())
        if not def_match:
            continue
        next_block_start = matches[idx + 1].start() if idx + 1 < len(matches) else len(text)
        block = text[block_start:next_block_start]
        yield route_path, block


def _full_path(prefix: str, route_path: str) -> str:
    return f"/api/v1{prefix}{route_path}".replace("//", "/")


def test_operational_routes_enforce_permission_or_whitelist() -> None:
    violations: list[str] = []

    for path in sorted(ROUTERS_DIR.glob("*.py")):
        text = path.read_text(encoding="utf-8", errors="ignore")
        prefix = _router_prefix(text)
        router_level_permission = _router_has_permission_dependency(text)

        for route_path, block in _iter_route_blocks(text):
            full_path = _full_path(prefix, route_path)
            has_permission_dependency = "Depends(require_permission(" in block
            has_inline_permission = "_require_permission(" in block
            whitelisted = full_path in PUBLIC_OR_TOKEN_ROUTE_WHITELIST

            if router_level_permission or has_permission_dependency or has_inline_permission or whitelisted:
                continue
            violations.append(f"{path}:{full_path}")

    assert not violations, (
        "Found API routes without explicit permission enforcement and not in whitelist:\n"
        + "\n".join(violations)
    )


def test_all_route_permission_keys_exist_in_catalog() -> None:
    route_keys: set[str] = set()
    known_keys = set(permission_keys())

    for path in sorted(ROUTERS_DIR.glob("*.py")):
        text = path.read_text(encoding="utf-8", errors="ignore")
        route_keys.update(match.group("key") for match in REQUIRE_PERMISSION_RE.finditer(text))
        route_keys.update(match.group("key") for match in INLINE_REQUIRE_PERMISSION_RE.finditer(text))

    missing = sorted(key for key in route_keys if key not in known_keys)
    assert not missing, f"Permission keys used by routes but missing from catalog: {missing}"


def test_settings_organization_routes_use_organization_permissions() -> None:
    settings_path = ROUTERS_DIR / "settings.py"
    text = settings_path.read_text(encoding="utf-8", errors="ignore")

    expected = {
        "/organizations": 'require_permission("organizations:read")',
        "/organizations/upsert": 'require_permission("organizations:manage")',
        "/organizations/delete": 'require_permission("organizations:manage")',
    }

    route_blocks = dict(_iter_route_blocks(text))
    missing_routes = [route for route in expected if route not in route_blocks]
    assert not missing_routes, f"Expected settings organization routes were not found: {missing_routes}"

    violations: list[str] = []
    for route_path, permission_call in expected.items():
        block = route_blocks.get(route_path, "")
        if permission_call not in block:
            violations.append(f"{settings_path}:{route_path} missing {permission_call}")

    assert not violations, "Organization routes must use organizations:* permissions:\n" + "\n".join(violations)


def test_settings_site_log_catalog_routes_use_expected_permissions() -> None:
    settings_path = ROUTERS_DIR / "settings.py"
    text = settings_path.read_text(encoding="utf-8", errors="ignore")

    expected = {
        "/site-log-catalogs/upsert": 'require_permission("settings:update")',
        "/site-log-catalogs/delete": 'require_permission("settings:update")',
    }

    route_blocks = dict(_iter_route_blocks(text))
    missing_routes = [route for route in expected if route not in route_blocks]
    assert not missing_routes, f"Expected settings site-log catalog routes were not found: {missing_routes}"

    violations: list[str] = []
    for route_path, permission_call in expected.items():
        block = route_blocks.get(route_path, "")
        if permission_call not in block:
            violations.append(f"{settings_path}:{route_path} missing {permission_call}")

    assert not violations, "Site-log catalog routes must use settings:update:\n" + "\n".join(violations)
