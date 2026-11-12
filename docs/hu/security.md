# Biztonsági megjegyzések (függőségek és reverse proxy)

[English](../security.md)

Az ellenőrzés a buildelt image-en történik, nem csupán a PyPI verziószámokon.

## Állapot: újrascan vár (Simkl/DRF/lock javítások után)

A korábbi tiszta Trivy az `8f7af77` digesten **nem** igazolja a még nem
image-elt Simkl fail-closed, DRF-lock és `requirements.txt`-törlés
változásait. Új image digest + Trivy + `verify_pillow_native` kell a lezáráshoz.

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
