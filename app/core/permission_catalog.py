from __future__ import annotations

from dataclasses import dataclass
from functools import lru_cache
from typing import Any

from app.core.roles import ROLE_PERMISSIONS


SYSTEM_PERMISSION_KEYS: tuple[str, ...] = (
    "settings:read",
    "settings:update",
    "permissions:read",
    "permissions:update",
    "permissions:audit_read",
    "users:read",
    "users:create",
    "users:update",
    "users:delete",
    "organizations:read",
    "organizations:manage",
    "lookup:read",
    "lookup:manage",
    "storage:read",
    "storage:update",
    "storage:sync_manage",
    "site_cache:read",
    "site_cache:manage",
    "integrations:read",
    "integrations:update",
)

CATEGORY_ALL: tuple[str, ...] = ("consultant", "contractor", "employer", "dcc")
CATEGORY_CONSULTANT: tuple[str, ...] = ("consultant", "dcc")
CATEGORY_CONTRACTOR: tuple[str, ...] = ("contractor", "dcc")
CATEGORY_EDMS: tuple[str, ...] = ("employer", "dcc")


@dataclass(frozen=True)
class PageMeta:
    key: str
    label_fa: str
    section_key: str
    section_label: str
    category_relevance: tuple[str, ...] = CATEGORY_ALL


PAGE_META: dict[str, PageMeta] = {
    "dashboard": PageMeta("dashboard", "کارتابل", "reports_dash", "گزارش و داشبورد"),
    "reports": PageMeta("reports", "گزارش‌ها", "reports_dash", "گزارش و داشبورد"),
    "archive": PageMeta("archive", "آرشیو مدارک", "edms", "مدیریت مدارک مهندسی", CATEGORY_EDMS),
    "transmittal": PageMeta("transmittal", "ترنسمیتال", "edms", "مدیریت مدارک مهندسی", CATEGORY_EDMS),
    "correspondence": PageMeta("correspondence", "مکاتبات", "edms", "مدیریت مدارک مهندسی", CATEGORY_EDMS),
    "meeting_minutes": PageMeta("meeting_minutes", "صورتجلسات", "edms", "مدیریت مدارک مهندسی", CATEGORY_EDMS),
    "edms_forms": PageMeta("edms_forms", "فرم‌ها", "edms", "مدیریت مدارک مهندسی", CATEGORY_EDMS),
    "site_logs_contractor": PageMeta("site_logs_contractor", "گزارش کارگاهی", "contractor", "فرم‌ها و اجرا (پیمانکار)", CATEGORY_CONTRACTOR),
    "comm_items_contractor": PageMeta("comm_items_contractor", "درخواست‌ها", "contractor", "فرم‌ها و اجرا (پیمانکار)", CATEGORY_CONTRACTOR),
    "permit_qc_contractor": PageMeta("permit_qc_contractor", "Permit + QC", "contractor", "فرم‌ها و اجرا (پیمانکار)", CATEGORY_CONTRACTOR),
    "site_logs_consultant": PageMeta("site_logs_consultant", "بازدید و چک‌لیست", "consultant", "نظارت و کنترل پروژه (مشاور)", CATEGORY_CONSULTANT),
    "comm_items_consultant": PageMeta("comm_items_consultant", "نواقص و درخواست‌ها", "consultant", "نظارت و کنترل پروژه (مشاور)", CATEGORY_CONSULTANT),
    "work_instructions_consultant": PageMeta("work_instructions_consultant", "دستورکار", "consultant", "نظارت و کنترل پروژه (مشاور)", CATEGORY_CONSULTANT),
    "permit_qc_consultant": PageMeta("permit_qc_consultant", "Permit + QC", "consultant", "نظارت و کنترل پروژه (مشاور)", CATEGORY_CONSULTANT),
    "bim": PageMeta("bim", "BIM / Revit", "consultant", "نظارت و کنترل پروژه (مشاور)", CATEGORY_CONSULTANT),
    "edms_settings": PageMeta("edms_settings", "تنظیمات داخلی مدیریت مدارک مهندسی", "edms", "مدیریت مدارک مهندسی", CATEGORY_EDMS),
    "contractor_settings": PageMeta("contractor_settings", "تنظیمات داخلی فرم‌ها و اجرا", "contractor", "فرم‌ها و اجرا (پیمانکار)", CATEGORY_CONTRACTOR),
    "consultant_settings": PageMeta("consultant_settings", "تنظیمات داخلی نظارت و کنترل پروژه", "consultant", "نظارت و کنترل پروژه (مشاور)", CATEGORY_CONSULTANT),
    "users": PageMeta("users", "مدیریت کاربران", "admin", "مدیریت و تنظیمات"),
    "permissions": PageMeta("permissions", "سطح دسترسی", "admin", "مدیریت و تنظیمات"),
    "organizations": PageMeta("organizations", "مدیریت سازمان‌ها", "admin", "مدیریت و تنظیمات"),
    "settings": PageMeta("settings", "تنظیمات سیستم", "admin", "مدیریت و تنظیمات"),
    "lookup": PageMeta("lookup", "فهرست‌های پایه", "admin", "مدیریت و تنظیمات"),
    "storage": PageMeta("storage", "ذخیره‌سازی", "infra", "زیرساخت و یکپارچه‌سازی"),
    "site_cache": PageMeta("site_cache", "کش سایت", "infra", "زیرساخت و یکپارچه‌سازی"),
    "integrations": PageMeta("integrations", "یکپارچه‌سازی‌ها", "infra", "زیرساخت و یکپارچه‌سازی"),
    "workboard": PageMeta("workboard", "کارتابل اجرایی", "contractor", "فرم‌ها و اجرا (پیمانکار)", CATEGORY_CONTRACTOR),
    "documents": PageMeta("documents", "مدارک مهندسی", "edms", "مدیریت مدارک مهندسی", CATEGORY_EDMS),
}


DOMAIN_DEFINITIONS: dict[str, dict[str, Any]] = {
    "documents": {"label_fa": "مدارک مهندسی", "page_key": "documents", "read_key": "documents:read", "category_relevance": CATEGORY_EDMS},
    "archive": {"label_fa": "آرشیو مدارک", "page_key": "archive", "read_key": "archive:read", "category_relevance": CATEGORY_EDMS},
    "transmittal": {"label_fa": "ترنسمیتال", "page_key": "transmittal", "read_key": "transmittal:read", "category_relevance": CATEGORY_EDMS},
    "correspondence": {"label_fa": "مکاتبات", "page_key": "correspondence", "read_key": "correspondence:read", "category_relevance": CATEGORY_EDMS},
    "meeting_minutes": {"label_fa": "صورتجلسات و مصوبات", "page_key": "meeting_minutes", "read_key": "meeting_minutes:read", "category_relevance": CATEGORY_EDMS},
    "edms_forms": {"label_fa": "فرم‌های مدیریت مدارک", "page_key": "edms_forms", "read_key": "edms_forms:read", "category_relevance": CATEGORY_EDMS},
    "site_logs": {"label_fa": "گزارش‌های کارگاهی", "page_key": "site_logs_contractor", "read_key": "site_logs:read", "category_relevance": CATEGORY_CONTRACTOR},
    "comm_items": {"label_fa": "RFI/NCR", "page_key": "comm_items_contractor", "read_key": "comm_items:read", "category_relevance": CATEGORY_CONTRACTOR},
    "work_instructions": {"label_fa": "دستورکار", "page_key": "work_instructions_consultant", "read_key": "work_instructions:read", "category_relevance": CATEGORY_CONSULTANT},
    "project_control": {"label_fa": "کنترل پروژه", "page_key": "site_logs_consultant", "read_key": "project_control:view", "category_relevance": CATEGORY_CONSULTANT},
    "permit_qc": {"label_fa": "Permit + QC", "page_key": "permit_qc_contractor", "read_key": "permit_qc:read", "category_relevance": CATEGORY_CONTRACTOR},
    "workboard": {"label_fa": "کارتابل", "page_key": "workboard", "read_key": "workboard:read", "category_relevance": CATEGORY_CONTRACTOR},
    "reports": {"label_fa": "گزارش‌ها", "page_key": "reports", "read_key": "reports:read", "category_relevance": CATEGORY_ALL},
    "bim": {"label_fa": "BIM / Revit", "page_key": "bim", "read_key": "bim:read", "category_relevance": CATEGORY_CONSULTANT},
    "settings": {"label_fa": "تنظیمات سیستم", "page_key": "settings", "read_key": "settings:read", "category_relevance": CATEGORY_ALL},
    "permissions": {"label_fa": "سطح دسترسی", "page_key": "permissions", "read_key": "permissions:read", "category_relevance": CATEGORY_ALL},
    "users": {"label_fa": "مدیریت کاربران", "page_key": "users", "read_key": "users:read", "category_relevance": CATEGORY_ALL},
    "organizations": {"label_fa": "مدیریت سازمان‌ها", "page_key": "organizations", "read_key": "organizations:read", "category_relevance": CATEGORY_ALL},
    "lookup": {"label_fa": "فهرست‌های پایه", "page_key": "lookup", "read_key": "lookup:read", "category_relevance": CATEGORY_ALL},
    "storage": {"label_fa": "ذخیره‌سازی", "page_key": "storage", "read_key": "storage:read", "category_relevance": CATEGORY_ALL},
    "site_cache": {"label_fa": "کش سایت", "page_key": "site_cache", "read_key": "site_cache:read", "category_relevance": CATEGORY_ALL},
    "integrations": {"label_fa": "یکپارچه‌سازی‌ها", "page_key": "integrations", "read_key": "integrations:read", "category_relevance": CATEGORY_ALL},
}


ACTION_LABELS: dict[str, str] = {
    "read": "مشاهده",
    "create": "ایجاد",
    "update": "ویرایش",
    "delete": "حذف",
    "issue": "صدور",
    "void": "ابطال",
    "manage": "مدیریت",
    "upload": "آپلود",
    "download": "دانلود",
    "share": "اشتراک‌گذاری",
    "export": "خروجی",
    "import": "ورودی",
    "review": "بررسی",
    "approve": "تأیید",
    "reject": "رد",
    "publish": "انتشار",
    "submit": "ارسال",
    "sync": "همگام‌سازی",
    "ingest": "دریافت",
    "audit": "ممیزی",
    "relation": "ارتباطات",
    "tag": "تگ‌ها",
    "comment": "کامنت",
    "template": "قالب",
    "attachment": "پیوست",
    "report": "گزارش",
    "view": "مشاهده",
    "measure": "اندازه‌گیری",
    "qc": "QC",
}


EXACT_PERMISSION_META: dict[str, dict[str, Any]] = {
    "documents:reclassify": {
        "label_fa": "اصلاح کدگذاری مدرک",
        "type": "action",
        "page_key": "archive",
        "depends_on": ["documents:read", "archive:read"],
        "category_relevance": CATEGORY_EDMS,
    },
    "dashboard:read": {
        "label_fa": "نمایش کارتابل",
        "type": "hub",
        "page_key": "dashboard",
        "depends_on": [],
        "category_relevance": CATEGORY_ALL,
    },
    "hub_edms:read": {
        "label_fa": "نمایش هاب مدیریت مدارک مهندسی",
        "type": "hub",
        "page_key": "archive",
        "depends_on": [],
        "category_relevance": CATEGORY_EDMS,
    },
    "hub_reports:read": {
        "label_fa": "نمایش هاب گزارش‌ها",
        "type": "hub",
        "page_key": "reports",
        "depends_on": [],
        "category_relevance": CATEGORY_ALL,
    },
    "hub_contractor:read": {
        "label_fa": "نمایش هاب فرم‌ها و اجرا",
        "type": "hub",
        "page_key": "site_logs_contractor",
        "depends_on": [],
        "category_relevance": CATEGORY_CONTRACTOR,
    },
    "hub_consultant:read": {
        "label_fa": "نمایش هاب نظارت و کنترل پروژه",
        "type": "hub",
        "page_key": "site_logs_consultant",
        "depends_on": [],
        "category_relevance": CATEGORY_CONSULTANT,
    },
    "module_archive:read": {
        "label_fa": "نمایش ماژول آرشیو مدارک",
        "type": "module",
        "page_key": "archive",
        "depends_on": ["hub_edms:read", "archive:read"],
        "category_relevance": CATEGORY_EDMS,
    },
    "module_transmittal:read": {
        "label_fa": "نمایش ماژول ترنسمیتال",
        "type": "module",
        "page_key": "transmittal",
        "depends_on": ["hub_edms:read", "transmittal:read"],
        "category_relevance": CATEGORY_EDMS,
    },
    "module_correspondence:read": {
        "label_fa": "نمایش ماژول مکاتبات",
        "type": "module",
        "page_key": "correspondence",
        "depends_on": ["hub_edms:read", "correspondence:read"],
        "category_relevance": CATEGORY_EDMS,
    },
    "module_meeting_minutes:read": {
        "label_fa": "نمایش ماژول صورتجلسات",
        "type": "module",
        "page_key": "meeting_minutes",
        "depends_on": ["hub_edms:read", "meeting_minutes:read"],
        "category_relevance": CATEGORY_EDMS,
    },
    "module_edms_forms:read": {
        "label_fa": "نمایش ماژول فرم‌های مدیریت مدارک",
        "type": "module",
        "page_key": "edms_forms",
        "depends_on": ["hub_edms:read", "edms_forms:read"],
        "category_relevance": CATEGORY_EDMS,
    },
    "module_reports:read": {
        "label_fa": "نمایش ماژول گزارش‌ها",
        "type": "module",
        "page_key": "reports",
        "depends_on": ["hub_reports:read", "reports:read"],
        "category_relevance": CATEGORY_ALL,
    },
    "module_site_logs_contractor:read": {
        "label_fa": "نمایش گزارش کارگاهی پیمانکار",
        "type": "module",
        "page_key": "site_logs_contractor",
        "depends_on": ["hub_contractor:read", "site_logs:read"],
        "category_relevance": CATEGORY_CONTRACTOR,
    },
    "module_comm_items_contractor:read": {
        "label_fa": "نمایش درخواست‌های پیمانکار",
        "type": "module",
        "page_key": "comm_items_contractor",
        "depends_on": ["hub_contractor:read", "comm_items:read"],
        "category_relevance": CATEGORY_CONTRACTOR,
    },
    "module_permit_qc_contractor:read": {
        "label_fa": "نمایش Permit + QC پیمانکار",
        "type": "module",
        "page_key": "permit_qc_contractor",
        "depends_on": ["hub_contractor:read", "permit_qc:read"],
        "category_relevance": CATEGORY_CONTRACTOR,
    },
    "module_site_logs_consultant:read": {
        "label_fa": "نمایش بازدید و چک‌لیست مشاور",
        "type": "module",
        "page_key": "site_logs_consultant",
        "depends_on": ["hub_consultant:read", "site_logs:read"],
        "category_relevance": CATEGORY_CONSULTANT,
    },
    "module_comm_items_consultant:read": {
        "label_fa": "نمایش نواقص و درخواست‌های مشاور",
        "type": "module",
        "page_key": "comm_items_consultant",
        "depends_on": ["hub_consultant:read", "comm_items:read"],
        "category_relevance": CATEGORY_CONSULTANT,
    },
    "module_work_instructions_consultant:read": {
        "label_fa": "نمایش دستورکار مشاور",
        "type": "module",
        "page_key": "work_instructions_consultant",
        "depends_on": ["hub_consultant:read", "work_instructions:read"],
        "category_relevance": CATEGORY_CONSULTANT,
    },
    "project_control:view": {
        "label_fa": "مشاهده کنترل پروژه",
        "type": "domain",
        "page_key": "site_logs_consultant",
        "depends_on": ["hub_consultant:read", "module_site_logs_consultant:read"],
        "category_relevance": CATEGORY_CONSULTANT,
    },
    "project_control:measure": {
        "label_fa": "ثبت اندازه‌گیری کنترل پروژه",
        "type": "action",
        "page_key": "site_logs_consultant",
        "depends_on": ["project_control:view"],
        "category_relevance": CATEGORY_CONSULTANT,
    },
    "project_control:qc": {
        "label_fa": "تایید QC کنترل پروژه",
        "type": "action",
        "page_key": "site_logs_consultant",
        "depends_on": ["project_control:view"],
        "category_relevance": CATEGORY_CONSULTANT,
    },
    "module_permit_qc_consultant:read": {
        "label_fa": "نمایش Permit + QC مشاور",
        "type": "module",
        "page_key": "permit_qc_consultant",
        "depends_on": ["hub_consultant:read", "permit_qc:read"],
        "category_relevance": CATEGORY_CONSULTANT,
    },
    "module_settings_edms:read": {
        "label_fa": "نمایش تنظیمات داخلی مدیریت مدارک مهندسی",
        "type": "module",
        "page_key": "edms_settings",
        "depends_on": ["settings:read"],
        "category_relevance": CATEGORY_EDMS,
    },
    "module_settings_contractor:read": {
        "label_fa": "نمایش تنظیمات داخلی فرم‌ها و اجرا",
        "type": "module",
        "page_key": "contractor_settings",
        "depends_on": ["settings:read"],
        "category_relevance": CATEGORY_CONTRACTOR,
    },
    "module_settings_consultant:read": {
        "label_fa": "نمایش تنظیمات داخلی نظارت و کنترل پروژه",
        "type": "module",
        "page_key": "consultant_settings",
        "depends_on": ["settings:read"],
        "category_relevance": CATEGORY_CONSULTANT,
    },
}


def _all_known_permission_keys() -> list[str]:
    keys: set[str] = set(SYSTEM_PERMISSION_KEYS)
    for permissions in ROLE_PERMISSIONS.values():
        for permission in permissions or []:
            if permission and permission != "*":
                keys.add(str(permission))
    return sorted(keys)


def _page_meta(page_key: str) -> PageMeta:
    return PAGE_META[page_key]


def _action_label(action_key: str) -> str:
    parts = str(action_key or "").split("_")
    return " / ".join(ACTION_LABELS.get(part, part.upper()) for part in parts if part)


def _permission_meta_for_domain(permission: str) -> dict[str, Any]:
    domain, action = permission.split(":", 1)
    config = DOMAIN_DEFINITIONS.get(domain)
    if config is None:
        return _generic_permission_meta(permission)
    page = _page_meta(str(config["page_key"]))
    is_read = action == "read"
    return {
        "key": permission,
        "label_fa": f"{'مشاهده' if is_read else _action_label(action)} {config['label_fa']}",
        "label_en": permission,
        "type": "domain" if is_read else "action",
        "section_key": page.section_key,
        "section_label": page.section_label,
        "page_key": page.key,
        "page_label": page.label_fa,
        "depends_on": [] if is_read else [str(config["read_key"])],
        "category_relevance": list(config["category_relevance"]),
    }


def _generic_permission_meta(permission: str) -> dict[str, Any]:
    if ":" in permission:
        left, right = permission.split(":", 1)
        label = f"{left.replace('_', ' ').upper()} / {_action_label(right)}"
    else:
        label = permission.replace("_", " ").upper()
    page = _page_meta("settings")
    return {
        "key": permission,
        "label_fa": label,
        "label_en": permission,
        "type": "action",
        "section_key": page.section_key,
        "section_label": page.section_label,
        "page_key": page.key,
        "page_label": page.label_fa,
        "depends_on": [],
        "category_relevance": list(CATEGORY_ALL),
    }


@lru_cache(maxsize=1)
def permission_meta_map() -> dict[str, dict[str, Any]]:
    meta: dict[str, dict[str, Any]] = {}
    for permission in _all_known_permission_keys():
        exact = EXACT_PERMISSION_META.get(permission)
        if exact:
            page = _page_meta(str(exact["page_key"]))
            meta[permission] = {
                "key": permission,
                "label_fa": exact["label_fa"],
                "label_en": permission,
                "type": exact["type"],
                "section_key": page.section_key,
                "section_label": page.section_label,
                "page_key": page.key,
                "page_label": page.label_fa,
                "depends_on": list(exact.get("depends_on") or []),
                "category_relevance": list(exact.get("category_relevance") or CATEGORY_ALL),
            }
            continue
        if ":" in permission:
            meta[permission] = _permission_meta_for_domain(permission)
        else:
            meta[permission] = _generic_permission_meta(permission)
    return meta


def permission_meta_list() -> list[dict[str, Any]]:
    return [permission_meta_map()[key] for key in permission_keys()]


def permission_keys() -> list[str]:
    return list(permission_meta_map().keys())


def _action_permissions_for(prefix: str) -> list[str]:
    return [
        key
        for key in permission_keys()
        if key.startswith(f"{prefix}:") and key != f"{prefix}:read"
    ]


@lru_cache(maxsize=1)
def feature_catalog() -> list[dict[str, Any]]:
    features: list[dict[str, Any]] = [
        {
            "key": "dashboard",
            "label_fa": "کارتابل",
            "description": "نمای اصلی کارتابل و دسترسی سریع به فعالیت‌های روزانه.",
            "section_key": "reports_dash",
            "section_label": "گزارش و داشبورد",
            "page_key": "dashboard",
            "page_label": "کارتابل",
            "category_relevance": list(CATEGORY_ALL),
            "base_permissions": ["dashboard:read"],
            "action_permissions": [],
        },
        {
            "key": "reports_overview",
            "label_fa": "گزارش‌ها",
            "description": "نمایش هاب گزارش‌ها و دسترسی به خروجی‌ها و تحلیل‌ها.",
            "section_key": "reports_dash",
            "section_label": "گزارش و داشبورد",
            "page_key": "reports",
            "page_label": "گزارش‌ها",
            "category_relevance": list(CATEGORY_ALL),
            "base_permissions": ["hub_reports:read", "module_reports:read", "reports:read"],
            "action_permissions": [],
        },
        {
            "key": "archive",
            "label_fa": "آرشیو مدارک",
            "description": "نمایش آرشیو مدارک مهندسی و عملیات روی فایل‌های MDR.",
            "section_key": "edms",
            "section_label": "مدیریت مدارک مهندسی",
            "page_key": "archive",
            "page_label": "آرشیو مدارک",
            "category_relevance": list(CATEGORY_EDMS),
            "base_permissions": ["hub_edms:read", "module_archive:read", "archive:read"],
            "action_permissions": _action_permissions_for("archive") + _action_permissions_for("documents"),
        },
        {
            "key": "transmittal",
            "label_fa": "ترنسمیتال",
            "description": "ثبت، صدور و پیگیری ترنسمیتال‌های مدارک.",
            "section_key": "edms",
            "section_label": "مدیریت مدارک مهندسی",
            "page_key": "transmittal",
            "page_label": "ترنسمیتال",
            "category_relevance": list(CATEGORY_EDMS),
            "base_permissions": ["hub_edms:read", "module_transmittal:read", "transmittal:read"],
            "action_permissions": _action_permissions_for("transmittal"),
        },
        {
            "key": "correspondence",
            "label_fa": "مکاتبات",
            "description": "ثبت و مدیریت نامه‌ها و پیوست‌های مکاتبات.",
            "section_key": "edms",
            "section_label": "مدیریت مدارک مهندسی",
            "page_key": "correspondence",
            "page_label": "مکاتبات",
            "category_relevance": list(CATEGORY_EDMS),
            "base_permissions": ["hub_edms:read", "module_correspondence:read", "correspondence:read"],
            "action_permissions": _action_permissions_for("correspondence"),
        },
        {
            "key": "meeting_minutes",
            "label_fa": "صورتجلسات",
            "description": "بایگانی صورتجلسه‌ها و پیگیری مصوبات، مسئول‌ها، سررسیدها و پیوست‌ها.",
            "section_key": "edms",
            "section_label": "مدیریت مدارک مهندسی",
            "page_key": "meeting_minutes",
            "page_label": "صورتجلسات",
            "category_relevance": list(CATEGORY_EDMS),
            "base_permissions": ["hub_edms:read", "module_meeting_minutes:read", "meeting_minutes:read"],
            "action_permissions": _action_permissions_for("meeting_minutes"),
        },
        {
            "key": "edms_forms",
            "label_fa": "فرم‌ها",
            "description": "نمای یکپارچه و خواندنی فرم‌های کارگاهی، RFI، NCR، دستورکار و Permit/QC برای مدیریت مدارک.",
            "section_key": "edms",
            "section_label": "مدیریت مدارک مهندسی",
            "page_key": "edms_forms",
            "page_label": "فرم‌ها",
            "category_relevance": list(CATEGORY_EDMS),
            "base_permissions": ["hub_edms:read", "module_edms_forms:read", "edms_forms:read"],
            "action_permissions": [],
        },
        {
            "key": "contractor_execution",
            "label_fa": "گزارش کارگاهی",
            "description": "ماژول گزارش کارگاهی پیمانکار.",
            "section_key": "contractor",
            "section_label": "فرم‌ها و اجرا (پیمانکار)",
            "page_key": "site_logs_contractor",
            "page_label": "گزارش کارگاهی",
            "category_relevance": list(CATEGORY_CONTRACTOR),
            "base_permissions": ["hub_contractor:read", "module_site_logs_contractor:read", "site_logs:read"],
            "action_permissions": _action_permissions_for("site_logs"),
        },
        {
            "key": "contractor_requests",
            "label_fa": "درخواست‌ها",
            "description": "ماژول درخواست‌ها، RFI و NCR پیمانکار.",
            "section_key": "contractor",
            "section_label": "فرم‌ها و اجرا (پیمانکار)",
            "page_key": "comm_items_contractor",
            "page_label": "درخواست‌ها",
            "category_relevance": list(CATEGORY_CONTRACTOR),
            "base_permissions": ["hub_contractor:read", "module_comm_items_contractor:read", "comm_items:read"],
            "action_permissions": _action_permissions_for("comm_items"),
        },
        {
            "key": "contractor_permit_qc",
            "label_fa": "Permit + QC",
            "description": "ثبت و گردش فرم‌های Permit و کنترل کیفیت پیمانکار.",
            "section_key": "contractor",
            "section_label": "فرم‌ها و اجرا (پیمانکار)",
            "page_key": "permit_qc_contractor",
            "page_label": "Permit + QC",
            "category_relevance": list(CATEGORY_CONTRACTOR),
            "base_permissions": ["hub_contractor:read", "module_permit_qc_contractor:read", "permit_qc:read"],
            "action_permissions": _action_permissions_for("permit_qc"),
        },
        {
            "key": "consultant_inspection",
            "label_fa": "بازدید و چک‌لیست",
            "description": "بازدیدهای میدانی و چک‌لیست‌های مشاور.",
            "section_key": "consultant",
            "section_label": "نظارت و کنترل پروژه (مشاور)",
            "page_key": "site_logs_consultant",
            "page_label": "بازدید و چک‌لیست",
            "category_relevance": list(CATEGORY_CONSULTANT),
            "base_permissions": ["hub_consultant:read", "module_site_logs_consultant:read", "site_logs:read"],
            "action_permissions": _action_permissions_for("site_logs"),
        },
        {
            "key": "consultant_defects",
            "label_fa": "لیست نواقص",
            "description": "مشاهده و مدیریت نواقص پروژه توسط مشاور.",
            "section_key": "consultant",
            "section_label": "نظارت و کنترل پروژه (مشاور)",
            "page_key": "comm_items_consultant",
            "page_label": "لیست نواقص",
            "category_relevance": list(CATEGORY_CONSULTANT),
            "base_permissions": ["hub_consultant:read", "module_comm_items_consultant:read", "comm_items:read"],
            "action_permissions": _action_permissions_for("comm_items"),
        },
        {
            "key": "consultant_instructions",
            "label_fa": "دستورکار",
            "description": "صدور و پیگیری دستورکار مستقل در هاب مشاور.",
            "section_key": "consultant",
            "section_label": "نظارت و کنترل پروژه (مشاور)",
            "page_key": "work_instructions_consultant",
            "page_label": "دستورکار",
            "category_relevance": list(CATEGORY_CONSULTANT),
            "base_permissions": ["hub_consultant:read", "module_work_instructions_consultant:read", "work_instructions:read"],
            "action_permissions": _action_permissions_for("work_instructions"),
        },
        {
            "key": "consultant_control",
            "label_fa": "کنترل پروژه",
            "description": "تحلیل فعالیت‌ها، نفرات، تجهیزات و مصالح از گزارش‌های کارگاهی.",
            "section_key": "consultant",
            "section_label": "نظارت و کنترل پروژه (مشاور)",
            "page_key": "site_logs_consultant",
            "page_label": "کنترل پروژه",
            "category_relevance": list(CATEGORY_CONSULTANT),
            "base_permissions": ["hub_consultant:read", "module_site_logs_consultant:read", "project_control:view"],
            "action_permissions": _action_permissions_for("project_control") + ["site_logs:report_read"],
        },
        {
            "key": "consultant_permit_qc",
            "label_fa": "Permit + QC",
            "description": "بررسی و گردش Permit/QC از دید مشاور.",
            "section_key": "consultant",
            "section_label": "نظارت و کنترل پروژه (مشاور)",
            "page_key": "permit_qc_consultant",
            "page_label": "Permit + QC",
            "category_relevance": list(CATEGORY_CONSULTANT),
            "base_permissions": ["hub_consultant:read", "module_permit_qc_consultant:read", "permit_qc:read"],
            "action_permissions": _action_permissions_for("permit_qc"),
        },
        {
            "key": "settings_console",
            "label_fa": "تنظیمات سیستم و امنیت",
            "description": "دسترسی به تنظیمات سیستم، کاربران و ماتریس دسترسی.",
            "section_key": "admin",
            "section_label": "مدیریت و تنظیمات",
            "page_key": "settings",
            "page_label": "تنظیمات سیستم",
            "category_relevance": list(CATEGORY_ALL),
            "base_permissions": ["settings:read"],
            "action_permissions": ["settings:update", "permissions:read", "permissions:update", "users:read", "users:create", "users:update", "users:delete", "organizations:read", "organizations:manage"],
        },
        {
            "key": "edms_internal_settings",
            "label_fa": "تنظیمات داخلی مدارک مهندسی",
            "description": "دسترسی به چرخ‌دنده داخلی هاب مدیریت مدارک مهندسی.",
            "section_key": "edms",
            "section_label": "مدیریت مدارک مهندسی",
            "page_key": "edms_settings",
            "page_label": "تنظیمات داخلی مدیریت مدارک مهندسی",
            "category_relevance": list(CATEGORY_EDMS),
            "base_permissions": ["module_settings_edms:read", "settings:read"],
            "action_permissions": ["settings:update"],
        },
        {
            "key": "contractor_internal_settings",
            "label_fa": "تنظیمات داخلی فرم‌ها و اجرا",
            "description": "دسترسی به چرخ‌دنده داخلی هاب پیمانکار.",
            "section_key": "contractor",
            "section_label": "فرم‌ها و اجرا (پیمانکار)",
            "page_key": "contractor_settings",
            "page_label": "تنظیمات داخلی فرم‌ها و اجرا",
            "category_relevance": list(CATEGORY_CONTRACTOR),
            "base_permissions": ["module_settings_contractor:read", "settings:read"],
            "action_permissions": ["settings:update"],
        },
        {
            "key": "consultant_internal_settings",
            "label_fa": "تنظیمات داخلی نظارت و کنترل پروژه",
            "description": "دسترسی به چرخ‌دنده داخلی هاب مشاور.",
            "section_key": "consultant",
            "section_label": "نظارت و کنترل پروژه (مشاور)",
            "page_key": "consultant_settings",
            "page_label": "تنظیمات داخلی نظارت و کنترل پروژه",
            "category_relevance": list(CATEGORY_CONSULTANT),
            "base_permissions": ["module_settings_consultant:read", "settings:read"],
            "action_permissions": ["settings:update"],
        },
        {
            "key": "platform_infra",
            "label_fa": "زیرساخت و یکپارچه‌سازی",
            "description": "مدیریت ذخیره‌سازی، کش و اتصال به سرویس‌های بیرونی.",
            "section_key": "infra",
            "section_label": "زیرساخت و یکپارچه‌سازی",
            "page_key": "storage",
            "page_label": "ذخیره‌سازی",
            "category_relevance": list(CATEGORY_ALL),
            "base_permissions": ["storage:read", "integrations:read", "site_cache:read"],
            "action_permissions": ["storage:update", "storage:sync_manage", "integrations:update", "site_cache:manage", "lookup:read", "lookup:manage"],
        },
    ]
    return features
