# MediaTrail

[🇭🇺 Magyar nyelvű leírás (README in Hungarian)](README_HU.md)

A self-hosted personal media tracker and digital logbook for everything you watch, read, and play.

[![Release](https://img.shields.io/badge/version-0.25.7-blue.svg)](https://github.com/aicon/MediaTrail/releases)
[![License: AGPL v3](https://img.shields.io/badge/License-AGPL_v3-green.svg)](LICENSE)
[![Docker Image](https://img.shields.io/badge/docker-ghcr.io%2Faicon%2Fmediatrail-blue?logo=docker)](https://github.com/aicon/MediaTrail/pkgs/container/mediatrail)
[![Documentation](https://img.shields.io/badge/docs-mediatrail--docs-brightgreen.svg)](https://aicon.github.io/mediatrail-docs/)
[![Support on Ko-fi](https://img.shields.io/badge/Ko--fi-Support-ff5e5b?logo=ko-fi)](https://ko-fi.com/aiconwg)

---

MediaTrail is an independent, self-hosted web application to track movies, TV shows, seasons, episodes, anime, manga, video games, books, comics, and board games in one place. Organize your library, log dates, assign ratings, track your progress, build custom lists, and explore your personal viewing statistics.

MediaTrail originates as an independent fork of [Yamtrack](https://github.com/FuzzyGrim/Yamtrack), adding essential capabilities such as an integrated REST API, rich episode watch histories, live playback status, Nuvio integration, and native Hungarian localization.

---

## Features

- **All-in-One Tracker:** Movies, TV shows, anime, manga, books, comic books, video games, and board games.
- **Now Watching:** Real-time playback status widget on the dashboard displaying your current progress, elapsed time, and time remaining.
- **Detailed Episode History:** Multiple watch records per episode with individual dates and custom notes. Independent tracking for movies and TV series.
- **REST API (Preview):** Full REST API at `/api/v1/`, OpenAPI schema at `/api/schema/`, and interactive Swagger documentation at `/api/docs/`. Written reference: [API.md](API.md) ([magyar](API_HU.md)).
- **Nuvio Integration:** Two-way sync / import directly from your Nuvio profile. Supports both *Import Missing* and *Update Existing* modes with encrypted credentials and scheduled background sync.
- **Multi-Language UI:** Seamless switching between English and Hungarian per account. Metadata from TMDB stays in your preferred language via `TMDB_LANG`.
- **All-in-One Deployment:** Embedded Redis engine inside the image—no extra container needed. All data lives neatly in a single mounted volume.
- **Universal Import:** Built-in imports from Trakt, SIMKL, MyAnimeList (MAL), and others.

---

## Preview: Now Watching

MediaTrail features a live "Now Watching" banner on your home dashboard that updates in real time as you watch:

![Now Watching Banner](docs/screenshots/now-watching-desktop.png)

*(Also available in a compact format for responsive dashboards)*

![Now Watching Compact](docs/screenshots/now-watching-narrow.png)

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
| **[MediaTrail-Scrobbler](https://github.com/aicon/MediaTrail-Scrobbler)** | Background service that scrobbles Nuvio playback events to MediaTrail. (`ghcr.io/aicon/mediatrail-scrobbler`) |
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