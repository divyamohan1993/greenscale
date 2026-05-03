FROM nginx:1.27-alpine

RUN apk add --no-cache gettext

COPY public/ /usr/share/nginx/html/
COPY nginx.conf.template /etc/nginx/templates/default.conf.template
COPY entrypoint.sh /entrypoint.sh
RUN chmod +x /entrypoint.sh

ENV BACKEND_URL="http://localhost:8080" \
    PORT=8080
EXPOSE 8080
CMD ["/entrypoint.sh"]
