# Importálás

[English](../imports.md)

A külső szolgáltatásokból származó megtekintési előzmények a Beállítások felületén, az Adatimport menüpont alatt emelhetők be a gyűjteménybe. Az oldal tetején található két működési mód valamennyi adatforrásra érvényes:

- **Csak az új elemek:** kizárólag azokat a tételeket rögzíti, amelyek még hiányoznak a helyi adatbázisból; a meglévő bejegyzéseket változatlanul hagyja.
- **Új elemek és a meglévők felülírása:** a hiányzó elemek felvétele mellett a már meglévő tételek megtekintési dátumát is frissíti a forrás adatai alapján. A személyes pontszámok és feljegyzések mindvégig megmaradnak, és a folyamat egyetlen sort sem töröl.

Az importálás indítható egyszeri alkalommal, vagy ütemezhető a megadott időponttól kezdődő rendszeres ismétlődéssel. Az ütemezett feladat mindaddig periodikusan lefut, amíg el nem távolítja az aktív időzített importok közül. A fájlfeltöltéssel járó import kizárólag egyszer futtatható le, míg a felhasználónévhez vagy elmentett bejelentkezéshez kötött források ütemezhetők.

A források alatt elhelyezkedő előzménytár az elmúlt hét nap feladatait sorolja fel. A folyamatban lévő feladatoknál külön állapotjelzés látható; a sikeresen lezárult feladatok részletes összegzésében pedig megtekinthetők azok a tételek is, amelyeket a rendszer figyelmen kívül hagyott.

## Nuvio

Az elsődleges adatforrás a Nuvio, amely közvetlenül egy kiválasztott Nuvio-profilhoz tartozó filmeket és epizódokat olvassa be. A kétirányú előzményszinkronizáció a Beállítások → Integrációk → Nuvio menüpontban tetszés szerint engedélyezhető: a megtekintett, illetve a még nem látott jelölések átvétele helyben érvényesíti a Nuvio változásait, míg a MediaTrailben végzett bejegyzések vagy törlések automatikusan a megfelelő szinkronizációs hívásokat (`sync_push_watched_items` / `sync_delete_watched_items`) indítják el.

A társalkalmazásokból érkező valós idejű **„Most nézem”** sáv működése ettől elkülönül: a MediaTrail beépített kiegészítője közvetlenül az eszközökhöz kötött lejátszási eseményeket fogadja. Az előzmények importálása ezeket az élő sávokat nem érinti. Erről bővebben a [Könyvtár](library.md) fejezetben és a [Live playback / Now Watching](../LIVE_PLAYBACK_NOW_WATCHING.md) leírásban olvashat.

A bejelentkezési adatok, az importálási mutatók (kurzor) és a beemelt sorok szigorúan az adott MediaTrail-felhasználóhoz tartoznak (minden fiókhoz egyetlen `NuvioAccount` rendelhető). Ha ugyanazon a szerveren több felhasználó is tevékenykedik, mindegyikük önálló Nuvio-fiókkal és független gyűjteménnyel rendelkezik.

Az űrlap a Nuvio-fiókhoz tartozó e-mail-címet, a jelszót és a kívánt profilszámot kéri. Az első sikeres hitelesítést követően a rendszer ezeket titkosítva tárolja a MediaTrail-fiókhoz. A következő látogatáskor az e-mail-cím és a profilszám már előre kitöltve jelenik meg; a jelszómezőt üresen hagyva a rendszer a már elmentett jelszót használja. Új jelszót csak akkor szükséges megadni, ha meg kívánja változtatni azt. Egy másik e-mail-cím vagy eltérő profilszám megadása az importálási kurzor elölről kezdését eredményezi.

Az importálás során a rendszer az alábbi szabályok szerint jár el:

- A gyűjteményben még nem szereplő filmeket befejezettként veszi fel, a Nuvióban rögzített megtekintési időponttal.
- A hiányzó epizódok ugyanígy kerülnek be; amennyiben a hozzájuk tartozó évad vagy sorozat még nem létezik, a rendszer automatikusan létrehozza azokat.
- A „Csak az új elemek” beállítás mellett a már meglévő filmek és epizódok változatlanok maradnak, megőrizve az Ön által korábban megadott egyedi dátumokat is.
- A felülírási mód alkalmazásakor a már nyilvántartott filmek, illetve az epizódok legutóbbi megtekintési bejegyzései átveszik a Nuvio szerinti időpontot, a tétel többi adata azonban érintetlen marad.
- Ha egy epizódot töröl a MediaTrail felületén, ám az a Nuvio előzményeiben továbbra is megtekintettként szerepel, a következő importálás ismét beemeli azt. A „Csak az új elemek” elve ugyanis a helyi hiányt pótolja, függetlenül attól, hogy a tétel korábban már szerepelt-e az adatbázisban.
- Azok a sorozatelemek, amelyek nem tartalmaznak évad- vagy epizódszámot, kimaradnak; a rendszer feljegyzi ezeket, hogy a későbbi futások során ne jelezze őket ismételten hibaként.
- A Nuvióban végzett törléseket a rendszer figyelmen kívül hagyja, kivéve, ha az Integrációk menüpontban bekapcsolta a **Nem megtekintett jelölés szinkronizálása** lehetőséget. Ekkor a művelet a helyi film- és epizód-előzményekből is eltávolítja a megfelelő tételt.

A megadandó profilszám a Nuvio rendszerében érvényes profilra utal, nem a MediaTrail-fiókra. A fiókok többsége egyetlen, 1-es azonosítójú profillal rendelkezik.

### Kétirányú interaktív szinkron

Ez a Jellyfin-szerű „megnézett / nem megtekintett” jelölést köti össze a Nuvio Cloud megtekintési előzménye és a MediaTrail film-, illetve epizódbejegyzései között. Nem távoli szüneteltetés, és nem azonos a „Most nézem” scrobble-lel.

A kapcsolók a **Beállítások → Integrációk → Nuvio** oldalon találhatók:

| Kapcsoló | Nuvio → MediaTrail | MediaTrail → Nuvio |
| --- | --- | --- |
| **Megnézett jelölés szinkronizálása** | Upsert az előzményimportból és a megtekintési-előzmény deltából | `sync_push_watched_items` sorba állítása, ha helyben megtekintettnek jelöl |
| **Nem megtekintett jelölés szinkronizálása** | Delta-törlések alkalmazása; teljes, sikeres history-snapshot után a Nuvióban már nem lévő, korábban szinkronizált helyi megtekintések is törlődhetnek | `sync_delete_watched_items` (és a kapcsolódó watch-progress kulcsok) sorba állítása nem megtekintett jelölésnél vagy előzménytörlésnél |

Ha bármelyik kapcsoló aktív, a MediaTrail rövid időközönként lekéri a Nuvio deltát is, így az interaktív változások kézi import nélkül is megjelenhetnek. A kézi Adatimport → Nuvio továbbra is teljes előzmény-ellenőrzést futtat, majd a deltát.

A nem megtekintett jelölés / snapshot-összevetés szabályai:

- Azonosítók összehasonlítás előtt TMDB megtekintési kulcsra egységesülnek (`tmdb:…` és IMDb `tt…` ugyanarra a címre egynek számít).
- Snapshot-reconcile csak akkor fut, ha minden history-oldal megérkezett, és minden TMDB-re várható sor feloldódott. Köztes API- vagy alkalmazási hiba nem indít törlést.
- Snapshotból csak a korábban Nuvióból szinkronizált megtekintések törölhetők. A Trakt, kézi vagy más forrású helyi megtekintések megmaradnak.
- A mentett delta-kurzor csak akkor lép előre, ha az adott futás minden eseménye sikeresen alkalmazódott. Hibánál a kurzor a futás elején marad, a következő futás újra megpróbálja a batch-et (at-least-once; az upsert és a törlés idempotens).
- A tárolt Nuvio megtekintési-kulcs készlet csak a teljes, sikeres importút után frissül.

## További adatforrások

Az egyéb források ugyanazokat a működési módokat és ütemezési lehetőségeket használják.

| Forrás | Szükséges adatok | Megjegyzések |
| --- | --- | --- |
| Trakt | Nyilvános felhasználónév, vagy közvetlen összekapcsolás | Zárt profil esetén saját Trakt-alkalmazás kliensazonosítója és titkos kulcsa szükséges (lásd a [Környezet](runtime.md) fejezetet). |
| Simkl | Közvetlen összekapcsolás gombbal | Saját alkalmazás használata esetén külön Simkl-azonosító és titkos kulcs szükséges a beépített kliens felülbírálásához. |
| MyAnimeList | Nyilvános felhasználónév | |
| AniList | Nyilvános felhasználónév, vagy közvetlen összekapcsolás | Zárt profil eléréséhez saját AniList-alkalmazás regisztrációja szükséges. |
| Kitsu | A profil hivatkozásában szereplő numerikus azonosító | |
| Steam | A 64 bites Steam-azonosító | A profilnak nyilvánosnak kell lennie, kivéve, ha az API-kulcs közvetlenül az adott fiókhoz tartozik. |
| MediaTrail biztonsági mentés | A Beállítások → Adatexport menüből származó CSV-fájl | Kizárólag egyszeri importként használható. |
| HowLongToBeat | CSV-exportfájl | Kizárólag egyszeri importként, videojátékokhoz használható. |
| IMDb | Értékeléseket tartalmazó CSV-fájl | Kizárólag egyszeri importként használható. |
| Goodreads | Gyűjteményexport CSV-formátumban | Kizárólag egyszeri importként, könyvekhez használható. |

A tételek párosítása azoknak a katalógusazonosítóknak az alapján történik, amelyeket a MediaTrail alapértelmezés szerint nyilvántart. Ha egy cím a katalógusokban nem azonosítható, az a feladat összegzésében jelenik meg, és a rendszer nem hoz létre hozzá pontatlan, fiktív bejegyzést.

## Médialejátszók

A Jellyfin, a Plex és az Emby szerverek webhookokon keresztül képesek értesíteni a MediaTrailt a lejátszási eseményekről. A Beállítások → Integrációk oldalon valamennyi támogatott lejátszóhoz megtalálható a hozzárendelt webhook-cím, amely magában foglalja a személyes hitelesítési tokent is. Az oldalon lépésről lépésre követhető útmutató található a lejátszók beállításához. Amennyiben a Beállításokban új személyes tokent igényel, ezek a webhook-címek is megváltoznak, így azokat a külső programokban is frissíteni szükséges.
