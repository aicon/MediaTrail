# MediaTrail REST API Útmutató

A MediaTrail beépített REST API-t biztosít a `/api/v1/` útvonal alatt. Ennek segítségével külső programok, automatizációk, scrobblerek és szkriptek lekérdezhetik a médiatárat, újranézéseket naplózhatnak, kezelhetik az egyéni listákat, vagy frissíthetik a haladást.

---

## Áttekintés és Interaktív Dokumentáció

- **Alapértelmezett URL:** `http(s)://<mediatrail-szerver-cime>/api/v1/`
- **Interaktív Swagger felület:** `/api/docs/`
- **Gépileg olvasható OpenAPI séma:** `/api/schema/`
- **Adatformátum:** Kizárólag JSON (`Content-Type: application/json`)
- **Záró perjel (`/`):** Opcionális (az `APPEND_SLASH` engedélyezve van, így a `/media` és a `/media/` ugyanarra a végpontra fut be).

> **Fontos:** Mind a `/api/docs/`, mind a `/api/schema/` felület megköveteli az API-kulcsos hitelesítést. Anonim módon kizárólag a `/api/v1/health/` és a `/api/v1/info/` végpontok érhetők el.

---

## Hitelesítés (Authentication)

Minden API-kérés (a nyilvános állapotlekérdező végpontokon kívül) személyes integrációs tokent igényel.

### A token beszerzése
A MediaTrail webes felületén lépj a következő menüpontra:
**Beállítások → Integrációk → API-kulcs / Token**

A token a bejelentkezett felhasználót azonosítja. Újragenerálás esetén a korábbi token azonnal érvényét veszti.

### A fejléc használata
A kérések küldésekor az alábbi két HTTP fejléc bármelyike használható:

```http
Authorization: Bearer <tokened>
```
vagy
```http
X-API-Key: <tokened>
```

---

## Alapfogalmak

### 1. Médiatípusok (`media_type`)
- **Fő kategóriák:** `movie` (film), `tv` (sorozat), `anime`, `manga`, `game` (játék), `book` (könyv), `comic` (képregény), `boardgame` (társasjáték)
- **Al-elemek (a sorozatok alatt):** `season` (évad), `episode` (epizód)

### 2. Metaadat-források (`source`)
- A szolgáltatói források egy szöveges azonosítót (`media_id`) igényelnek:
  - `tmdb` (The Movie Database)
  - `mal` (MyAnimeList)
  - `igdb` (Internet Game Database)
  - `mangaupdates`
  - `openlibrary`
  - `hardcover`
  - `comicvine`
  - `bgg` (BoardGameGeek)
- `manual`: Kézi hozzáadás olyan egyedi elemekhez, amelyek nincsenek fent a fenti oldalakon.

### 3. Állapotkódok (`status`)
Az állapotok egész számként vannak definiálva:

| Érték | Elnevezés | Jelentés |
| :---: | :--- | :--- |
| **0** | Planning | Tervezett (várólistán, backlogban lévő elem) |
| **1** | In progress | Folyamatban (éppen nézett, olvasott vagy játszott) |
| **2** | Paused | Szüneteltetve (ideiglenesen félretéve) |
| **3** | Completed | Befejezve (megnézve, elolvasva, végigjátszva) |
| **4** | Dropped | Félbehagyva (abbahagyott tartalom) |

### 4. Módosítható mezők
A külső hívásokkal frissíthető mezők médiatípusonként eltérnek:

| Médiatípus | Módosítható mezők |
| :--- | :--- |
| **movie** | `score`, `status`, `start_date`, `end_date`, `notes` |
| **tv**, **season** | `score`, `status`, `notes` |
| **episode** | `end_date` *(megtekintési előzményekben)* |
| **anime, manga, game, book, comic, boardgame** | `score`, `status`, `progress`, `start_date`, `end_date`, `notes` |

- **Pontszámok (`score`):** `0.0` és `10.0` közötti lebegőpontos szám (egy tizedesjegy pontossággal).
- **Dátumok:** Szabványos ISO-8601 szöveg (`YYYY-MM-DD` vagy teljes időbélyeg: `YYYY-MM-DDTHH:MM:SSZ`).

---

## Kérések és Válaszok Formátuma

### Lapozás (Pagination)
A listázó végpontok egységes burkolóstruktúrát adnak vissza:

```json
{
  "pagination": {
    "total": 42,
    "limit": 20,
    "offset": 0,
    "next": "/api/v1/media/?limit=20&offset=20",
    "previous": null
  },
  "results": [ ... ]
}
```

- `limit`: Egy oldalon visszaadott elemek száma (alapértelmezett: `20`, maximum: `200`).
- `offset`: Kezdőindex (alapértelmezett: `0`).

### Hibák formátuma
Sikertelen kérés esetén a MediaTrail strukturált JSON választ ad:

```json
{
  "detail": "Episode not found.",
  "errors": null
}
```
Amennyiben a validáció nem megy át, az `errors` objektum tartalmazza a mezőszintű hibaüzeneteket.

---

## Gyakorlati Példák és Munkafolyamatok

### 1. Keresés a szolgáltatóknál
Cím alapján megkeresheted az adott tartalomhoz tartozó `media_id`-t:

```http
GET /api/v1/search/tv/?search=Breaking+Bad HTTP/1.1
Authorization: Bearer <token>
```

---

### 2. Epizód megtekintésének rögzítése (Scrobble / Újranézés)
Új megtekintési bejegyzést hoz létre a megadott epizódhoz:

```http
POST /api/v1/media/tv/tmdb/1399/1/1/history/ HTTP/1.1
Authorization: Bearer <token>
Content-Type: application/json

{
  "end_date": "2026-03-24T20:15:00Z"
}
```

**Működési részletek:**
- **Nem idempotens:** A végpont minden egyes hívása új megtekintést jegyez be (így teljes újranézési előzmény keletkezik).
- **Opcionális törzs:** Ha az `end_date` hiányzik, vagy a törzs üres (`{}`), a befejezés ideje a szerver aktuális ideje lesz.
- **Automatikus felvétel:** Ha a szülő évad vagy sorozat még nincs benne a könyvtáradban, a rendszer automatikusan felveszi azt.
- **Katalógus-ellenőrzés:** Ha az adott szolgáltatónál nem létezik az adott évad- vagy epizódszám, `404 Episode not found` hibát ad vissza.

**Sikeres válasz (`201 Created`):**
```json
{
  "consumption_id": 412,
  "created": "2026-03-24T20:15:02Z",
  "score": null,
  "progress": 1,
  "progressed_at": "2026-03-24T20:15:02Z",
  "status": 3,
  "start_date": "2026-03-24T20:15:02Z",
  "end_date": "2026-03-24T20:15:00Z",
  "notes": ""
}
```

---

### 3. Film követése vagy befejezése
Az epizódokkal ellentétben a filmek egyetlen követési állapotot tartanak nyilván:

#### Film felvétele befejezettként:
```http
POST /api/v1/media/movie/ HTTP/1.1
Authorization: Bearer <token>
Content-Type: application/json

{
  "source": "tmdb",
  "media_id": "603",
  "status": 3,
  "score": 9.0,
  "end_date": "2026-03-24T22:30:00Z",
  "notes": "Újranézve 4K minőségben."
}
```

#### Meglévő film értékelésének vagy jegyzetének módosítása:
```http
PATCH /api/v1/media/movie/tmdb/603/ HTTP/1.1
Authorization: Bearer <token>
Content-Type: application/json

{
  "score": 9.5,
  "notes": "Jobban tetszett, mint elsőre."
}
```

---

### 4. Haladás frissítése (Könyvek, Játékok, Animék)
Olyan elemeknél, amelyeknél részleges haladást mérsz (pl. oldalszám, fejezet, játékórák):

```http
PATCH /api/v1/media/book/openlibrary/OL27479W/ HTTP/1.1
Authorization: Bearer <token>
Content-Type: application/json

{
  "status": 1,
  "progress": 150,
  "notes": "A 8. fejezetnél tartok."
}
```

---

### 5. Metaadatok frissítése a külső szolgáltatótól
A poszterek, leírások és megjelenési dátumok újraszinkronizálása a forrásról:

```http
POST /api/v1/media/tv/tmdb/1399/sync/ HTTP/1.1
Authorization: Bearer <token>
```
*A válasz `202 Accepted`, jelezve, hogy a frissítési feladat a háttérben elindult.*

---

## Végpontkatalógus Áttekintés

### Rendszer és Állapot
- `GET /api/v1/health/` — Rendszerállapot ellenőrzése (nyilvános).
- `GET /api/v1/info/` — Szerververzió, időzóna és beállítások (nyilvános).
- `GET /api/v1/statistics/` — Felhasználói statisztikák `start_date` és `end_date` szűrőkkel.

### Keresés
- `GET /api/v1/search/{media_type}/` — Keresés külső forrásokban cím alapján (`?search=szoveg&source=tmdb`).

### Médiaelemek és Követés
- `GET /api/v1/media/` — Az összes követett média listázása.
- `GET /api/v1/media/{media_type}/` — Követett elemek szűrése típus szerint.
- `POST /api/v1/media/{media_type}/` — Új követett elem rögzítése (forrásból vagy kézzel).
- `GET /api/v1/media/{media_type}/{source}/{media_id}/` — Követett elem részletes adatai.
- `PATCH /api/v1/media/{media_type}/{source}/{media_id}/` — Legutóbbi állapot vagy bejegyzés frissítése.
- `DELETE /api/v1/media/{media_type}/{source}/{media_id}/` — Média és teljes előzményének törlése.
- `POST /api/v1/media/{media_type}/{source}/{media_id}/sync/` — Metaadatok újraszinkronizálása a forrástól.

### Sorozatok, Évadok és Epizódok
- `GET /api/v1/media/tv/{source}/{media_id}/seasons/` — Követett évadok listája.
- `GET /api/v1/media/tv/{source}/{media_id}/{season}/episodes/` — Évadon belüli epizódok listája.
- `POST /api/v1/media/tv/{source}/{media_id}/{season}/{episode}/history/` — **Epizódmegtekintés rögzítése (watch).**
- `GET /api/v1/media/tv/{source}/{media_id}/{season}/{episode}/history/` — Epizód megtekintési előzményeinek listája.
- `PATCH /api/v1/media/tv/{source}/{media_id}/{season}/{episode}/history/{consumption_id}/` — Megtekintési dátum szerkesztése.
- `DELETE /api/v1/media/tv/{source}/{media_id}/{season}/{episode}/history/{consumption_id}/` — Egyetlen megtekintési bejegyzés törlése.

### Egyéni Listák
- `GET /api/v1/lists/` — Saját listák lekérése.
- `POST /api/v1/lists/` — Új lista létrehozása.
- `GET /api/v1/lists/{list_id}/` — Lista részletei.
- `PATCH /api/v1/lists/{list_id}/` — Lista nevének vagy leírásának szerkesztése.
- `DELETE /api/v1/lists/{list_id}/` — Lista törlése.
- `GET /api/v1/lists/{list_id}/items/` — Egy lista elemeinek listázása.
- `DELETE /api/v1/lists/{list_id}/items/{item_id}/` — Elem eltávolítása a listáról.

### Naptár
- `GET /api/v1/calendar/` — A követett tartalmak várható megjelenései.
- `POST /api/v1/calendar/update/` — Naptáresemények frissítésének indítása.

---

## Élő lejátszás vs. a Nuvio addon

A több eszközös **„Most nézem”** a NuvioMobile-MT / NuvioTV-MT felől **nem** ezen a REST API-n jön. A társalkalmazások a beépített MediaTrail addont telepítik (`…/nuvio/<token>/manifest.json`), és a `/nuvio/<token>/player/…` útvonalakat hívják `deviceId` / `deviceName` paraméterekkel. Lásd: [docs/now-watching.md](docs/now-watching.md).

A könyvtári megnézett / nem látott jelölés a társalkalmazásból **külön** útvonal: `POST /nuvio/watched.json`, `Authorization: Bearer <token>` (a token soha ne kerüljön az URL-be). Teljes szerződés: [docs/imports.md — Companion mark](docs/imports.md#companion-mark--unmark-post-nuviowatchedjson).

A `/api/v1/playback/` alatti REST végpontok tokenes előnézet eszközöknek. A `PUT` jelenleg a legacy eszközkosárba ír (a kérésben még nincs eszközönkénti azonosító). A befejezett nézés az addonon `stop`nál, **legalább 90%**nál kerül be — nem önmagában ezeken a REST hívásokon.

## Fontos Tanácsok Kliensfejlesztőknek

1. **Deduplikáció:** Mivel a `POST .../history/` hívás minden alkalommal új megtekintést hoz létre, a hálózati hibák miatti automatikus újrapróbálkozásokat a kliens oldalon érdemes kiszűrni, elkerülve a téves duplikációkat.
2. **Időzónák:** Az API által visszaadott időbélyegek mindig tartalmazzák az UTC eltolást (`Z` végződés). Bemenetként mind az UTC, mind a helyi időzónás ISO-8601 formátum elfogadott.
3. **Belső csomagnév:** Ha fejlesztés közben hibaüzeneteket vagy nyomkövetést vizsgálsz, vedd figyelembe, hogy a belső Python csomagnév az adatbázis-kompatibilitás megőrzése érdekében `yamtrack` maradt.