import logging
import threading

from PySide6.QtCore import QThread, Signal


class Worker(QThread):
    event = Signal(str, object)
    succeeded = Signal(object)
    failed = Signal(str)

    def __init__(self, action, parent=None):
        super().__init__(parent)
        self.action = action
        self.cancel = threading.Event()

    def run(self):
        try:
            self.succeeded.emit(self.action(self.cancel, self.event.emit))
        except Exception as error:
            logging.getLogger(__name__).exception("后台任务失败")
            self.failed.emit(f"操作未完成：{error}\n请检查配置、文件权限和磁盘空间。完整诊断已写入本地日志。")
