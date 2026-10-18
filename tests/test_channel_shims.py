"""The per-channel shim modules stay importable and re-export the real classes.

The package "pusher.channels" holds the implementations; "pusher.channels.<name>"
is a thin module kept for callers that import the channel by file. A shim that
drifts from the registry would break those callers silently, so each one is
checked against the class the registry actually hands out.
"""

from __future__ import annotations

import importlib

import pytest

from message_pusher.pusher import channels

SHIMS = {
    "discord": "DiscordChannel",
    "email": "EmailChannel",
    "ntfy": "NtfyChannel",
    "slack": "SlackChannel",
    "telegram": "TelegramChannel",
    "webhook": "WebhookChannel",
}


@pytest.mark.parametrize("module_name,class_name", sorted(SHIMS.items()))
def test_the_shim_re_exports_the_registered_class(module_name, class_name):
    shim = importlib.import_module("message_pusher.pusher.channels." + module_name)

    expected = getattr(channels, class_name)
    assert getattr(shim, class_name) is expected
    assert shim.CHANNELS is channels.CHANNELS
    assert shim._Base is channels._Base
    assert shim.__all__ == [class_name, "CHANNELS", "_Base"]


@pytest.mark.parametrize("name", sorted(SHIMS))
def test_every_shimmed_channel_is_registered_under_its_own_name(name):
    assert isinstance(channels.CHANNELS[name], type)
    assert channels.CHANNELS[name].__name__ == SHIMS[name]
