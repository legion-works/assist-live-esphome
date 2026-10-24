# Architecture

## Component boundary

ESPHome loads `components/assist_live/__init__.py` as an external component.
The schema accepts an identifier and the standard component options.
`to_code(config)` makes `assist_live::AssistLiveComponent` and calls `register_component`.

The C++ class extends `Component`. Its `setup()` is empty.
Its `dump_config()` prints a placeholder message.
The component has no network connection, timers, loop function, or voice hooks.

## Stock package

The example and compile fixture import the official Voice PE package by commit.
They add Wi-Fi secrets, a device name, and the local component.
They pin the stock `voice_kit` source and sound URLs without changes to the stock functions.
They do not redefine `voice_assistant`, `micro_wake_word`, timers, or `media_player`.

The token and server secrets flow only into substitutions with no consumer.
No component code reads those values.

## Source-only boundary

Build files stay in ignored directories. The repository contains no firmware image.
The compile fixture is not a configuration for a device in use.
See [the verification record](docs/verification.md) for dependency limits and test results.
