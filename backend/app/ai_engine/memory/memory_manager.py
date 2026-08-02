"""
Public import location for MemoryManager (per the requested project structure).

The implementation lives in this package's __init__.py so that
`from app.ai_engine.memory import MemoryManager, get_memory_manager` works; this
module re-exports the same objects so that
`from app.ai_engine.memory.memory_manager import MemoryManager` also works.
"""

from app.ai_engine.memory import (  # noqa: F401
    MemoryManager,
    get_memory_manager,
)

__all__ = ["MemoryManager", "get_memory_manager"]
