# SPDX-License-Identifier: GPL-3.0-or-later
import argparse
import ipaddress
import re
import subprocess
import sys
from pathlib import Path
from urllib.parse import urlsplit

import yaml

ROOT = Path(__file__).resolve().parents[1]
DOCUMENTS = (
    "README.md",
    "ARCHITECTURE.md",
    "STRUCTURE.md",
    "CHANGELOG.md",
    "AGENTS.md",
    "CODE_OF_CONDUCT.md",
    "CONTRIBUTING.md",
    "SECURITY.md",
    "THIRD_PARTY_NOTICES.md",
)
STOCK_REF = "2644f4c794271d735d182ca7ebf899ed46164f4e"
STOCK_URL = "https://github.com/esphome/home-assistant-voice-pe"
STOCK_PACKAGE = {
    "voice_pe": {
        "url": STOCK_URL,
        "ref": STOCK_REF,
        "files": ["home-assistant-voice.yaml"],
        "refresh": "never",
    }
}
STOCK_COMPONENT = {
    "source": {"type": "git", "url": STOCK_URL, "ref": STOCK_REF},
    "components": ["voice_kit"],
    "refresh": "never",
}
FAKE_SECRETS = {
    "wifi_ssid": "test-network",
    "wifi_password": "test-password-not-valid",
    "assist_live_device_token": "test-device-token-not-valid",
    "assist_live_server": "assist-live-server.invalid",
    "assist_live_device": "satellite-compile-test",
    "assist_live_hmac_key": "000102030405060708090a0b0c0d0e0f" * 2,
}
ARTIFACT_SUFFIXES = {".bin", ".elf", ".map", ".o", ".a", ".so", ".pyc", ".uf2"}


def require(condition, label):
    if not condition:
        raise ValueError(label)


class TemplateLoader(yaml.SafeLoader):
    pass


def secret_reference(loader, node):
    name = loader.construct_scalar(node)
    require(name in FAKE_SECRETS, "unknown compile secret")
    return ("!secret", name)


TemplateLoader.add_constructor("!secret", secret_reference)


def lambda_reference(loader, node):
    return loader.construct_scalar(node)


TemplateLoader.add_constructor("!lambda", lambda_reference)


def check_secret_names(values):
    require(set(values) == set(FAKE_SECRETS), "exact fixture secret names")
    require(values == FAKE_SECRETS, "exact fake fixture secret values")


def check_preserved(stock, current):
    if isinstance(stock, dict):
        require(isinstance(current, dict), "stock mapping removed")
        for key, value in stock.items():
            require(key in current, "stock field removed")
            check_preserved(value, current[key])
    elif isinstance(stock, list):
        require(
            isinstance(current, list) and len(current) >= len(stock),
            "stock list removed",
        )
        for before, after in zip(stock, current, strict=False):
            check_preserved(before, after)
    else:
        require(stock == current, "stock value changed")


def compare_example(fixture, example):
    expected = {**fixture}
    if "substitutions" in fixture:
        require(
            "assist_live_device_token" not in fixture["substitutions"]
            and "assist_live_device_token" not in example["substitutions"],
            "production example must not require a probe token",
        )
        expected["substitutions"] = {
            **fixture["substitutions"],
            "test_device": "assist-live-example",
        }
        expected["external_components"] = [
            STOCK_COMPONENT,
            {
                "source": {"type": "local", "path": "../components"},
                "components": ["assist_live"],
            },
        ]
        expected["assist_live"] = {
            **fixture["assist_live"],
            "transport": example["assist_live"]["transport"],
        }
        require(
            example["assist_live"]["transport"] in {"udp", "websocket"},
            "example transport",
        )
    require(expected == example, "example has an undocumented difference")


def load_checked(path):
    try:
        return yaml.load(path.read_text(), Loader=TemplateLoader)
    except (OSError, yaml.YAMLError, AttributeError, ValueError):
        raise ValueError(f"unreadable YAML: {path.relative_to(ROOT)}") from None


def check_pins(value, label):
    if isinstance(value, dict):
        for key, item in value.items():
            if key == "ref":
                require(item == STOCK_REF, f"{label}: pinned ref")
            check_pins(item, label)
    elif isinstance(value, (list, tuple)):
        for item in value:
            check_pins(item, label)
    elif isinstance(value, str):
        for match in re.finditer(r"https?://[^\s]+", value, flags=re.IGNORECASE):
            url = urlsplit(match.group())
            parts = url.path.strip("/").split("/")
            if url.hostname == "raw.githubusercontent.com":
                require(
                    len(parts) >= 4 and parts[2] == STOCK_REF,
                    f"{label}: pinned raw GitHub URL",
                )
            elif url.hostname == "github.com" and len(parts) > 2 and parts[2] == "raw":
                require(
                    len(parts) >= 5 and parts[3] == STOCK_REF,
                    f"{label}: pinned raw GitHub URL",
                )


def check_template(name, local_path, test_device):
    template = load_checked(ROOT / name)
    require(isinstance(template, dict), f"{name}: YAML mapping")
    require(
        set(template)
        == {
            "substitutions",
            "packages",
            "esphome",
            "wifi",
            "external_components",
            "assist_live",
            "micro_wake_word",
            "voice_assistant",
        },
        f"{name}: must not redefine stock voice, wake words, timers, or media player",
    )
    check_pins(template, name)
    require(
        template["packages"] == STOCK_PACKAGE, f"{name}: stock Voice PE package pin"
    )
    require(
        template["micro_wake_word"]
        == {
            "on_wake_word_detected": [
                {
                    "assist_live.emit_event": {
                        "id": "assist_live_component",
                        "stage": "wake_detected",
                    }
                }
            ]
        },
        f"{name}: append only the wake event",
    )
    require(
        template["voice_assistant"]
        == {
            "on_start": [
                {"lambda": "id(assist_live_component).command_stream_start();"}
            ],
            "on_end": [{"lambda": "id(assist_live_component).command_stream_end();"}],
        },
        f"{name}: append only the command callbacks",
    )
    require(
        set(template["assist_live"])
        == {"id", "device", "hmac_key", "server", "transport", "media_player_id"},
        f"{name}: exact telemetry fields",
    )
    for field_name, secret in (
        ("device", "assist_live_device"),
        ("hmac_key", "assist_live_hmac_key"),
        ("server", "assist_live_server"),
    ):
        require(
            template["assist_live"][field_name] == ("!secret", secret),
            f"{name}: external {field_name}",
        )
    require(
        template["assist_live"]["media_player_id"] == "external_media_player",
        f"{name}: stock media player",
    )
    require(
        template["assist_live"]["transport"] in {"udp", "websocket"},
        f"{name}: explicit transport",
    )
    require(
        template["external_components"]
        == [
            STOCK_COMPONENT,
            {
                "source": {"type": "local", "path": local_path},
                "components": ["assist_live"],
            },
        ],
        f"{name}: component sources",
    )
    require(
        template["esphome"] == {"name": "${test_device}"},
        f"{name}: test device substitution",
    )
    require(
        isinstance(template["substitutions"], dict)
        and template["substitutions"].get("test_device") == test_device,
        f"{name}: test device value",
    )
    return template


def git_output(*args):
    return subprocess.check_output(["git", *args], cwd=ROOT).decode().strip()


def check_privacy(paths, denylist):
    terms = []
    if denylist is not None:
        terms = [
            line.strip().casefold()
            for line in denylist.read_text().splitlines()
            if line.strip() and not line.lstrip().startswith("#")
        ]
    for name in paths:
        text = (ROOT / name).read_text()
        require("/" + "home/" not in text, "privacy: local home path")
        require(
            not any(term in text.casefold() for term in terms),
            "privacy: private denylist match",
        )
        for candidate in re.findall(r"\b(?:\d{1,3}\.){3}\d{1,3}\b", text):
            try:
                address = int(ipaddress.IPv4Address(candidate))
            except ipaddress.AddressValueError:
                continue
            private = (
                address >> 24 == 10 or address >> 20 == 0xAC1 or address >> 16 == 0xC0A8
            )
            require(not private, "privacy: private IPv4 address")


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--denylist", type=Path)
    args = parser.parse_args()
    require(Path(git_output("rev-parse", "--show-toplevel")) == ROOT, "own Git root")
    for name in DOCUMENTS:
        require((ROOT / name).is_file(), f"root document: {name}")
    license_text = (ROOT / "LICENSE").read_text()
    require(
        "GNU GENERAL PUBLIC LICENSE" in license_text
        and "Version 3, 29 June 2007" in license_text
        and "END OF TERMS AND CONDITIONS" in license_text,
        "full GPL version 3 license",
    )
    for name in ("__init__.py", "assist_live.h", "assist_live.cpp"):
        source = (ROOT / "components/assist_live" / name).read_text()
        require("SPDX-License-Identifier: GPL-3.0-or-later" in source, f"SPDX: {name}")
    header = (ROOT / "components/assist_live/assist_live.h").read_text()
    require("class AssistLiveComponent : public Component" in header, "component class")
    require("namespace assist_live" in header, "component namespace")
    check_secret_names(load_checked(ROOT / "tests/fixtures/secrets.yaml"))
    fixture = check_template(
        "tests/fixtures/voice-pe.yaml", "../../components", "assist-live-compile-test"
    )
    example = check_template(
        "examples/voice-pe.yaml", "../components", "assist-live-example"
    )
    compare_example(fixture, example)
    tracked = git_output("ls-files", "-z").split("\0")
    require(
        not any(
            Path(name).suffix in ARTIFACT_SUFFIXES
            or ".esphome" in Path(name).parts
            or ".venv" in Path(name).parts
            for name in tracked
        ),
        "no tracked compiled artifact",
    )
    published = set(
        git_output("ls-files", "-co", "--exclude-standard", "-z").split("\0")
    )
    published.discard("")
    published.difference_update(git_output("ls-files", "--deleted", "-z").split("\0"))
    require("tests/fixtures/secrets.yaml" in published, "fake secrets are not ignored")
    check_privacy(published, args.denylist)
    print("PASS firmware bootstrap")


if __name__ == "__main__":
    try:
        main()
    except (OSError, ValueError, subprocess.CalledProcessError) as error:
        print(f"FAIL firmware bootstrap: {error}")
        sys.exit(1)
