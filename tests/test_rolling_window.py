"""EMA and RollingWindow maths."""
import time

from utils.rolling_window import EMA, RollingWindow


def test_ema_seeds_then_smooths():
    ema = EMA(alpha=0.5)
    assert not ema.is_seeded
    assert ema.update(10.0) == 10.0
    assert ema.is_seeded
    assert ema.update(20.0) == 15.0
    ema.reset()
    assert not ema.is_seeded


def test_rolling_window_keeps_only_maxsize_and_prunes_by_age():
    now = time.monotonic()
    w = RollingWindow(maxsize=3)
    for i, v in enumerate([1.0, 2.0, 3.0, 4.0]):
        w.push(v, ts=now - 100 + i)          # all about 100 s old
    assert w.count == 3
    assert w.values == [2.0, 3.0, 4.0]
    assert w.latest == 4.0
    w.push(5.0, ts=now)                       # one fresh sample
    w.prune(max_age_sec=10.0)
    assert w.values == [5.0]
