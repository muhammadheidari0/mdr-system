from __future__ import annotations

from typing import Mapping

from app.core.organizations import DEFAULT_PERMISSION_CATEGORY, OrganizationType, normalize_permission_category
from app.core.permission_catalog import permission_keys
from app.core.roles import MATRIX_ROLES, ROLE_PERMISSIONS, Role


CANONICAL_PERMISSION_CATEGORIES: tuple[str, ...] = (
    OrganizationType.CONSULTANT.value,
    OrganizationType.CONTRACTOR.value,
    OrganizationType.EMPLOYER.value,
    OrganizationType.DCC.value,
)
CANONICAL_MATRIX_ROLES: tuple[str, ...] = MATRIX_ROLES

EDMS_TAB_RULES: dict[str, tuple[str, ...]] = {
    "archive": ("module_archive:read", "archive:read"),
    "transmittal": ("module_transmittal:read", "transmittal:read"),
    "correspondence": ("module_correspondence:read", "correspondence:read"),
    "meeting_minutes": ("module_meeting_minutes:read", "meeting_minutes:read"),
    "forms": ("module_edms_forms:read", "edms_forms:read"),
}
REPORTS_MODULE_RULES: dict[str, tuple[str, ...]] = {
    "overview": ("module_reports:read", "reports:read"),
}
CONTRACTOR_TAB_RULES: dict[str, tuple[str, ...]] = {
    "execution": ("module_site_logs_contractor:read", "site_logs:read"),
    "requests": ("module_comm_items_contractor:read", "comm_items:read"),
    "permit_qc": ("module_permit_qc_contractor:read", "permit_qc:read"),
}
CONSULTANT_TAB_RULES: dict[str, tuple[str, ...]] = {
    "inspection": ("module_site_logs_consultant:read", "site_logs:read"),
    "defects": ("module_comm_items_consultant:read", "comm_items:read"),
    "instructions": ("module_work_instructions_consultant:read", "work_instructions:read"),
    "control": ("module_site_logs_consultant:read", "project_control:view"),
    "permit_qc": ("module_permit_qc_consultant:read", "permit_qc:read"),
}

DEFAULT_HUB_BY_CATEGORY: dict[str, str] = {
    OrganizationType.CONSULTANT.value: "consultant",
    OrganizationType.CONTRACTOR.value: "contractor",
    OrganizationType.EMPLOYER.value: "reports",
    OrganizationType.DCC.value: "edms",
    OrganizationType.SYSTEM.value: "dashboard",
}
DEFAULT_EDMS_TAB_BY_ROLE: dict[str, str] = {
    Role.ADMIN.value: "archive",
    Role.DCC.value: "transmittal",
    Role.MANAGER.value: "transmittal",
    Role.PROJECT_CONTROL.value: "archive",
    Role.USER.value: "archive",
    Role.VIEWER.value: "archive",
}
ALLOWED_HUBS_BY_CATEGORY: dict[str, tuple[str, ...]] = {
    OrganizationType.CONSULTANT.value: ("dashboard", "consultant", "reports"),
    OrganizationType.CONTRACTOR.value: ("dashboard", "contractor", "reports"),
    OrganizationType.EMPLOYER.value: ("dashboard", "reports", "edms"),
    OrganizationType.DCC.value: ("dashboard", "edms", "reports", "contractor", "consultant"),
    OrganizationType.SYSTEM.value: ("dashboard", "edms", "reports", "contractor", "consultant"),
}


def canonical_permission_count() -> int:
    return len(permission_keys())


def module_visible_rule(capabilities: Mapping[str, bool], *required_keys: str) -> bool:
    keys = [str(key or "").strip() for key in required_keys if str(key or "").strip()]
    if not keys:
        return False
    return all(bool(capabilities.get(key, False)) for key in keys)


def hub_visible_rule(capabilities: Mapping[str, bool], hub_read_key: str, child_visibility: Mapping[str, bool]) -> bool:
    return bool(capabilities.get(hub_read_key, False)) and any(bool(value) for value in child_visibility.values())


def contractor_tab_rules() -> dict[str, tuple[str, ...]]:
    return dict(CONTRACTOR_TAB_RULES)


def consultant_tab_rules() -> dict[str, tuple[str, ...]]:
    return dict(CONSULTANT_TAB_RULES)


def build_navigation_diagnostics(
    navigation: Mapping[str, object],
    *,
    category: str,
) -> dict[str, object]:
    normalized_category = normalize_permission_category(category)
    hubs = navigation.get("hubs", {}) if isinstance(navigation, Mapping) else {}
    hub_map = hubs if isinstance(hubs, Mapping) else {}
    visible_hubs = sorted(key for key, visible in hub_map.items() if bool(visible))
    hidden_hubs = sorted(key for key, visible in hub_map.items() if not bool(visible))
    allowed_hubs = set(ALLOWED_HUBS_BY_CATEGORY.get(normalized_category, ("dashboard",)))
    unexpected_visible_hubs = sorted(hub for hub in visible_hubs if hub not in allowed_hubs)
    warnings: list[str] = []

    default_hub = str(navigation.get("default_hub") or "").strip().lower() if isinstance(navigation, Mapping) else ""
    if default_hub and default_hub not in visible_hubs:
        warnings.append(f"default_hub:{default_hub}:hidden")

    expected_primary_hub = DEFAULT_HUB_BY_CATEGORY.get(normalized_category)
    if expected_primary_hub and expected_primary_hub != "dashboard" and expected_primary_hub not in visible_hubs:
        warnings.append(f"expected_primary_hub_missing:{expected_primary_hub}")

    for hub in unexpected_visible_hubs:
        warnings.append(f"unexpected_visible_hub:{hub}")

    return {
        "visible_hubs": visible_hubs,
        "hidden_hubs": hidden_hubs,
        "unexpected_visible_hubs": unexpected_visible_hubs,
        "warnings": warnings,
    }


def _normalize_category(category: str | None) -> str:
    normalized = normalize_permission_category(category)
    if normalized in CANONICAL_PERMISSION_CATEGORIES:
        return normalized
    return DEFAULT_PERMISSION_CATEGORY


def _base_allowed_permissions(role: str) -> set[str]:
    role_key = str(role or "").strip().lower()
    try:
        role_enum = Role(role_key)
    except Exception:
        return set()
    return {str(item) for item in (ROLE_PERMISSIONS.get(role_enum, []) or []) if str(item or "").strip()}


def _disable(row: dict[str, bool], *keys: str) -> None:
    for key in keys:
        if key in row:
            row[key] = False


def _enable(row: dict[str, bool], *keys: str) -> None:
    for key in keys:
        if key in row:
            row[key] = True


def default_permission_row_for_category(category: str, role: str) -> dict[str, bool]:
    normalized_category = _normalize_category(category)
    allowed = _base_allowed_permissions(role)
    has_wildcard = "*" in allowed
    row = {
        perm: (has_wildcard or perm in allowed)
        for perm in permission_keys()
    }

    edms_keys = (
        "hub_edms:read",
        "module_archive:read",
        "module_transmittal:read",
        "module_correspondence:read",
        "module_meeting_minutes:read",
        "module_edms_forms:read",
        "module_settings_edms:read",
    )
    contractor_keys = (
        "hub_contractor:read",
        "module_site_logs_contractor:read",
        "module_comm_items_contractor:read",
        "module_permit_qc_contractor:read",
        "module_settings_contractor:read",
    )
    consultant_keys = (
        "hub_consultant:read",
        "module_site_logs_consultant:read",
        "module_comm_items_consultant:read",
        "module_work_instructions_consultant:read",
        "module_permit_qc_consultant:read",
        "module_settings_consultant:read",
    )

    if normalized_category == OrganizationType.CONSULTANT.value:
        _disable(row, *edms_keys, *contractor_keys)
        _enable(row, "hub_consultant:read")
    elif normalized_category == OrganizationType.CONTRACTOR.value:
        _disable(row, *edms_keys, *consultant_keys)
        _enable(row, "hub_contractor:read")
    elif normalized_category == OrganizationType.EMPLOYER.value:
        _disable(row, *edms_keys, *contractor_keys, *consultant_keys)
        _enable(row, "hub_reports:read", "module_reports:read", "reports:read")
    elif normalized_category == OrganizationType.DCC.value:
        _disable(row, *contractor_keys, *consultant_keys)
        _enable(
            row,
            "hub_edms:read",
            "module_archive:read",
            "module_transmittal:read",
            "module_correspondence:read",
            "module_meeting_minutes:read",
            "module_edms_forms:read",
        )

    return row


def default_permission_matrix_for_category(category: str | None) -> dict[str, dict[str, bool]]:
    normalized_category = _normalize_category(category)
    return {
        role: default_permission_row_for_category(normalized_category, role)
        for role in CANONICAL_MATRIX_ROLES
    }


def build_navigation_state(
    capabilities: Mapping[str, bool],
    *,
    category: str,
    effective_role: str,
) -> dict[str, object]:
    edms_tabs = {
        key: module_visible_rule(capabilities, *required_keys)
        for key, required_keys in EDMS_TAB_RULES.items()
    }
    reports_modules = {
        key: module_visible_rule(capabilities, *required_keys)
        for key, required_keys in REPORTS_MODULE_RULES.items()
    }
    contractor_tabs = {
        key: module_visible_rule(capabilities, *required_keys)
        for key, required_keys in CONTRACTOR_TAB_RULES.items()
    }
    consultant_tabs = {
        key: module_visible_rule(capabilities, *required_keys)
        for key, required_keys in CONSULTANT_TAB_RULES.items()
    }

    module_settings_visibility = {
        "edms": module_visible_rule(capabilities, "module_settings_edms:read", "settings:read"),
        "contractor": module_visible_rule(capabilities, "module_settings_contractor:read", "settings:read"),
        "consultant": module_visible_rule(capabilities, "module_settings_consultant:read", "settings:read"),
    }

    modules = {
        "edms": dict(edms_tabs),
        "reports": dict(reports_modules),
        "contractor": dict(contractor_tabs),
        "consultant": dict(consultant_tabs),
        "settings": {
            "module_settings": any(bool(value) for value in module_settings_visibility.values()),
            **module_settings_visibility,
        },
    }
    hubs = {
        "dashboard": bool(capabilities.get("dashboard:read", False)),
        "edms": hub_visible_rule(capabilities, "hub_edms:read", edms_tabs),
        "reports": hub_visible_rule(capabilities, "hub_reports:read", reports_modules),
        "contractor": hub_visible_rule(capabilities, "hub_contractor:read", contractor_tabs),
        "consultant": hub_visible_rule(capabilities, "hub_consultant:read", consultant_tabs),
    }

    normalized_category = normalize_permission_category(category)
    default_hub = DEFAULT_HUB_BY_CATEGORY.get(normalized_category, "dashboard")
    if not hubs.get(default_hub):
        default_hub = next(
            (hub for hub in ("dashboard", "edms", "reports", "contractor", "consultant") if hubs.get(hub)),
            "dashboard",
        )

    default_edms_tab = DEFAULT_EDMS_TAB_BY_ROLE.get(str(effective_role or "").strip().lower(), "archive")
    if not edms_tabs.get(default_edms_tab):
        default_edms_tab = next((tab for tab, visible in edms_tabs.items() if visible), "archive")

    return {
        "modules": modules,
        "hubs": hubs,
        "contractor_tabs": contractor_tabs,
        "consultant_tabs": consultant_tabs,
        "edms_tabs": edms_tabs,
        "default_hub": default_hub,
        "default_edms_tab": default_edms_tab,
        "module_settings_visibility": module_settings_visibility,
    }
