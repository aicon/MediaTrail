# MediaTrail

[🇭🇺 Magyar nyelvű leírás (README in Hungarian)](README_HU.md)

A self-hosted personal media tracker and digital logbook for everything you watch, read, and play.

[![Release](https://img.shields.io/badge/version-0.25.21-blue.svg)](https://github.com/aicon/MediaTrail/releases)
[![License: AGPL v3](https://img.shields.io/badge/License-AGPL_v3-green.svg)](LICENSE)
[![Docker Image](https://img.shields.io/badge/docker-ghcr.io%2Faicon%2Fmediatrail-blue?logo=docker)](https://github.com/aicon/MediaTrail/pkgs/container/mediatrail)
[![Documentation](https://img.shields.io/badge/docs-mediatrail--docs-brightgreen.svg)](https://aicon.github.io/mediatrail-docs/)
[![Support on Ko-fi](https://img.shields.io/badge/Ko--fi-Support-ff5e5b?logo=ko-fi)](https://ko-fi.com/aiconwg)

---

MediaTrail is an independent, self-hosted web application to track movies, TV shows, seasons, episodes, anime, manga, video games, books, comics, and board games in one place. Organize your library, log dates, assign ratings, track your progress, build custom lists, and explore your personal viewing statistics.

MediaTrail originates as an independent fork of [Yamtrack](https://github.com/FuzzyGrim/Yamtrack), adding essential capabilities such as an integrated REST API, rich episode watch histories, live playback status, Nuvio integration, and native Hungarian localization.

---

## Features

- **A record for every title:** Movies, TV shows, anime, manga, video games, books, comics, and board games. Save a score, status, and progress, count repeats, set start and end dates, and write a note.
- **Seasons, and every time you watched:** Follow each season on its own. An episode can keep several watch records, each with its own date and note. Movies and series stay separate.
- **A history of the changes:** The log keeps the steps themselves: when you added a title, when you started it, and when you watched or read it again.
- **Titles the catalogs do not have:** Add a custom entry when none of the supported sources lists it.
- **Lists with other people:** Build a personal list for any purpose and add other accounts as collaborators.
- **Upcoming releases:** A calendar of what is coming up, plus an iCalendar (`.ics`) link for other calendar apps. Release notices can go out through Apprise (Discord, Telegram, ntfy, Slack, email, and others).
- **Separate accounts:** Each person has their own library. Sign-in can stay on MediaTrail, or use OIDC and social providers such as Google, GitHub, and Discord through django-allauth.
- **English and Hungarian:** The interface language is chosen per account. TMDB titles follow `TMDB_LANG`.
- **Imports, including Nuvio:** Nuvio can add only new items or refresh items you already track, with encrypted credentials and a schedule. Trakt, SIMKL, MyAnimeList, AniList, and Kitsu can run on a schedule too. A free Trakt account can connect only two applications to the API. Private import can keep the current Trakt login or use the new device-code API (`TRAKT_API_PKCE`). Export the library to CSV and import that file back, or bring in IMDb, Goodreads, Steam, and HowLongToBeat lists.
- **Playback, including Nuvio:** The home page shows a live Now Watching banner with position, elapsed time, and time remaining when a [Nuvio companion app](#companion-apps) reports what is playing. Jellyfin, Plex, and Emby can mark newly watched media on their own.
- **REST API (Preview):** Full REST API at `/api/v1/`, OpenAPI schema at `/api/schema/`, and interactive Swagger documentation at `/api/docs/`. Written reference: [API.md](API.md) ([magyar](API_HU.md)).
- **One container:** Docker Compose, with SQLite or PostgreSQL. Redis runs inside the image, and all data stays in a single mounted folder.

---

## Preview: Now Watching

MediaTrail features a live "Now Watching" banner on your home dashboard that updates in real time as you watch:

![Now Watching Banner](docs/screenshots/now-watching-desktop.png)

*(Also available in a compact format for responsive dashboards)*

![Now Watching Compact](docs/screenshots/now-watching-narrow.png)

The banner sits at the top of the home page, above the library:

![Now Watching on the home page](docs/screenshots/now-watching-desktop2.png)

> **Note:** Now Watching needs a [Companion App](#companion-apps). The banner appears when that app reports what is playing.

---

## Quick Start

MediaTrail is distributed as a lightweight, pre-configured Docker container with internal Redis support.

### Docker Compose

Create a `docker-compose.yml` file:

```yaml
services:
  mediatrail:
    image: ghcr.io/aicon/mediatrail:latest
    container_name: mediatrail
    restart: unless-stopped
    ports:
      - "8000:8000"
    environment:
      SECRET: longstring
      TMDB_LANG: en
      TMDB_API:
      TVDB_API:
      URLS:
      ADMIN_ENABLED: false
      REGISTRATION: false
    volumes:
      - ./db:/mediatrail/db
```

### Update the environment values

Open the Compose file and replace the example secret:

```text
SECRET=longstring
```

Use a long random value for `SECRET`. If you are running MediaTrail behind a reverse proxy, also set `URLS` to the public origin:

```text
URLS=https://mediatrail.example.com
```

The URL must include the protocol (`https` or `http`) and should not include a trailing slash or application path. Multiple origins can be separated with commas.

For the full list of supported settings, see [Runtime](https://aicon.github.io/mediatrail-docs/runtime/).

Start the container:

```bash
docker compose up -d
```

Open your browser at `http://localhost:8000`.

> **Note on Upgrading from Yamtrack:**  
> The internal storage path in MediaTrail is `/mediatrail/db` (replacing Yamtrack's old `/yamtrack/db`). Simply map your existing directory to `./db:/mediatrail/db`.

---

## MediaTrail vs. Yamtrack

MediaTrail is an independent, unofficial fork and is **not affiliated with, maintained by, or endorsed by upstream Yamtrack**.

### Background
MediaTrail diverged from Yamtrack `dev` post-`v0.25.3` (specifically the July 12, 2026 tabbed detail view), incorporating PR `#1378` (REST API preview) and PR `#1608` (Episode history).

When upstream Yamtrack adopted the `0.26` architecture, MediaTrail intentionally remained on the `0.25.x` foundation to prioritize stability, self-contained deployment, and specific integrations. Upstream changes such as the rewritten log page, statistical reworks, and Trakt zip imports were deliberately omitted.

| Feature | Upstream Yamtrack (Stable) | MediaTrail |
| :--- | :---: | :---: |
| **REST API** (`/api/v1/`) | No | Yes |
| **Multi-record Episode History** | No | Yes |
| **Live "Now Watching" Banner** | No | Yes |
| **Nuvio Sync / Import** | No | Yes |
| **Hungarian Localization** | No | Yes |
| **Embedded Redis Container** | No *(Requires separate Redis)* | Yes *(Included in image)* |
| **Internal Python Package** | `yamtrack` | `yamtrack` *(kept for compatibility)* |

---

## Companion Apps

MediaTrail connects with dedicated companion applications to automatically scrobble your viewing activity:

| Project | Description |
| :--- | :--- |
| **[NuvioTV-MT](https://github.com/aicon/NuvioTV-MT)** | Dedicated Android TV build with native MediaTrail scrobbler integration. |
| **[NuvioMobile-MT](https://github.com/aicon/NuvioMobile-MT)** | Dedicated mobile client build with MediaTrail support. |

---

## Documentation

Comprehensive user guides, installation steps, and configuration examples are hosted in the official documentation repository:

- **Manual:** [https://aicon.github.io/mediatrail-docs/](https://aicon.github.io/mediatrail-docs/)
- **API reference:** [API.md](API.md) · [API_HU.md](API_HU.md)

Documentation chapters: *Installation, Library, Imports (including Nuvio), Environment Configuration, Accounts, and Maintenance.*

---

## Support

If you enjoy MediaTrail and want to support its maintenance and ongoing development:

[![Buy Me a Coffee](https://img.shields.io/badge/Ko--fi-Buy%20me%20a%20coffee-ff5e5b?style=for-the-badge&logo=ko-fi)](https://ko-fi.com/aiconwg)


---

## License & AGPL Compliance

MediaTrail is licensed under the **GNU Affero General Public License v3.0 (AGPL-3.0)**.  
Yamtrack's original copyright notices are preserved. MediaTrail's copyright declarations are recorded in `NOTICE`.

### Network Use Notice (AGPL-3.0 Section 13)
Because this is modified network software, AGPL-3.0 Section 13 requires a prominent offer of the corresponding source code of the exact version being executed:
- Set `MEDIATRAIL_SOURCE_URL` to the public HTTP(S) URL of your source repository or release package before exposing the instance over a network.
- This variable may be left empty for private local installations.