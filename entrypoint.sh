#!/bin/sh

set -e

configure_trusted_proxies() {
    proxies="$1"

    # BusyBox ash: avoid bare quotes inside the character class (breaks parsing).
    case "$proxies" in
        *[!0-9a-fA-F:./,\ ]*)
            echo "Invalid TRUSTED_PROXIES: '$proxies' (expected comma-separated IPv4/IPv6 addresses or CIDR subnets)" >&2
            exit 1
            ;;
    esac

    directives=$(for proxy in $(printf '%s' "$proxies" | tr ',' ' '); do
        printf '    set_real_ip_from %s;\\n' "$proxy"
    done)

    if [ -z "$directives" ]; then
        echo "Invalid TRUSTED_PROXIES: no entries found in '$proxies'" >&2
        exit 1
    fi

    # Only honor X-Forwarded-For from explicitly configured upstream proxies.
    directives="${directives}    real_ip_header X-Forwarded-For;\\n    real_ip_recursive on;"

    sed -i "s|^    # __TRUSTED_PROXIES__.*|${directives}|" \
        /etc/nginx/nginx.conf /etc/nginx/nginx.ipv6.conf

    nginx -t -c /etc/nginx/nginx.conf
    nginx -t -c /etc/nginx/nginx.ipv6.conf
}

python manage.py migrate --noinput

PUID=${PUID:-1000}
PGID=${PGID:-1000}

groupmod -o -g "$PGID" abc
usermod -o -u "$PUID" abc

if [ -n "$TRUSTED_PROXIES" ]; then
    configure_trusted_proxies "$TRUSTED_PROXIES"
fi

chown abc:abc /mediatrail
mkdir -p db/redis
chown -R abc:abc db
chown -R abc:abc staticfiles
chown -R abc:abc /var/log/nginx
chown -R abc:abc /var/lib/nginx

exec supervisord -c /etc/supervisord.conf