# nginx that runs as a non-root user (so it listens on 8080 instead of 80)
FROM nginxinc/nginx-unprivileged:1.27-alpine

# The base image ships an OpenSSL with a known critical vulnerability (found by the Trivy scan in CI).
# Upgrade just those libraries to the patched release, then drop back to the unprivileged user.
USER root
RUN apk upgrade --no-cache libcrypto3 libssl3
USER 101

COPY nginx.conf /etc/nginx/conf.d/default.conf

# Only the website itself goes into the web root (never the Dockerfile or nginx.conf)
COPY *.html /usr/share/nginx/html/
COPY css/ /usr/share/nginx/html/css/
COPY js/ /usr/share/nginx/html/js/

EXPOSE 8080
