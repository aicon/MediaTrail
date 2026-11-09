# Live playback / Now Watching

Fork feature for `aicon/Yamtrack` (`feature/live-playback-now-watching`).

## UX (Simkl-style)

Home strip:

- Blurred/darkened backdrop + left poster (poster and title both open the media/season page)
- Green **NOW WATCHING** or amber **PAUSED** badge + “Started … ago”
- Badge click queues remote **pause** / **resume** for Nuvio (via scrobbler poll) and flips the strip immediately
- Top-right **X** dismisses a stuck strip (`DELETE` live rows only — no history change; next player tick can recreate it while still playing)
- Movie: title + year
- Episode: series title + year, yellow **SxxExx**, episode title (not the series title)
- Large **NN% WATCHED**, **Nm LEFT**
- Soft translucent indigo elapsed wash + thinner bottom progress bar at the same percent
- Status badge keeps a 1px white border (strip border unchanged)
- HTMX poll every 10s (`/now-watching/`)

## Episode title sources (current + options)

**Current path (do not redesign metadata globally):**

1. Season episode list from TMDB via active `TMDB_LANG` (often `hu`) → `name` / `title` / `episode_title`
2. Dedicated TMDB episode endpoint (same language)
3. English fallback: one-off TMDB request with `language=en-US` when the HU (or other) name is a placeholder like `21. epizód` / `Episode 21`
4. Home strip hides remaining placeholders so only **SxxExx** shows when no real title exists

**Other already-reachable / future sources (not wired this round):**

| Source | Real HU titles? | Cost / limits |
|--------|-----------------|---------------|
| TMDB `en-US` (already used) | No (English), but real names | Free with existing TMDB key; +1 request when HU is placeholder |
| TMDB translations endpoint | Sometimes HU; often same placeholders for older shows | Extra TMDB call; still incomplete for 70s TV |
| TVDB | Often better English; HU inconsistent | Needs new API key + mapping TMDB↔TVDB; rate limits |
| Trakt episode titles | Mostly English | Needs OAuth/client; no reliable HU |
| OMDb | English only | Separate key; poor TV episode coverage |
| Manual / community (future) | Best HU quality | Product work; out of scope now |

For many classic series TMDB simply has no Hungarian episode names—English fallback is the practical fix until a dedicated title pipeline exists.

## Event mapping (scrobbler → Yamtrack)

| Client event | LivePlayback | History |
|--------------|--------------|---------|
| `start` / `progress` (position > 0) | `PUT /playback/` `watching` | — |
| `pause` | `PUT /playback/` `paused` (strip stays) | — |
| `start` with position 0 while row exists | no-op (keep last) | — |
| `stop` &lt; watched threshold | clear Now Watching first | **no** history |
| `stop` ≥ threshold | clear Now Watching, then history once | one row |
| repeated stop (dedupe) | clear again if leftover | **no** second history |
| back / exit player | client should send `stop` | — |

On every allowlisted `stop`, the scrobbler clears live playback **before** any history write: identity `DELETE /playback/`, then always `DELETE /playback/now/` so orphan movie rows cannot stick when identity resolution misses or completion write fails.

Clearing live playback never changes Episode/Movie history or tracked status.

Scrobbler: empty `YAMTRACK_ALLOWLIST` with `YAMTRACK_SINK=api` writes all titles (trial allowlist retired).

## Stale sessions

Missed player `stop` (e.g. back button while paused) must not leave the strip forever. Cleanup only deletes `LivePlayback`; history and tracked status are never touched.

| Status | Setting | Default | Why |
|--------|---------|---------|-----|
| `watching` | `LIVE_PLAYBACK_WATCHING_STALE_SECONDS` | **3 minutes** | Progress ticks should keep arriving; silence means an orphan play |
| `paused` | `LIVE_PLAYBACK_PAUSED_STALE_SECONDS` | **10 minutes** | Pause has no progress by design; short TTL would falsely clear a real pause |

`start` / `progress` refresh `updated_at` and set status back to `watching`. Ideal client behavior: send **`stop` on leaving the player** (back / exit) so the strip clears immediately; the TTLs are a safety net.

## Model

`LivePlayback`: `user`, `item` (movie|episode), `position_ms`, `duration_ms`, `status`, plus cached display fields `episode_title`, `year`, `poster_image`.

Percent = `floor(100 * clamp(position,0,duration) / duration)` when `duration_ms > 0`; otherwise no percent / no fill / no remaining.

## API

- `PUT /api/v1/playback/`
- `GET /api/v1/playback/`
- `GET /api/v1/playback/now/` → 204 if none
- `DELETE /api/v1/playback/` — clear one title without completing
- `DELETE /api/v1/playback/now/` — clear every live row for the user (movie leave fallback)

The home badge is status only. Playback stays under the player (Nuvio, Jellyfin, Stremio, and the rest); Yamtrack does not send pause or resume commands.

Dismiss uses simple clear (not a “hidden until next play” flag) so progress ticks stay honest.
