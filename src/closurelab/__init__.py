"""ClosureLab: an interpreter exploring lexical scope, closures and recursion."""

from .api import execute
from .errors import LanguageError
from .runtime import Environment, Limits, format_value

__version__ = "0.1.0"

__all__ = ["Environment", "LanguageError", "Limits", "__version__", "execute", "format_value"]
