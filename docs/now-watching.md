# Live playback / Now Watching

Multi-device Now Watching for MediaTrail (`aicon/MediaTrail`). Companion apps report Stremio `player` events to the **built-in MediaTrail addon** (`/nuvio/…`). No separate MediaTrail-Scrobbler container.

## UX

Home page: one strip per device that is currently playing or paused.

- Blurred/darkened backdrop + left poster (poster and title open the media/season page)
- Green **NOW WATCHING** or amber **PAUSED** badge + “Started … ago”
- Device label on the strip (automatic or renamed)
- Top-right **X** dismisses **that device’s** strip only (`DELETE` live row — no history change; the next player tick can recreate it while still playing)
- Movie: title + year
- Episode: series title + year, yellow **SxxExx**, episode title (not the series title)
- Large **NN% WATCHED**, **Nm LEFT**
- Soft translucent indigo elapsed wash + thinner bottom progress bar at the same percent
- HTMX poll every 10s (`/now-watching/`)

**Rename:** the strip name field posts to `/now-watching/rename/` with `device_id` + `custom_name`. Empty name clears the override and falls back to the automatic label. Custom names live in `DeviceDisplayName` and survive stop / dismiss.

The status badge is display only. MediaTrail does not send pause or resume commands to the player.

## Multi-device model

| Concept | Behaviour |
|---------|-----------|
| Identity | Unique `(user, device_id)` on `LivePlayback` |
| Client fields | `deviceId` (stable UUID per install) + `deviceName` (e.g. `telefon · Pixel 8`, `TV · Shield`) |
| Missing id | Falls back to `LEGACY_DEVICE_ID` (`legacy`) / “Ismeretlen eszköz” |
| Pause / stop | Only that `device_id` |
| Dismiss | Optional `device_id`; omit to clear every strip for the user |
| Same title, two devices | Two strips |
| One device, title switch | Updates that device’s single row |

## Companion setup

1. MediaTrail → Settings → Integrations → Nuvio → copy the addon address (`…/nuvio/<account-token>/manifest.json`). The token is personal to that MediaTrail account.
2. In each NuvioMobile-MT / NuvioTV-MT install: Settings → Addons → add that address; remove any old scrobbler URL or an untokened `/nuvio/manifest.json` URL.
3. Play a title. Each device appears as its own strip for **that** MediaTrail account only. Rename on the home page if you want friendlier labels.

With several MediaTrail users, each person must install **their own** Integrations URL. A legacy untokened `/nuvio/…` path is ignored when more than one account exists.

## Event mapping (Nuvio addon → MediaTrail)

| Client event | LivePlayback | History |
|--------------|--------------|---------|
| `start` / `progress` (position > 0) | upsert that device as `watching` | — |
| `pause` | upsert that device as `paused` (strip stays) | — |
| `start` with position 0 while row exists | no-op (keep last position) | — |
| `stop` &lt; 90% watched | clear that device’s strip | **no** history |
| `stop` ≥ 90% | clear that device’s strip, then history once | one row |
| repeated stop (dedupe) | clear again if leftover | **no** second history |
| seek | client should emit `progress` so the strip updates | — |
| back / exit player | client should send `stop` | — |

Watched threshold: **90%** (`WATCHED_THRESHOLD = 0.9`). Clearing live playback never changes Episode/Movie history or tracked status.

Nuvio **watch-history import / two-way interactive sync** is separate (Settings → Import and Settings → Integrations → Nuvio). That path updates movie/episode history; it must not wipe per-device Now Watching strips. Details: [Imports → Nuvio](imports.md#nuvio).

## Stale sessions

Missed player `stop` must not leave a strip forever. Cleanup only deletes `LivePlayback`.

| Status | Setting | Default | Why |
|--------|---------|---------|-----|
| `watching` | `LIVE_PLAYBACK_WATCHING_STALE_SECONDS` | **3 minutes** | Progress ticks should keep arriving |
| `paused` | `LIVE_PLAYBACK_PAUSED_STALE_SECONDS` | **10 minutes** | Pause has no progress by design |

`start` / `progress` refresh `updated_at` and set status back to `watching`. Ideal clients send **`stop` on leaving the player**.

## Models

- `LivePlayback`: `user`, `device_id`, `device_label`, `item` (movie\|episode), `position_ms`, `duration_ms`, `status`, plus cached `episode_title`, `year`, `poster_image`. Unique on `(user, device_id)`.
- `DeviceDisplayName`: `user`, `device_id`, `custom_name` — optional rename override.

Percent = `floor(100 * clamp(position,0,duration) / duration)` when `duration_ms > 0`.

## HTTP surfaces

**Home strip order:** first-seen (`created_at`), not last progress tick — updating one device does not jump its strip to the top.

**Built-in addon (companions):**

- `GET /nuvio/<token>/manifest.json`
- `GET /nuvio/<token>/player/{type}/{id}/{extra}.json` — query/extra carries `action`, `currentTime`, `duration`, `deviceId`, `deviceName`
- Legacy untokened `/nuvio/manifest.json` and `/nuvio/player/…` only work when the site has exactly one account

Library mark watched / unwatched from the companion is a **separate** Bearer endpoint (`POST /nuvio/watched.json`) — do not use the player route for that. See [Imports → Companion mark / unmark](imports.md#companion-mark--unmark-post-nuviowatchedjson).

**Home (session user):**

- `GET /now-watching/` — partial for HTMX
- `POST /now-watching/dismiss/` — body `device_id` (optional)
- `POST /now-watching/rename/` — body `device_id`, `custom_name`

**REST preview (token auth; not what the companion apps use):**

- `PUT /api/v1/playback/` — upsert; currently lands in the legacy device bucket (no `deviceId` in the request body yet)
- `GET /api/v1/playback/` — list live rows for the user
- `GET /api/v1/playback/now/` → latest row, or 204 if none
- `DELETE /api/v1/playback/` — clear one title without completing
- `DELETE /api/v1/playback/now/` — clear every live row for the user

For multi-device Now Watching, prefer the built-in `/nuvio/…` addon path above.

## Episode title sources

1. Season episode list from TMDB via active `TMDB_LANG` → `name` / `title` / `episode_title`
2. Dedicated TMDB episode endpoint (same language)
3. English fallback (`language=en-US`) when the local name is a placeholder like `21. epizód` / `Episode 21`
4. Home strip hides remaining placeholders so only **SxxExx** shows when no real title exists

For many classic series TMDB has no Hungarian episode names—English fallback is the practical fix until a dedicated title pipeline exists.
