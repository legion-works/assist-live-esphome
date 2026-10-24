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
        },
        f"{name}: must not redefine stock voice, wake words, timers, or media player",
    )
    check_pins(template, name)
    require(
        template["packages"] == STOCK_PACKAGE, f"{name}: stock Voice PE package pin"
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
    require(
        load_checked(ROOT / "tests/fixtures/secrets.yaml") == FAKE_SECRETS,
        "exactly four fake fixture secrets",
    )
    fixture = check_template(
        "tests/fixtures/voice-pe.yaml", "../../components", "assist-live-compile-test"
    )
    example = check_template(
        "examples/voice-pe.yaml", "../components", "assist-live-example"
    )
    expected_example = {
        **fixture,
        "substitutions": {
            **fixture["substitutions"],
            "test_device": "assist-live-example",
        },
        "external_components": example["external_components"],
    }
    require(
        example == expected_example,
        "examples/voice-pe.yaml: only device name and local path differ from fixture",
    )
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
    require("tests/fixtures/secrets.yaml" in published, "fake secrets are not ignored")
    check_privacy(published, args.denylist)
    print("PASS firmware bootstrap")


if __name__ == "__main__":
    try:
        main()
    except (OSError, ValueError, subprocess.CalledProcessError) as error:
        print(f"FAIL firmware bootstrap: {error}", file=sys.stderr)
        sys.exit(1)
