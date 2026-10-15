'''CLI contract: argument parsing, exit codes and printed output.

HTTP commands are driven through a stubbed urlopen, so the suite never needs
a listening server. `apps` reads the real SQLite file, which is exactly the
path an operator takes to inspect a deployment.
'''
from __future__ import annotations

import io
import json
import sqlite3
import urllib.error

import pytest
from sqlalchemy.exc import OperationalError

import message_pusher.cli as cli

_SCHEMA = (
    'CREATE TABLE apps (id INTEGER PRIMARY KEY, name VARCHAR(64) UNIQUE,'
     ' key_hash VARCHAR(64), channels_json TEXT, retry_max INTEGER, created_at DATETIME)',
    'CREATE TABLE messages (id INTEGER PRIMARY KEY, app_id INTEGER, title VARCHAR(256),'
     ' body TEXT, status VARCHAR(16), created_at DATETIME)',
    'CREATE TABLE receipts (id INTEGER PRIMARY KEY, message_id INTEGER, channel VARCHAR(32),'
     ' status VARCHAR(16), attempts INTEGER, detail VARCHAR(256), next_retry_at DATETIME,'
     ' updated_at DATETIME)',
)


class _Response:
    '''The subset of the urlopen return value the CLI relies on.'''

    def __init__(self, status=200, body='{}'):
        self.status = status
        self._body = body.encode()

    def read(self):
        return self._body

    def __enter__(self):
        return self

    def __exit__(self, *exc_info):
        return False


@pytest.fixture()
def http(monkeypatch):
    '''Capture the request the CLI builds, and answer with a canned response.'''
    seen = {'calls': [], 'response': _Response(200, '{"status": "queued"}')}

    def fake_urlopen(request, timeout=None):
        seen['calls'].append(
            {
                'url': request.full_url,
                'method': request.get_method(),
                'body': json.loads((request.data or b'{}').decode()),
                'headers': {k.lower(): v for k, v in request.header_items()},
                'timeout': timeout,
            }
        )
        outcome = seen['response']
        if isinstance(outcome, Exception):
            raise outcome
        return outcome

    monkeypatch.setattr(cli.urllib.request, 'urlopen', fake_urlopen)
    monkeypatch.setattr(cli, 'BASE', 'http://127.0.0.1:8123')
    return seen


@pytest.fixture()
def ledger(tmp_path, monkeypatch):
    '''A real SQLite file written straight into tmp_path.'''
    monkeypatch.setattr(cli.paths, 'INSTANCE_DIR', tmp_path)
    path = tmp_path / 'pusher.db'
    connection = sqlite3.connect(path)
    for statement in _SCHEMA:
        connection.execute(statement)
    connection.execute("INSERT INTO apps VALUES (1, 'ci-app', 'x', '{}', 7, '2024-01-01')")
    connection.execute("INSERT INTO apps VALUES (2, 'batch', 'y', '{}', 3, '2024-01-01')")
    connection.execute(
        "INSERT INTO messages VALUES (1, 1, 'Deploy finished', 'build 42', 'delivered', '2024-01-01')"
    )
    connection.commit()
    connection.close()
    return path


def run(capsys, argv):
    code = cli.main(argv)
    return code, capsys.readouterr().out


def test_the_parser_exposes_every_documented_subcommand():
    parser = cli.build_parser()
    subparsers = [a for a in parser._actions if hasattr(a, 'choices') and a.choices]

    assert set(subparsers[0].choices) == {'push', 'status', 'retry', 'apps'}


def test_no_subcommand_prints_help_and_exits_zero(capsys):
    code, out = run(capsys, [])

    assert code == 0
    assert 'message-pusher CLI' in out
    assert 'push' in out and 'retry' in out


def test_push_defaults_to_the_telegram_channel(capsys, http):
    code, out = run(capsys, ['push', 'Deploy finished', 'build 42', '--key', 'k'])

    call = http['calls'][0]
    assert code == 0
    assert call['method'] == 'POST'
    assert call['url'] == 'http://127.0.0.1:8123/api/push'
    assert call['body'] == {'title': 'Deploy finished', 'body': 'build 42',
                            'channels': ['telegram']}
    assert call['headers']['x-app-key'] == 'k'
    assert call['headers']['content-type'] == 'application/json'
    assert out.startswith('200 ')


def test_push_repeats_the_channel_flag_and_honours_url(capsys, http):
    code, _ = run(capsys, ['--url', 'http://elsewhere:9000/', 'push', 'T', 'B',
                           '--key', 'k', '--channel', 'slack', '--channel', 'ntfy'])

    assert code == 0
    assert http['calls'][0]['body']['channels'] == ['slack', 'ntfy']
    assert http['calls'][0]['url'].startswith('http://elsewhere:9000/')


def test_an_unknown_url_replaces_the_default_base(capsys, http):
    http['response'] = _Response(
        200, json.dumps({'id': 7, 'title': 'T', 'status': 'queued', 'receipts': []})
    )

    run(capsys, ['--url', 'http://10.0.0.5:8080', 'status', '7'])

    assert cli.BASE == 'http://10.0.0.5:8080'
    assert http['calls'][0]['method'] == 'GET'
    assert http['calls'][0]['body'] == {}


def test_a_200_that_is_not_the_envelope_is_printed_verbatim(capsys, http):
    http['response'] = _Response(200, '<html>proxy interstitial</html>')

    code, out = run(capsys, ['status', '7'])

    assert code == 0
    assert 'proxy interstitial' in out


def test_push_reports_a_non_200_as_failure(capsys, http):
    http['response'] = _Response(503, '{"error": "service_unavailable"}')

    code, out = run(capsys, ['push', 'T', 'B', '--key', 'k'])

    assert code == 1
    assert '503' in out and 'service_unavailable' in out


def test_status_renders_every_receipt(capsys, http):
    http['response'] = _Response(
        200,
        json.dumps(
            {
                'id': 4,
                'title': 'Deploy finished',
                'status': 'partial',
                'receipts': [
                    {'channel': 'telegram', 'status': 'sent', 'attempts': 1, 'detail': 'ok'},
                    {'channel': 'email', 'status': 'retrying', 'attempts': 3, 'detail': 'timeout'},
                ],
            }
        ),
    )

    code, out = run(capsys, ['status', '4'])

    assert code == 0
    assert http['calls'][0]['url'] == 'http://127.0.0.1:8123/api/status/4'
    assert 'message 4' in out and 'partial' in out
    assert 'telegram' in out and 'attempts=1' in out
    assert 'email' in out and 'attempts=3' in out


def test_status_on_a_missing_message_reports_the_envelope(capsys, http):
    http['response'] = _Response(404, '{"error": "not_found"}')

    code, out = run(capsys, ['status', '999'])

    assert code == 1
    assert 'not_found' in out


def test_retry_posts_to_the_retry_endpoint(capsys, http):
    http['response'] = _Response(200, '{"requeued": 2}')

    code, out = run(capsys, ['retry', '4'])

    assert code == 0
    assert http['calls'][0]['method'] == 'POST'
    assert http['calls'][0]['url'].endswith('/api/messages/4/retry')
    assert 'requeued' in out


def test_a_refused_connection_is_reported_not_raised(capsys, http):
    http['response'] = urllib.error.URLError('connection refused')

    code, out = run(capsys, ['push', 'T', 'B', '--key', 'k'])

    assert code == 1
    assert '0 ' in out
    assert 'cannot reach http://127.0.0.1:8123' in out
    assert 'connection refused' in out


def test_an_http_error_response_is_read_instead_of_raised(capsys, http):
    http['response'] = urllib.error.HTTPError(
        'http://127.0.0.1:8123/api/push', 401, 'Unauthorized', {},
        io.BytesIO(b'{"error": "unauthorized"}'),
    )

    code, out = run(capsys, ['push', 'T', 'B', '--key', 'bad'])

    assert code == 1
    assert out.startswith('401 ')
    assert 'unauthorized' in out


def test_apps_lists_the_local_database(capsys, ledger):
    code, out = run(capsys, ['apps'])

    assert code == 0
    assert 'ci-app' in out and 'max_attempts=7' in out
    assert 'batch' in out and 'max_attempts=3' in out
    assert 'msg   1' in out and 'delivered' in out and 'Deploy finished' in out


def test_apps_on_an_empty_directory_surfaces_the_missing_table(capsys, tmp_path, monkeypatch):
    monkeypatch.setattr(cli.paths, 'INSTANCE_DIR', tmp_path)

    with pytest.raises(OperationalError):
        cli.main(['apps'])

