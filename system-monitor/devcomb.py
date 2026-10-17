#!/usr/bin/env python3
"""Devtronix Model 264 combination (C) file decoder.

Format, from save_c_file ($559C) / load_c_file ($5528) and the piston code at
$B68A in System Monitor 2.6 (183); see README.md "Combination files (C)".

    word  pistons        = number of Pst items in the definition when saved
    word  stops          = number of Stp items
    word  hb             = (stops + 8) // 8  bytes per bitmap
    pistons times:
        hb bytes  OFF bitmap   bit (n-1)&7 of byte (n-1)>>3 = stop n is turned off
        hb bytes  ON  bitmap   same layout = stop n is turned on

Row i is piston Pst i.  A stop in neither bitmap is left alone, so OFF|ON is
the piston's *range* (the stops it captures).  All words little-endian.

usage:
  devcomb.py SIDE0 [SIDE1] -c C1 [-d D1]        decode a combination file
  devcomb.py --file c.bin [--def-file d.bin]    from extracted files
  options: --piston N (one piston, full stop list), --all (full stop lists for
           every piston), --raw (hex rows)
"""
import argparse, collections, os, re, struct, sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from devfs import Disk          # noqa: E402
from devdef import Definition   # noqa: E402

FOOTAGE = re.compile(r"^\s*(\d+(?:-\d+/\d+)?'|[IVX]+\s*(?:R|Rk|Rank)?\.?)\s+", re.I)

class Combination:
    def __init__(self, data):
        if len(data) < 6:
            raise ValueError(f"not a combination file ({len(data)} bytes)")
        self.pistons, self.stops, self.hb = struct.unpack_from("<HHH", data, 0)
        if self.hb != (self.stops + 8) // 8 or 6 + self.pistons * 2 * self.hb != len(data):
            raise ValueError(f"not a combination file (header {self.pistons},{self.stops},{self.hb}"
                             f" does not fit {len(data)} bytes)")
        self.rows = []
        off = 6
        for _ in range(self.pistons):
            off_map = data[off:off + self.hb]; on_map = data[off + self.hb:off + 2 * self.hb]
            off += 2 * self.hb
            self.rows.append((self._bits(off_map), self._bits(on_map)))

    def _bits(self, m):
        return [n for n in range(1, self.stops + 1) if m[(n - 1) >> 3] >> ((n - 1) & 7) & 1]

    def piston(self, i):
        """(off_stops, on_stops) of piston i (1-based)."""
        return self.rows[i - 1]

# ----------------------------------------------------------------------------- naming
def stop_label(d, n):
    """Stop name, or the editor's 'computer generated' one from its links/functions."""
    st = d.get("Stp", n)
    if st is None:
        return f"Stp {n}?"
    if st.name:
        return st.name
    for lnk in d.links_of_stop(n):
        if lnk.name:
            return lnk.name
        for f in d.link_functions(lnk):
            fn = d.get("Fnc", f)
            if fn is not None and fn.name:
                return fn.name
    return f"Stp {n}"

def division_of(label):
    """First word after the footage, e.g. "8' Solo Tibia" -> "Solo"."""
    s = FOOTAGE.sub("", label).strip()
    return s.split()[0].rstrip(".,:") if s else "?"

def classify(comb, d, i):
    off, on = comb.piston(i)
    rng = len(off) + len(on)
    if rng == 0:
        return "unprogrammed", ""
    big = rng >= 0.5 * comb.stops          # generals cover most of the organ
    if not on and big:
        return "cancel", ""
    if not off and big:
        return "all on", ""
    divs = ""
    if d is not None:
        c = collections.Counter(division_of(stop_label(d, n)) for n in off + on)
        top = c.most_common(3)
        divs = ", ".join(f"{k} {v}" for k, v in top)
    kind = "general" if big else "divisional"
    return kind, divs

# ----------------------------------------------------------------------------- output
def piston_address(d, i):
    if d is None:
        return ""
    p = d.get("Pst", i)
    if p is None:
        return "(no Pst item)"
    from devdef import io_address
    return io_address(p.w(0))

def print_combination(comb, d, what, args):
    print(f"{what}: {comb.pistons} pistons, {comb.stops} stops, {comb.hb} bytes per bitmap")
    if d is not None:
        ns, npst = len(d.lists.get("Stp", [])), len(d.lists.get("Pst", []))
        note = []
        if ns != comb.stops:
            note.append(f"definition has {ns} stops")
        if npst != comb.pistons:
            note.append(f"definition has {npst} pistons")
        print("  definition:", "matches" if not note else "MISMATCH: " + "; ".join(note),
              "(names below may be off)" if note else "")
    which = [args.piston] if args.piston else range(1, comb.pistons + 1)
    for i in which:
        off, on = comb.piston(i)
        kind, divs = classify(comb, d, i)
        addr = piston_address(d, i)
        line = f"  Pst {i:3d} {addr:7s} {kind:13s} range {len(off)+len(on):3d}  on {len(on):3d}"
        if divs:
            line += f"   [{divs}]"
        print(line)
        if args.raw:
            print("        off:", off); print("        on: ", on)
        if (args.all or args.piston) and on:
            for n in on:
                print(f"        on  {n:4d}  {stop_label(d, n) if d else ''}")
            if args.piston and off and len(off) <= 60:
                print("        off:", ", ".join(str(n) for n in off))

def main():
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("side0", nargs="?"); ap.add_argument("side1", nargs="?")
    ap.add_argument("-c", default="C1", help="combination slot (default C1)")
    ap.add_argument("-d", default=None, help="definition slot for stop names (default D1 if present)")
    ap.add_argument("--file", help="extracted combination file")
    ap.add_argument("--def-file", help="extracted definition file")
    ap.add_argument("--piston", type=int, help="show one piston in full")
    ap.add_argument("--all", action="store_true", help="list the ON stops of every piston")
    ap.add_argument("--raw", action="store_true", help="print the stop numbers of both bitmaps")
    a = ap.parse_args()
    d = None
    try:
        if a.file:
            comb = Combination(open(a.file, "rb").read()); what = a.file
            if a.def_file:
                d = Definition(open(a.def_file, "rb").read())
        else:
            if not a.side0:
                ap.error("give a disk image or --file")
            disk = Disk(a.side0, a.side1)
            e = disk.find(a.c)
            if e.letter != "C":
                raise SystemExit(f"{e.slot} is a {e.type} file, not a combination")
            comb = Combination(e.read()); what = f"{disk.label!r} {e.slot} {e.name!r}"
            dslot = a.d or ("D1" if any(x.slot == "D1" for x in disk.directory()) else None)
            if dslot:
                de = disk.find(dslot)
                d = Definition(de.read()); what += f" with {de.slot} {de.name!r}"
    except (ValueError, KeyError, IOError, struct.error) as err:
        raise SystemExit(f"error: {err}")
    print_combination(comb, d, what, a)

if __name__ == "__main__":
    main()
