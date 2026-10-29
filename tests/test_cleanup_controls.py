"""The Clean up / Reduce colours widget on its own (Qt offscreen): the switch is offered for any file, labelled
and ticked to match whether the source is a lossy WebP or already exact."""
import os

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

from PySide6.QtWidgets import QApplication

from src.app.cleanup_controls import CleanupControls

_APP = QApplication.instance() or QApplication([])


def test_a_lossy_file_is_offered_clean_up_pre_ticked():
    c = CleanupControls()
    c.set_file(True, "Medium", "Lossy WebP: 300 colours, cleaned up to 9 (Medium).")
    assert c.switch.text() == "Clean up colours"
    assert c.switch.isChecked() and c.switch.isEnabled()
    assert c.strength.isEnabled()
    assert c.value() == "Medium"


def test_an_exact_file_is_offered_reduce_colours_unticked():
    c = CleanupControls()
    c.set_file(False, None, "12 colours used. Tick Reduce colours to merge the ones closest in value.")
    assert c.switch.text() == "Reduce colours"
    assert not c.switch.isChecked()
    assert c.switch.isEnabled()                        # offered, just off by default
    assert not c.strength.isEnabled()
    assert c.value() is None


def test_ticking_reduce_colours_enables_the_strength_choice():
    c = CleanupControls()
    c.set_file(False, None, "")
    c.switch.setChecked(True)
    assert c.strength.isEnabled()
    assert c.value() is not None
