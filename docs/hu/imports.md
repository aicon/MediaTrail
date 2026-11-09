# Import

[English](../imports.md)

A Beállítások, majd az Adatimport oldal viszi be a külső előzményt a könyvtár soraiba. A lap tetején két választás minden forrásra vonatkozik:

- A **csak az új elemek** azt veszi fel, ami helyben hiányzik, és a meglévő sorokat békén hagyja.
- Az **új elemek és a meglévők felülírása** a már meglévő sor megtekintési dátumát is frissíti. A pontszám és a jegyzet megmarad. Törlés nincs.

A gyakoriság lehet egyszeri, vagy ismétlődés a kiválasztott órától. Az ismétlés addig fut, amíg az aktív ütemezett importok közül ki nem veszed. A fájlfeltöltés nem ismételhető. A felhasználónév és a mentett belépés igen.

A források alatti történet az elmúlt hét napot mutatja. A „most fut” állapotú feladat még dolgozik. A lezárt feladat felsorolhatja azokat a sorokat is, amelyeket kihagyott.

## Nuvio

A Nuvio az első forrás. Egy Nuvio-profil filmjeit és epizódjait olvassa. A Nuvio felé nem ír, és nem töröl helyi sort attól, hogy a forrásnál valami eltűnik.

Az űrlap a Nuvio e-mailt, a jelszót és a profil számát kéri. Az első sikeres küldés titkosítva menti őket a MediaTrail-fiókodhoz. Legközelebb az e-mail és a profil ki van töltve. A jelszómezőt üresen hagyva a mentett jelszó marad. Új jelszót csak akkor írj be, ha cserélni akarod. Más e-mail vagy más profil elölről kezdi ennek a fióknak az importkurzort.

Egy futás ezt csinálja:

- A könyvtárban nem lévő film befejezettként kerül be, a Nuvio megtekintési idejével.
- A könyvtárban nem lévő epizód ugyanígy. Az évad és a sorozat létrejön, ha még nincs meg.
- „Csak az új elemek” mellett a már meglévő film vagy epizód változatlan marad, az általad javított dátummal együtt.
- Felülírásnál a meglévő film, vagy az epizód legutóbbi sora megkapja a Nuvio idejét. A sor többi mezője marad.
- Ha egy epizódot a MediaTrailben kiveszel, a Nuvio pedig még őrzi a megtekintést, a következő import visszateszi. A „csak az új elemek” a helyben hiányzót jelenti, akkor is, ha az az esemény egyszer már bejött.
- Az a sorozatsor, amelyen nincs évadszám vagy nincs epizódszám, kimarad, és megjegyződik, hogy a későbbi futások ne jelentsék újra.
- A Nuvio törlési eseményét a program figyelmen kívül hagyja.

A profilszám a Nuvio profilja, nem egy MediaTrail-felhasználó. A legtöbb fióknak egy profilja van, az 1-es.

## További források

Ezek ugyanazt a módot és gyakoriságot használják.

| Forrás | Amit megadsz | Megjegyzés |
| --- | --- | --- |
| Trakt | Nyilvános felhasználónév, vagy gomb a zárt profilhoz | A zárt profilhoz saját Trakt-alkalmazás azonosítója és titka kell. Lásd a [Környezet](runtime.md) oldalt. |
| Simkl | Kapcsolódás gombbal | A zárt importhoz saját Simkl-azonosító és titok kell, ha a beépített klienst cseréled. |
| MyAnimeList | Nyilvános felhasználónév | |
| AniList | Nyilvános felhasználónév, vagy kapcsolódás gombbal | A zárt profilhoz saját AniList-alkalmazás kell. |
| Kitsu | A profilcímben lévő szám | |
| Steam | A 64 bites Steam-azonosító | A profilnak nyilvánosnak kell lennie, kivéve ha a Steam-kulcs ehhez a fiókhoz tartozik. |
| MediaTrail-mentés | CSV a Beállítások, majd az Adatexport oldalról | Csak egyszeri. |
| HowLongToBeat | CSV-export | Csak egyszeri. Játékok. |
| IMDb | Értékelés-CSV | Csak egyszeri. |
| Goodreads | Könyvtárexport | Csak egyszeri. Könyvek. |

A párosítás azokkal a katalógusazonosítókkal megy, amelyeket a MediaTrail eleve tárol. A katalógusban ismeretlen cím a lezárt feladatban jelenik meg, és nem jön létre helyette kitalált sor.

## Lejátszók

A Jellyfin, a Plex és az Emby webhookkal szólhat a MediaTrailnek a lejátszásról. A Beállítások, majd az Integrációk oldal mutatja mindegyik címét. A címben benne van a token. A kattintások listája magán az oldalon van. Új token kérése után a cím megváltozik.
