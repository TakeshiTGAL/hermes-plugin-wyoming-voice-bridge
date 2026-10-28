"""Skip checks that need the Wyoming library, and skip collection on Python 3.9.

Use Hermes's secret scope when it is installed. Without Hermes, install a
contextvar stand-in so the same tests still run. It is not the product.
Multiplex with no scope raises; a scope wins over the environment.
"""
import importlib.util
import os
import sys
from contextvars import ContextVar
from pathlib import Path

import pytest

if sys.version_info < (3, 10):
    collect_ignore = [
        path.name
        for path in Path(__file__).parent.glob("test_*.py")
        if path.name != "test_python_floor.py"
    ]

# These call the protocol. Without the library the plugin returns one sentence
# and does not open a socket. Hermes installs wyoming from plugin.yaml on enable.
_NEEDS_WYOMING = {
    "test_is_available_is_address_shape_not_a_live_server",
    "test_tool_handler_keeps_the_env_host",
    "test_speech_path_does_not_ask_for_approval",
    "test_installed_false_is_not_a_candidate_and_null_is",
    "test_languages_over_two_hundred_are_marked",
    "test_empty_and_default_names_are_not_sent",
    "test_text_limits_stop_before_connect",
    "test_symlink_and_unconvertible_audio_send_nothing",
    "test_target_wav_does_not_start_ffmpeg_and_conversion_is_an_argv_list",
    "test_file_over_25_mb_does_not_convert_or_connect",
    "test_wav_header_over_20_mib_sends_no_audio",
    "test_small_flac_that_expands_past_20_mib_sends_no_audio",
    "test_catalog_of_500_is_allowed_and_501_sends_nothing_else",
    "test_synthesis_over_20_mib_is_not_written",
    "test_partial_pcm_is_not_success",
    "test_json_array_is_refused_before_the_library",
    "test_describe_default_is_ten_seconds_and_a_short_hang_says_so",
    "test_logs_omit_words_and_pcm",
    "test_transcribe_audio_on_hermes_main",
    "test_transcribe_audio_on_hermes_v0214",
    "test_language_must_match_a_listed_code_exactly",
    "test_unnamed_model_sends_a_language_only_when_every_model_lists_it",
    "test_speakers_over_fifty_are_marked",
    "test_fifty_speakers_are_not_marked_truncated",
    "test_missing_installed_counts_as_installed",
    "test_unknown_model_sends_no_audio",
    "test_empty_transcript_is_success_and_disconnect_is_not",
    "test_both_is_not_success_when_one_side_fails",
    "test_speech_timeout_text",
    "test_voice_not_listed_does_not_synthesize",
    "test_wav_is_replaced_only_after_audio",
    "test_tool_ignores_a_host_argument",
    "test_describe_and_empty_transcript_are_distinct",
    "test_silence_longer_than_connect_timeout_still_returns",
    "test_server_error_event_is_not_success",
    "test_non_json_line_is_not_a_closed_connection",
    "test_dropped_connection_is_not_a_transcript",
    "test_stop_without_audio_start_is_empty_audio_not_a_format_error",
    "test_empty_audio_is_not_a_file",
    "test_synthesize_returns_pcm_without_writing",
    "test_open_drops_any_read_timeout_the_library_sets",
    "test_connect_timeout_is_five_seconds_and_refused_port_fails",
    "test_status_tool_asks_about_and_describes_the_scope_server",
}

_SKIP_REASON = (
    "plugin.yaml lists wyoming==1.5.4 in python_dependencies, and this Python does not have it. "
    "Hermes installs it on enable. Without it the plugin sends no audio and returns one sentence."
)


def pytest_collection_modifyitems(config, items):
    import wyoming_pin

    installed = importlib.util.find_spec("wyoming") is not None
    if installed and wyoming_pin.library_status() == "ready":
        return
    if installed:
        reason = (
            "This build's wyoming sha256 table does not list the installed tree, "
            "so the package is not imported and protocol tests are skipped."
        )
    else:
        reason = _SKIP_REASON
    skip = pytest.mark.skip(reason=reason)
    for item in items:
        if item.name in _NEEDS_WYOMING:
            item.add_marker(skip)


def pytest_configure(config):
    try:
        import agent.secret_scope  # noqa: F401
    except ImportError:
        _install_scope_standin()


def _install_scope_standin():
    import types

    scope_var = ContextVar("_SECRET_SCOPE", default=None)
    state = {"multiplex": False}

    class UnscopedSecretError(RuntimeError):
        def __init__(self, secret_name="", developer_detail=""):
            self.secret_name = secret_name
            self.developer_detail = developer_detail
            super().__init__(secret_name or "unscoped")

    def set_multiplex_active(active):
        state["multiplex"] = bool(active)

    def set_secret_scope(secrets, *, profile_home=None):
        del profile_home
        return scope_var.set(None if secrets is None else dict(secrets))

    def reset_secret_scope(token):
        scope_var.reset(token)

    def get_secret(name, default=None):
        bound = scope_var.get()
        if bound is not None:
            if name in bound:
                return bound[name]
            if state["multiplex"]:
                return default
            value = os.environ.get(name)
            return default if value is None else value
        if state["multiplex"]:
            raise UnscopedSecretError(name)
        value = os.environ.get(name)
        return default if value is None else value

    package = sys.modules.get("agent")
    if package is None:
        package = types.ModuleType("agent")
        package.__path__ = []
        sys.modules["agent"] = package
    module = types.ModuleType("agent.secret_scope")
    module.UnscopedSecretError = UnscopedSecretError
    module.set_multiplex_active = set_multiplex_active
    module.set_secret_scope = set_secret_scope
    module.reset_secret_scope = reset_secret_scope
    module.get_secret = get_secret
    package.secret_scope = module
    sys.modules["agent.secret_scope"] = module
