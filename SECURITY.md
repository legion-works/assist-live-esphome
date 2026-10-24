# Vulnerability reports

This project is experimental and has no release.
The placeholder component does not send or receive network data.
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
The four values in `tests/fixtures/secrets.yaml` are fake and apply only to the compile check.
