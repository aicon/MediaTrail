# Karbantartás és üzemeltetés

[English](../care.md)

## Frissítés

Töltsd le a legújabb konténerképet, majd hozd létre újra a futó konténert:

```bash
docker compose pull
docker compose up -d
```

Az indítás során a rendszer önműködően elvégzi a szükséges adatbázis-migrációkat. Mivel a `db` mappa a kiszolgálógépeden helyezkedik el, egy új konténerkép alkalmazása nem érinti a gyűjteményed már meglévő adatait.

A hivatalos, folyamatosan frissülő konténerkép a `ghcr.io/aicon/mediatrail:latest`. A számozott verziócímkék mindvégig az adott kiadás változatlan állapotát rögzítik.

## Állapotvizsgálat (Health check)

A konténer belső rutinja rendszeresen lekérdezi a `GET /health/` végpontot a 8000-es porton. Az indulás legelső másodperceiben az alkalmazás inicializálása még tarthat, így a rendszernaplóban megjelenhet a `connect() failed (111: Connection refused)` bejegyzés a `127.0.0.1:8001` belső címre hivatkozva. Ez csupán azt jelzi, hogy az állapotellenőrzés egy pillanattal megelőzte a kiszolgáló felállását; a soron következő vizsgálatnak már zökkenőmentesen sikerülnie kell.

Amennyiben ugyanez a hibaüzenet körülbelül 45 másodpercenként folyamatosan ismétlődik, az alkalmazás nem tudott elindulni vagy váratlanul leállt. A hiba pontos okáról az azt követő, közvetlenül a főfolyamatból származó naplósorok nyújtanak részletes tájékoztatást.

## Biztonsági mentés és visszaállítás

Állítsd le a futó konténert, majd készíts másolatot a `db` mappáról. Ez a biztonsági mentés tartalmazza a SQLite adatbázisállományt és a Redis állapotmentését is. A helyreállítás fordított sorrendben történik: helyezd vissza a mentett mappát az eredeti helyére, majd indítsd el a konténert. A SQLite adatbázisfájl futás közbeni másolása csonka vagy sérült fájlt eredményezhet, a konténer előzetes leállítása ezt a kockázatot küszöböli ki.

A `SECRET` környezeti változó értéke nem ebben a mappában tárolódik. A visszaállított gyűjtemény zökkenőmentes használatához – a meglévő bejelentkezési munkamenetek és a titkosított Nuvio-jelszavak megőrzése érdekében – pontosan ugyanazt a `SECRET` értéket kell biztosítanod. Ha a titkosítási kulcs megváltozik, a felhasználóknak újra be kell lépniük, és a mentett Nuvio-jelszót ismét be kell írniuk.

## A forráskód közzététele

Nyilvánosan elérhető rendszer üzemeltetése esetén a `MEDIATRAIL_SOURCE_URL` változónak a futó verziót felépítő pontos forráskód `http` vagy `https` címére kell mutatnia. Az oldal lábléce és a `/source/` hivatkozás erre a forrásra mutat. A változó értékét kizárólag szigorúan magáncélú, zárt környezetben futtatott példányok esetén szabad üresen hagynod.
