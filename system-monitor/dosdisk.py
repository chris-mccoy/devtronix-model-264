#!/usr/bin/env python3
"""
dosdisk.py -- extract the files from an MS-DOS (FAT12) floppy image.

Two of the floppies in the collection are not Devtronix disks but 720 KB MS-DOS
disks written by a Yamaha Disklavier (boot sector OEM name "YAMAHA", "DRC
Ver1.60 Copyright(C) 1989 by YAMAHA"): new-images/fenelon-tarantelle and
new-images/midi-piano-selections.  DTC imaged them per side like the others,
as <name>_s0 / <name>_s1 of 368640 bytes each (80 cylinders x 9 sectors x 512
bytes).  This tool interleaves the two sides into an ordinary 737280-byte
image (cylinder c side h at offset (c*2+h)*4608), which any PC, mtools or an
HxC/Gotek will mount, and copies every file out of it.

usage:
  dosdisk.py SIDE0 SIDE1 OUTDIR [--img OUT.img]
  dosdisk.py IMAGE.img OUTDIR

Files are written under OUTDIR with their 8.3 names (subdirectories become
folders); a file's DOS date, when it has a valid one, becomes its mtime.  The
directory listing is printed, and the tool stops if the two FAT copies differ,
a cluster chain is broken, or two files share a cluster.
"""
import argparse, datetime, os, pathlib, struct, sys

SECTOR, SPT, CYLS = 512, 9, 80
SIDE_BYTES = SECTOR * SPT * CYLS            # 368640
TRACK = SECTOR * SPT                        # 4608

def interleave(s0, s1):
    if len(s0) != SIDE_BYTES or len(s1) != SIDE_BYTES:
        raise SystemExit(f'side images must be {SIDE_BYTES} bytes')
    return b''.join(s[c * TRACK:(c + 1) * TRACK] for c in range(CYLS) for s in (s0, s1))

class Fat12:
    def __init__(self, img):
        self.d = img
        (self.bps, self.spc, self.res, self.nfat, self.nroot, total, self.media, self.spf,
         self.spt, self.heads) = struct.unpack_from('<HBHBHHBHHH', img, 11)
        if img[510:512] != b'\x55\xaa' or self.bps != SECTOR:
            raise SystemExit('not an MS-DOS boot sector')
        self.oem = img[3:11].decode('latin1').rstrip()
        fats = [img[(self.res + i * self.spf) * self.bps:(self.res + (i + 1) * self.spf) * self.bps]
                for i in range(self.nfat)]
        if any(f != fats[0] for f in fats):
            raise SystemExit('the FAT copies differ')
        self.fat = fats[0]
        self.root = (self.res + self.nfat * self.spf) * self.bps
        self.data = self.root + self.nroot * 32
        self.csize = self.spc * self.bps
        self.nclus = (total * self.bps - self.data) // self.csize
        self.owner = {}

    def next(self, c):
        v = self.fat[c * 3 // 2] | self.fat[c * 3 // 2 + 1] << 8
        return v >> 4 if c & 1 else v & 0xFFF

    def chain(self, first, who):
        out, c = [], first
        while 2 <= c < 0xFF0:
            if c >= self.nclus + 2 or c in self.owner:
                raise SystemExit(f'{who}: cluster {c} out of range or already used by {self.owner.get(c)}')
            self.owner[c] = who
            out.append(c)
            c = self.next(c)
        if out and c < 0xFF8:
            raise SystemExit(f'{who}: chain ends in {c:#x}')
        return out

    def read(self, first, who, size=None):
        b = b''.join(self.d[self.data + (c - 2) * self.csize:self.data + (c - 1) * self.csize]
                     for c in self.chain(first, who))
        if size is not None and len(b) < size:
            raise SystemExit(f'{who}: {size} bytes but only {len(b)} allocated')
        return b if size is None else b[:size]

    def entries(self, raw, path=''):
        """Yield (path, attr, datetime or None, size, data) for every file, depth first."""
        for i in range(0, len(raw), 32):
            e = raw[i:i + 32]
            if e[0] == 0:
                break
            if e[0] in (0xE5, 0x2E) or e[11] & 0x08:          # deleted, . / .., volume label or LFN
                continue
            base, ext = e[0:8].decode('latin1').rstrip(), e[8:11].decode('latin1').rstrip()
            name = path + base + ('.' + ext if ext else '')
            attr = e[11]
            t, dt, first, size = struct.unpack_from('<HHHI', e, 22)
            try:
                when = datetime.datetime(1980 + (dt >> 9), dt >> 5 & 15, dt & 31,
                                         t >> 11, t >> 5 & 63, (t & 31) * 2)
            except ValueError:
                when = None
            if attr & 0x10:
                yield name + '/', attr, when, 0, None
                yield from self.entries(self.read(first, name), name + '/')
            else:
                yield name, attr, when, size, self.read(first, name, size) if size else b''

def main():
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument('paths', nargs='+', metavar='PATH', help='SIDE0 SIDE1 OUTDIR, or IMAGE.img OUTDIR')
    ap.add_argument('--img', help='also write the interleaved 737280-byte image here')
    a = ap.parse_args()
    if len(a.paths) == 3:
        img = interleave(pathlib.Path(a.paths[0]).read_bytes(), pathlib.Path(a.paths[1]).read_bytes())
    elif len(a.paths) == 2:
        img = pathlib.Path(a.paths[0]).read_bytes()
    else:
        ap.error('give SIDE0 SIDE1 OUTDIR or IMAGE.img OUTDIR')
    out = pathlib.Path(a.paths[-1])
    fs = Fat12(img)
    files = list(fs.entries(img[fs.root:fs.data]))
    if a.img:
        pathlib.Path(a.img).write_bytes(img)
    out.mkdir(parents=True, exist_ok=True)
    print(f'OEM {fs.oem!r}, media {fs.media:#04x}, {fs.nclus} clusters of {fs.csize} bytes, '
          f'{len(fs.owner)} in use, {sum(1 for c in range(2, fs.nclus + 2) if fs.next(c) == 0)} free')
    for name, attr, when, size, data in files:
        stamp = when.strftime('%Y-%m-%d %H:%M') if when else '(no date)       '
        print(f'  {name:16} {size:8}  {stamp}  attr {attr:02x}')
        p = out / name
        if data is None:
            p.mkdir(exist_ok=True)
            continue
        p.write_bytes(data)
        if when:
            os.utime(p, (when.timestamp(), when.timestamp()))
    lost = [c for c in range(2, fs.nclus + 2) if fs.next(c) not in (0, 0xFF7) and c not in fs.owner]
    if lost:
        print(f'  {len(lost)} allocated clusters belong to no file (first {lost[0]})')
    print(f'{sum(1 for f in files if f[4] is not None)} files -> {out}')

if __name__ == '__main__':
    main()
