"""The six real sheets the owner supplied on 16 Oct 2026 (the sample set). The counts are the ones the first version
finds; they guard against the detection getting worse, and are updated on purpose when it gets better."""
from pathlib import Path

from PIL import Image

from src.core import layout, output
from src.core.detect import Options, analyse

SAMPLES = Path(__file__).parent / "samples"


def run(name, **kw):
    o = Options(**kw)
    a = analyse(Image.open(SAMPLES / f"{name}.png"), o)
    return a, layout.make_groups(a, o), o


def test_commando_is_six_lattices_of_8_by_6_cells():
    a, groups, o = run("commando")
    kept = a.kept()
    assert len(kept) == 288 and {s.kind for s in kept} == {"grid"}
    assert len(groups) == 1 and groups[0].count == 288
    assert 55 <= groups[0].width <= 62 and 55 <= groups[0].height <= 62
    res = output.build_sheets(a, groups, "commando", o)
    assert [s.count for s in res.sheets] == [120, 120, 48]


def test_samurai_cells_are_frames():
    a, groups, o = run("samurai")
    assert sum(1 for s in a.kept() if s.kind == "cell") >= 140
    assert len(a.kept()) >= 190


def test_barbarian_cells_keep_magenta_out_of_the_sprites():
    a, groups, o = run("barbarian")
    assert len(a.kept()) >= 78
    res = output.build_sheets(a, groups, "barbarian", o)
    assert not any("exactly (255, 0, 255)" in m for s in res.sheets for m in s.messages)


def test_sonic_cells_and_text():
    a, groups, o = run("sonic_2")
    cells = [s for s in a.kept() if s.kind == "cell"]
    assert len(cells) >= 220
    assert sum(1 for s in a.shapes if s.removed and s.reason == "text") >= 80
    assert max(g.count for g in groups) >= 190                      # the 60 x 59 blocks


def test_turrican_loose_sprites_on_a_transparent_background():
    a, groups, o = run("turrican_2")
    assert a.background == -1
    assert 45 <= len(a.kept()) <= 56
    assert len(groups) == 1


def test_streets_of_rage_loose_sprites_in_rows():
    a, groups, o = run("streets_of_rage_2")
    assert 140 <= len(a.kept()) <= 156
    assert sum(g.count for g in groups) == len(a.kept())
    assert all(not g.problem for g in groups)


def test_same_size_for_all_gives_one_group_on_every_sheet():
    for name in ("turrican_2", "barbarian"):
        a, groups, o = run(name, box_mode="same")
        assert len(groups) == 1
