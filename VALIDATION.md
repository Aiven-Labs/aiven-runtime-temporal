# Validation status — 2026-09-17

Passed locally:

- Six Python configuration tests: credential decoding/escaping, verified TLS enforcement, CA requirement, UI password requirement, HTTPS origin requirement, and explicit local mode.
- Go SDK workflow test: the intentionally failed first activity attempt retries and returns the expected greeting.
- Go worker compilation using Go 1.26.2 on macOS arm64.

Not yet validated:

- Full container image build and startup (no container engine was available on this machine).
- Live Aiven PostgreSQL schema initialization, TLS connection, and Runtime deployment.
- Public HTTPS/UI authentication, workflow completion on Runtime, and persistence after restart.

The Runtime smoke test must use a reviewed commit pushed to GitHub. No commit or push was made by the assistant. Treat this as a draft until the deployment checks in README.md have passed.
