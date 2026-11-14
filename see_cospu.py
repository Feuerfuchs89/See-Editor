#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Cospudener See – Revier aus echten Daten (wie Rügen, Usedom, Rostock)
=====================================================================
Wird von revier_bauen.py aufgerufen (Revier „cospu“), erzeugt dieselben Dateien wie die Küstenreviere:
  cospu-revier.json, cospu-gelaende.bin, cospu-umgebung.json, cospu-gebaeude.json, cospu-maske.png,
  cospu-vorschau.png, cospu-spiel.json + Kacheln (cospu-spiel-*.bin) und zusätzlich cospu-lage.json.

Quellen
- Ufer und Inseln: OSM-Relation 285950 in voller Auflösung (ODbL)
- Gelände: amtliches DGM Sachsen (GeoSN), sonst Copernicus GLO-30 mit herausgerechneten Baumkronen und Dächern
- Tiefen: EMODnet deckt Binnenseen nicht ab. Deshalb ein MODELL, geeicht an den bekannten Seewerten
  (Fläche 4,36 km², max. Tiefe 54 m, Volumen 109 Mio. m³ → mittlere Tiefe ≈ 25 m): flache Strände, steile Kippenhänge, tiefe Mitte.
  KEINE Messung, KEINE Navigationskarte.
- Gebäude, Wald, Landnutzung, Straßen, Landmarken: OSM

cospu-lage.json: Umrechnung vom alten Spielsystem (Ost/Nord in m, Ursprung Seemitte) ins Revier-System
(Meter ab Südwest-Ecke, x = Ost, y = Nord) und die Hafen-Aufmaße (LSC, Zöbigker, Steg Nordufer, Tonnen, Inseln) darin.
"""
import json, math
import numpy as np
from PIL import Image, ImageDraw
from scipy import ndimage

import revier_bauen as rb
import umland_cospu as uc

log, warn = rb.log, rb.warn

SEE_REL = 285950
LSC_IDX, HARB_IDX = 25, 121              # Uferpunkte im alten Spielsystem (COSPU_PTS)
PEGEL_NENN = 110.7                       # m ü. NHN (Vorgabe, wird aus dem Gelände nachgemessen)
FAKTEN = dict(flaeche=4.36e6, max_tiefe=54.0, volumen=109e6)     # Wikipedia/LMBV: 4,36 km², 54 m, 109 Mio. m³
PLUS_LSC = (51.26719, 12.32194)          # Plus Code 788C+VQW (Mitte der 14-m-Zelle), Kontrollpunkt LSC
ATTR_TIEFE = 'Seetiefen: Modell nach bekannten Seewerten (max. 54 m, Volumen 109 Mio. m³), KEINE Messung'

COSPU_OBJ = {"COSPU_STEGE":[[418.3,-451.7,539.6,-305.1,2.6,0],[527.1,-320.1,555.8,-341.7,2,5],[507.6,-343.7,550.5,-377.5,2,5],[490,-365,544.7,-409.2,2,5],[473.1,-385.5,534.9,-435.7,2,5],[451,-412.2,524.3,-477.2,2,5],[431.1,-436.2,493.6,-488.7,2,5],[559.5,-483.6,583,-501.9,1.6,0],[603.5,-383.2,620,-369.8,1.6,0],[568.1,-330.2,559.7,-324.3,1.6,0],[559.7,-324.3,571,-312.7,1.6,0],[410.1,1701.5,427.3,1726.4,1.6,0]],"COSPU_N22":[410.1,1701.5,427.3,1726.4],"COSPU_TONNEN":[[-654.7,-963.9,"spherical","Sondertonne"],[-221.2,-735.3,"spherical","Sondertonne"],[-436.4,-830.3,"spherical","Sondertonne"],[-477.2,-246.5,"conical","Cospudentonne"],[334.3,-297.6,"barrel","Hafentonne"],[635.4,826.4,"barrel","Gymnasium"],[48.8,980.5,"can","Nordtonne"]],"COSPU_INSELN":[[[-223.37,-485.06],[-222.32,-486.71],[-220.3,-487.05],[-217.58,-488.04],[-215.56,-487.38],[-214.8,-485.17],[-213.61,-482.84],[-215.15,-481.41],[-216.4,-479.75],[-217.86,-478.31],[-220.09,-478.09],[-221.28,-478.64],[-222.11,-479.86],[-222.25,-481.41],[-223.02,-483.18],[-223.37,-485.06]],[[-188.54,-484.5],[-189.23,-481.96],[-190.7,-480.97],[-192.23,-478.64],[-194.6,-478.2],[-197.38,-478.64],[-199.47,-480.52],[-199.12,-483.73],[-196.34,-485.61],[-193.55,-488.26],[-190.9,-488.7],[-188.82,-488.59],[-188.19,-486.82],[-188.54,-484.5]]],"LSC_REAL":{"od":[0.9986,-0.0523],"ta":24.1,"os":9.6,"po":53.6,"pn":[37.2,53.6,11,53.6],"dg":[-54.3,22.5,-38.4,46.8],"sm":[-11.6,9.7,-12,-2.1]}}


# ------------------------------------------------------------------ Ufer
def ufer(feats, geb, cfg):
    """OSM-Relation → Wasserteile (Außenring + Inseln), Land als Fläche mit Loch (Schlüssellochring), Fläche."""
    kand = []
    ist_rel = lambda f: str((f.get('properties') or {}).get('@id', '')) == str(SEE_REL) and str((f.get('properties') or {}).get('@type', 'r'))[:1] == 'r'
    feats = [f for f in feats if ist_rel(f)] or feats          # nur die Relation selbst (nicht getaggte Mitglieds-Wege)
    for f in feats:
        for aussen, loecher in uc.polys(f.get('geometry')):
            if len(aussen) < 4:
                continue
            lo, la = np.array(aussen, float)[:, :2].T; x, y = geb.to_m(lo, la)
            P = np.c_[np.asarray(x, float), np.asarray(y, float)]
            L = []
            for h in loecher:
                if len(h) < 4:
                    continue
                lo, la = np.array(h, float)[:, :2].T; x, y = geb.to_m(lo, la)
                L.append(np.c_[np.asarray(x, float), np.asarray(y, float)])
            kand.append((abs(rb.flaeche(P)), P, L))
    if not kand:
        raise RuntimeError(f'Seeufer (OSM-Relation {SEE_REL}) nicht gefunden')
    kand.sort(key=lambda c: -c[0])
    tol = cfg['ufer_tol']; teile = []
    for A, P, L in kand:
        if teile and A < 5e4:
            continue
        o = rb.dp_ring(P, tol)
        if rb.flaeche(o) < 0:
            o = o[::-1]
        ins = []
        for h in L:
            h2 = rb.dp_ring(h, min(tol, 0.5))
            if abs(rb.flaeche(h2)) < 4:
                continue
            ins.append(h2 if rb.flaeche(h2) < 0 else h2[::-1])
        teile.append(dict(outer=o, islands=ins))
    W, H = geb.W, geb.H
    for t in teile:
        a = t['outer']
        if a[:, 0].min() < 300 or a[:, 0].max() > W - 300 or a[:, 1].min() < 300 or a[:, 1].max() > H - 300:
            warn('Seeufer liegt nahe am Rand des Reviers (< 300 m) – bbox vergrößern')
    wf = sum(rb.flaeche(t['outer']) + sum(rb.flaeche(i) for i in t['islands']) for t in teile)
    log(f'  See: {wf / 1e6:.2f} km² (Soll {FAKTEN["flaeche"] / 1e6:.2f}), {len(teile[0]["outer"])} Uferpunkte, '
        f'{sum(len(t["islands"]) for t in teile)} Inseln')
    if abs(wf - FAKTEN['flaeche']) / FAKTEN['flaeche'] > 0.12:
        warn(f'OSM-Seefläche {wf / 1e6:.2f} km² weicht stark von 4,36 km² ab')
    land = [schluessel(W, H, teile[0]['outer'])] + [i[::-1] for t in teile for i in t['islands']]
    return teile, land, wf


def schluessel(W, H, ring):
    """Rechteck mit Loch (See) als ein einfacher Ring: Brücke von der Ecke zum See, See im Uhrzeigersinn."""
    R = np.asarray(ring, float)
    if rb.flaeche(R) < 0:
        R = R[::-1]
    k = int(np.argmin(np.hypot(R[:, 0], R[:, 1])))
    Rr = np.roll(R[::-1], -(len(R) - 1 - k), axis=0)           # im Uhrzeigersinn, beginnt am Brückenpunkt
    pts = [(0.0, 0.0), (W, 0.0), (W, H), (0.0, H), (0.0, 0.0)] + [tuple(p) for p in Rr] + [tuple(Rr[0]), (0.0, 0.0)]
    return np.array(pts, float)[:-1]


# ------------------------------------------------------------------ Tiefenmodell
def poly_maske(polys, W, H, cs, nx, ny, fuell=1):
    im = Image.new('L', (nx, ny), 0); d = ImageDraw.Draw(im)
    for P in polys:
        if len(P) >= 3:
            d.polygon([(p[0] / cs, (H - p[1]) / cs) for p in P], fill=fuell)
    return np.asarray(im) > 0


def tiefe_modell(mim, geb, cfg, teile, strand_ringe):
    """Tiefe (m, negativ) auf dem Gelände-Raster. Eichung: mittlere Tiefe = Volumen/Fläche, Maximum 54 m."""
    cs = cfg['zelle']; nx, ny = geb.W // cs, geb.H // cs; mc = cfg['maske']; f = cs // mc
    M5 = np.asarray(mim) >= 128
    d5 = ndimage.distance_transform_edt(M5) * mc                 # Abstand zum Land (m), feine Maske
    h5, w5 = M5.shape
    d5 = d5[:ny * f, :nx * f]; M5c = M5[:ny * f, :nx * f]
    dist = d5.reshape(ny, f, nx, f).mean(axis=(1, 3))
    wm = M5c.reshape(ny, f, nx, f).mean(axis=(1, 3)) >= 0.5
    dist = np.maximum(dist, mc * 0.5)
    Dmax = FAKTEN['max_tiefe']; ziel = FAKTEN['volumen'] / FAKTEN['flaeche']; p = 1.3
    dw = dist[wm]
    mittel = lambda L: float((Dmax * (1 - np.exp(-(dw / L) ** p))).mean())
    lo, hi = 20.0, 3000.0
    for _ in range(60):
        L = math.sqrt(lo * hi)
        if mittel(L) > ziel:
            lo = L           # zu tief → Hang flacher… L größer macht es flacher
        else:
            hi = L
    # mittel(L) fällt mit wachsendem L: zu tief (> Ziel) braucht größeres L
    L = math.sqrt(lo * hi)
    prof = Dmax * (1 - np.exp(-(dist / L) ** p))
    rng = np.random.default_rng(SEE_REL)
    rau = ndimage.gaussian_filter(rng.standard_normal(prof.shape), 6); rau /= max(1e-9, np.abs(rau).max())
    prof = np.clip(prof + rau * 2.5 * np.clip(prof / Dmax * 1.6, 0, 1), 0.3, Dmax)
    tief = np.where(wm, prof, 0.0)
    log(f'  Tiefenmodell: Hangmaß L = {L:.0f} m, mittlere Tiefe {tief[wm].mean():.1f} m (Soll {ziel:.1f}), max. {tief.max():.1f} m, '
        f'Volumen {tief[wm].sum() * cs * cs / 1e6:.0f} Mio. m³ (Soll {FAKTEN["volumen"] / 1e6:.0f})')
    # flache Strände: Böschung 1:25 vor Strandflächen
    if strand_ringe:
        sm = poly_maske(strand_ringe, geb.W, geb.H, mc, w5, h5)
        db = ndimage.distance_transform_edt(~sm) * mc
        db = db[:ny * f, :nx * f].reshape(ny, f, nx, f).min(axis=(1, 3))
        flach = wm & (db < 160)
        tief = np.where(flach, np.minimum(tief, 0.3 + db / 25.0), tief)
        log(f'  Strände: {int(flach.sum() * cs * cs / 1e4)} ha Flachwasser (1:25)')
    # Inseln (zu klein für das Raster): Flachwasser rund um jede Insel
    for t in teile:
        for I in t['islands']:
            cx, cy = I[:, 0].mean(), I[:, 1].mean(); r = float(np.hypot(I[:, 0] - cx, I[:, 1] - cy).mean())
            gy, gx = np.mgrid[0:ny, 0:nx]; X = (gx + 0.5) * cs; Y = geb.H - (gy + 0.5) * cs
            dr = np.hypot(X - cx, Y - cy)
            m = wm & (dr < r + 22)
            tief = np.where(m, np.minimum(tief, 0.35 + 0.05 * np.maximum(dr - r, 0)), tief)
    return -tief, wm


# ------------------------------------------------------------------ Gelände
def gelaende(netz, geb, cfg, mim, teile, env):
    cs = cfg['zelle']; nx, ny = geb.W // cs, geb.H // cs
    strand = [np.array(f['g'][0], float).reshape(-1, 2) for f in env if f.get('c') == 'beach' and f.get('t') == 'P' and f.get('g')]
    tiefe, wm = tiefe_modell(mim, geb, cfg, teile, strand)
    xs = (np.arange(nx) + 0.5) * cs; ys = geb.H - (np.arange(ny) + 0.5) * cs
    gx, gy = np.meshgrid(xs, ys)
    X, Y = gx + geb.ox, gy + geb.oy
    lon, lat = geb.to_ll(gx, gy)
    quellen = dict(tiefe=ATTR_TIEFE)
    attr = [rb.ATTRIBUTION[0], ATTR_TIEFE]
    ubox = (float(X.min()) - 50, float(Y.min()) - 50, float(X.max()) + 50, float(Y.max()) + 50)
    sa = uc.gelaende_sachsen(netz, ubox)
    if sa is not None:
        h = uc.utm_abtasten(sa, X, Y)
        if np.isnan(h).any():
            cop = uc.gelaende_cop(netz, lon, lat)
            m = np.isfinite(h) & np.isfinite(cop)
            off = float(np.median(h[m] - cop[m])) if m.any() else 0.0
            h = np.where(np.isfinite(h), h, cop + off)
        quellen['hoehe'] = sa['quelle']; attr.append(sa['quelle']); canopy = False
    else:
        h = uc.gelaende_cop(netz, lon, lat); canopy = True
        quellen['hoehe'] = 'Copernicus DEM GLO-30, Baumkronen und Dächer herausgerechnet'
        attr.append('Gelände: Copernicus DEM GLO-30 © DLR e.V. 2010–2014 und © Airbus Defence and Space GmbH 2014–2018, '
                    'bereitgestellt im Rahmen von COPERNICUS durch die Europäische Union und ESA')
    ok = np.isfinite(h).any()
    if not ok:
        warn('Keine Geländehöhen – Land wird flach angenommen')
        h = np.full(gx.shape, PEGEL_NENN + 1.0); quellen['hoehe'] = 'keine Daten (flach)'
    h = rb.fuellen(h, np.ones_like(h, bool))
    # Wasserspiegel aus dem Seegebiet messen (mind. 100 m vom Ufer)
    dist = ndimage.distance_transform_edt(wm) * cs
    sel = wm & (dist >= 100)
    pegel = float(np.nanmedian(h[sel])) if ok and sel.any() else PEGEL_NENN
    log(f'  Wasserspiegel gemessen {pegel:.2f} m ü. NHN (Vorgabe {PEGEL_NENN} m)')
    if abs(pegel - PEGEL_NENN) > 2.0:
        warn(f'Gemessener Wasserspiegel {pegel:.1f} m weicht von {PEGEL_NENN} m ab – Gelände relativ zum gemessenen Wert')
    if canopy and ok:
        # Oberflächenmodell → Boden: unter Wald/Ort/Gebüsch Kronen und Dächer herausrechnen
        def klass(*cs_):
            return [np.array(f['g'][0], float).reshape(-1, 2) for f in env if f.get('c') in cs_ and f.get('t') == 'P' and f.get('g')]
        bed = poly_maske(klass('forest', 'scrub', 'urban', 'building'), geb.W, geb.H, cs, nx, ny)
        w = ndimage.gaussian_filter(bed.astype(float), 1.5)
        boden = ndimage.grey_opening(h, size=(5, 5))
        h = h * (1 - w) + boden * w
        h = ndimage.gaussian_filter(h, 0.8)
    rel = np.maximum(h - pegel, 0.3)
    z = np.where(wm, tiefe, rel)
    cm = np.clip(np.round(z * 100), -32767, 32767).astype('<i2')
    quellen['wasserspiegel_nhn'] = round(pegel, 2)
    quellen['attribution'] = attr
    log(f'  Gelände {float(rel[~wm].min()):.1f} … {float(rel[~wm].max()):.1f} m über dem Wasser, Tiefe {float(tiefe[wm].min()):.1f} m')
    return cm, wm, quellen, (nx, ny)


# ------------------------------------------------------------------ Lage und Häfen
def vorbereiten(osm, geb, cfg):
    """Ufer, Lage (altes System → Revier), Häfen und Bahn. Ergänzt cfg['haefen'] und cfg['bahnen']."""
    teile, land, wf = ufer(osm['see'], geb, cfg)
    hin, rueck, ring, lage = uc.einpassen(osm['see'])
    ox, oy = geb.ox, geb.oy
    M = np.array(lage['utm33_M'], float); t = np.array(lage['utm33_t'], float) - np.array([ox, oy])
    alt = lambda E, N: (M @ np.array([E, N], float) + t)               # altes System → Revier (m)
    P = uc.COSPU_PTS
    def ll(xy):
        lo, la = geb.to_ll(xy[0], xy[1]); return (float(lo), float(la))
    lsc = alt(*P[LSC_IDX]); zoeb = alt(*P[HARB_IDX])
    plx, ply = rb.utm(PLUS_LSC[1], PLUS_LSC[0]); pl = np.array([float(plx) - ox, float(ply) - oy])
    d_pl = float(np.hypot(*(pl - lsc)))
    log(f'  LSC im Revier: {lsc[0]:.0f} / {lsc[1]:.0f}; Plus Code 788C+VQW liegt {d_pl:.0f} m daneben')
    if d_pl > 80:
        warn(f'LSC-Uferpunkt liegt {d_pl:.0f} m vom Plus-Code-Punkt – Einpassung prüfen')
    cfg['haefen'] = [
        dict(name='Leipziger Seesportclub', mitte=ll(lsc), groesse=400, tiefe=2.5, land_z=0.82, kai=False, pier_z=1.2),
        dict(name='Hafen Zöbigker', mitte=ll(zoeb), groesse=800, tiefe=3.0, land_z=1.0, kai=False, pier_z=1.2),
    ]
    out = teile[0]['outer']; cen = out.mean(axis=0)
    cfg['bahnen'] = {'bahn': dict(name='Regattabahn Cospudener See', nahe=ll(cen), r=2500, min_frei=250, cap=1500)}
    # Uferpunkt und Wasserrichtung am LSC (aus der echten OSM-Linie)
    def ufer_info(xy):
        d = np.hypot(out[:, 0] - xy[0], out[:, 1] - xy[1]); k = int(np.argmin(d)); n = len(out)
        a, b = out[(k - 8) % n], out[(k + 8) % n]; tx, ty = b - a; l = math.hypot(tx, ty) or 1
        nx_, ny_ = -ty / l, tx / l                                     # Ring positiv (links = Wasser)
        return dict(ufer=[round(float(out[k][0]), 1), round(float(out[k][1]), 1)], wasser=[round(nx_, 4), round(ny_, 4)], abstand=round(float(d[k]), 1))
    objs = {}
    C = COSPU_OBJ
    objs['stege'] = [[*[round(float(v), 1) for v in alt(e[0], e[1])], *[round(float(v), 1) for v in alt(e[2], e[3])], e[4], e[5]] for e in C['COSPU_STEGE']]
    objs['n22'] = [round(float(v), 1) for v in [*alt(C['COSPU_N22'][0], C['COSPU_N22'][1]), *alt(C['COSPU_N22'][2], C['COSPU_N22'][3])]]
    objs['tonnen'] = [[*[round(float(v), 1) for v in alt(q[0], q[1])], q[2], q[3]] for q in C['COSPU_TONNEN']]
    objs['inseln'] = [[[round(float(v), 2) for v in alt(p[0], p[1])] for p in ring] for ring in C['COSPU_INSELN']]
    lj = dict(format='seekoje-lage-1', revier='cospu', origin_utm=dict(x=ox, y=oy), alt_system=lage,
              revier_aus_alt=dict(M=[[float(v) for v in r] for r in M], t=[float(v) for v in t],
                                  formel='Revier[x,y] = M · [Ost_alt, Nord_alt] + t  (Meter ab Südwest-Ecke)'),
              lsc=dict(alt=P[LSC_IDX][:2], xy=[round(float(lsc[0]), 1), round(float(lsc[1]), 1)], plus_code='788C+VQW',
                       plus_code_abstand_m=round(d_pl, 1), aufmass=C['LSC_REAL'], **ufer_info(lsc)),
              zoebigker=dict(alt=P[HARB_IDX][:2], xy=[round(float(zoeb[0]), 1), round(float(zoeb[1]), 1)], **ufer_info(zoeb)),
              objekte=objs)
    return teile, land, wf, lj

