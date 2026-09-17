"""Single-replica demo bootstrap. No credentials are written to logs."""
import base64
import binascii
import json
import os
import re
import signal
import subprocess
import sys
import time
from pathlib import Path
from urllib.parse import unquote, urlsplit

RUN = Path("/run/temporal")
CHILDREN = []


def settings(env):
    url = urlsplit(env.get("DATABASE_URL", ""))
    if url.scheme not in ("postgres", "postgresql") or not url.hostname or not url.username or not url.password:
        raise ValueError("DATABASE_URL must contain a PostgreSQL host, username, and password")
    mode = env.get("PG_SSLMODE", "verify-full")
    if mode != "verify-full" and not (mode == "disable" and env.get("LOCAL_DEVELOPMENT") == "true"):
        raise ValueError("PG_SSLMODE must be verify-full; disable is only allowed for LOCAL_DEVELOPMENT=true")
    ca_cert = env.get("PG_CA_CERT", "").strip()
    if env.get("PG_CA_CERT_BASE64"):
        try:
            ca_cert = base64.b64decode(env["PG_CA_CERT_BASE64"], validate=True).decode("ascii")
        except (ValueError, binascii.Error, UnicodeDecodeError):
            raise ValueError("PG_CA_CERT_BASE64 must be a valid base64-encoded PEM certificate") from None
    if mode == "verify-full" and not ca_cert:
        raise ValueError("Set PG_CA_CERT to the Aiven project CA certificate")
    password = env.get("UI_PASSWORD", "")
    if len(password) < 16 or any(c in password for c in "\r\n\x00"):
        raise ValueError("UI_PASSWORD must contain at least 16 characters and no line breaks")
    username = env.get("UI_USERNAME", "demo")
    if not re.fullmatch(r"[A-Za-z0-9_-]{1,64}", username):
        raise ValueError("UI_USERNAME must use letters, numbers, underscore, or hyphen")
    origin = env.get("PUBLIC_ORIGIN", "")
    parsed = urlsplit(origin)
    local = env.get("LOCAL_DEVELOPMENT") == "true"
    if (parsed.scheme not in (("https", "http") if local else ("https",))
            or not parsed.hostname or parsed.username or parsed.password
            or parsed.path not in ("", "/") or parsed.query or parsed.fragment):
        raise ValueError("PUBLIC_ORIGIN must be the HTTPS origin of the Runtime application")
    return dict(host=url.hostname, port=url.port or 5432, user=unquote(url.username),
                password=unquote(url.password), database=unquote(url.path.lstrip("/")) or "defaultdb",
                tls=mode == "verify-full", username=username, ui_password=password,
                origin=origin.rstrip("/"), local=local, ca_cert=ca_cert)


def server_config(s):
    def store(database, connections):
        host = f'[{s["host"]}]' if ":" in s["host"] else s["host"]
        return {"sql": {"pluginName": "postgres12", "databaseName": database,
                "connectAddr": f'{host}:{s["port"]}', "connectProtocol": "tcp",
                "user": s["user"], "password": s["password"],
                "maxConns": connections, "maxIdleConns": connections, "maxConnLifetime": "1h",
                "tls": {"enabled": s["tls"], "enableHostVerification": True,
                        "serverName": s["host"], "caFile": str(RUN / "ca.pem") if s["tls"] else ""}}}
    return {
        "log": {"stdout": True, "level": "info"},
        "persistence": {"numHistoryShards": 4, "defaultStore": "default", "visibilityStore": "visibility",
                        "datastores": {"default": store("temporal", 5), "visibility": store("temporal_visibility", 2)}},
        "global": {"membership": {"maxJoinDuration": "30s", "broadcastAddress": "127.0.0.1"}},
        "services": {name: {"rpc": {"grpcPort": port, "membershipPort": port - 300, "bindOnIP": "127.0.0.1"}}
                     for name, port in (("frontend", 7233), ("history", 7234), ("matching", 7235), ("worker", 7239))},
        "clusterMetadata": {"enableGlobalNamespace": False, "failoverVersionIncrement": 10,
                            "masterClusterName": "active", "currentClusterName": "active",
                            "clusterInformation": {"active": {"enabled": True, "initialFailoverVersion": 1,
                                                              "rpcName": "frontend", "rpcAddress": "127.0.0.1:7233"}}},
        "dcRedirectionPolicy": {"policy": "noop"},
        "archival": {"history": {"state": "disabled"}, "visibility": {"state": "disabled"}},
        "dynamicConfigClient": {"filepath": str(RUN / "dynamic.yaml"), "pollInterval": "60s"},
    }


def write(path, value):
    Path(path).write_text(value)
    Path(path).chmod(0o600)


def prepare(s):
    RUN.mkdir(parents=True, exist_ok=True)
    if s["tls"]:
        write(RUN / "ca.pem", s["ca_cert"])
    # JSON is valid YAML and safely escapes quotes and special characters in secrets.
    write(RUN / "server.yaml", json.dumps(server_config(s)))
    write(RUN / "dynamic.yaml", "{}\n")
    write("/home/ui-server/config/docker.yaml", json.dumps({
        "temporalGrpcAddress": "127.0.0.1:7233", "host": "127.0.0.1", "port": 8081,
        "enableUi": True, "defaultNamespace": "default",
        "cors": {"allowOrigins": [s["origin"]], "cookieInsecure": s["local"]},
    }))
    # Password comes through stdin, never the process command line.
    hashed = subprocess.run(["htpasswd", "-niB", s["username"]],
                            input=s["ui_password"] + "\n", text=True, capture_output=True, check=True).stdout
    write(RUN / "htpasswd", hashed)


def database_env(s, database):
    return dict(os.environ, PGHOST=s["host"], PGPORT=str(s["port"]), PGUSER=s["user"],
                PGPASSWORD=s["password"], PGDATABASE=database, PGCONNECT_TIMEOUT="10",
                PGSSLMODE="verify-full" if s["tls"] else "disable", PGSSLROOTCERT=str(RUN / "ca.pem"),
                SQL_HOST=s["host"], SQL_PORT=str(s["port"]), SQL_USER=s["user"],
                SQL_PASSWORD=s["password"], SQL_DATABASE=database, SQL_PLUGIN="postgres12",
                SQL_TLS=str(s["tls"]).lower(), SQL_TLS_SERVER_NAME=s["host"],
                SQL_TLS_CA_FILE=str(RUN / "ca.pem") if s["tls"] else "",
                SQL_TLS_DISABLE_HOST_VERIFICATION="false")


def query(env, sql):
    return subprocess.check_output(["psql", "-XAt", "-v", "ON_ERROR_STOP=1", "-c", sql],
                                   env=env, text=True, stderr=subprocess.DEVNULL).strip()


def migrate(s):
    env = database_env(s, s["database"])
    for attempt in range(60):
        try:
            query(env, "SELECT 1")
            break
        except subprocess.CalledProcessError:
            if attempt == 59:
                raise RuntimeError("PostgreSQL connection failed; check host, credentials, CA and network access")
            time.sleep(2)
    for database, schema in (("temporal", "temporal"), ("temporal_visibility", "visibility")):
        # Database names are fixed, never interpolated from user input.
        if query(env, f"SELECT 1 FROM pg_database WHERE datname = '{database}'") != "1":
            query(env, f'CREATE DATABASE "{database}"')
        db_env = database_env(s, database)
        if not query(db_env, "SELECT to_regclass('public.schema_version')"):
            subprocess.run(["temporal-sql-tool", "setup-schema", "-v", "0.0"], env=db_env, check=True)
        subprocess.run(["temporal-sql-tool", "update-schema", "-d",
                        f"/etc/temporal/schema/postgresql/v12/{schema}/versioned"], env=db_env, check=True)


def spawn(args, **kwargs):
    process = subprocess.Popen(args, **kwargs)
    CHILDREN.append(process)
    return process


def stop(*_):
    for child in reversed(CHILDREN):
        if child.poll() is None:
            child.terminate()
    deadline = time.monotonic() + 30
    for child in CHILDREN:
        try:
            child.wait(timeout=max(0.1, deadline - time.monotonic()))
        except subprocess.TimeoutExpired:
            child.kill()


def main():
    os.umask(0o077)
    s = settings(os.environ)
    prepare(s)
    migrate(s)
    env = dict(os.environ, TEMPORAL_SERVER_CONFIG_FILE_PATH=str(RUN / "server.yaml"))
    server = spawn(["temporal-server", "start"], env=env)
    for attempt in range(90):
        if server.poll() is not None:
            raise RuntimeError("Temporal Server exited during startup")
        check = subprocess.run(["temporal", "operator", "cluster", "health", "--address", "127.0.0.1:7233"],
                               stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL, timeout=10)
        if check.returncode == 0:
            break
        time.sleep(2)
    else:
        raise RuntimeError("Temporal Server did not become healthy")
    spawn(["/home/ui-server/ui-server", "--env", "docker", "start"], cwd="/home/ui-server")
    spawn(["demo-worker"])
    spawn(["nginx", "-c", "/app/nginx.conf", "-g", "daemon off;"])
    print("Temporal demo running; only authenticated Web UI port 8080 is exposed", flush=True)
    while True:
        for child in CHILDREN:
            if child.poll() is not None:
                raise RuntimeError("A required demo process exited; stopping container")
        time.sleep(1)


if __name__ == "__main__":
    def shutdown(*_):
        raise SystemExit(0)
    signal.signal(signal.SIGTERM, shutdown)
    signal.signal(signal.SIGINT, shutdown)
    try:
        main()
    except (ValueError, RuntimeError) as error:
        print(f"Startup failed: {error}", file=sys.stderr)
        sys.exit(1)
    except Exception:
        print("Startup failed; inspect component logs and configuration", file=sys.stderr)
        sys.exit(1)
    finally:
        stop()
