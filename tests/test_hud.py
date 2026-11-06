import numpy as np

from detection import hud


def test_backpack_ladder_known_points():
    assert hud.backpack_percent_from_rgb(0xF7, 0x00, 0x17) == 100
    # Grey (unlit bar background) is not a bar colour
    assert hud.backpack_percent_from_rgb(0x75, 0x75, 0x75) is None
    # Pure black is not a bar colour
    assert hud.backpack_percent_from_rgb(0, 0, 0) is None


def test_backpack_ladder_bands_in_order():
    # (red low exclusive, red high inclusive, gb low exclusive, gb high inclusive, percent)
    # transcribed from the ladder; the 0 percent band in Natro is unreachable
    # (its bounds are inverted), so an empty bar reads None and the filter maps it to 0.
    bands = [
        (0x41, 0x42, 0xFC85, 0xFF80, 5), (0x42, 0x44, 0xF984, 0xFE85, 10),
        (0x44, 0x47, 0xF582, 0xFB84, 15), (0x47, 0x4B, 0xF080, 0xF782, 20),
        (0x4B, 0x4F, 0xEA7D, 0xF280, 25), (0x4F, 0x55, 0xE37A, 0xEC7D, 30),
        (0x55, 0x5B, 0xDA76, 0xE57A, 35), (0x5B, 0x62, 0xD072, 0xDC76, 40),
        (0x62, 0x69, 0xC66D, 0xD272, 45), (0x69, 0x72, 0xBA68, 0xC86D, 50),
        (0x72, 0x7B, 0xAD62, 0xBC68, 55), (0x7B, 0x85, 0x9E5C, 0xAF62, 60),
        (0x85, 0x90, 0x8F55, 0xA05C, 65), (0x90, 0x9C, 0x7E4E, 0x9155, 70),
        (0x9C, 0xA9, 0x6C46, 0x804E, 75), (0xA9, 0xB6, 0x5A3F, 0x6E46, 80),
        (0xB6, 0xC4, 0x4637, 0x5D3F, 85), (0xC4, 0xD3, 0x322E, 0x4A37, 90),
        (0xD3, 0xDF, 0x2000, 0x342E, 95), (0xE0, 0xFF, 0x1000, 0x2427, 100),
    ]
    last = -1
    for r_lo, r_hi, gb_lo, gb_hi, expected in bands:
        r = (r_lo + 1 + r_hi) // 2
        gb = (gb_lo + 1 + gb_hi) // 2
        got = hud.backpack_percent_from_rgb(r, gb >> 8, gb & 0xFF)
        assert got == expected, (hex(hud.rgb_to_int(r, gb >> 8, gb & 0xFF)), got, expected)
        assert got > last
        last = got


def test_backpack_filter_averages_and_counts_unreadable():
    f = hud.BackpackFilter(size=3)
    assert f.push(None) == 0 and f.unreadable_streak == 1
    assert f.push(90) == 45 and f.unreadable_streak == 0   # the None counted as 0
    assert f.push(100) == 63
    f.push(100)
    f.push(100)
    assert f.value == 100
    f.reset()
    assert f.value == 0


def test_grey_detection_band():
    assert hud.is_grey(0x4D, 0x4D, 0x4D)
    assert hud.is_grey(0x83, 0x83, 0x83)
    assert not hud.is_grey(0x4C, 0x60, 0x60)
    assert not hud.is_grey(0xF0, 0x20, 0x20)


def test_count_colour_and_hls_range():
    img = np.zeros((4, 4, 3), dtype=np.uint8)
    img[0, :] = (255, 0, 0)
    img[1, :2] = (250, 5, 5)
    assert hud.count_colour(img, (255, 0, 0), tolerance=6) == 6
    assert hud.count_colour(img, (255, 0, 0), tolerance=0) == 4
    # Red hue around 0 degrees, lightness 50, saturation 100
    assert hud.count_hls_range(img, (0, 40, 90), (10, 60, 100)) == 6
    # White has lightness 100
    white = np.full((2, 2, 3), 255, dtype=np.uint8)
    assert hud.count_hls_range(white, (0, 95, 0), (360, 100, 100)) == 4


def test_find_template_locates_and_rejects():
    rng = np.random.default_rng(1)
    img = rng.integers(0, 255, size=(60, 80, 3), dtype=np.uint8)
    tpl = img[20:28, 30:42].copy()
    assert hud.find_template(img, tpl, tolerance=0) == (30, 20)
    # Small noise within tolerance still matches
    noisy = np.clip(tpl.astype(int) + rng.integers(-3, 4, size=tpl.shape), 0, 255).astype(np.uint8)
    assert hud.find_template(img, noisy, tolerance=4) == (30, 20)
    # Noise above tolerance does not
    assert hud.find_template(img, noisy, tolerance=1) is None
    # Template bigger than image
    assert hud.find_template(tpl, img) is None
    # Sampling every second pixel still finds it
    assert hud.find_template(img, tpl, tolerance=0, step=2) == (30, 20)
