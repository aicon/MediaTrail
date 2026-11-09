# Telepítés

[English](../install.md)

A MediaTrail egy konténerben fut. A webszerver, az alkalmazás, a háttérfeladat és a Redis mind ebben a képben van. Külön Redis-szolgáltatás nem kell.

A használandó kép a `ghcr.io/aicon/mediatrail:latest`. A csomag zárt, ezért a gépnek olyan belépés kell, amely olvashatja a `ghcr.io/aicon/mediatrail` csomagot.

## Compose

Mentsd el `docker-compose.yml` néven egy üres `db` könyvtár mellé:

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
    volumes:
      - ./db:/mediatrail/db
```

A `SECRET` a munkameneteket és a titkosított értékeket írja alá. Cseréld le, mielőtt más is eléri az oldalt, és később csak akkor változtasd meg, ha mindenkit ki akarsz léptetni. A `TZ` az az időzóna, amelyben a tárolt időpont megjelenik.

A gépen a `db` könyvtárban van a SQLite-adatbázis és a Redis tartós fájlja. A konténeren belül ez a `/mediatrail/db`. A csatolást így hagyd.

Indítás:

```bash
docker compose up -d
```

Nyisd meg a `http://localhost:8000` címet, és hozz létre fiókot. A regisztráció nyitva van, amíg le nem zárod. Erről a [Fiókok](accounts.md) oldal szól.

Az indulás első másodperceiben az állapotvizsgálat egyszer elbukhat, mert az alkalmazás még nem figyel. Ha a következő vizsgálat sikerül, az indulás rendben lezajlott. Részletek a [Karbantartás](care.md) oldalon.

## Nyilvános cím

Ha egy közvetítő a MediaTrailt valódi névre teszi, a `URLS` értéke ez a cím, `http://` vagy `https://` előtaggal, perjel nélkül a végén:

```yaml
URLS: https://mediatrail.example
```

Több cím vesszővel választható el. A bejelentkezés és az import visszairányítása ezt fogadja el. Enélkül a közvetítő mögötti oldal elutasítja a saját űrlapjait.

Ha ezen a nyilvános oldalon mások is használják a programot, a `MEDIATRAIL_SOURCE_URL` a futó verzió pontos forrásának nyilvános címe legyen. Lásd a [Kezdés](index.md) oldalt.

## Ebből a könyvtárból építve

A `docker-compose.local.yml` a helyi másolatot `mediatrail:local` néven építi. Ezt akkor használd, ha a programon dolgozol. Különben a fenti, közzétett kép a futtatandó.

A szolgáltatói kulcsok és a többi titok a Compose környezetében vagy egy helyi `.env` fájlban maradnak, és nem kerülnek a képbe. Ne add át őket a build argumentumaként.
