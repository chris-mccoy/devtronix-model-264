#!/usr/bin/env python3
"""
fluxdecode.py -- decode flux-level dumps of Devtronix Model 264 floppies to sector images.

Two input formats are understood:

  KryoFlux stream folders   one <prefix>NN.S.raw file per cylinder NN and side S
                            (as written by DTC; ~5 revolutions per track)
  HxC .hfe                  HXCPICFE v0, 2 sides, MFM bitstream per track

Disk format (see README.md): IBM-style MFM at 250 kbit/s, 1024-byte sectors
numbered 1..5 per track, 80 cylinders, 2 sides.  Output is the per-side layout
the other tools use: <name>_s0 and <name>_s1, 409600 bytes each, cylinder c at
offset c*5120, sector r at (r-1)*1024.

usage:
  fluxdecode.py STREAMDIR|FILE.hfe OUTDIR/NAME [--ref REF_s0 REF_s1] [--jobs N]
  fluxdecode.py --all [--images ../disk-images] [--out ../decoded-images]

Every revolution of every track is decoded by a software PLL and the first
copy of each sector whose ID and data CRCs are both good is kept.  With --ref
(the sector image the KryoFlux software itself produced from the same read) the
good flux sectors are compared against it, and sectors that never decoded with
a good CRC are filled from it (noted in the report) instead of being zeroed.
A per-disk report <name>.report.txt lists every sector that was bad, missing,
filled, or differs from the reference.
"""
import argparse, bisect, collections, concurrent.futures, json, os, pathlib, re, struct, sys

SECTOR, SPT, CYLS, SIDES = 1024, 5, 80, 2
SIDE_BYTES = SECTOR * SPT * CYLS           # 409600
MFM_RATE = 250_000                         # bit/s (data); bit cell 2 us

# ---------------------------------------------------------------- CRC-16/CCITT (WD179x)
_CRC = []
for _b in range(256):
    _c = _b << 8
    for _ in range(8):
        _c = ((_c << 1) ^ 0x1021) if _c & 0x8000 else (_c << 1)
    _CRC.append(_c & 0xFFFF)

def crc16(data, crc=0xFFFF):
    for b in data:
        crc = ((crc << 8) & 0xFFFF) ^ _CRC[(crc >> 8) ^ b]
    return crc

# ---------------------------------------------------------------- KryoFlux stream
def read_kryoflux(path):
    """Return (flux ticks list, list of flux indices at which an index pulse fell, sck Hz)."""
    d = pathlib.Path(path).read_bytes()
    flux, offs = [], []            # offs[i] = stream byte offset of flux i
    index_pos = []
    sck = 24027428.5714285
    i = n = 0                      # n = stream position (bytes, OOB excluded)
    ovl = 0
    L = len(d)
    while i < L:
        b = d[i]
        if b >= 0x0E:                      # Flux1
            flux.append(ovl + b); offs.append(n); ovl = 0; i += 1; n += 1
        elif b <= 0x07:                    # Flux2
            flux.append(ovl + (b << 8) + d[i + 1]); offs.append(n); ovl = 0; i += 2; n += 2
        elif b == 0x08: i += 1; n += 1     # Nop1
        elif b == 0x09: i += 2; n += 2     # Nop2
        elif b == 0x0A: i += 3; n += 3     # Nop3
        elif b == 0x0B: ovl += 0x10000; i += 1; n += 1   # Ovl16
        elif b == 0x0C:                    # Flux3
            flux.append(ovl + (d[i + 1] << 8) + d[i + 2]); offs.append(n); ovl = 0; i += 3; n += 3
        else:                              # 0x0D OOB
            typ, ln = struct.unpack_from('<BH', d, i + 1)
            if typ == 0x0D:
                break
            p = d[i + 4:i + 4 + ln]
            if typ == 2 and ln >= 12:
                spos, scount, icount = struct.unpack_from('<3I', p)
                index_pos.append(spos)
            elif typ == 4:
                m = re.search(rb'sck=([0-9.]+)', p)
                if m:
                    sck = float(m.group(1))
            i += 4 + ln
    idx = [bisect.bisect_left(offs, sp) for sp in index_pos]
    return flux, idx, sck

# ---------------------------------------------------------------- PLL: flux -> MFM bit cells
def flux_to_bits(flux, start, end, cell, state=None, out=None):
    """Decode flux[start:end] to MFM bits (bytearray of 0/1).  `state` carries the PLL
    (clock, ticks) across calls so a revolution can be decoded after the previous one."""
    clock, ticks = state if state else (cell, 0.0)
    clock_min, clock_max = cell * 0.9, cell * 1.1
    bits = out if out is not None else bytearray()
    append = bits.append
    for k in range(start, end):
        ticks += flux[k]
        if ticks < clock / 2:
            continue
        zeros = 0
        while True:
            ticks -= clock
            if ticks < clock / 2:
                break
            zeros += 1
            append(0)
        append(1)
        if zeros <= 3:
            clock += ticks * 0.05
        else:
            clock += (cell - clock) * 0.05
        clock = min(max(clock, clock_min), clock_max)
        ticks *= 0.4
    return bits, (clock, ticks)

# ---------------------------------------------------------------- MFM sector scan
A1_BITS = bytes([0, 1, 0, 0, 0, 1, 0, 0, 1, 0, 0, 0, 1, 0, 0, 1])   # 0x4489
SYNC = A1_BITS * 3
_TR = bytes.maketrans(bytes([0, 1]), b'01')

def mfm_bytes(bits, p, n):
    """Decode n data bytes from MFM cells starting at bit p (clock bit first)."""
    s = bits[p + 1:p + 16 * n:2]
    if len(s) < 8 * n:
        return None
    return int(s.translate(_TR).decode(), 2).to_bytes(n, 'big')

def scan_sectors(bits, start, found, cyl_hint=None):
    """Find IDAM/DAM pairs in bits[start:].  found[sector] = list of (good, data, (c,h,r,n)).
    Returns the position up to which the scan is complete."""
    p = bits.find(SYNC, start)
    last = start
    while p >= 0:
        last = p
        q = p + 48
        mark = mfm_bytes(bits, q, 1)
        if mark is None:
            break
        if mark[0] == 0xFE:
            idf = mfm_bytes(bits, q + 16, 6)
            if idf is None:
                break
            c, h, r, n = idf[0], idf[1], idf[2], idf[3]
            id_ok = crc16(b'\xa1\xa1\xa1\xfe' + idf) == 0
            # data address mark: within gap2 (~43 bytes) -- allow up to 100 bytes
            dp = bits.find(SYNC, q + 16 * 7, q + 16 * 7 + 16 * 100)
            if dp >= 0 and id_ok:
                dm = mfm_bytes(bits, dp + 48, 1)
                size = 128 << (n & 3)
                if dm is not None and dm[0] in (0xFB, 0xF8):
                    body = mfm_bytes(bits, dp + 64, size + 2)
                    if body is not None:
                        ok = crc16(b'\xa1\xa1\xa1' + dm + body) == 0
                        found[(c, h, r, n)].append((ok, body[:size], dm[0]))
                        p = bits.find(SYNC, dp + 64 + 16 * (size + 2))
                        continue
                    else:
                        break
            p = bits.find(SYNC, q + 16)
        else:
            p = bits.find(SYNC, q + 16)
    return last

def decode_track_flux(path, cyl, side):
    """Decode one KryoFlux stream file.  Returns dict with the per-sector results."""
    flux, idx, sck = read_kryoflux(path)
    cell = sck / (2 * MFM_RATE)              # MFM half-bit cell, 2 us = ~48.05 ticks
    found = collections.defaultdict(list)
    bits = bytearray()
    state = None
    # revolution boundaries: index pulses; add stream start/end
    bounds = [0] + [i for i in idx if 0 < i < len(flux)] + [len(flux)]
    bounds = sorted(set(bounds))
    scan_from = 0
    revs = 0
    for a, b in zip(bounds, bounds[1:]):
        if b - a < 1000:
            continue
        bits, state = flux_to_bits(flux, a, b, cell, state, bits)
        revs += 1
        scan_from = max(0, scan_sectors(bits, max(0, scan_from - 20000), found) - 20000)
        good = {k[2] for k, v in found.items() if k[0] == cyl and k[1] == side and any(g for g, _, _ in v)}
        if len(good) >= SPT and revs >= 2:
            break
    return summarize(found, cyl, side, revs=revs, nflux=len(flux))

def summarize(found, cyl, side, **extra):
    res = {'cyl': cyl, 'side': side, 'sectors': {}, 'foreign': [], **extra}
    for (c, h, r, n), copies in found.items():
        if c != cyl or h != side or n != 3 or not (1 <= r <= SPT):
            res['foreign'].append({'id': [c, h, r, n], 'copies': len(copies),
                                   'good': sum(1 for g, _, _ in copies if g)})
            continue
        goods = [d for g, d, _ in copies if g]
        distinct = {bytes(d) for d in goods}
        if goods:
            data, status = goods[0], 'good'
        else:
            # best-effort: the most common bad copy
            cnt = collections.Counter(bytes(d) for _, d, _ in copies)
            data, status = cnt.most_common(1)[0][0], 'bad'
        res['sectors'][r] = {'status': status, 'copies': len(copies), 'good': len(goods),
                             'distinct_good': len(distinct), 'deleted': any(m == 0xF8 for _, _, m in copies),
                             'data': bytes(data)}
    return res

# ---------------------------------------------------------------- HFE
def read_hfe(path):
    d = pathlib.Path(path).read_bytes()
    sig, rev, ntr, nsides, enc, bitrate, rpm, mode, _, tloff = struct.unpack_from('<8sBBBBHHBBH', d, 0)
    if sig != b'HXCPICFE':
        raise ValueError('not an HFE file')
    tracks = {}
    for t in range(ntr):
        off, ln = struct.unpack_from('<HH', d, tloff * 512 + t * 4)
        blob = d[off * 512: off * 512 + ln]
        sides = [bytearray(), bytearray()]
        for k in range(0, len(blob), 512):
            sides[0] += blob[k:k + 256]
            sides[1] += blob[k + 256:k + 512]
        for s in range(nsides):
            bits = bytearray()
            for byte in sides[s]:
                for i in range(8):            # LSB first
                    bits.append((byte >> i) & 1)
            tracks[(t, s)] = bits
    return tracks, {'tracks': ntr, 'sides': nsides, 'encoding': enc, 'bitrate_kbps': bitrate, 'mode': mode}

def decode_track_bits(bits, cyl, side):
    found = collections.defaultdict(list)
    # one revolution; wrap 24 kbit so a sector straddling the end is seen whole
    scan_sectors(bits + bits[:24000], 0, found)
    return summarize(found, cyl, side, revs=1)

# ---------------------------------------------------------------- disk assembly
STREAM_RE = re.compile(r'^(.*?)(\d{2})\.([01])\.raw$', re.I)

def stream_files(folder):
    files = {}
    for p in pathlib.Path(folder).iterdir():
        m = STREAM_RE.match(p.name)
        if m:
            files[(int(m.group(2)), int(m.group(3)))] = p
    return files

def _job(args):
    path, cyl, side = args
    try:
        return decode_track_flux(path, cyl, side)
    except Exception as e:           # keep going; report the track as failed
        return {'cyl': cyl, 'side': side, 'sectors': {}, 'foreign': [], 'error': repr(e)}

def decode_disk(src, jobs=None):
    """Return {(cyl, side): track result} for a stream folder or an .hfe file."""
    src = pathlib.Path(src)
    if src.is_file() and src.suffix.lower() == '.hfe':
        tracks, info = read_hfe(src)
        out = {k: decode_track_bits(b, k[0], k[1]) for k, b in tracks.items()}
        return out, info
    files = stream_files(src)
    if not files:
        raise SystemExit(f'{src}: no KryoFlux stream files')
    work = [(str(p), c, s) for (c, s), p in sorted(files.items())]
    out = {}
    with concurrent.futures.ProcessPoolExecutor(max_workers=jobs or os.cpu_count()) as ex:
        for r in ex.map(_job, work, chunksize=2):
            out[(r['cyl'], r['side'])] = r
    return out, {'stream_files': len(files)}

def assemble(tracks, ref=None):
    """Build the two side images.  Returns (s0, s1, report lines, stats)."""
    sides = [bytearray(SIDE_BYTES), bytearray(SIDE_BYTES)]
    lines, stats = [], collections.Counter()
    for c in range(CYLS):
        for h in range(SIDES):
            t = tracks.get((c, h))
            for r in range(1, SPT + 1):
                off = c * SPT * SECTOR + (r - 1) * SECTOR
                refdata = ref[h][off:off + SECTOR] if ref else None
                sec = t['sectors'].get(r) if t else None
                tag = f'cyl {c:2d} side {h} sector {r}'
                if sec is None:
                    if t is None:
                        stats['no track'] += 1
                        why = 'no stream file' if t is None else 'no copy decoded'
                    else:
                        why = 'no copy decoded' + (f" ({t['error']})" if t.get('error') else '')
                    stats['missing'] += 1
                    if refdata is not None:
                        sides[h][off:off + SECTOR] = refdata
                        stats['filled from reference'] += 1
                        lines.append(f'{tag}: MISSING, {why}; filled from reference image')
                    else:
                        lines.append(f'{tag}: MISSING, {why}; zero filled')
                    continue
                data = sec['data']
                if sec['status'] == 'good':
                    stats['good'] += 1
                    if sec['distinct_good'] > 1:
                        stats['good but inconsistent'] += 1
                        lines.append(f"{tag}: {sec['distinct_good']} different contents all with good CRC "
                                     f"({sec['good']} good of {sec['copies']} copies); first kept")
                    if refdata is not None and refdata != data:
                        stats['differs from reference'] += 1
                        nd = sum(1 for a, b in zip(refdata, data) if a != b)
                        lines.append(f"{tag}: good CRC ({sec['good']} of {sec['copies']} copies) but differs "
                                     f"from reference image in {nd} bytes -- flux copy kept")
                else:
                    stats['bad crc'] += 1
                    if refdata is not None:
                        nd = sum(1 for a, b in zip(refdata, data) if a != b)
                        if nd == 0:
                            lines.append(f"{tag}: BAD CRC in all {sec['copies']} copies, best copy equals reference image; kept")
                        else:
                            data = refdata
                            stats['filled from reference'] += 1
                            lines.append(f"{tag}: BAD CRC in all {sec['copies']} copies ({nd} bytes differ from "
                                         f"reference); filled from reference image")
                    else:
                        lines.append(f"{tag}: BAD CRC in all {sec['copies']} copies; best-effort copy kept")
                if sec['deleted']:
                    lines.append(f'{tag}: deleted data mark ($F8)')
                sides[h][off:off + SECTOR] = data
            if t and t.get('foreign'):
                for f in t['foreign']:
                    lines.append(f"cyl {c:2d} side {h}: unexpected sector id C={f['id'][0]} H={f['id'][1]} "
                                 f"R={f['id'][2]} N={f['id'][3]} ({f['good']} good of {f['copies']} copies)")
    extra = [k for k in tracks if k[0] >= CYLS]
    if extra:
        lines.append(f'{len(extra)} stream files beyond cylinder {CYLS-1} ignored: '
                     + ', '.join(f'{c}.{h}' for c, h in sorted(extra)))
    return sides[0], sides[1], lines, stats

def load_ref(s0, s1):
    a = pathlib.Path(s0).read_bytes()
    if s1:
        b = pathlib.Path(s1).read_bytes()
    else:
        a, b = a[:SIDE_BYTES], a[SIDE_BYTES:]
    if len(a) != SIDE_BYTES or len(b) != SIDE_BYTES:
        raise SystemExit('reference image is not 2 x 409600 bytes')
    return [a, b]

def run_one(src, outbase, ref=None, jobs=None, quiet=False):
    src, outbase = pathlib.Path(src), pathlib.Path(outbase)
    outbase.parent.mkdir(parents=True, exist_ok=True)
    tracks, info = decode_disk(src, jobs)
    refimg = load_ref(*ref) if ref else None
    s0, s1, lines, stats = assemble(tracks, refimg)
    (outbase.parent / (outbase.name + '_s0')).write_bytes(s0)
    (outbase.parent / (outbase.name + '_s1')).write_bytes(s1)
    total = CYLS * SIDES * SPT
    def show(p):                      # paths relative to the project root where possible
        try:
            return os.path.relpath(pathlib.Path(p).resolve(), pathlib.Path(__file__).resolve().parent.parent)
        except ValueError:
            return str(p)
    head = [f'# {outbase.name}: decoded from {show(src)}',
            f'# {info}',
            f"# sectors: {total}; good CRC from flux: {stats['good']}; bad CRC: {stats['bad crc']}; "
            f"missing: {stats['missing']}; filled from reference: {stats['filled from reference']}; "
            f"good-CRC sectors differing from reference: {stats['differs from reference']}; "
            f"inconsistent good copies: {stats['good but inconsistent']}",
            f"# reference: {show(ref[0]) if ref else 'none'}"]
    revs = [t.get('revs', 0) for t in tracks.values()]
    if revs:
        head.append(f'# revolutions decoded per track: min {min(revs)} max {max(revs)}')
    rep = '\n'.join(head + lines) + '\n'
    (outbase.parent / (outbase.name + '.report.txt')).write_text(rep)
    if not quiet:
        print('\n'.join(head))
        for l in lines[:60]:
            print(' ', l)
        if len(lines) > 60:
            print(f'  ... {len(lines) - 60} more lines in the report')
    return dict(stats), lines

# ---------------------------------------------------------------- --all driver
def find_reference(folder, name):
    """The DTC-made sector image that sits beside a stream folder, if any."""
    cands = []
    for d in (folder, folder.parent):
        for p in d.iterdir():
            if p.is_file() and re.search(r'[-_]s0(\.raw|\.img)?$', p.name, re.I) and p.stat().st_size == SIDE_BYTES:
                s1 = p.with_name(re.sub(r'([-_])s0', r'\1s1', p.name, flags=re.I))
                if s1.exists() and (d == folder or p.name.lower().startswith(name.lower())):
                    cands.append((p, s1))
    return cands[0] if cands else None

def already_imaged(folder, name):
    """True when render_all.py already catalogues this folder: a <stem>_s0[.img] pair of any size in
    the folder, a lone 819200-byte .img, or (as for cmm/cmm3) a <name>_s0 pair in the parent folder."""
    for p in folder.iterdir():
        if p.is_file() and (re.search(r'_s0(\.img)?$', p.name, re.I) or
                            (p.suffix.lower() == '.img' and p.stat().st_size == 2 * SIDE_BYTES)):
            return True
    return any(p.is_file() and re.match(re.escape(name) + r'_s0(\.img)?$', p.name, re.I)
               for p in folder.parent.iterdir())

def run_all(images_root, out_root, jobs=None, include_imaged=False):
    images_root, out_root = pathlib.Path(images_root), pathlib.Path(out_root)
    summary = []
    folders = sorted({p.parent for p in images_root.rglob('*.raw') if STREAM_RE.match(p.name)})
    if not include_imaged:
        folders = [f for f in folders if not already_imaged(f, f.name)]
    hfes = sorted(p for p in images_root.rglob('*') if p.suffix.lower() == '.hfe'
                  and not any(q.is_file() and re.search(r'[-_]s0', q.name) and q.stat().st_size == SIDE_BYTES
                              for q in p.parent.iterdir()))
    for folder in folders:
        rel = folder.relative_to(images_root)
        name = folder.name
        outbase = out_root / rel / name
        ref = find_reference(folder, name)
        print(f'== {rel}  ref={ref[0].name if ref else None}', flush=True)
        stats, lines = run_one(folder, outbase, ref, jobs, quiet=True)
        summary.append({'disk': str(rel), 'name': name, 'source': 'kryoflux', 'reference': str(ref[0]) if ref else None,
                        'stats': stats, 'issues': len(lines)})
        print('  ', stats, flush=True)
    for hfe in hfes:
        rel = hfe.parent.relative_to(images_root)
        name = hfe.stem.lower()
        outbase = out_root / rel / name
        print(f'== {rel}/{hfe.name}', flush=True)
        stats, lines = run_one(hfe, outbase, None, jobs, quiet=True)
        summary.append({'disk': str(rel), 'name': name, 'source': 'hfe', 'reference': None,
                        'stats': stats, 'issues': len(lines)})
        print('  ', stats, flush=True)
    (out_root / 'decode-summary.json').write_text(json.dumps(summary, indent=1))
    return summary

def main():
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument('src', nargs='?', help='KryoFlux stream folder or .hfe file')
    ap.add_argument('out', nargs='?', help='output base path; _s0/_s1/.report.txt are appended')
    ap.add_argument('--ref', nargs='+', metavar='IMG', help='reference sector image (_s0 _s1, or one 819200-byte img)')
    ap.add_argument('--jobs', type=int)
    ap.add_argument('--all', action='store_true', help='decode every stream folder / lone .hfe under --images')
    ap.add_argument('--include-imaged', action='store_true',
                    help='with --all: also decode stream folders that already hold a <stem>_s0 image render_all.py sees')
    ap.add_argument('--images', dest='images_root', default=str(pathlib.Path(__file__).parent / '../disk-images'))
    ap.add_argument('--out', dest='out_root', default=str(pathlib.Path(__file__).parent / '../decoded-images'))
    a = ap.parse_args()
    if a.all:
        run_all(a.images_root, a.out_root, a.jobs, a.include_imaged)
    elif a.src and a.out:
        ref = None
        if a.ref:
            ref = (a.ref[0], a.ref[1] if len(a.ref) > 1 else None)
        run_one(a.src, a.out, ref, a.jobs)
    else:
        ap.print_help()

if __name__ == '__main__':
    main()
