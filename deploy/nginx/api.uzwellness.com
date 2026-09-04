# Source-controlled mirror of /etc/nginx/sites-available/api.uzwellness.com
# on the VPS. Keep this in sync by hand when the live file changes (Certbot
# will keep rewriting the "managed by Certbot" lines on renewal — leave
# those alone and just update the rest here to match).
#
# proxy_set_header X-Real-IP $remote_addr; below is security-load-bearing,
# not style: the app listens on a unix socket, so request.client is always
# None — X-Real-IP is the only signal it has for the guest's address
# (see app/core/rate_limit.py). Drop it and every guest shares one
# rate-limit bucket.

server {
    server_name api.uzwellness.com;

    client_max_body_size 100M;

    location / {
        proxy_pass http://unix:/run/uzwellness/uvicorn.sock;

        proxy_http_version 1.1;

        proxy_set_header Host $host;
        proxy_set_header X-Real-IP $remote_addr;
        proxy_set_header X-Forwarded-For $proxy_add_x_forwarded_for;
        proxy_set_header X-Forwarded-Proto $scheme;

        proxy_redirect off;
    }

    listen 443 ssl;
    ssl_certificate /etc/letsencrypt/live/api.uzwellness.com/fullchain.pem;
    ssl_certificate_key /etc/letsencrypt/live/api.uzwellness.com/privkey.pem;
    include /etc/letsencrypt/options-ssl-nginx.conf;
    ssl_dhparam /etc/letsencrypt/ssl-dhparams.pem;

}
server {
    if ($host = api.uzwellness.com) {
        return 301 https://$host$request_uri;
    }


    listen 80;
    server_name api.uzwellness.com;
    return 404;


}
