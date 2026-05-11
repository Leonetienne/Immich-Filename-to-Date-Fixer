#!python3
import argparse
import csv
import os
import re
from datetime import datetime, timedelta, timezone
from pathlib import Path

import requests


def parse_filename_dt(filename: str, tz: timezone):
    name = Path(filename).name

    full_match = re.search(
        r"(\d{4})(\d{2})(\d{2})[_-](\d{2})(\d{2})(\d{2})",
        name,
    )

    if full_match:
        year = int(full_match.group(1))
        month = int(full_match.group(2))
        day = int(full_match.group(3))
        hour = int(full_match.group(4))
        minute = int(full_match.group(5))
        second = int(full_match.group(6))

        try:
            return datetime(year, month, day, hour, minute, second, tzinfo=tz)
        except ValueError:
            return None

    date_only_match = re.search(
        r"(\d{4})(\d{2})(\d{2})",
        name,
    )

    if date_only_match:
        year = int(date_only_match.group(1))
        month = int(date_only_match.group(2))
        day = int(date_only_match.group(3))

        try:
            return datetime(year, month, day, 12, 0, 0, tzinfo=tz)
        except ValueError:
            return None

    return None


def immich_post(base_url, api_key, path, payload):
    r = requests.post(
        f"{base_url.rstrip('/')}/api{path}",
        headers={"x-api-key": api_key, "Content-Type": "application/json"},
        json=payload,
        timeout=60,
    )
    r.raise_for_status()
    return r.json()


def immich_put(base_url, api_key, path, payload):
    r = requests.put(
        f"{base_url.rstrip('/')}/api{path}",
        headers={"x-api-key": api_key, "Content-Type": "application/json"},
        json=payload,
        timeout=60,
    )
    r.raise_for_status()
    return r.json()


def search_assets_in_bad_date_range(base_url, api_key, bad_date_from, bad_date_to, page_size=500):
    start = datetime.fromisoformat(bad_date_from).replace(tzinfo=timezone.utc)

    # Inclusive date range: --bad-date-to 2025-04-30 includes all of April 30.
    end = datetime.fromisoformat(bad_date_to).replace(tzinfo=timezone.utc) + timedelta(days=1)

    page = 1

    while True:
        payload = {
            "takenAfter": start.isoformat().replace("+00:00", "Z"),
            "takenBefore": end.isoformat().replace("+00:00", "Z"),
            "type": "IMAGE",
            "size": page_size,
            "page": page,
            "withExif": True,
        }

        data = immich_post(base_url, api_key, "/search/metadata", payload)

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


def main():
    parser = argparse.ArgumentParser(
        description="Fix Immich asset dates for assets clustered on one wrong date/range by parsing the true date from filenames."
    )

    parser.add_argument("--url", required=True)
    parser.add_argument("--key", default=os.getenv("IMMICH_API_KEY"))
    parser.add_argument("--bad-date", help="Single bad Immich timeline date, YYYY-MM-DD")
    parser.add_argument("--bad-date-from", help="Start of bad Immich timeline range, YYYY-MM-DD")
    parser.add_argument("--bad-date-to", help="End of bad Immich timeline range, YYYY-MM-DD, inclusive")
    parser.add_argument("--apply", action="store_true")
    parser.add_argument("--tz-offset", default="+00:00")
    parser.add_argument("--csv", default=None)

    args = parser.parse_args()

    if not args.key:
        raise SystemExit("Missing API key. Set IMMICH_API_KEY or pass --key.")

    bad_date_from, bad_date_to = resolve_bad_date_range(args)

    csv_filename = args.csv or f"immich-date-fix-{bad_date_from}_to_{bad_date_to}.csv"
    tz = parse_tz_offset(args.tz_offset)

    rows = []
    scanned = 0
    matched = 0
    updated = 0
    skipped = 0
    already_correct = 0

    for asset in search_assets_in_bad_date_range(args.url, args.key, bad_date_from, bad_date_to):
        scanned += 1

        filename = get_asset_filename(asset)
        new_dt = parse_filename_dt(filename, tz)

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

        if old_dt.date() == new_dt_utc.date():
            already_correct += 1
            print(f"File {filename} was already on correct date {old_iso}")
            rows.append([asset.get("id"), filename, "ALREADY_CORRECT_DAY", old_iso, new_iso])
            continue

        print(f"File {filename} was corrected from {old_iso} to {new_iso}")

        rows.append([
            asset.get("id"),
            filename,
            "WOULD_CORRECT" if not args.apply else "CORRECTED",
            old_iso,
            new_iso,
        ])

        if args.apply:
            immich_put(
                args.url,
                args.key,
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

    if not args.apply:
        print("Dry-run only. Re-run with --apply to update Immich.")


if __name__ == "__main__":
    main()

