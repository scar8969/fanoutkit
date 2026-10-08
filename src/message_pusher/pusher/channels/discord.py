"""discord channel.

The implementation lives in :mod:`pusher.channels`; importing this module only
re-exports it so `pusher.channels.discord` stays importable.
"""

from . import CHANNELS, DiscordChannel, _Base

__all__ = ["DiscordChannel", "CHANNELS", "_Base"]
