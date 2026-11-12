# syntax=docker/dockerfile:1
FROM node:24-bookworm-slim AS build
WORKDIR /build
COPY frontend/package.json frontend/package-lock.json ./
RUN --mount=type=secret,id=proxy_ca \
    if [ -f /run/secrets/proxy_ca ]; then export NODE_EXTRA_CA_CERTS=/run/secrets/proxy_ca; fi; \
    npm ci
COPY frontend/ ./
RUN npm run build

FROM nginxinc/nginx-unprivileged:1.28-alpine
ENV API_UPSTREAM=myquant-backend:8080 \
    NGINX_ENVSUBST_FILTER=API_UPSTREAM \
    NGINX_ENVSUBST_OUTPUT_DIR=/tmp/nginxconf
COPY --chmod=644 deploy/nginx/nginx.conf /etc/nginx/nginx.conf
COPY --chmod=755 deploy/nginx/15-runtime-directory.sh /docker-entrypoint.d/15-runtime-directory.sh
COPY --chmod=644 deploy/nginx/default.conf.template /etc/nginx/templates/default.conf.template
COPY --chown=101:101 --from=build /build/dist /usr/share/nginx/html
USER 0
RUN chmod 755 /etc/nginx/templates
USER 101:101
EXPOSE 8080
