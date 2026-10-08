from datetime import datetime
from PySide6.QtCore import QAbstractListModel, QModelIndex, Qt, QSize
from PySide6.QtGui import QColor, QPen
from PySide6.QtWidgets import QStyledItemDelegate, QStyle
from ..models import Idea

class IdeaListModel(QAbstractListModel):
    def __init__(self, parent=None):
        super().__init__(parent)
        self.ideas: list[Idea] = []

    def rowCount(self, parent=QModelIndex()):
        return 0 if parent.isValid() else len(self.ideas)

    def data(self, index, role=Qt.ItemDataRole.DisplayRole):
        if not index.isValid() or index.row() >= len(self.ideas):
            return None
        idea = self.ideas[index.row()]
        if role == Qt.ItemDataRole.DisplayRole:
            return idea.title
        if role == Qt.ItemDataRole.UserRole:
            return idea
        if role == Qt.ItemDataRole.ToolTipRole:
            return idea.title
        return None

    def replace(self, ideas):
        self.beginResetModel()
        self.ideas = ideas
        self.endResetModel()

class IdeaDelegate(QStyledItemDelegate):
    def __init__(self, parent=None):
        super().__init__(parent)
        self.dark = False

    def sizeHint(self, option, index):
        return QSize(160, 62)

    def paint(self, painter, option, index):
        idea = index.data(Qt.ItemDataRole.UserRole)
        if idea is None:
            return
        color = QColor(idea.project_color or ("#F5F5F7" if not self.dark else "#30343A"))
        if self.dark and idea.project_color:
            color = QColor(int(color.red() * .26 + 23), int(color.green() * .26 + 25), int(color.blue() * .26 + 29))
        selected = bool(option.state & QStyle.StateFlag.State_Selected)
        hover = bool(option.state & QStyle.StateFlag.State_MouseOver)
        if hover:
            color = color.lighter(108) if self.dark else color.darker(103)
        painter.save()
        painter.fillRect(option.rect, color)
        if selected:
            painter.setPen(QPen(QColor("#80B7FF" if self.dark else "#356CB5"), 2))
            painter.drawRect(option.rect.adjusted(1, 1, -1, -1))
            painter.fillRect(option.rect.adjusted(0, 0, -option.rect.width() + 4, 0), QColor("#80B7FF" if self.dark else "#356CB5"))
        def linear(channel):
            value = channel / 255
            return value / 12.92 if value <= .04045 else ((value + .055) / 1.055) ** 2.4
        luminance = .2126 * linear(color.red()) + .7152 * linear(color.green()) + .0722 * linear(color.blue())
        text_color = QColor("#FFFFFF" if luminance < .179 else "#000000")
        painter.setPen(text_color)
        rect = option.rect.adjusted(12, 7, -12, -7)
        font = option.font
        font.setBold(True)
        painter.setFont(font)
        title = ("★ " if idea.pinned else "") + idea.title
        painter.drawText(rect.adjusted(0, 0, 0, -23), Qt.AlignmentFlag.AlignLeft | Qt.AlignmentFlag.AlignVCenter,
                         painter.fontMetrics().elidedText(title, Qt.TextElideMode.ElideRight, rect.width()))
        font.setBold(False)
        font.setPointSizeF(max(8, font.pointSizeF() - 1))
        painter.setFont(font)
        modified = datetime.fromisoformat(idea.updated_at).astimezone().strftime("%b %d · %H:%M")
        subtitle = f"{idea.project_name or 'Unassigned'} · {modified} · {idea.group_name or idea.status.title()}"
        painter.drawText(rect.adjusted(0, 25, 0, 0), Qt.AlignmentFlag.AlignLeft | Qt.AlignmentFlag.AlignVCenter,
                         painter.fontMetrics().elidedText(subtitle, Qt.TextElideMode.ElideRight, rect.width()))
        painter.restore()
