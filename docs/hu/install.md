# Telepítés

[English](../install.md)

A MediaTrail egyetlen önálló konténerként fut. A webszerver, a főalkalmazás, a háttérfolyamatokat végző kiszolgáló és a beépített Redis egyaránt ebben a lemezképben kapott helyet, így nincs szükség különálló Redis-szolgáltatás beállítására.

A futtatandó konténerkép: `ghcr.io/aicon/mediatrail:latest`.

## Docker Compose konfiguráció

Hozd létre az alábbi `docker-compose.yml` fájlt egy üresen létrehozott `db` mappa mellett:

```yaml
services:
  mediatrail:
    image: ghcr.io/aicon/mediatrail:latest
    container_name: mediatrail
    restart: unless-stopped
    ports:
      - "8000:8000"
    environment:
      TZ: Europe/Budapest
      SECRET: ide-hosszu-veletlen-sor
      # Vedd ki a kommentjelet, ha zárt Trakt importot használsz (aktiváló kód):
      # TRAKT_API_PKCE:
    volumes:
      - ./db:/mediatrail/db
```

A `SECRET` kulcs a munkamenetek hitelesítésére és a bizalmas adatok titkosítására szolgál. Mindenképpen helyettesítsd egy hosszú, véletlenszerű karaktersorozattal még azelőtt, hogy a felületet mások számára elérhetővé tennéd. Ezt a kulcsot a későbbiekben csak akkor érdemes megváltoztatnod, ha szándékosan minden aktív felhasználót ki szeretnél léptetni. A `TZ` változó határozza meg azt az időzónát, amely szerint a naplózott időpontok megjelennek.

A kiszolgálógép `db` mappája őrzi a SQLite-adatbázist és a Redis perzisztens állapotfájlját; ez a konténeren belül a `/mediatrail/db` útvonalnak felel meg. Ezt a kötetcsatolást változatlan formában érdemes hagyni.

Az indítás menete:

```bash
docker compose up -d
```

Ezt követően nyisd meg a böngésződben a `http://localhost:8000` címet, és hozd létre az első felhasználói fiókot. A regisztráció alapértelmezés szerint nyitott, mindaddig, amíg le nem tiltod. Erről részletesebben a [Fiókok](accounts.md) fejezetben olvashatsz.

A valós idejű „Most nézem” funkció használatához nyisd meg a MediaTrail felületén a **Beállítások → Integrációk → Nuvio** menüpontot, másold ki a bővítmény egyedi hivatkozását (amely tartalmazza a fiók személyes hitelesítési tokenjét), majd add hozzá a kapcsolódó alkalmazásokhoz a **Beállítások → Bővítmények** alatt. További részletek: [Live playback / Now Watching](../now-watching.md).

Az elindulást követő első másodpercekben az automatikus állapotvizsgálat egyszer még hibát jelezhet, mivel az alkalmazás inicializálása éppen folyamatban van. Amennyiben a rá következő ellenőrzés sikeres, a rendszer indítása zökkenőmentesen befejeződött. További tudnivalók a [Karbantartás](care.md) oldalon találhatók.

## Nyilvános elérés és egyedi domainnév

Amennyiben a MediaTrail fordított proxy (reverse proxy) mögött, saját domainnév alatt üzemel, a `URLS` változóban kell megadnod ezt a nyilvános címet a `http://` vagy `https://` protokollal együtt, lezáró perjel nélkül:

```yaml
URLS: https://mediatrail.example
```

Több domain esetén a címeket vesszővel választhatod el. A bejelentkezés és az importálás átirányításai ezeket a címeket fogadják el hiteles forrásként. E konfiguráció hiányában a proxy mögé helyezett oldal elutasítja a beérkező űrlapokat.

Ha ezen a nyilvános címen más felhasználók is igénybe veszik a rendszert, a `MEDIATRAIL_SOURCE_URL` változónak a futó verziót felépítő pontos forráskód nyilvános elérésére kell mutatnia (lásd a [Kezdés](index.md) fejezetet).

## Helyi forrásból történő fordítás

A tárolóban található `docker-compose.local.yml` állomány segítségével a helyi forráskódból építheted fel a `mediatrail:local` nevű konténerképet. Ezt kizárólag a forráskód módosítása és fejlesztése során célszerű használnod, általános használatra a hivatalosan közzétett, kész konténerkép javasolt.

A külső szolgáltatókhoz tartozó API-kulcsokat és egyéb bizalmas adatokat a Compose futási környezetében vagy egy helyi `.env` fájlban tárold, soha ne építsd be őket a konténerképbe (ne add át őket build argumentumként).
