from PyQt6.QtWidgets import (
    QWidget,
    QVBoxLayout,
    QGroupBox,
    QTextEdit,
    QLabel,
    QHBoxLayout,
    QPushButton,
    QSizePolicy,
    QSplitter,
)
from PyQt6.QtCore import pyqtSignal, Qt, QEvent
from PyQt6.QtGui import QTextCursor
from core.processor import ProcessedBlock


class TextDetailPanel(QWidget):
    translated_text_changed_externally_signal = pyqtSignal(str, str)

    def __init__(self, parent=None):
        super().__init__(parent)
        self._current_block_id = None
        self._programmatic_update = False
        self._init_ui()

    def _init_ui(self):
        main_layout = QVBoxLayout(self)
        main_layout.setContentsMargins(0, 0, 0, 0)
        main_layout.setSpacing(0)
        self.splitter = QSplitter(Qt.Orientation.Vertical)
        self.splitter.setHandleWidth(10)
        self.original_text_edit = QTextEdit()
        self.original_text_edit.setReadOnly(True)
        self.original_text_edit.setPlaceholderText("原文（只可复制）")
        self.splitter.addWidget(self.original_text_edit)
        self.translated_text_edit = QTextEdit()
        self.translated_text_edit.setPlaceholderText("译文")
        self.translated_text_edit.installEventFilter(self)
        self.splitter.addWidget(self.translated_text_edit)
        self.splitter.setStretchFactor(0, 1)
        self.splitter.setStretchFactor(1, 1)
        main_layout.addWidget(self.splitter)
        self.splitter.setStyleSheet(
            """
            QSplitter::handle {
                background-color: transparent;
            }
        """
        )

    def eventFilter(self, obj, event):
        if obj is self.translated_text_edit:
            if event.type() == QEvent.Type.FocusOut:
                if self._current_block_id is not None and not self._programmatic_update:
                    new_text = self.translated_text_edit.toPlainText()
                    self.translated_text_changed_externally_signal.emit(
                        new_text, str(self._current_block_id)
                    )
        return super().eventFilter(obj, event)

    def update_texts(
        self,
        original_text: str | None,
        translated_text: str | None,
        block_id: str | int | None,
    ):
        self._programmatic_update = True
        current_displayed_original = self.original_text_edit.toPlainText()
        current_displayed_translated = self.translated_text_edit.toPlainText()
        new_original = original_text if original_text is not None else ""
        new_translated = translated_text if translated_text is not None else ""
        if current_displayed_original != new_original:
            self.original_text_edit.setPlainText(new_original)
        if current_displayed_translated != new_translated:
            old_cursor_pos = self.translated_text_edit.textCursor().position()
            self.translated_text_edit.setPlainText(new_translated)
        self._current_block_id = block_id
        self._programmatic_update = False

    def clear_texts(self):
        self._programmatic_update = True
        self._current_block_id = None
        self.original_text_edit.clear()
        self.translated_text_edit.clear()
        self._programmatic_update = False

    def get_current_translated_text(self) -> str:
        return self.translated_text_edit.toPlainText()

    def refresh_block_display(self, block: ProcessedBlock):
        if block:
            self.update_texts(block.original_text, block.translated_text, block.id)
        else:
            self.clear_texts()

    def select_block(self, block: ProcessedBlock | None):
        if block:
            self.update_texts(block.original_text, block.translated_text, block.id)
        else:
            self.clear_texts()

    def set_blocks(self, blocks: list[ProcessedBlock]):
        pass

    def clear_content(self):
        self.clear_texts()
