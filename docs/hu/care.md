# Karbantartás

[English](../care.md)

## Frissítés

Húzd le a futtatott címkét, majd hozd létre újra a konténert:

```bash
docker compose pull
docker compose up -d
```

Az indulás magától lefuttatja az adatbázis-migrációt. A `db` könyvtár a gépen marad, ezért az új kép nem üríti ki a könyvtárat.

A `ghcr.io/aicon/mediatrail:latest` a lehívandó kép. A számozott címke annál a kiadásnál marad.

## Állapotvizsgálat

A konténer saját magától kéri a `GET /health/` címet a 8000-es porton. Az első másodpercekben az alkalmazás még indulhat, és a naplóban megjelenhet a `connect() failed (111: Connection refused)` sor a `127.0.0.1:8001` címre. Ez az az egy sor, amikor a vizsgálat hamarabb érkezik, mint hogy az alkalmazás figyelne. A következő vizsgálatnak sikerülnie kell.

Ha ugyanez a sor körülbelül 45 másodpercenként ismétlődik, az alkalmazás nem maradt fent. Az oka az utána következő, az alkalmazás folyamatából származó sorokban van.

## Mentés

Állítsd le a konténert, és másold le a `db` könyvtárat. A másolatban benne van a SQLite-fájl és a Redis pillanatképe. A visszaállítás fordítva megy: tedd vissza a könyvtárat, majd indítsd a konténert. A SQLite-fájl másolása írás közben csonka fájlt adhat. A leállítás ezt elkerüli.

A `SECRET` nincs ebben a könyvtárban. A visszaállított könyvtárhoz ugyanaz a `SECRET` kell, ha a meglévő munkameneteknek és a titkosított Nuvio-jelszónak működnie kell. Ha a titok megváltozik, mindenki újra belép, és a mentett Nuvio-jelszót egyszer újra be kell írni.

## Forráskód felajánlása

Nyilvános telepítésnél a `MEDIATRAIL_SOURCE_URL` a futó képet felépítő pontos forrás `http` vagy `https` címe. A lábléc ide mutat. A `/source/` ugyanez az ajánlat. Üresen hagyni csak zárt, saját példánynál szabad.
