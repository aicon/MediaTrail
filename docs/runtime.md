# Runtime

[Magyar változat](hu/runtime.md)

These are environment variables on the container. They are not the Preferences page. Change them in Compose, then recreate the container. A secret can also be a file path: the variable `SOMETHING_FILE` points at a file whose contents are the value, which is how Docker secrets are read.

Do not put these values into the image build. The image is the program. The keys stay on the machine that runs it.

Dependency and reverse-proxy hardening details (Pillow/Brotli verification, pinned Alpine packages, `TRUSTED_PROXIES`) are in [security notes in the MediaTrail repository](https://github.com/aicon/MediaTrail/blob/main/docs/security.md).

## The ones you usually set

| Variable | Role |
| --- | --- |
| `SECRET` | Session and encryption key. Set a long random value before the site is shared. |
| `TZ` | Time zone name, such as `Europe/Budapest`. Shown dates use this zone. |
| `URLS` | Public origins, comma-separated, with `http://` or `https://` and no trailing slash. Required behind a reverse proxy. |
| `TRUSTED_PROXIES` | Optional. Comma-separated IP addresses or CIDR subnets of upstream reverse proxies (for example `192.168.1.0/24,10.0.0.5`). When set, nginx uses `X-Forwarded-For` only from those proxies. Leave unset to keep the previous behavior. |
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
| `TRAKT_API` | Trakt API key used as `trakt-api-key` on public / legacy API calls. |
| `TRAKT_API_SECRET` | Only needed to refresh older private-import schedules that still use the legacy client. New logins do not use it. |
| `TRAKT_API_PKCE` | Client ID of a modern Trakt app (no secret). Used for private Import via the activate code at `trakt.tv/activate`. A free Trakt account can connect only two applications. |
| `ANILIST_ID` and `ANILIST_SECRET` | Your own AniList application, for a private import. |
| `SIMKL_ID` and `SIMKL_SECRET` | Simkl AUTH V1 app (deprecated; planned retirement ~April 2027). Still used for existing V1 tokens and as fallback when V2 is unset. A V1 `client_id` **cannot** be upgraded to V2. |
| `SIMKL_V2_ID` | Simkl AUTH V2 client id for new connections (PKCE). Register callback `…/import/simkl_private`. |
| `SIMKL_V2_SECRET` | V2 client secret when the Simkl app type is **Server apps & services** (required for that type). Leave unset for a public client type. Never commit; prefer `*_FILE` mounts. |

### Simkl AUTH V2: get keys and connect

MediaTrail runs the OAuth callback and token exchange on your server. Prefer a **new** AUTH V2 app; V1 credentials do not work on `/oauth2/*`.

1. Sign in at [simkl.com](https://simkl.com) and open [Developer settings](https://simkl.com/settings/developer/).
2. Create a **new** app (V2). The client type is fixed at registration:
   - **Server apps & services** — best fit for MediaTrail. You get a `client_id` and a `client_secret` (shown once). Set both `SIMKL_V2_ID` and `SIMKL_V2_SECRET`.
   - **Mobile, desktop & browser apps** — public client, no secret. Set only `SIMKL_V2_ID`. MediaTrail still uses S256 PKCE.
   - Do **not** pick **TV, devices & command line** for this Import button (that type has no redirect URI).
3. Add a redirect URI that matches MediaTrail exactly: `{URLS}/import/simkl_private`  
   Example: if `URLS=https://mediatrail.example.com`, register `https://mediatrail.example.com/import/simkl_private` (scheme, host, port, path; no trailing slash on `URLS`).
4. Put the values in Compose or `.env`, then recreate the container:

```text
SIMKL_V2_ID=your-v2-client-id
SIMKL_V2_SECRET=your-v2-client-secret
# Or file mounts:
# SIMKL_V2_ID_FILE=/run/secrets/simkl_v2_id
# SIMKL_V2_SECRET_FILE=/run/secrets/simkl_v2_secret
```

5. Open **Import → Connect with Simkl**. With `SIMKL_V2_ID` set, MediaTrail uses `https://simkl.com/oauth2/authorize` (PKCE), stores an encrypted **refresh** token, and schedules imports with `auth=v2`.
6. After turning V2 on, reconnect once so recurring tasks stop relying on V1-only access tokens.

Without `SIMKL_V2_ID`, MediaTrail falls back to AUTH V1 (`/oauth/authorize`) and encrypted access tokens. V1 remains until Simkl’s planned ~April 2027 retirement. Official Simkl reference: [AUTH V2 overview](https://api.simkl.org/api-reference/auth-v2) and [How to register an app](https://docs.simkl.org/how-to-use-simkl/for-developers/how-to-register-an-app).

`MU_NSFW` is the adult-content switch for MangaUpdates.

## Sign-in through another site

`SOCIAL_PROVIDERS` is a comma-separated list of django-allauth provider modules, for example `allauth.socialaccount.providers.github`. `SOCIALACCOUNT_PROVIDERS` is a JSON object with that provider's client id, secret, and any extra settings the provider documents.

`SOCIALACCOUNT_ONLY` set to `True` hides password sign-in. `REDIRECT_LOGIN_TO_SSO` set to `True` sends the login page straight to the external provider.

The redirect address you register at the provider is the public MediaTrail origin plus the path that provider expects. `URLS` has to be the same origin, or the return trip is rejected.

## Now Watching idle timers

Companion apps drive live strips through the built-in MediaTrail addon. Missed `stop` events are cleaned up by these optional overrides (defaults are fine for most installs):

| Variable | Default | Role |
| --- | --- | --- |
| `LIVE_PLAYBACK_WATCHING_STALE_SECONDS` | `180` | Drop a `watching` strip with no progress for this long |
| `LIVE_PLAYBACK_PAUSED_STALE_SECONDS` | `600` | Drop a `paused` strip left idle this long |

See [Live playback / Now Watching](now-watching.md).
