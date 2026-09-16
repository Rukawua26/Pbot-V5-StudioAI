"""
Top-level config module shim.
Re-exports Config from core.config for project-wide import compatibility.
"""
from core.config import Config

__all__ = ["Config"]
