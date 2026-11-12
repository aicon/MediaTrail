# Imports

[Magyar változat](hu/imports.md)

Settings, then Import, is where an outside history becomes library rows. Two choices at the top apply to every source:

- **Only new items** adds what is missing locally and leaves existing rows alone.
- **New items and overwrite** also updates the watch date of a row that is already there. Scores and notes stay. Nothing is deleted.

Frequency is once, or a repeat from the clock time you pick. A repeat keeps running until you remove it from Active periodic imports. File uploads cannot be repeated. A username or a saved sign-in can.

The history list below the sources shows the last seven days. A task that says it has started is still in progress. A finished task can still list rows it skipped.

## Nuvio

Nuvio is the first source. It reads movies and episodes from one Nuvio profile. Optional **two-way interactive watch-history sync** is configured under Settings → Integrations → Nuvio (see below). Live **Now Watching** from the companion apps is a separate path: the built-in MediaTrail addon receives `player` events with a per-device id. History import and watch-history sync do not replace those device strips. See [Library](library.md) and [Live playback / Now Watching](LIVE_PLAYBACK_NOW_WATCHING.md).

Credentials, cursor, and imported rows belong to the signed-in MediaTrail user only (`NuvioAccount` is one per account). Another MediaTrail user on the same site keeps a separate Nuvio login and library.

The form asks for the Nuvio email, the password, and the profile number. The first successful submit stores them encrypted on your MediaTrail account. The next time you open the page, the email and the profile are filled in. Leave the password blank to keep the saved one. Type a new password only when you want to replace it. A different email or a different profile starts that account's import cursor over.

What a run does:

- A movie that is not in the library is added as completed, with the Nuvio watch time.
- An episode that is not in the library is added the same way. The season and the show are created if they are missing.
- In "only new items", a movie or episode that is already there is left as it is, including a date you edited.
- In overwrite, the existing movie, or the latest row of that episode, gets the Nuvio watch time. The rest of the row stays.
- If you remove an episode in MediaTrail and Nuvio still has that watch, the next import adds it again. "Only new items" means missing locally, even when that Nuvio event was imported before.
- A series row that has no season number or no episode number is skipped and remembered, so later runs do not keep reporting it.
- A delete event from Nuvio is ignored unless **Sync mark-unwatched** is on (see two-way sync below).

The profile number is the Nuvio profile, not a MediaTrail user. Most people have one profile, numbered 1.

### Two-way interactive sync

This mirrors Jellyfin-style mark played / mark unplayed between Nuvio Cloud watch history and MediaTrail movie/episode rows. It is **not** remote pause or Now Watching scrobble.

Turn it on under **Settings → Integrations → Nuvio**:

| Toggle | Nuvio → MediaTrail | MediaTrail → Nuvio |
| --- | --- | --- |
| **Sync mark-watched** | Upserts from history import and from the watched-history delta | Queues `sync_push_watched_items` when you mark something watched |
| **Sync mark-unwatched** | Applies delta deletes, and after a full successful history snapshot can remove local watches that Nuvio no longer has | Queues `sync_delete_watched_items` (and matching watch-progress keys) when you mark unwatched or delete history |

With either toggle on, MediaTrail polls the Nuvio delta about every **30 seconds** in the background, and runs a full history snapshot reconcile about every **15 minutes**. Saving the toggles also queues an immediate delta pull. Only one sync runs per account at a time (overlapping polls are skipped). You still need one successful manual Import → Nuvio first (so the account is bootstrapped); after that, interactive mark/unmark should appear without starting Import by hand.

First import captures the Nuvio delta cursor **before** the history snapshot, then applies delta events after that tip. That matches Nuvio’s bootstrap order so watches that change while snapshot pages download are not missed by both the snapshot and the later cursor.

Safety rules for unwatched / snapshot reconcile:

- Content ids are normalized to TMDB watch keys before compare (`tmdb:…` and IMDb `tt…` for the same title count as one item).
- Snapshot reconcile runs only after every history page was fetched and every row that should map to TMDB did. A mid-import API or apply failure does not start deletes.
- Only watches previously recorded from Nuvio sync are eligible for snapshot removal. Watches from Trakt, manual entry, or other sources stay.
- The saved delta cursor advances only when every event in that run applied successfully. On failure the cursor stays put so the next run retries the batch (at-least-once; upsert and delete are idempotent).
- The stored Nuvio watch-key set updates only after that full successful import path finishes.

## Other sources

These sources use the same mode and frequency controls.

| Source | What you provide | Notes |
| --- | --- | --- |
| Trakt | A public username, private API login (browser PKCE on `auth.trakt.tv`, or device code), or a website export ZIP | Private login needs `TRAKT_API_PKCE` (modern Trakt app, no secret). Device code stays available for TVs and limited-input devices. The ZIP comes from Trakt → Settings → Export (max 50 MB). Corrupt or empty archives are rejected before the import starts. “Only new items” skips titles you already have. |
| Simkl | A connect button | Needs operator keys: register a **new** AUTH V2 app at [simkl.com/settings/developer](https://simkl.com/settings/developer/) (V1 ids cannot upgrade). Prefer **Server apps & services**, set `SIMKL_V2_ID` / `SIMKL_V2_SECRET`, redirect `{URLS}/import/simkl_private`. Step-by-step: [Runtime → Simkl AUTH V2](runtime.md#simkl-auth-v2-get-keys-and-connect). Existing V1 tokens work until ~April 2027; reconnect after enabling V2. |
| MyAnimeList | A public username | |
| AniList | A public username, or a connect button | A private profile needs your own AniList application. |
| Kitsu | The numeric user id from the profile address | |
| Steam | The 64-bit Steam id | The profile has to be public unless the Steam key belongs to that account. |
| MediaTrail backup | A CSV file from Settings, then Export | One-time only. |
| HowLongToBeat | A CSV export | One-time only. Games. |
| IMDb | A ratings CSV | One-time only. |
| Goodreads | A library export | One-time only. Books. |

Matching uses the catalog ids MediaTrail already stores. A title the catalog does not know is reported on the finished task and is not invented.

## Players

Jellyfin, Plex, and Emby can tell MediaTrail about playback through a webhook. Settings, then Integrations, shows the address for each player. The address includes your token. The page itself lists the clicks for that player. Regenerating the token changes the address.
