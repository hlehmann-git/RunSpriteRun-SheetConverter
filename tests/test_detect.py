import numpy as np
from PIL import ImageDraw, ImageFont

from src.core.detect import Options, analyse, key_of
from tests.helpers import blank, make_sprite, opaque_set, paste

RNG = np.random.default_rng


def kept(a):
    return a.kept()


def test_loose_sprites_found_exactly():
    rng = RNG(1)
    sheet = blank(200, 120)
    sprites = [(make_sprite(rng, 20, 30), 10, 10), (make_sprite(rng, 30, 20), 60, 20), (make_sprite(rng, 12, 12), 120, 70),
               (make_sprite(rng, 25, 40), 160, 15)]
    for s, x, y in sprites:
        paste(sheet, s, x, y)
    a = analyse(sheet)
    assert a.background == key_of((0, 128, 128))
    shapes = sorted(kept(a), key=lambda s: s.box[0])
    assert [s.box for s in shapes] == [(x, y, x + s.shape[1] - 1, y + s.shape[0] - 1) for s, x, y in sprites]
    assert all(s.kind == "sprite" for s in shapes)
    for shape, (spr, x, y) in zip(shapes, sprites):
        assert int(shape.mask.sum()) == len(opaque_set(spr))


def test_transparent_background_is_found():
    rng = RNG(2)
    sheet = blank(80, 60, alpha=True)
    paste(sheet, make_sprite(rng, 16, 16), 5, 5)
    paste(sheet, make_sprite(rng, 16, 16), 40, 30)
    a = analyse(sheet)
    assert a.background == -1 and a.had_alpha
    assert len(kept(a)) == 2


def test_background_is_the_commonest_colour_on_the_border():
    sheet = blank(60, 40, bg=(90, 10, 200))
    paste(sheet, make_sprite(RNG(3), 10, 10), 20, 10)
    a = analyse(sheet)
    assert a.background == key_of((90, 10, 200))
    # the user can choose another background colour by hand
    a2 = analyse(sheet, Options(background=key_of((200, 30, 30))))
    assert a2.background == key_of((200, 30, 30))


def test_specks_are_ignored():
    sheet = blank(60, 40)
    paste(sheet, make_sprite(RNG(4), 12, 12), 10, 10)
    sheet.putpixel((50, 5), (255, 255, 255, 255))
    sheet.putpixel((51, 5), (255, 255, 255, 255))
    a = analyse(sheet)
    assert len(kept(a)) == 1
    assert len(kept(analyse(sheet, Options(min_shape=1)))) == 2


def test_pieces_closer_than_the_join_gap_are_one_sprite():
    sheet = blank(120, 40)
    spr = make_sprite(RNG(5), 14, 14)
    paste(sheet, spr, 10, 10)
    paste(sheet, make_sprite(RNG(6), 8, 8), 10 + 14 + 2, 12)       # 2 empty pixels away: joined
    paste(sheet, make_sprite(RNG(7), 8, 8), 70, 12)                # far away: its own sprite
    paste(sheet, make_sprite(RNG(8), 8, 8), 70 + 8 + 6, 12)        # 6 away from that one: separate
    a = analyse(sheet)
    boxes = sorted(s.box for s in kept(a))
    assert boxes[0] == (10, 10, 10 + 14 + 2 + 7, 23)
    assert len(boxes) == 3
    # a Join gap of 0 keeps every piece apart
    assert len(kept(analyse(sheet, Options(join_gap=0)))) == 4
    # a Join gap of 16 joins the last two as well
    assert len(kept(analyse(sheet, Options(join_gap=16)))) == 2


def test_cells_each_become_a_frame_and_the_sprite_keeps_its_place():
    rng = RNG(9)
    sheet = blank(200, 100, bg=(0, 128, 128))
    d = ImageDraw.Draw(sheet)
    cells = [(10, 10, 49, 59), (60, 10, 109, 59), (120, 10, 159, 59)]
    for x0, y0, x1, y1 in cells:
        d.rectangle((x0, y0, x1, y1), fill=(0, 255, 255, 255))
    spr = [make_sprite(rng, 14, 20), make_sprite(rng, 20, 30), make_sprite(rng, 10, 10)]
    offsets = [(5, 8), (15, 10), (28, 40)]
    for (c, s, o) in zip(cells, spr, offsets):
        paste(sheet, s, c[0] + o[0], c[1] + o[1])
    a = analyse(sheet)
    got = sorted(kept(a), key=lambda s: s.box[0])
    assert [s.kind for s in got] == ["cell"] * 3
    assert [s.box for s in got] == cells
    assert a.cell_colour == key_of((0, 255, 255))
    for s, spr_, o in zip(got, spr, offsets):
        ys, xs = np.nonzero(s.mask)
        assert (xs.min(), ys.min()) == o                       # the sprite is where it was inside the cell
        assert int(s.mask.sum()) == len(opaque_set(spr_))      # the cell colour is not part of the sprite


def test_a_panel_holding_cells_is_not_a_cell():
    rng = RNG(10)
    sheet = blank(220, 120, bg=(10, 60, 10))
    d = ImageDraw.Draw(sheet)
    d.rectangle((5, 5, 214, 114), fill=(40, 110, 40, 255))               # the panel
    for x0 in (15, 80, 145):
        d.rectangle((x0, 20, x0 + 50, 90), fill=(10, 60, 10, 255))        # cells, the same colour as the page
    for x0 in (15, 80, 145):
        paste(sheet, make_sprite(rng, 12, 24), x0 + 10, 30)
    a = analyse(sheet)
    cells = [s for s in kept(a) if s.kind == "cell"]
    assert len(cells) == 3 and all(s.width == 51 and s.height == 71 for s in cells)


def test_lines_make_a_lattice_of_cells():
    rng = RNG(11)
    sheet = blank(260, 200, bg=(255, 0, 255))
    d = ImageDraw.Draw(sheet)
    xs = [10 + 50 * i for i in range(5)]          # 4 columns of cells
    ys = [10 + 40 * i for i in range(4)]          # 3 rows
    for y in ys:
        d.line((xs[0], y, xs[-1], y), fill=(255, 222, 33, 255))
    for x in xs:
        d.line((x, ys[0], x, ys[-1]), fill=(255, 44, 211, 255))
    for r in range(3):
        for c in range(4):
            paste(sheet, make_sprite(rng, 16, 20), xs[c] + 8 + (r % 2) * 3, ys[r] + 6)
    a = analyse(sheet)
    cells = kept(a)
    assert len(cells) == 12 and {s.kind for s in cells} == {"grid"}
    assert {(s.width, s.height) for s in cells} == {(49, 39)}
    assert "A" in a.sheet_kinds


def test_text_is_removed_and_the_sprite_stays():
    sheet = blank(240, 90)
    paste(sheet, make_sprite(RNG(12), 20, 30), 10, 40)
    d = ImageDraw.Draw(sheet)
    d.fontmode = "1"                                           # pixel-art text: no grey edges
    d.text((10, 8), "Sonic the Hedgehog", fill=(255, 255, 255, 255), font=ImageFont.load_default(size=10))
    a = analyse(sheet)
    assert len(kept(a)) == 1 and kept(a)[0].box == (10, 40, 29, 69)
    assert any(s.reason == "text" for s in a.shapes)
    b = analyse(sheet, Options(remove_text=False))
    assert len(kept(b)) > 1


def test_palette_strip_is_removed():
    sheet = blank(120, 60)
    paste(sheet, make_sprite(RNG(13), 20, 30), 80, 20)
    d = ImageDraw.Draw(sheet)
    for i, c in enumerate([(255, 0, 0), (0, 255, 0), (0, 0, 255), (255, 255, 0), (10, 10, 10), (250, 250, 250)]):
        d.rectangle((5 + i * 8, 10, 5 + i * 8 + 7, 17), fill=c + (255,))
    a = analyse(sheet)
    assert [s.box for s in kept(a)] == [(80, 20, 99, 49)]
    assert any(s.removed for s in a.shapes)


def test_pictures_larger_than_a_frame_are_removed():
    sheet = blank(300, 200)
    paste(sheet, make_sprite(RNG(14), 150, 20), 10, 10)
    paste(sheet, make_sprite(RNG(15), 20, 20), 10, 100)
    a = analyse(sheet)
    assert len(kept(a)) == 1
    assert [s.reason for s in a.shapes if s.removed] == ["picture"]


def test_nothing_found_gives_a_message():
    a = analyse(blank(50, 50))
    assert not kept(a) and "No sprites were found" in a.messages[0]
