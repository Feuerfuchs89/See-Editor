#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Seekoje – Revier-Bauer
======================
Baut aus offenen Daten ein Küstenrevier (z. B. Hiddensee – Kubitzer Bodden – Strelasund)
für die Revierkarte und das Spiel. Läuft als GitHub Action (Datei .github/workflows/revier.yml)
oder lokal:   python revier_bauen.py hiddensee

Quellen
- Küstenlinie, Umgebung, Seezeichen: OpenStreetMap / OpenSeaMap, Landesauszug von Geofabrik,
  zugeschnitten mit osmium-tool (ODbL)
- Wassertiefe: EMODnet Digital Bathymetry (DTM), WCS, ca. 115 m Raster (CC BY 4.0)
- Gelände: Copernicus DEM GLO-30 (Oberflächenmodell, 30 m), AWS Open Data

Ausgabe (alles im Hauptordner, Präfix = Reviername):
  <r>-revier.json      Metadaten, Wasser (Außenring + Inseln, Meter), Land, Seezeichen, Raster-Infos
  <r>-gelaende.bin     Höhen/Tiefen-Raster int16 little-endian in cm (NHN ≈ Mittelwasser), Zeile 0 = Norden
  <r>-umgebung.json    Umgebung (Wald, Häuser, Straßen, Häfen, Orte …) kompakt in Metern
  <r>-maske.png        Wasser-Maske (weiß = Wasser), Norden oben
  <r>-vorschau.png     Übersichtsbild
  <r>-namensnennung.txt
Koordinaten: EPSG:25833 (UTM 33), Meter, Ursprung = Südwest-Ecke des Reviers, x = Ost, y = Nord.
KEINE Navigationskarte.
"""
import argparse, io, json, math, os, sys, time, datetime

import numpy as np
import requests
from PIL import Image, ImageDraw

# ------------------------------------------------------------------ Reviere
REVIERE = {
    'hiddensee': dict(
        name='Hiddensee · Kubitzer Bodden · Strelasund',
        # Länge/Breite: West, Süd, Ost, Nord  (Stralsund/Rügendamm bis Dornbusch/Bessin, westlich um Hiddensee)
        bbox=(12.95, 54.28, 13.30, 54.64),
        zelle=20,        # Gelände-/Tiefenraster in m
        maske=5,         # Wasser-Maske in m
        ufer_tol=1.0,    # Ufer-Vereinfachung (Douglas-Peucker) in m
        hang=0.10,       # max. Unterwasser-Neigung am Ufer (Glättung der 115-m-Tiefen), 0 = aus
        osm='https://download.geofabrik.de/europe/germany/mecklenburg-vorpommern-latest.osm.pbf',
        regatten=['Blaues Band vom Strelasund (Stralsund → Neuendorf/Hiddensee)', 'Rund Hiddensee'],
        spiel=dict(zelle=40, kachel=400),
    ),
    'usedom': dict(
        name='Usedom · Stettiner Haff · Peenestrom (ab dem Ruden)',
        spielname='Usedom · Haff · Peenestrom',
        # vom Ruden über Peenestrom, Achterwasser, Usedom-Außenküste bis Swinemünde, Kleines Haff mit Anklam, Mönkebude, Ueckermünde
        bbox=(13.60, 53.70, 14.32, 54.23),
        zelle=40, maske=10, ufer_tol=1.5, hang=0.10,
        umgebung_schlank=True,
        osm=['https://download.geofabrik.de/europe/germany/mecklenburg-vorpommern-latest.osm.pbf',
             'https://download.geofabrik.de/europe/poland/zachodniopomorskie-latest.osm.pbf'],
        regatten=['Peenestrom–Haff', 'Ruden → Wolgast'],
        spiel=dict(zelle=40, kachel=400, haeuser_je_kachel=9000),
    ),
    'rostock': dict(
        name='Rostock · Warnemünde · Unterwarnow',
        spielname='Rostock · Warnemünde',
        # Stadthafen Rostock, Unterwarnow, Breitling, Seekanal, Warnemünde, Hohe Düne, Ostsee von Nienhagen bis Markgrafenheide
        bbox=(11.95, 54.07, 12.25, 54.27),
        zelle=40, maske=10, ufer_tol=1.5, hang=0.10,
        umgebung_schlank=True,
        osm='https://download.geofabrik.de/europe/germany/mecklenburg-vorpommern-latest.osm.pbf',
        regatten=['Warnow-Regatta (Stadthafen → Warnemünde)', 'Warnemünder Woche'],
        spiel=dict(zelle=40, kachel=400, haeuser_je_kachel=9000),
    ),
    'ruegen': dict(
        name='Rügen · Hiddensee · Strelasund · Greifswalder Bodden · Peenestrom',
        spielname='Rügen · Bodden · Peenestrom',
        # ganze Insel mit Hiddensee, Stralsund, Greifswalder Bodden, Greifswalder Oie, Wolgast/Peenemünde
        bbox=(12.95, 54.03, 13.95, 54.71),
        zelle=40, maske=10, ufer_tol=1.5, hang=0.10,
        umgebung_schlank=True,   # Revierkarte ohne Gebäude/Fußwege (Gebäude in <r>-gebaeude.json und in den Spielkacheln)
        osm='https://download.geofabrik.de/europe/germany/mecklenburg-vorpommern-latest.osm.pbf',
        regatten=['Blaues Band vom Strelasund', 'Rund Hiddensee'],
        spiel=dict(zelle=40, kachel=400, haeuser_je_kachel=9000),
    ),
}

# Fertige Kurse (Länge/Breite) – die Bahn wird automatisch durch Wasser ab 1,5 m gelegt
KURSE_HIDDENSEE = {
    'bb': dict(name='Blaues Band vom Strelasund', kurz='Stralsund → Neuendorf',
               start=(13.10359, 54.32544), ziel=(13.09998, 54.52368), ziel_name='Ziel Neuendorf (Hiddensee)'),
    'rund': dict(name='Rund Hiddensee', kurz='Neuendorf → Gellenstrom → Westseite → Dornbusch → Libben → Neuendorf',
                 start=(13.10196, 54.52084), start_r=800,
                 anker=[(13.05774, 54.46944), (13.03755, 54.53653), (13.12619, 54.62602), (13.17356, 54.60607)],
                 ziel=(13.09998, 54.52368), ziel_name='Ziel Neuendorf (Hiddensee)'),
}
REVIERE['hiddensee']['kurse'] = KURSE_HIDDENSEE
REVIERE['hiddensee']['bahnen'] = {'bahn': dict(name='Regattabahn vor Hiddensee (Westseite)', nahe=(13.01378, 54.54522), r=4000)}
REVIERE['ruegen']['kurse'] = KURSE_HIDDENSEE
REVIERE['ruegen']['bahnen'] = {
    'bahn': dict(name='Regattabahn vor Hiddensee (Westseite)', nahe=(13.01378, 54.54522), r=4000),
    'bahn_gb': dict(name='Regattabahn Greifswalder Bodden', nahe=(13.55, 54.20), r=7000),
    'bahn_pr': dict(name='Regattabahn Prorer Wiek (vor Binz)', nahe=(13.66, 54.43), r=4000),
}
# Leuchtfeuer, die in OSM fehlen könnten (Angaben: Lighthouse Directory, ibiblio.org/lighthouse)
REVIERE['ruegen']['feuer_extra'] = [
    dict(name='Leuchtfeuer Arkona', pos=(13.43266, 54.67954), turm=35, h=75,
         f=dict(c='Fl', g='3', p=17, s='0.3+(3.7),0.3+(3.7),0.3+(8.7)', k='white', r=22)),
    dict(name='Greifswalder Oie', pos=(13.92401, 54.24898), turm=39, h=49,
         f=dict(c='Fl', p=3.8, s='0.3+(3.5)', k='white', r=22)),
    dict(name='Dornbusch', pos=(13.11941, 54.59913), h=95,
         f=dict(c='LFl', p=10, s='2.4+(7.6)', k='white', r=24)),
]
# Häfen mit feinem Ausschnitt (4 m) für Kais, Molen und Stege
REVIERE['ruegen']['bruecken'] = [
    # Rügenbrücke (2007): Schrägseilbrücke, Pylon 128 m, Hauptfelder 126 m + 198 m, Durchfahrtshöhe 42 m
    dict(name='Rügenbrücke', art='schraegseil', bbox=(13.093, 54.298, 13.137, 54.321), wahl=dict(s=['trunk']),
         pylon_osm='Rügenbrücke', felder=[126, 198], hoehe=45, pylon_h=128),
    # Rügendamm (1936) mit Ziegelgrabenbrücke (Klappbrücke); Öffnungszeiten laut BOOTE/YACHT 2025, je 20 min
    dict(name='Rügendamm', art='damm', bbox=(13.093, 54.298, 13.137, 54.321), wahl=dict(n='Rügendamm'), hoehe=6,
         klappe=dict(name='Ziegelgrabenbrücke', breite=32, zeiten=['05:20', '08:20', '12:20', '15:20', '17:20', '21:30'], dauer=20)),
    # Peenebrücke Wolgast (1997): Klapp-/Wippbrücke für Straße B 111 und Bahn, 256 m, Klappe 42 m, Durchfahrt 30,75 m breit (mageba);
    # Öffnungen 16.3.–15.10. laut YACHT, außerhalb davon unbekannt – hier ganzjährig angenommen
    dict(name='Peenebrücke Wolgast', art='klapp', bbox=(13.7775, 54.0512, 13.7942, 54.0586),
         wahl=dict(n=['Peenebrücke', 'Peenemünder Straße', 'Straße der Freundschaft'], s=['primary']), hoehe=6,
         klappe=dict(name='Peenebrücke Wolgast', osm='Peenebrücke Wolgast', laenge=42, breite=19, art='wippe', dauer=15,
                     zeiten=['05:45', '07:45', '12:45', '17:45', '20:45', dict(z='23:45', von=[6, 1], bis=[9, 30])])),
]
# Hängebrücke Sassnitz (2007): Fußgängerbrücke, 243 m, Hauptfeld 119 m, gekrümmt, ein Mast (Structurae)
REVIERE['ruegen']['wahrzeichen_neu'] = [
    dict(n='Hängebrücke Sassnitz', art='haengebruecke', pos=(13.642122, 54.513219), l=243, feld=119, mast=38),
    # Slawischer Burgwall Jaromarsburg am Kap Arkona (Wall quer über das Kap, bis 13 m hoch)
    dict(n='Burgwall Jaromarsburg', art='burgwall', pos=(13.43654, 54.67708), r=190, h=11),
]
# Stralsund: Speicher auf der Hafeninsel (Backstein, Steildach, Treppengiebel)
REVIERE['ruegen']['speicher'] = [dict(name='Hafeninsel Stralsund', bbox=(13.0949, 54.3114, 13.1008, 54.3152), min_flaeche=600, h=24)]
# Großschiffbahnen für Regatten mit bis zu 10 Gorch Focks: viel Platz (≥ 3 km frei) und ≥ 8 m Wassertiefe
REVIERE['ruegen']['bahnen']['bahn_gfs'] = dict(name='Großschiffbahn vor Sassnitz (Gorch Fock)', nahe=(13.74, 54.51), r=9000, tief=8, cap=6000, min_frei=3000, gross=True)
REVIERE['ruegen']['bahnen']['bahn_gft'] = dict(name='Großschiffbahn Tromper Wiek (Gorch Fock)', nahe=(13.45, 54.62), r=8000, tief=8, cap=6000, min_frei=3000, gross=True)
# Gorch Fock I fährt (im Spiel) vom Liegeplatz in Stralsund bis vor Hiddensee und zurück
REVIERE['ruegen']['schiffe'] = [dict(name='Gorch Fock', wz=r'Gorch Fock', ziel=(13.085, 54.495), ziel_name='vor Hiddensee (Gellen)', tief=4.0, kn=7),
    # Linienschiffe und Kutter (Fahrplan im Spiel, weichen Regattabahnen sowie Start und Ziel aus)
    dict(name='Hiddensee-Fähre', schiff='INSEL HIDDENSEE', typ='faehre', start=(13.1630, 54.5135), start_r=500, ziel=(13.1150, 54.5640), ziel_r=500, ziel_name='Vitte', tief=2.0, kn=10),
    dict(name='Ausflugsschiff Kreideküste', schiff='BINZ', typ='ausflug', start=(13.6440, 54.5105), start_r=600, ziel=(13.6950, 54.5720), ziel_r=900, ziel_name='vor dem Königsstuhl', tief=3.0, kn=9),
    dict(name='Bäderschiff Binz–Sellin', schiff='ADLER-MÖNCHGUT', typ='baeder', start=(13.6150, 54.4030), start_r=500, ziel=(13.6990, 54.3790), ziel_r=500, ziel_name='Seebrücke Sellin', tief=2.5, kn=9),
    dict(name='Fischkutter SAS 12', typ='kutter', start=(13.6420, 54.5110), start_r=600, ziel=(13.8000, 54.5600), ziel_r=1500, ziel_name='Fanggebiet', tief=4.0, kn=8),
]
# ------------------------------------------------------------------ Usedom
REVIERE['usedom']['kurse'] = {
    'haff': dict(name='Peenestrom–Haff (Wolgast → Ueckermünde)', kurz='Wolgast → Peenestrom → Zecheriner Brücke → Kleines Haff → Ueckermünde',
                 start=(13.7800, 54.0420), start_r=1200, anker=[(13.8560, 53.9550), (13.8380, 53.8750), (13.9500, 53.8050)],
                 ziel=(14.0600, 53.7500), ziel_name='Ziel Ueckermünde'),
    'ruden': dict(name='Ruden → Wolgast (Peenemündung)', kurz='Ruden → Peenemünde → Kröslin → Wolgast',
                  start=(13.7700, 54.1950), start_r=1500, anker=[(13.8000, 54.1350)], ziel=(13.7780, 54.0700), ziel_name='Ziel vor der Peenebrücke'),
}
REVIERE['usedom']['bahnen'] = {
    'bahn_haff': dict(name='Regattabahn Kleines Haff (vor Mönkebude)', nahe=(14.05, 53.81), r=6000),
    'bahn_achter': dict(name='Regattabahn Achterwasser', nahe=(13.97, 54.00), r=4000),
    'bahn_heringsdorf': dict(name='Regattabahn vor Heringsdorf (Ostsee)', nahe=(14.17, 53.98), r=5000),
    'bahn_ksc': dict(name='Regattabahn Peenestrom vor dem Kuttersegelclub (Mahlzow)', nahe=(13.7905, 54.0700), r=1500, min_frei=250, cap=700),
    'bahn_gfu': dict(name='Großschiffbahn Pommersche Bucht (Gorch Fock)', nahe=(14.05, 54.12), r=9000, tief=8, cap=6000, min_frei=3000, gross=True),
}
REVIERE['usedom']['haefen'] = [
    dict(name='Wolgast', mitte=(13.7750, 54.0530), groesse=2400),
    dict(name='Peenemünde', mitte=(13.76263, 54.14229), groesse=2400),
    dict(name='Ueckermünde', mitte=(14.0650, 53.7410), groesse=2400),
    dict(name='Mönkebude', mitte=(13.9700, 53.7750), groesse=1600),
]
REVIERE['usedom']['bruecken'] = [
    dict(name='Peenebrücke Wolgast', art='klapp', bbox=(13.7775, 54.0512, 13.7942, 54.0586),
         wahl=dict(n=['Peenebrücke', 'Peenemünder Straße', 'Straße der Freundschaft'], s=['primary']), hoehe=6,
         klappe=dict(name='Peenebrücke Wolgast', osm='Peenebrücke Wolgast', laenge=42, breite=19, art='wippe', dauer=15,
                     zeiten=['05:45', '07:45', '12:45', '17:45', '20:45', dict(z='23:45', von=[6, 1], bis=[9, 30])])),
    # Zecheriner Brücke (B 110) über den Peenestrom; Öffnungen laut YACHT 5.45, 8.45, 12.45, 16.45, 20.45 Uhr
    dict(name='Zecheriner Brücke', art='klapp', bbox=(13.815, 53.865, 13.860, 53.885), wahl=dict(s=['primary', 'secondary', 'trunk']), hoehe=6,
         klappe=dict(name='Zecheriner Brücke', osm='Zecheriner Brücke', laenge=40, breite=12, art='wippe', dauer=15,
                     zeiten=['05:45', '08:45', '12:45', '16:45', '20:45'])),
]

# ------------------------------------------------------------------ Rostock / Warnemünde
REVIERE['rostock']['kurse'] = {
    'warnow': dict(name='Warnow-Regatta (Stadthafen → Warnemünde → Ostsee)', kurz='Stadthafen Rostock → Unterwarnow → Breitling → Seekanal → Warnemünde → Ziel auf See',
                   start=(12.1250, 54.0985), start_r=600, anker=[(12.1060, 54.1340), (12.0930, 54.1720)], ziel=(12.0600, 54.2150), ziel_name='Ziel vor Warnemünde'),
    'heide': dict(name='Warnemünde → Markgrafenheide (Küstenkurs)', kurz='vor Warnemünde → entlang der Rostocker Heide → Ziel vor Markgrafenheide',
                  start=(12.0700, 54.2000), start_r=1500, anker=[(12.1300, 54.2150)], ziel=(12.1900, 54.2200), ziel_name='Ziel vor Markgrafenheide'),
}
REVIERE['rostock']['bahnen'] = {
    'bahn_warnemuende': dict(name='Regattabahn vor Warnemünde (Warnemünder Woche)', nahe=(12.0700, 54.2050), r=4000),
    'bahn_heide': dict(name='Regattabahn vor Markgrafenheide', nahe=(12.1600, 54.2150), r=4000),
    'bahn_breitling': dict(name='Regattabahn Breitling', nahe=(12.1250, 54.1550), r=1800, min_frei=300, cap=900),
    'bahn_gfr': dict(name='Großschiffbahn vor Warnemünde (Gorch Fock)', nahe=(12.1000, 54.2400), r=9000, tief=8, cap=6000, min_frei=2000, gross=True),
}
REVIERE['rostock']['haefen'] = [
    dict(name='Warnemünde · Alter Strom · Hohe Düne', mitte=(12.0930, 54.1800), groesse=2400),
    dict(name='Rostock Stadthafen', mitte=(12.1330, 54.0930), groesse=2400),
    dict(name='Überseehafen Fährterminal', mitte=(12.1030, 54.1510), groesse=2000),
]
REVIERE['rostock']['werften'] = [dict(name='Neptun Werft', re=r'Neptun', schrift='NEPTUN WERFT', schrift2='', kraene=3, abstand=70)]
# Kreuzfahrtschiff am Warnemünde Cruise Center (Liegeplatz wird am Kai gesucht)
REVIERE['rostock']['liegeschiffe'] = [dict(n='AIDAdiva', typ='aida', schiff='AIDAdiva', pos=(12.0925, 54.1775), r=600, L=252, B=32, tief=7.0)]
# Linienverkehr: Fähren nach Gedser und Trelleborg, Warnowfähre, Hafenrundfahrt (Modelle nach Maßen und Reedereifarben)
REVIERE['rostock']['schiffe'] = [
    dict(name='Scandlines Berlin (Rostock–Gedser)', schiff='BERLIN', typ='scandlines', start=(12.1040, 54.1525), start_r=500, ziel=(12.1500, 54.2650), ziel_r=1500, ziel_name='Kurs Gedser', tief=7.0, kn=18),
    dict(name='Scandlines Copenhagen (Rostock–Gedser)', schiff='COPENHAGEN', typ='scandlines_rotor', start=(12.1050, 54.1500), start_r=500, ziel=(12.1700, 54.2650), ziel_r=1500, ziel_name='Kurs Gedser', tief=7.0, kn=18),
    dict(name='Stena Skåne (Rostock–Trelleborg)', schiff='SKÅNE', typ='stena', start=(12.1070, 54.1480), start_r=600, ziel=(12.2200, 54.2650), ziel_r=1500, ziel_name='Kurs Trelleborg', tief=7.5, kn=16),
    dict(name='Warnowfähre Warnemünde–Hohe Düne', schiff='WARNOW', typ='warnow', start=(12.0905, 54.1745), start_r=250, ziel=(12.0985, 54.1745), ziel_r=250, ziel_name='Hohe Düne', tief=3.0, kn=5),
    dict(name='Hafenrundfahrt Warnemünde–Stadthafen', schiff='HANSE', typ='ausflug', start=(12.0870, 54.1790), start_r=400, ziel=(12.1300, 54.0960), ziel_r=500, ziel_name='Stadthafen Rostock', tief=2.5, kn=9),
]

# Wolgast: Peene-Werft und Kuttersegelclub Blau-Weiß Wolgast in Mahlzow (Lage des Vereinshauses aus OSM-Gebäude und Luftbild)
WOLGAST_WERFT = dict(name='Peene-Werft', re=r'Peene[- ]?Werft', schrift='PEENE-WERFT', schrift2='LÜRSSEN', kraene=5, abstand=60, yacht='Yacht in der Ausrüstung', yacht_l=85)
KSC_WOLGAST = dict(n='Kuttersegelclub Blau-Weiß Wolgast', art='verein', pos=(13.79932, 54.06302), rect=(-12, -18, 10, 16), h=9)
KSC_HAFEN = dict(name='Kuttersegelclub Wolgast (Mahlzow)', mitte=(13.7999, 54.0626), groesse=800, tiefe=2.0)
REVIERE['usedom']['werften'] = [WOLGAST_WERFT]
REVIERE['usedom']['wahrzeichen_neu'] = [KSC_WOLGAST]
REVIERE['usedom']['haefen'].append(KSC_HAFEN)

# Kreideküste Jasmund (Sassnitz – Königsstuhl – Lohme): feines Raster, Kliffs aus OSM natural=cliff
REVIERE['ruegen']['kliffs'] = [
    dict(name='Kreideküste Jasmund', bbox=(13.6099, 54.5197, 13.6788, 54.5863), zelle=6),
    dict(name='Kreideküste Kap Arkona', bbox=(13.4113, 54.6604, 13.4490, 54.6869), zelle=6),
]
REVIERE['ruegen']['haefen'] = [
    dict(name='Stralsund', mitte=(13.09864, 54.31611), groesse=2800),
    dict(name='Sassnitz', mitte=(13.64112, 54.50949), groesse=2400),
    dict(name='Mukran (Fährhafen Sassnitz)', mitte=(13.58957, 54.48149), groesse=2400),
    dict(name='Peenemünde', mitte=(13.76263, 54.14229), groesse=2800),
    dict(name='Wolgast', mitte=(13.7750, 54.0530), groesse=2400),
    KSC_HAFEN,
]
REVIERE['ruegen']['werften'] = [WOLGAST_WERFT]
REVIERE['ruegen']['wahrzeichen_neu'].append(KSC_WOLGAST)

EMODNET_WCS = 'https://ows.emodnet-bathymetry.eu/wcs'
COP30 = 'https://copernicus-dem-30m.s3.amazonaws.com/{n}/{n}.tif'
UA = {'User-Agent': 'Seekoje-Revierbauer/1.0 (github.com/Feuerfuchs89; Segelsimulation, nicht kommerziell)'}

ATTRIBUTION = [
    '© OpenStreetMap-Mitwirkende, ODbL 1.0 (openstreetmap.org/copyright)',
    'Seezeichen: OpenSeaMap (aus OpenStreetMap, ODbL)',
    'Wassertiefe: EMODnet Bathymetry Consortium, EMODnet Digital Bathymetry (DTM), CC BY 4.0',
    'Gelände: Copernicus DEM GLO-30 © DLR e.V. 2010–2014 und © Airbus Defence and Space GmbH 2014–2018, '
    'bereitgestellt im Rahmen von COPERNICUS durch die Europäische Union und ESA',
]
WARN = []


def log(*a):
    print(*a, flush=True)


def warn(t):
    WARN.append(t)
    log('WARNUNG:', t)


# ------------------------------------------------------------------ UTM 33 (ETRS89/GRS80), Krüger-Reihen
_A, _F = 6378137.0, 1 / 298.257222101
_N = _F / (2 - _F)
_AA = _A / (1 + _N) * (1 + _N ** 2 / 4 + _N ** 4 / 64)
_AL = [_N / 2 - 2 * _N ** 2 / 3 + 5 * _N ** 3 / 16, 13 * _N ** 2 / 48 - 3 * _N ** 3 / 5, 61 * _N ** 3 / 240]
_BE = [_N / 2 - 2 * _N ** 2 / 3 + 37 * _N ** 3 / 96, _N ** 2 / 48 + _N ** 3 / 15, 17 * _N ** 3 / 480]
_DE = [2 * _N - 2 * _N ** 2 / 3 - 2 * _N ** 3, 7 * _N ** 2 / 3 - 8 * _N ** 3 / 5, 56 * _N ** 3 / 15]
_E = 2 * math.sqrt(_N) / (1 + _N)
_K0, _E0, _L0 = 0.9996, 500000.0, math.radians(15.0)


def utm(lon, lat):
    lon = np.radians(np.asarray(lon, float)); lat = np.radians(np.asarray(lat, float))
    s = np.sin(lat)
    t = np.sinh(np.arctanh(s) - _E * np.arctanh(_E * s))
    dl = lon - _L0
    xi = np.arctan2(t, np.cos(dl)); eta = np.arctanh(np.sin(dl) / np.sqrt(1 + t * t))
    x = eta.copy(); y = xi.copy()
    for j, a in enumerate(_AL, 1):
        x = x + a * np.cos(2 * j * xi) * np.sinh(2 * j * eta)
        y = y + a * np.sin(2 * j * xi) * np.cosh(2 * j * eta)
    return _E0 + _K0 * _AA * x, _K0 * _AA * y


def geo(x, y):
    xi = np.asarray(y, float) / (_K0 * _AA); eta = (np.asarray(x, float) - _E0) / (_K0 * _AA)
    xi2 = xi.copy(); eta2 = eta.copy()
    for j, b in enumerate(_BE, 1):
        xi2 = xi2 - b * np.sin(2 * j * xi) * np.cosh(2 * j * eta)
        eta2 = eta2 - b * np.cos(2 * j * xi) * np.sinh(2 * j * eta)
    chi = np.arcsin(np.sin(xi2) / np.cosh(eta2))
    lat = chi.copy()
    for j, d in enumerate(_DE, 1):
        lat = lat + d * np.sin(2 * j * chi)
    lon = _L0 + np.arctan2(np.sinh(eta2), np.cos(xi2))
    return np.degrees(lon), np.degrees(lat)


# ------------------------------------------------------------------ Gebiet
class Gebiet:
    def __init__(self, bbox, zelle):
        w, s, e, n = bbox
        lo = np.array([w, e, e, w, (w + e) / 2, (w + e) / 2]); la = np.array([s, s, n, n, s, n])
        X, Y = utm(lo, la)
        # Rechteck in UTM um die Länge/Breite-Box, auf ganze Zellen gerundet
        self.ox = math.floor(X.min() / zelle) * zelle
        self.oy = math.floor(Y.min() / zelle) * zelle
        x1 = math.ceil(X.max() / zelle) * zelle
        y1 = math.ceil(Y.max() / zelle) * zelle
        self.W, self.H = x1 - self.ox, y1 - self.oy
        self.zelle = zelle

    def to_m(self, lon, lat):
        x, y = utm(lon, lat)
        return x - self.ox, y - self.oy

    def to_ll(self, x, y):
        return geo(np.asarray(x) + self.ox, np.asarray(y) + self.oy)

    def llbox(self, rand_m=0.0):
        xs = np.array([-rand_m, self.W + rand_m]); ys = np.array([-rand_m, self.H + rand_m])
        gx, gy = np.meshgrid(np.linspace(xs[0], xs[1], 9), np.linspace(ys[0], ys[1], 9))
        lo, la = self.to_ll(gx.ravel(), gy.ravel())
        return float(lo.min()), float(la.min()), float(lo.max()), float(la.max())


# ------------------------------------------------------------------ Netz mit Zwischenspeicher
class Netz:
    def __init__(self, cache, offline):
        self.cache = cache; self.offline = offline
        os.makedirs(cache, exist_ok=True)

    def _pfad(self, name):
        return os.path.join(self.cache, name)

    def datei(self, name, url, params=None, pflicht=False, nur_pfad=False):
        p = self._pfad(name)
        if os.path.exists(p):
            log(f'  {name}: aus Zwischenspeicher')
            return p if nur_pfad else open(p, 'rb').read()
        if self.offline:
            warn(f'offline: {name} fehlt im Zwischenspeicher')
            return None
        for v in range(3):
            try:
                log(f'  lade {name} …'); t0 = time.time()
                with requests.get(url, params=params, headers=UA, timeout=(20, 300), stream=True) as r:
                    if r.status_code == 200:
                        with open(p + '.teil', 'wb') as f:
                            for ch in r.iter_content(1 << 20):
                                f.write(ch)
                        if os.path.getsize(p + '.teil') > 1000:
                            os.replace(p + '.teil', p)
                            log(f'  {name}: {os.path.getsize(p) / 1e6:.1f} MB in {time.time() - t0:.0f} s')
                            return open(p, 'rb').read() if not nur_pfad else p
                    body = r.content[:200] if r.status_code != 200 else b''
                    log(f'  {url} → HTTP {r.status_code} {body!r}')
                    if r.status_code == 404:
                        break
            except Exception as ex:
                log(f'  {url} → {ex}')
            time.sleep(15 * (v + 1))
        if pflicht:
            raise RuntimeError(f'Download {name} fehlgeschlagen')
        return None


# ------------------------------------------------------------------ OSM: Geofabrik-Auszug + osmium
UMG_FILTER = [
    'nwr/landuse', 'nwr/natural=wood,scrub,heath,wetland,beach,sand,grassland,water,cliff,bare_rock',
    'w/building', 'w/highway=motorway,trunk,primary,secondary,tertiary,unclassified,residential,service,living_street,'
                  'motorway_link,trunk_link,primary_link,secondary_link,tertiary_link,track,path,footway,cycleway,bridleway,steps,pedestrian',
    'w/railway=rail', 'nwr/leisure=marina,slipway', 'nwr/man_made=pier,breakwater,groyne,quay,lighthouse,tower,bridge',
    'nwr/harbour', 'w/waterway=river,canal,stream,ditch,dock',
    'n/place=city,town,village,hamlet,isolated_dwelling,island,islet,locality,peninsula', 'n/natural=peak,cape']
TEILE = {'kueste': ['w/natural=coastline'], 'seezeichen': ['nwr/seamark:type'], 'umgebung': UMG_FILTER}


def osm_daten(netz, geb, cfg, mit_umgebung=True):
    """Liefert {'kueste': [...], 'seezeichen': [...], 'umgebung': [...]} als GeoJSON-Features."""
    import shutil, subprocess
    teile = [t for t in TEILE if mit_umgebung or t != 'umgebung']
    ziel = {t: netz._pfad(f'osm_{t}.geojsonseq') for t in teile}
    if not all(os.path.exists(v) for v in ziel.values()):
        if netz.offline:
            warn('offline: OSM-Auszüge fehlen im Zwischenspeicher – leer')
            return {t: (lies_seq(ziel[t]) if os.path.exists(ziel[t]) else []) for t in teile}
        if not shutil.which('osmium'):
            raise RuntimeError('osmium-tool fehlt (in der Action: sudo apt-get install -y osmium-tool)')
        log('OSM-Landesauszug (Geofabrik) laden …')
        urls = cfg['osm'] if isinstance(cfg['osm'], list) else [cfg['osm']]
        w, s, e, n = geb.llbox(3000)
        rev = netz._pfad('revier.osm.pbf')
        lauf = lambda *a: (log('  osmium ' + ' '.join(a[:2])), subprocess.run(['osmium', *a], check=True))
        teil_pbf = []
        for i, url in enumerate(urls):
            pbf = netz.datei('land.osm.pbf' if i == 0 else f'land{i}.osm.pbf', url, pflicht=True, nur_pfad=True)
            ziel_i = rev if len(urls) == 1 else netz._pfad(f'revier{i}.osm.pbf')
            lauf('extract', '-b', f'{w:.5f},{s:.5f},{e:.5f},{n:.5f}', '-s', 'smart', pbf, '-o', ziel_i, '--overwrite')
            teil_pbf.append(ziel_i)
        if len(teil_pbf) > 1:
            lauf('merge', *teil_pbf, '-o', rev, '--overwrite')
        konf = netz._pfad('nur_linien.json')
        json.dump({'linear_tags': True, 'area_tags': False}, open(konf, 'w'))
        for t in teile:
            f = netz._pfad(f'osm_{t}.osm.pbf')
            lauf('tags-filter', rev, *TEILE[t], '-o', f, '--overwrite')
            extra = ['-c', konf] if t == 'kueste' else []      # Küste als Linien: Wegrichtung (Land links) bleibt erhalten
            lauf('export', f, '-f', 'geojsonseq', '-x', 'print_record_separator=false', '-a', 'type,id', *extra, '-o', ziel[t], '--overwrite')
    out = {}
    for t in teile:
        out[t] = lies_seq(ziel[t]); log(f'  OSM {t}: {len(out[t])} Objekte')
    return out


def lies_seq(pfad):
    feats = []
    for z in open(pfad, encoding='utf-8'):
        z = z.strip().lstrip('\x1e')
        if z:
            feats.append(json.loads(z))
    return feats


def ringe_von(geom):
    """Polygon/MultiPolygon → Liste von Polygonen (je Liste von Ringen aus (lon,lat))."""
    if geom['type'] == 'Polygon':
        return [geom['coordinates']]
    if geom['type'] == 'MultiPolygon':
        return geom['coordinates']
    return []


# ------------------------------------------------------------------ Geometrie-Helfer
def dp(P, tol):
    """Douglas-Peucker für offene Linie (N,2)."""
    P = np.asarray(P, float)
    if tol <= 0 or len(P) < 3:
        return P
    keep = np.zeros(len(P), bool); keep[0] = keep[-1] = True
    st = [(0, len(P) - 1)]
    while st:
        i, j = st.pop()
        if j <= i + 1:
            continue
        a, b = P[i], P[j]; seg = P[i + 1:j]; ab = b - a; L2 = float(ab @ ab)
        if L2 == 0:
            d = np.hypot(*(seg - a).T)
        else:
            t = np.clip(((seg - a) @ ab) / L2, 0, 1)
            d = np.hypot(*(seg - (a + t[:, None] * ab)).T)
        k = int(np.argmax(d))
        if d[k] > tol:
            m = i + 1 + k; keep[m] = True; st += [(i, m), (m, j)]
    return P[keep]


def dp_ring(P, tol):
    P = np.asarray(P, float)
    if len(P) > 1 and np.allclose(P[0], P[-1]):
        P = P[:-1]
    if tol <= 0 or len(P) < 4:
        return P
    # an den zwei entferntesten Punkten teilen, damit der Ring stabil bleibt
    k = int(np.argmax(np.hypot(*(P - P[0]).T)))
    a = dp(P[:k + 1], tol); b = dp(np.vstack([P[k:], P[:1]]), tol)
    R = np.vstack([a[:-1], b[:-1]])
    return R if len(R) >= 3 else P


def flaeche(P):
    P = np.asarray(P, float); x, y = P[:, 0], P[:, 1]
    return 0.5 * float(np.dot(x, np.roll(y, -1)) - np.dot(y, np.roll(x, -1)))


def im_poly(pt, P):
    x, y = pt; P = np.asarray(P, float); xi, yi = P[:, 0], P[:, 1]; xj, yj = np.roll(xi, 1), np.roll(yi, 1)
    c = ((yi > y) != (yj > y)) & (x < (xj - xi) * (y - yi) / np.where(yj - yi == 0, 1e-30, yj - yi) + xi)
    return bool(np.count_nonzero(c) % 2)


def ketten(wege, richtung_fest):
    """Wege (Listen von (lon,lat)) an gemeinsamen Endpunkten zu Ketten verbinden."""
    key = lambda p: (round(p[0], 7), round(p[1], 7))
    wege = [list(w) for w in wege if len(w) >= 2]
    frei = set(range(len(wege)))
    an_start, an_ende = {}, {}
    for i, w in enumerate(wege):
        an_start.setdefault(key(w[0]), []).append(i); an_ende.setdefault(key(w[-1]), []).append(i)
    def nimm(d, k, umgekehrt=False):
        for i in d.get(k, []):
            if i in frei:
                frei.discard(i); return wege[i][::-1] if umgekehrt else wege[i]
        return None
    out = []
    while frei:
        i = frei.pop(); c = list(wege[i])
        while key(c[-1]) != key(c[0]):
            w = nimm(an_start, key(c[-1]))
            if w is None and not richtung_fest:
                w = nimm(an_ende, key(c[-1]), True)
            if w is None:
                break
            c += w[1:]
        while key(c[-1]) != key(c[0]):
            w = nimm(an_ende, key(c[0]))
            if w is None and not richtung_fest:
                w = nimm(an_start, key(c[0]), True)
            if w is None:
                break
            c = w[:-1] + c
        out.append((c, key(c[-1]) == key(c[0])))
    return out


# ------------------------------------------------------------------ Küste → Land/Wasser
class Rechteck:
    def __init__(self, W, H):
        self.W, self.H = W, H; self.L = 2 * (W + H)
        self.ecken = [(0.0, (0.0, 0.0)), (W, (W, 0.0)), (W + H, (W, H)), (2 * W + H, (0.0, H))]

    def drin(self, p, eps=1e-6):
        return -eps <= p[0] <= self.W + eps and -eps <= p[1] <= self.H + eps

    def t(self, p):
        x, y = p; W, H = self.W, self.H
        d = [abs(y), abs(x - W), abs(y - H), abs(x)]
        k = int(np.argmin(d))
        return [min(max(x, 0), W), W + min(max(y, 0), H), W + H + (W - min(max(x, 0), W)), 2 * W + H + (H - min(max(y, 0), H))][k] % self.L

    def rand(self, p):
        x, y = p; W, H = self.W, self.H
        d = [abs(y), abs(x - W), abs(y - H), abs(x)]
        k = int(np.argmin(d)); x = min(max(x, 0), W); y = min(max(y, 0), H)
        return [(x, 0.0), (W, y), (x, H), (0.0, y)][k]

    def seg(self, p, q):
        x0, y0 = p; dx, dy = q[0] - x0, q[1] - y0; t0, t1 = 0.0, 1.0
        for pp, qq in ((-dx, x0), (dx, self.W - x0), (-dy, y0), (dy, self.H - y0)):
            if pp == 0:
                if qq < 0:
                    return None
            else:
                r = qq / pp
                if pp < 0:
                    t0 = max(t0, r)
                else:
                    t1 = min(t1, r)
        if t1 - t0 <= 1e-12:
            return None
        return t0, t1

    def clip(self, pts):
        """Linie an Rechteck schneiden → Teilstücke, die am Rand beginnen und enden."""
        stuecke, cur, innen_start = [], None, False
        lerp = lambda p, q, t: (p[0] + (q[0] - p[0]) * t, p[1] + (q[1] - p[1]) * t)
        for p, q in zip(pts, pts[1:]):
            c = self.seg(p, q)
            if c is None:
                if cur is not None:
                    stuecke.append(cur); cur = None
                continue
            t0, t1 = c
            if cur is None:
                if t0 == 0 and not self._aufrand(p):
                    innen_start = True
                cur = [lerp(p, q, t0)]
            cur.append(lerp(p, q, t1))
            if t1 < 1:
                stuecke.append(cur); cur = None
        if cur is not None:
            stuecke.append(cur)
        out = []
        for s in stuecke:
            s2 = [s[0]]
            for p in s[1:]:
                if abs(p[0] - s2[-1][0]) > 1e-6 or abs(p[1] - s2[-1][1]) > 1e-6:
                    s2.append(p)
            if len(s2) < 2:
                continue
            for ende in (0, -1):
                if not self._aufrand(s2[ende]):
                    warn(f'Küstenlinie endet im Revier bei x={s2[ende][0]:.0f} m, y={s2[ende][1]:.0f} m – an den Rand verlängert (Datenlücke in OSM?)')
                    r = self.rand(s2[ende])
                    if ende == 0:
                        s2.insert(0, r)
                    else:
                        s2.append(r)
            out.append(s2)
        return out

    def _aufrand(self, p, eps=0.01):
        return min(abs(p[0]), abs(p[0] - self.W), abs(p[1]), abs(p[1] - self.H)) <= eps

    def lauf(self, stuecke):
        """Teilstücke (Fläche jeweils links) über den Rand gegen den Uhrzeigersinn zu Ringen schließen."""
        S = [dict(p=s, a=self.t(s[0]), e=self.t(s[-1])) for s in stuecke]
        frei = set(range(len(S))); ringe = []
        while frei:
            st = frei.pop(); ring = list(S[st]['p']); cur = st; schutz = 0
            while True:
                schutz += 1
                if schutz > len(S) + 5:
                    warn('Ring konnte nicht geschlossen werden'); break
                te = S[cur]['e']
                nx = min(range(len(S)), key=lambda i: ((S[i]['a'] - te) % self.L) if (i in frei or i == st) else 1e30)
                ta = S[nx]['a']; d = (ta - te) % self.L
                for tc, pc in sorted(self.ecken, key=lambda c: (c[0] - te) % self.L):
                    dc = (tc - te) % self.L
                    if 0 < dc < d:
                        ring.append(pc)
                if nx == st:
                    break
                frei.discard(nx); ring += S[nx]['p']; cur = nx
            if len(ring) >= 3:
                ringe.append(ring)
        return ringe


def kueste(feats, geb, cfg):
    log('Küstenlinie verarbeiten …')
    wege = []
    for f in feats:
        g = f.get('geometry') or {}
        if g.get('type') == 'LineString':
            wege.append([tuple(c[:2]) for c in g['coordinates']])
        elif g.get('type') == 'MultiLineString':
            wege += [[tuple(c[:2]) for c in l] for l in g['coordinates']]
    log(f'  {len(wege)} Küstenwege')
    R = Rechteck(geb.W, geb.H)
    stuecke, insel, seen = [], [], []
    for c, zu in ketten(wege, True):
        lo, la = np.array(c).T; x, y = geb.to_m(lo, la); P = list(zip(x.tolist(), y.tolist()))
        if zu:
            innen = [R.drin(p) for p in P]
            if all(innen):
                (insel if flaeche(P) > 0 else seen).append(P); continue
            if any(innen) or any(R.seg(p, q) for p, q in zip(P, P[1:])):
                k = next((i for i, f in enumerate(innen) if not f), 0)   # Ring an einem Punkt außerhalb beginnen
                P = P[k:] + P[1:k + 1]
            else:
                if im_poly((geb.W / 2, geb.H / 2), P) and flaeche(P) > 0:
                    warn('Revier liegt komplett in einer Landfläche'); insel.append([(0, 0), (geb.W, 0), (geb.W, geb.H), (0, geb.H)])
                continue
        stuecke += R.clip(P)
    land = R.lauf(stuecke) + insel
    wasser_aussen = R.lauf([s[::-1] for s in stuecke]) if stuecke else [[(0.0, 0.0), (geb.W, 0.0), (geb.W, geb.H), (0.0, geb.H)]]
    wasser_aussen += [P[::-1] for P in seen]
    tol = cfg['ufer_tol']
    teile = []
    for A in wasser_aussen:
        A = dp_ring(A, tol)
        if abs(flaeche(A)) < 50:
            continue
        teile.append(dict(outer=A, islands=[]))
    for I in insel:
        I2 = dp_ring(I, tol)
        if abs(flaeche(I2)) < 5:
            continue
        for t in teile:
            if im_poly(I2[0], t['outer']):
                t['islands'].append(I2); break
    land = [dp_ring(L, tol) for L in land]
    land = [L for L in land if abs(flaeche(L)) >= 5]
    for t in teile:
        if flaeche(t['outer']) < 0: t['outer'] = t['outer'][::-1]
        t['islands'] = [I if flaeche(I) < 0 else I[::-1] for I in t['islands']]
    land = [L if flaeche(L) > 0 else L[::-1] for L in land]
    wf = sum(flaeche(t['outer']) + sum(flaeche(i) for i in t['islands']) for t in teile)
    log(f'  Wasser {wf / 1e6:.1f} km² in {len(teile)} Teil(en), {sum(len(t["islands"]) for t in teile)} Inseln, {len(land)} Landflächen')
    if not wege:
        warn('Keine Küstenlinie gefunden – das ganze Revier wird als Wasser behandelt')
    return teile, land, wf


def maske(teile, W, H, cs):
    w, h = int(math.ceil(W / cs)), int(math.ceil(H / cs))
    im = Image.new('L', (w, h), 0); dr = ImageDraw.Draw(im)
    f = lambda P: [(p[0] / cs, (H - p[1]) / cs) for p in P]
    for t in teile:
        dr.polygon(f(t['outer']), fill=255)
    for t in teile:
        for i in t['islands']:
            dr.polygon(f(i), fill=0)
    return im


# ------------------------------------------------------------------ GeoTIFF lesen (tifffile)
def geotiff(daten, grenzen=None):
    """GeoTIFF in Länge/Breite lesen. Unterstützt PixelScale+Tiepoint, ModelTransformation
    und als Notlösung die angefragten Grenzen (w, s, e, n)."""
    import tifffile
    with tifffile.TiffFile(io.BytesIO(daten)) as tf:
        pg = tf.pages[0]; a = pg.asarray().astype(np.float64)
        if a.ndim == 3:
            a = a[..., 0] if a.shape[-1] < a.shape[0] else a[0]
        tg = pg.tags
        namen = sorted(t.name for t in tg.values())
        punkt = False
        if 'GeoKeyDirectoryTag' in tg:
            g = tg['GeoKeyDirectoryTag'].value
            for k in range(4, len(g), 4):
                if g[k] == 1025 and g[k + 3] == 2:
                    punkt = True
        nod = None
        if 'GDAL_NODATA' in tg:
            try:
                nod = float(str(tg['GDAL_NODATA'].value).strip('\x00 '))
            except ValueError:
                pass
        ny, nx = a.shape
        if 'ModelPixelScaleTag' in tg and 'ModelTiepointTag' in tg:
            sx, sy = tg['ModelPixelScaleTag'].value[:2]
            tp = tg['ModelTiepointTag'].value; i0, j0, x0, y0 = tp[0], tp[1], tp[3], tp[4]
            ecke_lon, ecke_lat = x0 - i0 * sx, y0 + j0 * sy
        elif 'ModelTransformationTag' in tg:
            m = tg['ModelTransformationTag'].value          # lon = m0*col + m1*row + m3 ; lat = m4*col + m5*row + m7
            if abs(m[1]) > 1e-12 or abs(m[4]) > 1e-12:
                raise ValueError('gedrehtes Raster wird nicht unterstützt')
            sx, sy = m[0], -m[5]; ecke_lon, ecke_lat = m[3], m[7]
        elif grenzen:
            w, s, e, n = grenzen
            sx, sy = (e - w) / nx, (n - s) / ny; ecke_lon, ecke_lat = w, n; punkt = False
            warn(f'GeoTIFF ohne Lageangabe (Tags: {", ".join(namen)}) – Lage aus angefragtem Ausschnitt berechnet (±1 Pixel)')
        else:
            raise ValueError('keine Lageangabe im GeoTIFF, Tags: ' + ', '.join(namen))
        if sy < 0:      # Zeilen von Süd nach Nord
            a = a[::-1]; ecke_lat = ecke_lat + (-sy) * ny; sy = -sy
    if nod is not None:
        a[a == nod] = np.nan
    a[~np.isfinite(a)] = np.nan
    a[np.abs(a) > 20000] = np.nan
    # Pixelmittelpunkt-Koordinaten: lon = lon0 + col*sx, lat = lat0 - row*sy
    lon0 = ecke_lon + (0 if punkt else sx / 2); lat0 = ecke_lat - (0 if punkt else sy / 2)
    return dict(a=a, lon0=lon0, lat0=lat0, sx=sx, sy=sy)


def abtasten(r, lon, lat, sammel=None):
    """Bilinear, NaN-tolerant. Mit sammel=(acc, wsum) werden mehrere Kacheln nahtlos gemittelt."""
    a = r['a']; ny, nx = a.shape
    c = (lon - r['lon0']) / r['sx']; z = (r['lat0'] - lat) / r['sy']
    c0 = np.floor(c).astype(int); z0 = np.floor(z).astype(int); fc = c - c0; fz = z - z0
    out = np.full(lon.shape, np.nan)
    acc, wsum = sammel if sammel else (np.zeros(lon.shape), np.zeros(lon.shape))
    for dz, dc, wgt in ((0, 0, (1 - fz) * (1 - fc)), (0, 1, (1 - fz) * fc), (1, 0, fz * (1 - fc)), (1, 1, fz * fc)):
        zz = z0 + dz; cc = c0 + dc; ok = (zz >= 0) & (zz < ny) & (cc >= 0) & (cc < nx)
        v = np.full(lon.shape, np.nan); v[ok] = a[zz[ok], cc[ok]]
        g = np.isfinite(v) & (wgt > 0)
        acc[g] += v[g] * wgt[g]; wsum[g] += wgt[g]
    m = wsum > 0.25
    out[m] = acc[m] / wsum[m]
    return out


def fuellen(v, maske_ok):
    """NaN-Zellen (innerhalb maske_ok) mit nächstem gültigem Wert füllen."""
    from scipy import ndimage
    gut = np.isfinite(v)
    if not gut.any():
        return v
    idx = ndimage.distance_transform_edt(~gut, return_distances=False, return_indices=True)
    f = v[tuple(idx)]
    return np.where(maske_ok & ~gut, f, v)


# ------------------------------------------------------------------ Tiefe + Höhe
def gelaende(netz, geb, cfg, wasser_im):
    from scipy import ndimage
    cs = cfg['zelle']; nx, ny = geb.W // cs, geb.H // cs
    xs = (np.arange(nx) + 0.5) * cs; ys = geb.H - (np.arange(ny) + 0.5) * cs     # Zeile 0 = Norden
    gx, gy = np.meshgrid(xs, ys)
    lon, lat = geb.to_ll(gx, gy)
    wm = np.asarray(wasser_im.resize((nx, ny), Image.BILINEAR)) >= 128
    quellen = {}

    # --- Tiefe EMODnet
    w, s, e, n = geb.llbox(1500)
    log('EMODnet-Tiefen laden …')
    tiefe = np.full(gx.shape, np.nan)
    d = netz.datei('emodnet.tif', EMODNET_WCS, params={
        'SERVICE': 'WCS', 'VERSION': '2.0.1', 'REQUEST': 'GetCoverage', 'CoverageId': 'emodnet__mean',
        'SUBSET': [f'Lat({s:.5f},{n:.5f})', f'Long({w:.5f},{e:.5f})'], 'FORMAT': 'image/tiff'})
    if d:
        try:
            r = geotiff(d, (w, s, e, n)); tiefe = abtasten(r, lon, lat)
            log(f'  EMODnet: {r["a"].shape[1]}×{r["a"].shape[0]} Pixel, {np.isfinite(r["a"]).mean() * 100:.0f} % mit Werten')
            sw = tiefe[wm & np.isfinite(tiefe)]
            if sw.size and np.median(sw) > 0:
                tiefe = -tiefe; log('  Vorzeichen umgedreht (Tiefen positiv geliefert)')
            quellen['tiefe'] = 'EMODnet DTM (emodnet:mean, ca. 115 m), bilinear auf %d m' % cs
        except Exception as ex:
            warn(f'EMODnet-Datei nicht lesbar: {ex}')
    else:
        warn('Keine EMODnet-Tiefen – Tiefe wird aus Uferabstand geschätzt (Modell, KEINE Messung)')
    dist = ndimage.distance_transform_edt(wm) * cs        # Abstand zum Land in m (Wasserzellen)
    if not np.isfinite(tiefe[wm]).any():
        tiefe = -np.minimum(0.5 + dist * 0.02, 12.0)
        quellen['tiefe'] = 'Modellschätzung aus Uferabstand (2 %, max. 12 m) – KEINE Messung'
    tiefe = fuellen(tiefe, wm)
    tiefe = np.where(np.isfinite(tiefe), tiefe, -1.0)
    tiefe = np.minimum(tiefe, -0.3)
    if cfg.get('hang', 0) > 0:
        tiefe = np.maximum(tiefe, -(0.3 + dist * cfg['hang']))

    # --- Höhe Copernicus GLO-30
    log('Copernicus-Höhen laden …')
    hoehe = np.full(gx.shape, np.nan); ok = False
    acc, wsum = np.zeros(gx.shape), np.zeros(gx.shape)
    for la in range(int(math.floor(s)), int(math.floor(n)) + 1):
        for lo in range(int(math.floor(w)), int(math.floor(e)) + 1):
            nm = f'Copernicus_DSM_COG_10_{"N" if la >= 0 else "S"}{abs(la):02d}_00_{"E" if lo >= 0 else "W"}{abs(lo):03d}_00_DEM'
            dd = netz.datei(nm + '.tif', COP30.format(n=nm))
            if not dd:
                continue
            try:
                r = geotiff(dd); abtasten(r, lon, lat, (acc, wsum)); ok = True
            except Exception as ex:
                warn(f'{nm} nicht lesbar: {ex}')
    m = wsum > 0.25
    hoehe[m] = acc[m] / wsum[m]
    if ok:
        quellen['hoehe'] = 'Copernicus DEM GLO-30 (Oberflächenmodell inkl. Wald/Gebäude), bilinear auf %d m' % cs
    else:
        warn('Keine Geländehöhen – Land wird flach (1 m) angenommen')
        quellen['hoehe'] = 'keine Daten (flach 1 m)'
    hoehe = fuellen(hoehe, ~wm)
    hoehe = np.where(np.isfinite(hoehe), hoehe, 1.0)
    hoehe = np.maximum(hoehe, 0.3)

    z = np.where(wm, tiefe, hoehe)
    cm = np.clip(np.round(z * 100), -32767, 32767).astype('<i2')
    return cm, wm, quellen, (nx, ny)


# ------------------------------------------------------------------ Seezeichen
def feuer_def(t):
    """Alle Feuer-Angaben aus OpenSeaMap-Tags (seamark:light…) kompakt: Kennung, Gruppe, Periode, Folge, Farbe, Reichweite, Höhe, Sektoren."""
    L = {k[len('seamark:light:'):]: v for k, v in t.items() if k.startswith('seamark:light:')}
    if not L:
        return None
    num = lambda v: (float(str(v).replace(',', '.').split(';')[0].split()[0]) if v not in (None, '') else None)
    def eins(pre):
        g = lambda k: L.get(pre + k)
        d = dict(c=g('character'), g=g('group'), p=g('period'), s=g('sequence'), k=g('colour'), r=g('range'), h=g('height'),
                 a=g('sector_start'), e=g('sector_end'), o=g('orientation'), cat=g('category'))
        out = {}
        for k_, v in d.items():
            if v in (None, ''):
                continue
            if k_ in ('p', 'r', 'h', 'a', 'e', 'o'):
                try:
                    out[k_] = num(v)
                except ValueError:
                    pass
            else:
                out[k_] = str(v)[:40]
        return out
    f = eins('')
    sek = []
    for n in range(1, 25):
        if any(k.startswith(f'{n}:') for k in L):
            x = eins(f'{n}:')
            if x:
                sek.append(x)
    if sek:
        f['sek'] = sek
    return f if (f.get('c') or sek) else None


def seezeichen(feats, geb):
    log('Seezeichen verarbeiten …')
    pkt, lin = [], []
    for el in feats:
        t = el.get('properties', {}); typ = t.get('seamark:type', ''); g = el.get('geometry') or {}
        p = lambda k: t.get(f'seamark:{typ}:{k}', '')
        info = {k: v for k, v in dict(
            typ=typ, name=t.get('seamark:name') or t.get('name', ''), farbe=p('colour'), muster=p('colour_pattern'),
            form=p('shape'), kategorie=p('category'), toppzeichen=t.get('seamark:topmark:shape', ''),
            licht=' '.join(x for x in (t.get('seamark:light:character', ''), t.get('seamark:light:colour', ''),
                                       (t.get('seamark:light:period', '') + 's') if t.get('seamark:light:period') else '') if x),
            hoehe=t.get('height', ''), osm=f"{str(t.get('@type', 'x'))[:1]}{t.get('@id', '')}").items() if v}
        fd = feuer_def(t)
        if fd:
            info['feuer'] = fd
        if g.get('type') == 'Point':
            x, y = geb.to_m(*g['coordinates'][:2])
            if 0 <= x <= geb.W and 0 <= y <= geb.H:
                pkt.append({**info, 'x': round(float(x), 1), 'y': round(float(y), 1)})
            continue
        linien = [g['coordinates']] if g.get('type') == 'LineString' else g.get('coordinates', []) if g.get('type') == 'MultiLineString' \
            else [pl[0] for pl in ringe_von(g)]
        flaechig = g.get('type') in ('Polygon', 'MultiPolygon')
        for l in linien:
            if len(l) < 2:
                continue
            lo, la = np.array([c[:2] for c in l]).T; x, y = geb.to_m(lo, la)
            # Feuer, Leuchttürme und Landmarken auf Gebäudeflächen/Wegen auch als Punkt (Schwerpunkt) übernehmen
            if fd or typ.startswith('light') or typ == 'landmark' or flaechig and typ in ('beacon_lateral', 'beacon_special_purpose', 'beacon_cardinal'):
                cx, cy = float(np.mean(x)), float(np.mean(y))
                if 0 <= cx <= geb.W and 0 <= cy <= geb.H:
                    pkt.append({**info, 'x': round(cx, 1), 'y': round(cy, 1), 'aus': 'flaeche'})
                if flaechig:
                    continue
            lin.append({**info, 'p': [[round(a, 1), round(b, 1)] for a, b in zip(x.tolist(), y.tolist())]})
    log(f'  {len(pkt)} Seezeichen ({sum(1 for q in pkt if "feuer" in q)} mit Feuer), {len(lin)} Linien/Flächen')
    return pkt, lin


# ------------------------------------------------------------------ Umgebung
FL_NAT = {'wood': 'forest', 'scrub': 'scrub', 'heath': 'scrub', 'wetland': 'wetland', 'beach': 'beach', 'sand': 'beach',
          'grassland': 'grass', 'water': 'water', 'cliff': 'cliff', 'bare_rock': 'beach'}
FL_LU = {'forest': 'forest', 'farmland': 'farmland', 'meadow': 'grass', 'grass': 'grass', 'residential': 'urban',
         'commercial': 'urban', 'industrial': 'urban', 'retail': 'urban', 'allotments': 'grass', 'orchard': 'farmland',
         'farmyard': 'urban', 'harbour': 'harbor', 'port': 'harbor', 'recreation_ground': 'grass', 'cemetery': 'grass',
         'reservoir': 'water', 'basin': 'water', 'military': 'other', 'construction': 'urban', 'railway': 'urban',
         'village_green': 'grass', 'plant_nursery': 'farmland', 'vineyard': 'farmland', 'greenfield': 'grass', 'brownfield': 'urban'}
HW_ROAD = {'motorway', 'trunk', 'primary', 'secondary', 'tertiary', 'unclassified', 'residential', 'service', 'living_street',
           'motorway_link', 'trunk_link', 'primary_link', 'secondary_link', 'tertiary_link'}


def klasse(t):
    if 'building' in t: return 'building'
    if t.get('place'): return 'place'
    if t.get('man_made') == 'lighthouse' or t.get('seamark:type') == 'light_major': return 'lighthouse'
    if t.get('man_made') in ('pier', 'breakwater', 'groyne', 'quay'): return 'pier'
    if t.get('man_made') == 'bridge' or t.get('bridge') == 'yes' and 'highway' not in t: return 'bridge'
    if t.get('man_made') == 'tower': return 'tower'
    if t.get('leisure') in ('marina', 'slipway') or 'harbour' in t: return 'harbor'
    if t.get('waterway'): return 'waterway'
    if t.get('railway') == 'rail': return 'rail'
    if t.get('highway') in HW_ROAD: return 'road'
    if t.get('highway'): return 'path'
    if t.get('natural') in FL_NAT: return FL_NAT[t['natural']]
    if t.get('landuse') in FL_LU: return FL_LU[t['landuse']]
    if t.get('natural') == 'tree': return 'tree'
    return 'other'


def hoehe_von(c, t, std):
    try:
        if t.get('height'): return float(str(t['height']).replace('m', '').replace(',', '.').split(';')[0]), 'tag'
    except ValueError:
        pass
    try:
        if t.get('building:levels'): return float(t['building:levels'].replace(',', '.')) * 3 + 1, 'levels'
    except ValueError:
        pass
    return {'building': std['gebaeude'], 'forest': std['wald'], 'scrub': 2.0, 'tree': 8.0, 'lighthouse': 20.0, 'tower': 15.0}.get(c, 0.0), 'default'


def umgebung(osm, geb, std):
    log('Umgebung verarbeiten …')
    feats, seen = [], set()
    flat = lambda P: [v for p in P for v in (int(round(p[0])), int(round(p[1])))]
    zu_m = lambda l: np.c_[geb.to_m(*np.array([c[:2] for c in l]).T)]
    for el in osm:
        t = dict(el.get('properties', {})); g = el.get('geometry') or {}
        uid = f"{str(t.pop('@type', 'x'))[:1]}{t.pop('@id', '')}"
        if (uid, g.get('type')) in seen:
            continue
        seen.add((uid, g.get('type')))
        c = klasse(t)
        if t.get('natural') in ('peak', 'cape'): c = 'place'
        if c == 'other':
            continue
        h, hs = hoehe_von(c, t, std)
        f = dict(c=c, osm=uid)
        if t.get('name'): f['n'] = t['name']
        if h: f['h'] = round(h, 1); f['hs'] = hs
        sub = t.get('highway') or t.get('place') or t.get('landuse') or t.get('natural') or t.get('man_made') or t.get('leisure') or t.get('waterway')
        if sub: f['s'] = sub
        typ = g.get('type')
        if typ == 'Point':
            if c in ('road', 'path', 'building', 'forest', 'farmland', 'grass', 'urban'):
                continue   # Knoten auf Wegen/Flächen (z. B. Übergänge) weglassen
            x, y = geb.to_m(*g['coordinates'][:2])
            f['t'] = 'N'; f['g'] = [int(round(float(x))), int(round(float(y)))]
            feats.append(f)
        elif typ in ('LineString', 'MultiLineString'):
            for k, l in enumerate([g['coordinates']] if typ == 'LineString' else g['coordinates']):
                if len(l) < 2: continue
                P = dp(zu_m(l), 2)
                h2 = dict(f, t='L', g=flat(P))
                if k: h2['osm'] = f'{uid}.{k}'
                feats.append(h2)
        elif typ in ('Polygon', 'MultiPolygon'):
            for k, pl in enumerate(ringe_von(g)):
                rr = []
                for r in pl:
                    if len(r) < 4: continue
                    P = dp_ring(zu_m(r), 1.5 if c == 'building' else 3)
                    if len(P) >= 3: rr.append(flat(P))
                if not rr: continue
                h2 = dict(f, t='P', g=rr)
                if k: h2['osm'] = f'{uid}.{k}'
                feats.append(h2)
    # grob auf Revier (+800 m) beschränken
    def drin(f):
        g = f['g']
        if f['t'] == 'N': xs, ys = [g[0]], [g[1]]
        elif f['t'] == 'L': xs, ys = g[0::2], g[1::2]
        else: xs, ys = g[0][0::2], g[0][1::2]
        return max(xs) >= -800 and min(xs) <= geb.W + 800 and max(ys) >= -800 and min(ys) <= geb.H + 800
    feats = [f for f in feats if drin(f)]
    reihen = ['farmland', 'grass', 'urban', 'wetland', 'beach', 'scrub', 'forest', 'harbor', 'water', 'waterway', 'cliff', 'path', 'road', 'rail', 'pier', 'bridge', 'building', 'tower', 'lighthouse', 'tree', 'place']
    feats.sort(key=lambda f: reihen.index(f['c']) if f['c'] in reihen else 99)
    z = {}
    for f in feats: z[f['c']] = z.get(f['c'], 0) + 1
    log('  ' + ', '.join(f'{k} {v}' for k, v in z.items()))
    return feats


# ------------------------------------------------------------------ Vorschau
def vorschau(cm, wm, teile, nx, ny, pfad):
    z = cm.astype(float) / 100
    img = np.zeros((ny, nx, 3), np.uint8)
    t = -z
    stufen = [(1, (120, 170, 215)), (2, (150, 192, 228)), (5, (185, 214, 238)), (10, (214, 232, 246)), (1e9, (236, 244, 251))]
    for i, (g, col) in enumerate(stufen[::-1]):
        img[wm & (t < g)] = col
    gy, gx = np.gradient(z)
    hs = np.clip(0.75 + (gx - gy) * 0.35, 0.35, 1.15)
    land = np.array([226, 214, 178]) * hs[..., None]
    img[~wm] = np.clip(land[~wm], 0, 255).astype(np.uint8)
    Image.fromarray(img).save(pfad, optimize=True)


# ------------------------------------------------------------------ Hauptprogramm
def main():
    ap = argparse.ArgumentParser(description='Seekoje Revier-Bauer')
    ap.add_argument('revier', nargs='?', default='hiddensee', choices=sorted(REVIERE))
    ap.add_argument('--cache', default='.revier-cache', help='Zwischenspeicher für Downloads')
    ap.add_argument('--offline', action='store_true', help='nur Zwischenspeicher verwenden (Test)')
    ap.add_argument('--ohne-umgebung', action='store_true')
    ap.add_argument('--aus', default='.', help='Ausgabeordner')
    a = ap.parse_args()
    cfg = REVIERE[a.revier]; r = a.revier
    geb = Gebiet(cfg['bbox'], cfg['zelle'])
    log(f'Revier {cfg["name"]}: {geb.W / 1000:.1f} × {geb.H / 1000:.1f} km, Ursprung UTM33 {geb.ox} / {geb.oy}')
    netz = Netz(a.cache, a.offline)

    osm = osm_daten(netz, geb, cfg, not a.ohne_umgebung)
    teile, land, wf = kueste(osm['kueste'], geb, cfg)
    mim = maske(teile, geb.W, geb.H, cfg['maske'])
    cm, wm, quellen, (nx, ny) = gelaende(netz, geb, cfg, mim)
    pkt, lin = seezeichen(osm['seezeichen'], geb)
    std = dict(gebaeude=8.0, wald=15.0)
    env = [] if a.ohne_umgebung else umgebung(osm['umgebung'], geb, std)

    o84 = geb.to_ll(0, 0); n84 = geb.to_ll(geb.W, geb.H)
    rnd = lambda P: [[round(float(p[0]), 1), round(float(p[1]), 1)] for p in P]
    zt = cm[wm].astype(float) / 100
    meta = dict(
        format='seekoje-revier-1', revier=r, name=cfg['name'], regatten=cfg.get('regatten', []),
        erstellt=datetime.datetime.now(datetime.timezone.utc).isoformat(timespec='seconds'),
        hinweis='KEINE Navigationskarte. Tiefen grob (ca. 115 m Quellraster) und geglättet, Stand der Quelldaten unbekannt.',
        attribution=ATTRIBUTION,
        license_note='Abgeleitete Datenbank aus OpenStreetMap (ODbL 1.0): bei Weitergabe unter ODbL stellen. Im Spiel sichtbar nennen.',
        crs='EPSG:25833', units='m', axes='x = Ost, y = Nord, Ursprung = Südwest-Ecke des Reviers',
        origin_utm=dict(x=geb.ox, y=geb.oy), size=dict(w=geb.W, h=geb.H),
        bbox_wgs84=dict(west=round(float(o84[0]), 6), south=round(float(o84[1]), 6), east=round(float(n84[0]), 6), north=round(float(n84[1]), 6)),
        origin_wgs84=dict(lon=round(float(o84[0]), 6), lat=round(float(o84[1]), 6)),
        grid=dict(file=f'{r}-gelaende.bin', type='int16 little-endian', unit='cm (über/unter NHN ≈ Mittelwasser Ostsee)',
                  cellsize=cfg['zelle'], ncols=nx, nrows=ny, order='Zeile 0 = Norden, Spalten West → Ost; Zellmittelpunkte',
                  lowerLeft=dict(x=0, y=0), quellen=quellen,
                  tiefe_min_m=round(float(zt.min()), 2) if zt.size else None, tiefe_mittel_m=round(float(zt.mean()), 2) if zt.size else None,
                  hoehe_max_m=round(float(cm[~wm].max()) / 100, 1) if (~wm).any() else None),
        mask=dict(file=f'{r}-maske.png', cellsize=cfg['maske'], ncols=mim.size[0], nrows=mim.size[1], north='oben', white='Wasser', black='Land'),
        environment=dict(file=f'{r}-umgebung.json', count=len(env)),
        water=[dict(outer=rnd(t['outer']), islands=[rnd(i) for i in t['islands']]) for t in teile],
        water_area_km2=round(wf / 1e6, 2), simplify_m=cfg['ufer_tol'],
        land=[rnd(L) for L in land],
        seamarks=pkt, seamark_lines=lin,
        warnungen=WARN,
    )
    os.makedirs(a.aus, exist_ok=True)
    P = lambda s: os.path.join(a.aus, f'{r}-{s}')
    json.dump(meta, open(P('revier.json'), 'w', encoding='utf-8'), ensure_ascii=False, separators=(',', ':'))
    open(P('gelaende.bin'), 'wb').write(cm.tobytes())
    mim.convert('1').save(P('maske.png'), optimize=True)
    env_alle = env
    if cfg.get('umgebung_schlank'):
        geb_feats = [f for f in env if f['c'] == 'building']
        env = [f for f in env if f['c'] not in ('building', 'path')]
        json.dump(dict(format='seekoje-gebaeude-1', revier=r, attribution=ATTRIBUTION[:1], features=geb_feats),
                  open(P('gebaeude.json'), 'w', encoding='utf-8'), ensure_ascii=False, separators=(',', ':'))
        log(f'  Gebäude separat: {len(geb_feats)} (für Spielkacheln)')
        meta['environment']['count'] = len(env); meta['environment']['ohne'] = 'Gebäude und Fußwege (siehe ' + f'{r}-gebaeude.json)'
        json.dump(meta, open(P('revier.json'), 'w', encoding='utf-8'), ensure_ascii=False, separators=(',', ':'))
    json.dump(dict(format='seekoje-umgebung-1', revier=r, attribution=ATTRIBUTION[:1],
                   legende='t: N=Punkt [x,y], L=Linie [x,y,x,y…], P=Fläche [[Außenring],[Loch]…] als flache Listen in m; '
                           'c=Klasse, s=OSM-Unterart, n=Name, h=Höhe m, hs=Höhenquelle',
                   features=env),
              open(P('umgebung.json'), 'w', encoding='utf-8'), ensure_ascii=False, separators=(',', ':'))
    vorschau(cm, wm, teile, nx, ny, P('vorschau.png'))
    open(P('namensnennung.txt'), 'w', encoding='utf-8').write(
        f'Revier {cfg["name"]} – Datenquellen (im Spiel sichtbar nennen)\n\n' + '\n'.join(ATTRIBUTION) +
        '\n\nHinweise:\n- OpenStreetMap: Die Revierdateien sind eine abgeleitete Datenbank (ODbL 1.0). Bilder/Spielszenen daraus sind „Produced Work“ und brauchen die Nennung.\n'
        '- EMODnet und Copernicus DEM: Namensnennung nötig.\n- KEINE Navigationskarte. Keine Rechtsberatung.\n')
    if cfg.get('spiel'):
        import revier_spiel
        try:
            revier_spiel.export(r, cfg, meta, cm, cfg['zelle'], env_alle, a.aus, utm, geo)
        except Exception as ex:
            warn(f'Spielexport fehlgeschlagen: {ex}')
            import traceback; traceback.print_exc()
    gr = {s: os.path.getsize(P(s)) for s in ('revier.json', 'gelaende.bin', 'umgebung.json', 'maske.png', 'vorschau.png')}
    log('Fertig: ' + ', '.join(f'{r}-{k} {v / 1e6:.1f} MB' for k, v in gr.items()))
    zs = os.environ.get('GITHUB_STEP_SUMMARY')
    if zs:
        with open(zs, 'a', encoding='utf-8') as f:
            f.write(f'## Revier {cfg["name"]}\n\n- Fläche {geb.W / 1000:.1f} × {geb.H / 1000:.1f} km, Wasser {wf / 1e6:.1f} km²\n'
                    f'- {len(pkt)} Seezeichen, {len(env)} Umgebungsobjekte\n- Tiefe: {quellen.get("tiefe")}\n- Höhe: {quellen.get("hoehe")}\n'
                    + ''.join(f'- ⚠️ {w}\n' for w in WARN) + f'\n![Vorschau]({r}-vorschau.png)\n')


if __name__ == '__main__':
    main()
