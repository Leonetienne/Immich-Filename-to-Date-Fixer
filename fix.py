#!python3
import argparse
import csv
import os
from datetime import datetime, timedelta, timezone
from pathlib import Path

import requests

from filename_parsing import parse_filename_dt


def api_key_headers(api_key):
    return {"x-api-key": api_key, "Content-Type": "application/json"}


def _immich_request(method, base_url, headers, path, payload):
    r = requests.request(
        method,
        f"{base_url.rstrip('/')}/api{path}",
        headers=headers,
        json=payload,
        timeout=60,
    )

    if not r.ok:
        try:
            detail = r.json().get("message", r.text)
        except ValueError:
            detail = r.text
        if isinstance(detail, list):
            detail = "; ".join(detail)
        raise SystemExit(f"Immich API error {r.status_code} on {method} {path}: {detail}")

    return r.json() if r.content else None


def immich_post(base_url, headers, path, payload):
    return _immich_request("POST", base_url, headers, path, payload)


def immich_put(base_url, headers, path, payload):
    return _immich_request("PUT", base_url, headers, path, payload)


ASSET_TYPES = ("IMAGE", "VIDEO")


def search_assets_in_bad_date_range(base_url, headers, bad_date_from, bad_date_to, page_size=500, visibility=None):
    start = datetime.fromisoformat(bad_date_from).replace(tzinfo=timezone.utc)

    # Inclusive date range: --bad-date-to 2025-04-30 includes all of April 30.
    end = datetime.fromisoformat(bad_date_to).replace(tzinfo=timezone.utc) + timedelta(days=1)

    # /search/metadata only accepts a single asset type per request, so each type gets its own
    # paginated pass.
    for asset_type in ASSET_TYPES:
        page = 1

        while True:
            payload = {
                "takenAfter": start.isoformat().replace("+00:00", "Z"),
                "takenBefore": end.isoformat().replace("+00:00", "Z"),
                "type": asset_type,
                "size": page_size,
                "page": page,
                "withExif": True,
            }

            if visibility:
                payload["visibility"] = visibility

            data = immich_post(base_url, headers, "/search/metadata", payload)

            assets = (
                data.get("assets", {}).get("items")
                or data.get("items")
                or data.get("results")
                or []
            )

            if not assets:
                break

            for asset in assets:
                yield asset

            if len(assets) < page_size:
                break

            page += 1


def get_asset_filename(asset):
    return (
        asset.get("originalFileName")
        or Path(asset.get("originalPath", "")).name
        or asset.get("fileName")
        or asset.get("id")
        or ""
    )


def get_current_asset_date(asset):
    return (
        asset.get("fileCreatedAt")
        or asset.get("localDateTime")
        or asset.get("exifInfo", {}).get("dateTimeOriginal")
    )


def parse_tz_offset(offset):
    sign = 1 if offset.startswith("+") else -1
    hh, mm = map(int, offset[1:].split(":"))
    return timezone(sign * timedelta(hours=hh, minutes=mm))


def resolve_bad_date_range(args):
    if args.bad_date:
        return args.bad_date, args.bad_date

    if args.bad_date_from and args.bad_date_to:
        return args.bad_date_from, args.bad_date_to

    raise SystemExit("Use either --bad-date YYYY-MM-DD or --bad-date-from YYYY-MM-DD --bad-date-to YYYY-MM-DD.")


def add_common_arguments(parser):
    parser.add_argument("--url", required=True)
    parser.add_argument("--bad-date", help="Single bad Immich timeline date, YYYY-MM-DD")
    parser.add_argument("--bad-date-from", help="Start of bad Immich timeline range, YYYY-MM-DD")
    parser.add_argument("--bad-date-to", help="End of bad Immich timeline range, YYYY-MM-DD, inclusive")
    parser.add_argument("--apply", action="store_true")
    parser.add_argument("--fix-time", action="store_true",
                        help="Also correct the time-of-day (up to the second) when the filename contains HH MM SS")
    parser.add_argument("--tz-offset", default="+00:00")
    parser.add_argument("--csv", default=None)
    return parser


def run(base_url, headers, bad_date_from, bad_date_to, tz, csv_filename, apply_changes, fix_time, visibility=None):
    rows = []
    scanned = 0
    matched = 0
    updated = 0
    skipped = 0
    already_correct = 0

    # Snapshot the full result set before applying any fixes: correcting an asset's date moves it
    # outside takenAfter/takenBefore, which would shift page offsets and skip assets mid-scan
    # if we paginated and applied changes at the same time.
    assets = list(search_assets_in_bad_date_range(base_url, headers, bad_date_from, bad_date_to, visibility=visibility))

    for asset in assets:
        scanned += 1

        filename = get_asset_filename(asset)
        new_dt, has_time = parse_filename_dt(filename, tz)

        if not new_dt:
            skipped += 1
            print(f"File {filename} skipped because filename contains no usable date")
            rows.append([asset.get("id"), filename, "SKIP_NO_FILENAME_DATE", "", ""])
            continue

        matched += 1

        old_date_raw = get_current_asset_date(asset)

        if not old_date_raw:
            skipped += 1
            print(f"File {filename} skipped because current date is unknown")
            rows.append([asset.get("id"), filename, "SKIP_NO_CURRENT_DATE", "", ""])
            continue

        old_dt = datetime.fromisoformat(old_date_raw.replace("Z", "+00:00"))
        new_dt_utc = new_dt.astimezone(timezone.utc)

        old_iso = old_dt.astimezone(timezone.utc).isoformat().replace("+00:00", "Z")
        new_iso = new_dt_utc.isoformat().replace("+00:00", "Z")

        fix_time_for_this = fix_time and has_time

        if fix_time_for_this:
            already_correct_flag = (
                old_dt.astimezone(timezone.utc).replace(microsecond=0)
                == new_dt_utc.replace(microsecond=0)
            )
            already_correct_label = "ALREADY_CORRECT_DATETIME"
        else:
            already_correct_flag = old_dt.date() == new_dt_utc.date()
            already_correct_label = "ALREADY_CORRECT_DAY"

        if already_correct_flag:
            already_correct += 1
            print(f"File {filename} was already on correct {'datetime' if fix_time_for_this else 'date'} {old_iso}")
            rows.append([asset.get("id"), filename, already_correct_label, old_iso, new_iso])
            continue

        print(f"File {filename} was corrected from {old_iso} to {new_iso}")

        rows.append([
            asset.get("id"),
            filename,
            "WOULD_CORRECT" if not apply_changes else "CORRECTED",
            old_iso,
            new_iso,
        ])

        if apply_changes:
            immich_put(
                base_url,
                headers,
                f"/assets/{asset['id']}",
                {"dateTimeOriginal": new_iso},
            )
            updated += 1

    with open(csv_filename, "w", newline="", encoding="utf-8") as f:
        writer = csv.writer(f)
        writer.writerow(["asset_id", "filename", "action", "old_date", "new_date_utc"])
        writer.writerows(rows)

    print()
    print(f"Bad date range: {bad_date_from} to {bad_date_to}")
    print(f"Scanned: {scanned}")
    print(f"Filename date matched: {matched}")
    print(f"Already correct day: {already_correct}")
    print(f"Updated: {updated}")
    print(f"Skipped: {skipped}")
    print(f"Report: {csv_filename}")

    if not apply_changes:
        print("Dry-run only. Re-run with --apply to update Immich.")


def main():
    parser = argparse.ArgumentParser(
        description="Fix Immich asset dates for assets clustered on one wrong date/range by parsing the true date from filenames."
    )
    add_common_arguments(parser)
    parser.add_argument("--key", default=os.getenv("IMMICH_API_KEY"))

    args = parser.parse_args()

    if not args.key:
        raise SystemExit("Missing API key. Set IMMICH_API_KEY or pass --key.")

    bad_date_from, bad_date_to = resolve_bad_date_range(args)

    csv_filename = args.csv or f"immich-date-fix-{bad_date_from}_to_{bad_date_to}.csv"
    tz = parse_tz_offset(args.tz_offset)

    run(
        args.url,
        api_key_headers(args.key),
        bad_date_from,
        bad_date_to,
        tz,
        csv_filename,
        args.apply,
        args.fix_time,
    )


if __name__ == "__main__":
    main()

