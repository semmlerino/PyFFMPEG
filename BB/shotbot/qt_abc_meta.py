"""Compatible metaclass for combining ABC with Qt classes.

This module provides a metaclass that resolves the conflict when trying
to use both ABC (ABCMeta) and Qt classes (Shiboken.ObjectType) together.
"""

from abc import ABCMeta
from PySide6.QtCore import QObject


# Create a compatible metaclass that combines ABCMeta and Qt's metaclass
class QABCMeta(type(QObject), ABCMeta):  # type: ignore[misc]
    """Metaclass that combines ABCMeta with Qt's metaclass.

    This allows classes to inherit from both ABC and Qt classes (like QObject
    or QAbstractListModel) without metaclass conflicts.

    Example:
        class MyModel(ABC, QObject, metaclass=QABCMeta):
            @abstractmethod
            def my_method(self):
                pass
    """
    pass
