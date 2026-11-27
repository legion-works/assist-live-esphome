# SPDX-License-Identifier: GPL-3.0-or-later
import subprocess

import pytest

from tests.event_vectors import COMPONENT, ROOT, compiler, run
from tests.test_reply_options import reply_config


def condition_cpp(value):
    if isinstance(value, list):
        return " && ".join(f"({condition_cpp(item)})" for item in value)
    key, body = next(iter(value.items()))
    if key == "lambda":
        return f"([&]() {{ {body} }})()"
    if key == "and":
        return condition_cpp(body)
    if key == "not":
        return f"!({condition_cpp(body)})"
    if key in {"switch.is_off", "switch.is_on"}:
        state = f"id({body['id']}).state"
        return f"!{state}" if key.endswith("off") else state
    if key == "voice_assistant.is_running":
        return "va.running"
    if key == "media_player.is_announcing":
        return "announcing"
    raise AssertionError(f"unsupported condition: {value}")


def actions_cpp(actions):
    result = []
    for action in actions:
        key, value = next(iter(action.items()))
        if key == "lambda":
            result.append(f"[&]() {{ {value} }}();")
        elif key == "if":
            result.append(
                f"if ({condition_cpp(value['condition'])}) {{"
                + actions_cpp(value.get("then", []))
                + "} else {"
                + actions_cpp(value.get("else", []))
                + "}"
            )
        elif key == "assist_live.emit_event":
            result.append('events.push_back("wake"); wake_times.push_back(now);')
        elif key == "voice_assistant.stop":
            result.append("va.stop();")
        elif key == "voice_assistant.start":
            result.append("va.start();")
        elif key == "switch.turn_off":
            result.append(f"id({value['id']}).state = false;")
        elif key == "media_player.stop":
            result.append('announcing = false; events.push_back("media stop");')
        elif key == "script.execute":
            name = value["id"]
            if name == "play_sound":
                result.append('events.push_back("chime");')
            else:
                argument = "wake_word" if "wake_word" in value else ""
                result.append(f"id({name}).execute({argument});")
        elif key == "delay":
            assert value == "300ms"
            result.append("chime_wait();")
        elif key == "wait_until":
            assert value["timeout"] == "500ms"
            condition = condition_cpp(value["condition"])
            result.append(f"wait_for_idle([&]() {{ return {condition}; }});")
        else:
            raise AssertionError(f"unsupported action: {action}")
    return "\n".join(result)


@pytest.fixture(scope="module")
def reply_barge_native(tmp_path_factory):
    tmp_path = tmp_path_factory.mktemp("reply-barge")
    config = reply_config(ROOT / "tests/fixtures/voice-pe-pre-roll.yaml", tmp_path)
    scripts = {str(item["id"]): item for item in config["script"]}
    if "assist_live_restart_reply_wake" not in scripts:
        return None
    restart = scripts["assist_live_restart_reply_wake"]
    assert restart["mode"] == "single", "one pending reply restart"
    handler = config["micro_wake_word"]["on_wake_word_detected"]["then"]
    on_error = config["voice_assistant"]["on_error"]["then"]
    # Stock error actions control LEDs and phases. The harness runs only the added tail.
    added = [
        item
        for item in on_error
        if "pre_roll_mic" in str(item.get("lambda", ""))
        or str(item.get("script.execute", {}).get("id", "")).startswith("assist_live_")
    ]
    assert added == on_error[len(on_error) - len(added) :], (
        "error actions added after the stock actions"
    )
    source = (ROOT / "tests/native/reply_barge.cpp").read_text()
    for marker, actions in (
        ("HANDLER_BODY", handler),
        ("RESTART_BODY", restart["then"]),
        ("CANCEL_BODY", scripts["assist_live_cancel_reply_wake"]["then"]),
        ("ERROR_BODY", added),
    ):
        source = source.replace(marker, actions_cpp(actions))
    path = tmp_path / "reply_barge.cpp"
    path.write_text(source)
    executable = str(tmp_path / "reply_barge")
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
    return executable


@pytest.mark.parametrize(
    "scenario",
    [
        "reply",
        "stop",
        "timer",
        "muted",
        "listening",
        "thinking",
        "announcement",
        "timeout",
        "pending_stop",
        "pending_wake",
        "pending_mute",
        "pending_error",
        "pending_timer",
        "chime",
        "stop_during_chime",
        "stop_during_chime_with_announcement",
        "stop_during_chime_with_timer",
        "timer_during_chime",
        "announcement_during_chime",
        "split_clock",
        "split_clock_chime",
        "split_clock_wrap",
    ],
)
def test_reply_stop_then_start(reply_barge_native, scenario):
    assert reply_barge_native is not None, "missing reply stop-to-start path"
    result = subprocess.run(
        [reply_barge_native, scenario], capture_output=True, text=True, timeout=60
    )
    assert result.returncode == 0, result.stdout + result.stderr
    assert result.stdout == f"PASS {scenario}\n"
