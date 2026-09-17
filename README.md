# Temporal demo starter for Aiven Runtime

Self-hosted Temporal Server **1.31.0**, Temporal Web UI **2.49.1**, and a Go example worker, with durable storage in **Aiven for PostgreSQL**. This is a single-replica demo starter, not a production cluster.

## Design

```text
Browser --HTTPS--> Aiven Runtime ingress --> :8080 nginx (Basic authentication)
                                             |
                                  127.0.0.1:8081 Web UI
                                             |
                                  127.0.0.1:7233 Temporal Server
                                             |        ^
                                             |        | example worker
                                             v
                                   Aiven PostgreSQL (verified TLS)
                                   temporal + temporal_visibility
```

Server, UI, proxy, and worker share one container. Runtime does not currently support service integrations between Runtime applications, so the demo uses localhost connections. Only HTTP port **8080** is exposed; gRPC and Temporal's internal ports stay on loopback. External SDK clients cannot connect to this starter. Add your own workers to the image, or redesign networking and authentication before supporting external clients.

The UI requires a username and password. Runtime terminates HTTPS; nginx checks the password before forwarding requests to the UI. PostgreSQL certificate and hostname verification are mandatory except in the explicit local development mode. Credentials and generated configuration stay out of Git.

## Run locally

Requires a running Docker-compatible engine and Docker Compose v2.

1. Copy `.env.example` to `.env` and set `UI_PASSWORD` to a unique password of at least 16 characters.
2. Run `docker compose up --build -d`.
3. Open <http://localhost:8080> and sign in as `demo` with your password.
4. Select namespace `default`. Open workflow `aiven-starter-demo`.

The first activity attempt deliberately fails. Temporal retries it after two seconds and the workflow returns a greeting. This demonstrates durable execution rather than just an empty UI. Each container restart can start another run of this workflow ID; an already-running execution is reused.

Start another workflow from the Web UI using workflow type `GreetingWorkflow`, task queue `aiven-demo`, and one JSON string input such as `"Cara"`.

`docker compose down` preserves PostgreSQL data. `docker compose down -v` **permanently deletes the local demo data**.

## Deploy on Aiven Runtime

Use **`compose.aiven.yaml`**, not the local `compose.yaml`.

1. Review, commit and push this repository yourself. Runtime's documented deployment flow builds from a GitHub branch; uncommitted or staged local changes are not available to it.
2. In the target project, choose **Runtime > Deploy application**, select the repository and branch, then scan **compose.aiven.yaml**.
3. Review the detected application and PostgreSQL integration. Choose a PostgreSQL version supported by Temporal (16 is the local reference). Runtime does not necessarily honor the database image tag. Start with a single Runtime replica and enough memory for Server, UI and worker (2 GiB is a starting estimate, not a tested minimum).
4. Prefer an internal/free plan when available. Check the displayed hourly/monthly cost before creating either resource. The template does not select or hard-code plans, regions, or account identifiers.
5. Use a **dedicated PostgreSQL service** for this demo. The startup account must be able to connect, create databases, and own the Temporal schema. Map its connection URI to `DATABASE_URL`. The URI's database (usually `defaultdb`) is used for bootstrap; the application creates `temporal` and `temporal_visibility`.
6. Set the variables below. Store passwords, the connection URI, and the CA certificate in Runtime's secret/variable configuration, never in this repository. If Runtime initially creates the app before its hostname is known, allow that first startup to fail closed, then set `PUBLIC_ORIGIN` and redeploy.
7. Expose **only port 8080**. Use the generated HTTPS URL as `PUBLIC_ORIGIN`, then deploy/redeploy. Expect database schema initialization on the first startup.

| Variable | Value |
| --- | --- |
| `DATABASE_URL` | Aiven PostgreSQL URI with URL-encoded credentials and actual service port |
| `PG_CA_CERT_BASE64` | Base64-encoded Aiven project CA certificate, on one line; use this for Runtime because its API rejects multiline values |
| `PG_CA_CERT` | Alternative: raw PEM certificate, only where multiline environment values are supported |
| `PG_SSLMODE` | `verify-full` (default); URI query parameters do not override this setting |
| `UI_USERNAME` | `demo` by default |
| `UI_PASSWORD` | Unique password of at least 16 characters |
| `PUBLIC_ORIGIN` | Exact public HTTPS origin, e.g. `https://your-app-hostname` |

Startup validates configuration, waits for PostgreSQL, creates missing databases, initializes missing schemas and applies the pinned version's migrations. Existing schemas are updated, never dropped. It then starts Temporal, waits for gRPC health, starts the worker and UI, and exposes the authenticated proxy. A required process exiting stops the whole container. SIGTERM is forwarded and children get up to 30 seconds to stop.

Encode a downloaded `ca.pem` without line breaks using `openssl base64 -A -in ca.pem`. Base64 is a transport encoding, not encryption; decoding restores the certificate used for full TLS verification.

**Run exactly one replica and avoid overlapping deployments during schema setup.** This starter does not coordinate migrations across replicas. Before upgrading, back up PostgreSQL and follow Temporal's supported upgrade sequence; keep the Server and admin-tools pins identical. Do not downgrade a migrated database.

## Verify a deployment

- An unauthenticated request to the public URL must return HTTP **401**.
- Sign in and confirm the `default` namespace and `aiven-starter-demo` execution are visible.
- Confirm the workflow completes after its intentional activity retry and inspect its greeting result.
- Restart/redeploy the application. Confirm previous execution history is still present in PostgreSQL.
- Confirm only port 8080 is exposed. Do not publish 7233, 8081, or internal membership ports.
- Check logs for schema, namespace, worker, and process failures. The first deliberate activity failure is expected.

Local container health checks validate Temporal gRPC and the UI. Runtime's OCI builder ignores Dockerfile HEALTHCHECK; check deployment status and the authenticated endpoint instead. See [VALIDATION.md](VALIDATION.md) for the actual tests and their limits.

The root Dockerfile can also be deployed through Aiven MCP/API, with a managed PostgreSQL integration mapping its connection string to `DATABASE_URL` and the variables above. This is the deployment path used for the recorded live validation; Console scanning of the Compose manifest has not yet been tested.

## Developer checks

```sh
python3 -m unittest discover -s tests -v
cd demo
go test ./...
go build ./...
```

The unit checks cover credential escaping, TLS requirements, loopback binding, and the example's retry behavior. They do not replace a real container build and Aiven deployment test.

## Scope and limitations

- No high availability, autoscaling, external worker endpoint, SSO, or production access model.
- One shared demo UI login; everyone with it can operate workflows. Use synthetic demo data only.
- PostgreSQL is the durable store for history and visibility. No Elasticsearch or local application volume is required.
- Schema initialization uses an elevated database account for convenience. Production should separate migration and runtime roles.
- Four history shards are fixed in this template. Do not change this for an existing database.
- Authentication and Runtime plan selection must be configured before the demo can be considered deployed.

## References

- [Aiven Runtime Compose files](https://aiven.io/docs/products/runtime/manifest-files/compose-files)
- [Aiven Runtime deployment](https://aiven.io/docs/products/runtime/deploy-apps)
- [Aiven Runtime service integrations and migrations](https://aiven.io/docs/products/runtime/connect-services-to-apps)
- [Temporal self-hosted deployment](https://docs.temporal.io/self-hosted-guide/deployment)
- [Temporal official Compose examples](https://github.com/temporalio/samples-server/tree/main/compose)
