"""email channel.

The implementation lives in :mod:`pusher.channels`; importing this module only
re-exports it so `pusher.channels.email` stays importable.
"""

from . import CHANNELS, EmailChannel, _Base

__all__ = ["EmailChannel", "CHANNELS", "_Base"]
