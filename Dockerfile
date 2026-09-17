# Match server and schema tooling versions when upgrading.
FROM temporalio/server:1.31.0 AS server
FROM temporalio/admin-tools:1.31.0 AS tools
FROM temporalio/ui:2.49.1 AS ui
FROM golang:1.26.2-alpine3.23 AS demo
WORKDIR /src
COPY demo/go.mod demo/go.sum ./
RUN go mod download
COPY demo/ ./
RUN CGO_ENABLED=0 go build -trimpath -o /demo ./

FROM alpine:3.23.3
RUN apk add --no-cache ca-certificates tzdata python3 postgresql-client nginx apache2-utils tini \
    && addgroup -g 1000 temporal && adduser -D -u 1000 -G temporal temporal \
    && mkdir -p /app /run/temporal /home/ui-server/config \
    && chown -R temporal:temporal /app /run/temporal /home/ui-server
COPY --from=server /usr/local/bin/temporal-server /usr/local/bin/
COPY --from=tools /usr/local/bin/temporal /usr/local/bin/temporal-sql-tool /usr/local/bin/
COPY --from=tools /etc/temporal/schema /etc/temporal/schema
COPY --from=ui /home/ui-server/ui-server /home/ui-server/ui-server
COPY --from=demo /demo /usr/local/bin/demo-worker
COPY docker/ /app/
USER temporal
WORKDIR /app
ENV PYTHONUNBUFFERED=1
# Only the authenticated HTTP proxy is published. gRPC stays on loopback.
EXPOSE 8080
HEALTHCHECK --interval=30s --timeout=10s --start-period=180s \
    CMD python3 /app/healthcheck.py
ENTRYPOINT ["/sbin/tini", "--", "python3", "/app/start.py"]
