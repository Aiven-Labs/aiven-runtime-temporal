# Validation status — 2026-09-17

Validated deployment: commit `ea2ec1639998e3ece434e1376544541c55c6489d`, using the root Dockerfile through the Aiven API/MCP workflow, in AWS Dublin.

Passed locally:

- Eight Python configuration tests: credential decoding/escaping, verified TLS enforcement, CA requirement, valid/invalid base64 CA input, UI password requirement, HTTPS origin requirement, and explicit local mode.
- Go SDK workflow test: the intentionally failed first activity attempt retries and returns the expected greeting.
- Go worker compilation using Go 1.26.2 on macOS arm64.

Passed on Aiven Runtime:

- Full container image build and startup; Runtime reports build SUCCESS, deployment COMPLETED, and service RUNNING.
- PostgreSQL 16 on startup-4 with the managed DATABASE_URL integration, base64-encoded project CA, and full TLS verification.
- Runtime startup-100-2048 (2 GiB), with only HTTP port 8080 exposed.
- Public HTTPS returns 401 without credentials and 200 with the demo login.
- The authenticated workflow API reports the example workflow COMPLETED after its intentional first activity failure.
- The workflow result is: `Hello, Aiven! Temporal recovered from a failed activity on Aiven Runtime.`
- After powering the application off and back on, the original run's history and result remain readable. The restarted worker completes another run.
- The previous attempt's PostgreSQL service was deleted and an empty project verified before this clean deployment.

Platform observations:

- Runtime rejects environment values with literal newlines. Set PG_CA_CERT_BASE64 to a single-line base64 value; the application decodes it without weakening TLS verification.
- Runtime's OCI builder ignores Dockerfile HEALTHCHECK. The supervisor, live endpoint checks, and platform status were used for validation.
- Source changes must be reviewed and pushed before Runtime can build them. All commits/pushes were performed by the user.

Not covered: Console Compose scanning, a local Docker Compose run, production sizing, HA, external workers, and production authentication. The deployed Dockerfile and managed PostgreSQL integration are validated; this remains a single-replica demo starter.
