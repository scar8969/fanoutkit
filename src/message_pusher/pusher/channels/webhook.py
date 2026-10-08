"""webhook channel.

The implementation lives in :mod:`pusher.channels`; importing this module only
re-exports it so `pusher.channels.webhook` stays importable.
"""

from . import CHANNELS, WebhookChannel, _Base

__all__ = ["WebhookChannel", "CHANNELS", "_Base"]
