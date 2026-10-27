"""What both windows do with the output panel: rebuild it after a change, choose a folder, ask Replace or Cancel,
and save the ticked sheets. A window that uses it provides `output`, `save_action`, `_out_timer`, `_build_output()`
(returning (Result, refused_html) or None) and `_has_content()`."""
from __future__ import annotations

from pathlib import Path

from PySide6.QtWidgets import QFileDialog, QMessageBox

from ..io.save import save_sheets

TITLE = "RunSpriteRun Sheet Converter"


class OutputMixin:
    def _schedule_output(self) -> None:
        self._out_timer.start()

    def _rebuild_output(self) -> None:
        built = self._build_output()
        if built is None:
            return
        result, refused = built
        self.output.show_result(result, self.output.ticks(), self.output.current_name(), refused)
        self.save_action.setEnabled(self.output.save_button.isEnabled())

    def _ticks_changed(self) -> None:
        self.save_action.setEnabled(self.output.save_button.isEnabled())

    def _browse(self) -> None:
        folder = QFileDialog.getExistingDirectory(self, "Save sheets to", str(self.output.folder))
        if folder:
            self.output.set_folder(Path(folder))

    def _ask_replace(self, paths: list[Path]) -> bool:
        names = "\n".join(p.name for p in paths)
        box = QMessageBox(self)
        box.setWindowTitle(TITLE)
        box.setIcon(QMessageBox.Question)
        box.setText(f"{'This file already exists' if len(paths) == 1 else 'These files already exist'} in "
                    f"{paths[0].parent}:\n\n{names}\n\nReplace {'it' if len(paths) == 1 else 'them'}?")
        replace = box.addButton("Replace", QMessageBox.AcceptRole)
        box.addButton("Cancel", QMessageBox.RejectRole)
        box.exec()
        return box.clickedButton() is replace

    def save_now(self) -> None:
        if not self._has_content() or not self.output.sheets:
            return
        if self._out_timer.isActive():
            self._out_timer.stop()
            self._rebuild_output()
        try:
            written = save_sheets(self.output.sheets, self.output.folder, self._ask_replace)
        except OSError as exc:
            QMessageBox.warning(self, TITLE, str(exc))
            return
        if written:
            self.output.show_saved(f"Saved {len(written)} sheet{'s' if len(written) != 1 else ''} to "
                                   f"{self.output.folder}.")
        else:
            self.output.show_saved("Nothing was saved.")
