#!python3
import argparse
import getpass
import os

from fix import (
    add_common_arguments,
    immich_post,
    parse_tz_offset,
    resolve_bad_date_range,
    run,
)


def bearer_headers(access_token):
    return {"Authorization": f"Bearer {access_token}", "Content-Type": "application/json"}


def login(base_url, email, password):
    data = immich_post(
        base_url,
        {"Content-Type": "application/json"},
        "/auth/login",
        {"email": email, "password": password},
    )
    return data["accessToken"]


def unlock_session(base_url, headers, pin_code):
    immich_post(base_url, headers, "/auth/session/unlock", {"pinCode": pin_code})


def lock_session(base_url, headers):
    immich_post(base_url, headers, "/auth/session/lock", {})


def main():
    parser = argparse.ArgumentParser(
        description="Fix Immich asset dates for Locked Folder assets clustered on one wrong date/range, "
                     "by parsing the true date from filenames."
    )
    add_common_arguments(parser)
    parser.add_argument("--login-email", default=os.getenv("IMMICH_LOGIN_EMAIL"),
                         help="Immich account email used to log in (env IMMICH_LOGIN_EMAIL). Prompted if omitted.")
    parser.add_argument("--login-pass", default=os.getenv("IMMICH_LOGIN_PASS"),
                         help="Immich account password used to log in (env IMMICH_LOGIN_PASS). Prompted if omitted.")
    parser.add_argument("--locked-pin", default=os.getenv("IMMICH_LOCKED_PIN"),
                         help="Locked Folder PIN code (env IMMICH_LOCKED_PIN). Prompted if omitted.")

    args = parser.parse_args()

    bad_date_from, bad_date_to = resolve_bad_date_range(args)

    email = args.login_email or input("Immich login email: ")
    password = args.login_pass or getpass.getpass("Immich login password: ")
    pin_code = args.locked_pin or getpass.getpass("Locked Folder PIN: ")

    csv_filename = args.csv or f"immich-date-fix-locked-{bad_date_from}_to_{bad_date_to}.csv"
    tz = parse_tz_offset(args.tz_offset)

    access_token = login(args.url, email, password)
    headers = bearer_headers(access_token)
    unlock_session(args.url, headers, pin_code)

    try:
        run(
            args.url,
            headers,
            bad_date_from,
            bad_date_to,
            tz,
            csv_filename,
            args.apply,
            args.fix_time,
            visibility="locked",
        )
    finally:
        lock_session(args.url, headers)


if __name__ == "__main__":
    main()
