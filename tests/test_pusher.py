'''Delivery-path tests: channel adapters, the dispatch state machine, retries.

The channel adapters are the only place this service talks to the network, so
each one is driven through a stub that records exactly what would have gone on
the wire: a monkeypatched urlopen, a fake SMTP transport, or a real loopback
HTTP server bound to an ephemeral port. No test reaches a third-party API, and
no test needs a credential.
'''
from __future__ import annotations

import json
import threading
import uuid
from datetime import UTC, datetime, timedelta
from http.server import BaseHTTPRequestHandler, HTTPServer

import pytest

from message_pusher.models import App, Message, Receipt, db
from message_pusher.pusher import channels as channel_package
from message_pusher.pusher.channels import (
    CHANNELS,
    DiscordChannel,
    EmailChannel,
    NtfyChannel,
    SlackChannel,
    TelegramChannel,
    WebhookChannel,
    register,
)
from message_pusher.pusher.dispatch import dispatch_message
from message_pusher.pusher.retry import RetryPolicy
from message_pusher.pusher.templates import render

BODY = 'build 42 is live'
TITLE = 'Deploy finished'


def _naive_utcnow():
    return datetime.now(UTC).replace(tzinfo=None)


@pytest.fixture()
def seeded():
    '''Insert an app plus a queued message with one receipt per channel name.'''
    created = []

    def make(channels=('telegram',), retry_max=5, config=None, title=TITLE, body=BODY):
        app_row = App(
            name='t-' + uuid.uuid4().hex[:12],
            key_hash='0' * 64,
            channels_json=json.dumps(config or {}),
            retry_max=retry_max,
        )
        db.session.add(app_row)
        db.session.flush()
        message = Message(app_id=app_row.id, title=title, body=body)
        db.session.add(message)
        db.session.flush()
        for name in channels:
            db.session.add(Receipt(message_id=message.id, channel=name))
        db.session.commit()
        created.append(app_row.id)
        return app_row, message

    yield make

    for app_id in created:
        for message in Message.query.filter_by(app_id=app_id).all():
            Receipt.query.filter_by(message_id=message.id).delete()
            db.session.delete(message)
        app_row = db.session.get(App, app_id)
        if app_row is not None:
            db.session.delete(app_row)
    db.session.commit()


class _FakeResponse:
    '''Minimal stand-in for the object urlopen yields as a context manager.'''

    def __init__(self, status=200, body=b'{"ok":true}'):
        self.status = status
        self._body = body

    def read(self, amount=None):
        return self._body

    def __enter__(self):
        return self

    def __exit__(self, *exc_info):
        return False


@pytest.fixture()
def wire(monkeypatch):
    '''Capture every urllib request the adapters attempt; answer 200.'''
    seen = []

    def fake_urlopen(request, timeout=None):
        raw = (request.data or b'').decode('utf-8', 'replace')
        try:
            parsed = json.loads(raw) if raw else None
        except ValueError:
            parsed = None
        seen.append(
            {
                'url': request.full_url,
                'method': request.get_method(),
                'raw': raw,
                'body': parsed,
                'headers': {k.lower(): v for k, v in request.header_items()},
                'timeout': timeout,
            }
        )
        return _FakeResponse()

    monkeypatch.setattr(channel_package.urllib.request, 'urlopen', fake_urlopen)
    return seen


class _FakeSMTP:
    '''Records the SMTP conversation instead of opening a socket.'''

    instances = []

    def __init__(self, host, port=25, timeout=None):
        self.host = host
        self.port = port
        self.timeout = timeout
        self.started_tls = False
        self.credentials = None
        self.message = None
        _FakeSMTP.instances.append(self)

    def __enter__(self):
        return self

    def __exit__(self, *exc_info):
        return False

    def starttls(self):
        self.started_tls = True

    def login(self, user, password):
        self.credentials = (user, password)

    def send_message(self, message):
        self.message = message


class _ExplodingSMTP:
    def __init__(self, *args, **kwargs):
        raise OSError('connection refused by stub')


class _EchoHandler(BaseHTTPRequestHandler):
    '''Answers any POST with a fixed body and remembers the request.'''

    received = []

    def do_POST(self):
        length = int(self.headers.get('Content-Length') or 0)
        body = self.rfile.read(length).decode('utf-8', 'replace')
        _EchoHandler.received.append({'path': self.path, 'body': body,
                                     'headers': dict(self.headers.items())})
        payload = b'{"accepted":true}'
        self.send_response(200)
        self.send_header('Content-Type', 'application/json')
        self.send_header('Content-Length', str(len(payload)))
        self.end_headers()
        self.wfile.write(payload)

    def log_message(self, *args):
        return None


@pytest.fixture()
def echo_server():
    '''A real HTTP server on a loopback ephemeral port.'''
    _EchoHandler.received = []
    server = HTTPServer(('127.0.0.1', 0), _EchoHandler)
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()
    yield 'http://127.0.0.1:%d/hook' % server.server_address[1], _EchoHandler.received
    server.shutdown()
    server.server_close()
    thread.join(timeout=5)


def _stub_channel(ok=True, detail='250 ok'):
    '''Build a channel class suitable for CHANNELS: callable, records payloads.'''
    calls = []

    class Stub:
        def send(self, payload):
            calls.append(payload)
            return ok, detail

    Stub.calls = calls
    return Stub


def _quarantine_other_retries(keep_id):
    '''Move every unrelated retrying receipt far into the future.'''
    Receipt.query.filter(Receipt.status == 'retrying', Receipt.id != keep_id).update(
        {'next_retry_at': _naive_utcnow() + timedelta(days=3650)},
        synchronize_session=False,
    )
    db.session.commit()


# ---------------------------------------------------------------------------
# registry
# ---------------------------------------------------------------------------


def test_registry_holds_every_shipped_adapter():
    assert sorted(CHANNELS) == ['discord', 'email', 'ntfy', 'slack', 'telegram', 'webhook']


def test_register_adds_and_returns_the_class():
    class Tempo:
        def send(self, payload):
            return True, 'ok'

    returned = register('tempo')(Tempo)
    try:
        assert returned is Tempo
        assert CHANNELS['tempo'] is Tempo
    finally:
        del CHANNELS['tempo']


# ---------------------------------------------------------------------------
# channel adapters
# ---------------------------------------------------------------------------


def test_telegram_channel_posts_to_the_bot_api(wire):
    payload = render('telegram', TITLE, BODY)
    payload['config'] = {'token': 'BOT:TOKEN', 'chat_id': '4242'}

    ok, detail = TelegramChannel().send(payload)

    assert ok is True
    assert detail.startswith('200')
    assert wire[0]['url'] == 'https://api.telegram.org/botBOT:TOKEN/sendMessage'
    assert wire[0]['method'] == 'POST'
    assert wire[0]['body'] == {'chat_id': '4242', 'text': TITLE + chr(10) + BODY}
    assert wire[0]['headers']['content-type'] == 'application/json'


def test_discord_channel_posts_the_rendered_text(wire):
    payload = render('discord', TITLE, BODY)
    payload['config'] = {'webhook': 'https://discord.test/api/webhooks/1/abc'}

    ok, _ = DiscordChannel().send(payload)

    assert ok is True
    assert wire[0]['url'] == 'https://discord.test/api/webhooks/1/abc'
    assert wire[0]['body'] == {'content': TITLE + chr(10) + BODY}


def test_slack_channel_posts_a_mrkdwn_block(wire):
    payload = render('slack', TITLE, BODY)
    payload['config'] = {'webhook': 'https://hooks.slack.test/services/T/B/X'}

    ok, _ = SlackChannel().send(payload)

    assert ok is True
    assert wire[0]['body'] == {
        'blocks': [{'type': 'section',
                    'text': {'type': 'mrkdwn', 'text': TITLE + chr(10) + BODY}}]
    }


def test_webhook_channel_forwards_configured_headers(wire):
    payload = render('webhook', TITLE, BODY)
    payload['config'] = {'url': 'https://internal.test/notify',
                         'headers': {'X-Signature': 'sha256=deadbeef'}}

    ok, _ = WebhookChannel().send(payload)

    assert ok is True
    assert wire[0]['url'] == 'https://internal.test/notify'
    assert wire[0]['headers']['x-signature'] == 'sha256=deadbeef'
    assert wire[0]['body'] == {'text': TITLE + chr(10) + BODY}


def test_webhook_channel_completes_a_real_http_round_trip(echo_server):
    url, received = echo_server
    payload = render('webhook', TITLE, BODY)
    payload['config'] = {'url': url}

    ok, detail = WebhookChannel().send(payload)

    assert ok is True
    assert detail.startswith('200')
    assert 'accepted' in detail
    assert received[0]['path'] == '/hook'
    assert json.loads(received[0]['body']) == {'text': TITLE + chr(10) + BODY}
    assert received[0]['headers']['Content-Type'] == 'application/json'


def test_ntfy_channel_sends_plain_text_with_a_bearer_token(wire):
    payload = render('ntfy', TITLE, BODY)
    payload['config'] = {'topic': 'deploys', 'token': 'tk_abc'}

    ok, detail = NtfyChannel().send(payload)

    assert ok is True
    assert detail == '200'
    assert wire[0]['url'] == 'https://ntfy.sh/deploys'
    assert wire[0]['raw'] == TITLE + chr(10) + BODY
    assert wire[0]['headers']['title'] == TITLE
    assert wire[0]['headers']['authorization'] == 'Bearer tk_abc'


def test_ntfy_channel_sends_an_empty_bearer_when_unauthenticated(wire):
    payload = render('ntfy', TITLE, BODY)
    payload['config'] = {'topic': 'public-topic'}

    ok, _ = NtfyChannel().send(payload)

    assert ok is True
    assert wire[0]['headers']['authorization'] == 'Bearer '


def test_email_channel_authenticates_and_submits(monkeypatch):
    _FakeSMTP.instances = []
    monkeypatch.setattr(channel_package.smtplib, 'SMTP', _FakeSMTP)
    payload = render('email', TITLE, BODY)
    payload['config'] = {'host': 'smtp.test', 'port': '2525', 'from': 'ci@test',
                         'to': 'ops@test', 'user': 'ci', 'password': 'pw'}

    ok, detail = EmailChannel().send(payload)

    assert (ok, detail) == (True, '250 queued')
    session = _FakeSMTP.instances[0]
    assert (session.host, session.port) == ('smtp.test', 2525)
    assert session.started_tls is True
    assert session.credentials == ('ci', 'pw')
    assert session.message['Subject'] == TITLE
    assert session.message['From'] == 'ci@test'
    assert session.message['To'] == 'ops@test'
    assert BODY in session.message.get_content()


def test_email_channel_skips_login_when_no_user_is_configured(monkeypatch):
    _FakeSMTP.instances = []
    monkeypatch.setattr(channel_package.smtplib, 'SMTP', _FakeSMTP)
    payload = render('email', TITLE, BODY)
    payload['config'] = {'host': 'smtp.test', 'from': 'ci@test', 'to': 'ops@test'}

    ok, _ = EmailChannel().send(payload)

    assert ok is True
    assert _FakeSMTP.instances[0].credentials is None
    assert _FakeSMTP.instances[0].port == 587


def test_email_channel_reports_a_transport_failure_as_data(monkeypatch):
    monkeypatch.setattr(channel_package.smtplib, 'SMTP', _ExplodingSMTP)
    payload = render('email', TITLE, BODY)
    payload['config'] = {'host': 'smtp.test', 'from': 'ci@test', 'to': 'ops@test'}

    ok, detail = EmailChannel().send(payload)

    assert ok is False
    assert detail == 'connection refused by stub'


# ---------------------------------------------------------------------------
# dispatch state machine
# ---------------------------------------------------------------------------


def test_dispatch_marks_a_successful_receipt_sent(monkeypatch, seeded):
    _app, message = seeded()
    stub = _stub_channel(True, '200 delivered')
    monkeypatch.setitem(CHANNELS, 'telegram', stub)

    dispatch_message(message.id)

    receipt = Receipt.query.filter_by(message_id=message.id).one()
    assert (receipt.status, receipt.attempts, receipt.detail) == ('sent', 1, '200 delivered')
    assert receipt.updated_at is not None
    assert db.session.get(Message, message.id).status == 'delivered'


def test_dispatch_merges_the_per_app_channel_configuration(monkeypatch, seeded):
    seeded(config={'telegram': {'token': 'BOT', 'chat_id': '7'}})
    stub = _stub_channel()
    monkeypatch.setitem(CHANNELS, 'telegram', stub)

    dispatch_message(Message.query.order_by(Message.id.desc()).first().id)

    assert stub.calls[0]['config'] == {'token': 'BOT', 'chat_id': '7'}
    assert stub.calls[0]['title'] == TITLE
    assert stub.calls[0]['text'] == TITLE + chr(10) + BODY


def test_dispatch_schedules_a_retry_then_stops_at_the_attempt_ceiling(monkeypatch, seeded):
    _app, message = seeded(retry_max=2)
    monkeypatch.setitem(CHANNELS, 'telegram', _stub_channel(False, '503 upstream'))

    dispatch_message(message.id)
    first = Receipt.query.filter_by(message_id=message.id).one()
    assert (first.status, first.attempts) == ('retrying', 1)
    assert first.next_retry_at is not None
    assert db.session.get(Message, message.id).status == 'queued'

    # A receipt that is merely 'retrying' is deliberately not dispatchable:
    # only the retry scheduler may turn it back into a queued attempt. Bring
    # its backoff window forward rather than sleeping in the suite.
    first.next_retry_at = _naive_utcnow() - timedelta(seconds=1)
    db.session.commit()

    assert RetryPolicy().process_due() == 1
    db.session.refresh(first)
    assert (first.status, first.attempts, first.detail) == ('failed', 2, '503 upstream')
    assert db.session.get(Message, message.id).status == 'failed'


def test_dispatch_records_an_unknown_channel_as_failed(monkeypatch, seeded):
    _app, message = seeded(channels=('carrier-pigeon',))

    dispatch_message(message.id)

    receipt = Receipt.query.filter_by(message_id=message.id).one()
    assert (receipt.status, receipt.attempts, receipt.detail) == ('failed', 0, 'unknown channel')
    assert db.session.get(Message, message.id).status == 'failed'


def test_dispatch_turns_a_transport_exception_into_a_retry(monkeypatch, seeded):
    _app, message = seeded(channels=('webhook',), config={'webhook': {'url': 'https://down.test/x'}})

    def raising_urlopen(request, timeout=None):
        raise OSError('connection reset by peer')

    monkeypatch.setattr(channel_package.urllib.request, 'urlopen', raising_urlopen)

    dispatch_message(message.id)

    receipt = Receipt.query.filter_by(message_id=message.id).one()
    assert receipt.status == 'retrying'
    assert receipt.attempts == 1
    assert receipt.detail == 'connection reset by peer'


def test_dispatch_reports_a_partial_fan_out(monkeypatch, seeded):
    _app, message = seeded(channels=('telegram', 'slack'), retry_max=1)
    monkeypatch.setitem(CHANNELS, 'telegram', _stub_channel(True))
    monkeypatch.setitem(CHANNELS, 'slack', _stub_channel(False, '410 gone'))

    dispatch_message(message.id)

    statuses = {r.channel: r.status for r in Receipt.query.filter_by(message_id=message.id)}
    assert statuses == {'telegram': 'sent', 'slack': 'failed'}
    assert db.session.get(Message, message.id).status == 'partial'


def test_dispatch_keeps_a_message_queued_while_all_receipts_retry(monkeypatch, seeded):
    _app, message = seeded(channels=('telegram', 'slack'))
    monkeypatch.setitem(CHANNELS, 'telegram', _stub_channel(False, 'timeout'))
    monkeypatch.setitem(CHANNELS, 'slack', _stub_channel(False, 'timeout'))

    dispatch_message(message.id)

    assert db.session.get(Message, message.id).status == 'queued'


def test_dispatch_treats_a_message_without_receipts_as_delivered(seeded):
    _app, message = seeded(channels=())

    dispatch_message(message.id)

    assert db.session.get(Message, message.id).status == 'delivered'


def test_dispatch_ignores_an_unknown_message_id(legacy_app_context):
    assert dispatch_message(2_000_000_001) is None


def test_dispatch_skips_receipts_that_are_not_queued(monkeypatch, seeded):
    _app, message = seeded()
    receipt = Receipt.query.filter_by(message_id=message.id).one()
    receipt.status = 'sent'
    db.session.commit()
    stub = _stub_channel()
    monkeypatch.setitem(CHANNELS, 'telegram', stub)

    dispatch_message(message.id)

    assert stub.calls == []
    assert db.session.get(Message, message.id).status == 'delivered'


# ---------------------------------------------------------------------------
# retry policy
# ---------------------------------------------------------------------------


def test_next_delay_grows_then_saturates():
    policy = RetryPolicy()
    assert policy.next_delay(0) == 1.0
    assert policy.next_delay(4) == 16.0
    assert policy.next_delay(30) == 300.0


def test_schedule_retry_sets_a_future_timestamp():
    receipt = Receipt(channel='telegram', attempts=3)

    RetryPolicy().schedule_retry(receipt)

    assert receipt.next_retry_at is not None
    assert receipt.next_retry_at > _naive_utcnow() + timedelta(seconds=7)
    assert receipt.next_retry_at < _naive_utcnow() + timedelta(seconds=9)


def test_process_due_drains_and_redispatches(monkeypatch, seeded):
    _app, message = seeded(channels=('telegram',))
    receipt = Receipt.query.filter_by(message_id=message.id).one()
    receipt.status = 'retrying'
    receipt.attempts = 1
    receipt.next_retry_at = _naive_utcnow() - timedelta(seconds=30)
    db.session.commit()
    _quarantine_other_retries(receipt.id)
    monkeypatch.setitem(CHANNELS, 'telegram', _stub_channel(True))

    handled = RetryPolicy().process_due()

    assert handled >= 1
    db.session.refresh(receipt)
    assert receipt.status == 'sent'
    assert receipt.attempts == 2
    assert db.session.get(Message, message.id).status == 'delivered'


def test_process_due_leaves_future_retries_alone(monkeypatch, seeded):
    _app, message = seeded(channels=('telegram',))
    receipt = Receipt.query.filter_by(message_id=message.id).one()
    receipt.status = 'retrying'
    receipt.next_retry_at = _naive_utcnow() + timedelta(hours=6)
    db.session.commit()
    _quarantine_other_retries(receipt.id)
    stub = _stub_channel(True)
    monkeypatch.setitem(CHANNELS, 'telegram', stub)

    RetryPolicy().process_due()

    db.session.refresh(receipt)
    assert receipt.status == 'retrying'
    assert stub.calls == []

