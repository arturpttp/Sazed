from sazed.core.outcomes import NoSuchMonitor, SingleMonitor
from sazed.skills.pc.windows import Monitor, Rect, half, move_between, target_monitor

MAIN = Rect(0, 0, 1920, 1040)
LEFT = Rect(-1280, 0, 0, 984)  # a monitor left of the primary


def test_halves_split_the_work_area() -> None:
    assert half(MAIN, "esquerda") == Rect(0, 0, 960, 1040)
    assert half(MAIN, "direita") == Rect(960, 0, 1920, 1040)


def test_odd_widths_leave_no_gap() -> None:
    work = Rect(0, 0, 1366, 728)
    assert half(work, "esquerda").right == half(work, "direita").left


def test_moving_keeps_relative_position_and_size() -> None:
    rect = Rect(480, 260, 1440, 780)  # centred, half the size
    assert move_between(rect, MAIN, LEFT) == Rect(-960, 246, -320, 738)


def test_moving_back_returns_to_the_same_place() -> None:
    rect = Rect(480, 260, 1440, 780)
    assert move_between(move_between(rect, MAIN, LEFT), LEFT, MAIN) == rect


def test_moving_clamps_inside_the_destination() -> None:
    rect = Rect(1800, 900, 2400, 1300)  # partly off the main screen
    moved = move_between(rect, MAIN, LEFT)
    assert LEFT.left <= moved.left and moved.right <= LEFT.right
    assert LEFT.top <= moved.top and moved.bottom <= LEFT.bottom
    assert moved.width > 0 and moved.height > 0


def test_a_window_bigger_than_the_destination_is_cut_to_it() -> None:
    rect = Rect(-100, -100, 2100, 1200)
    assert move_between(rect, MAIN, LEFT) == LEFT


def test_other_cycles_to_the_next_monitor() -> None:
    mons = [Monitor(1, LEFT, False), Monitor(2, MAIN, True)]
    assert target_monitor(mons, current=2, wanted="outro") == mons[0]
    assert target_monitor(mons, current=1, wanted="outro") == mons[1]


def test_a_number_picks_that_monitor_or_explains() -> None:
    mons = [Monitor(1, LEFT, False), Monitor(2, MAIN, True)]
    assert target_monitor(mons, current=2, wanted=1) == mons[0]
    assert target_monitor(mons, current=2, wanted=3) == NoSuchMonitor(3, 2)
    assert target_monitor(mons, current=2, wanted=0) == NoSuchMonitor(0, 2)


def test_one_monitor_on_means_nowhere_to_go() -> None:
    one = [Monitor(1, MAIN, True)]
    assert target_monitor(one, current=1, wanted="outro") == SingleMonitor()
    assert target_monitor(one, current=1, wanted=2) == SingleMonitor()
