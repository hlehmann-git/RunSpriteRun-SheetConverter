from PIL import Image

from src.core.output import OutputSheet
from src.io import save


def sheet(name):
    return OutputSheet(name, Image.new("RGB", (8, 8), (1, 2, 3)), 4, 4, 1)


def test_save_writes_ticked_sheets_only(tmp_path):
    a, b = sheet("a_RSR_4x4.png"), sheet("b_RSR_4x4.png")
    b.save = False
    written = save.save_sheets([a, b], tmp_path / "out")
    assert [p.name for p in written] == ["a_RSR_4x4.png"]
    assert not (tmp_path / "out" / "b_RSR_4x4.png").exists()
    assert Image.open(written[0]).size == (8, 8)


def test_one_replace_or_cancel_question_lists_every_existing_file(tmp_path):
    (tmp_path / "a_RSR_4x4.png").write_bytes(b"old")
    (tmp_path / "b_RSR_4x4.png").write_bytes(b"old")
    asked = []
    sheets = [sheet("a_RSR_4x4.png"), sheet("b_RSR_4x4.png"), sheet("c_RSR_4x4.png")]
    assert save.save_sheets(sheets, tmp_path, lambda files: asked.append(files) or False) == []     # Cancel
    assert len(asked) == 1 and sorted(p.name for p in asked[0]) == ["a_RSR_4x4.png", "b_RSR_4x4.png"]
    assert (tmp_path / "a_RSR_4x4.png").read_bytes() == b"old" and not (tmp_path / "c_RSR_4x4.png").exists()
    written = save.save_sheets(sheets, tmp_path, lambda files: True)                                # Replace
    assert len(written) == 3 and (tmp_path / "a_RSR_4x4.png").read_bytes() != b"old"


def test_the_default_folder_is_documents_runspriterun_converted():
    assert save.default_folder().parts[-3:] == ("Documents", "RunSpriteRun", "Converted")
