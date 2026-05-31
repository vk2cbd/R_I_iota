import pytest

from radio_interferometer.gui import format_ra_hours, parse_ra_hours_text


def test_parse_ra_hours_accepts_hms_and_decimal_hours() -> None:
    assert parse_ra_hours_text("04:31:39.6") == pytest.approx(4.527667, abs=1e-6)
    assert parse_ra_hours_text("4.527667") == pytest.approx(4.527667, abs=1e-6)


def test_format_ra_hours_returns_hms_display() -> None:
    assert format_ra_hours(67.9186 / 15.0) == "04:31:40.5"


def test_parse_ra_hours_rejects_degree_like_value() -> None:
    with pytest.raises(ValueError):
        parse_ra_hours_text("67.9186")
