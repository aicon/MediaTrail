# Notes from the Yamtrack fork this tree was copied from

MediaTrail versions continue from 0.25.3 in small steps. The current version is `0.25.5`. The notes below describe the earlier Yamtrack packaging (`0.25.3-fork.1`). They are not the MediaTrail version.

# Yamtrack fork `0.25.3-fork.1`

Community build of [FuzzyGrim/Yamtrack](https://github.com/FuzzyGrim/Yamtrack). It is not an official Yamtrack release, and it is not `ghcr.io/fuzzygrim/yamtrack:latest`.

| | |
| --- | --- |
| Fork release | `0.25.3-fork.1` |
| Git tag | `v0.25.3-fork.1` |
| Image | `ghcr.io/aicon/yamtrack:0.25.3-fork.1` |
| Moving tag | `ghcr.io/aicon/yamtrack:latest` (same build as the version tag) |
| Repository | [aicon/Yamtrack](https://github.com/aicon/Yamtrack), branch `episode-history` |
| Upstream package version | `0.25.3` in `pyproject.toml` and `uv.lock` |
| License | AGPL-3.0, unchanged from upstream |

`GET /api/v1/info/` and the About page read the `VERSION` environment variable baked into the image. Before this release that argument defaulted to `dev`, and the image workflow never set it, so a running container reported `dev`. The release image sets `VERSION=0.25.3-fork.1`.

## Why this version

The last upstream release tag reachable from this tree is `v0.25.3`. The fork point on FuzzyGrim `dev` is `6a240cc2` (12 July 2026, “redesign media details page with section tabs”), 119 commits after that tag. Official Yamtrack has moved on since then, including `v0.26.x`. Those later upstream commits are not in this fork, so the version is not `0.26` and it is not a second `0.25.3`.

`0.25.3-fork.1` keeps the starting point in the name and marks the first packaged fork release. The Python package version stays `0.25.3` because `uv sync --locked` installs from `uv.lock`, which records that version. The fork release is the git tag and the image tag. `latest` on this image is the current fork build, not `ghcr.io/fuzzygrim/yamtrack:latest`.

## Upstream 0.26.3, not merged

`v0.25.3` to the fork point is already in this tree: 15 commits. That includes the media-details tabs, the home-page filter that hides unreleased episodes, and migration `0062`, which strips seconds from watch dates.

`v0.26.0` through `v0.26.3` are 41 commits after 12 July 2026. They are not in this image.

Worth a later, separate backport:

- Migration `0064` repairs dates that `0062` shifted by the container's UTC offset. `TruncMinute` ran without a timezone, so Django wrote the local wall time back as if it were UTC. On `Europe/Budapest` that is one hour. Upstream numbers this repair after `0063_season_image_fallback_to_tv`. This fork's `0063` is the episode-notes migration, so the repair has to be renumbered before it can run. It rewrites stored dates, and only where the history row still matches the shifted value.
- Django `5.2.14` to `5.2.16`, and PyJWT `2.12.1` to `2.13.0`. Cryptography `46.0.7` to `50.0.0` and gunicorn `25.3.0` to `26.0.0` are larger lockfile changes.
- SQLite WAL and an immediate transaction mode, for import locks. This only matters when the database is SQLite.

Left on upstream on purpose: the journal page, the statistics redesign, in-place HTMX edits, the Trakt export-zip import, the Goodreads import fixes, and the season-poster fallback. They do not change the API this fork added, and several of them edit the same files as the preview API. The season-poster change also wants migration number `0063`, which this fork already uses.

## What this tree adds

Compared with FuzzyGrim `dev` at `6a240cc2`, this branch is 45 files, about 19,000 lines added. Almost all of that is the preview REST API. The stable Yamtrack image has no `/api/v1`.

The API comes from the unmerged `feat/add-api` line (the work opened as Yamtrack pull request 1378 and kept current with `dev` through `6a240cc2`). Episode creation comes from [Yamtrack pull request 1608](https://github.com/FuzzyGrim/Yamtrack/pull/1608), branch `codex/api-episode-history`. On top of that pull request this fork has four commits of its own.

### Preview API (`feat/add-api`)

- New Django app `src/api/`: URLs, views, serializers, helpers, authentication, JSON error middleware, and the OpenAPI file `openapi.yaml`.
- Mounted at `/api/v1/`. Machine-readable schema at `/api/schema/`. Swagger UI at `/api/docs/`. Both schema routes use the default API authentication.
- `rest_framework` and `drf_spectacular` are installed apps. `APPEND_SLASH` is on, so a path with or without the trailing slash reaches the same view.
- Authentication is the per-user integration token, sent as `Authorization: Bearer <token>` or `X-API-Key: <token>`. There is no narrower key. The token is the user. Settings → Integrations. Regenerating it invalidates the old value immediately.
- Every route except `GET /api/v1/health/` and `GET /api/v1/info/` requires that token. A missing or unknown token is rejected.
- Lists gained a list-scoped item id, item counts, a latest-update annotation, and search on name or description (`src/lists/models.py`, migration `0004`).
- Manual-source search can be paged with `limit` and `offset` and is scoped to the user (`src/app/providers/manual.py`, `services.search`).
- Date fields accept an ISO datetime, not only `YYYY-MM-DD` (upstream API commit `bfa64306`).
- `requirements.txt` is carried from the API branch. The image does not install from it. The image installs the locked `uv.lock` set, then the two API packages named below.

### Episode history (pull request 1608)

- `POST /api/v1/media/tv/{source}/{media_id}/{season}/{episode}/history/` creates one watch. The official preview API can create a movie. It cannot create an episode: `POST /api/v1/media/episode/` is the broken path, and the episode history URL on that API only allows `GET`.
- The handler is `watch_episode` in `src/app/episode_operations.py`. It loads `tv_with_seasons` metadata, refuses a season or episode the provider does not list, creates the user season when it is missing, and calls `Season.watch`.
- `Season.watch` inserts a new `Episode` row. Repeating the same request records another watch. It does not update the previous row. Callers that retry must deduplicate.
- Season episode listings return episodes the user already tracks (`444788fa`).
- The OpenAPI text for this `POST` says the call is not idempotent and that `end_date` defaults to the current time (`43a0b858`).

### This fork, on top of pull request 1608

| Commit | Change |
| --- | --- |
| `786ffe82` | The preview API imports Django REST framework and drf-spectacular, but `uv.lock` does not list them, so `collectstatic` failed. The image runs `uv sync --locked`, then installs `djangorestframework~=3.16.1` and `drf-spectacular~=0.28.0` into that virtualenv. |
| `a4b5e0cc` | A history `POST` that creates an episode stores `notes=""`. A database created by a newer Yamtrack requires `notes`. Omitting it rolled the insert back. |
| `247afcdf` | `Episode` and its history model include `notes`. Migration `0063_episode_notes_when_missing` adds the column only when it is absent, so a database that already has `notes` still starts. Tests cover a new database and an existing one. |
| `ff3c1e64` | README records what the image did on a live library. |

The image workflow `.github/workflows/episode-history-image.yml` publishes this branch to GHCR as `0.25.3-fork.1` and `latest` only.

## Runtime behavior checked on a live library

Checked against an existing library after a backup. No titles are recorded here. The same notes are at the top of `README.md`.

- The history `POST` stores the UTC instant it is given. The page shows that instant in the container `TZ`. With `TZ=Europe/Budapest`, winter time is one hour ahead of the stored clock. The API response keeps the `Z` offset either way.
- An episode TMDB does not list for that season and number returns `404` with `{"detail": "Episode not found."}`. That is a catalog mismatch. Nothing is inserted.
- A second identical history `POST` records another watch. The page does not replace the previous one.
- Movies stay on their own path. A movie has one tracking row. A later `end_date` updates that row. It does not keep a second watch.

## API

Base path: `/api/v1/`. JSON only. The catalog below is generated from `openapi.yaml` in this tree. Where that file and the view disagree, the view is what the image does. Those disagreements are listed here, before the catalog.

### Authentication

Send one of these headers. The value is the user's integration token.

```
Authorization: Bearer <token>
X-API-Key: <token>
```

`openapi.yaml` names the header `X-API-KEY`. HTTP header names are case-insensitive, and the code reads `X-API-Key`. Both spellings work.

`GET /api/v1/health/` and `GET /api/v1/info/` allow anonymous calls. `/api/schema/` and `/api/docs/` do not: they use the default permission class `IsAuthenticated`. The Docker healthcheck is a different URL, `GET /health/` on port 8000, and it does not use the API token.

`GET /api/v1/info/` returns `version`, `debug`, `frontend_url`, `language`, and `timezone`. On this image `version` is `0.25.3-fork.1`.

### Media types, sources, status

`media_type` for a title: `movie`, `tv`, `anime`, `manga`, `game`, `book`, `comic`, `boardgame`.

`media_type` when the path addresses a child row as well: also `season` and `episode`. Episode *creation* does not use `media_type=episode`. It uses `media_type=tv` and the season and episode numbers in the path.

`source`: `tmdb`, `mal`, `igdb`, `mangaupdates`, `openlibrary`, `hardcover`, `comicvine`, `bgg`, `manual`. A provider source requires `media_id`. `manual` omits `media_id` and sends the title.

`media_id` is a string. A TMDB id is still sent as text, for example `1399`.

Status integers:

| Value | Name |
| --- | --- |
| 0 | Planning |
| 1 | In progress |
| 2 | Paused |
| 3 | Completed |
| 4 | Dropped |

Creating a tracked item without `status` stores Planning. An episode history `POST` does not take a status. The history response for an episode uses `3` (Completed) when the row exists.

### Fields a client may write

From `MEDIA_MODIFIABLE_FIELDS` in `src/api/helpers.py`:

| Type | Writable fields |
| --- | --- |
| movie | `score`, `status`, `start_date`, `end_date`, `notes` |
| tv | `score`, `status`, `notes` |
| season | `score`, `status`, `notes` |
| episode | `end_date` |
| anime, manga, game, book, comic, boardgame | `score`, `status`, `progress`, `start_date`, `end_date`, `notes` |

`score` is 0 through 10, one decimal. Dates are ISO-8601. A date-only value and a full datetime are both accepted.

### Pagination and errors

List views return:

```json
{
  "pagination": {
    "total": 0,
    "limit": 20,
    "offset": 0,
    "next": null,
    "previous": null
  },
  "results": []
}
```

`limit` defaults to 20 and is capped at 200. `offset` defaults to 0. `limit` must be greater than 0 and `offset` must be at least 0, or the response is `400`.

`openapi.yaml` types a few list responses as a bare array (`ConsumptionInfos` or `ListsMinimized`). The views still wrap those lists in `pagination` and `results`. Read `results`.

Errors:

```json
{"detail": "Episode not found.", "errors": null}
```

`errors` is present when a form or a serializer rejected the body. It can be an object of field messages or a string from a provider failure.

### Episode watch

```
POST /api/v1/media/tv/tmdb/1399/1/1/history/
X-API-Key: <token>
Content-Type: application/json

{"end_date": "2026-01-15T20:30:00Z"}
```

The body may be omitted or `{}`. `end_date` then becomes the current time in the container timezone, with seconds and microseconds cleared.

Success is `201` and one history object:

| Field | Episode value |
| --- | --- |
| `consumption_id` | new episode row id |
| `created` | row `created_at` |
| `score` | `null` |
| `progress` | `1` |
| `progressed_at` | `created_at` |
| `status` | `3` |
| `start_date` | `created_at` |
| `end_date` | the instant that was stored |
| `notes` | `""` |

`notes` in this response is always an empty string for an episode, including when the stored column is empty. The insert writes `notes=""` so a database whose `notes` column is `NOT NULL` accepts the row.

`400` means the media type is not `tv`, the source is not valid for `tv`, or `end_date` is not a datetime. `404` means the provider metadata has no such season or episode. `500` means the provider failed for another reason. `403` means the token is missing or unknown.

`GET` on the same path lists watches for that episode, newest ordering as stored, inside `pagination` and `results`. `PATCH` on `.../history/{consumption_id}/` can change that row's `end_date`. `DELETE` removes that one watch. Deleting is supported by the API. A sync client that must not delete simply never calls `DELETE`.

Creating the parent season sets it to In progress with empty notes. The TV show row is not given a second history entry by this call.

### Movie watch

```
POST /api/v1/media/movie/
X-API-Key: <token>

{"source": "tmdb", "media_id": "603", "status": 3, "end_date": "2026-01-15T20:30:00Z"}
```

This creates the tracked movie. A later change is `PATCH /api/v1/media/movie/tmdb/603/` with the new `end_date`. There is no movie equivalent of the episode history `POST`. One movie has one tracking row.

### Other routes

The same pattern repeats for seasons and for the other media types: list, create, detail, patch, delete, changes history, consumption history, lists, recommendations, and provider sync. Sync is `POST .../sync/` and refreshes metadata from the provider. Manual items are not synced from a provider. Calendar `POST /api/v1/calendar/update/` queues a calendar refresh and returns `202`.

The Docker healthcheck stays on `/health/`. `GET /api/v1/health/` runs the same style of checks and returns JSON. It is anonymous and can take about two seconds.

## Endpoint catalog

Generated from `openapi.yaml`. Path parameters use `{name}`. A trailing slash is optional because `APPEND_SLASH` is enabled.

### GET `/api/v1/calendar/`

List upcoming events of tracked media

| Parameter | In | Required | Type | Description |
| --- | --- | --- | --- | --- |
| `start_date` | query | no | string (date) | The start date to retrieve events for (YYYY-MM-DD) |
| `end_date` | query | no | string (date) | The end date to retrieve events for. If omitted with start_date, defaults to the end of that month; otherwise defaults to the end of the selected/current month (YYYY-MM-DD) |
| `limit` | query | no | integer | Maximum number of items to return (default: 20) |
| `offset` | query | no | integer | Offset for pagination (default: 0) |
| `month` | query | no | integer | The month to retrieve events for (1-12). Used only if start_date is not set. Default is current month |
| `year` | query | no | integer | The year to retrieve events for. Used only if start_date is not set. Default is current year |

Responses: `200` OK — `PaginatedCalendar`; `400` Bad Request — `ErrorResponse`; `403` Forbidden — `ErrorResponse`; `500` Internal Server Error — `ErrorResponse`.

### POST `/api/v1/calendar/update/`

Update calendar events

Responses: `202` Accepted — `BasicResponse`; `403` Forbidden — `ErrorResponse`; `500` Internal Server Error — `ErrorResponse`.

### GET `/api/v1/changes_history/{media_type}/{history_id}/`

Retrieve a specific changes history record by media type and history id

| Parameter | In | Required | Type | Description |
| --- | --- | --- | --- | --- |
| `media_type` | path | yes | MediaTypesComplete |  |
| `history_id` | path | yes | integer |  |

Responses: `200` OK — `ChangesHistoryRecord`; `400` Bad Request — `ErrorResponse`; `403` Forbidden — `ErrorResponse`; `404` Not Found — `ErrorResponse`; `500` Internal Server Error — `ErrorResponse`.

### DELETE `/api/v1/changes_history/{media_type}/{history_id}/`

Delete a specific changes history record by media type and history id

| Parameter | In | Required | Type | Description |
| --- | --- | --- | --- | --- |
| `media_type` | path | yes | MediaTypes |  |
| `history_id` | path | yes | integer |  |

Responses: `204` No Content — `BasicResponse`; `400` Bad Request — `ErrorResponse`; `403` Forbidden — `ErrorResponse`; `404` Not Found — `ErrorResponse`; `500` Internal Server Error — `ErrorResponse`.

### GET `/api/v1/health/`

Health check endpoint

Responses: `200` OK — `HealthResponse`; `500` Internal Server Error — `HealthResponse`.

### GET `/api/v1/info/`

Get application information

Responses: `200` OK — `InfoResponse`.

### GET `/api/v1/lists/`

List the user's custom lists

| Parameter | In | Required | Type | Description |
| --- | --- | --- | --- | --- |
| `limit` | query | no | integer | Maximum number of items to return (default: 20) |
| `offset` | query | no | integer | Offset for pagination (default: 0) |
| `search` | query | no | string | Case-insensitive substring search on list name or description |
| `sort` | query | no | ListsSortOptions | Sort order for results |

Responses: `200` OK — `PaginatedListsNoItems`; `400` Bad Request — `ErrorResponse`; `403` Forbidden — `ErrorResponse`; `404` Not Found — `ErrorResponse`; `500` Internal Server Error — `ErrorResponse`.

### POST `/api/v1/lists/`

Create a new list

Body (required, JSON):

| Field | Type | Description |
| --- | --- | --- |
| `name` | string |  |
| `description` | string, null |  |
| `collaborators` | array of number | List of username ids allowed to collaborate on this list |

Responses: `201` Created — `CompleteList`; `400` Bad Request — `ErrorResponse`; `403` Forbidden — `ErrorResponse`; `404` Not Found — `ErrorResponse`; `500` Internal Server Error — `ErrorResponse`.

### GET `/api/v1/lists/{list_id}/`

Get list details

| Parameter | In | Required | Type | Description |
| --- | --- | --- | --- | --- |
| `list_id` | path | yes | integer |  |
| `limit` | query | no | integer | Maximum number of items to return (default: 20) |
| `offset` | query | no | integer | Offset for pagination (default: 0) |
| `search` | query | no | string | Case-insensitive substring search on item titles |
| `sort` | query | no | SortOptions | Sort order for results |

Responses: `200` OK — `CompleteList`; `400` Bad Request — `ErrorResponse`; `403` Forbidden — `ErrorResponse`; `404` Not Found — `ErrorResponse`; `500` Internal Server Error — `ErrorResponse`.

### PATCH `/api/v1/lists/{list_id}/`

Edit a list

| Parameter | In | Required | Type | Description |
| --- | --- | --- | --- | --- |
| `list_id` | path | yes | integer |  |

Body (required, JSON):

| Field | Type | Description |
| --- | --- | --- |
| `name` | string, null |  |
| `description` | string, null |  |
| `collaborators` | array of number | List of username ids allowed to collaborate on this list |

Responses: `200` OK — `CompleteList`; `400` Bad Request — `ErrorResponse`; `403` Forbidden — `ErrorResponse`; `404` Not Found — `ErrorResponse`; `500` Internal Server Error — `ErrorResponse`.

### DELETE `/api/v1/lists/{list_id}/`

Delete a list

| Parameter | In | Required | Type | Description |
| --- | --- | --- | --- | --- |
| `list_id` | path | yes | integer |  |

Responses: `204` No Content; `400` Bad Request — `ErrorResponse`; `403` Forbidden — `ErrorResponse`; `404` Not Found — `ErrorResponse`; `500` Internal Server Error — `ErrorResponse`.

### GET `/api/v1/lists/{list_id}/items/`

List list items

| Parameter | In | Required | Type | Description |
| --- | --- | --- | --- | --- |
| `list_id` | path | yes | integer |  |

Responses: `200` OK — `PaginatedMedia`; `400` Bad Request — `ErrorResponse`; `403` Forbidden — `ErrorResponse`; `404` Not Found — `ErrorResponse`; `500` Internal Server Error — `ErrorResponse`.

### GET `/api/v1/lists/{list_id}/items/{item_id}/`

Get an Item from a list

| Parameter | In | Required | Type | Description |
| --- | --- | --- | --- | --- |
| `list_id` | path | yes | integer |  |
| `item_id` | path | yes | integer | Sequential item identifier scoped to the list (starts from 0). |

Responses: `200` OK — `CompleteMedia`; `400` Bad Request — `ErrorResponse`; `403` Forbidden — `ErrorResponse`; `404` Not Found — `ErrorResponse`; `500` Internal Server Error — `ErrorResponse`.

### DELETE `/api/v1/lists/{list_id}/items/{item_id}/`

Remove an item from a list

| Parameter | In | Required | Type | Description |
| --- | --- | --- | --- | --- |
| `list_id` | path | yes | integer |  |
| `item_id` | path | yes | integer | Sequential item identifier scoped to the list (starts from 0). |

Responses: `204` Removed; `400` Bad Request — `ErrorResponse`; `403` Forbidden — `ErrorResponse`; `404` Not Found — `ErrorResponse`; `500` Internal Server Error — `ErrorResponse`.

### GET `/api/v1/media/`

List tracked media for the authenticated user

| Parameter | In | Required | Type | Description |
| --- | --- | --- | --- | --- |
| `exclude` | query | no | string | Comma-separated list of media types to exclude (excluded by default are seasons and episodes) |
| `limit` | query | no | integer | Maximum number of items to return (default: 20) |
| `offset` | query | no | integer | Offset for pagination (default: 0) |
| `search` | query | no | string | Case-insensitive substring search on item title |
| `sort` | query | no | SortOptions | Sort order for results |
| `status` | query | no | MediaStatus | Filter by media status |
| `media_type` | query | no | MediaTypesComplete | Filter by media type |

Responses: `200` OK — `PaginatedMedia`; `400` Bad Request — `ErrorResponse`; `403` Forbidden — `ErrorResponse`; `404` Not Found — `ErrorResponse`; `500` Internal Server Error — `ErrorResponse`.

### GET `/api/v1/media/{media_type}/`

List tracked media of a given media type for the authenticated user

| Parameter | In | Required | Type | Description |
| --- | --- | --- | --- | --- |
| `media_type` | path | yes | MediaTypesComplete | Filter by media type |
| `limit` | query | no | integer | Maximum number of items to return (default: 20) |
| `offset` | query | no | integer | Offset for pagination (default: 0) |
| `search` | query | no | string | Case-insensitive substring search on item title |
| `sort` | query | no | SortOptions | Sort order for results |
| `status` | query | no | MediaStatus | Filter by media status |

Responses: `200` OK — `PaginatedMedia`; `400` Bad Request — `ErrorResponse`; `403` Forbidden — `ErrorResponse`; `404` Not Found — `ErrorResponse`; `500` Internal Server Error — `ErrorResponse`.

### POST `/api/v1/media/{media_type}/`

Create a media item of a given media type

Create a new tracked media item. 
For manual creations set `source` to `manual` and omit `media_id`.
For provider creations set `source` to the provider name (eg. `tmdb`) and
provide `media_id`. Provider metadata (title/image) will overwrite any
existing values when creating or updating the Item.

| Parameter | In | Required | Type | Description |
| --- | --- | --- | --- | --- |
| `media_type` | path | yes | MediaTypesComplete |  |

Body (required, JSON):

| Field | Type | Description |
| --- | --- | --- |
| `source` | Source | Provider source or 'manual' |
| `media_id` | string, null | Provider media identifier (required for provider sources) |
| `title` | string |  |
| `image` | string, null |  |
| `score` | number (float), null |  |
| `status` | MediaStatus |  |
| `progress` | integer, null |  |
| `start_date` | string (date-time), null |  |
| `end_date` | string (date-time), null |  |
| `notes` | string, null |  |
| `repeats` | integer, null |  |
| `season_number` | integer, null |  |
| `episode_number` | integer, null |  |

Responses: `201` Created — `CompleteMedia`; `400` Bad Request — `ErrorResponse`; `403` Forbidden — `ErrorResponse`; `404` Not Found — `ErrorResponse`; `500` Internal Server Error — `ErrorResponse`.

### GET `/api/v1/media/{media_type}/{source}/{media_id}/`

Retrieve a media item

| Parameter | In | Required | Type | Description |
| --- | --- | --- | --- | --- |
| `media_type` | path | yes | MediaTypes |  |
| `source` | path | yes | Source |  |
| `media_id` | path | yes | string |  |

Responses: `200` OK — `CompleteMedia`; `400` Bad Request — `ErrorResponse`; `403` Forbidden — `ErrorResponse`; `404` Not Found — `ErrorResponse`; `500` Internal Server Error — `ErrorResponse`.

### PATCH `/api/v1/media/{media_type}/{source}/{media_id}/`

Edit LAST CONSUMPTION of a media item if it's tracked

| Parameter | In | Required | Type | Description |
| --- | --- | --- | --- | --- |
| `media_type` | path | yes | MediaTypes |  |
| `source` | path | yes | Source |  |
| `media_id` | path | yes | string |  |

Body (required, JSON):

Schema: `object`.

Responses: `200` Updated; `400` Bad Request — `ErrorResponse`; `403` Forbidden — `ErrorResponse`; `404` Not Found — `ErrorResponse`; `500` Internal Server Error — `ErrorResponse`.

### DELETE `/api/v1/media/{media_type}/{source}/{media_id}/`

Delete a media item and all its consumptions if it's tracked

| Parameter | In | Required | Type | Description |
| --- | --- | --- | --- | --- |
| `media_type` | path | yes | MediaTypes |  |
| `source` | path | yes | Source |  |
| `media_id` | path | yes | string |  |

Responses: `204` No Content; `400` Bad Request — `ErrorResponse`; `403` Forbidden — `ErrorResponse`; `404` Not Found — `ErrorResponse`; `500` Internal Server Error — `ErrorResponse`.

### GET `/api/v1/media/{media_type}/{source}/{media_id}/changes_history/`

Get changes history records for a media item

| Parameter | In | Required | Type | Description |
| --- | --- | --- | --- | --- |
| `media_type` | path | yes | MediaTypes |  |
| `source` | path | yes | Source |  |
| `media_id` | path | yes | string |  |
| `limit` | query | no | integer | Maximum number of results per page |
| `offset` | query | no | integer | Starting index for pagination |

Responses: `200` OK — `PaginatedChangesHistory`; `400` Bad Request — `ErrorResponse`; `403` Forbidden — `ErrorResponse`; `404` Not Found — `ErrorResponse`; `500` Internal Server Error — `ErrorResponse`.

### GET `/api/v1/media/{media_type}/{source}/{media_id}/history/`

Get watch history records for a media item

| Parameter | In | Required | Type | Description |
| --- | --- | --- | --- | --- |
| `media_type` | path | yes | MediaTypes |  |
| `source` | path | yes | Source |  |
| `media_id` | path | yes | string |  |
| `limit` | query | no | integer | Maximum number of results per page |
| `offset` | query | no | integer | Starting index for pagination |

Responses: `200` OK — `PaginatedConsumptionHistory`; `400` Bad Request — `ErrorResponse`; `403` Forbidden — `ErrorResponse`; `404` Not Found — `ErrorResponse`; `500` Internal Server Error — `ErrorResponse`.

### GET `/api/v1/media/{media_type}/{source}/{media_id}/history/{consumption_id}/`

Retrieve a specific watch history record by media type, source, media id and watch id

| Parameter | In | Required | Type | Description |
| --- | --- | --- | --- | --- |
| `media_type` | path | yes | MediaTypes |  |
| `source` | path | yes | Source |  |
| `media_id` | path | yes | string |  |
| `consumption_id` | path | yes | integer |  |

Responses: `200` OK — `ConsumptionInfos`; `400` Bad Request — `ErrorResponse`; `403` Forbidden — `ErrorResponse`; `404` Not Found — `ErrorResponse`; `500` Internal Server Error — `ErrorResponse`.

### PATCH `/api/v1/media/{media_type}/{source}/{media_id}/history/{consumption_id}/`

Edit a specific consumption history record of a tracked media item

| Parameter | In | Required | Type | Description |
| --- | --- | --- | --- | --- |
| `media_type` | path | yes | MediaTypes |  |
| `source` | path | yes | Source |  |
| `media_id` | path | yes | string |  |
| `consumption_id` | path | yes | integer |  |

Body (required, JSON):

Schema: `object`.

Responses: `200` Updated — `ConsumptionInfos`; `400` Bad Request — `ErrorResponse`; `403` Forbidden — `ErrorResponse`; `404` Not Found — `ErrorResponse`; `500` Internal Server Error — `ErrorResponse`.

### DELETE `/api/v1/media/{media_type}/{source}/{media_id}/history/{consumption_id}/`

Delete a specific watch history record by media type, source, media id and watch id

| Parameter | In | Required | Type | Description |
| --- | --- | --- | --- | --- |
| `media_type` | path | yes | MediaTypes |  |
| `source` | path | yes | Source |  |
| `media_id` | path | yes | string |  |
| `consumption_id` | path | yes | integer |  |

Responses: `204` No Content; `400` Bad Request — `ErrorResponse`; `403` Forbidden — `ErrorResponse`; `404` Not Found — `ErrorResponse`; `500` Internal Server Error — `ErrorResponse`.

### GET `/api/v1/media/{media_type}/{source}/{media_id}/lists/`

List lists that the item belongs to

| Parameter | In | Required | Type | Description |
| --- | --- | --- | --- | --- |
| `media_type` | path | yes | MediaTypes |  |
| `source` | path | yes | Source |  |
| `media_id` | path | yes | string |  |
| `offset` | query | no | integer | Offset for pagination (default: 0) |
| `sort` | query | no | SortOptions | Sort order for results |

Responses: `200` OK — `PaginatedLists`; `400` Bad Request — `ErrorResponse`; `403` Forbidden — `ErrorResponse`; `404` Not Found — `ErrorResponse`; `500` Internal Server Error — `ErrorResponse`.

### PUT `/api/v1/media/{media_type}/{source}/{media_id}/lists/{list_id}/`

Remove the item from a specific list by list id

| Parameter | In | Required | Type | Description |
| --- | --- | --- | --- | --- |
| `media_type` | path | yes | MediaTypes |  |
| `source` | path | yes | Source |  |
| `media_id` | path | yes | string |  |
| `list_id` | path | yes | integer |  |

Responses: `200` OK — `array of ListsMinimized`; `400` Bad Request — `ErrorResponse`; `403` Forbidden — `ErrorResponse`; `404` Not Found — `ErrorResponse`; `500` Internal Server Error — `ErrorResponse`.

### DELETE `/api/v1/media/{media_type}/{source}/{media_id}/lists/{list_id}/`

Remove the item from a specific list by list id

| Parameter | In | Required | Type | Description |
| --- | --- | --- | --- | --- |
| `media_type` | path | yes | MediaTypes |  |
| `source` | path | yes | Source |  |
| `media_id` | path | yes | string |  |
| `list_id` | path | yes | integer |  |

Responses: `204` Removed; `400` Bad Request — `ErrorResponse`; `403` Forbidden — `ErrorResponse`; `404` Not Found — `ErrorResponse`; `500` Internal Server Error — `ErrorResponse`.

### GET `/api/v1/media/{media_type}/{source}/{media_id}/recommendations/`

Retrieve related medias of a tracked media item by media type, source and media id

| Parameter | In | Required | Type | Description |
| --- | --- | --- | --- | --- |
| `media_type` | path | yes | MediaTypes |  |
| `source` | path | yes | Source |  |
| `media_id` | path | yes | string |  |

Responses: `200` OK — `RelatedMedia`; `400` Bad Request — `ErrorResponse`; `403` Forbidden — `ErrorResponse`; `404` Not Found — `ErrorResponse`; `500` Internal Server Error — `ErrorResponse`.

### GET `/api/v1/media/{media_type}/{source}/{media_id}/seasons/`

Retrieve tracked seasons for a TV media item by media type, source and media id

| Parameter | In | Required | Type | Description |
| --- | --- | --- | --- | --- |
| `media_type` | path | yes | MediaTypes |  |
| `source` | path | yes | Source |  |
| `media_id` | path | yes | string |  |
| `limit` | query | no | integer | Maximum number of items to return (default: 20) |
| `offset` | query | no | integer | Offset for pagination (default: 0) |

Responses: `200` OK — `PaginatedMedia`; `400` Bad Request — `ErrorResponse`; `403` Forbidden — `ErrorResponse`; `404` Not Found — `ErrorResponse`; `500` Internal Server Error — `ErrorResponse`.

### POST `/api/v1/media/{media_type}/{source}/{media_id}/sync/`

Sync metadata from provider (non-manual sources)

| Parameter | In | Required | Type | Description |
| --- | --- | --- | --- | --- |
| `media_type` | path | yes | MediaTypes |  |
| `source` | path | yes | Source |  |
| `media_id` | path | yes | string |  |

Responses: `202` Sync triggered — `BasicResponse`; `400` Bad Request — `ErrorResponse`; `403` Forbidden — `ErrorResponse`; `404` Not Found — `ErrorResponse`; `429` Too Many Requests — `ErrorResponse`; `500` Internal Server Error — `ErrorResponse`.

### GET `/api/v1/media/{media_type}/{source}/{media_id}/{season_number}/`

Retrieve a tracked season

| Parameter | In | Required | Type | Description |
| --- | --- | --- | --- | --- |
| `media_type` | path | yes | MediaTypes |  |
| `source` | path | yes | Source |  |
| `media_id` | path | yes | string |  |
| `season_number` | path | yes | integer |  |

Responses: `200` OK — `CompleteMedia`; `400` Bad Request — `ErrorResponse`; `403` Forbidden — `ErrorResponse`; `404` Not Found — `ErrorResponse`; `500` Internal Server Error — `ErrorResponse`.

### PATCH `/api/v1/media/{media_type}/{source}/{media_id}/{season_number}/`

Edit LAST CONSUMPTION of a tracked season

| Parameter | In | Required | Type | Description |
| --- | --- | --- | --- | --- |
| `media_type` | path | yes | MediaTypes |  |
| `source` | path | yes | Source |  |
| `media_id` | path | yes | string |  |
| `season_number` | path | yes | integer |  |

Body (required, JSON):

| Field | Type | Description |
| --- | --- | --- |
| `score` | number (float), null |  |
| `status` | MediaStatus |  |
| `notes` | string, null |  |

Responses: `200` Updated; `400` Bad Request — `ErrorResponse`; `403` Forbidden — `ErrorResponse`; `404` Not Found — `ErrorResponse`; `500` Internal Server Error — `ErrorResponse`.

### DELETE `/api/v1/media/{media_type}/{source}/{media_id}/{season_number}/`

Delete a tracked season and all of its consumptions

| Parameter | In | Required | Type | Description |
| --- | --- | --- | --- | --- |
| `media_type` | path | yes | MediaTypes |  |
| `source` | path | yes | Source |  |
| `media_id` | path | yes | string |  |
| `season_number` | path | yes | integer |  |

Responses: `204` No Content; `400` Bad Request — `ErrorResponse`; `403` Forbidden — `ErrorResponse`; `404` Not Found — `ErrorResponse`; `500` Internal Server Error — `ErrorResponse`.

### GET `/api/v1/media/{media_type}/{source}/{media_id}/{season_number}/changes_history/`

Get changes history records for a season

| Parameter | In | Required | Type | Description |
| --- | --- | --- | --- | --- |
| `media_type` | path | yes | MediaTypes |  |
| `source` | path | yes | Source |  |
| `media_id` | path | yes | string |  |
| `season_number` | path | yes | integer |  |
| `limit` | query | no | integer | Maximum number of results per page |
| `offset` | query | no | integer | Starting index for pagination |

Responses: `200` OK — `PaginatedChangesHistory`; `400` Bad Request — `ErrorResponse`; `403` Forbidden — `ErrorResponse`; `404` Not Found — `ErrorResponse`; `500` Internal Server Error — `ErrorResponse`.

### GET `/api/v1/media/{media_type}/{source}/{media_id}/{season_number}/episodes/`

Retrieve tracked episodes for a season item by media type, source, media id and season number

| Parameter | In | Required | Type | Description |
| --- | --- | --- | --- | --- |
| `media_type` | path | yes | MediaTypes |  |
| `source` | path | yes | Source |  |
| `media_id` | path | yes | string |  |
| `season_number` | path | yes | integer |  |
| `limit` | query | no | integer | Maximum number of items to return (default: 20) |
| `offset` | query | no | integer | Offset for pagination (default: 0) |

Responses: `200` OK — `PaginatedMedia`; `400` Bad Request — `ErrorResponse`; `403` Forbidden — `ErrorResponse`; `404` Not Found — `ErrorResponse`; `500` Internal Server Error — `ErrorResponse`.

### GET `/api/v1/media/{media_type}/{source}/{media_id}/{season_number}/history/`

Get watch history records for a season

| Parameter | In | Required | Type | Description |
| --- | --- | --- | --- | --- |
| `media_type` | path | yes | MediaTypes |  |
| `source` | path | yes | Source |  |
| `media_id` | path | yes | string |  |
| `season_number` | path | yes | integer |  |
| `limit` | query | no | integer | Maximum number of results per page |
| `offset` | query | no | integer | Starting index for pagination |

Responses: `200` OK — `array of ConsumptionInfos`; `400` Bad Request — `ErrorResponse`; `403` Forbidden — `ErrorResponse`; `404` Not Found — `ErrorResponse`; `500` Internal Server Error — `ErrorResponse`.

### GET `/api/v1/media/{media_type}/{source}/{media_id}/{season_number}/history/{consumption_id}/`

Retrieve a specific watch history record by media type, source, media id, season number and watch id

| Parameter | In | Required | Type | Description |
| --- | --- | --- | --- | --- |
| `media_type` | path | yes | MediaTypes |  |
| `source` | path | yes | Source |  |
| `media_id` | path | yes | string |  |
| `season_number` | path | yes | integer |  |
| `consumption_id` | path | yes | integer |  |

Responses: `200` OK — `ConsumptionInfos`; `400` Bad Request — `ErrorResponse`; `403` Forbidden — `ErrorResponse`; `404` Not Found — `ErrorResponse`; `500` Internal Server Error — `ErrorResponse`.

### PATCH `/api/v1/media/{media_type}/{source}/{media_id}/{season_number}/history/{consumption_id}/`

Edit a specific consumption history record of a tracked season

| Parameter | In | Required | Type | Description |
| --- | --- | --- | --- | --- |
| `media_type` | path | yes | MediaTypes |  |
| `source` | path | yes | Source |  |
| `media_id` | path | yes | string |  |
| `season_number` | path | yes | integer |  |
| `consumption_id` | path | yes | integer |  |

Body (required, JSON):

| Field | Type | Description |
| --- | --- | --- |
| `score` | number (float), null |  |
| `status` | MediaStatus |  |
| `notes` | string, null |  |

Responses: `200` Updated — `ConsumptionInfos`; `400` Bad Request — `ErrorResponse`; `403` Forbidden — `ErrorResponse`; `404` Not Found — `ErrorResponse`; `500` Internal Server Error — `ErrorResponse`.

### DELETE `/api/v1/media/{media_type}/{source}/{media_id}/{season_number}/history/{consumption_id}/`

Delete a specific watch history record by media type, source, media id, season number and watch id

| Parameter | In | Required | Type | Description |
| --- | --- | --- | --- | --- |
| `media_type` | path | yes | MediaTypes |  |
| `source` | path | yes | Source |  |
| `media_id` | path | yes | string |  |
| `season_number` | path | yes | integer |  |
| `consumption_id` | path | yes | integer |  |

Responses: `204` No Content; `400` Bad Request — `ErrorResponse`; `403` Forbidden — `ErrorResponse`; `404` Not Found — `ErrorResponse`; `500` Internal Server Error — `ErrorResponse`.

### GET `/api/v1/media/{media_type}/{source}/{media_id}/{season_number}/lists/`

List lists that the season item belongs to

| Parameter | In | Required | Type | Description |
| --- | --- | --- | --- | --- |
| `media_type` | path | yes | MediaTypes |  |
| `source` | path | yes | Source |  |
| `media_id` | path | yes | string |  |
| `season_number` | path | yes | integer |  |
| `offset` | query | no | integer | Offset for pagination (default: 0) |
| `sort` | query | no | SortOptions | Sort order for results |

Responses: `200` OK — `PaginatedLists`; `400` Bad Request — `ErrorResponse`; `403` Forbidden — `ErrorResponse`; `404` Not Found — `ErrorResponse`; `500` Internal Server Error — `ErrorResponse`.

### PUT `/api/v1/media/{media_type}/{source}/{media_id}/{season_number}/lists/{list_id}/`

Add the season item to a specific list by list id

| Parameter | In | Required | Type | Description |
| --- | --- | --- | --- | --- |
| `media_type` | path | yes | MediaTypes |  |
| `source` | path | yes | Source |  |
| `media_id` | path | yes | string |  |
| `season_number` | path | yes | integer |  |
| `list_id` | path | yes | integer |  |

Responses: `200` OK — `array of ListsMinimized`; `400` Bad Request — `ErrorResponse`; `403` Forbidden — `ErrorResponse`; `404` Not Found — `ErrorResponse`; `500` Internal Server Error — `ErrorResponse`.

### DELETE `/api/v1/media/{media_type}/{source}/{media_id}/{season_number}/lists/{list_id}/`

Remove the season item from a specific list by list id

| Parameter | In | Required | Type | Description |
| --- | --- | --- | --- | --- |
| `media_type` | path | yes | MediaTypes |  |
| `source` | path | yes | Source |  |
| `media_id` | path | yes | string |  |
| `season_number` | path | yes | integer |  |
| `list_id` | path | yes | integer |  |

Responses: `204` Removed; `400` Bad Request — `ErrorResponse`; `403` Forbidden — `ErrorResponse`; `404` Not Found — `ErrorResponse`; `500` Internal Server Error — `ErrorResponse`.

### POST `/api/v1/media/{media_type}/{source}/{media_id}/{season_number}/sync/`

Sync season metadata from provider (non-manual sources)

| Parameter | In | Required | Type | Description |
| --- | --- | --- | --- | --- |
| `media_type` | path | yes | MediaTypes |  |
| `source` | path | yes | Source |  |
| `media_id` | path | yes | string |  |
| `season_number` | path | yes | integer |  |

Responses: `202` Sync triggered; `400` Bad Request — `ErrorResponse`; `403` Forbidden — `ErrorResponse`; `404` Not Found — `ErrorResponse`; `429` Too Many Requests — `ErrorResponse`; `500` Internal Server Error — `ErrorResponse`.

### GET `/api/v1/media/{media_type}/{source}/{media_id}/{season_number}/{episode_number}/`

Retrieve a tracked episode item by media type, source, media id, season number and episode number

| Parameter | In | Required | Type | Description |
| --- | --- | --- | --- | --- |
| `media_type` | path | yes | MediaTypes |  |
| `source` | path | yes | Source |  |
| `media_id` | path | yes | string |  |
| `season_number` | path | yes | integer |  |
| `episode_number` | path | yes | integer |  |

Responses: `200` OK — `CompleteMedia`; `400` Bad Request — `ErrorResponse`; `403` Forbidden — `ErrorResponse`; `404` Not Found — `ErrorResponse`; `500` Internal Server Error — `ErrorResponse`.

### PATCH `/api/v1/media/{media_type}/{source}/{media_id}/{season_number}/{episode_number}/`

Edit LAST CONSUMPTION of a tracked episode

| Parameter | In | Required | Type | Description |
| --- | --- | --- | --- | --- |
| `media_type` | path | yes | MediaTypes |  |
| `source` | path | yes | Source |  |
| `media_id` | path | yes | string |  |
| `season_number` | path | yes | integer |  |
| `episode_number` | path | yes | integer |  |

Body (required, JSON):

| Field | Type | Description |
| --- | --- | --- |
| `end_date` | string (date-time), null |  |

Responses: `200` Updated; `400` Bad Request — `ErrorResponse`; `403` Forbidden — `ErrorResponse`; `404` Not Found — `ErrorResponse`; `500` Internal Server Error — `ErrorResponse`.

### DELETE `/api/v1/media/{media_type}/{source}/{media_id}/{season_number}/{episode_number}/`

Delete a tracked media item

| Parameter | In | Required | Type | Description |
| --- | --- | --- | --- | --- |
| `media_type` | path | yes | MediaTypes |  |
| `source` | path | yes | Source |  |
| `media_id` | path | yes | string |  |
| `season_number` | path | yes | integer |  |
| `episode_number` | path | yes | integer |  |

Responses: `204` No Content; `400` Bad Request — `ErrorResponse`; `403` Forbidden — `ErrorResponse`; `404` Not Found — `ErrorResponse`; `500` Internal Server Error — `ErrorResponse`.

### GET `/api/v1/media/{media_type}/{source}/{media_id}/{season_number}/{episode_number}/changes_history/`

Get changes history records for an episode

| Parameter | In | Required | Type | Description |
| --- | --- | --- | --- | --- |
| `media_type` | path | yes | MediaTypes |  |
| `source` | path | yes | Source |  |
| `media_id` | path | yes | string |  |
| `season_number` | path | yes | integer |  |
| `episode_number` | path | yes | integer |  |
| `limit` | query | no | integer | Maximum number of results per page |
| `offset` | query | no | integer | Starting index for pagination |

Responses: `200` OK — `PaginatedChangesHistory`; `400` Bad Request — `ErrorResponse`; `403` Forbidden — `ErrorResponse`; `404` Not Found — `ErrorResponse`; `500` Internal Server Error — `ErrorResponse`.

### GET `/api/v1/media/{media_type}/{source}/{media_id}/{season_number}/{episode_number}/history/`

Get watch history records for an episode

| Parameter | In | Required | Type | Description |
| --- | --- | --- | --- | --- |
| `media_type` | path | yes | MediaTypes |  |
| `source` | path | yes | Source |  |
| `media_id` | path | yes | string |  |
| `season_number` | path | yes | integer |  |
| `episode_number` | path | yes | integer |  |
| `limit` | query | no | integer | Maximum number of results per page |
| `offset` | query | no | integer | Starting index for pagination |

Responses: `200` OK — `array of ConsumptionInfos`; `400` Bad Request — `ErrorResponse`; `403` Forbidden — `ErrorResponse`; `404` Not Found — `ErrorResponse`; `500` Internal Server Error — `ErrorResponse`.

### POST `/api/v1/media/{media_type}/{source}/{media_id}/{season_number}/{episode_number}/history/`

Create an episode watch history record

Creates a new consumption for the requested episode. Every successful request creates another consumption, so repeating the same request records a rewatch rather than updating an existing record. This operation is not idempotent; clients should deduplicate retries if they do not intend to record another viewing. The request body is optional and end_date defaults to the current timezone-aware time.

| Parameter | In | Required | Type | Description |
| --- | --- | --- | --- | --- |
| `media_type` | path | yes | MediaTypes |  |
| `source` | path | yes | Source |  |
| `media_id` | path | yes | string |  |
| `season_number` | path | yes | integer |  |
| `episode_number` | path | yes | integer |  |

Body (optional, JSON):

| Field | Type | Description |
| --- | --- | --- |
| `end_date` | string (date-time) | When the episode was watched. Defaults to the current time when omitted. |

Responses: `201` Created — `ConsumptionInfos`; `400` Bad Request — `ErrorResponse`; `403` Forbidden — `ErrorResponse`; `404` Episode Not Found — `ErrorResponse`; `500` Internal Server Error — `ErrorResponse`.

### GET `/api/v1/media/{media_type}/{source}/{media_id}/{season_number}/{episode_number}/history/{consumption_id}/`

Retrieve a specific consumption history record

| Parameter | In | Required | Type | Description |
| --- | --- | --- | --- | --- |
| `media_type` | path | yes | MediaTypes |  |
| `source` | path | yes | Source |  |
| `media_id` | path | yes | string |  |
| `season_number` | path | yes | integer |  |
| `episode_number` | path | yes | integer |  |
| `consumption_id` | path | yes | integer |  |

Responses: `200` OK — `ConsumptionInfos`; `400` Bad Request — `ErrorResponse`; `403` Forbidden — `ErrorResponse`; `404` Not Found — `ErrorResponse`; `500` Internal Server Error — `ErrorResponse`.

### PATCH `/api/v1/media/{media_type}/{source}/{media_id}/{season_number}/{episode_number}/history/{consumption_id}/`

Edit a specific consumption history record of a tracked episode

| Parameter | In | Required | Type | Description |
| --- | --- | --- | --- | --- |
| `media_type` | path | yes | MediaTypes |  |
| `source` | path | yes | Source |  |
| `media_id` | path | yes | string |  |
| `season_number` | path | yes | integer |  |
| `episode_number` | path | yes | integer |  |
| `consumption_id` | path | yes | integer |  |

Body (required, JSON):

| Field | Type | Description |
| --- | --- | --- |
| `end_date` | string (date-time), null |  |

Responses: `200` Updated — `ConsumptionInfos`; `400` Bad Request — `ErrorResponse`; `403` Forbidden — `ErrorResponse`; `404` Not Found — `ErrorResponse`; `500` Internal Server Error — `ErrorResponse`.

### DELETE `/api/v1/media/{media_type}/{source}/{media_id}/{season_number}/{episode_number}/history/{consumption_id}/`

Delete a specific consumption history record

| Parameter | In | Required | Type | Description |
| --- | --- | --- | --- | --- |
| `media_type` | path | yes | MediaTypes |  |
| `source` | path | yes | Source |  |
| `media_id` | path | yes | string |  |
| `season_number` | path | yes | integer |  |
| `episode_number` | path | yes | integer |  |
| `consumption_id` | path | yes | integer |  |

Responses: `204` No Content; `400` Bad Request — `ErrorResponse`; `403` Forbidden — `ErrorResponse`; `404` Not Found — `ErrorResponse`; `500` Internal Server Error — `ErrorResponse`.

### GET `/api/v1/media/{media_type}/{source}/{media_id}/{season_number}/{episode_number}/lists/`

List lists that the episode item belongs to

| Parameter | In | Required | Type | Description |
| --- | --- | --- | --- | --- |
| `media_type` | path | yes | MediaTypes |  |
| `source` | path | yes | Source |  |
| `media_id` | path | yes | string |  |
| `season_number` | path | yes | integer |  |
| `episode_number` | path | yes | integer |  |
| `offset` | query | no | integer | Offset for pagination (default: 0) |
| `sort` | query | no | SortOptions | Sort order for results |

Responses: `200` OK — `PaginatedLists`; `400` Bad Request — `ErrorResponse`; `403` Forbidden — `ErrorResponse`; `404` Not Found — `ErrorResponse`; `500` Internal Server Error — `ErrorResponse`.

### PUT `/api/v1/media/{media_type}/{source}/{media_id}/{season_number}/{episode_number}/lists/{list_id}`

Add the episode item to a specific list by list id

| Parameter | In | Required | Type | Description |
| --- | --- | --- | --- | --- |
| `media_type` | path | yes | MediaTypes |  |
| `source` | path | yes | Source |  |
| `media_id` | path | yes | string |  |
| `season_number` | path | yes | integer |  |
| `episode_number` | path | yes | integer |  |
| `list_id` | path | yes | integer |  |

Responses: `200` OK — `array of ListsMinimized`; `400` Bad Request — `ErrorResponse`; `403` Forbidden — `ErrorResponse`; `404` Not Found — `ErrorResponse`; `500` Internal Server Error — `ErrorResponse`.

### DELETE `/api/v1/media/{media_type}/{source}/{media_id}/{season_number}/{episode_number}/lists/{list_id}`

Remove the episode item from a specific list by list id

| Parameter | In | Required | Type | Description |
| --- | --- | --- | --- | --- |
| `media_type` | path | yes | MediaTypes |  |
| `source` | path | yes | Source |  |
| `media_id` | path | yes | string |  |
| `season_number` | path | yes | integer |  |
| `episode_number` | path | yes | integer |  |
| `list_id` | path | yes | integer |  |

Responses: `204` Removed; `400` Bad Request — `ErrorResponse`; `403` Forbidden — `ErrorResponse`; `404` Not Found — `ErrorResponse`; `500` Internal Server Error — `ErrorResponse`.

### POST `/api/v1/media/{media_type}/{source}/{media_id}/{season_number}/{episode_number}/sync/`

Sync season metadata from provider (non-manual sources). Redirects to the parent season sync.

| Parameter | In | Required | Type | Description |
| --- | --- | --- | --- | --- |
| `media_type` | path | yes | MediaTypes |  |
| `source` | path | yes | Source |  |
| `media_id` | path | yes | string |  |
| `season_number` | path | yes | integer |  |
| `episode_number` | path | yes | integer |  |

Responses: `202` Sync triggered; `400` Bad Request — `ErrorResponse`; `403` Forbidden — `ErrorResponse`; `404` Not Found — `ErrorResponse`; `429` Too Many Requests — `ErrorResponse`; `500` Internal Server Error — `ErrorResponse`.

### GET `/api/v1/search/{media_type}/`

Search for media items across supported providers

| Parameter | In | Required | Type | Description |
| --- | --- | --- | --- | --- |
| `media_type` | path | yes | MediaTypes | Media type to search for |
| `search` | query | yes | string | Search query string |
| `source` | query | no | Source | The specific source of the media type to query |
| `limit` | query | no | integer | Maximum number of items to return (default: 20) |
| `offset` | query | no | integer | Offset for pagination (default: 0) |

Responses: `200` OK — `PaginatedSearch`; `400` Bad Request — `ErrorResponse`; `403` Forbidden — `ErrorResponse`; `500` Internal Server Error — `ErrorResponse`.

### GET `/api/v1/statistics/`

Get statistics for the authenticated user

| Parameter | In | Required | Type | Description |
| --- | --- | --- | --- | --- |
| `end_date` | query | no | string (date) | Filter media ended before this date (YYYY-MM-DD) |
| `start_date` | query | no | string (date) | Filter media started after this date (YYYY-MM-DD) |

Responses: `200` OK — `StatisticsResponse`; `400` Bad Request — `ErrorResponse`; `403` Forbidden — `ErrorResponse`; `500` Internal Server Error — `ErrorResponse`.

