# Biztonsági megjegyzések (függőségek és reverse proxy)

[English](../security.md)

Az ellenőrzés a buildelt image-en történik, nem csupán a PyPI verziószámokon.

## Állapot: biztonsági kör lezárva (`f75f118`)

Ellenőrzött runtime artifact:

- Commit: `f75f118`
- Workflow: https://github.com/aicon/MediaTrail/actions/runs/43251480942
- Image digest: `ghcr.io/aicon/mediatrail@sha256:b2578814843384541a8cb219c5f8d04c1c9ca4007b183e2efaf9284716573545`
- Build gate: `verify_pillow_native: OK`
- Trivy (CRITICAL+HIGH+MEDIUM+LOW, vuln): **0 találat**; runtime: **nincs pip**; DRF 3.18.3 / Pillow 13.0.0 a lockból

Célzott tesztek push előtt: Simkl 13/13, Trakt OAuth 11/11, lock tesztek 4/4.
A teljes suite ebben a körben nem futott végig.

## Támogatott telepítés (reprodukálható)

Nincs támogatott gyökér `requirements.txt`. Hivatalos útvonalak:

| Útvonal | Parancs |
| --- | --- |
| Runtime image | `Dockerfile` → `uv sync --locked --no-binary-package pillow` |
| Helyi / CI Python | `uv sync --locked` (szükség szerint `--group test` / `dev`) |
| Lock ellenőrzés | `uv lock --check` (pre-commit) |

```bash
uv sync --locked
```

A image Pillow forrásbuild + Alpine Brotli 1.2.1 gate-je nem helyettesíthető
puszta helyi wheel `uv sync`-kel.

Lock pinék (többek között): `PyJWT==2.15.1`, `multidict==7.2.1`,
`apprise==1.11.0`, `djangorestframework==3.18.3`, `drf-spectacular==0.28.0`,
`pillow==13.0.0`, `soupsieve==4.1`; Alpine: `zlib=1.4-r0`,
`brotli-libs=1.2.1-r0`, `krb5-libs=1.22.3-r0`.

## Pillow és Brotli

A PyPI 12.3.0/13.0.0 wheelök Brotli 1.2.0-t ágyaznak be. A MediaTrail ezért
`--no-binary-package pillow` + pinelt `brotli-libs=1.2.1-r0` mellett épít, amíg
nincs hivatalos Brotli ≥ 1.2.1 wheel.

## Lezárt Trivy-tételek (nyomvonal)

- `krb5-libs` → **1.22.3-r0**
- PyJWT / certifi / cryptography / DRF / dnspython / oauthlib(+allauth 65.22) /
  soupsieve frissítve
- MEDIUM/LOW: zlib **1.4-r0**, PyJWT **2.15.x**, multidict **≥6.9.1**, soupsieve
  **≥2.9**, apprise **1.11.x**, a base image **pip** eltávolítva (runtime-ban
  nem kell)

## Egyéb

- Nincs vak `apk upgrade`; OS-csomagok explicit pinjei.
- `TRUSTED_PROXIES`: ash-biztos validáció (a korábbi `"` a karakterosztályban
  BusyBox szintaxishibát okozott).
- Pillow forrásbuild és az allauth 65.22 SSO smoke-test továbbra is
  üzemeltetési megjegyzés, nem nyitott CVE-lista.

## Nyitott üzemeltetési ellenőrzések (nem zárja le az image scan)

1. **TLS / `X-Forwarded-Proto`:** a MediaTrail nginx zárja-e a TLS-t, vagy egy
   megbízható előtte álló proxy?
2. **`TRUSTED_PROXIES`:** reverse proxy mögött be van-e állítva (+ `URLS`)?
3. **Production `SECRET` / `SECRET_FILE`:** nem a repo default.
