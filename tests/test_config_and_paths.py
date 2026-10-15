'''Configuration and filesystem-layout contract.

Every case builds a Settings object from an explicit mapping, so the suite
never depends on the ambient environment. The production guard is covered
here because it is the one rule that stops the service starting with the
development default secret.
'''
from __future__ import annotations

import pathlib

import pytest

from message_pusher import paths
from message_pusher.config import ConfigError, Settings, get_settings, reset_settings


def test_defaults_are_the_documented_ones():
    settings = Settings.from_env({})

    assert settings.app_name == 'message_pusher'
    assert settings.env == 'development'
    assert settings.host == '0.0.0.0'
    assert settings.port == 8000
    assert settings.log_level == 'INFO'
    assert settings.log_json is True
    assert settings.secret_key_provided is False
    assert settings.database_uri == ''
    assert settings.request_id_header == 'X-Request-ID'
    assert settings.max_content_length == 8 * 1024 * 1024
    assert settings.extras == {}


def test_the_environment_overrides_every_documented_knob():
    settings = Settings.from_env(
        {
            'APP_NAME': 'pusher-ci',
            'APP_ENV': 'production',
            'SECRET_KEY': 'a-real-secret',
            'DEBUG': 'yes',
            'HOST': '127.0.0.1',
            'PORT': '9001',
            'DATABASE_URL': 'sqlite:///custom.db',
            'SQLALCHEMY_TRACK_MODIFICATIONS': 'on',
            'LOG_LEVEL': 'debug',
            'LOG_JSON': 'off',
            'REQUEST_ID_HEADER': 'X-Trace',
            'MAX_CONTENT_LENGTH': '1024',
        }
    )

    assert settings.app_name == 'pusher-ci'
    assert settings.is_production is True
    assert settings.debug is True
    assert (settings.host, settings.port) == ('127.0.0.1', 9001)
    assert settings.database_uri == 'sqlite:///custom.db'
    assert settings.sqlalchemy_track_modifications is True
    assert settings.log_level == 'DEBUG'
    assert settings.log_json is False
    assert settings.request_id_header == 'X-Trace'
    assert settings.max_content_length == 1024


def test_flask_env_is_the_fallback_for_app_env():
    settings = Settings.from_env({'FLASK_ENV': 'production', 'SECRET_KEY': 's'})

    assert settings.env == 'production'


def test_sqlalchemy_database_uri_is_an_accepted_alias():
    settings = Settings.from_env({'SQLALCHEMY_DATABASE_URI': 'sqlite:///x.db'})

    assert settings.database_uri == 'sqlite:///x.db'


def test_reads_from_os_environ_when_no_mapping_is_given(monkeypatch):
    monkeypatch.setenv('APP_NAME', 'from-the-real-environment')

    assert Settings.from_env().app_name == 'from-the-real-environment'


def test_the_legacy_environment_variables_are_recorded():
    settings = Settings.from_env({'PORT': '8000', 'ANALYTICS_SALT': 'pepper'})

    assert settings.extras == {'PORT': '8000', 'ANALYTICS_SALT': 'pepper'}
    assert settings.as_dict()['legacy_env_present'] == ['ANALYTICS_SALT', 'PORT']


@pytest.mark.parametrize(
    'raw,expected',
    [('1', True), ('true', True), ('yes', True), ('ON', True),
     ('0', False), ('false', False), ('no', False), ('OFF', False)],
)
def test_boolean_spellings_are_accepted(raw, expected):
    assert Settings.from_env({'DEBUG': raw}).debug is expected


def test_an_unparseable_boolean_is_refused():
    with pytest.raises(ConfigError, match='must be a boolean'):
        Settings.from_env({'DEBUG': 'sometimes'})


def test_a_blank_or_absent_boolean_falls_back_to_the_default():
    assert Settings.from_env({'DEBUG': ''}).debug is False
    assert Settings.from_env({'LOG_JSON': '  '}).log_json is True


def test_a_non_numeric_port_is_refused():
    with pytest.raises(ConfigError, match='PORT must be an integer'):
        Settings.from_env({'PORT': 'http'})


def test_a_port_below_one_is_refused():
    with pytest.raises(ConfigError, match='PORT must be >= 1'):
        Settings.from_env({'PORT': '0'})


def test_the_validation_guard_rejects_a_port_above_the_tcp_range():
    with pytest.raises(ConfigError, match='PORT out of range: 70000'):
        Settings.validate(Settings(port=70000))


def test_an_unknown_log_level_is_refused():
    with pytest.raises(ConfigError, match='LOG_LEVEL must be one of'):
        Settings.from_env({'LOG_LEVEL': 'chatty'})


def test_production_without_a_secret_key_refuses_to_start():
    with pytest.raises(ConfigError, match='SECRET_KEY must be set'):
        Settings.validate(Settings(env='production'))


def test_production_with_a_secret_key_is_accepted():
    settings = Settings.from_env({'APP_ENV': 'prod', 'SECRET_KEY': 's3cret'})

    assert settings.is_production is True
    assert settings.as_dict()['secret_key_configured'] is True


def test_a_non_numeric_content_length_is_refused():
    with pytest.raises(ConfigError, match='MAX_CONTENT_LENGTH must be an integer'):
        Settings.from_env({'MAX_CONTENT_LENGTH': 'twelve'})


def test_a_content_length_below_one_is_refused():
    with pytest.raises(ConfigError, match='MAX_CONTENT_LENGTH must be >= 1'):
        Settings.from_env({'MAX_CONTENT_LENGTH': '0'})


def test_as_dict_never_reveals_the_secret():
    settings = Settings.from_env({'SECRET_KEY': 'super-secret', 'APP_ENV': 'production'})
    view = settings.as_dict()

    assert view['secret_key_configured'] is True
    assert 'super-secret' not in repr(view)
    assert view['database_configured'] is False
    assert view['data_dir'] == str(paths.DATA_DIR)


def test_app_version_comes_from_the_package():
    from message_pusher import __version__

    assert Settings.from_env({}).app_version == __version__


def test_get_settings_caches_and_reset_settings_drops_the_cache():
    reset_settings()
    first = get_settings()

    assert get_settings() is first
    assert get_settings(refresh=True) is not first

    reset_settings()
    assert get_settings() is not first


def test_paths_accept_the_prefixed_spelling_first(monkeypatch, tmp_path):
    monkeypatch.setenv('MESSAGE_PUSHER_DATA_DIR', str(tmp_path / 'prefixed'))
    monkeypatch.setenv('DATA_DIR', str(tmp_path / 'bare'))

    assert paths.ENV_PREFIX == 'MESSAGE_PUSHER_'
    assert paths._env_path('DATA_DIR', tmp_path) == tmp_path / 'prefixed'


def test_paths_expand_a_user_home_in_the_supplied_value(monkeypatch, tmp_path):
    monkeypatch.setenv('MESSAGE_PUSHER_LOG_DIR', '~/pusher-logs')

    assert paths._env_path('LOG_DIR', tmp_path) == pathlib.Path('~/pusher-logs').expanduser()


def test_paths_fall_back_to_the_bare_spelling(monkeypatch, tmp_path):
    monkeypatch.delenv('MESSAGE_PUSHER_INSTANCE_DIR', raising=False)
    monkeypatch.setenv('INSTANCE_DIR', str(tmp_path / 'bare'))

    assert paths._env_path('INSTANCE_DIR', tmp_path) == tmp_path / 'bare'


def test_paths_fall_back_to_the_supplied_default(monkeypatch):
    monkeypatch.delenv('MESSAGE_PUSHER_LOG_DIR', raising=False)
    monkeypatch.delenv('LOG_DIR', raising=False)

    assert paths._env_path('LOG_DIR', paths.DATA_DIR / 'log') == paths.DATA_DIR / 'log'


def test_ensure_runtime_dirs_is_idempotent():
    paths.ensure_runtime_dirs()
    paths.ensure_runtime_dirs()

    assert paths.INSTANCE_DIR.is_dir() and paths.LOG_DIR.is_dir()


def test_as_dict_reports_the_layout():
    layout = paths.as_dict()

    assert set(layout) == {
        'package_dir', 'project_root', 'templates_dir', 'data_dir', 'instance_dir'
    }
    assert layout['package_dir'] == str(paths.PACKAGE_DIR)
    assert paths.PACKAGE_DIR.is_dir()

