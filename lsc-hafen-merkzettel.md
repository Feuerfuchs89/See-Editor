# Merkzettel: Vereinshafen LSC und Cospudener See
Stand 14.11.2026, Spiel-Cache `regattakoje-v60`. Quelle: `lsc_hafen_archiv.js` (Zeilenangaben dort), `cospu_merkzettel.json`, Michas `karte-cospu.json` und seine Fotos.
Der Nachbau muss exakt diese Lage, Maße, Farben und Anzahlen haben.

## 1. Bezugssystem
- Uferpunkt `COSPU_PTS[25]` = Ost −992, Nord 57 (Spielsystem in m, x = Ost, y = Nord, Ursprung Mitte der See-Box). Er liegt am Westufer, Uferparameter s = 0,029 (`COSPU_LSCS`).
- Hafen-System: `Wp(a,o) = P_lsc + t·a + od·o`.
  - `a` läuft am Ufer entlang (Richtung Nord, `t = (−od_y, od_x)`).
  - `o` ist der Abstand aufs Wasser.
  - `od = LSC_REAL.od = [0.9986, −0.0523]` in Ost/Nord. Das Wasser liegt also fast genau östlich.
- Bei Windrichtung ≠ 0 dreht `cospuPlace` die ganze Szene. Der Hafen hängt über `SHORE.fwd(0,0)` und `SHORE.fwd(od)` daran und dreht mit.
- **Neuaufbau:** Den Ursprung `P_lsc` und `od` aus dem neuen OSM-Ufer (Relation 285950) neu bestimmen. Alle Maße in `a` und `o` bleiben unverändert.

## 2. Aufmaß `LSC_REAL`
| Feld | Wert (a, o in m) | Bedeutung |
|---|---|---|
| `ta` | 24,1 | T-Steg liegt bei a = 24,1 |
| `os` | 9,6 | T-Steg beginnt bei o = 9,6 |
| `po` | 53,6 | Ende T-Steg und Ponton bei o = 53,6 |
| `pn` | [37,2 / 53,6 → 11,0 / 53,6] | Schwimmponton quer, 26,2 m lang, 2,6 m breit |
| `dg` | [−54,3 / 22,5 → −38,4 / 46,8] | Diagonalsteg, ~29 m lang, nach Nordost |
| `sm` | [−11,6 / 9,7 → −12,0 / −2,1] | kleiner Steg, 1,2 m breit, quer zum Ufer |

**Reihenfolge entlang des Ufers (a, Nord = +):** Diagonalsteg (a ≈ −54…−38, südlich) · kleiner Steg (a ≈ −12) · T-Steg (a = 24, nördlich).
Das passt zu Michas Satellitenfotos: Im Norden liegt der gerade T-Steg mit grünem Ponton, im Süden der schräge Steg mit Boxen und Booten.

## 3. Stege und Anlagen
Maße und Höhen stehen in `lscBuild` (Archiv Z. 246–302). Dort ist `deck(...)` die Stegfunktion.
- **T-Steg** (`lsc:tsteg`)
  - Deck 2,0 m breit, Holz `#8b7458`, Höhe 0,6 m.
  - Pfähle `#3b2f25`, Ø 0,2 m, alle 4 m an beiden Seiten.
  - **Ponton:** 2,6 m breit, grün `#5f9f73`, Anzeigefarbe `#7fc49a`.
  - **Stegfinger:** 0,5 m breit, 6 m lang (a ± 1…7), alle 5,4 m von `os+13` bis `po−9`, beidseitig. Das ergibt Boxen von 5,4 m Breite.
  - **Pro Seite** bleiben 2 zufällige Boxen frei (`box: true`, 4,8 m tief). Das sind die Hafenmanöver-Boxen.
  - **Belegung der übrigen Boxen:**
    - 45 %: ein Kielboot aus `jk, zk, varianta, dehler22, dehler29, bavaria32`.
    - sonst: ein Jollenpaar bei ±1,27 m aus `jolle, ixylon, opti, topcat`. Jede Jolle fehlt mit 15 % Wahrscheinlichkeit.
    - Kielboote liegen zu 50 % mit dem Heck zum Steg.
- **Kleiner Steg** (`lsc:ksteg`): 1,2 m breit, Holz `#5e4a36`, Pfähle alle 3 m.
- **Diagonalsteg** (`lsc:dsteg`)
  - 2,0 m breit, Holz `#8b7458`.
  - **Steg-Kopf:** 5 m breit, 3 m hinter dem Ende, `#5e4a36`.
  - **Schwimmsteg:** grün, 1,6 m breit, 10 m hinter dem Ende, quer. Er hat einen Liegeplatz (`berth`).
  - **Boote quer am Steg:** 5 auf der einen, 4 auf der anderen Seite. Position bei s = 10 + k·4,3 m (die 4er-Seite um +2 m versetzt). Typen: `jolle, ixylon, zk, varianta, dehler22, jk, opti`.
  - Sie liegen mit dem Bug von Steg weg, mit 1,0 m Abstand zur Stegkante.
- **Slipanlage** (`lsc:slip`)
  - Beton `#9c9a93`, 4 m breit, bei a = `round(sm[0]+7)` = −5.
  - Verläuft von o = −9 nach o = 4 und fällt zum Wasser ab.
- **Edelstahl-Pfeiler** (Archiv Z. 312–328)
  - 1 m hoch, Lampe oben, weißes Licht nachts. Das Licht hängt an `NIGHT`.
  - Abstand 5,4 m auf allen drei Stegen, beidseitig.
  - T-Steg: bei a = ta ± 0,85, Höhe 1,26 m, von `os+13` bis `po−9`.
  - Diagonalsteg: s = 3…L−1, ± 0,85, Höhe 1,26 m.
  - Kleiner Steg: ± 0,5, Höhe 1,16 m.
  - Sie gehören zu den Abschnitten `lsc:tsteg`, `lsc:dsteg` und `lsc:ksteg`.

## 4. Gelände und Gebäude
- **Rasen:** Fläche a = −70…70, o = −53…34, Höhe 0,82 m über dem Wasser. Raster 24 × 14, Farbe HSL(0,24; 0,35; 0,38).
  - Die Slip-Zone ist `#a39a82`.
  - Wasserflächen werden ans Ufer geklappt.
- **Gebäude** (Archiv Z. 289–294). Alle Positionen (a, o) und Maße (Breite, Tiefe, Höhe) sind unten angegeben:

| ID | Name | a, o | B×T×H | Wand | Dach |
|---|---|---|---|---|---|
| `lsc:heim` | Vereinsheim | 28, −32 | 9×7×3,2 | `#6d5440` | `#3f4246`, Satteldach, Fenster |
| `lsc:schuppen` | Schuppen | 44, −22 | 5×4×2,6 | `#7a6650` | `#44474b`, Satteldach |
| `lsc:halle` | Bootshalle | −48, −30 | 7×15×4,2 | `#9aa1a5` | `#5b6166`, Satteldach |
| `lsc:container` | Container | −18, −17 | 2,5×6×2,6 | `#3f6f5a` | flach |
| `lsc:lager` | Lagerschuppen | −30, −42 | 6×5×2,6 | `#8a7860` | `#3f4246`, Satteldach |

  - **Micha hat die Bootshalle in seiner Karte gelöscht.** Die Frage, ob sie im Neubau wegbleibt, ist noch offen.
- **11 Jollen an Land** (`lsc:jollen`): a = −8 + k·3,2, o = −10 − (k mod 2)·3,5 (zwei Reihen versetzt). Typen: `jolle, ixylon, jolle, topcat`. Höhe 0,3 m, Ausrichtung zum Wasser ± 0,1 rad.
- **6 Optis auf Gestellen** (`lsc:optis`): a = 32 + k·2,1, o = −14, Höhe 0,45 m, parallel zum Ufer.
- **Flaggenmast** (`lsc:flagge`)
  - Position a = 16, o = −14. Mast 9 m, Ø 0,12–0,18 m, weiß `#e8e8e4`.
  - Flagge 1,8×1,2 m auf Höhe 8,3 m, Bild `LSC_PENNANT`. Das ist ein base64-PNG in `index.html` Z. 4823 und bleibt dort.

## 5. Bäume, Weide, Feuerstelle (Mittwochsgruppe), Bänke
Alle Positionen hängen an `aW` = min(Stegenden a) − 5 = −54,3 − 5 = **−59,3** (südlich vom Diagonalsteg). `shoreO(a)` ist der Uferabstand an dieser Stelle.
- **Trauerweide** (`lsc:weide`)
  - Position (aW, shoreO(aW) − 0,5), also direkt am Ufer.
  - Stamm 0,08 rad übers Wasser geneigt. `willowBuild(…, jahreszeit, 1.05)`, Krone 4,6 m Radius, 7,2 m hoch, im Winter kahl. Sie bewegt sich (Animation).
- **Feuerstelle mit Mittwochsgruppe** (`lsc:feuer`)
  - Position (aW, shoreO(aW) − 7,5), also 7 m hinter der Weide.
  - **Dreibein:** 3 Eisenbeine, Länge ~2,05 m, Fußkreis r = 0,95 m. Eine Kette hängt bis 1,3 m, daran ein dunkler Kessel (Ø 0,3 m) mit Deckel.
  - **Feuerschale:** Halbkugel r = 0,45 m auf 3 Füßen, mit 4 Holzscheiten.
  - **Flammen:** 5 Kegel in Orange- und Gelbtönen, animiert. Dazu ein Lichtschein (Sprite) und ein Lichtfleck am Boden. Beide werden nachts stärker.
  - **Leute:** 8 Personen auf Baumstumpf-Hockern (Ø 0,42 m, `#6b5336`).
    - 3 + 3 auf den langen Seiten bei x = ±1,5 m und z = −1,2 / 0 / 1,2.
    - je 1 an den Stirnseiten bei z = ±2,2 m.
    - Alle schauen zum Feuer. Jacken-, Haut-, Haar- und Hosenfarben sind zufällig aus festen Paletten.
    - **Das ist die „Mittwochsgruppe“** (Micha: „sitzt um ein Lagerfeuer am Dreibein mit Trauerweide“). Sie ist also schon im Code. Eine eigene neue Gruppe ist nicht nötig. Beim Neuaufbau bleibt sie 1:1 erhalten.
- **Zwei überdachte Picknickbänke** (`lsc:bank`)
  - 5 m südlich der Weide: aP = aW − 7,3, parallel zum Ufer, aneinandergestellt (z = ±1,15 m).
  - Tisch 0,75 m breit, Bänke beidseitig. Satteldach 2,05–2,75 m hoch, Holz `#a29a6a`, Dach `#9b9468`.
  - **Micha hat 4 Kopien erzeugt:** 2 stehen bei d = (−25,6 / 35,1) und (−26,2 / 33,5), 1 bei (4,2 / −1,6) und 1 bei (−5,1 / 9,5) relativ zum Original.
- **Baumbestand** (Archiv Z. 108–110): ca. 1100 Bäume, handplatziert, a ∈ ±170 m, o ∈ −170…40 m.
  - Ausgespart ist das Vereinsgelände: |a| < 68 und o > −58. Zwischen o = −58 und dem Gelände nur 25 % Dichte.
  - Am Ufer (o > −80): 50 % Laubbäume 8–14 m, 35 % Nadelbäume, 15 % Büsche.
  - Weiter im Land: Laubbäume 10–16 m und hohe Eichen 15–24 m.
  - **Michas Wald:** 12 Waldflecken, je 30 m Radius, bei E ≈ −1063…−947 und N ≈ −132…229. Dazu kommen die OSM-Wälder aus dem Neuaufbau.

## 6. Boote (`LSC_T`, Archiv Z. 531–543)
| Typ | Breite | Mast | Rumpf- und Segelfarben |
|---|---|---|---|
| `jolle` | 1,7 | 6,9 | `#ffd23f #e5484d #2bb3a3 #f4f4f0 #3d8bff`, Unterwasser `#f4f4f0` |
| `ixylon` | 1,8 | 6,3 | `#2f6db3 #f4f4f0 #c9322a #2f8f5b` |
| `opti` | 1,13 | 2,55 | `#f4f4f0 #e9eef2 #ffd23f` |
| `topcat` | 2,4 | 8,2 | `#f4f4f0 #e8f0f4` |
| `zk` (ZK10) | 2,08 | – | `#f4f5f2 #b0201a`, Unterwasser `#2a2a2a` (zk10-gfk.glb) |
| `jk` | 2,2 | 9,2 | `#f2f2ee #dfe9ef #24425f #7a1f1f`, Länge 7,5 m |
| `varianta` | 2,5 | 8,4 | weiß, Streifen `#c43a2a`, Länge 6,5 m, Außenborder |
| `dehler22` | 2,5 | 9,0 | weiß, Streifen `#1f3a6b`, Länge 6,6 m |
| `dehler29` | 3,0 | 12,5 | `#1f2f4f`/weiß, Streifen `#c9a227`, Länge 8,8 m |
| `bavaria32` | 3,4 | 14 | weiß, Streifen `#5a6168`, Länge 9,9 m |

## 7. Spiellogik am Hafen (muss erhalten bleiben)
`SHORE.lsc = {obst, berths, piers, out:[ox,oy], tN:[tx,ty], p:[px,py], Wp}`
- `obst`: Kollisionssegmente. Dazu gehören alle Stege, Stegfinger und Liegeboote.
- `berths`: Liegeplätze für An- und Ablegen und Hafenmanöver. Das sind die Ponton-Seeseite, der Schwimmsteg und die freien Boxen.
- `piers`: Stegliste [x0, y0, x1, y1, Breite, Farbe] für Minikarte und Hafen-HUD.
- **Abschnitts-IDs (`objSec`), dürfen sich nicht ändern:**
  `lsc:tsteg, lsc:ksteg, lsc:dsteg, lsc:slip, lsc:heim, lsc:schuppen, lsc:halle, lsc:container, lsc:lager, lsc:jollen, lsc:optis, lsc:flagge, lsc:weide, lsc:feuer, lsc:bank`
  Dazu: `zoeb:stege, zoeb:pier1, n22, tonne:0…6, turm, insel:briefkasten, insel:flamingos, insel:ring, umland:haeuser`.
  - `zoeb:pier1` entsteht heute nur ohne Umland. Michas Karte enthält Kopien davon. Beim Neuaufbau muss die ID mit dem OSM-Gebäude bedient werden.
- **Editor-Sperrzonen** (`edLocks`): LSC 200 m, Hafen Zöbigker (`COSPU_HARB`, Index 121) 230 m, Steg Nordufer 70 m.

## 8. Weitere Objekte am See (übernehmen)
- **Hafen Zöbigker** (`COSPU_STEGE`, Aufmaß): 12 Einträge [x0, y0, x1, y1, Breite, Typ]. Typ ≠ 0 bedeutet Boxen alle 4,4 m (Liegeboote, `TY`-Tabelle im Archiv Z. 190).
  - Hauptsteg: (418,3 / −451,7) → (539,6 / −305,1), 2,6 m.
  - Boxenstege: 6 Stück mit Breite 2,0 m.
  - Kurze Stege: 3 mit je 1,6 m.
  - **Der Eintrag 12 ist der Steg am Nordufer**: (410,1 / 1701,5) → (427,3 / 1726,4), 1,6 m.
  - Hafenpunkt `COSPU_PTS[121]` = (540, −305).
- **Steg Nordufer** (`COSPU_N22`, ID `n22`): (410,1 / 1701,5) → (427,3 / 1726,4), 2 m breit, Holz `#8a7a63`.
- **Tonnen** (`COSPU_TONNEN`, 7 Stück, ID `tonne:k`):
  - (−654,7 / −963,9) Sondertonne, Kugel
  - (−221,2 / −735,3) Sondertonne, Kugel
  - (−436,4 / −830,3) Sondertonne, Kugel
  - (−477,2 / −246,5) Cospudentonne, Kegel
  - (334,3 / −297,6) Hafentonne, Fass
  - (635,4 / 826,4) Gymnasium, Fass
  - (48,8 / 980,5) Nordtonne, Zylinder
  - Alle gelb, Skalierung ×2,6, mit Namensschild.
- **Inseln** (`COSPU_INSELN`): 2 OSM-Löcher bei ca. (−218 / −483) und (−194 / −483), je ~10 m.
  - Westinsel mit Steinhaufen (−220,05 / −482,86), Briefkasten und 2 Plastikflamingos (−216,1 / −482,2 und −216,1 / −483,7). 13 weitere Flamingos stehen rund um beide Inseln.
  - Flachwasser: `SHORE.shoal` (Kreis um beide Inseln, Radius +7 m). Dort läuft das Boot „auf Grund“.
- **Rundweg mit Laternen** (`cospuRundweg`, Archiv Z. 388–450): 1,6 m breit, 100 m vom Ufer, am Nordufer 250 m, Farbe `#b3a788`.
- Weiter: A38-Brücke (`highwayA38`, Fahrbahnhöhen heute von Hand, muss ans echte Gelände), Aussichtsturm Bistumshöhe (ID `turm`, 30 m, grau `#6b6f73`), Windpark (`windFarm3D`) und Horizont (`horizon3D`).

## 9. Michas eigene Änderungen (`karte-cospu.json`, `pub` 14.11.2026)
- **Nicht verändert:** Uferpunkte (`pts: null`), Häuser, Inseln und Geländehöhen (`rle: null`).
- **Wald:** 12 Flecken (siehe Abschnitt 5).
- **`ov` (verschoben, Δx / Δy / Δz in m, Drehung in rad):**
  - `lsc:halle`: gelöscht (`x: true`)
  - `lsc:container`: (20,9 / 0 / 14,3), r = 0,40
  - `lsc:lager`: (57,6 / 0 / −48,9), r = 0,64
  - `lsc:schuppen`: (1,4 / 0 / 5,2), r = 1,11
  - `lsc:jollen`: (42,5 / 0 / 3,1), r = −2,78
  - `zoeb:pier1`: (−0,7 / 0 / 26,3), r = 1,15
- **`cp` (31 neue Kopien und Katalogobjekte):**
  - Am LSC: 2 Container, 1 Kopie `ksteg`, 1 `slip`, 1 `optis`, 4 Bänke, 1 Jollen-Kopie.
  - 4 Kopien von `zoeb:pier1`.
  - Ein **zweites Vereinsgelände** weit weg: 3× `lsc:heim`, 5× `lsc:schuppen`, 7× `lsc:jollen`, bei d ≈ (610…780 / −1520…−1600). Es liegt wohl am Nordufer.
  - Katalog (`cat:`): 2 Hecken `cat:hecke` bei (−128 / 835) und die Trauerweide `cat:weide` bei (−90 / 787).
- **Wichtig:** Alle Δ sind relativ zur Originalposition der Quelle. Die Kopien-Schlüssel (`k`) ändern sich nicht. Die Karte lädt wieder, solange die IDs gleich bleiben und die Hafenlage nicht um mehr als einige Meter wandert.
- **Offen bei Micha:** Ist das zweite Gelände echt? Bleibt die Bootshalle weg?

## 10. Beobachtungen aus Michas Fotos (Google Maps und Spiel)
- **Echter Hafen von oben:**
  - Im Norden liegt ein langer gerader Steg nach Osten, mit einem grünen Schwimmponton quer am Ende (T-Steg).
  - Im Süden liegt der schräge Steg mit Boxen und Booten auf beiden Seiten. Am Ende steht ein kleines Häuschen, dahinter ein weißer Schwimmsteg (Diagonalsteg).
  - Dazwischen liegen kleine Stege am Ufer. Am Land liegen Boote (blau/weiß) in Reihen.
  - Gebäude stehen am Hang westlich der Rasenfläche. Ein Weg führt von Süden heran.
  - Der Hafen liegt in einer leichten Bucht, das Ufer biegt hier nach Osten aus.
- **Spiel heute:** Das Ufer ist am LSC glatt, dahinter flache Wiese. Die Stege passen ungefähr zum echten Bild. Weitere Waldstücke gibt es hinter dem Rasen.
- **Schilf:** Im Spiel stehen Schilfbüschel (`reedBelt`) im Flachwasser am Ufer. Sie bleiben im Neubau erhalten.
- **Zu prüfen im Neubau:** Das Häuschen am Ende des Diagonalstegs hat der Code heute nicht. Dort steht nur der Steg-Kopf.
