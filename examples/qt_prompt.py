"""Independent Prompt presentation component; optional PySide6 dependency."""
import sys
from PySide6 import QtCore, QtGui, QtWidgets


class PromptEditor(QtWidgets.QPlainTextEdit):
    editRequested = QtCore.Signal()

    def keyPressEvent(self, event):
        # Finish before a keystroke changes text; preserve ordinary selection/copy.
        if event.text() or event.key() in (QtCore.Qt.Key_Backspace, QtCore.Qt.Key_Delete):
            if not event.matches(QtGui.QKeySequence.Copy):
                self.editRequested.emit()
        super().keyPressEvent(event)

    def inputMethodEvent(self, event):
        if event.commitString():
            self.editRequested.emit()
        super().inputMethodEvent(event)

    def insertFromMimeData(self, source):
        self.editRequested.emit()
        super().insertFromMimeData(source)


class PromptPanel(QtWidgets.QWidget):
    def __init__(self):
        super().__init__()
        self.model, self.cursor = "", 0
        self.motion = True
        self.animating = False
        self.dirty = False
        self.editor = PromptEditor()
        self.editor.editRequested.connect(self.finish_animation)
        self.editor.textChanged.connect(self._edited)
        self.copy_button = QtWidgets.QPushButton("复制完整 Prompt")
        self.copy_button.clicked.connect(self.copy_prompt)
        self.motion_box = QtWidgets.QCheckBox("动效")
        self.motion_box.setChecked(True)
        self.motion_box.toggled.connect(self.set_motion_enabled)
        layout = QtWidgets.QVBoxLayout(self)
        layout.addWidget(self.editor)
        layout.addWidget(self.copy_button)
        layout.addWidget(self.motion_box)
        self.timer = QtCore.QTimer(self)
        self.timer.setInterval(33)
        self.timer.timeout.connect(self._advance)
        self.delay = QtCore.QTimer(self)
        self.delay.setSingleShot(True)
        self.delay.timeout.connect(self._begin)

    def _set_text(self, value):
        blocker = QtCore.QSignalBlocker(self.editor)
        self.editor.setPlainText(value)
        del blocker

    def _edited(self):
        self.dirty = True

    def set_prompt(self, value, animate=True):
        self.timer.stop()
        self.delay.stop()
        self.model, self.cursor, self.dirty = value, 0, False
        self.animating = animate and self.motion
        if self.animating:
            self._set_text("少女祈祷中...")
            if self.isVisible():
                self.delay.start(600)
        else:
            self._set_text(value)

    def _begin(self):
        self._set_text("")
        if self.isVisible():
            self.timer.start()

    def _advance(self):
        end = min(len(self.model), self.cursor + 60)
        blocker = QtCore.QSignalBlocker(self.editor)
        self.editor.moveCursor(QtGui.QTextCursor.End)
        self.editor.insertPlainText(self.model[self.cursor:end])
        del blocker
        self.cursor = end
        if end == len(self.model):
            self.animating = False
            self.timer.stop()

    def finish_animation(self):
        self.timer.stop()
        self.delay.stop()
        if self.animating:
            self._set_text(self.model)
            self.cursor = len(self.model)
        self.animating = False

    def copy_prompt(self):
        self.finish_animation()
        QtWidgets.QApplication.clipboard().setText(self.editor.toPlainText() if self.dirty else self.model)

    def set_motion_enabled(self, enabled):
        self.motion = enabled
        if not enabled:
            self.finish_animation()

    def showEvent(self, event):
        super().showEvent(event)
        if self.animating:
            if self.cursor:
                self.timer.start()
            else:
                self.delay.start(600)

    def hideEvent(self, event):
        self.timer.stop()
        self.delay.stop()
        super().hideEvent(event)

    def closeEvent(self, event):
        self.timer.stop()
        self.delay.stop()
        super().closeEvent(event)


if __name__ == "__main__":
    app = QtWidgets.QApplication(sys.argv)
    panel = PromptPanel()
    panel.setWindowTitle("C-AL · Prompt 动画参考")
    panel.resize(720, 500)
    panel.set_prompt("先 identify 当前 session，再 inspect 当前工程；dry-run 后 apply。\n"
                     "保留用户已有对象，超时先 inspect，不盲重试；实际结果通过验证后 finish。\n" * 10)
    panel.show()
    sys.exit(app.exec())

