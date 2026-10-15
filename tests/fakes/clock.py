from datetime import datetime, timedelta


class ManualClock:
    def __init__(self, start: datetime = datetime(2026, 10, 14, 12, 0)) -> None:
        self.now = start

    def __call__(self) -> datetime:
        return self.now

    def advance(self, seconds: float) -> None:
        self.now += timedelta(seconds=seconds)
