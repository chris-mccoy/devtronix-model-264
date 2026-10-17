#!/usr/bin/env python3
"""Render a Devtronix Model 264 Track/Song file to a standard MIDI file.

usage:
  dev2midi.py SIDE0 [SIDE1] -t T8 [-d D1] [-o out.mid] [--tempo 120] [--ranks]

Two renderings:

  keyboards (default): one MIDI channel per keyboard of the definition; every
      key press becomes the note at the key's own pitch (key 25 = 8' C = MIDI
      36).  Stop and swell changes go into track 0 as marker/text events, so
      the registration can be read but is not heard.  Simple and faithful to
      what the organist played.

  --ranks: play the recording through the definition the way the relay does:
      a stop is on -> its links' expressions are evaluated -> the "Normal rank
      output" functions of true links sound, for every key of their division
      (plus keys coupled in by active divisional couplers), at key + pitch
      offset, on the pipes the rank actually has.  One MIDI track per rank.
      This is what the organ sounded like (16' stops an octave down, octave
      couplers, unison off, ...) minus traps, tremulants and expression.

The pulse clock is 96 per beat, which is used directly as the MIDI division;
the tempo is not stored in a track (default 120 BPM, see README.md).
"""
import argparse, os, struct, sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from devfs import Disk, iter_events  # noqa: E402
from devdef import Definition, midi_note, note_name, NOTES  # noqa: E402

PPQ = 96
GM_CHURCH_ORGAN = 19
CHANNELS = [c for c in range(16) if c != 9]     # 9 is GM percussion

# A few General MIDI programs for rank names, so a tuned-percussion rank does
# not play as an organ.  Everything else is Church Organ.
PROGRAM_HINTS = [("piano", 0), ("chrysoglott", 11), ("chrys", 11), ("vibraharp", 11),
                 ("marimba", 12), ("xylo", 13), ("chime", 14), ("glock", 9), ("harp", 46),
                 ("celesta", 8), ("bell", 14), ("vox", 52), ("string", 48), ("viol", 48)]

def program_for(name):
    n = name.lower()
    for key, prog in PROGRAM_HINTS:
        if key in n:
            return prog
    return GM_CHURCH_ORGAN

# ----------------------------------------------------------------------------- SMF writer
def vlq(n):
    out = [n & 0x7F]
    n >>= 7
    while n:
        out.append(0x80 | (n & 0x7F)); n >>= 7
    return bytes(reversed(out))

class Track:
    def __init__(self, name=None):
        self.events = []            # (time, order, bytes)
        self.n = 0
        if name:
            self.meta(0, 0x03, name.encode("latin-1", "replace"))

    def add(self, t, data):
        self.events.append((t, self.n, bytes(data))); self.n += 1

    def meta(self, t, kind, payload):
        self.add(t, bytes([0xFF, kind]) + vlq(len(payload)) + payload)

    def text(self, t, s, kind=0x01):
        self.meta(t, kind, s.encode("latin-1", "replace"))

    def chunk(self, end_time):
        self.events.sort()
        out, last = bytearray(), 0
        for t, _, data in self.events:
            out += vlq(t - last) + data; last = t
        out += vlq(max(end_time, last) - last) + b"\xff\x2f\x00"
        return b"MTrk" + struct.pack(">I", len(out)) + bytes(out)

def write_midi(path, tracks, end_time):
    data = b"MThd" + struct.pack(">IHHH", 6, 1, len(tracks), PPQ)
    for tr in tracks:
        data += tr.chunk(end_time)
    with open(path, "wb") as f:
        f.write(data)

class NoteSink:
    """Note on/off with a use count per (channel, note), so two ranks (or two
    keyboards) sharing a channel do not cut each other off.  The note-off goes
    to the track that carried the note-on."""
    def __init__(self, velocity):
        self.count = {}             # (channel, note) -> [count, track]
        self.velocity = velocity

    def on(self, track, t, chan, note):
        k = (chan, note)
        e = self.count.setdefault(k, [0, track])
        e[0] += 1
        if e[0] == 1 and 0 <= note < 128:
            e[1] = track
            track.add(t, [0x90 | chan, note, self.velocity])

    def off(self, track, t, chan, note):
        k = (chan, note)
        e = self.count.get(k)
        if not e or e[0] <= 0:
            return
        e[0] -= 1
        if e[0] == 0 and 0 <= note < 128:
            e[1].add(t, [0x80 | chan, note, 0])

    def all_off(self, t):
        for (chan, note), e in self.count.items():
            if e[0] > 0 and 0 <= note < 128:
                e[1].add(t, [0x80 | chan, note, 0])
            e[0] = 0

# ----------------------------------------------------------------------------- organ model
class Organ:
    """Enough of the relay logic to turn keys and stops into sounding pipes."""
    def __init__(self, d):
        self.d = d
        self.stops_on = set()
        self.keys = {}                      # keyboard -> set of key numbers
        self.links = d.lists.get("Lnk", [])
        self.fncs = {f.number: f for f in d.lists.get("Fnc", [])}
        self.active = set()                 # function numbers of true links
        self.by_stop = {}
        for l in self.links:
            for s in d.link_stops(l):
                self.by_stop.setdefault(s, []).append(l)
        self.rank_pipes = {r.number: set(d.rank_notes(r)) for r in d.lists.get("Rnk", [])}

    def eval_link(self, lnk):
        stack = []
        for i in range(15):
            v = lnk.w(2 * i)
            if v == 0:
                break
            if v & 0x8000:
                op = v & 0xFF
                try:
                    if op == 1:
                        stack.append(not stack.pop())
                    elif op == 2:
                        b, a = stack.pop(), stack.pop(); stack.append(a and b)
                    else:
                        b, a = stack.pop(), stack.pop(); stack.append(a or b)
                except IndexError:
                    stack.append(False)
            elif v & 0x4000:
                stack.append(False)         # control buttons: not recorded
            else:
                stack.append(v in self.stops_on)
        return bool(stack and stack[-1])

    def set_stop(self, n, on):
        if on:
            self.stops_on.add(n)
        else:
            self.stops_on.discard(n)
        self.active = set()
        for l in self.links:
            if self.eval_link(l):
                self.active.update(self.d.link_functions(l))

    def set_key(self, kbd, key, on):
        s = self.keys.setdefault(kbd, set())
        if on:
            s.add(key)
        else:
            s.discard(key)

    def rank_functions(self):
        """Active functions that sound a rank, following modifiers and multipliers."""
        out, seen = [], set()
        todo = list(self.active)
        while todo:
            n = todo.pop()
            if n in seen:
                continue
            seen.add(n)
            f = self.fncs.get(n)
            if f is None:
                continue
            t = f.type
            if t == 3:
                out.append(f)
            elif t in (13, 14):                      # pizzicato / reiterate modifier
                todo.append(f.w(2))
            elif t == 12:                            # function multiplier
                todo.extend(v for v in f.words(2, 8) if v)
        return out

    def division_keys(self, kbd, depth=0):
        """Keys sounding on a division: its own keys unless unison off, plus
        keys coupled in from other keyboards by active divisional couplers."""
        keys = set()
        unison_off = any(self.fncs[n].type == 6 and self.fncs[n].w(2) == kbd
                         for n in self.active if n in self.fncs)
        if not unison_off:
            keys |= self.keys.get(kbd, set())
        if depth > 4:
            return keys
        for n in self.active:
            f = self.fncs.get(n)
            if f is None or f.type != 1 or f.w(4) != kbd:
                continue
            src, off = f.w(2), f.s(6)
            lo, hi = f.w(8) or 1, f.w(10) or NOTES
            if f.b(12):                              # couple the couplers
                src_keys = self.division_keys(src, depth + 1)
            else:
                src_keys = self.keys.get(src, set())
            for k in src_keys:
                n2 = k + off
                if lo <= n2 <= hi:
                    keys.add(n2)
        return keys

    def sounding(self):
        """Set of (rank, note) currently sounding."""
        out = set()
        cache = {}
        for f in self.rank_functions():
            kbd, rank, off = f.w(2), f.w(4), f.s(6)
            lo, hi = f.w(8) or 1, f.w(10) or NOTES
            if kbd not in cache:
                cache[kbd] = self.division_keys(kbd)
            pipes = self.rank_pipes.get(rank, set())
            for k in cache[kbd]:
                n = k + off
                if lo <= n <= hi and n in pipes:
                    out.add((rank, n))
        return out

# ----------------------------------------------------------------------------- rendering
def stop_label(d, n):
    s = d.get("Stp", n)
    if s is None:
        return f"stop {n}"
    if s.name:
        return f"{s.name} (stop {n})"
    for l in d.links_of_stop(n):
        if l.name:
            return f"{l.name} (stop {n})"
        for fn in d.link_functions(l):
            f = d.get("Fnc", fn)
            if f and f.name:
                return f"{f.name} (stop {n})"
    return f"stop {n}"

def render(data, d, tempo, velocity, ranks, verbose=False):
    meta = Track("Devtronix track")
    meta.meta(0, 0x51, struct.pack(">I", int(60e6 / tempo))[1:])
    meta.meta(0, 0x58, bytes([4, 2, 24, 8]))
    sink = NoteSink(velocity)
    tracks = [meta]
    kbd_tracks, rank_tracks = {}, {}
    organ = Organ(d) if ranks else None
    sounding = set()
    last_t = 0
    keyboards = {k.number: k for k in d.lists.get("Kbd", [])}
    chan_names = {c.number: c.name for c in d.lists.get("Chn", [])}
    stats = {"keys": 0, "stops": 0, "notes": 0, "unknown_kbd": set()}

    def kbd_track(n):
        if n not in kbd_tracks:
            chan = CHANNELS[(n - 1) % len(CHANNELS)]
            name = keyboards[n].name if n in keyboards else f"keyboard {n}"
            tr = Track(f"Kbd {n} {name}")
            tr.add(0, [0xC0 | chan, GM_CHURCH_ORGAN])
            kbd_tracks[n] = (tr, chan); tracks.append(tr)
        return kbd_tracks[n]

    def rank_track(n):
        if n not in rank_tracks:
            chan = CHANNELS[(len(rank_tracks)) % len(CHANNELS)]
            r = d.get("Rnk", n)
            name = r.name if r else f"rank {n}"
            tr = Track(f"Rnk {n} {name}")
            tr.add(0, [0xC0 | chan, program_for(name)])
            rank_tracks[n] = (tr, chan); tracks.append(tr)
        return rank_tracks[n]

    def update_sounding(t):
        nonlocal sounding
        now = organ.sounding()
        for rank, n in sorted(sounding - now):
            tr, chan = rank_track(rank)
            sink.off(tr, t, chan, midi_note(n))
        for rank, n in sorted(now - sounding):
            tr, chan = rank_track(rank)
            sink.on(tr, t, chan, midi_note(n)); stats["notes"] += 1
        sounding = now

    pending = False
    for off, t, kind, info in iter_events(data):
        if ranks and pending and t != last_t:
            update_sounding(last_t); pending = False
        last_t = t
        if kind == "key":
            kbd, key, on = info
            stats["keys"] += 1
            if kbd not in keyboards:
                stats["unknown_kbd"].add(kbd)
            if ranks:
                organ.set_key(kbd, key, on); pending = True
            else:
                tr, chan = kbd_track(kbd)
                (sink.on if on else sink.off)(tr, t, chan, midi_note(key))
                if on:
                    stats["notes"] += 1
        elif kind == "stop":
            n, on = info
            stats["stops"] += 1
            meta.text(t, f"{'+' if on else '-'} {stop_label(d, n)}", 0x06)
            if ranks:
                organ.set_stop(n, on); pending = True
        elif kind == "sync":
            stops_on, values, cnt, unknown = info
            if stops_on:
                meta.text(t, "sync: on " + ", ".join(stop_label(d, s) for s in stops_on), 0x06)
            if ranks:
                for s in stops_on:
                    organ.set_stop(s, True)
                pending = True
        elif kind == "channel":
            c, v = info
            meta.text(t, f"Chn {c} {chan_names.get(c, '')} = {v}".replace("  ", " "))
        elif kind == "midi":
            meta.text(t, "midi " + info.hex(" "))
        elif kind == "end":
            break
    if ranks and pending:
        update_sounding(last_t)
    sink.all_off(last_t)                      # a track cut short
    # a rank that only ever doubled another rank on the same channel has no notes
    tracks = [tr for i, tr in enumerate(tracks)
              if i == 0 or any(e[2][0] & 0xF0 in (0x80, 0x90) for e in tr.events)]
    return tracks, last_t, stats

def main():
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("side0"); ap.add_argument("side1", nargs="?")
    ap.add_argument("-t", "--track", required=True, help="track slot, e.g. T8")
    ap.add_argument("-d", "--definition", default="D1", help="definition slot (default D1)")
    ap.add_argument("--def-file", help="use an extracted definition file instead of a slot")
    ap.add_argument("-o", "--out", help="output .mid (default: <disk>-<slot>.mid)")
    ap.add_argument("--tempo", type=float, default=120.0, help="BPM (default 120)")
    ap.add_argument("--velocity", type=int, default=80)
    ap.add_argument("--ranks", action="store_true", help="render through stops and ranks")
    a = ap.parse_args()

    disk = Disk(a.side0, a.side1)
    e = disk.find(a.track)
    if e.letter != "T":
        raise SystemExit(f"{e.slot} is a {e.type} file, not a track")
    if a.def_file:
        d = Definition(open(a.def_file, "rb").read()); dname = a.def_file
    else:
        de = disk.find(a.definition)
        if de.letter != "D":
            raise SystemExit(f"{de.slot} is a {de.type} file, not a definition")
        d = Definition(de.read()); dname = f"{de.slot} {de.name!r}"
    tracks, end, stats = render(e.read(), d, a.tempo, a.velocity, a.ranks)
    out = a.out or f"{os.path.basename(a.side0).split('_s')[0].split('.')[0]}-{e.slot}.mid"
    write_midi(out, tracks, end + PPQ)
    secs = end * 60 / (PPQ * a.tempo)
    print(f"{e.slot} {e.name!r} with {dname}: {stats['keys']} key events, {stats['stops']} stop changes, "
          f"{stats['notes']} notes on {len(tracks) - 1} tracks, {secs:.1f} s at {a.tempo:g} BPM"
          f"{' (' + ('ranks' if a.ranks else 'keyboards') + ')'} -> {out}")
    if stats["unknown_kbd"]:
        print(f"  note: keyboards {sorted(stats['unknown_kbd'])} are not in the definition")

if __name__ == "__main__":
    main()
