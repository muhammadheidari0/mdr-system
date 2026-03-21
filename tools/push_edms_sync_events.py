from __future__ import annotations

import argparse
import json

import requests

from app.core.config import settings
from app.db.session import SessionLocal
from app.services.edms_sync_outbox import EVENT_ENDPOINTS, build_sync_envelopes


def main() -> int:
    parser = argparse.ArgumentParser(description="Push signed native EDMS sync events.")
    parser.add_argument("--target-url", default=str(settings.NATIVE_EDMS_SYNC_TARGET_URL or "").strip())
    parser.add_argument("--secret", default=str(settings.NATIVE_EDMS_SYNC_SHARED_SECRET or "").strip())
    parser.add_argument("--include", action="append", default=[])
    parser.add_argument("--dry-run", action="store_true")
    parser.add_argument("--timeout", type=int, default=int(settings.NATIVE_EDMS_SYNC_TIMEOUT_SECONDS or 15))
    args = parser.parse_args()

    if not args.secret:
        raise SystemExit("Missing secret. Set --secret or NATIVE_EDMS_SYNC_SHARED_SECRET.")

    with SessionLocal() as db:
        envelopes = build_sync_envelopes(db, secret=args.secret, source=settings.NATIVE_EDMS_SYNC_SOURCE)

    if args.include:
        envelopes = {key: value for key, value in envelopes.items() if key in set(args.include)}

    if args.dry_run or not args.target_url:
        print(json.dumps({"dry_run": True, "events": envelopes}, ensure_ascii=False, indent=2))
        return 0

    results = []
    target_url = str(args.target_url or "").rstrip("/")
    for entity, envelope in envelopes.items():
        endpoint = EVENT_ENDPOINTS.get(entity)
        if not endpoint:
            continue
        url = f"{target_url}{endpoint}"
        response = requests.post(url, json=envelope, timeout=int(args.timeout))
        results.append({"entity": entity, "status_code": response.status_code, "ok": response.ok, "url": url})

    print(json.dumps({"dry_run": False, "results": results}, ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
