# Seekoje – Seekarten-Editor (Prototyp)

Webapp (PWA) für Gewässer- und Regattastrecken. Keine Navigationssoftware. Alle Dateien liegen im Hauptverzeichnis, keine Unterordner.

## Auf GitHub Pages veröffentlichen
1. Neues Repository anlegen (z. B. `seekoje`), alle Dateien dieses Ordners hochladen (Add file → Upload files).
2. Settings → Pages → Branch `main`, Ordner `/ (root)` → Save.
3. Nach ca. 1 Minute: `https://<name>.github.io/seekoje/`. Auf dem Handy „Zur Startseite hinzufügen“ bzw. „App installieren“.

Lokal testen: `python3 -m http.server 8080` im Ordner, dann http://localhost:8080.

## Dateien
`index.html` (enthält CSS, Code und Konfiguration; GeoSN-Einstellungen oben im Block `window.CFG`, es gibt keine separate config.js), `manifest.webmanifest`, `sw.js`, Icons (`icon-192.png`, `icon-512.png`, `icon-maskable-512.png`, `apple-touch-icon.png`).

## Neues Projekt & Autosave
- **＋ Neu** (Leiste) bzw. **＋ Neues Projekt** (Panel „Projekt“): Name eingeben, Ort per Namenssuche (OSM-Nominatim, nur auf Knopfdruck/Enter) oder als „Breite, Länge“ (z. B. `51.27, 12.33`) wählen, oder „Aktuellen Kartenausschnitt nehmen“. Das alte Projekt kann vorher als JSON gesichert werden (Haken ist voreingestellt). Danach ist „💧 See wählen“ aktiv: auf die Wasserfläche tippen.
- Der Projektname steht in der Leiste, im Seitentitel, in den Dateinamen (`<name>.json`, `<name>-spiel.json`) und im Spiel-Export (`project`, `origin_wgs84`).
- **Autosave:** Der letzte Stand wird automatisch im Browser (IndexedDB) abgelegt und beim nächsten Start wiederhergestellt. Das ist ein Sicherheitsnetz, kein Archiv: wichtige Stände weiterhin mit „Speichern (JSON)“ sichern. Autosave gilt pro Browser/Gerät.
- Die geschätzte Cospudener-Ellipse erscheint nur noch beim allerersten Start.

## Prüfen & Spiel-Export (Block A)
- **Daten prüfen** (Panel „Umgebung & Gelände“): meldet fehlendes Gewässer, geschätzte Platzhalter, sich selbst schneidende Ufer, kleine Inseln, Tonnen an Land, fehlende Startlinie, fehlenden Wasserspiegel, fehlende Umgebung/Höhen/Tiefen.
- **Spiel-Export** enthält jetzt `water`: je Gewässerteil `outer` (gegen den Uhrzeigersinn) und `islands` (im Uhrzeigersinn) in Metern, mit der gewählten **Ufer-Vereinfachung** (Douglas-Peucker, 1 m Standard), dazu `mask`-Metadaten.
- **Wasser-Maske .png**: Norden oben, weiß = Wasser, schwarz = Land, Pixelgröße = „Rasterweite“ (max. 4096 px), Ursprung = SW-Ecke wie im Spiel-Export.
- Overpass-Abrufe fallen bei Überlast (429/504) automatisch auf Ausweichserver zurück (`CFG.overpassAlt`).

## Wind, Windabschattung, Bahn-Assistent (Block B)
- **Windstatistik laden (Open-Meteo)**: 5 volle Jahre stündlich (ERA5, ca. 25 km Raster, CC BY 4.0, nur nicht-kommerziell), am Kartenmittelpunkt. Ergebnis: 16 Sektoren (Häufigkeit, Ø m/s, Flaute) für das ganze Jahr und für die Segelsaison Apr–Okt, plus Hauptwindrichtung. Im Spiel-Export unter `wind`, im Projekt gespeichert. Regionalwerte, keine Messung am See.
- **Höhen für Windschatten**: Jedes Umgebungsobjekt im Export hat `h_m` und `h_src` (`tag` aus OSM-`height`, `levels` = `building:levels` × 3 m, sonst `default`). Standardwerte für Wald (15 m) und Gebäude (8 m) im Panel einstellbar; Einzelbaum 8 m, Gebüsch 2 m.
- **Regattabahn (Assistent)**: Form (Up-and-Down, mit Ablauftonne, mit Leetor, Dreieck), Windrichtung (woher), Schenkellänge, Startlinienbreite eingeben, dann „Bahn auf Karte setzen“ und die Mitte der Startlinie antippen (oder „In Kartenmitte“). Erzeugt Start-/Ziellinie, Tonnen und Kurslinie als Gruppe. Tonnen werden an Backbord gerundet; Dreieck ist gleichseitig; Leetor liegt 0,12 × Schenkel unterhalb der Startlinie. Werte sind Vorschläge – danach nach Bedarf anpassen.

## Tiefenschätzung (Block C)
Panel „Messdaten & Profil“ → **Tiefe aus Ufer-Abstand schätzen**: Tiefe = Abstand zum Ufer × Neigung (Standard 12 %), begrenzt auf die Maximaltiefe (Standard 8 m), im Raster (Standard 25 m, bei großen Seen automatisch gröber). Inseln zählen als Ufer. Gedacht für Seen ohne Lotungen; alles ist als „Modellschätzung – KEINE Messung“ gekennzeichnet (Projekt, Export: `depthEstimated`, `depthSource`, Datenprüfung). Tiefenlinien mit Tiefenwert haben Vorrang (Schätzpunkte im Umkreis von 40 m werden ausgelassen). Vorhandene Lotungen werden nur nach Rückfrage ersetzt.

## Rechtliche Namensnennung & Revierkarte (Block D/E)
- Panel **„Quellen & Lizenzen (Namensnennung)“** zeigt automatisch die für dieses Projekt nötigen Nennungen (OSM/ODbL, OpenSeaMap-Seezeichen, Open-Meteo/ERA5, Copernicus DEM; Höhenquellen aus Dateien nur als Hinweis). Eigene Zeilen unter „Weitere Quellen“ (im Projekt gespeichert).
- **Namensnennung .txt** liefert den fertigen Credits-Text für das Spiel plus Hinweise zu ODbL (Produced Work vs. abgeleitete Datenbank) und Open-Meteo (nur nicht-kommerziell). Keine Rechtsberatung.
- Alle Exporte tragen die Nennung: Spiel-Export, Projekt-JSON, Objekte-/Umgebungs-GeoJSON (`attribution`, `license_note`), GPX (`<metadata><copyright>`).
- **Revierkarte .png** zeichnet Gewässer, Umgebung (falls geladen), Objekte, Tonnen, Maßstab, Nord- und Windpfeil; die Namensnennung steht in der Fußzeile des Bildes.
- Die Wasser-Maske (PNG) kann keinen Text tragen: Nennung steht im Spiel-Export und in der .txt.
- Im Spiel selbst muss die Nennung sichtbar sein (Credits/Info-Bildschirm).

## Daten & Lizenz
- Karte: OpenStreetMap (ODbL), Seezeichen: OpenSeaMap. Die OSM-Standardkacheln sind nur für leichte Nutzung gedacht ([Tile Usage Policy](https://operations.osmfoundation.org/policies/tiles/)); für viel Verkehr eigenen Kachelserver in `window.CFG.tiles` (index.html) eintragen.
- „OSM-Daten für Ausschnitt laden“ nutzt Overpass (ab Zoom 14), nur lesbar.
- GeoSN-Luftbild/Gelände: WMS-URL, Layer und Lizenz selbst in `window.CFG.geosn` (index.html) eintragen; leer = deaktiviert.
- LMBV-Tiefenkarte (04/2018): nicht eingebunden, nur visuelle Referenz.
- Startgewässer ist eine **geschätzte Ellipse** (Mittelpunkt Wikipedia, Fläche 4,36 km²), kein echter Uferverlauf: mit „OSM laden“ als Vorlage nachzeichnen.
- Keine API-Schlüssel im Frontend. Bibliotheken: Leaflet (BSD-2), Leaflet-Geoman (MIT), proj4js (MIT).

## Formate
Projekt-JSON, GeoJSON (EPSG:4326), GPX (Wegpunkte, Routen). Messungen in EPSG:25833.

## Messdaten & Profile
- **Tiefenlinien**: Typ „Tiefenlinie“ zeichnen (z. B. nach dem LMBV-Bild, Stand 04/2018) und im Panel die Tiefe in m eintragen. Ohne Tiefenwert wird die Linie ignoriert.
- **CSV/XYZ laden**: Art „Tiefe“ (Lotungen) oder „Höhe“ (z. B. GeoSN-DGM als XYZ). Spalten: WGS84 Breite;Länge;Wert oder UTM33 E;N;Wert (Zonenpräfix 33 wird erkannt). Kopfzeile mit lat/lon/tiefe/x/y/z wird erkannt. Höhen werden auf 10-m-Zellen ausgedünnt (max. 400 000). GeoTIFF wird nicht gelesen: vorher z. B. mit QGIS/GDAL in XYZ-Text umwandeln.
- **Profil (Schnitt)**: Typ „Profil“ zeichnen → Diagramme Höhe und Tiefe, CSV-Export. Werte nur dort, wo Daten vorliegen; Tiefen sind interpoliert und geschätzt. Wasserspiegel nicht vorbelegt (leer lassen, wenn unbekannt).

## Automatische Umrandung
Flächen mit gesetztem „Uferlinie auto“ (bei Typ „Gewässer“ standardmäßig an) bekommen eine abgeleitete Uferlinie, die bei Verschieben, Bearbeiten, Drehen und Skalieren nachgeführt wird (nach dem Loslassen).

## Gewässer aus OSM übernehmen
„💧 See wählen“ antippen, dann auf eine Wasserfläche tippen: Der Editor fragt per Overpass die OSM-Wasserfläche an dieser Stelle ab (auch Seen mit Inseln), zeigt sie gelb an und übernimmt sie nach Bestätigung als Gewässer mit automatischer Uferlinie und Infos (Name, OSM-ID, Tags, Fläche, Abrufdatum, Lizenz). Grundlage sind OSM-Vektordaten, keine Farberkennung der Karte; ist ein Gewässer in OSM nicht erfasst, wird nichts gefunden.

## Tonnen
Typ „Boje / Tonne“ setzen; im Panel Form (Tonne, Spitz-, Kugel-, Säulen-, Spieren-, Fasstonne, Raute, Quadrat), Größe und Farbe (Schnellwahl oder freie Farbe) wählen. „Tonnen übernehmen“ lädt vorhandene OSM/OpenSeaMap-Seezeichen im Kartenausschnitt (ab Zoom 13) als Objekte mit Name, Farbe, Form und OSM-Tags; bereits übernommene werden übersprungen.

## Import
Der Import-Button liest GeoJSON, GPX (Wegpunkte, Routen, Tracks) und KML (Punkt, Linie, Fläche). OSM-XML (.osm) wird nicht gelesen; dafür „OSM-Daten für Ausschnitt laden“ bzw. „See wählen“ nutzen.

## Wasserspiegel aus OSM
Hat ein übernommenes Gewässer den OSM-Tag `ele`, bietet der Editor an, ihn als Wasserspiegel für Profile zu setzen (auch nachträglich per Button im Eigenschaftenpanel). Der Wert ist eine ungeprüfte OSM-Angabe.

## Umgebung (1 km) & Höhen für das Spiel
1. See übernehmen („💧 See wählen“), dann **„Umgebung 1 km laden (OSM)“**: lädt ein Rechteck mit 1 km Rand um den Seeumriss (max. 40 km²). Jedes Objekt bekommt eine Klasse (`water, waterway, forest, scrub, grass, farmland, wetland, beach, urban, building, road, path, rail, harbor, tree, other`) plus die OSM-Tags. Wird im Projekt-JSON mitgespeichert.
2. **Höhen genau:** GeoSN-DGM1 (1 m, XYZ-Textdateien, ETRS89/UTM33) aus dem Sächsischen „Portal Offene Geodaten“ laden (Kacheln 2×2 km; für See + 1 km meist mehrere). Im Editor unter „Messdaten“: Art „Höhe“, Koordinaten „UTM33“, Rasterweite wählen, Dateien auswählen (mehrere möglich). Große Dateien werden gestreamt und in das Raster gemittelt, nur der Gebietsausschnitt bleibt im Speicher.
3. **Höhen grob (Vorschau):** „Höhen grob laden (90 m)“ ruft Copernicus DEM GLO-90 über Open-Meteo ab (CC BY 4.0, kostenlos nur nicht-kommerziell, Namensnennung nötig; Oberflächenmodell, für Ufergestaltung zu grob).
4. **Export:** „Umgebung GeoJSON“ (WGS84), „Spiel-Export (m)“ (JSON in Metern, UTM33, Ursprung SW-Ecke: Objekte, Tonnen, Uferlinien, Tiefenpunkte, Umgebung), „Höhen .asc“ (ESRI-ASCII-Grid, EPSG:25833, Norden oben) und „Höhen .r16“ (16-Bit-RAW little-endian, Norden oben; 0 = Minimum, 65535 = Maximum, Werte stehen im Dateinamen).
Hinweise: Höhenraster werden als Uint16 (5-cm-Stufen) im Projekt gespeichert. Für Unity/Unreal muss das RAW ggf. auf 2^n+1 skaliert werden. Das DGM1 ist ein Geländemodell ohne Gebäude/Bäume; die Seetiefe ist darin nicht enthalten.
