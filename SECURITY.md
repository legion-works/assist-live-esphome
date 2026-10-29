# Vulnerability reports

This project is experimental and has no release.
The component sends HMAC-authenticated timing events through UDP or WebSocket.
The two transports do not encrypt the events. Use an isolated network.
The WebSocket sender also receives transport control frames.

The stock Voice PE package has its own network functions.
The compile fixture is not safe to flash.

## Report a defect

Do not post credentials, recordings, or personal data in an issue.
If the repository offers private vulnerability reporting, use its Security tab to send a report.
If that service is not available, contact a maintainer in private without disclosing the defect.
No response-time guarantee applies at this step.

## Local data

Keep actual secrets in an external directory.
Keep configuration output and build logs private because they can contain configuration values.
The six values in `tests/fixtures/secrets.yaml` are fake and apply only to the compile check.
Build output contains the device HMAC key and Wi-Fi password. Do not publish C++ build output or firmware images.
