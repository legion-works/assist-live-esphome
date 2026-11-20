# SPDX-License-Identifier: GPL-3.0-or-later
import copy

import pytest

from tests.event_vectors import ROOT
from tests.test_pre_roll import resolved_config, stock_wake_config


def reply_config(path, tmp_path, *, window=True, restart=True):
    config = tmp_path / "reply-options.yaml"
    config.write_text(
        f"packages:\n  base: !include {path}\n"
        "substitutions:\n"
        f"  assist_live_reply_window: '{str(window).lower()}'\n"
        f"  assist_live_reply_restart: '{str(restart).lower()}'\n"
    )
    return resolved_config(config, tmp_path)


def assert_stock_off(stock, config, arm="return;"):
    handler = copy.deepcopy(config["micro_wake_word"]["on_wake_word_detected"]["then"])
    assert handler.pop(0) == {
        "assist_live.emit_event": {
            "id": "assist_live_component",
            "stage": "wake_detected",
            "data": "{}",
        }
    }
    removed = 0

    def without_slots(value):
        nonlocal removed
        if isinstance(value, list):
            result = []
            for item in value:
                if item == {"lambda": arm} or item == {
                    "lambda": "id(pre_roll_mic).wake_started();"
                }:
                    removed += 1
                else:
                    result.append(without_slots(item))
            return result
        if isinstance(value, dict):
            return {key: without_slots(item) for key, item in value.items()}
        return value

    assert (
        without_slots(handler)
        == stock["micro_wake_word"]["on_wake_word_detected"]["then"]
    ), "default-off handler must equal stock except timing and arm slots"
    assert removed == 2
    for key in ("select", "script", "switch", "media_player", "microphone", "globals"):
        assert config[key] == stock[key], key
    assert config["micro_wake_word"]["models"] == stock["micro_wake_word"]["models"]
    assert config["esphome"]["on_boot"] == stock["esphome"]["on_boot"]


@pytest.mark.parametrize("name", ["voice-pe.yaml", "pre-roll.yaml", "wake-word.yaml"])
def test_repository_examples_default_both_options_off(name):
    source = (ROOT / "examples" / name).read_text()
    for option in ("assist_live_reply_window", "assist_live_reply_restart"):
        assert f"  {option}: 'false'" in source


def test_default_off_resolves_to_stock(tmp_path):
    stock = stock_wake_config(tmp_path)
    config = resolved_config(ROOT / "tests/fixtures/voice-pe.yaml", tmp_path)
    assert config["substitutions"].get("assist_live_reply_window") == "false"
    assert config["substitutions"].get("assist_live_reply_restart") == "false"
    assert_stock_off(stock, config)


@pytest.mark.parametrize(
    "window,restart", [(False, False), (True, False), (False, True), (True, True)]
)
def test_reply_options_independent(tmp_path, window, restart):
    config = reply_config(
        ROOT / "tests/fixtures/voice-pe.yaml", tmp_path, window=window, restart=restart
    )
    scripts = {str(item["id"]) for item in config["script"]}
    assert ("assist_live_reply_wake_tail" in scripts) is window
    assert ("assist_live_restart_reply_wake" in scripts) is restart
    if not window and not restart:
        assert_stock_off(stock_wake_config(tmp_path), config)


def test_pre_roll_default_off_handler_and_cutoffs_are_stock(tmp_path):
    from tests.test_pre_roll import assert_stock_wake_handler

    stock = stock_wake_config(tmp_path)
    config = resolved_config(ROOT / "tests/fixtures/voice-pe-pre-roll.yaml", tmp_path)
    for option in ("assist_live_reply_window", "assist_live_reply_restart"):
        assert config["substitutions"][option] == "false"
    assert_stock_wake_handler(
        config["micro_wake_word"]["on_wake_word_detected"]["then"],
        stock["micro_wake_word"]["on_wake_word_detected"]["then"],
        "id(pre_roll_mic).wake_detected();",
    )
    for key in ("select", "script", "globals"):
        assert config[key] == stock[key]
