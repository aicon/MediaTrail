# MediaTrail REST API Reference

MediaTrail provides a built-in REST API located under `/api/v1/`. It enables third-party developers, automation scripts, and scrobblers to query media libraries, record watches (including episode rewatches), manage custom lists, and update user progress.

---

## Overview & Interactive Documentation

- **Base URL:** `http(s)://<your-mediatrail-host>/api/v1/`
- **Interactive Swagger UI:** `/api/docs/`
- **Machine-readable OpenAPI Schema:** `/api/schema/`
- **Data Format:** JSON only (`Content-Type: application/json`)
- **Trailing Slashes:** Optional (`APPEND_SLASH` is enabled, meaning `/media` and `/media/` resolve to the same handler).

> **Note:** Both `/api/docs/` and `/api/schema/` require standard API authentication. Anonymous access is only permitted for `/api/v1/health/` and `/api/v1/info/`.

---

## Authentication

Every API call (except public health/info endpoints) requires a personal integration token.

### Getting Your Token
In the MediaTrail web interface, navigate to:
**Settings → Integrations → API Key / Token**

The token represents the logged-in user. Regenerating the key immediately invalidates the old token.

### Sending the Header
Authenticate requests using either of the following HTTP headers:

```http
Authorization: Bearer <your_token>
```
or
```http
X-API-Key: <your_token>
```

---

## Core Concepts

### 1. Media Types
- **Top-level Media:** `movie`, `tv`, `anime`, `manga`, `game`, `book`, `comic`, `boardgame`
- **Child Items (under TV):** `season`, `episode`

### 2. Metadata Sources (`source`)
- Provider sources require a string identifier (`media_id`):
  - `tmdb` (The Movie Database)
  - `mal` (MyAnimeList)
  - `igdb` (Internet Game Database)
  - `mangaupdates`
  - `openlibrary`
  - `hardcover`
  - `comicvine`
  - `bgg` (BoardGameGeek)
- `manual`: For custom, untracked items without provider IDs.

### 3. Status Values
Statuses are represented as integers:

| Value | Label | Description |
| :---: | :--- | :--- |
| **0** | Planning | Item added to watchlist or backlog |
| **1** | In progress | Currently watching / playing / reading |
| **2** | Paused | Temporarily put on hold |
| **3** | Completed | Finished viewing or playing |
| **4** | Dropped | Abandoned |

### 4. Writable Fields
Only certain fields can be updated depending on the media type:

| Media Type | Writable Fields |
| :--- | :--- |
| **movie** | `score`, `status`, `start_date`, `end_date`, `notes` |
| **tv**, **season** | `score`, `status`, `notes` |
| **episode** | `end_date` *(history records)* |
| **anime, manga, game, book, comic, boardgame** | `score`, `status`, `progress`, `start_date`, `end_date`, `notes` |

- **Scores:** Floats from `0.0` to `10.0` (one decimal point).
- **Dates:** ISO-8601 strings (`YYYY-MM-DD` or full datetime `YYYY-MM-DDTHH:MM:SSZ`).

---

## Request & Response Format

### Pagination
List endpoints return a standardized pagination envelope:

```json
{
  "pagination": {
    "total": 42,
    "limit": 20,
    "offset": 0,
    "next": "/api/v1/media/?limit=20&offset=20",
    "previous": null
  },
  "results": [ ... ]
}
```

- `limit`: Number of items per page (default: `20`, maximum: `200`).
- `offset`: Starting index (default: `0`).

### Error Format
When a request fails, MediaTrail returns a structured error response:

```json
{
  "detail": "Episode not found.",
  "errors": null
}
```
If input validation fails, the `errors` object contains field-level error messages.

---

## Practical Examples & Common Workflows

### 1. Search for Content Across Providers
Search for movies or shows to discover their `media_id`:

```http
GET /api/v1/search/tv/?search=Breaking+Bad HTTP/1.1
Authorization: Bearer <token>
```

---

### 2. Record an Episode Watch (Scrobble / Rewatch)
Creates a new watch entry in the episode history.

```http
POST /api/v1/media/tv/tmdb/1399/1/1/history/ HTTP/1.1
Authorization: Bearer <token>
Content-Type: application/json

{
  "end_date": "2026-03-24T20:15:00Z"
}
```

**Behavior Details:**
- **Non-Idempotent:** Calling this endpoint multiple times creates multiple watch entries (allowing full rewatch histories).
- **Optional Body:** If `end_date` is omitted or an empty body `{}` is passed, the completion timestamp defaults to the server's current time.
- **Auto-Provisioning:** If the parent season or show is not yet tracked, MediaTrail automatically provisions them in your library.
- **Catalog Validation:** Returns `404 Episode not found` if the provider does not list that season or episode number.

**Response (`201 Created`):**
```json
{
  "consumption_id": 412,
  "created": "2026-03-24T20:15:02Z",
  "score": null,
  "progress": 1,
  "progressed_at": "2026-03-24T20:15:02Z",
  "status": 3,
  "start_date": "2026-03-24T20:15:02Z",
  "end_date": "2026-03-24T20:15:00Z",
  "notes": ""
}
```

---

### 3. Track or Complete a Movie
Unlike episodes, a tracked movie maintains a single state row:

#### Add a movie as Completed:
```http
POST /api/v1/media/movie/ HTTP/1.1
Authorization: Bearer <token>
Content-Type: application/json

{
  "source": "tmdb",
  "media_id": "603",
  "status": 3,
  "score": 9.0,
  "end_date": "2026-03-24T22:30:00Z",
  "notes": "Rewatched in 4K."
}
```

#### Update an existing movie's rating or notes:
```http
PATCH /api/v1/media/movie/tmdb/603/ HTTP/1.1
Authorization: Bearer <token>
Content-Type: application/json

{
  "score": 9.5,
  "notes": "Even better on second thought."
}
```

---

### 4. Update Progress on Games, Books, or Anime
For items tracking fractional progress (e.g., page count, chapter, game hours):

```http
PATCH /api/v1/media/book/openlibrary/OL27479W/ HTTP/1.1
Authorization: Bearer <token>
Content-Type: application/json

{
  "status": 1,
  "progress": 150,
  "notes": "Currently at Chapter 8."
}
```

---

### 5. Trigger a Provider Metadata Refresh
To pull updated posters, release dates, or titles from the upstream provider:

```http
POST /api/v1/media/tv/tmdb/1399/sync/ HTTP/1.1
Authorization: Bearer <token>
```
*Returns `202 Accepted` when the background sync job is queued.*

---

## Endpoint Catalog Summary

### System & Information
- `GET /api/v1/health/` — System health status check (anonymous).
- `GET /api/v1/info/` — Server version, timezone, debug status (anonymous).
- `GET /api/v1/statistics/` — User statistics filtered by `start_date` and `end_date`.

### Search
- `GET /api/v1/search/{media_type}/` — Query providers by title (`?search=query&source=tmdb`).

### Tracking & Consumptions
- `GET /api/v1/media/` — List all tracked media for the user.
- `GET /api/v1/media/{media_type}/` — List items filtered by media type.
- `POST /api/v1/media/{media_type}/` — Create a tracked item (provider or manual).
- `GET /api/v1/media/{media_type}/{source}/{media_id}/` — Retrieve tracked item details.
- `PATCH /api/v1/media/{media_type}/{source}/{media_id}/` — Update the latest entry / state.
- `DELETE /api/v1/media/{media_type}/{source}/{media_id}/` — Remove media and all its history.
- `POST /api/v1/media/{media_type}/{source}/{media_id}/sync/` — Refresh metadata from provider.

### TV Shows, Seasons & Episodes
- `GET /api/v1/media/tv/{source}/{media_id}/seasons/` — List tracked seasons.
- `GET /api/v1/media/tv/{source}/{media_id}/{season}/episodes/` — List tracked episodes in season.
- `POST /api/v1/media/tv/{source}/{media_id}/{season}/{episode}/history/` — **Record an episode watch.**
- `GET /api/v1/media/tv/{source}/{media_id}/{season}/{episode}/history/` — List watch events for an episode.
- `PATCH /api/v1/media/tv/{source}/{media_id}/{season}/{episode}/history/{consumption_id}/` — Edit watch date.
- `DELETE /api/v1/media/tv/{source}/{media_id}/{season}/{episode}/history/{consumption_id}/` — Delete a single watch.

### Custom Lists
- `GET /api/v1/lists/` — List user custom lists.
- `POST /api/v1/lists/` — Create a custom list.
- `GET /api/v1/lists/{list_id}/` — Get list details.
- `PATCH /api/v1/lists/{list_id}/` — Update list title or description.
- `DELETE /api/v1/lists/{list_id}/` — Delete a list.
- `GET /api/v1/lists/{list_id}/items/` — List all items in a list.
- `DELETE /api/v1/lists/{list_id}/items/{item_id}/` — Remove item from list.

### Calendar
- `GET /api/v1/calendar/` — List scheduled release events for tracked items.
- `POST /api/v1/calendar/update/` — Trigger a calendar refresh job.

---

## Live playback vs. the Nuvio addon

Multi-device **Now Watching** from NuvioMobile-MT / NuvioTV-MT does **not** use this REST API. Companions install the built-in MediaTrail addon (`…/nuvio/<token>/manifest.json`) and call `/nuvio/<token>/player/…` with `deviceId` / `deviceName`. See [docs/now-watching.md](docs/now-watching.md).

Library mark watched / unwatched from the companion is a **separate** route: `POST /nuvio/watched.json` with `Authorization: Bearer <token>` (token never in the URL). Full contract: [docs/imports.md — Companion mark / unmark](docs/imports.md#companion-mark--unmark-post-nuviowatchedjson).

The REST endpoints under `/api/v1/playback/` are a token-authenticated preview for tools. `PUT` currently upserts the legacy device bucket (no per-device id in the body yet). A finished watch from the addon is recorded on `stop` at **90%** or more — not by these REST routes alone.

## Important Tips for Client Developers

1. **Deduplication:** Because `POST .../history/` always creates a new watch entry, external scrobblers must implement deduplication logic to avoid recording duplicates on network retries.
2. **Timezone Awareness:** All timestamps returned by the API include a UTC offset (`Z` suffix). Date inputs accept both UTC and timezone-aware ISO-8601 strings.
3. **Internal Package Name:** If inspecting low-level exceptions or error traces, note that the internal Python package name remains `yamtrack` for database compatibility.