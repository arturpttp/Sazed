from datetime import datetime, timedelta

from fakes.clock import ManualClock


def test_clock_returns_its_time_and_advances() -> None:
    clock = ManualClock(datetime(2026, 10, 14, 12, 0))
    assert clock() == datetime(2026, 10, 14, 12, 0)
    clock.advance(61)
    assert clock() == datetime(2026, 10, 14, 12, 0) + timedelta(seconds=61)
