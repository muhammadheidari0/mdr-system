from __future__ import annotations

from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
TARGETS = [
    ROOT / "static" / "js" / "app.js",
    ROOT / "static" / "js" / "transmittal_v2.js",
    ROOT / "static" / "js" / "correspondence.js",
]

BRIDGE_CONTRACT_TARGETS = [
    *TARGETS,
    ROOT / "frontend" / "src" / "entries" / "app.ts",
    ROOT / "frontend" / "src" / "globals.d.ts",
    ROOT / "frontend" / "src" / "lib" / "app_router.ts",
    ROOT / "templates" / "base.html",
    ROOT / "static" / "js" / "views" / "dashboard.js",
    ROOT / "static" / "js" / "views" / "edms.js",
    ROOT / "static" / "js" / "views" / "reports.js",
    ROOT / "static" / "js" / "views" / "contractor.js",
    ROOT / "static" / "js" / "views" / "consultant.js",
    ROOT / "static" / "js" / "views" / "profile.js",
    ROOT / "static" / "js" / "views" / "settings.js",
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
