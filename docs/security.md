# Security notes (dependencies and reverse proxy)

[Magyar változat](hu/security.md)

Verified against built images, not PyPI version numbers alone.

## Status (split)

### Closed — image dependencies / Trivy (`f75f118`)

- Commit: `f75f118`
- Workflow: https://github.com/aicon/MediaTrail/actions/runs/43251480942
- Image digest: `ghcr.io/aicon/mediatrail@sha256:b2578814843384541a8cb219c5f8d04c1c9ca4007b183e2efaf9284716573545`
- Image ID (config): `sha256:0b6f8ebe19f8ae664334cf463fa5139a5d55ba837d21c1b2e1e459a10bad2e6e`
- Build gate: `verify_pillow_native: OK` (in image build log)
- Trivy (`--severity CRITICAL,HIGH,MEDIUM,LOW`, `--scanners vuln`): **0 findings**
- Runtime inventory on that digest: **no `pip`**; `djangorestframework==3.18.3`,
  `pillow==13.0.0`, `soupsieve==4.1` from the locked venv

### Closed — targeted OAuth / lock tests

`SimklOAuthViewTests` 13/13, `TraktOAuthViewTests` 11/11,
`LockedDependencyInstallTests` 4/4 (28/28). These do **not** cover SoupSieve /
BeautifulSoup import paths.

### Closed — SoupSieve 4.1 / BeautifulSoup import paths

Dedicated pass under local `soupsieve==4.1` / `beautifulsoup4==4.14.3` (not
covered by the 28 OAuth/lock tests):

- `Metadata::test_book`, `test_comic`, `test_openlibrary_publish_date_with_abbreviated_month`
- `Search::test_books`, `test_comics`
- `ServicesTests` comicvine/openlibrary metadata + search (4)
- CSS/`get_text` smoke against soupsieve 4.1

**9/9** nodeids + smoke OK. A broader `-k book|comic` run also hit an unrelated
Hardcover genre-label assertion failure (`Fiction` vs API `Literary Fiction`);
that path does not use BeautifulSoup. Full suite remains a separate question.

### Open — deployment settings (Compose / proxy audit)

Checked against **shipped** `docker-compose*.yml` + `nginx.conf` in this repo.
No live production Compose/env with real host values was present on the audit
machine, so operator confirmation is still required for the running host.

| Check | Evidence in repo templates | Implication |
| --- | --- | --- |
| TLS termination | `nginx.conf` `listen 8000` only; no `ssl_certificate` / `:443` | MediaTrail **does not** terminate TLS. HTTPS must be terminated by an **upstream** reverse proxy (or clients use plain HTTP on `:8000`). |
| `X-Forwarded-Proto` | `nginx.conf` sets `proxy_set_header X-Forwarded-Proto $http_x_forwarded_proto` | Inside the container nginx **forwards** the incoming proto header to Gunicorn; it does not set `$scheme` from a local TLS listener. Correct only when a trusted upstream sets that header. |
| `TRUSTED_PROXIES` | **Absent** from `docker-compose.yml`, `docker-compose.local.yml`, `docker-compose.postgres.yml` | Default deploys leave real-ip **unset** → no `set_real_ip_from`. Behind a reverse proxy, set `TRUSTED_PROXIES` to that proxy’s IP/CIDR (and set `URLS`). |
| `URLS` | Documented in README / `docs/install.md`; empty in Compose examples | Required for public HTTPS origin / OAuth redirects when proxied. |
| `SECRET` | Compose placeholders: `replace-with-a-long-random-string` / `change-me` (not the Django code default) | Templates force an env override shape, but **this audit could not read a production env** to prove the live value ≠ placeholder and ≠ `settings.py` default. |

**Still need from the live host:** the actual Compose (or orchestrator env) showing `SECRET`/`SECRET_FILE`, `URLS`, `TRUSTED_PROXIES`, and where TLS is terminated (e.g. Caddy/Traefik/nginx in front).

## Supported dependency install (reproducible)

MediaTrail does **not** ship or support a root `requirements.txt`. The only
supported paths:

| Path | Command |
| --- | --- |
| Runtime image | `Dockerfile` → `uv sync --locked --no-binary-package pillow` |
| Local / CI Python env | `uv sync --locked` (add `--group test` / `--group dev` as needed) |
| Lock freshness | `uv lock --check` (pre-commit) |

Reproduce a local env matching the image Python deps:

```bash
uv sync --locked
```

Pillow in the **image** is still built from sdist against Alpine Brotli 1.2.1
(`--no-binary-package pillow` + `scripts/verify_pillow_native.py`). A plain
local `uv sync` may install a PyPI wheel and is not a substitute for that gate.

Final locked pins of note (from `uv.lock`): `PyJWT==2.15.1`, `multidict==7.2.1`,
`apprise==1.11.0`, `djangorestframework==3.18.3`, `drf-spectacular==0.28.0`,
`pillow==13.0.0`, `soupsieve==4.1`. Alpine pins in the Dockerfile:
`zlib=1.4-r0`, `brotli-libs=1.2.1-r0`, `krb5-libs=1.22.3-r0`.

## Pillow and Brotli

| Risk | ID | Status |
| --- | --- | --- |
| XBM ReDoS | CVE-2026-112901 | Fixed via Pillow ≥ 13.0.0 source build |
| Brotli OOB | CVE-2026-111497 | Fixed via Alpine `brotli-libs=1.2.1-r0` (not PyPI wheel libs) |

PyPI musllinux/manylinux wheels for Pillow 12.3.0 and 13.0.0 still embed Brotli
1.2.0. MediaTrail keeps building Pillow from source until official wheels ship
Brotli ≥ 1.2.1.

## Closed Trivy findings (trail)

### Was HIGH/CRITICAL on `3a081e4`

- Alpine: 16 × `krb5-libs` `1.22.1-r0` → pinned **`1.22.3-r0`**
- Python: PyJWT, certifi, cryptography, djangorestframework, dnspython,
  oauthlib (via django-allauth 65.22), soupsieve — bumped in lock / Dockerfile

### Was MEDIUM/LOW on `26af91a`

| Item | Resolution |
| --- | --- |
| zlib `1.3.2-r1` (CVE-2026-4738) | Pinned **`zlib=1.4-r0`** / `zlib-dev=1.4-r0` |
| PyJWT `2.14.0` MEDIUM | Locked **`PyJWT~=2.15.0`** (2.15.1) |
| multidict `6.7.1` | Locked **`multidict>=6.9.1`** (7.2.1) |
| soupsieve `2.8.4` MEDIUM | Locked **`soupsieve>=2.9.0`** (4.1) |
| apprise `1.9.9` LOW | Locked **`apprise~=1.11.0`** (compatible minor bump) |
| pip `25.0.1` (base image) | **Removed** from runtime (`/usr/local/.../pip*`); app does not need pip |

## `apk` policy

No blanket `apk upgrade`. Security-relevant OS packages are version-pinned
(`brotli-libs`, `krb5-libs`, `zlib`, …).

## Trusted reverse proxies

`TRUSTED_PROXIES` (comma-separated IPs/CIDRs) configures nginx
`set_real_ip_from` + `real_ip_header X-Forwarded-For` only when set. The
entrypoint validator uses an ash-safe character class (no bare `"` inside
`[!…]`, which broke BusyBox with `unexpected word (expecting ")")`).

## Residual notes (not open CVEs)

- Pillow remains a **source build** until upstream wheels embed Brotli ≥ 1.2.1.
- `django-allauth` is on **65.22** (needed for oauthlib 4); smoke-test SSO if used.
- Future Trivy hits on a newer base image need a new pin + rescan before claiming
  closure again.

## Open deployment checks (not closed by this image scan)

See **Status → Open — deployment settings** above. Summary: container nginx is
HTTP-only on `:8000` and forwards `X-Forwarded-Proto`; Compose templates omit
`TRUSTED_PROXIES`; `SECRET` must be confirmed on the live host (templates are
placeholders only).
