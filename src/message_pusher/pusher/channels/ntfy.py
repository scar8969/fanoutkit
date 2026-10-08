"""ntfy channel.

The implementation lives in :mod:`pusher.channels`; importing this module only
re-exports it so `pusher.channels.ntfy` stays importable.
"""

from . import CHANNELS, NtfyChannel, _Base

__all__ = ["NtfyChannel", "CHANNELS", "_Base"]
