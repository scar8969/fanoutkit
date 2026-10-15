'''HTTP-surface tests: the JSON API blueprint and the legacy HTML pages.

These drive the real Flask application through its test client. Database
writes land in the same SQLite file the service uses, so every fixture cleans
up the rows it created. Outbound delivery is always stubbed: no test opens a
socket to a third party.
'''
from __future__ import annotations

import hashlib

import pytest

from message_pusher.models import App, Message, Receipt, db
from message_pusher.pusher.channels import CHANNELS

KEY = 'test-app-key'


def _cleanup(app_id):
    for message in Message.query.filter_by(app_id=app_id).all():
        Receipt.query.filter_by(message_id=message.id).delete()
        db.session.delete(message)
    db.session.commit()


@pytest.fixture()
def app_row():
    row = App(
        name='api-fixture-app',
        key_hash=hashlib.sha256(KEY.encode()).hexdigest(),
        channels_json='{}',
        retry_max=5,
    )
    db.session.add(row)
    db.session.commit()
    yield row
    _cleanup(row.id)
    db.session.delete(db.session.get(App, row.id))
    db.session.commit()


@pytest.fixture()
def accepting_channel(monkeypatch):
    '''Replace the telegram adapter with one that always succeeds.'''
    calls = []

    class Accepting:
        def send(self, payload):
            calls.append(payload)
            return True, '200 accepted'

    monkeypatch.setitem(CHANNELS, 'telegram', Accepting)
    return calls


# ---------------------------------------------------------------------------
# /api/push
# ---------------------------------------------------------------------------


def test_push_without_a_key_is_unauthorized(client):
    response = client.post('/api/push', json={'title': 't', 'body': 'b'})

    assert response.status_code == 401
    assert response.get_json() == {'error': 'unauthorized'}


def test_push_with_an_unknown_key_is_unauthorized(client):
    response = client.post('/api/push', json={'title': 't'},
                           headers={'X-App-Key': 'not-a-real-key'})

    assert response.status_code == 401


def test_push_accepts_a_signed_request_and_fans_out_to_channels(client, app_row, accepting_channel):
    response = client.post('/api/push',
                           json={'title': 'Deploy finished', 'body': 'build 42',
                                 'channels': ['telegram']},
                           headers={'X-App-Key': KEY})

    assert response.status_code == 200
    payload = response.get_json()
    assert payload['status'] == 'queued'
    mid = payload['message_id']
    try:
        message = db.session.get(Message, mid)
        assert (message.title, message.body) == ('Deploy finished', 'build 42')
        receipts = Receipt.query.filter_by(message_id=mid).all()
        assert [r.channel for r in receipts] == ['telegram']
        assert receipts[0].status == 'sent'
        assert message.status == 'delivered'
        assert accepting_channel[0]['title'] == 'Deploy finished'
    finally:
        _cleanup(app_row.id)


def test_push_defaults_to_telegram_when_channels_are_omitted(client, app_row, accepting_channel):
    response = client.post('/api/push', json={'title': 'ping'},
                           headers={'X-App-Key': KEY})

    mid = response.get_json()['message_id']
    try:
        receipts = Receipt.query.filter_by(message_id=mid).all()
        assert [r.channel for r in receipts] == ['telegram']
    finally:
        _cleanup(app_row.id)


def test_push_survives_a_malformed_json_body(client, app_row):
    response = client.post('/api/push', data='not json at all',
                           content_type='application/json',
                           headers={'X-App-Key': KEY})

    assert response.status_code == 200
    mid = response.get_json()['message_id']
    try:
        message = db.session.get(Message, mid)
        assert (message.title, message.body) == ('', '')
    finally:
        _cleanup(app_row.id)


# ---------------------------------------------------------------------------
# /api/status and /api/messages/<id>/retry
# ---------------------------------------------------------------------------


def test_status_returns_404_for_an_unknown_message(client):
    response = client.get('/api/status/999999999')

    assert response.status_code == 404
    assert response.get_json()['error'] == 'not_found'


def test_status_reports_every_receipt(client, app_row):
    message = Message(app_id=app_row.id, title='status probe', body='x')
    db.session.add(message)
    db.session.flush()
    db.session.add(Receipt(message_id=message.id, channel='slack', status='retrying',
                           attempts=2, detail='503 upstream'))
    db.session.add(Receipt(message_id=message.id, channel='discord', status='sent',
                           attempts=1, detail='204 no content'))
    db.session.commit()

    body = client.get('/api/status/%d' % message.id).get_json()
    try:
        assert body['title'] == 'status probe'
        assert sorted(r['channel'] for r in body['receipts']) == ['discord', 'slack']
        slack = next(r for r in body['receipts'] if r['channel'] == 'slack')
        assert (slack['status'], slack['attempts']) == ('retrying', 2)
        assert slack['next_retry_at'] == ''
    finally:
        _cleanup(app_row.id)


def test_api_retry_requeues_and_redispatches(client, app_row, accepting_channel):
    message = Message(app_id=app_row.id, title='retry me', body='x')
    db.session.add(message)
    db.session.flush()
    receipt = Receipt(message_id=message.id, channel='telegram', status='retrying',
                      attempts=1, detail='timeout')
    db.session.add(receipt)
    db.session.commit()

    response = client.post('/api/messages/%d/retry' % message.id)
    try:
        assert response.status_code == 200
        assert response.get_json() == {'status': 'queued'}
        db.session.refresh(receipt)
        assert receipt.status == 'sent'
        assert receipt.attempts == 2
    finally:
        _cleanup(app_row.id)


# ---------------------------------------------------------------------------
# legacy HTML pages
# ---------------------------------------------------------------------------


def test_index_page_renders_the_dashboard(client):
    response = client.get('/')

    assert response.status_code == 200
    body = response.get_data(as_text=True)
    assert 'X-App-Key' in body
    assert 'curl' in body


def test_apps_page_lists_registered_applications(client, app_row):
    body = client.get('/apps').get_data(as_text=True)

    assert app_row.name in body


def test_posting_the_apps_form_stores_a_hashed_key(client, settings):
    response = client.post('/apps', data={'name': 'form-created-app', 'key': 'form-secret',
                                          'retry_max': '3'})

    assert response.status_code == 200
    created = App.query.filter_by(name='form-created-app').first()
    try:
        assert created is not None
        assert created.key_hash == hashlib.sha256(b'form-secret').hexdigest()
        assert created.retry_max == 3
    finally:
        _cleanup(created.id)
        db.session.delete(created)
        db.session.commit()


def test_posting_the_apps_form_twice_keeps_the_first_registration(client):
    client.post('/apps', data={'name': 'duplicate-app', 'key': 'first'})
    client.post('/apps', data={'name': 'duplicate-app', 'key': 'second'})

    rows = App.query.filter_by(name='duplicate-app').all()
    try:
        assert len(rows) == 1
        assert rows[0].key_hash == hashlib.sha256(b'first').hexdigest()
    finally:
        _cleanup(rows[0].id)
        db.session.delete(rows[0])
        db.session.commit()


def test_posting_the_apps_form_without_a_name_is_a_no_op(client):
    before = App.query.count()

    assert client.post('/apps', data={'name': '   '}).status_code == 200
    assert App.query.count() == before


def test_message_detail_page_lists_its_receipts(client, app_row):
    message = Message(app_id=app_row.id, title='detail probe', body='hello')
    db.session.add(message)
    db.session.flush()
    db.session.add(Receipt(message_id=message.id, channel='webhook', status='failed',
                           attempts=5, detail='connection refused'))
    db.session.commit()

    try:
        body = client.get('/messages/%d' % message.id).get_data(as_text=True)
        assert 'detail probe' in body
        assert 'webhook' in body
    finally:
        _cleanup(app_row.id)


def test_message_detail_returns_html_404_for_an_unknown_message(client):
    response = client.get('/messages/999999999')

    assert response.status_code == 404
    assert response.mimetype == 'text/html'


def test_page_retry_requeues_retrying_receipts(client, app_row, accepting_channel):
    message = Message(app_id=app_row.id, title='page retry', body='x')
    db.session.add(message)
    db.session.flush()
    receipt = Receipt(message_id=message.id, channel='telegram', status='retrying',
                      attempts=1, detail='timeout')
    db.session.add(receipt)
    db.session.commit()

    response = client.post('/messages/%d/retry' % message.id)
    try:
        assert response.status_code == 200
        db.session.refresh(receipt)
        assert receipt.status == 'sent'
    finally:
        _cleanup(app_row.id)


def test_healthz_reports_row_counts(client, app_row):
    body = client.get('/healthz').get_json()

    assert body['status'] == 'ok'
    assert body['apps'] == App.query.count()
    assert body['messages'] == Message.query.count()
    assert body['apps'] >= 1

