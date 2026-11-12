# Biztonsági megjegyzések (függőségek és reverse proxy)

[English](../security.md)

Ez az oldal a MediaTrail image-ben **ellenőrzött** állapotot rögzíti, nem csupán
a PyPI verziószámokra alapozott állításokat.

## Pillow és Brotli (ellenőrizve)

| Kockázat | Azonosító | MediaTrail image-szabály |
| --- | --- | --- |
| XBM ReDoS az `Image.open()`-ben | CVE-2026-112901 / GHSA-xgh8-jp6q-p5x8 | Csak **Pillow ≥ 13.0.0** javítja. A **12.3.0 érintett**. |
| Brotli dekóder OOB írás | CVE-2026-111497 | **Brotli 1.0.3–1.2.0** érintett. Javítás: **Brotli 1.2.1**. |

### Mit szállítanak a PyPI wheelök

Megnézett wheel-tartalom (CPython 3.12):

| Artefaktum | Beágyazott `libbrotlidec` |
| --- | --- |
| `pillow-12.3.0-…-musllinux_1_2_x86_64.whl` | `…so.1.2.0` (**sebezhető**) |
| `pillow-13.0.0-…-musllinux_1_2_x86_64.whl` | `…so.1.2.0` (**sebezhető**) |
| `pillow-13.0.0-…-manylinux_2_28_x86_64.whl` | `…so.1.2.0` (**sebezhető**) |

Tehát:

- A 12.3.0-n maradás nyitva hagyja a ReDoS-t, és továbbra is Brotli 1.2.0-t ágyaz be.
- A kész Pillow 13.0.0 wheel javítja a ReDoS-t, de **nem** zárja a CVE-2026-111497-et.
- Az Alpine **v3.23** `brotli` / `brotli-libs` csomagja **1.2.1-r0** (javított).
- Létezik nem hivatalos, patch-elt manylinux wheel; musl/Alpine build nincs, ezért
  ehhez az image-hez nem használjuk.

### Választott megoldás

A Docker **builder** szakaszban:

1. Alpine imaging build-függőségek, **`brotli-dev=1.2.1-r0`** pinnal.
2. `uv sync --locked --no-binary-package pillow` — a Pillow **13.x** a rendszer
   Brotli ellen fordul, nem a PyPI wheelből jön.
3. A **runtime** szakaszban ugyanarra a major Alpine ágra illeszkedő shared
   library-k, **`brotli-libs=1.2.1-r0`** pinnal (nincs lebegő `apk upgrade`).
4. A build futtatja a `scripts/verify_pillow_native.py` scriptet: elbukik, ha
   Pillow &lt; 13.0.0, ha van beágyazott Brotli 1.2.0, vagy ha a
   `BrotliDecoderVersion()` &lt; 1.2.1.

Amikor az upstream Pillow **13.1.0** (vagy újabb) wheelje már Brotli ≥ 1.2.1-et
ágyaz be, ugyanazzal a wheel-vizsgálattal lehet visszatérni a bináris wheelre.

## Egyéb függőségi frissítések (lockfile)

| Csomag | Lock cél | Megjegyzés |
| --- | --- | --- |
| Django | ≥ 5.2.17 (5.2.19) | CVE-2026-15307, 15337, 15830, 15920 |
| sqlparse | ≥ 0.6.0 (0.6.1) | CVE-2026-54284, 59893, 59894, 71491 |
| aiohttp | ≥ 3.14.1 (3.14.5) | 2026-os advisoryk a 3.14.x-ben |
| urllib3 | ≥ 2.8.0 (2.8.0) | Audit szerinti javítások |

## `apk upgrade` és reprodukálhatóság

A vak `apk upgrade --no-cache` **nem** kerül az image-be:

- Build időben az Alpine index összes telepített csomagját a pillanatnyi
  legújabbra húzza.
- Ugyanarra a Git commitra két build eltérő `openssl` / `sqlite-libs` /
  `pcre2` revíziókat kaphat.
- A CVE-zárás Gitből nem igazolható.

Helyette: pinelt base tag (`python:3.12-alpine3.23`), biztonsági csomagok
explicit `pkg=verzió` pinjei, és Trivy/Grype után csak az igazoltan érintett
Alpine csomagok felvétele. Széles `apk upgrade` tilos.

## Megbízható reverse proxy

A `TRUSTED_PROXIES` (IP/CIDR lista) csak beállítva engedi az nginxnek az
`X-Forwarded-For` alapú kliens-IP feloldást. Üresen a korábbi viselkedés marad.

## Nyitott kockázatok

- **Pillow 13.1.0 még nincs**: amíg a hivatalos wheel Brotli ≥ 1.2.1-et nem
  szállít, Alpine-on forrásból kell építeni a Pillow-t.
- **WOFF2**: a CVE-2026-111497 FreeType WOFF2 úton érhető el; a MediaTrail nem
  tölt szándékosan felhasználói fontot, de a sebezhető library másolatot így is
  eltávolítjuk.
- **Egyéb Alpine CVE-k** csak a buildelt image szkennelése + explicit pin után
  zárhatók; az `apk upgrade` nem megoldás.
- A táblázaton kívüli tranzitív Python advisorykat esetenként kell kezelni.
