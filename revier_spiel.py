#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Seekoje – Spielexport für die Regattakoje
=========================================
Macht aus einem gebauten Revier die Dateien, die das Spiel lädt:
  <r>-spiel.json               Index: Kacheln, Landflächen, Orte, Leuchttürme, Seezeichen, Kurse
  <r>-spiel-uebersicht.bin     ganzes Revier grob (z int16 cm + Landnutzung uint8), zlib
  <r>-spiel-k-<i>-<j>.bin      Kacheln fein (z, Landnutzung, Landabstand, Häuser), zlib
Das Spiel hält die Übersicht immer im Speicher und lädt Kacheln nur rund um die Boote nach.

Wird von revier_bauen.py am Ende aufgerufen. Einzeln (ohne neue Downloads, aus vorhandenen Dateien):
  python revier_spiel.py hiddensee
"""
import json, math, os, sys, zlib, heapq, struct, glob
import numpy as np
from PIL import Image, ImageDraw
from scipy import ndimage

LU = {'forest': 1, 'urban': 2, 'farmland': 3, 'beach': 4, 'wetland': 5, 'scrub': 6, 'grass': 7}
LU_ORDER = ['farmland', 'grass', 'wetland', 'scrub', 'beach', 'urban', 'forest']


def log(*a):
    print(*a, flush=True)


# ------------------------------------------------------------------ Raster-Helfer
class Raster:
    """Tiefen-/Höhenraster in m, Zeile 0 = Norden."""
    def __init__(self, Z, cs, H):
        self.Z, self.cs, self.H = Z, cs, H; self.ny, self.nx = Z.shape

    def ij(self, x, y):
        return int((self.H - y) // self.cs), int(x // self.cs)

    def xy(self, j, i):
        return ((i + .5) * self.cs, self.H - (j + .5) * self.cs)

    def depth(self, x, y):
        j, i = self.ij(x, y)
        return -self.Z[j, i] if 0 <= j < self.ny and 0 <= i < self.nx else -99


def astar(R, a, b, thr):
    sj, si = R.ij(*a); tj, ti = R.ij(*b); Z = R.Z
    ok = (-Z) >= thr
    if not (ok[sj, si] and ok[tj, ti]):
        return None
    dep = np.clip(-Z, 0, 20); pen = 1 + 2.5 * np.clip(4 - dep, 0, 4) / 4
    dist = np.full(Z.shape, np.inf, np.float32); dist[sj, si] = 0
    prev = np.full(Z.shape, -1, np.int64)
    h = lambda j, i: math.hypot(j - tj, i - ti)
    pq = [(h(sj, si), 0.0, sj, si)]; ny, nx = Z.shape
    N8 = [(-1, 0, 1), (1, 0, 1), (0, -1, 1), (0, 1, 1), (-1, -1, 1.414), (-1, 1, 1.414), (1, -1, 1.414), (1, 1, 1.414)]
    while pq:
        f, d, j, i = heapq.heappop(pq)
        if j == tj and i == ti:
            break
        if d > dist[j, i]:
            continue
        for dj, di, c in N8:
            J, I = j + dj, i + di
            if 0 <= J < ny and 0 <= I < nx and ok[J, I]:
                nd = d + c * pen[J, I]
                if nd < dist[J, I]:
                    dist[J, I] = nd; prev[J, I] = j * nx + i; heapq.heappush(pq, (nd + h(J, I), nd, J, I))
    if prev[tj, ti] < 0:
        return None
    p = [(tj, ti)]
    while p[-1] != (sj, si):
        k = prev[p[-1]]; p.append((k // nx, k % nx))
    return [R.xy(j, i) for j, i in p[::-1]]


def los(R, a, b, thr, buf=30):
    L = math.hypot(b[0] - a[0], b[1] - a[1]); n = max(2, int(L / (R.cs / 2)))
    nxv, nyv = ((-(b[1] - a[1]) / L, (b[0] - a[0]) / L) if L > 0 else (0, 0))
    for k in range(n + 1):
        t = k / n; x = a[0] + (b[0] - a[0]) * t; y = a[1] + (b[1] - a[1]) * t
        for o in (0, -buf, buf):
            if R.depth(x + nxv * o, y + nyv * o) < thr:
                return False
    return True


def vereinfachen(R, path, thr, buf):
    out = [path[0]]; i = 0
    while i < len(path) - 1:
        j = len(path) - 1
        while j > i + 1 and not los(R, path[i], path[j], thr, buf):
            j -= 1
        out.append(path[j]); i = j
    return out


def zusammenfassen(R, pts, thr, buf=30, minlen=250):
    out = list(pts); geaendert = True
    while geaendert:
        geaendert = False
        for k in range(1, len(out) - 1):
            a, b, c = out[k - 1], out[k], out[k + 1]
            if (math.hypot(b[0] - a[0], b[1] - a[1]) < minlen or math.hypot(c[0] - b[0], c[1] - b[1]) < minlen) and los(R, a, c, thr, buf):
                del out[k]; geaendert = True; break
    return out


def route(R, anker, thr0=1.5):
    out = []
    for a, b in zip(anker, anker[1:]):
        p = None
        for thr in (thr0, thr0 - 0.2, thr0 - 0.4):
            p = astar(R, a, b, thr)
            if p:
                break
        if not p:
            raise RuntimeError(f'kein Weg durch tiefes Wasser von {a} nach {b}')
        s = vereinfachen(R, p, thr, 30)
        out += s if not out else s[1:]
    out = zusammenfassen(R, out, thr0, 12, 150 if R.cs <= 20 else 250)
    return zusammenfassen(R, out, thr0 - 0.3, 0, 100 if R.cs <= 20 else 200)


def bester_platz(CLR, R, x, y, r, cap=400):
    j0, i0 = R.ij(x, y); Rr = int(r / R.cs)
    j1, j2, i1, i2 = max(0, j0 - Rr), min(R.ny, j0 + Rr), max(0, i0 - Rr), min(R.nx, i0 + Rr)
    sub = CLR[j1:j2, i1:i2]; jj, ii = np.mgrid[j1:j2, i1:i2]
    score = np.minimum(sub, cap) - np.hypot(jj - j0, ii - i0) * R.cs * 0.08
    k = np.unravel_index(np.argmax(score), score.shape)
    return R.xy(jj[k], ii[k]), float(sub[k])


def tor_breite(R, p, u, cap=180):
    r = (-u[1], u[0]); out = []
    for s in (1, -1):
        d = 0
        while d < cap and R.depth(p[0] + r[0] * s * (d + 10), p[1] + r[1] * s * (d + 10)) >= 1.3:
            d += 10
        out.append(d)
    return out


def verdichten(route, maxleg=5000, teil=3500):
    out = [route[0]]
    for a, b in zip(route, route[1:]):
        L = math.hypot(b[0] - a[0], b[1] - a[1]); n = int(L // teil) if L > maxleg else 0
        for k in range(1, n + 1):
            t = k / (n + 1); out.append((a[0] + (b[0] - a[0]) * t, a[1] + (b[1] - a[1]) * t))
        out.append(b)
    return out


# ------------------------------------------------------------------ Hilfen für Geometrie
def dp(P, tol):
    P = np.asarray(P, float)
    if tol <= 0 or len(P) < 3:
        return P
    keep = np.zeros(len(P), bool); keep[0] = keep[-1] = True; st = [(0, len(P) - 1)]
    while st:
        i, j = st.pop()
        if j <= i + 1:
            continue
        a, b = P[i], P[j]; seg = P[i + 1:j]; ab = b - a; L2 = float(ab @ ab)
        d = np.hypot(*(seg - a).T) if L2 == 0 else np.hypot(*(seg - (a + np.clip(((seg - a) @ ab) / L2, 0, 1)[:, None] * ab)).T)
        k = int(np.argmax(d))
        if d[k] > tol:
            m = i + 1 + k; keep[m] = True; st += [(i, m), (m, j)]
    return P[keep]


def dp_ring(P, tol):
    P = np.asarray(P, float)
    if len(P) > 1 and np.allclose(P[0], P[-1]):
        P = P[:-1]
    if len(P) < 4:
        return P
    k = int(np.argmax(np.hypot(*(P - P[0]).T)))
    a = dp(P[:k + 1], tol); b = dp(np.vstack([P[k:], P[:1]]), tol)
    R = np.vstack([a[:-1], b[:-1]])
    return R if len(R) >= 3 else P


def flaeche(P):
    P = np.asarray(P, float); x, y = P[:, 0], P[:, 1]
    return 0.5 * float(np.dot(x, np.roll(y, -1)) - np.dot(y, np.roll(x, -1)))


# ------------------------------------------------------------------ Export
def export(r, cfg, meta, cm, cs, env, aus, utm, geo):
    """cm: int16-Raster in cm (Zeile 0 = Norden) mit Zellgröße cs; env: Umgebungsobjekte (mit Gebäuden);
    utm/geo: Umrechnung Länge/Breite <-> UTM33."""
    sp = cfg.get('spiel', {}); gcs = sp.get('zelle', 40); T = sp.get('kachel', 400)
    W, H = meta['size']['w'], meta['size']['h']; ox, oy = meta['origin_utm']['x'], meta['origin_utm']['y']
    ll2m = lambda lo, la: tuple(float(v) for v in np.subtract(utm(lo, la), (ox, oy)))
    Zn = cm.astype(np.float32) / 100.0
    Rn = Raster(Zn, cs, H)                                  # natives Raster (für Kurse)
    f = max(1, gcs // cs)
    ny, nx = Zn.shape[0] // f, Zn.shape[1] // f
    Z = Zn[:ny * f, :nx * f].reshape(ny, f, nx, f).mean(axis=(1, 3)) if f > 1 else Zn.copy()
    wet = Z < 0
    log(f'Spielexport: {nx}×{ny} Zellen à {gcs} m, Kacheln {T}×{T} ({T * gcs / 1000:.0f} km)')
    # --- Landnutzung
    LUi = Image.new('L', (nx, ny), 0); dr = ImageDraw.Draw(LUi)
    fl = lambda g: [(g[k] / gcs, (H - g[k + 1]) / gcs) for k in range(0, len(g), 2)]
    for cls in LU_ORDER:
        for ft in env:
            if ft.get('c') == cls and ft.get('t') == 'P' and len(ft['g'][0]) >= 6:
                dr.polygon(fl(ft['g'][0]), fill=LU[cls])
                for hole in ft['g'][1:]:
                    if len(hole) >= 6:
                        dr.polygon(fl(hole), fill=0)
    lu = np.asarray(LUi).astype(np.uint8).copy(); lu[wet] = 0
    cd = np.clip(ndimage.distance_transform_edt(~wet), 0, 255).astype(np.uint8)
    wd = ndimage.distance_transform_edt(~wet) * gcs
    zc = np.clip(np.round(Z * 100), -32767, 32767).astype('<i2')
    # --- Häuser in Ufernähe
    def wdist(x, y):
        j, i = int((H - y) // gcs), int(x // gcs)
        return wd[j, i] if 0 <= j < ny and 0 <= i < nx else 1e9
    haeuser = []
    for ft in env:
        if ft.get('c') != 'building' or ft.get('t') != 'P':
            continue
        g = np.array(ft['g'][0], float).reshape(-1, 2)
        if len(g) < 3:
            continue
        c = g.mean(0)
        if wdist(*c) > sp.get('haus_abstand', 900):
            continue
        q = g - c; ev, evec = np.linalg.eigh(q.T @ q); ax = evec[:, 1]
        a_ = q @ ax; b_ = q @ np.array([-ax[1], ax[0]]); l = a_.max() - a_.min(); w = b_.max() - b_.min()
        if l < 3 or w < 2 or l > 80:
            continue
        haeuser.append((c[0], c[1], l, w, math.atan2(ax[1], ax[0]), ft.get('h', 8)))
    log(f'  {len(haeuser)} Häuser in Ufernähe')
    # --- Übersicht (doppelte Zellgröße)
    nyo, nxo = ny // 2, nx // 2
    zo = np.clip(np.round(Z[:nyo * 2, :nxo * 2].reshape(nyo, 2, nxo, 2).mean(axis=(1, 3)) * 100), -32767, 32767).astype('<i2')
    luo = lu[:nyo * 2:2, :nxo * 2:2].copy(); luo[zo < 0] = 0
    uebersicht = f'{r}-spiel-uebersicht.bin'
    open(os.path.join(aus, uebersicht), 'wb').write(zlib.compress(zo.tobytes() + luo.tobytes(), 9))
    # --- Kacheln
    for alt in glob.glob(os.path.join(aus, f'{r}-spiel-k-*.bin')):
        os.remove(alt)
    kacheln = []
    hs_arr = np.array(haeuser, float) if haeuser else np.zeros((0, 6))
    for tj in range(math.ceil(ny / T)):
        for ti in range(math.ceil(nx / T)):
            j1, j2, i1, i2 = tj * T, min(ny, (tj + 1) * T), ti * T, min(nx, (ti + 1) * T)
            zt = zc[j1:j2, i1:i2]
            if (zt > -400).sum() == 0:      # nur tiefe See (> 4 m): die Übersicht reicht
                continue
            ex0, ny0 = i1 * gcs, H - j2 * gcs                        # Südwest-Ecke der Kachel (m)
            if len(hs_arr):
                m = (hs_arr[:, 0] >= i1 * gcs) & (hs_arr[:, 0] < i2 * gcs) & (hs_arr[:, 1] <= H - j1 * gcs) & (hs_arr[:, 1] > H - j2 * gcs)
                hk = hs_arr[m][:sp.get('haeuser_je_kachel', 7000)]
            else:
                hk = hs_arr
            hb = np.zeros((len(hk), 6), '<i2')
            if len(hk):
                hb[:, 0] = np.round(hk[:, 0] - ex0); hb[:, 1] = np.round(hk[:, 1] - ny0)
                hb[:, 2] = np.round(hk[:, 2] * 10); hb[:, 3] = np.round(hk[:, 3] * 10)
                hb[:, 4] = np.round(hk[:, 4] * 1000); hb[:, 5] = np.round(np.minimum(hk[:, 5], 60) * 10)
            kx, ky = i2 - i1, j2 - j1
            roh = b'RKT1' + struct.pack('<HHI', kx, ky, len(hk)) + zt.tobytes() + lu[j1:j2, i1:i2].tobytes() + cd[j1:j2, i1:i2].tobytes() + hb.tobytes()
            name = f'{r}-spiel-k-{ti:02d}-{tj:02d}.bin'
            open(os.path.join(aus, name), 'wb').write(zlib.compress(roh, 9))
            kacheln.append([ti, tj, name, kx, ky, len(hk)])
    log(f'  {len(kacheln)} Kacheln geschrieben')
    # --- Landflächen, Orte, Leuchttürme, Seezeichen
    tol = sp.get('land_tol', 10 if W * H < 2e9 else 15); amin = sp.get('land_min', 3000 if W * H < 2e9 else 6000)
    land = []
    for ring in meta['land']:
        q = dp_ring(np.array(ring, float), tol)
        if abs(flaeche(q)) > amin:
            land.append([int(round(v)) for p in q for v in p])
    cmap = {'red': 'r', 'green': 'g', 'yellow': 'y', 'black': 'k', 'white': 'w', 'orange': 'o'}
    sm = []
    for s in meta['seamarks']:
        t = s.get('typ', '')
        k = ('L' if 'lateral' in t else 'C' if 'cardinal' in t else 'S' if 'special' in t else 'I' if 'isolated' in t else 'W' if 'safe' in t else 'F' if t.startswith('light') else None)
        if not k:
            continue
        col = ''.join(cmap.get(c, '') for c in (s.get('farbe') or '').split(';'))
        sm.append([round(s['x']), round(s['y']), k, col, (s.get('form') or '')[:8], s.get('name', '')[:30], (s.get('kategorie') or '')[:12]])
    rank = {'town': 0, 'city': 0, 'village': 1, 'island': 1, 'hamlet': 2, 'peninsula': 2, 'locality': 3, 'cape': 3}
    places = [[f_['g'][0], f_['g'][1], f_['n'], rank.get(f_.get('s'), 4)] for f_ in env if f_.get('c') == 'place' and f_.get('n') and f_.get('t') == 'N' and f_.get('s') in rank]
    lights = [[f_['g'][0], f_['g'][1], f_.get('n', ''), f_.get('h', 20)] for f_ in env if f_.get('c') == 'lighthouse' and f_.get('t') == 'N']
    # --- Kurse
    CLR = ndimage.distance_transform_edt((-Zn) >= 1.4) * cs
    CL3 = ndimage.distance_transform_edt(np.pad((-Zn) >= 3, 1))[1:-1, 1:-1] * cs
    def name_bei(p, maxd=6000):
        best = None
        for x, y, n, rk in places:
            d = math.hypot(x - p[0], y - p[1]) + rk * 700
            if d < maxd and (best is None or d < best[0]):
                best = (d, n)
        return best[1] if best else ''
    def tore(rt, ziel_name):
        rt = verdichten(rt); G = []
        for k in range(1, len(rt) - 1):
            a, b, c = rt[k - 1], rt[k], rt[k + 1]
            u1 = np.subtract(b, a); u1 /= np.linalg.norm(u1); u2 = np.subtract(c, b); u2 /= np.linalg.norm(u2); u = u1 + u2
            if np.linalg.norm(u) < 1e-6:
                u = u1
            u /= np.linalg.norm(u); l_, r_ = tor_breite(Rn, b, u); hw = max(25, min(l_, r_, 150)); nb = name_bei(b)
            G.append(dict(x=round(b[0]), y=round(b[1]), u=[round(float(u[0]), 4), round(float(u[1]), 4)], hw=int(hw), name=f'Tor {k}' + (' · ' + nb if nb else '')))
        a, b = rt[-2], rt[-1]; u = np.subtract(b, a); u /= np.linalg.norm(u); l_, r_ = tor_breite(Rn, b, u)
        fin = dict(x=round(b[0]), y=round(b[1]), u=[round(float(u[0]), 4), round(float(u[1]), 4)], hw=int(max(30, min(l_, r_, 90))), name=ziel_name)
        return G, fin
    Lsum = lambda s: sum(math.hypot(b[0] - a[0], b[1] - a[1]) for a, b in zip(s, s[1:]))
    kurse = {}
    for key, k in cfg.get('kurse', {}).items():
        try:
            if not all(0 <= q[0] <= W and 0 <= q[1] <= H for q in [ll2m(*k['start']), ll2m(*k['ziel'])] + [ll2m(*p) for p in k.get('anker', [])]):
                raise RuntimeError('liegt teilweise außerhalb des Reviers')
            st, _ = bester_platz(CLR, Rn, *ll2m(*k['start']), k.get('start_r', 2000))
            anker = [st] + [ll2m(*p) for p in k.get('anker', [])] + [ll2m(*k['ziel'])]
            rt = route(Rn, anker)
            G, fin = tore(rt, k.get('ziel_name', 'Ziel'))
            kurse[key] = dict(name=k['name'], kurz=k.get('kurz', ''), sm=round(Lsum(rt) / 1852, 1), start=[round(st[0]), round(st[1])],
                              gates=G, finish=fin, route=[[round(p[0]), round(p[1])] for p in rt])
            log(f'  Kurs {k["name"]}: {kurse[key]["sm"]} sm, {len(G)} Tore')
        except Exception as ex:
            log(f'  WARNUNG Kurs {key}: {ex}')
    for key, b in cfg.get('bahnen', {}).items():
        bx, by = ll2m(*b['nahe'])
        if not (0 <= bx <= W and 0 <= by <= H):
            log(f'  WARNUNG Bahn {key}: liegt außerhalb des Reviers'); continue
        p, frei = bester_platz(CL3, Rn, bx, by, b.get('r', 4000), cap=2500)
        if frei < 800:
            log(f'  WARNUNG Bahn {key}: zu wenig freies Wasser ({frei:.0f} m) – weggelassen'); continue
        kurse[key] = dict(name=b['name'], center=[round(p[0]), round(p[1])], frei_m=int(frei), bahn=True)
        log(f'  Bahn {b["name"]}: Freiraum {frei:.0f} m')
    # --- Feuer (echte Kennung) und Leuchttürme
    STD_H = {'buoy': 2.5, 'beacon': 5.0, 'light_minor': 8.0, 'light_major': 15.0, 'landmark': 15.0, 'light_float': 6.0, 'light_vessel': 10.0, 'platform': 10.0}
    tuerme = []
    for f_ in env:
        ist_lt = f_.get('c') == 'lighthouse' or (f_.get('c') == 'building' and f_.get('s') == 'lighthouse') or \
            (f_.get('c') in ('tower', 'building') and 'Peilturm' in (f_.get('n') or ''))
        if not ist_lt:
            continue
        if f_.get('t') == 'N':
            x, y = f_['g'][0], f_['g'][1]
        elif f_.get('t') == 'P':
            g = f_['g'][0]; x, y = sum(g[0::2]) / (len(g) // 2), sum(g[1::2]) / (len(g) // 2)
        else:
            continue
        if any(math.hypot(x - q[0], y - q[1]) < 15 for q in tuerme):
            continue
        tuerme.append([int(round(x)), int(round(y)), f_.get('n', ''), round(float(f_.get('h') or 0), 1)])
    feuer = []
    for s_ in meta['seamarks']:
        fd = s_.get('feuer')
        if not fd:
            continue
        typ = s_.get('typ', ''); hs = None
        try:
            hs = float(str(s_.get('hoehe', '')).replace('m', '').replace(',', '.')) if s_.get('hoehe') else None
        except ValueError:
            hs = None
        h = fd.get('h') or hs or next((v for k, v in STD_H.items() if typ.startswith(k)), 4.0)
        feuer.append(dict(x=round(s_['x']), y=round(s_['y']), h=round(float(h), 1), typ=typ, name=s_.get('name', ''), f=fd))
        # Feuer auf Bauwerk ohne eigenen Leuchtturm-Eintrag: kleinen Turm vorsehen
        if (typ.startswith('light') or typ == 'landmark') and not any(math.hypot(s_['x'] - q[0], s_['y'] - q[1]) < 40 for q in tuerme):
            tuerme.append([round(s_['x']), round(s_['y']), s_.get('name', ''), round(float(hs or fd.get('h') or 10), 1)])
    # bekannte Leuchttürme/Feuer, die in OSM fehlen oder anders eingetragen sind (Recherche: Lighthouse Directory)
    for ex in cfg.get('feuer_extra', []):
        ex_x, ex_y = ll2m(*ex['pos'])
        if ex.get('turm') and not any(math.hypot(ex_x - q[0], ex_y - q[1]) < 60 for q in tuerme):
            tuerme.append([round(ex_x), round(ex_y), ex['name'], ex.get('turm')])
        if ex.get('f') and not any(math.hypot(ex_x - q['x'], ex_y - q['y']) < 150 and q['f'].get('c') for q in feuer):
            feuer.append(dict(x=round(ex_x), y=round(ex_y), h=ex.get('h', 30), typ='light_major', name=ex['name'], f=ex['f'], quelle='Recherche'))
    log(f'  {len(feuer)} Feuer mit Kennung, {len(tuerme)} Leuchttürme/Feuerträger')
    # --- Hafen-Ausschnitte (4 m)
    haefen = []
    for alt in glob.glob(os.path.join(aus, f'{r}-spiel-hafen-*.bin')):
        os.remove(alt)
    for hn, hf in enumerate(cfg.get('haefen', [])):
        hcs = 4; S_ = hf.get('groesse', 2400)
        cx, cy = ll2m(*hf['mitte'])
        x0 = math.floor((cx - S_ / 2) / gcs) * gcs; y0 = math.floor((cy - S_ / 2) / gcs) * gcs
        if x0 < 0 or y0 < 0 or x0 + S_ > W or y0 + S_ > H:
            log(f'  WARNUNG Hafen {hf["name"]}: außerhalb des Reviers'); continue
        n_ = S_ // hcs; y1 = y0 + S_
        toP = lambda x, y: ((x - x0) / hcs, (y1 - y) / hcs)
        mk = Image.new('L', (n_, n_), 0); dm = ImageDraw.Draw(mk)
        for ring in meta['land']:
            xs = [q[0] for q in ring]; ys = [q[1] for q in ring]
            if max(xs) < x0 or min(xs) > x0 + S_ or max(ys) < y0 or min(ys) > y1:
                continue
            dm.polygon([toP(q[0], q[1]) for q in ring], fill=1)
        stege = []
        BREITE = {'pier': 3.5, 'breakwater': 7.0, 'groyne': 3.0, 'quay': 0}
        for f_ in env:
            if f_.get('c') != 'pier' or f_.get('s') == 'coastline':
                continue
            k_ = f_.get('s') if f_.get('s') in BREITE else 'pier'
            if f_.get('t') == 'L':
                g = f_['g']; xs, ys = g[0::2], g[1::2]
            elif f_.get('t') == 'P':
                g = f_['g'][0]; xs, ys = g[0::2], g[1::2]
            else:
                continue
            if max(xs) < x0 or min(xs) > x0 + S_ or max(ys) < y0 or min(ys) > y1:
                continue
            pts = [toP(a_, b_) for a_, b_ in zip(xs, ys)]
            if f_['t'] == 'P' and len(pts) >= 3:
                dm.polygon(pts, fill=2); stege.append(dict(k=k_, t='P', g=f_['g'][0]))
            elif f_['t'] == 'L' and BREITE[k_] > 0 and len(pts) >= 2:
                dm.line(pts, fill=2, width=max(1, int(round(BREITE[k_] / hcs)))); stege.append(dict(k=k_, t='L', w=BREITE[k_], g=g))
        msk = np.asarray(mk).astype(np.uint8).copy()
        # Kaimauern: Landkante in Hafennähe (nahe Stegen/Molen oder Hafen-Objekten) → Typ 3, 2 Zellen breit
        nah = np.zeros_like(msk, bool)
        if (msk == 2).any():
            nah |= ndimage.distance_transform_edt(msk != 2) * hcs < 250
        hm = Image.new('L', (n_, n_), 0); dh = ImageDraw.Draw(hm); rr = 300 / hcs
        for f_ in env:
            if f_.get('c') != 'harbor':
                continue
            g = f_['g']; xs, ys = (([g[0]], [g[1]]) if f_['t'] == 'N' else (g[0][0::2], g[0][1::2]) if f_['t'] == 'P' else (g[0::2], g[1::2]))
            px, py = toP(sum(xs) / len(xs), sum(ys) / len(ys))
            if -rr < px < n_ + rr and -rr < py < n_ + rr:
                dh.ellipse([px - rr, py - rr, px + rr, py + rr], fill=1)
        nah |= np.asarray(hm) > 0
        wasser = msk == 0
        kante = (msk == 1) & ndimage.binary_dilation(wasser, iterations=2)
        msk[kante & nah] = 3
        jj, ii = np.mgrid[0:n_, 0:n_]
        Xc = x0 + (ii + 0.5) * hcs; Yc = y1 - (jj + 0.5) * hcs
        fx = Xc / cs - 0.5; fy = (H - Yc) / cs - 0.5; i0 = np.clip(np.floor(fx).astype(int), 0, Zn.shape[1] - 2); j0 = np.clip(np.floor(fy).astype(int), 0, Zn.shape[0] - 2)
        tx = fx - i0; ty = fy - j0
        zc = (Zn[j0, i0] * (1 - tx) + Zn[j0, i0 + 1] * tx) * (1 - ty) + (Zn[j0 + 1, i0] * (1 - tx) + Zn[j0 + 1, i0 + 1] * tx) * ty
        tief = hf.get('tiefe', 3.0)
        z = np.where(msk == 0, np.minimum(zc, -tief), np.where(msk == 2, 1.8, np.where(msk == 3, np.maximum(zc, 1.9), np.maximum(zc, 1.6))))
        rand = np.zeros_like(msk, bool); rand[:2, :] = rand[-2:, :] = rand[:, :2] = rand[:, -2:] = True
        z = np.where(rand, zc, z)                       # Rand passt zum groben Gelände
        zcm = np.clip(np.round(z * 100), -32767, 32767).astype('<i2')
        name = f'{r}-spiel-hafen-{hn}.bin'
        open(os.path.join(aus, name), 'wb').write(zlib.compress(b'RKH1' + struct.pack('<iiHH', int(x0), int(y0), hcs, n_) + zcm.tobytes() + msk.tobytes(), 9))
        haefen.append(dict(name=hf['name'], file=name, x0=int(x0), y0=int(y0), cs=hcs, n=int(n_), stege=stege))
        log(f'  Hafen {hf["name"]}: {S_ / 1000:.1f} km, {len(stege)} Molen/Stege, {(msk == 0).mean() * 100:.0f} % Wasser')
    index = dict(format='regattakoje-revier-2', revier=r, name=cfg.get('spielname', meta['name']), attribution=meta['attribution'],
                 hinweis='Vereinfachte Regattabahnen entlang tiefem Wasser laut Datensatz. Keine Navigationskarte.',
                 origin_utm=meta['origin_utm'], size=meta['size'],
                 grid=dict(cs=gcs, nx=nx, ny=ny, tile=T, tiles=kacheln, tile_format='RKT1: <HHI nx,ny,nhaus> z int16 cm, landnutzung uint8, landabstand uint8, haeuser int16[6] (x,y m ab SW der Kachel, l*10, b*10, winkel*1000, h*10); zlib'),
                 overview=dict(file=uebersicht, cs=gcs * 2, nx=nxo, ny=nyo, format='z int16 cm, landnutzung uint8; zlib'),
                 lu_klassen={'1': 'Wald', '2': 'Ort', '3': 'Acker', '4': 'Strand', '5': 'Feuchtgebiet', '6': 'Gebüsch', '7': 'Wiese'},
                 land=land, seamarks=sm, places=places, lights=lights, courses=kurse, feuer=feuer, tuerme=tuerme, haefen=haefen)
    json.dump(index, open(os.path.join(aus, f'{r}-spiel.json'), 'w', encoding='utf-8'), ensure_ascii=False, separators=(',', ':'))
    gr = sum(os.path.getsize(os.path.join(aus, k[2])) for k in kacheln)
    log(f'  Spieldaten: Index {os.path.getsize(os.path.join(aus, f"{r}-spiel.json")) / 1e6:.1f} MB, Übersicht {os.path.getsize(os.path.join(aus, uebersicht)) / 1e6:.1f} MB, Kacheln zusammen {gr / 1e6:.1f} MB')
    return index


if __name__ == '__main__':
    import argparse
    sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
    import revier_bauen as rb
    ap = argparse.ArgumentParser(description='Spielexport aus vorhandenen Revierdateien')
    ap.add_argument('revier'); ap.add_argument('--aus', default='.')
    a = ap.parse_args(); r = a.revier; P = lambda s: os.path.join(a.aus, f'{r}-{s}')
    meta = json.load(open(P('revier.json'), encoding='utf-8')); g = meta['grid']
    cm = np.fromfile(P('gelaende.bin'), '<i2').reshape(g['nrows'], g['ncols'])
    env = json.load(open(P('umgebung.json'), encoding='utf-8'))['features']
    if os.path.exists(P('gebaeude.json')):
        env = env + json.load(open(P('gebaeude.json'), encoding='utf-8'))['features']
    export(r, rb.REVIERE[r], meta, cm, g['cellsize'], env, a.aus, rb.utm, rb.geo)
