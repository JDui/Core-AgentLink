"""Optional Qt client for Rust v1. All IPC runs off the GUI thread."""
import argparse
from pathlib import Path
import sys

REPO = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(REPO / "python"))
sys.path.insert(0, str(REPO / "examples"))
from cal_sdk import AgentLink, LogProjection
from qt_prompt import PromptPanel
from PySide6 import QtCore, QtWidgets


def quote(value):
    return "'" + str(value).replace("'", "''") + "'"


class Worker(QtCore.QObject):
    completed = QtCore.Signal(object)
    failed = QtCore.Signal(str)
    stopped = QtCore.Signal()

    def __init__(self, client):
        super().__init__()
        self.client = client

    @QtCore.Slot(str, object)
    def execute(self, command, payload):
        try:
            if command != "poll":
                self.client.call(command, payload)
            snapshot = self.client.call("inspect")
            events = self.client.call("events", payload if command == "poll" else {})
            self.completed.emit(dict(snapshot=snapshot, events=events))
        except Exception as exc:
            self.failed.emit(str(exc))


class Panel(QtWidgets.QWidget):
    requested = QtCore.Signal(str, object)
    stop_requested = QtCore.Signal(str, object)

    def __init__(self, client, cli):
        super().__init__()
        self.setWindowTitle("C-AL · Rust Core / Python 工程")
        self.resize(1100, 750)
        self.client, self.cli = client, Path(cli).resolve()
        self.projection = LogProjection()
        self.busy = False
        self.snapshot = None
        self.termination = None
        self.stop_busy = False
        self.status = QtWidgets.QLabel("连接中")
        self.prompt = PromptPanel()
        self.log = QtWidgets.QPlainTextEdit()
        self.log.setReadOnly(True)
        self.log.document().setMaximumBlockCount(1600)
        self.results = QtWidgets.QLabel()
        self.results.setWordWrap(True)
        self.follow = QtWidgets.QCheckBox("追随日志")
        self.follow.setChecked(True)
        self.cancel = QtWidgets.QPushButton("取消接管")
        self.stop_agent = QtWidgets.QPushButton("终止 Agent")
        self.stop_agent.setToolTip("向当前会话的 Agent 发送终止命令，等待 Agent 确认；保留已提交结果")
        self.stop_agent.clicked.connect(self.request_agent_stop)
        self.clear = QtWidgets.QPushButton("清空显示")
        self.cleanup = QtWidgets.QPushButton("清理旧归档")
        self.refresh = QtWidgets.QPushButton("重新生成 Prompt")
        self.cancel.clicked.connect(lambda: self.dispatch("cancel", {}))
        self.cleanup.clicked.connect(lambda: self.dispatch("cleanup", {}))
        self.clear.clicked.connect(self.clear_display)
        self.refresh.clicked.connect(self.generate_prompt)
        header = QtWidgets.QHBoxLayout()
        for widget in [self.status, self.refresh, self.follow, self.cancel, self.stop_agent, self.clear, self.cleanup]:
            header.addWidget(widget)
        splitter = QtWidgets.QSplitter()
        splitter.addWidget(self.prompt)
        splitter.addWidget(self.log)
        layout = QtWidgets.QVBoxLayout(self)
        layout.addLayout(header)
        layout.addWidget(splitter, 1)
        layout.addWidget(self.results)
        self.thread = QtCore.QThread(self)
        self.worker = Worker(client)
        self.worker.moveToThread(self.thread)
        self.requested.connect(self.worker.execute)
        self.worker.completed.connect(self.accept)
        self.worker.failed.connect(self.failed)
        self.thread.finished.connect(self.worker.deleteLater)
        self.thread.start()
        # A separate worker keeps the termination button usable during normal IPC.
        self.stop_thread = QtCore.QThread(self)
        self.stop_worker = StopWorker(client)
        self.stop_worker.moveToThread(self.stop_thread)
        self.stop_requested.connect(self.stop_worker.execute)
        self.stop_worker.completed.connect(self.stop_delivered)
        self.stop_worker.failed.connect(self.stop_failed)
        self.stop_thread.finished.connect(self.stop_worker.deleteLater)
        self.stop_thread.start()
        self.timer = QtCore.QTimer(self)
        self.timer.setInterval(500)
        self.timer.timeout.connect(lambda: self.dispatch("poll", self.projection.query()))
        self.timer.start()
        self.dispatch("poll", self.projection.query())

    def dispatch(self, command, payload):
        if self.busy:
            return
        self.busy = True
        self.cancel.setEnabled(False)
        self.cleanup.setEnabled(False)
        self.requested.emit(command, payload)

    def accept(self, packet):
        self.busy = False
        first = self.snapshot is None
        self.snapshot = packet["snapshot"]
        self.termination = self.snapshot.get("agentControl") or self.termination
        self.projection.accept(packet["events"])
        state = self.snapshot["status"]
        error = self.snapshot["journalError"] or self.snapshot["transportError"] or packet["events"]["error"]
        if self.projection.gap:
            error = error or "部分日志已超出保留窗口"
        self.status.setText(f"{state} · {self.snapshot['agentName'] or '等待Agent'}" + (f" · {error}" if error else ""))
        if self.termination:
            self.show_termination()
        self.stop_agent.setEnabled(not self.stop_busy and not self.termination and state != "finished")
        self.cancel.setEnabled(state in ("active", "waiting"))
        self.cleanup.setEnabled(True)
        self.prompt.copy_button.setEnabled(True)
        scroll = self.log.verticalScrollBar()
        old = scroll.value()
        at_bottom = old >= scroll.maximum() - 2
        lines = [f"{event['operation']} · {event['phase']} | {event['message']}" for event in self.projection.rows]
        self.log.setPlainText("\n".join(lines) or "等待新的操作记录")
        scroll.setValue(scroll.maximum() if self.follow.isChecked() and at_bottom else old)
        clips = self.snapshot["domain"]["clips"]
        self.results.setText("当前工程 revision " + str(self.snapshot["domain"]["projectRevision"]) + "\n" +
                             " | ".join(f"{c['name']} · 轨道{c['track']} · {c['start']}–{c['end']}s" for c in clips))
        if first:
            self.generate_prompt()

    def failed(self, message):
        self.busy = False
        self.status.setText("连接 / 操作异常 · " + message)
        self.cancel.setEnabled(False)
        self.cleanup.setEnabled(False)
        self.prompt.finish_animation()
        self.prompt.copy_button.setEnabled(False)

    def request_agent_stop(self):
        if self.stop_busy or self.termination:
            return
        self.stop_busy = True
        self.stop_agent.setEnabled(False)
        self.stop_requested.emit("stop-agent", {"reason": "用户点击终止 Agent"})

    def stop_delivered(self, signal):
        self.stop_busy = False
        self.termination = signal
        self.show_termination()
        self.prompt.finish_animation()

    def show_termination(self):
        self.status.setText("Agent 已确认终止" if self.termination["status"] == "acknowledged" else "终止命令已发送，等待 Agent 确认")

    def stop_failed(self, message):
        self.stop_busy = False
        self.stop_agent.setEnabled(True)
        self.status.setText(("终止命令状态未知，请查询 control · " if "UnknownResult" in message else "终止命令发送失败 · ") + message)

    def clear_display(self):
        self.projection.clear()
        self.log.clear()

    def generate_prompt(self):
        if not self.snapshot:
            return
        prefix = f"& {quote(self.cli)} <command> --state-dir {quote(self.client.root)} --project-id demo --session {self.client.session_id}"
        self.prompt.set_prompt(f"控制当前 C-AL 演示工程，保留用户已有片段。\nCLI：{prefix}\n"
            f"协议：{REPO / 'docs/08-protocol-v1.md'}\n提案例：{REPO / 'examples/rust_python/proposal.json'}\n"
            "先 identify --name <真实名称>，再 inspect；按最新 domain.projectRevision 制作提案。\n"
            "apply --proposal <文件> --dry-run 后实际 apply；保留 runId，再 inspect 确认真实片段。\n"
            "log --message <依据> 反馈进度；未知进度不编造百分比。超时先 inspect，不盲重试。\n"
            "每个步骤前以及长任务期间定期调用 control 检查终止命令；非 null 时立即停止工作，调用 ack-stop 确认后结束任务。\n"
            "finish --summary <结果> 前必须留下本会话的实际片段。取消 / 旧会话立即停止写入。\n"
            "本例没有渲染或音频，不能宣称视觉 / 听觉验收。")

    def closeEvent(self, event):
        if self.busy or self.stop_busy:
            self.status.setText("正在等待当前 IPC 返回后关闭，请稍后关闭窗口")
            event.ignore()
            return
        self.timer.stop()
        self.thread.quit()
        self.thread.wait(2000)
        self.stop_thread.quit()
        self.stop_thread.wait(2000)
        super().closeEvent(event)


class StopWorker(QtCore.QObject):
    completed = QtCore.Signal(object)
    failed = QtCore.Signal(str)

    def __init__(self, client):
        super().__init__()
        self.client = client

    @QtCore.Slot(str, object)
    def execute(self, command, payload):
        try:
            self.completed.emit(self.client.call(command, payload))
        except Exception as exc:
            self.failed.emit(str(exc))


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--state-dir", required=True)
    parser.add_argument("--session", required=True)
    parser.add_argument("--cli", required=True)
    args = parser.parse_args()
    app = QtWidgets.QApplication(sys.argv)
    panel = Panel(AgentLink(args.state_dir, args.session, "demo"), args.cli)
    panel.show()
    sys.exit(app.exec())

