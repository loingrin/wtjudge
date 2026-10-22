"""Quiet translucent surfaces over an application-owned diffuse backdrop."""
from PySide6.QtCore import QPointF, QRectF, Qt
from PySide6.QtGui import QColor, QIcon, QPainter, QPainterPath, QPen, QPixmap, QRadialGradient
from PySide6.QtWidgets import QGraphicsDropShadowEffect, QWidget

from wtjudge.presentation import STATUS_COLOURS


class GlassBackdrop(QWidget):
    """Paint soft light beneath alpha surfaces without assuming OS blur APIs."""
    def paintEvent(self, event):
        painter = QPainter(self)
        painter.setRenderHint(QPainter.RenderHint.Antialiasing)
        painter.fillRect(self.rect(), QColor("#edf0ed"))
        for x, y, radius, colour in [(.05, .93, .70, "#c4c1a6"), (.90, .02, .78, "#d9e4d3"), (.88, .90, .68, "#d9dfee")]:
            centre = QPointF(self.width() * x, self.height() * y)
            gradient = QRadialGradient(centre, max(self.width(), self.height()) * radius)
            colour = QColor(colour)
            colour.setAlpha(130)
            gradient.setColorAt(0, colour)
            colour.setAlpha(0)
            gradient.setColorAt(1, colour)
            painter.fillRect(self.rect(), gradient)


def soft_shadow(widget):
    effect = QGraphicsDropShadowEffect(widget)
    effect.setBlurRadius(32)
    effect.setOffset(0, 6)
    effect.setColor(QColor(45, 65, 50, 22))
    widget.setGraphicsEffect(effect)


def line_icon(kind, colour="#89988d"):
    pixmap = QPixmap(22, 22)
    pixmap.fill(Qt.GlobalColor.transparent)
    p = QPainter(pixmap)
    p.setRenderHint(QPainter.RenderHint.Antialiasing)
    p.setPen(QPen(QColor(colour), 1.5, Qt.PenStyle.SolidLine, Qt.PenCapStyle.RoundCap, Qt.PenJoinStyle.RoundJoin))
    p.setBrush(Qt.BrushStyle.NoBrush)
    if kind == "folder":
        path = QPainterPath(QPointF(3, 6))
        path.lineTo(9, 6); path.lineTo(11, 8); path.lineTo(19, 8)
        path.lineTo(19, 17); path.lineTo(3, 17); path.closeSubpath()
        p.drawPath(path)
    elif kind == "settings":
        for x, centre in [(5, 9), (11, 14), (17, 7)]:
            p.drawLine(x, 4, x, 18)
            p.setBrush(QColor("#f7faf6"))
            p.drawEllipse(QPointF(x, centre), 2.1, 2.1)
    elif kind == "play":
        path = QPainterPath(QPointF(7, 4))
        path.lineTo(18, 11); path.lineTo(7, 18); path.closeSubpath()
        p.drawPath(path)
    elif kind == "chart":
        p.drawLine(4, 18, 19, 18)
        p.drawRoundedRect(QRectF(5, 11, 2, 7), 1, 1)
        p.drawRoundedRect(QRectF(10, 7, 2, 11), 1, 1)
        p.drawRoundedRect(QRectF(15, 4, 2, 14), 1, 1)
    elif kind == "export":
        p.drawLine(11, 3, 11, 13)
        p.drawLine(7, 9, 11, 13); p.drawLine(15, 9, 11, 13)
        path = QPainterPath(QPointF(4, 12))
        path.lineTo(4, 18); path.lineTo(18, 18); path.lineTo(18, 12)
        p.drawPath(path)
    p.end()
    icon = QIcon(pixmap)
    icon.addPixmap(pixmap, QIcon.Mode.Selected, QIcon.State.Off)
    return icon


GLASS_STYLE = """
QMainWindow { background: #edf0ed; }
QWidget { font-family: "Segoe UI", "Microsoft YaHei UI"; font-size: 13px; color: #35413a; }
QFrame#applicationShell { background: rgba(255,255,255,205); border: 1px solid rgba(255,255,255,240); border-radius: 20px; }
QWidget#sidebar { background: rgba(255,255,255,183); border: 0; border-right: 1px solid rgba(223,231,223,140); border-top-left-radius: 20px; border-bottom-left-radius: 20px; }
QLabel#brand { color: #446e35; font-size: 21px; font-weight: 650; }
QListWidget#navigation { background: transparent; border: 0; outline: 0; color: #8c978e; }
QListWidget#navigation::item { padding: 14px 10px; margin: 3px 7px; border: 0; border-radius: 8px; }
QListWidget#navigation::item:hover { background: rgba(232,241,225,140); }
QListWidget#navigation::item:selected { background: rgba(224,239,211,185); color: #476d34; }
QWidget#workPage, QScrollArea, QScrollArea>QWidget>QWidget { background: transparent; border: 0; }
QFrame#topBar { background: transparent; border: 0; }
QLabel#examCaption { color: #405345; font-size: 14px; font-weight: 600; }
QLabel#heading { color: #2d3931; font-size: 24px; font-weight: 600; padding: 0 0 8px 0; }
QFrame#surface { background: rgba(255,255,255,195); border: 1px solid rgba(255,255,255,240); border-radius: 14px; }
QFrame#metric { background: transparent; border: 0; }
QLabel#metricValue { color: #526d41; font-size: 21px; font-weight: 600; }
QLabel#metricLabel { color: #929b91; font-size: 12px; }
QLabel#notice { color: #6c7f64; background: transparent; border: 0; padding: 3px 0; }
QLabel#notice[tone="warning"] { background: rgba(255,243,216,210); color: #936a27; border-radius: 9px; padding: 10px 12px; }
QLabel#notice[tone="error"] { background: rgba(253,234,229,215); color: #ac5749; border-radius: 9px; padding: 10px 12px; }
QLabel#stage { color: #536b46; font-size: 17px; padding: 6px 0; }
QLabel#count { color: #879283; padding: 3px 0; }
QPushButton { background: rgba(255,255,255,215); border: 1px solid #e0e7dc; border-radius: 8px; padding: 8px 14px; min-height: 18px; }
QPushButton:hover { background: #f3f8ef; border-color: #bacfa9; }
QPushButton:pressed { background: #e2edd9; }
QPushButton:disabled { color: #b0b9ac; background: rgba(243,246,240,160); border-color: #e8ede4; }
QPushButton#primary { background: #91af76; color: white; border: 1px solid #91af76; font-weight: 600; }
QPushButton#primary:hover { background: #829f68; border-color: #829f68; }
QPushButton#primary:disabled { background: #c5d4b7; border-color: #c5d4b7; }
QPushButton#quiet { background: transparent; border: 0; color: #85917d; padding: 5px 10px; min-height: 18px; }
QPushButton#quiet:hover { background: rgba(227,238,218,160); color: #52763d; }
QPushButton#stop { color: #ae6b5e; border-color: #e6cbc2; }
QPushButton#stop:hover { background: #fff1ec; }
QLineEdit, QSpinBox, QComboBox { background: rgba(255,255,255,210); border: 1px solid #e3e9e0; border-radius: 8px; padding: 7px 10px; selection-background-color: #b7cea2; }
QLineEdit:focus, QSpinBox:focus, QComboBox:focus { border: 1px solid #a2bd89; background: white; }
QLineEdit:disabled, QSpinBox:disabled, QComboBox:disabled { background: rgba(242,246,238,150); color: #b0b8a9; }
QComboBox::drop-down { border: 0; width: 20px; }
QTableWidget { background: rgba(255,255,255,205); alternate-background-color: rgba(246,249,243,120); border: 1px solid rgba(255,255,255,240); border-radius: 12px; selection-background-color: #e5efdc; selection-color: #435f30; gridline-color: transparent; }
QHeaderView::section { background: #f3f6f0; color: #8c9986; padding: 10px 9px; border: 0; border-bottom: 1px solid #eaf0e5; font-weight: 500; }
QTableWidget::item { padding: 6px; border: 0; border-bottom: 1px solid rgba(230,237,224,150); }
QPlainTextEdit { background: rgba(255,255,255,185); border: 1px solid rgba(225,232,220,180); border-radius: 10px; padding: 8px; selection-background-color: #c4d8ad; }
QPlainTextEdit#executionLog { font-family: "Cascadia Mono", "Consolas", "Microsoft YaHei UI"; font-size: 12px; }
QProgressBar { background: #e9eee3; border: 0; border-radius: 5px; text-align: center; height: 20px; color: #7c8e6e; }
QProgressBar::chunk { background: #a8c98b; border-radius: 5px; }
QStatusBar { background: transparent; color: #899680; border: 0; }
QCheckBox { spacing: 8px; }
QScrollBar:vertical { width: 8px; background: transparent; margin: 1px; }
QScrollBar::handle:vertical { background: #d6dfcf; min-height: 26px; border-radius: 3px; }
QScrollBar::add-line:vertical, QScrollBar::sub-line:vertical { height: 0; }
QDialog { background: #f5f7f2; }
"""

def colour_status(item, status):
    background, foreground = STATUS_COLOURS.get(status, ("#f2f7ed", "#6e835b"))
    item.setBackground(QColor(background))
    item.setForeground(QColor(foreground))


def notice_tone(widget, tone):
    widget.setProperty("tone", tone)
    widget.style().unpolish(widget)
    widget.style().polish(widget)
