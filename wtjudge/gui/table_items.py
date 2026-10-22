"""Table painting that keeps score and verdict colours visible when selected."""
from PySide6.QtCore import Qt
from PySide6.QtGui import QColor, QPalette, QPen
from PySide6.QtWidgets import QStyle, QStyledItemDelegate, QStyleOptionViewItem


class ColourPreservingDelegate(QStyledItemDelegate):
    def paint(self, painter, option, index):
        selected = bool(option.state & QStyle.StateFlag.State_Selected)
        background = index.data(Qt.ItemDataRole.BackgroundRole)
        coloured = background is not None and background.style() != Qt.BrushStyle.NoBrush
        if not coloured:
            return super().paint(painter, option, index)

        preserved = QStyleOptionViewItem(option)
        self.initStyleOption(preserved, index)
        painter.save()
        painter.setClipRect(option.rect)
        # A stylesheet item panel can cover BackgroundRole even without an
        # explicit background declaration. Paint these simple text cells
        # directly, so both the heatmap and verdicts remain opaque and stable.
        painter.fillRect(option.rect, background)
        painter.setFont(preserved.font)
        foreground = index.data(Qt.ItemDataRole.ForegroundRole)
        painter.setPen(foreground.color() if foreground is not None else preserved.palette.color(QPalette.ColorRole.Text))
        text_rect = option.rect.adjusted(6, 3, -6, -3)
        text = preserved.fontMetrics.elidedText(preserved.text, preserved.textElideMode, text_rect.width())
        painter.drawText(text_rect, int(preserved.displayAlignment | Qt.AlignmentFlag.AlignVCenter), text)
        if selected:
            # An outline retains selection without hiding the colour's meaning.
            colour = QColor("#ffffff" if background.color().lightness() < 125 else "#426338")
            colour.setAlpha(190)
            painter.setPen(QPen(colour, 1))
            painter.setBrush(Qt.BrushStyle.NoBrush)
            painter.drawRect(option.rect.adjusted(1, 1, -2, -2))
        painter.restore()
