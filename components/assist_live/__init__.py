# SPDX-License-Identifier: GPL-3.0-or-later
import json
import re

import esphome.codegen as cg
import esphome.config_validation as cv
import esphome.final_validate as fv
from esphome import automation, yaml_util
from esphome.components import (
    audio,
    binary_sensor,
    esp32,
    media_player,
    microphone,
    sensor,
    switch,
)
from esphome.const import (
    CONF_FORCE_UPDATE,
    CONF_ID,
    DEVICE_CLASS_CONNECTIVITY,
    ENTITY_CATEGORY_DIAGNOSTIC,
    STATE_CLASS_MEASUREMENT,
    STATE_CLASS_TOTAL_INCREASING,
    UNIT_MILLISECOND,
)
from esphome.core import ID, Lambda


def AUTO_LOAD(config):
    return (
        ["json", "sensor", "binary_sensor"] if config.get("diagnostics") else ["json"]
    )


assist_live_ns = cg.esphome_ns.namespace("assist_live")
AssistLiveComponent = assist_live_ns.class_("AssistLiveComponent", cg.Component)
# Do not make this ID a candidate for stock id-less microphone actions.
# The C++ class implements Microphone. Final validation binds only VA to it.
PreRollMicrophone = assist_live_ns.class_("PreRollMicrophone", cg.Component)
EmitEventAction = assist_live_ns.class_("EmitEventAction", automation.Action)
Stage = assist_live_ns.enum("Stage", is_class=True)
STAGES = {
    name.lower(): getattr(Stage, name)
    for name in ("WAKE_DETECTED", "MIC_OPEN", "PLAYBACK_START", "PLAYBACK_END")
}


class _DeviceKey:
    __slots__ = ("_bytes",)

    def __init__(self, value):
        self._bytes = bytes.fromhex(value)

    def __str__(self):
        return "[redacted]"

    def __repr__(self):
        return "[redacted]"


def _represent_device_key(dumper, value):
    # The marker contains no key bytes, with or without --show-secrets.
    return dumper.represent_sensitive(yaml_util.SensitiveStr("[redacted]"))


yaml_util.ESPHomeDumper.add_representer(_DeviceKey, _represent_device_key)


def identifier(value):
    value = cv.string_strict(value)
    if not re.fullmatch(r"[A-Za-z0-9_-]{1,128}", value):
        raise cv.Invalid("expected an anonymous satellite key")
    return value


def hmac_key(value):
    value = cv.string_strict(value)
    if not re.fullmatch(r"[0-9a-fA-F]{64}", value):
        raise cv.Invalid("expected a 32-byte HMAC key in hexadecimal")
    return _DeviceKey(value)


def server_address(value):
    value = cv.string_strict(value)
    if len(value) > 253 or not re.fullmatch(
        r"[A-Za-z0-9_-]+(?:\.[A-Za-z0-9_-]+)*\.?", value
    ):
        raise cv.Invalid("expected an IPv4 address or host name without a URL path")
    return value


def _validate_data_value(value, depth=0):
    if depth > 8:
        raise cv.Invalid("event data exceeds eight nested levels")
    if isinstance(value, dict):
        for key, child in value.items():
            if not isinstance(key, str):
                raise cv.Invalid("event object keys must be strings")
            _validate_data_value(child, depth + 1)
    elif isinstance(value, list):
        for child in value:
            _validate_data_value(child, depth + 1)
    elif type(value) is int:
        if not -(2**63) <= value < 2**64:
            raise cv.Invalid("event integers must fit in 64 bits")
    elif value is not None and not isinstance(value, (str, bool)):
        raise cv.Invalid("event data does not support floating-point values")


def event_data(value):
    if not isinstance(value, dict) or value.get("quality") == "measured":
        raise cv.Invalid("expected an event object, not a measured sample")
    _validate_data_value(value)
    try:
        data = json.dumps(
            value,
            sort_keys=True,
            ensure_ascii=False,
            separators=(",", ":"),
            allow_nan=False,
        )
    except (TypeError, ValueError):
        raise cv.Invalid("expected finite JSON event data") from None
    if len(data.encode()) > 256:
        raise cv.Invalid("event data exceeds 256 bytes")
    return data


def pre_roll_stream_limits(config):
    audio.set_stream_limits(
        min_bits_per_sample=32,
        max_bits_per_sample=32,
        min_channels=2,
        max_channels=2,
        min_sample_rate=16000,
        max_sample_rate=16000,
    )(config)
    return config


PRE_ROLL_SCHEMA = cv.All(
    cv.Schema(
        {
            cv.GenerateID(): cv.declare_id(PreRollMicrophone),
            cv.Required("microphone"): cv.use_id(microphone.Microphone),
            cv.Required("wake_sound"): cv.use_id(switch.Switch),
            cv.Optional("length_ms", default=250): cv.int_range(min=1, max=1000),
        }
    ).extend(cv.COMPONENT_SCHEMA),
    pre_roll_stream_limits,
)

TURN_DIAGNOSTICS = (
    "pre_roll_ms",
    "replay_gate_delay_ms",
    "history_trimmed_ms",
    "overflows",
    "dropped_ms",
    "first_live_queue_ms",
    "history_end_queue_ms",
    "turn_end_queue_ms",
)
COUNTER_DIAGNOSTICS = (
    "events_sent",
    "events_confirmed",
    "events_dropped",
    "events_refused",
    "sender_initialization_failures",
    "expired_gates",
)
DIAGNOSTIC_SCHEMA = cv.Schema(
    {
        **{
            cv.Optional(key): sensor.sensor_schema(
                accuracy_decimals=0,
                unit_of_measurement=UNIT_MILLISECOND if key.endswith("_ms") else "",
                state_class=STATE_CLASS_MEASUREMENT,
                entity_category=ENTITY_CATEGORY_DIAGNOSTIC,
            ).extend({cv.Optional(CONF_FORCE_UPDATE, default=True): cv.boolean})
            for key in TURN_DIAGNOSTICS
        },
        **{
            cv.Optional(key): sensor.sensor_schema(
                accuracy_decimals=0,
                state_class=STATE_CLASS_TOTAL_INCREASING,
                entity_category=ENTITY_CATEGORY_DIAGNOSTIC,
            )
            for key in COUNTER_DIAGNOSTICS
        },
        cv.Optional("passthrough_reached"): binary_sensor.binary_sensor_schema(
            entity_category=ENTITY_CATEGORY_DIAGNOSTIC,
        ),
        cv.Optional("connected"): binary_sensor.binary_sensor_schema(
            entity_category=ENTITY_CATEGORY_DIAGNOSTIC,
            device_class=DEVICE_CLASS_CONNECTIVITY,
        ),
    }
)


def validate_diagnostics(config):
    diagnostics = config.get("diagnostics", {})
    for key in ("connected", "events_confirmed"):
        if key in diagnostics and config["transport"] != "websocket":
            raise cv.Invalid(f"diagnostics.{key} requires websocket transport")
    for key in (*TURN_DIAGNOSTICS, "passthrough_reached", "expired_gates"):
        if key in diagnostics and "pre_roll" not in config:
            raise cv.Invalid(f"diagnostics.{key} requires pre_roll")
    return config


CONFIG_SCHEMA = cv.All(
    cv.Schema(
        {
            cv.GenerateID(): cv.declare_id(AssistLiveComponent),
            cv.Required("device"): identifier,
            cv.Required("hmac_key"): cv.sensitive(hmac_key),
            cv.Required("server"): server_address,
            cv.Required("transport"): cv.one_of("udp", "websocket", lower=True),
            cv.Required("media_player_id"): cv.use_id(media_player.MediaPlayer),
            cv.Optional("port", default=8765): cv.port,
            cv.Optional("pre_roll"): PRE_ROLL_SCHEMA,
            cv.Optional("diagnostics"): DIAGNOSTIC_SCHEMA,
        }
    ).extend(cv.COMPONENT_SCHEMA),
    cv.only_on_esp32,
    cv.only_with_framework("esp-idf"),
    validate_diagnostics,
)


def validate_pre_roll(config):
    if "pre_roll" not in config:
        return config
    pre_roll = config["pre_roll"]
    full = fv.full_config.get()
    try:
        va = full.get_config_for_path(["voice_assistant"])
    except KeyError:
        raise cv.Invalid(
            "pre_roll requires the stock Voice PE voice_assistant"
        ) from None
    sources = va.get("microphone", [])
    if len(sources) != 2 or any(
        str(source.get("microphone")) != str(pre_roll["microphone"])
        or source.get("channels") != [channel]
        or source.get("gain_factor") != 1
        or source.get("bits_per_sample") != 16
        for channel, source in enumerate(sources)
    ):
        raise cv.Invalid("pre_roll requires the unchanged stock two-channel VA sources")
    audio.final_validate_audio_schema(
        "pre_roll",
        audio_device="microphone",
        bits_per_sample=32,
        channels=2,
        sample_rate=16000,
        audio_device_issue=True,
    )(pre_roll)
    # Stock sources have no IDs in YAML. List merging cannot replace them.
    for source in sources:
        source["microphone"] = ID(
            str(pre_roll[CONF_ID]), is_declaration=False, type=microphone.Microphone
        )
    return config


FINAL_VALIDATE_SCHEMA = validate_pre_roll


async def to_code(config):
    component = cg.new_Pvariable(config[CONF_ID])
    await cg.register_component(component, config)
    cg.add(component.set_media_player(await cg.get_variable(config["media_player_id"])))
    cg.add(component.set_device(config["device"]))
    key = config["hmac_key"]._bytes
    cg.add(
        component.set_hmac_key(
            cg.RawExpression(
                "std::array<uint8_t, 32>{"
                + ",".join(f"0x{byte:02x}" for byte in key)
                + "}"
            )
        )
    )
    cg.add(component.set_server(config["server"]))
    cg.add(component.set_port(config["port"]))
    cg.add(component.set_websocket(config["transport"] == "websocket"))
    if diagnostics := config.get("diagnostics"):
        cg.add_define("USE_ASSIST_LIVE_DIAGNOSTICS")
        for keys, setter in (
            (TURN_DIAGNOSTICS, component.set_turn_sensor),
            (COUNTER_DIAGNOSTICS, component.set_counter_sensor),
        ):
            for index, key in enumerate(keys):
                if key in diagnostics:
                    entity = await sensor.new_sensor(diagnostics[key])
                    cg.add(setter(index, entity))
        for key, setter in (
            ("passthrough_reached", component.set_passthrough_sensor),
            ("connected", component.set_connected_sensor),
        ):
            if key in diagnostics:
                entity = await binary_sensor.new_binary_sensor(diagnostics[key])
                cg.add(setter(entity))
    if "pre_roll" in config:
        cg.add_define("USE_ASSIST_LIVE_PRE_ROLL")
        pre_roll = config["pre_roll"]
        mic = cg.new_Pvariable(pre_roll[CONF_ID])
        await cg.register_component(mic, pre_roll)
        await microphone.register_microphone(mic, pre_roll)
        cg.add(mic.set_source(await cg.get_variable(pre_roll["microphone"])))
        cg.add(mic.set_wake_sound(await cg.get_variable(pre_roll["wake_sound"])))
        cg.add(mic.set_length_ms(pre_roll["length_ms"]))
        cg.add(mic.set_parent(component))
        cg.add(component.set_pre_roll(mic))
    if config["transport"] == "websocket":
        cg.add_define("USE_ASSIST_LIVE_WEBSOCKET")
        esp32.include_builtin_idf_component("tcp_transport")
        esp32.add_idf_sdkconfig_option("CONFIG_WS_TRANSPORT", True)


@automation.register_action(
    "assist_live.emit_event",
    EmitEventAction,
    cv.Schema(
        {
            cv.Required(CONF_ID): cv.use_id(AssistLiveComponent),
            cv.Required("stage"): cv.enum(STAGES, lower=True),
            cv.Optional("device_ms"): cv.templatable(
                cv.int_range(min=0, max=2**64 - 1)
            ),
            cv.Optional("data", default={}): event_data,
        }
    ),
    synchronous=True,
)
async def emit_event_to_code(config, action_id, template_arg, args):
    parent = await cg.get_variable(config[CONF_ID])
    action = cg.new_Pvariable(action_id, template_arg, parent)
    cg.add(action.set_stage(config["stage"]))
    cg.add(action.set_data(config["data"]))
    device_ms = await cg.templatable(
        config.get(
            "device_ms",
            Lambda("return esphome::assist_live::AssistLiveComponent::monotonic_ms();"),
        ),
        args,
        cg.uint64,
    )
    cg.add(action.set_device_ms(device_ms))
    return action
