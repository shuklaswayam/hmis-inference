#!/usr/bin/env bash
# One-shot production deploy helper for HMIS Inference.
#
# Usage (run on the production host, NOT locally):
#
#   sudo DEPLOY_DOMAIN=api.your-domain.com \
#        DEPLOY_LE_EMAIL=ops@your-domain.com \
#        DEPLOY_API_KEY="$(openssl rand -hex 32)" \
#        ./deploy.sh
#
# What it does:
#   1. Installs nginx + certbot if missing (apt / dnf aware).
#   2. Writes an nginx vhost for $DEPLOY_DOMAIN with TLS termination,
#      long timeouts for Groq synthesis, and explicit WebSocket passthrough
#      on /ws/. The HTTP > HTTPS redirect is in place from day one.
#   3. Runs certbot --nginx to fetch the first Let's Encrypt cert.
#   4. Adds a certbot auto-renew cron (idempotent).
#   5. Reloads nginx and prints a smoke-test reminder.

set -euo pipefail

: "${DEPLOY_DOMAIN:?Set DEPLOY_DOMAIN (e.g. api.your-domain.com)}"
: "${DEPLOY_API_KEY:?Set DEPLOY_API_KEY to the secret in your backend .env}"
: "${DEPLOY_LE_EMAIL:?Set DEPLOY_LE_EMAIL (Let's Encrypt registration email)}"

NGINX_CONF_SRC="$(cd "$(dirname "$0")" && pwd)/deploy/nginx.conf"
if [ ! -f "$NGINX_CONF_SRC" ]; then
  echo "ERROR: $NGINX_CONF_SRC not found. Are you running this from the repo root?"
  exit 1
fi

echo "==> Installing nginx and certbot (if absent)"
if command -v apt-get >/dev/null 2>&1; then
  apt-get update -qq
  apt-get install -y nginx certbot python3-certbot-nginx
elif command -v dnf >/dev/null 2>&1; then
  dnf install -y nginx certbot python3-certbot-nginx
elif command -v yum >/dev/null 2>&1; then
  yum install -y nginx certbot python3-certbot-nginx
else
  echo "ERROR: neither apt-get nor dnf/yum found. Install nginx + certbot manually."
  exit 1
fi

echo "==> Writing nginx vhost for $DEPLOY_DOMAIN"
install -m 0644 "$NGINX_CONF_SRC" "/etc/nginx/sites-available/$DEPLOY_DOMAIN"
sed -i "s/__DOMAIN__/$DEPLOY_DOMAIN/g" "/etc/nginx/sites-available/$DEPLOY_DOMAIN"

ln -sf "/etc/nginx/sites-available/$DEPLOY_DOMAIN" /etc/nginx/sites-enabled/
# Drop the default site if present (don't clobber if it's a symlink to ours).
if [ -f /etc/nginx/sites-enabled/default ] && \
   [ ! -L /etc/nginx/sites-enabled/default ]; then
  rm -f /etc/nginx/sites-enabled/default
fi

nginx -t

echo "==> Fetching Let's Encrypt cert for $DEPLOY_DOMAIN"
certbot --nginx \
  --non-interactive --agree-tos -m "$DEPLOY_LE_EMAIL" \
  -d "$DEPLOY_DOMAIN" || {
  echo "!! certbot failed. Check that TCP/80 is reachable from the internet"
  echo "   and that DNS for $DEPLOY_DOMAIN resolves to this host."
  exit 1
}

echo "==> Adding certbot auto-renew cron (idempotent)"
CRON_LINE='0 3 * * * certbot renew --quiet --deploy-hook "nginx -s reload"'
( crontab -l 2>/dev/null | grep -q 'certbot renew' ) \
  || ( crontab -l 2>/dev/null; echo "$CRON_LINE" ) | crontab -

systemctl reload nginx

echo ""
echo "============================================================"
echo "  done.  smoke-test:"
echo "    curl -fsSL https://$DEPLOY_DOMAIN/health"
echo "    curl -fsSL -H \"X-API-Key: \$DEPLOY_API_KEY\" \\"
echo "         https://$DEPLOY_DOMAIN/api/v1/alerts/"
echo ""
echo "  the SPA build must also be redeployed with:"
echo "    VITE_API_BASE_URL=https://$DEPLOY_DOMAIN \\"
echo "    VITE_API_KEY=$DEPLOY_API_KEY \\"
echo "      ./frontend/dist    # or rebuild: npm run build"
echo "============================================================"
