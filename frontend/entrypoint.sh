#!/bin/sh
set -eu
: "${PORT:=8080}"
: "${BACKEND_URL:?BACKEND_URL must be set}"

mkdir -p /etc/nginx/conf.d
envsubst '${PORT} ${BACKEND_URL}' < /etc/nginx/templates/default.conf.template \
    > /etc/nginx/conf.d/default.conf

# main nginx.conf with logging to stdout/stderr (cloud run pattern)
cat > /etc/nginx/nginx.conf <<'EOF'
worker_processes auto;
pid /tmp/nginx.pid;
error_log /dev/stderr warn;
events { worker_connections 1024; }
http {
    include /etc/nginx/mime.types;
    default_type application/octet-stream;
    log_format main '$remote_addr - $remote_user [$time_iso8601] "$request" '
                    '$status $body_bytes_sent "$http_referer" "$http_user_agent" rt=$request_time';
    access_log /dev/stdout main;
    sendfile on;
    tcp_nopush on;
    keepalive_timeout 75;
    server_tokens off;
    gzip on;
    gzip_types text/plain text/css text/javascript application/javascript application/json application/wasm image/svg+xml;
    client_body_temp_path /tmp/nginx_client_body;
    proxy_temp_path /tmp/nginx_proxy;
    fastcgi_temp_path /tmp/nginx_fastcgi;
    uwsgi_temp_path /tmp/nginx_uwsgi;
    scgi_temp_path /tmp/nginx_scgi;
    include /etc/nginx/conf.d/*.conf;
}
EOF

exec nginx -g 'daemon off;'
