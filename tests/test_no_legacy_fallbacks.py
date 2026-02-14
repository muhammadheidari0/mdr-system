from __future__ import annotations

from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
TARGETS = [
    ROOT / "frontend" / "src" / "legacy_runtime" / "app.ts",
    ROOT / "frontend" / "src" / "legacy_runtime" / "transmittal_v2.ts",
    ROOT / "frontend" / "src" / "legacy_runtime" / "correspondence.ts",
]

BRIDGE_CONTRACT_TARGETS = [
    *TARGETS,
    ROOT / "frontend" / "src" / "entries" / "app.ts",
    ROOT / "frontend" / "src" / "globals.d.ts",
    ROOT / "frontend" / "src" / "lib" / "app_router.ts",
    ROOT / "frontend" / "src" / "legacy_runtime" / "views" / "dashboard.ts",
    ROOT / "frontend" / "src" / "legacy_runtime" / "views" / "edms.ts",
    ROOT / "frontend" / "src" / "legacy_runtime" / "views" / "reports.ts",
    ROOT / "frontend" / "src" / "legacy_runtime" / "views" / "contractor.ts",
    ROOT / "frontend" / "src" / "legacy_runtime" / "views" / "consultant.ts",
    ROOT / "frontend" / "src" / "legacy_runtime" / "views" / "profile.ts",
    ROOT / "frontend" / "src" / "legacy_runtime" / "views" / "settings.ts",
    ROOT / "templates" / "base.html",
]


def test_targeted_legacy_fallback_messages_removed() -> None:
    needles = ("fallback to legacy", "falling back to legacy")
    for path in TARGETS:
        text = path.read_text(encoding="utf-8").lower()
        assert all(needle not in text for needle in needles), f"Legacy fallback marker found in {path}"


def test_legacy_bridge_contract_markers_removed() -> None:
    needles = ("window.__ts_", "window.viewboot", "registerviewboot")
    for path in BRIDGE_CONTRACT_TARGETS:
        text = path.read_text(encoding="utf-8").lower()
        assert all(needle not in text for needle in needles), f"Legacy bridge contract marker found in {path}"


def test_static_js_folder_removed() -> None:
    assert not (ROOT / "static" / "js").exists(), "Legacy static/js folder must remain removed."


def test_templates_do_not_reference_static_js_assets() -> None:
    for path in (ROOT / "templates").rglob("*.html"):
        text = path.read_text(encoding="utf-8")
        assert "/static/js/" not in text, f"Template still references legacy static/js assets: {path}"
