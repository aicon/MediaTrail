# Runtime

[Magyar változat](hu/runtime.md)

These are environment variables on the container. They are not the Preferences page. Change them in Compose, then recreate the container. A secret can also be a file path: the variable `SOMETHING_FILE` points at a file whose contents are the value, which is how Docker secrets are read.

Do not put these values into the image build. The image is the program. The keys stay on the machine that runs it.

## The ones you usually set

| Variable | Role |
| --- | --- |
| `SECRET` | Session and encryption key. Set a long random value before the site is shared. |
| `TZ` | Time zone name, such as `Europe/Budapest`. Shown dates use this zone. |
| `URLS` | Public origins, comma-separated, with `http://` or `https://` and no trailing slash. Required behind a reverse proxy. |
| `ALLOWED_HOSTS` | Hostnames the site answers to. The default is `*`. `localhost` and `127.0.0.1` are always added when you set an explicit list. |
| `PUID` and `PGID` | User and group that own the `db` folder. The default is `1000`. |
| `MEDIATRAIL_SOURCE_URL` | Public `http` or `https` address of the exact source that is running. Required when other people use the site. |
| `REGISTRATION` | `True` allows new accounts. `False` keeps the sign-up page closed. |
| `ADMIN_ENABLED` | `True` turns on `/admin/`. It is off unless you set it. |

`DEBUG` stays `False` on a machine other people can reach.

## Database

With no database host, MediaTrail uses SQLite at `db/db.sqlite3` inside the mounted data folder. Redis inside the image stores its file under `db/redis`.

Set `DB_HOST` to use PostgreSQL instead. Then also set `DB_PORT`, `DB_NAME`, `DB_USER`, and `DB_PASSWORD`. `DB_SSL_MODE` and `DB_SSL_CERT_MODE` are optional and use the names PostgreSQL uses for those two connection options.

`REDIS_URL` defaults to the Redis inside the image, `redis://127.0.0.1:6379`. Set it only when you deliberately point at another Redis. `CELERY_REDIS_URL` overrides the worker's broker on its own. `REDIS_PREFIX` prefixes cache keys when two apps share one Redis.

## Catalog keys

Movie, series, anime, game, book, comic, and board-game lookups work with the client keys shipped in the program. Replace a key when you want your own quota or when a provider asks you to. Leave a key unset to keep the built-in client. Do not copy a key into the image or into this book.

| Variable | Provider |
| --- | --- |
| `TMDB_API` | Movies and series. `TMDB_LANG` is the metadata language, default `en`. `TMDB_NSFW` includes adult results when `True`. |
| `TVDB_API` | Extra series metadata. |
| `MAL_API` | MyAnimeList. `MAL_NSFW` includes adult results when `True`. |
| `IGDB_ID` and `IGDB_SECRET` | Games. `IGDB_NSFW` when `True`. |
| `STEAM_API_KEY` | Steam store details. There is no built-in key. |
| `HARDCOVER_API` | Books. The value has to start with `Bearer` followed by a space. |
| `COMICVINE_API` | Comics. |
| `BGG_API_TOKEN` | Board games. |
| `TRAKT_API` and `TRAKT_API_SECRET` | Your own Trakt application, for a private import or your own rate limit. |
| `ANILIST_ID` and `ANILIST_SECRET` | Your own AniList application, for a private import. |
| `SIMKL_ID` and `SIMKL_SECRET` | Your own Simkl application. |

`MU_NSFW` is the adult-content switch for MangaUpdates.

## Sign-in through another site

`SOCIAL_PROVIDERS` is a comma-separated list of django-allauth provider modules, for example `allauth.socialaccount.providers.github`. `SOCIALACCOUNT_PROVIDERS` is a JSON object with that provider's client id, secret, and any extra settings the provider documents.

`SOCIALACCOUNT_ONLY` set to `True` hides password sign-in. `REDIRECT_LOGIN_TO_SSO` set to `True` sends the login page straight to the external provider.

The redirect address you register at the provider is the public MediaTrail origin plus the path that provider expects. `URLS` has to be the same origin, or the return trip is rejected.
