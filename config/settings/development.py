"""Development settings for AlgoBot."""

# base.py already composes the shared settings modules; development only needs
# to expose that canonical aggregate rather than importing each module twice.
from .base import *  # noqa: F403
