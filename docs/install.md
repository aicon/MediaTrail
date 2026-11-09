# Install

[Magyar változat](hu/install.md)

MediaTrail runs as one container. The web server, the application, the background worker, and Redis are all inside that image. You do not add a separate Redis service.

Pull `ghcr.io/aicon/mediatrail:latest`. The package is private, so the machine that pulls it needs a login that can read `ghcr.io/aicon/mediatrail`.

## Compose

Save this as `docker-compose.yml` next to an empty `db` directory:

```yaml
services:
  mediatrail:
    image: ghcr.io/aicon/mediatrail:latest
    container_name: mediatrail
    restart: unless-stopped
    ports:
      - "8000:8000"
    environment:
      TZ: Europe/Budapest
      SECRET: replace-with-a-long-random-string
    volumes:
      - ./db:/mediatrail/db
```

`SECRET` signs sessions and encrypted values. Replace it before anyone else can reach the site, and do not change it later unless you intend to sign everyone out. `TZ` is the clock used when a stored instant is shown on the page.

The `db` folder on the host holds the SQLite database and Redis persistence. Inside the container that folder is `/mediatrail/db`. Leave the mount as it is.

Start it:

```bash
docker compose up -d
```

Open `http://localhost:8000` and create an account. Registration is open unless you turn it off. See [Accounts](accounts.md).

On the first seconds of a start, the health check can fail once because the application is not listening yet. A following check that returns success means the start finished. See [Looking after it](care.md).

## A public address

When a reverse proxy puts MediaTrail on a real hostname, set `URLS` to that origin, including `http://` or `https://`, with no trailing slash:

```yaml
URLS: https://mediatrail.example
```

Several origins are separated with commas. This is what the login form and the import redirects trust. Without it, a proxied site rejects its own forms.

If other people use that public site, also set `MEDIATRAIL_SOURCE_URL` to the public archive of the exact source you are running. See [Start](index.md).

## Building this directory

`docker-compose.local.yml` builds the checkout as `mediatrail:local`. Use that when you are changing the program. The published image above is the one to run otherwise.

Provider keys and other secrets stay in the Compose environment or a local `.env` that is not copied into the image. Do not pass them as build arguments.
