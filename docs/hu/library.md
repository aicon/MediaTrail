# Könyvtár

[English](../library.md)

A gyűjteményed a kezdőlapon és az oldalsávon keresztül érhető el. A filmek, sorozatok, évadok és egyéb médiatípusok mind saját listával rendelkeznek. A listák keresőmezője a saját tételeid között böngészik.

Lejátszás vagy szüneteltetés közben a kezdőlap tetején megjelennek a dinamikus **„Most nézem”** sávok – minden kapcsolódó eszközhöz (telefonhoz vagy különálló televízióhoz) egy-egy önálló sáv. A panelen látható a mű címe, az epizód száma, a megtekintett hányad, a hátralévő idő, valamint a tetszés szerint átnevezhető eszköznév. Ha egy adott eszközön leállítod a lejátszást vagy elrejted a sávot, az a többi készülék kijelzését nem érinti. Amikor a társalkalmazás leállítási (`stop`) eseményt küld, és az előrehaladás elérte a legalább **90%**-ot, a MediaTrail kiegészítője automatikusan egy befejezett megtekintést rögzít a naplódba.

![A Most nézem sáv a kezdőlapon](../screenshots/now-watching-hu.png)

A MediaTrail kiegészítő hivatkozását a **Beállítások → Integrációk → Nuvio** menüpontból másolhatod ki, amelyet valamennyi [NuvioMobile-MT](https://github.com/aicon/NuvioMobile-MT) és [NuvioTV-MT](https://github.com/aicon/NuvioTV-MT) kliensedben hozzá kell adnod a bővítményekhez. Részletes tájékoztató: [Live playback / Now Watching](../now-watching.md).

Ha egy **filmet** kb. **2–90%** között állítasz le, a főoldali **In Progress** listában megmarad folytatási csíkkal; a kártya törlésével veheted le. Epizódokra ez még nem vonatkozik.

Egy mű adatlapját megnyitva a külső katalógus adatai és a naplózási űrlap jelenik meg. A bejegyzéshez rögzítheted az aktuális állapotot, a személyes értékelésedet, a megtekintés előrehaladását, a kezdeti és befejezési dátumot, valamint az egyéni megjegyzéseidet. Amennyiben egy korábban befejezett művet újra megtekintesz vagy újraolvasol, a rendszer újabb bejegyzést fűz a megtekintési előzményeidhez. A sorozatok hierarchikus felépítésűek: az évadok és az epizódok különálló tételként szerepelnek a rendszerben, így egyetlen rész megtekintésének rögzítése nem írja felül a teljes műsort.

## Kezelőfelület és metaadatok nyelve

A felület nyelvét (magyar vagy angol) a Beállításokban választhatod ki, ezt a rendszer a felhasználói fiókodhoz rendelve menti el. A külső katalógusokból beemelt leírások nyelve attól függ, hogy a kiszolgálót milyen nyelvi paraméterrel kérdezi le a rendszer. A filmek és sorozatok leírásának nyelvét a `TMDB_LANG` környezeti változó határozza meg (lásd a [Környezet](runtime.md) fejezetet).

## Egyéni bejegyzések

Előfordulhat, hogy egy keresett mű nem szerepel az elérhető online katalógusokban. Az oldalsávban található **Egyéni bejegyzés** menüpont révén bármilyen tételt rögzíthetsz saját kezűleg is: megadhatod a típust, a címet és igény szerint a borítókép hivatkozását. Ezt követően a bejegyzés éppúgy kezelhető és naplózható, mint bármely más katalógustétel.

## Egyéni listák

A listák tetszésed szerint elnevezhető, tematikus gyűjtemények. Egyetlen listán belül különböző típusú műveket is vegyíthetsz, sőt, a szerkesztésbe bevonhatod a szerveren lévő más felhasználói fiókokat is. A listán belüli keresés és a rendezési szempontok az adott lista oldalán érhetők el.

## Naptár

A naptár a gyűjteményedben szereplő tételek közelgő megjelenési dátumait foglalja össze. Az oldalon található exportálási hivatkozás révén a naptár privát forrásként beilleszthető bármilyen külső naptárprogramba. Ez a hivatkozás a személyes hitelesítési tokenedet tartalmazza; amennyiben a Beállításokban új tokent generálsz, a régi hivatkozás érvényét veszti, és a korábbi tokennel működő médialejátszó-webhookok beállításait is frissítened kell.

## Statisztika

A statisztikai áttekintés összegzi az állapotok megoszlását, a naplózási aktivitásodat és a választott időszak eredményeit, a mai naptól kezdve egészen a kezdetekig visszamenően. A diagramok feliratai a felület választott nyelvét követik.

## Értesítések

A Beállítások menüpont Értesítések oldalán soronként egy-egy Apprise-címet adhatsz meg. A megjelenési emlékeztetők és a napi összesítők ezekre az értesítési végpontokra érkeznek. Az oldalon található segédlet részletesen felsorolja az Apprise által elfogadott formátumokat.
