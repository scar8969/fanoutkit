'''Typed errors and the logging contract.

The formatters are exercised directly with synthesised LogRecords: the
handler writes to sys.stdout rather than through logging's own capture, so
driving them through caplog would test the wrong thing.
'''
from __future__ import annotations

import json
import logging
import sys

import pytest

from message_pusher import __version__, errors, observability


@pytest.fixture(autouse=True)
def restore_root_logging():
    '''configure_logging rewrites the root handler; put it back afterwards.'''
    root = logging.getLogger()
    handlers, level = list(root.handlers), root.level
    configured = observability._CONFIGURED
    yield
    for handler in list(root.handlers):
        root.removeHandler(handler)
    for handler in handlers:
        root.addHandler(handler)
    root.setLevel(level)
    observability._CONFIGURED = configured


def record(exc_info=None, **extra):
    item = logging.LogRecord('svc.push', logging.INFO, __file__, 10, 'hello %s', ('world',), exc_info)
    item.__dict__.update(extra)
    return item


def failure():
    try:
        raise ValueError('the transport gave up')
    except ValueError:
        return sys.exc_info()


def test_the_json_formatter_emits_one_object_per_line():
    payload = json.loads(observability._JsonFormatter().format(
        record(event='push.queued', channel='telegram')
    ))

    assert payload['message'] == 'hello world'
    assert payload['level'] == 'INFO'
    assert payload['logger'] == 'svc.push'
    assert payload['service'] == 'message_pusher'
    assert payload['version'] == __version__
    assert payload['request_id'] == observability.request_id()
    assert payload['ts'].endswith('Z') and 'T' in payload['ts']
    assert payload['event'] == 'push.queued' and payload['channel'] == 'telegram'


def test_the_json_formatter_drops_private_and_reserved_keys():
    payload = json.loads(
        observability._JsonFormatter().format(
            record(_secret='nope', msg='hello %s', args=('world',), levelname='INFO')
        )
    )

    assert '_secret' not in payload
    assert payload['message'] == 'hello world'


def test_the_json_formatter_renders_a_traceback_when_one_is_attached():
    payload = json.loads(observability._JsonFormatter().format(record(exc_info=failure())))

    assert 'ValueError: the transport gave up' in payload['exception']
    assert 'Traceback' in payload['exception']


def test_the_text_formatter_is_the_single_line_human_form():
    line = observability._TextFormatter().format(record())

    assert 'level=info' in line
    assert 'logger=svc.push' in line
    assert "msg='hello world'" in line
    assert 'request_id=' in line
    assert '\n' not in line


def test_the_text_formatter_appends_the_traceback():
    line = observability._TextFormatter().format(record(exc_info=failure()))

    head, _, trace = line.partition('\n')

    assert trace and 'ValueError: the transport gave up' in trace
    assert 'Traceback' in trace


def test_the_stdout_handler_writes_to_the_current_stdout(capsys):
    handler = observability._StdoutHandler()
    handler.setFormatter(observability._TextFormatter())

    handler.emit(record())
    handler.flush()

    assert 'hello world' in capsys.readouterr().out


def test_request_ids_are_generated_and_scoped():
    token = observability.set_request_id('trace-abc')
    assert token == 'trace-abc' and observability.request_id() == 'trace-abc'

    generated = observability.set_request_id(None)
    assert generated == observability.request_id() and len(generated) == 32

    assert observability.new_request_id() != generated


def test_a_json_line_carries_the_active_request_id():
    observability.set_request_id('trace-xyz')

    payload = json.loads(observability._JsonFormatter().format(record()))

    assert payload['request_id'] == 'trace-xyz'


def test_configure_logging_installs_exactly_one_handler():
    observability.configure_logging('debug', json_output=True)
    first = list(logging.getLogger().handlers)

    observability.configure_logging('WARNING', json_output=True)
    second = list(logging.getLogger().handlers)

    assert len(first) == len(second) == 1
    assert isinstance(second[0].formatter, observability._JsonFormatter)
    assert logging.getLogger().level == logging.WARNING
    assert logging.getLogger('werkzeug').level == logging.WARNING


def test_configure_logging_switches_to_the_text_formatter():
    observability.configure_logging('INFO', json_output=False)

    handler = logging.getLogger().handlers[0]

    assert isinstance(handler.formatter, observability._TextFormatter)


def test_an_unknown_level_falls_back_to_info():
    observability.configure_logging('not-a-level', json_output=True)

    assert logging.getLogger().level == logging.INFO


@pytest.mark.parametrize('raw,expected', [('0', False), ('false', False), ('no', False),
                                          ('off', False), ('1', True), ('yes', True)])
def test_the_log_json_environment_variable_selects_the_formatter(monkeypatch, raw, expected):
    monkeypatch.setenv('LOG_JSON', raw)

    observability.configure_logging()
    formatter = logging.getLogger().handlers[0].formatter

    assert isinstance(formatter, observability._JsonFormatter) is expected
    assert isinstance(formatter, observability._TextFormatter) is (not expected)


def test_the_log_json_fallback_is_json_when_the_variable_is_absent(monkeypatch):
    monkeypatch.delenv('LOG_JSON', raising=False)

    observability.configure_logging()

    assert isinstance(logging.getLogger().handlers[0].formatter, observability._JsonFormatter)


def test_get_logger_configures_logging_on_first_use(monkeypatch):
    monkeypatch.setattr(observability, '_CONFIGURED', False)
    root = logging.getLogger()
    for handler in list(root.handlers):
        root.removeHandler(handler)

    logger = observability.get_logger('message_pusher.demo')

    assert logger.name == 'message_pusher.demo'
    assert observability._CONFIGURED is True
    assert len(root.handlers) == 1


def test_log_event_emits_one_structured_event():
    captured = {}

    class _Logger:
        def info(self, message, extra=None):
            captured['message'] = message
            captured['extra'] = extra

    observability.log_event(_Logger(), 'push.delivered', message_id=4, channel='telegram')

    assert captured['message'] == 'push.delivered'
    assert captured['extra'] == {'event': 'push.delivered', 'message_id': 4, 'channel': 'telegram'}


def test_the_base_error_falls_back_to_its_docstring():
    error = errors.AppError()

    assert error.status_code == 500 and error.code == 'internal_error'
    assert error.message == errors.AppError.__doc__
    assert error.context == {}
    assert str(error) == error.message
    assert repr(errors.AppError('boom', tried=2)) == "AppError('boom', {'tried': 2})"


@pytest.mark.parametrize(
    'cls,status,code',
    [
        (errors.BadRequest, 400, 'bad_request'),
        (errors.Unauthorized, 401, 'unauthorized'),
        (errors.Forbidden, 403, 'forbidden'),
        (errors.NotFound, 404, 'not_found'),
        (errors.Conflict, 409, 'conflict'),
        (errors.PayloadTooLarge, 413, 'payload_too_large'),
        (errors.RateLimited, 429, 'rate_limited'),
        (errors.ServiceUnavailable, 503, 'service_unavailable'),
    ],
)
def test_every_error_maps_to_a_stable_status_and_code(cls, status, code):
    assert cls.status_code == status and cls.code == code
    assert cls().message == cls.__doc__
    assert cls is not errors.AppError


def test_context_travels_only_when_it_is_not_empty():
    assert errors.NotFound('no message 9').to_dict() == {
        'error': 'not_found', 'message': 'no message 9',
    }
    assert errors.NotFound('no message 9', message_id=9).to_dict() == {
        'error': 'not_found',
        'message': 'no message 9',
        'details': {'message_id': 9},
    }


def test_error_payload_builds_the_same_envelope_without_an_exception():
    assert errors.error_payload('bad_request', 'title is required') == {
        'error': 'bad_request', 'message': 'title is required',
    }
    assert errors.error_payload('bad_request', 'title is required', field='title') == {
        'error': 'bad_request',
        'message': 'title is required',
        'details': {'field': 'title'},
    }


def test_the_public_error_names_are_exported():
    missing = [name for name in errors.__all__ if not hasattr(errors, name)]

    assert missing == []

