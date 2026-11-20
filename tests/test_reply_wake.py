# SPDX-License-Identifier: GPL-3.0-or-later
import re
import subprocess

import pytest

from tests.event_vectors import COMPONENT, ROOT, compiler, run
from tests.test_pre_roll import resolved_config, stock_wake_config


@pytest.fixture(scope="module")
def reply_wake_native(tmp_path_factory):
    executable = str(tmp_path_factory.mktemp("reply-wake") / "reply_wake")
    run(
        [
            compiler(),
            "-std=c++17",
            "-Wall",
            "-Wextra",
            "-Werror",
            "-I",
            str(COMPONENT),
            str(ROOT / "tests/native/reply_wake.cpp"),
            "-o",
            executable,
        ]
    )
    return executable


@pytest.mark.parametrize(
    "scenario",
    [
        "window_start_end",
        "tail_1000_ms",
        "select_inside_window",
        "very_selected",
        "mute_during_window",
        "follow_up_listening",
        "announcement",
        "overlapping_reply",
        "clock_wrap",
        "change_reasons",
        "stuck_va_timeout",
    ],
)
def test_native_reply_wake(reply_wake_native, scenario):
    result = subprocess.run(
        [reply_wake_native, scenario], capture_output=True, text=True, timeout=60
    )
    assert result.returncode == 0, result.stdout + result.stderr
    assert result.stdout == f"PASS {scenario}\n"


def assert_stock_mapping(stock, actual):
    sensitivity = next(
        item for item in stock["select"] if item["id"] == "wake_word_sensitivity"
    )
    body = sensitivity["on_value"][0]["then"][0]["lambda"]
    expected = [
        tuple(map(int, values))
        for values in re.findall(
            r"id\(okay_nabu\).set_probability_cutoff\((\d+)\);.*?"
            r"id\(hey_jarvis\).set_probability_cutoff\((\d+)\);.*?"
            r"id\(hey_mycroft\).set_probability_cutoff\((\d+)\);",
            body,
            re.DOTALL,
        )
    ]
    assert len(expected) == 3, "stock sensitivity mapping drift: unknown format"
    assert actual == expected, "stock sensitivity mapping drift"


def test_resolved_cutoff_mapping_matches_stock(reply_wake_native, tmp_path):
    output = run([reply_wake_native, "mapping"])
    actual = [tuple(map(int, line.split())) for line in output.splitlines()]
    stock = stock_wake_config(tmp_path)
    assert_stock_mapping(stock, actual)
    changed = [*actual]
    changed[1] = (177, 235, 242)
    with pytest.raises(AssertionError, match="stock sensitivity mapping drift"):
        assert_stock_mapping(stock, changed)


def test_resolved_reply_window_wiring_preserves_stock(tmp_path):
    stock = stock_wake_config(tmp_path)
    config = resolved_config(ROOT / "tests/fixtures/voice-pe.yaml", tmp_path)
    assert_reply_wake_wiring(stock, config)


def assert_reply_wake_wiring(stock, config):
    assert any(
        item["id"] == "reply_wake_window" for item in config.get("globals", [])
    ), "missing reply window policy"
    scripts = {str(item["id"]): item for item in config["script"]}
    update = scripts["assist_live_update_reply_wake"]["then"][0]["lambda"]
    assert (
        "id(external_media_player).state == media_player::MEDIA_PLAYER_STATE_ANNOUNCING"
        in update
    )
    assert "id(va).is_running()" in update
    assert "id(reply_wake_window).observe(millis()," in update
    assert (
        scripts["assist_live_apply_wake_cutoffs"]["then"][0]["lambda"].count(
            ".set_probability_cutoff("
        )
        == 3
    )
    apply = scripts["assist_live_apply_wake_cutoffs"]["then"][0]["lambda"]
    for model, index in (("okay_nabu", 0), ("hey_jarvis", 1), ("hey_mycroft", 2)):
        assert f"id({model}).set_probability_cutoff(cutoffs[{index}]);" in apply
        assert f'"{model} reason=%s cutoff=%u"' in apply
    assert "take_change()" in apply
    tail = scripts["assist_live_reply_wake_tail"]
    assert tail["mode"] == "restart"
    assert tail["then"][0] == {
        "wait_until": {
            "condition": {
                "lambda": "return id(external_media_player).state != "
                "media_player::MEDIA_PLAYER_STATE_ANNOUNCING\n"
                "    && (!id(va).is_running() || "
                "id(reply_wake_window).listening_turn());"
            },
            "timeout": "30s",
        }
    }
    assert tail["then"][2] == {"delay": "1000ms"}
    assert "interval" not in config
    before_select = next(
        item for item in stock["select"] if item["id"] == "wake_word_sensitivity"
    )
    after_select = next(
        item for item in config["select"] if item["id"] == "wake_word_sensitivity"
    )
    assert {k: v for k, v in after_select.items() if k != "on_value"} == {
        k: v for k, v in before_select.items() if k != "on_value"
    }
    assert after_select["on_value"][0]["then"] == [
        {
            "lambda": "static bool attached = false;\n"
            "if (!attached) {\n"
            "  id(external_media_player).add_on_state_callback("
            "[](media_player::MediaPlayerState) {\n"
            "    id(assist_live_update_reply_wake).execute();\n"
            "  });\n"
            "  attached = true;\n"
            "}\n"
            "id(reply_wake_window).select(x);\n"
            "id(assist_live_update_reply_wake).execute();"
        }
    ]
    assert config["media_player"] == stock["media_player"]
    assert config["esphome"]["on_boot"] == stock["esphome"]["on_boot"]
    before = stock["voice_assistant"]["on_listening"]["then"]
    assert config["voice_assistant"]["on_listening"]["then"] == before + [
        {"lambda": "id(reply_wake_window).listening(millis());"},
        {"script.execute": {"id": "assist_live_apply_wake_cutoffs"}},
    ]
    for key in ("switch", "microphone"):
        assert config[key] == stock[key], key
    assert config["micro_wake_word"]["models"] == stock["micro_wake_word"]["models"]
    for item in stock["script"]:
        assert scripts[item["id"]] == item, item["id"]


def test_resolved_select_callback_registered_once(tmp_path):
    config = resolved_config(ROOT / "tests/fixtures/voice-pe.yaml", tmp_path)
    select = next(
        item for item in config["select"] if item["id"] == "wake_word_sensitivity"
    )["on_value"][0]["then"][0]["lambda"]
    scripts = {str(item["id"]): item for item in config["script"]}
    apply = scripts["assist_live_apply_wake_cutoffs"]["then"][0]["lambda"]
    update = scripts["assist_live_update_reply_wake"]["then"][0]["lambda"]
    expire = scripts["assist_live_reply_wake_tail"]["then"][3]["lambda"]
    source = (ROOT / "tests/native/reply_wake_callbacks.cpp").read_text()
    for marker, body in (
        ("SELECT_BODY", select),
        ("APPLY_BODY", apply),
        ("UPDATE_BODY", update),
        ("EXPIRE_BODY", expire),
    ):
        source = source.replace(marker, body)
    for name, body in (
        ("control", source),
        (
            "duplicate",
            source.replace("if (!attached)", "if (!attached || !x.empty())"),
        ),
    ):
        path = tmp_path / f"{name}.cpp"
        path.write_text(body)
        executable = str(tmp_path / name)
        run(
            [
                compiler(),
                "-std=c++17",
                "-Wall",
                "-Wextra",
                "-Werror",
                "-I",
                str(COMPONENT),
                str(path),
                "-o",
                executable,
            ]
        )
        result = subprocess.run(
            [executable], capture_output=True, text=True, timeout=60
        )
        if name == "control":
            assert result.returncode == 0, result.stdout + result.stderr
            assert result.stdout == "PASS one callback and one log per model per edge\n"
        else:
            assert result.returncode != 0
            assert "exactly one state callback" in result.stderr
