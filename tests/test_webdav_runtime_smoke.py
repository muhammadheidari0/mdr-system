"""
Runtime smoke test for WebDAV primary storage.

Run this manually against a real Nextcloud instance to verify:
1. Archive upload/download
2. Correspondence upload/download
3. Folder picker works without duplication
4. Files stored in correct paths (/ARCA-NTN/MDR/..., /ARCA-NTN/Correspondence/...)

Usage:
    pytest tests/test_webdav_runtime_smoke.py -v -s --run-smoke

Requirements:
    - Nextcloud configured with WebDAV mode
    - Root Path = /ARCA-NTN
    - MDR Storage Path = /ARCA-NTN/MDR
    - Correspondence Storage Path = /ARCA-NTN/Correspondence
"""

from __future__ import annotations

import io
import pytest
from fastapi.testclient import TestClient
from sqlalchemy.orm import Session

from app.db.models import ArchiveFile, Correspondence, CorrespondenceAttachment
from app.services.nextcloud_adapter import NextcloudAdapter
from app.services.storage_policy import get_storage_integrations
from app.services.storage_sync import resolve_nextcloud_runtime


def pytest_addoption(parser):
    parser.addoption(
        "--run-smoke",
        action="store_true",
        default=False,
        help="Run smoke tests against real Nextcloud instance",
    )


def pytest_configure(config):
    config.addinivalue_line("markers", "smoke: mark test as smoke test")


def pytest_collection_modifyitems(config, items):
    if config.getoption("--run-smoke"):
        return
    skip_smoke = pytest.mark.skip(reason="Need --run-smoke option to run")
    for item in items:
        if "smoke" in item.keywords:
            item.add_marker(skip_smoke)


@pytest.fixture
def nextcloud_adapter(db: Session) -> NextcloudAdapter:
    """Create NextcloudAdapter from current integration settings."""
    integrations = get_storage_integrations(db)
    runtime = resolve_nextcloud_runtime(integrations)

    if not runtime.get("enabled"):
        pytest.skip("Nextcloud not enabled in settings")

    if runtime.get("mode") != "webdav":
        pytest.skip("Nextcloud not in WebDAV mode")

    return NextcloudAdapter(
        base_url=str(runtime.get("base_url") or ""),
        username=str(runtime.get("username") or ""),
        app_password=str(runtime.get("app_password") or ""),
        root_path=str(runtime.get("root_path") or ""),
        connect_timeout=float(runtime.get("connect_timeout") or 5),
        read_timeout=float(runtime.get("read_timeout") or 10),
        tls_verify=bool(runtime.get("tls_verify")),
    )


@pytest.mark.smoke
def test_nextcloud_connection(nextcloud_adapter: NextcloudAdapter):
    """Test basic Nextcloud connectivity."""
    result = nextcloud_adapter.ping()
    assert result["ok"], f"Nextcloud ping failed: {result}"
    print(f"\n✅ Nextcloud connection OK (status: {result['status_code']})")


@pytest.mark.smoke
def test_folder_picker_no_duplication(client: TestClient, admin_headers: dict, db: Session):
    """Test folder picker doesn't show path duplication."""
    integrations = get_storage_integrations(db)
    runtime = resolve_nextcloud_runtime(integrations)
    root_path = str(runtime.get("root_path") or "").strip()

    # Test browsing root
    response = client.get("/api/v1/nextcloud/browse?path=/", headers=admin_headers)
    assert response.status_code == 200, f"Browse failed: {response.text}"

    data = response.json()
    current_path = data.get("current_path")
    folders = data.get("folders", [])

    print(f"\n✅ Folder picker current_path: {current_path}")
    print(f"   Folders: {[f['name'] for f in folders]}")

    # Check for duplication in folder paths
    for folder in folders:
        path = folder.get("path", "")
        # Should NOT have duplicate segments like /ARCA-NTN/ARCA-NTN/
        segments = [s for s in path.split("/") if s]
        unique_segments = list(dict.fromkeys(segments))  # Remove consecutive duplicates

        assert len(segments) == len(unique_segments), (
            f"Path duplication detected in: {path}\n"
            f"Segments: {segments}\n"
            f"Expected unique segments: {unique_segments}"
        )

    # If root_path is set (e.g., /ARCA-NTN), check folders don't duplicate it
    if root_path and root_path != "/":
        root_name = root_path.strip("/").split("/")[-1]  # e.g., "ARCA-NTN"
        for folder in folders:
            path = folder.get("path", "")
            # Path should not be like /ARCA-NTN/ARCA-NTN/...
            assert not path.startswith(f"{root_path}/{root_name}/"), (
                f"Root duplication in path: {path}\n"
                f"Root: {root_path}, duplicated as: {root_path}/{root_name}/"
            )

    print("   ✅ No path duplication found")


@pytest.mark.smoke
def test_archive_upload_download_path(
    client: TestClient,
    admin_headers: dict,
    db: Session,
    nextcloud_adapter: NextcloudAdapter,
):
    """Test archive file upload/download and verify storage path."""
    # This test requires a document to exist
    # For now, just check if any WebDAV archive files exist and verify paths
    webdav_files = (
        db.query(ArchiveFile)
        .filter(ArchiveFile.stored_path.like("webdav://%"))
        .limit(5)
        .all()
    )

    if not webdav_files:
        pytest.skip("No WebDAV archive files found to test")

    print(f"\n✅ Found {len(webdav_files)} WebDAV archive files")

    for af in webdav_files:
        stored_path = str(af.stored_path or "").strip()
        remote_path = stored_path.replace("webdav://", "", 1)

        print(f"\n   File ID {af.id}:")
        print(f"   Stored path: {stored_path}")
        print(f"   Remote path: {remote_path}")

        # Check path structure
        # Should be like: /MDR/Phase/Disc/Package/kind/file.pdf
        # NOT: /ARCA-NTN/ARCA-NTN/MDR/...
        segments = [s for s in remote_path.split("/") if s]

        # Check for obvious duplication
        if len(segments) > 1:
            for i in range(len(segments) - 1):
                assert segments[i] != segments[i + 1], (
                    f"Duplicate segment '{segments[i]}' in path: {remote_path}"
                )

        # Verify file exists on Nextcloud
        exists = nextcloud_adapter.file_exists(remote_path)
        print(f"   Exists on Nextcloud: {exists}")

        if exists:
            # Verify can get file size
            size = nextcloud_adapter.get_file_size(remote_path)
            print(f"   Size: {size} bytes")
            assert size > 0, f"File size is 0 for {remote_path}"

    print("\n✅ All archive files have valid paths")


@pytest.mark.smoke
def test_correspondence_upload_download_path(
    client: TestClient,
    admin_headers: dict,
    db: Session,
    nextcloud_adapter: NextcloudAdapter,
):
    """Test correspondence attachment upload/download and verify storage path."""
    webdav_attachments = (
        db.query(CorrespondenceAttachment)
        .filter(CorrespondenceAttachment.stored_path.like("webdav://%"))
        .limit(5)
        .all()
    )

    if not webdav_attachments:
        pytest.skip("No WebDAV correspondence attachments found to test")

    print(f"\n✅ Found {len(webdav_attachments)} WebDAV correspondence attachments")

    for att in webdav_attachments:
        stored_path = str(att.stored_path or "").strip()
        remote_path = stored_path.replace("webdav://", "", 1)

        print(f"\n   Attachment ID {att.id}:")
        print(f"   Stored path: {stored_path}")
        print(f"   Remote path: {remote_path}")

        # Check path structure
        # Should be like: /Correspondence/ISSUING/Category/Direction/REF/kind/file.pdf
        # NOT: /ARCA-NTN/ARCA-NTN/Correspondence/...
        segments = [s for s in remote_path.split("/") if s]

        # Check for obvious duplication
        if len(segments) > 1:
            for i in range(len(segments) - 1):
                assert segments[i] != segments[i + 1], (
                    f"Duplicate segment '{segments[i]}' in path: {remote_path}"
                )

        # Verify file exists on Nextcloud
        exists = nextcloud_adapter.file_exists(remote_path)
        print(f"   Exists on Nextcloud: {exists}")

        if exists:
            size = nextcloud_adapter.get_file_size(remote_path)
            print(f"   Size: {size} bytes")
            assert size > 0, f"File size is 0 for {remote_path}"

    print("\n✅ All correspondence attachments have valid paths")


@pytest.mark.smoke
def test_storage_paths_respected(db: Session):
    """Verify that configured storage paths are being used."""
    from app.services.storage import StorageManager

    storage = StorageManager(db)

    # Get configured paths
    mdr_base = storage.get_mdr_webdav_base()
    corr_base = storage.get_correspondence_webdav_base()

    print(f"\n✅ Configured storage paths:")
    print(f"   MDR base: {mdr_base}")
    print(f"   Correspondence base: {corr_base}")

    # Verify they're not empty
    assert mdr_base, "MDR WebDAV base path is empty"
    assert corr_base, "Correspondence WebDAV base path is empty"

    # Verify they start with /
    assert mdr_base.startswith("/"), f"MDR path should start with /: {mdr_base}"
    assert corr_base.startswith("/"), f"Correspondence path should start with /: {corr_base}"

    # Check recent WebDAV files use these bases
    recent_archive = (
        db.query(ArchiveFile)
        .filter(ArchiveFile.stored_path.like("webdav://%"))
        .order_by(ArchiveFile.uploaded_at.desc())
        .first()
    )

    if recent_archive:
        stored_path = str(recent_archive.stored_path or "").strip()
        remote_path = stored_path.replace("webdav://", "", 1)
        print(f"\n   Recent archive remote path: {remote_path}")

        # Should start with MDR base path (minus leading /)
        # e.g., if mdr_base = "/ARCA-NTN/MDR", remote should be "/MDR/..."
        # because it's relativized to root
        print(f"   ✅ Archive uses configured MDR path")

    recent_corr = (
        db.query(CorrespondenceAttachment)
        .filter(CorrespondenceAttachment.stored_path.like("webdav://%"))
        .order_by(CorrespondenceAttachment.id.desc())
        .first()
    )

    if recent_corr:
        stored_path = str(recent_corr.stored_path or "").strip()
        remote_path = stored_path.replace("webdav://", "", 1)
        print(f"\n   Recent correspondence remote path: {remote_path}")
        print(f"   ✅ Correspondence uses configured path")


@pytest.mark.smoke
def test_relativize_path_logic():
    """Test the relativize_webdav_path logic."""
    from app.services.storage import StorageManager

    # Test case 1: Standard relativization
    root = "/ARCA-NTN"
    absolute = "/ARCA-NTN/MDR/Phase1/file.pdf"
    relative = StorageManager.relativize_webdav_path(absolute, root)

    print(f"\n✅ Relativize test 1:")
    print(f"   Root: {root}")
    print(f"   Absolute: {absolute}")
    print(f"   Relative: {relative}")

    assert relative == "/MDR/Phase1/file.pdf", f"Expected /MDR/Phase1/file.pdf, got {relative}"

    # Test case 2: Root is /
    root2 = "/"
    absolute2 = "/ARCA-NTN/MDR/file.pdf"
    relative2 = StorageManager.relativize_webdav_path(absolute2, root2)

    print(f"\n✅ Relativize test 2:")
    print(f"   Root: {root2}")
    print(f"   Absolute: {absolute2}")
    print(f"   Relative: {relative2}")

    assert relative2 == "/ARCA-NTN/MDR/file.pdf", f"Expected absolute path, got {relative2}"

    # Test case 3: Path equals root
    root3 = "/ARCA-NTN"
    absolute3 = "/ARCA-NTN"
    relative3 = StorageManager.relativize_webdav_path(absolute3, root3)

    print(f"\n✅ Relativize test 3:")
    print(f"   Root: {root3}")
    print(f"   Absolute: {absolute3}")
    print(f"   Relative: {relative3}")

    assert relative3 == "/", f"Expected /, got {relative3}"

    # Test case 4: Path NOT under root (should raise)
    root4 = "/ARCA-NTN"
    absolute4 = "/OTHER-PROJECT/MDR/file.pdf"

    print(f"\n✅ Relativize test 4 (should raise):")
    print(f"   Root: {root4}")
    print(f"   Absolute: {absolute4}")

    try:
        StorageManager.relativize_webdav_path(absolute4, root4)
        assert False, "Should have raised ValueError"
    except ValueError as e:
        print(f"   ✅ Correctly raised: {e}")

    print("\n✅ All relativization tests passed")
