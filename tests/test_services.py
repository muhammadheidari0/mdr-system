from __future__ import annotations

from app.services import docnum_service, import_service, mdr_service


def test_services_modules_import_smoke() -> None:
    """
    Keep services test module active without skip placeholders.
    """
    assert docnum_service is not None
    assert import_service is not None
    assert mdr_service is not None
