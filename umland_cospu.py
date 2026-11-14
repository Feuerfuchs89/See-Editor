#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Umland Cospudener See für die Regattakoje: echtes Gelände, Landnutzung und alle Gebäude.

Ergebnis: cospu-umland.json im Hauptordner. Das Spiel lädt die Datei im Revier „Cospudener See“
und legt damit das Gelände rund um den See, Wald, Felder, Orte und jedes Haus aus OpenStreetMap an.

Koordinaten: dasselbe Meter-System wie die Uferlinie im Spiel (COSPU_PTS, Osten/Norden in m).
Die Lage wird automatisch bestimmt: Die OSM-Uferlinie des Sees (Relation 285950) wird auf die
Spiel-Uferlinie eingepasst (Verschiebung, Drehung, Maßstab).

Gelände: zuerst das amtliche Digitale Geländemodell Sachsen (GeoSN, INSPIRE-Download, dl-de/by-2-0),
wenn das nicht klappt Copernicus GLO-30 (Oberflächenmodell; Wald und Häuser werden herausgerechnet).
Start: Action „Revier bauen“ mit Revier „cospu“.
"""
import base64, io, json, math, os, re, subprocess, sys, time, zipfile
import numpy as np
import requests
from PIL import Image, ImageDraw

import revier_bauen as rb
log, warn = rb.log, rb.warn

PBF = 'https://download.geofabrik.de/europe/germany/sachsen-latest.osm.pbf'
SEE_REL = 285950
RAND = 2600            # m Umland um die See-Box (wie das Spielraster)
CS_H = 20              # m Höhenraster
CS_LC = 10             # m Landnutzungsraster
GEOSN_ATOM = 'https://geodownload.sachsen.de/inspire/el_atom/Service_el.xml'
ZIEL = 'cospu-umland.json'

# Uferlinie des Spiels (COSPU_PTS, nur Ost/Nord)
COSPU_PTS = json.loads(
'[[116,-1995],[-28,-1994],[-60,-1944],[-132,-1901],[-409,-1632],[-464,-1551],[-484,-1547],[-525,-1459],[-627,-1317],'
'[-607,-1254],[-612,-1236],[-637,-1198],[-645,-1152],[-678,-1124],[-809,-962],[-836,-528],[-850,-503],[-862,-436],'
'[-901,-367],[-910,-343],[-932,-291],[-956,-201],[-994,-63],[-996,33],[-994,47],[-992,57],[-990,72],[-965,182],'
'[-935,271],[-896,385],[-878,427],[-841,509],[-784,602],[-760,662],[-761,691],[-776,712],[-767,749],[-741,762],'
'[-718,791],[-706,834],[-704,915],[-687,958],[-680,1001],[-710,1067],[-719,1115],[-744,1170],[-773,1256],[-783,1303],'
'[-780,1321],[-771,1340],[-753,1356],[-702,1368],[-688,1384],[-669,1431],[-664,1457],[-647,1477],[-643,1496],'
'[-611,1553],[-579,1592],[-552,1612],[-471,1660],[-385,1691],[-276,1706],[-205,1719],[-171,1740],[-130,1745],'
'[-56,1730],[29,1729],[66,1715],[121,1714],[184,1703],[220,1712],[263,1712],[297,1745],[351,1800],[379,1833],'
'[396,1866],[407,1919],[438,1951],[473,1975],[510,1987],[537,1995],[565,1993],[607,1983],[637,1966],[671,1937],'
'[686,1906],[693,1874],[706,1829],[729,1763],[750,1708],[767,1674],[786,1643],[803,1603],[820,1555],[840,1488],'
'[846,1442],[849,1410],[850,1370],[841,1340],[845,1319],[842,1271],[846,1218],[860,1173],[876,1142],[896,1103],'
'[916,1052],[934,1001],[946,964],[961,898],[974,822],[982,739],[985,616],[982,566],[983,515],[994,453],[996,388],'
'[994,330],[981,277],[960,243],[921,177],[894,150],[869,121],[856,81],[853,46],[852,12],[838,-28],[812,-76],'
'[781,-110],[734,-136],[702,-166],[681,-191],[652,-226],[611,-249],[578,-263],[555,-288],[540,-305],[514,-330],'
'[486,-372],[463,-430],[438,-480],[413,-516],[389,-539],[356,-567],[318,-613],[295,-637],[255,-707],[230,-748],'
'[206,-815],[194,-866],[184,-929],[183,-990],[185,-1045],[192,-1093],[202,-1137],[234,-1207],[264,-1259],'
'[311,-1336],[350,-1394],[391,-1477],[408,-1530],[419,-1588],[418,-1651],[407,-1700],[383,-1756],[347,-1813],'
'[302,-1876],[250,-1929],[201,-1963],[160,-1982],[116,-1995]]')

ATTR = ['© OpenStreetMap-Mitwirkende, ODbL 1.0 (openstreetmap.org/copyright)']

# Landnutzungsklassen (das Spiel kennt dieselben Nummern)
LC = dict(leer=0, wald=1, gebuesch=2, wiese=3, acker=4, siedlung=5, gewerbe=6, strand=7, wasser=8, garten=9, strasse=10, sumpf=11)


# ------------------------------------------------------------------ OSM
def osm(netz):
    pfad = {t: netz._pfad(f'cospu_{t}.geojsonseq') for t in ('see', 'geb', 'lc', 'weg', 'pkt')}
    if not all(os.path.exists(p) for p in pfad.values()):
        pbf = netz.datei('sachsen.osm.pbf', PBF, pflicht=True, nur_pfad=True)
        ext = netz._pfad('cospu.osm.pbf')
        lauf = lambda *a: (log('  osmium ' + ' '.join(a[:2])), subprocess.run(['osmium', *a], check=True))
        lauf('extract', '-b', '12.20,51.18,12.48,51.36', '-s', 'smart', pbf, '-o', ext, '--overwrite')
        sp = netz._pfad('cospu_see.osm.pbf')
        lauf('getid', '-r', ext, f'r{SEE_REL}', '-o', sp, '--overwrite')
        filt = {
            'geb': ['wr/building'],
            'lc': ['wr/landuse', 'wr/natural=wood,scrub,heath,grassland,beach,sand,water,wetland',
                   'wr/leisure=park,golf_course,pitch,playground,garden,recreation_ground,beach_resort',
                   'wr/waterway=riverbank', 'wr/amenity=parking'],
            'weg': ['w/highway=motorway,trunk,primary,secondary,tertiary,unclassified,residential,living_street,'
                    'motorway_link,trunk_link,primary_link,secondary_link,tertiary_link,service,pedestrian'],
            'pkt': ['nwr/man_made=tower', 'nwr/tourism=viewpoint', 'nwr/man_made=water_tower'],
        }
        lauf('export', sp, '-f', 'geojsonseq', '-x', 'print_record_separator=false', '-a', 'type,id', '-o', pfad['see'], '--overwrite')
        for t, f in filt.items():
            tp = netz._pfad(f'cospu_{t}.osm.pbf')
            lauf('tags-filter', ext, *f, '-o', tp, '--overwrite')
            lauf('export', tp, '-f', 'geojsonseq', '-x', 'print_record_separator=false', '-a', 'type,id', '-o', pfad[t], '--overwrite')
    out = {t: rb.lies_seq(p) for t, p in pfad.items()}
    for t, v in out.items():
        log(f'  OSM {t}: {len(v)} Objekte')
    return out


def polys(geom):
    """Liste von (aussen, [loecher]) in Länge/Breite."""
    if not geom:
        return []
    if geom['type'] == 'Polygon':
        c = geom['coordinates']; return [(c[0], c[1:])] if c else []
    if geom['type'] == 'MultiPolygon':
        return [(c[0], c[1:]) for c in geom['coordinates'] if c]
    return []


# ------------------------------------------------------------------ Lage: OSM-Ufer → Spiel-Ufer
def einpassen(see_feats):
    from scipy.spatial import cKDTree
    ringe = []
    for f in see_feats:
        for a, _ in polys(f.get('geometry')):
            x, y = rb.utm([p[0] for p in a], [p[1] for p in a]); ringe.append(np.c_[x, y])
    if not ringe:
        raise RuntimeError(f'Seeufer (OSM-Relation {SEE_REL}) nicht gefunden')
    R = max(ringe, key=lambda r: abs(rb.flaeche(r)))
    # dicht abtasten (1 m)
    d = []
    for i in range(len(R) - 1):
        a, b = R[i], R[i + 1]; n = max(1, int(np.hypot(*(b - a))))
        d.append(a + (b - a) * (np.arange(n)[:, None] / n))
    D = np.vstack(d); kd = cKDTree(D)
    P = np.array(COSPU_PTS, float)
    def zentrum(Q):
        x, y = Q[:, 0], Q[:, 1]; c = x * np.roll(y, -1) - np.roll(x, -1) * y; A = c.sum() / 2
        return np.array([((x + np.roll(x, -1)) * c).sum() / (6 * A), ((y + np.roll(y, -1)) * c).sum() / (6 * A)])
    best = None
    for th0 in (-0.05, 0.0, 0.05):
        s, th = 1.0, th0; t = zentrum(R) - zentrum(P) @ np.array([[math.cos(th), math.sin(th)], [-math.sin(th), math.cos(th)]])
        for _ in range(60):
            M = s * np.array([[math.cos(th), -math.sin(th)], [math.sin(th), math.cos(th)]])
            Q = P @ M.T + t
            _, j = kd.query(Q); Z = D[j]
            # Umeyama (Ähnlichkeit)
            mp, mz = P.mean(0), Z.mean(0); Pc, Zc = P - mp, Z - mz
            U, S, Vt = np.linalg.svd(Zc.T @ Pc / len(P))
            dd = np.sign(np.linalg.det(U @ Vt)); Sd = np.diag([1, dd])
            Rm = U @ Sd @ Vt; s = float(np.trace(np.diag(S) @ Sd) / (Pc ** 2).sum() * len(P))
            th = math.atan2(Rm[1, 0], Rm[0, 0]); t = mz - s * (Rm @ mp)
        M = s * np.array([[math.cos(th), -math.sin(th)], [math.sin(th), math.cos(th)]])
        rms = float(np.sqrt((kd.query(P @ M.T + t)[0] ** 2).mean()))
        if best is None or rms < best[0]:
            best = (rms, s, th, t)
    rms, s, th, t = best
    log(f'  Lage eingepasst: Maßstab {s:.4f}, Drehung {math.degrees(th):+.2f}°, Abweichung {rms:.1f} m (RMS)')
    if rms > 25:
        warn(f'Spiel-Ufer passt schlecht auf die OSM-Uferlinie ({rms:.0f} m) – Gelände kann versetzt sein')
    M = s * np.array([[math.cos(th), -math.sin(th)], [math.sin(th), math.cos(th)]]); Mi = np.linalg.inv(M)
    hin = lambda E, N: (np.stack([np.asarray(E, float), np.asarray(N, float)], -1) @ M.T + t)       # Spiel → UTM
    rueck = lambda X, Y: ((np.stack([np.asarray(X, float), np.asarray(Y, float)], -1) - t) @ Mi.T)  # UTM → Spiel
    return hin, rueck, R, dict(massstab=round(s, 5), drehung=round(math.degrees(th), 3), rms=round(rms, 1))


# ------------------------------------------------------------------ Gelände Sachsen (INSPIRE-ATOM)
def _get(url, timeout=60):
    r = requests.get(url, headers=rb.UA, timeout=(20, timeout)); r.raise_for_status(); return r.content


def _eintraege(xml):
    out = []
    for e in re.findall(r'<(?:\w+:)?entry\b.*?</(?:\w+:)?entry>', xml, re.S):
        ti = re.search(r'<(?:\w+:)?title[^>]*>(.*?)</', e, re.S)
        links = re.findall(r'<(?:\w+:)?link\b([^>]*)/?>', e)
        L = []
        for a in links:
            h = re.search(r'href="([^"]+)"', a); ty = re.search(r'type="([^"]+)"', a); rl = re.search(r'rel="([^"]+)"', a)
            if h:
                L.append((h.group(1).replace('&amp;', '&'), ty.group(1) if ty else '', rl.group(1) if rl else ''))
        poly = re.search(r'<georss:polygon>(.*?)</', e, re.S); box = re.search(r'<georss:box>(.*?)</', e, re.S)
        out.append(dict(titel=(ti.group(1).strip() if ti else ''), links=L,
                        poly=(poly.group(1) if poly else None), box=(box.group(1) if box else None), xml=e))
    return out


def _bbox_ll(e):
    v = None
    if e['poly']:
        v = [float(x) for x in e['poly'].split()]
    elif e['box']:
        v = [float(x) for x in e['box'].split()]
    if not v:
        return None
    la, lo = v[0::2], v[1::2]
    return min(lo), min(la), max(lo), max(la)


def _lies_kachel(name, daten, acc, cnt, ux0, uy0, uc, nx, ny):
    """Kachel (GeoTIFF/XYZ/ASC, auch im ZIP) ins UTM-Hilfsraster eintragen. Koordinaten: ETRS89/UTM33."""
    def eintragen(X, Y, Z):
        X = np.asarray(X, float); Y = np.asarray(Y, float); Z = np.asarray(Z, float)
        if X.size and np.nanmedian(X) > 3e7:          # mit Zonen-Präfix 33xxxxxx
            X = X - 33e6
        i = np.floor((X - ux0) / uc).astype(np.int64); j = np.floor((Y - uy0) / uc).astype(np.int64)
        ok = (i >= 0) & (i < nx) & (j >= 0) & (j < ny) & np.isfinite(Z) & (Z > -100) & (Z < 3000)
        np.add.at(acc, (j[ok], i[ok]), Z[ok]); np.add.at(cnt, (j[ok], i[ok]), 1)
        return int(ok.sum())
    n = 0
    low = name.lower()
    if low.endswith('.zip'):
        with zipfile.ZipFile(io.BytesIO(daten)) as z:
            for m in z.namelist():
                if re.search(r'\.(tif|tiff|xyz|txt|asc|csv)$', m, re.I):
                    n += _lies_kachel(m, z.read(m), acc, cnt, ux0, uy0, uc, nx, ny)
        return n
    if re.search(r'\.(tif|tiff)$', low):
        import tifffile
        with tifffile.TiffFile(io.BytesIO(daten)) as tf:
            pg = tf.pages[0]; a = pg.asarray().astype(np.float64); tg = pg.tags
            if a.ndim == 3:
                a = a[..., 0]
            sx, sy = tg['ModelPixelScaleTag'].value[:2]; tp = tg['ModelTiepointTag'].value
            x0, y0 = tp[3] - tp[0] * sx, tp[4] + tp[1] * sy
            nod = None
            if 'GDAL_NODATA' in tg:
                try: nod = float(str(tg['GDAL_NODATA'].value).strip('\x00 '))
                except ValueError: pass
        if nod is not None:
            a[a == nod] = np.nan
        st = max(1, int(round(uc / 2 / sx)))           # auf etwa halbe Hilfszelle ausdünnen
        a = a[::st, ::st]; jj, ii = np.mgrid[0:a.shape[0], 0:a.shape[1]]
        X = x0 + (ii * st + 0.5) * sx; Y = y0 - (jj * st + 0.5) * sy
        return eintragen(X.ravel(), Y.ravel(), a.ravel())
    txt = daten.decode('latin-1', 'replace')
    if re.match(r'\s*ncols', txt, re.I):              # ESRI-ASCII-Raster
        kopf = {}; zeilen = txt.splitlines(); k = 0
        while k < len(zeilen) and re.match(r'\s*[a-zA-Z_]', zeilen[k]):
            a_, b_ = zeilen[k].split()[:2]; kopf[a_.lower()] = float(b_); k += 1
        A = np.array(' '.join(zeilen[k:]).split(), float).reshape(int(kopf['nrows']), int(kopf['ncols']))
        c = kopf['cellsize']; xl = kopf.get('xllcorner', kopf.get('xllcenter', 0) - c / 2); yl = kopf.get('yllcorner', kopf.get('yllcenter', 0) - c / 2)
        if 'nodata_value' in kopf:
            A[A == kopf['nodata_value']] = np.nan
        st = max(1, int(round(uc / 2 / c))); A = A[::st, ::st]; jj, ii = np.mgrid[0:A.shape[0], 0:A.shape[1]]
        X = xl + (ii * st + 0.5) * c; Y = yl + (int(kopf['nrows']) - jj * st - 0.5) * c
        return eintragen(X.ravel(), Y.ravel(), A.ravel())
    txt = re.sub(r'[,;]', ' ', txt) if (',' in txt[:2000] or ';' in txt[:2000]) else txt
    v = np.fromstring(txt, sep=' ')
    v = v[: len(v) // 3 * 3].reshape(-1, 3)
    return eintragen(v[:, 0], v[:, 1], v[:, 2])


def gelaende_sachsen(netz, ubox):
    """Liefert (Hilfsraster dict) oder None. ubox = (x0, y0, x1, y1) in UTM33."""
    if netz.offline:
        return None
    try:
        log('GeoSN-Geländemodell (INSPIRE-Download) suchen …')
        svc = _get(GEOSN_ATOM).decode('utf-8', 'replace')
        ds = _eintraege(svc)
        for e in ds:
            log('  Datensatz:', e['titel'][:100])
        def aufl(t):
            m = re.search(r'DGM\s*-?\s*(\d+)', t, re.I) or re.search(r'(\d+)\s*m\b', t)
            return int(m.group(1)) if m else None
        kand = [e for e in ds if re.search(r'DGM|Gel(ä|ae)nde', e['titel'], re.I) and not re.search(r'DOM|Oberfl', e['titel'], re.I)]
        if not kand:
            warn('GeoSN: kein Geländemodell im Download-Dienst gefunden'); return None
        rang = {10: 0, 5: 1, 20: 2, 2: 3, 25: 4, 1: 5}
        kand.sort(key=lambda e: rang.get(aufl(e['titel']), 9))
        for e in kand[:3]:
            feed = next((h for h, ty, rl in e['links'] if 'atom' in ty or h.endswith('.xml')), None)
            if not feed:
                continue
            log(f'  nehme „{e["titel"][:80]}“ ({aufl(e["titel"]) or "?"} m)')
            kach = _eintraege(_get(feed).decode('utf-8', 'replace'))
            lo_, la_ = rb.geo(np.array([ubox[0], ubox[2], ubox[0], ubox[2]]), np.array([ubox[1], ubox[1], ubox[3], ubox[3]]))
            w_, s_, e_, n_ = float(lo_.min()), float(la_.min()), float(lo_.max()), float(la_.max())
            treffer = []
            for k in kach:
                bb = _bbox_ll(k)
                dl = [h for h, ty, rl in k['links'] if re.search(r'\.(zip|tif|tiff|xyz|asc)(\?|$)', h, re.I) or 'zip' in ty or 'tiff' in ty]
                if not dl:
                    continue
                if bb:
                    if bb[2] < w_ or bb[0] > e_ or bb[3] < s_ or bb[1] > n_:
                        continue
                else:
                    m = re.search(r'(?:33)?(\d{3})[_-](\d{4})', k['titel'] + ' ' + dl[0])
                    if not m:
                        continue
                    X, Y = int(m.group(1)) * 1000, int(m.group(2)) * 1000
                    if X > ubox[2] or X + 2000 < ubox[0] or Y > ubox[3] or Y + 2000 < ubox[1]:
                        continue
                treffer.append((k['titel'], dl[0]))
            log(f'  {len(treffer)} Kacheln im Gebiet (von {len(kach)})')
            if not treffer or len(treffer) > 120:
                continue
            uc = 5.0; ux0, uy0 = ubox[0], ubox[1]; nx = int((ubox[2] - ubox[0]) / uc) + 1; ny = int((ubox[3] - ubox[1]) / uc) + 1
            acc = np.zeros((ny, nx)); cnt = np.zeros((ny, nx))
            for i, (ti, url) in enumerate(treffer):
                nm = 'geosn_' + re.sub(r'[^\w.-]+', '_', url.split('/')[-1].split('?')[0])[-80:]
                d = netz.datei(nm, url)
                if not d:
                    continue
                try:
                    k = _lies_kachel(nm, d, acc, cnt, ux0, uy0, uc, nx, ny)
                    log(f'    {i + 1}/{len(treffer)} {nm}: {k} Werte')
                except Exception as ex:
                    warn(f'GeoSN-Kachel {nm} nicht lesbar: {ex}')
            ok = cnt > 0
            if ok.mean() < 0.5:
                warn(f'GeoSN: nur {ok.mean() * 100:.0f} % des Gebiets abgedeckt – nehme Copernicus'); continue
            a = np.where(ok, acc / np.maximum(cnt, 1), np.nan)
            log(f'  GeoSN-Gelände: {ok.mean() * 100:.0f} % abgedeckt')
            return dict(a=a, x0=ux0, y0=uy0, c=uc, quelle=f'Geländemodell: © GeoSN, dl-de/by-2-0 ({e["titel"][:60]})')
    except Exception as ex:
        warn(f'GeoSN-Gelände nicht verfügbar: {ex}')
    return None


def utm_abtasten(r, X, Y):
    a = r['a']; ny, nx = a.shape
    c = (X - r['x0']) / r['c'] - 0.5; z = (Y - r['y0']) / r['c'] - 0.5
    c0 = np.floor(c).astype(int); z0 = np.floor(z).astype(int); fc = c - c0; fz = z - z0
    acc = np.zeros(X.shape); ws = np.zeros(X.shape)
    for dz, dc, w in ((0, 0, (1 - fz) * (1 - fc)), (0, 1, (1 - fz) * fc), (1, 0, fz * (1 - fc)), (1, 1, fz * fc)):
        zz, cc = z0 + dz, c0 + dc; ok = (zz >= 0) & (zz < ny) & (cc >= 0) & (cc < nx)
        v = np.full(X.shape, np.nan); v[ok] = a[zz[ok], cc[ok]]; g = np.isfinite(v)
        acc[g] += v[g] * w[g]; ws[g] += w[g]
    return np.where(ws > 0.25, acc / np.maximum(ws, 1e-9), np.nan)


def gelaende_cop(netz, lon, lat):
    acc, ws = np.zeros(lon.shape), np.zeros(lon.shape)
    for la in range(int(math.floor(lat.min())), int(math.floor(lat.max())) + 1):
        for lo in range(int(math.floor(lon.min())), int(math.floor(lon.max())) + 1):
            nm = f'Copernicus_DSM_COG_10_N{la:02d}_00_E{lo:03d}_00_DEM'
            d = netz.datei(nm + '.tif', rb.COP30.format(n=nm))
            if d:
                rb.abtasten(rb.geotiff(d), lon, lat, (acc, ws))
    return np.where(ws > 0.25, acc / np.maximum(ws, 1e-9), np.nan)


# ------------------------------------------------------------------ Gebäude
HAUS = {'house', 'detached', 'semidetached_house', 'terrace', 'bungalow', 'farm', 'cabin', 'villa'}
NEBEN = {'garage', 'garages', 'carport', 'shed', 'hut', 'roof', 'kiosk', 'toilets', 'boathouse', 'container', 'greenhouse', 'allotment_house', 'service', 'transformer_tower'}
GEWERBE = {'industrial', 'warehouse', 'retail', 'commercial', 'supermarket', 'office', 'manufacture', 'hangar', 'storage_tank'}
OEFF = {'church', 'chapel', 'school', 'kindergarten', 'university', 'hospital', 'public', 'civic', 'government', 'train_station', 'sports_hall', 'hotel', 'museum', 'college'}
LAND = {'barn', 'stable', 'cowshed', 'farm_auxiliary', 'sty', 'silo'}
MEHR = {'apartments', 'residential', 'dormitory'}


def zahl(v):
    if v is None:
        return None
    m = re.match(r'\s*([\d.,]+)', str(v))
    try:
        return float(m.group(1).replace(',', '.')) if m else None
    except ValueError:
        return None


def gebaeude(feats, rueck, innen_see, E0, N0, E1, N1):
    out, namen = [], []
    for f in feats:
        p = f.get('properties') or {}
        b = p.get('building', 'yes')
        if b in ('no', 'construction', 'ruins', 'collapsed') or p.get('location') == 'underground':
            continue
        for aussen, _ in polys(f.get('geometry')):
            if len(aussen) < 4:
                continue
            X, Y = rb.utm([q[0] for q in aussen], [q[1] for q in aussen])
            Q = rueck(X, Y)
            Q = rb.dp(Q, 0.4)
            if len(Q) < 4:
                continue
            Q = Q[:-1] if np.allclose(Q[0], Q[-1]) else Q
            cx, cy = Q[:, 0].mean(), Q[:, 1].mean()
            if not (E0 < cx < E1 and N0 < cy < N1) or innen_see(cx, cy):
                continue
            A = abs(rb.flaeche(np.vstack([Q, Q[:1]])))
            if A < 6:
                continue
            lv = zahl(p.get('building:levels')); rl = zahl(p.get('roof:levels')) or 0
            h = zahl(p.get('height'))
            if b in NEBEN:
                typ, h0 = 2, 2.7
            elif b in GEWERBE:
                typ, h0 = 3, 8.0
            elif b in OEFF:
                typ, h0 = 4, 12.0 if b not in ('church', 'chapel') else 16.0
            elif b in LAND:
                typ, h0 = 5, 6.5
            elif b in MEHR:
                typ, h0 = 1, 11.0
            elif b in HAUS:
                typ, h0 = 0, 6.0
            else:
                typ, h0 = (2, 2.8) if A < 45 else (0, 6.2) if A < 260 else (1, 10.0) if A < 900 else (3, 8.0)
            if h is None:
                h = lv * 2.9 + 0.6 + rl * 1.5 if lv else h0
            h = float(min(max(h, 2.2), 120))
            rs = p.get('roof:shape')
            if rs in ('gabled', 'hipped', 'half-hipped', 'gambrel', 'mansard', 'saltbox', 'pyramidal'):
                dach = 2 if rs in ('hipped', 'half-hipped', 'pyramidal') else 1
            elif rs in ('flat', 'skillion'):
                dach = 0
            else:
                dach = 1 if (typ in (0, 5) and A < 420) or (typ == 1 and A < 300 and h < 13) else 0
            dm = np.round(Q * 10).astype(int)
            flach = [int(dm[0, 0]), int(dm[0, 1])]
            for k in range(1, len(dm)):
                flach += [int(dm[k, 0] - dm[k - 1, 0]), int(dm[k, 1] - dm[k - 1, 1])]
            out.append([typ, int(round(h * 10)), dach] + flach)
            nm = p.get('name')
            if nm:
                namen.append([len(out) - 1, nm[:60]])
    return out, namen


# ------------------------------------------------------------------ Landnutzung
def lc_klasse(p):
    lu, na, le = p.get('landuse'), p.get('natural'), p.get('leisure')
    if na in ('water',) or lu in ('basin', 'reservoir') or p.get('waterway') == 'riverbank':
        return 'wasser'
    if na == 'wood' or lu == 'forest':
        return 'wald'
    if na in ('scrub', 'heath'):
        return 'gebuesch'
    if na == 'wetland':
        return 'sumpf'
    if na in ('beach', 'sand') or le == 'beach_resort':
        return 'strand'
    if lu in ('farmland', 'orchard', 'vineyard', 'plant_nursery'):
        return 'acker'
    if lu in ('allotments',) or le == 'garden':
        return 'garten'
    if lu in ('meadow', 'grass', 'village_green', 'recreation_ground', 'cemetery') or na == 'grassland' or le in ('park', 'golf_course', 'pitch', 'playground', 'recreation_ground'):
        return 'wiese'
    if lu in ('residential',):
        return 'siedlung'
    if lu in ('industrial', 'commercial', 'retail', 'railway', 'construction', 'garages', 'brownfield', 'landfill', 'quarry') or p.get('amenity') == 'parking':
        return 'gewerbe'
    return None


ORDNUNG = ['siedlung', 'gewerbe', 'acker', 'wiese', 'garten', 'gebuesch', 'sumpf', 'wald', 'strand', 'wasser']


def landnutzung(feats, wege, rueck, E0, N1, W, H):
    im = Image.new('L', (W, H), 0); dr = ImageDraw.Draw(im)
    px = lambda Q: [((q[0] - E0) / CS_LC, (N1 - q[1]) / CS_LC) for q in Q]
    nach = {k: [] for k in ORDNUNG}
    for f in feats:
        k = lc_klasse(f.get('properties') or {})
        if k:
            nach[k].append(f)
    for k in ORDNUNG:
        for f in nach[k]:
            for aussen, loecher in polys(f.get('geometry')):
                X, Y = rb.utm([q[0] for q in aussen], [q[1] for q in aussen]); P = px(rueck(X, Y))
                if len(P) >= 3:
                    dr.polygon(P, fill=LC[k])
                for l in loecher:
                    X, Y = rb.utm([q[0] for q in l], [q[1] for q in l]); P = px(rueck(X, Y))
                    if len(P) >= 3 and k in ('wald', 'wasser'):
                        dr.polygon(P, fill=0)
    breite = dict(motorway=26, trunk=18, primary=12, secondary=10, tertiary=8, unclassified=6, residential=6, living_street=5,
                  pedestrian=5, service=4, motorway_link=8, trunk_link=8, primary_link=7, secondary_link=7, tertiary_link=6)
    for f in wege:
        g = f.get('geometry') or {}
        if g.get('type') != 'LineString':
            continue
        hw = (f.get('properties') or {}).get('highway')
        if (f.get('properties') or {}).get('tunnel') in ('yes', 'building_passage'):
            continue
        b = breite.get(hw, 5)
        X, Y = rb.utm([q[0] for q in g['coordinates']], [q[1] for q in g['coordinates']])
        dr.line(px(rueck(X, Y)), fill=LC['strasse'], width=max(1, int(round(b / CS_LC))))
    return np.asarray(im, np.uint8)


def rle(a):
    a = a.ravel(); out = bytearray(); i = 0; n = len(a)
    while i < n:
        v = a[i]; j = i + 1
        while j < n and j - i < 255 and a[j] == v:
            j += 1
        out += bytes((int(v), j - i)); i = j
    return base64.b64encode(bytes(out)).decode()


# ------------------------------------------------------------------ Hauptteil
def _innen(P):
    try:
        from matplotlib.path import Path
        pa = Path(P); return lambda x, y: bool(pa.contains_point((x, y)))
    except Exception:
        return lambda x, y: rb.im_poly((x, y), P)


def hauptteil():
    t0 = time.time()
    netz = rb.Netz('.revier-cache', offline='--offline' in sys.argv)
    feats = osm(netz)
    hin, rueck, see_ring, lage = einpassen(feats['see'])
    P = np.array(COSPU_PTS, float)
    innen_see = _innen(P)
    E0, E1 = P[:, 0].min() - RAND, P[:, 0].max() + RAND
    N0, N1 = P[:, 1].min() - RAND, P[:, 1].max() + RAND
    E0, N0 = math.floor(E0 / CS_LC) * CS_LC, math.floor(N0 / CS_LC) * CS_LC
    E1, N1 = math.ceil(E1 / CS_LC) * CS_LC, math.ceil(N1 / CS_LC) * CS_LC

    # --- Landnutzung (10 m), Zeile 0 = Norden
    W, H = int((E1 - E0) / CS_LC), int((N1 - N0) / CS_LC)
    lc = landnutzung(feats['lc'], feats['weg'], rueck, E0, N1, W, H)
    log(f'  Landnutzung {W}×{H}: ' + ', '.join(f'{k} {np.mean(lc == v) * 100:.0f} %' for k, v in LC.items() if np.mean(lc == v) > 0.005))

    # --- Höhen (20 m), Zeile 0 = Süden (wie das Spielraster)
    nx, ny = int((E1 - E0) / CS_H) + 1, int((N1 - N0) / CS_H) + 1
    gE, gN = np.meshgrid(E0 + np.arange(nx) * CS_H, N0 + np.arange(ny) * CS_H)
    U = hin(gE, gN); X, Y = U[..., 0], U[..., 1]
    lon, lat = rb.geo(X, Y)
    ubox = (X.min() - 50, Y.min() - 50, X.max() + 50, Y.max() + 50)
    sa = gelaende_sachsen(netz, ubox)
    if sa is not None:
        h = utm_abtasten(sa, X, Y); quelle = sa['quelle']
        if np.isnan(h).any():
            cop = gelaende_cop(netz, lon, lat)
            # Lücken mit Copernicus, auf das GeoSN-Niveau verschoben
            m = np.isfinite(h) & np.isfinite(cop)
            off = float(np.median(h[m] - cop[m])) if m.any() else 0.0
            h = np.where(np.isfinite(h), h, cop + off)
    else:
        from scipy import ndimage
        h = gelaende_cop(netz, lon, lat)
        quelle = ('Gelände: Copernicus DEM GLO-30 © DLR e.V. 2010–2014 und © Airbus Defence and Space GmbH 2014–2018, '
                  'bereitgestellt im Rahmen von COPERNICUS durch die Europäische Union und ESA')
        # Oberflächenmodell → Boden: in Wald/Ort Baumkronen und Dächer herausrechnen (Öffnen über ~100 m)
        lc20 = np.asarray(Image.fromarray(lc).resize((nx, ny), Image.NEAREST))[::-1]
        bedeckt = np.isin(lc20, [LC['wald'], LC['siedlung'], LC['gewerbe'], LC['gebuesch'], LC['garten']])
        hf = rb.fuellen(h, np.ones_like(h, bool))
        boden = ndimage.grey_opening(hf, size=(5, 5))
        w = ndimage.gaussian_filter(bedeckt.astype(float), 1.5)
        h = hf * (1 - w) + boden * w
        h = ndimage.gaussian_filter(h, 0.8)
    ATTR.append(quelle)
    h = rb.fuellen(h, np.ones_like(h, bool))
    # Wasserspiegel: Höhe entlang der OSM-Uferlinie (Median)
    lo_s, la_s = rb.geo(see_ring[:, 0], see_ring[:, 1])
    if sa is not None:
        hs = utm_abtasten(sa, see_ring[:, 0], see_ring[:, 1])
    else:
        hs = gelaende_cop(netz, np.asarray(lo_s), np.asarray(la_s))
    pegel = float(np.nanmedian(hs)) if np.isfinite(hs).any() else float(np.nanpercentile(h, 5))
    log(f'  Wasserspiegel ≈ {pegel:.1f} m, Gelände {np.nanmin(h) - pegel:+.0f} … {np.nanmax(h) - pegel:+.0f} m darüber')
    rel = np.clip(np.round((h - pegel) * 10), -2000, 20000).astype('<i2')

    # --- Gebäude
    geb, namen = gebaeude(feats['geb'], rueck, innen_see, E0, N0, E1, N1)
    log(f'  Gebäude: {len(geb)} (mit Namen: {len(namen)})')

    # --- Punkte (Türme, Aussicht)
    pkt = []
    for f in feats['pkt']:
        g = f.get('geometry') or {}; p = f.get('properties') or {}
        if g.get('type') == 'Point':
            c = g['coordinates']
        else:
            ps = polys(g)
            if not ps:
                continue
            a = np.array(ps[0][0]); c = a.mean(0)
        x, y = rb.utm(c[0], c[1]); q = rueck(x, y)
        if E0 < q[0] < E1 and N0 < q[1] < N1:
            pkt.append([round(float(q[0]), 1), round(float(q[1]), 1), p.get('name') or '', p.get('man_made') or p.get('tourism') or '',
                        zahl(p.get('height')) or 0])
    log(f'  Punkte: {len(pkt)} ' + '; '.join(p[2] for p in pkt if p[2])[:300])

    out = dict(v=1, erzeugt=time.strftime('%Y-%m-%d'), lage=lage, pegel=round(pegel, 2), quelle=ATTR,
               h=dict(x0=E0, y0=N0, cs=CS_H, nx=nx, ny=ny, dm=base64.b64encode(rel.tobytes()).decode()),
               lc=dict(x0=E0, y1=N1, cs=CS_LC, w=W, h=H, rle=rle(lc), klassen=LC),
               geb=geb, namen=namen, pkt=pkt)
    s = json.dumps(out, ensure_ascii=False, separators=(',', ':'))
    open(ZIEL, 'w', encoding='utf-8').write(s)
    log(f'{ZIEL}: {len(s) / 1e6:.1f} MB, fertig in {time.time() - t0:.0f} s')
    for w in rb.WARN:
        log('⚠️', w)


if __name__ == '__main__':
    hauptteil()
