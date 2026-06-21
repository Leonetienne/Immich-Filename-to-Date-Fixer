from datetime import datetime, timezone

from filename_parsing import parse_filename_dt

UTC = timezone.utc


def test_underscore_datetime():
    dt, has_time = parse_filename_dt("IMG_20230312_130300_383.jpg", UTC)
    assert dt == datetime(2023, 3, 12, 13, 3, 0, tzinfo=UTC)
    assert has_time is True


def test_hyphen_datetime():
    dt, has_time = parse_filename_dt("IMG-20230312-130300.jpg", UTC)
    assert dt == datetime(2023, 3, 12, 13, 3, 0, tzinfo=UTC)
    assert has_time is True


def test_bare_datetime():
    dt, has_time = parse_filename_dt("20260605_123049.jpg", UTC)
    assert dt == datetime(2026, 6, 5, 12, 30, 49, tzinfo=UTC)
    assert has_time is True


def test_whatsapp_caption():
    dt, has_time = parse_filename_dt(
        "WhatsApp Image 2026-06-22 at 14.37.05.jpeg", UTC
    )
    assert dt == datetime(2026, 6, 22, 14, 37, 5, tzinfo=UTC)
    assert has_time is True


def test_whatsapp_android_date_only():
    dt, has_time = parse_filename_dt("IMG-20260622-WA0001.jpg", UTC)
    assert dt == datetime(2026, 6, 22, 12, 0, 0, tzinfo=UTC)
    assert has_time is False


def test_date_only_fallback():
    dt, has_time = parse_filename_dt("IMG-20201026-WA0000.jpg", UTC)
    assert dt == datetime(2020, 10, 26, 12, 0, 0, tzinfo=UTC)
    assert has_time is False


def test_invalid_month_is_skipped():
    dt, has_time = parse_filename_dt("PXL_20232312.jpg", UTC)
    assert dt is None
    assert has_time is False


def test_invalid_time_does_not_fall_back_to_date_only():
    dt, has_time = parse_filename_dt("IMG_20230312_250000.jpg", UTC)
    assert dt is None
    assert has_time is False


def test_no_date_in_filename():
    dt, has_time = parse_filename_dt("vacation_photo.jpg", UTC)
    assert dt is None
    assert has_time is False


def test_full_path_is_reduced_to_basename():
    dt, has_time = parse_filename_dt("/some/dir/IMG_20230312_130300_383.jpg", UTC)
    assert dt == datetime(2023, 3, 12, 13, 3, 0, tzinfo=UTC)
    assert has_time is True


def test_timezone_is_preserved():
    tz = timezone.utc
    dt, _ = parse_filename_dt("IMG_20230312_130300_383.jpg", tz)
    assert dt.tzinfo == tz
