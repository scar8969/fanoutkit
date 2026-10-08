"""telegram channel.

The implementation lives in :mod:`pusher.channels`; importing this module only
re-exports it so `pusher.channels.telegram` stays importable.
"""

from . import CHANNELS, TelegramChannel, _Base

__all__ = ["TelegramChannel", "CHANNELS", "_Base"]
