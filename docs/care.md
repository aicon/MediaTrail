# Looking after it

[Magyar változat](hu/care.md)

## Updates

Pull the tag you run, then recreate the container:

```bash
docker compose pull
docker compose up -d
```

The start runs database migrations on its own. The `db` folder stays on the host, so a new image does not empty the library.

`ghcr.io/aicon/mediatrail:latest` is the image to pull. A numbered tag stays on that release.

## The health check

The container asks itself for `GET /health/` on port 8000. During the first seconds the application may still be starting, and the log can show `connect() failed (111: Connection refused)` for `127.0.0.1:8001`. That single line is the check arriving before the application is listening. The next check should succeed.

If the same line repeats about every 45 seconds, the application did not stay up. The lines after it, from the application process, are the cause.

## Backup

Stop the container and copy the `db` folder. That copy includes the SQLite file and the Redis snapshot. Restoring is the reverse: put the folder back, then start the container. Copying the SQLite file while the container is writing can produce a half-written file. Stopping first avoids that.

`SECRET` is not in that folder. A restored library still needs the same `SECRET` if you want existing sessions and the encrypted Nuvio password to keep working. If the secret changes, people sign in again, and a saved Nuvio password has to be typed once more.

## Source offer

A public install sets `MEDIATRAIL_SOURCE_URL` to an `http` or `https` address of the exact source that built the running image. The footer links there. `/source/` is the same offer. Leaving it empty is for a private copy only.
