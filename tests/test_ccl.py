import numpy as np

from src.core.ccl import components, dilate


def test_two_separate_blobs_are_two_components():
    m = np.zeros((10, 10), bool)
    m[1:3, 1:3] = True
    m[6:9, 5:9] = True
    c = components(m, eight=True, want_labels=True)
    assert c.count == 2
    boxes = sorted(map(tuple, c.boxes.tolist()))
    assert boxes == [(1, 1, 2, 2), (5, 6, 8, 8)]
    assert sorted(c.sizes.tolist()) == [4, 12]
    assert c.labels[1, 1] != c.labels[6, 5] and c.labels[0, 0] == 0


def test_diagonal_touch_joins_only_with_eight_connectivity():
    m = np.zeros((5, 5), bool)
    m[1, 1] = m[2, 2] = True
    assert components(m, eight=True).count == 1
    assert components(m, eight=False).count == 2


def test_shape_that_bends_back_is_one_component():
    m = np.zeros((8, 8), bool)
    m[1:7, 1] = True
    m[6, 1:7] = True
    m[1:7, 6] = True            # a U shape: the two arms are joined along the bottom
    c = components(m, eight=False)
    assert c.count == 1 and tuple(c.boxes[0]) == (1, 1, 6, 6)


def test_empty_picture():
    c = components(np.zeros((4, 4), bool))
    assert c.count == 0


def test_dilate_grows_a_square():
    m = np.zeros((9, 9), bool)
    m[4, 4] = True
    d = dilate(m, 2)
    assert d[2:7, 2:7].all() and d.sum() == 25
    assert dilate(m, 0).sum() == 1
