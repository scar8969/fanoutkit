"""slack channel.

The implementation lives in :mod:`pusher.channels`; importing this module only
re-exports it so `pusher.channels.slack` stays importable.
"""

from . import CHANNELS, SlackChannel, _Base

__all__ = ["SlackChannel", "CHANNELS", "_Base"]
