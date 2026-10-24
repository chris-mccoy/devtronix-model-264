#!/usr/bin/env python3
"""Render a Devtronix Model 264 Track/Song file to a standard MIDI file.

usage:
  dev2midi.py SIDE0 [SIDE1] -t T8 [-d D1] [-o out.mid] [--tempo 120] [--ranks | --paramount | --friesach]

Four renderings:

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

  --paramount: a file for Hauptwerk's MIDI player with the Paramount 332
      loaded.  The keys play the Paramount's manuals and the registration is
      sent as the Paramount's own stop, tremulant and swell messages, so
      Hauptwerk's relay does the rest.  The Devtronix relay logic decides
      which ranks sound at which pitch on each manual (couplers included);
      paramount332.py maps those onto Paramount stop tabs and reports what it
      had to substitute or leave out (-v lists it).

  --friesach: the same for Hauptwerk's Friesach, a classical organ
      (friesach.py), with the ranks played on its stops of the nearest
      family.  The 58 Note Player plays the Hauptwerk and its lowest held key
      also plays the Pedal while it is in the bottom two octaves.

The pulse clock is 96 per beat, which is used directly as the MIDI division;
the tempo is not stored in a track (default 120 BPM, see README.md).
"""
import argparse, heapq, re, os, struct, sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from devfs import Disk, iter_events  # noqa: E402
from devdef import Definition, midi_note, note_name, NOTES, io_address  # noqa: E402

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
    """Enough of the relay logic to turn keys, stops and channel values into
    sounding pipes, struck traps, running tremulants and shade positions."""
    CHAMBERS = ("main", "solo", "echo", "great", "swell", "choir", "accomp", "pedal",
                "orchestral", "percussion", "brass", "foundation", "ethereal")

    def __init__(self, d):
        self.d = d
        self.stops_on = set()
        self.keys = {}                      # keyboard -> set of key numbers
        self.chan = {}                      # channel -> value 0..255
        self.links = d.lists.get("Lnk", [])
        self.fncs = {f.number: f for f in d.lists.get("Fnc", [])}
        self.units = {u.number: u for u in d.lists.get("Unt", [])}
        self.cots = [(c.w(0), c.w(2), c.w(4)) for c in d.lists.get("Cot", []) if c.w(0) and c.w(2)]
        self.active = set()                 # function numbers of true links
        self.by_stop = {}
        for l in self.links:
            for s in d.link_stops(l):
                self.by_stop.setdefault(s, []).append(l)
        self.rank_pipes = {r.number: set(d.rank_notes(r)) for r in d.lists.get("Rnk", [])}
        self.piz = {p.number: p.words(0, 122) for p in d.lists.get("Piz", [])}
        self.rit = {r.number: r.words(0, 122) for r in d.lists.get("Rit", [])}
        self._chambers()

    # -- chambers, tremulants, shades (by name; board letters fill the gaps)
    @staticmethod
    def tokens(name):
        return [t for t in re.split(r"[^a-z0-9]+", name.lower()) if t]

    def chamber_of(self, name):
        for t in self.tokens(name):
            if t in self.CHAMBERS:
                return t
        return None

    def _chambers(self):
        d = self.d
        self.rank_chamber = {}
        letter_votes = {}
        for r in d.lists.get("Rnk", []):
            ch = self.chamber_of(r.name)
            letters = {io_address(r.w(2 * n))[0] for n in range(1, 122) if r.w(2 * n) and r.w(2 * n) < 0x6001}
            if ch:
                self.rank_chamber[r.number] = ch
                for L in letters:
                    letter_votes.setdefault(L, {}).setdefault(ch, 0)
                    letter_votes[L][ch] += 1
            else:
                self.rank_chamber[r.number] = letters
        for n, v in list(self.rank_chamber.items()):
            if isinstance(v, set):
                best = {}
                for L in v:
                    for ch, c in letter_votes.get(L, {}).items():
                        best[ch] = best.get(ch, 0) + c
                self.rank_chamber[n] = max(best, key=best.get) if best else None
        rank_tokens = {r.number: set(self.tokens(r.name)) for r in d.lists.get("Rnk", [])}
        skip = set(self.CHAMBERS) | {"trem", "tremolo", "tremulant", "tremulants", "shade", "shades", "shutter", "shutters"}
        # tremulants: unit -> set of ranks
        self.trem_ranks, specific_claimed = {}, {}
        trems = [u for u in self.units.values() if re.search(r"trem", u.name, re.I)]
        for u in trems:
            ch = self.chamber_of(u.name)
            spec = {t for t in self.tokens(u.name) if t not in skip and not t.isdigit()}
            ranks = set()
            for n, toks in rank_tokens.items():
                if ch and self.rank_chamber.get(n) not in (ch, None):
                    continue
                if spec and (toks & spec):
                    ranks.add(n)
            if ranks:
                self.trem_ranks[u.number] = ranks
                specific_claimed.setdefault(ch, set()).update(ranks)
        for u in trems:
            if u.number in self.trem_ranks:
                continue
            ch = self.chamber_of(u.name)
            self.trem_ranks[u.number] = {n for n in rank_tokens
                                         if (ch is None or self.rank_chamber.get(n) == ch)
                                         and n not in specific_claimed.get(ch, set())}
        # shades: chamber -> list of unit numbers
        self.shade_units = {}
        for u in self.units.values():
            toks = self.tokens(u.name)
            if any(t in ("shade", "shades", "shutter", "shutters", "upper", "lower", "side") for t in toks):
                ch = self.chamber_of(u.name)
                if ch:
                    self.shade_units.setdefault(ch, []).append(u.number)
        # traps: unit -> GM percussion note
        self.perc_note = {}
        for u in self.units.values():
            if u.type == 0:
                continue
            name = u.name.lower()
            for key, note in PERCUSSION:
                if key in name:
                    self.perc_note[u.number] = note
                    break

    # -- links / functions
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

    def _recompute(self):
        self.active = set()
        for l in self.links:
            if self.eval_link(l):
                self.active.update(self.d.link_functions(l))
        for c, f, v in self.cots:             # channel outputs: active while the channel is at or above the value
            if self.chan.get(c, 0) >= v:
                self.active.add(f)

    def set_stop(self, n, on):
        if on:
            self.stops_on.add(n)
        else:
            self.stops_on.discard(n)
        self._recompute()

    def set_channel(self, c, v):
        self.chan[c] = v
        self._recompute()

    def set_key(self, kbd, key, on):
        s = self.keys.setdefault(kbd, set())
        if on:
            s.add(key)
        else:
            s.discard(key)

    def rank_functions(self):
        """Active functions that sound a rank, as (function, modifier) where the
        modifier is the pizzicato/reiterate function that reached it, if any."""
        out, seen = [], set()
        todo = [(n, None) for n in self.active]
        while todo:
            n, mod = todo.pop()
            if (n, mod and mod.number) in seen:
                continue
            seen.add((n, mod and mod.number))
            f = self.fncs.get(n)
            if f is None:
                continue
            t = f.type
            if t == 3:
                out.append((f, mod))
            elif t in (13, 14):                      # pizzicato / reiterate modifier
                todo.append((f.w(2), f))
            elif t == 12:                            # function multiplier
                todo.extend((v, mod) for v in f.words(2, 8) if v)
        return out

    def division_keys(self, kbd, depth=0):
        """Keys sounding on a division: its own keys unless unison off, plus
        keys coupled in from other keyboards by active divisional couplers
        (melody and bass couplers pass only their highest or lowest key)."""
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
            special = f.w(14)
            if src_keys and special in (1, 2):      # melody coupler: highest key only
                src_keys = {max(src_keys)}
            elif src_keys and special in (3, 4):    # bass coupler: lowest key only
                src_keys = {min(src_keys)}
            for k in src_keys:
                n2 = k + off
                if lo <= n2 <= hi:
                    keys.add(n2)
        return keys

    def sounding(self):
        """{(rank, note): mode} currently sounding; mode is None, ("piz", ms) or
        ("rit", cycle_ms, duty_tenths, offsets)."""
        out = {}
        cache = {}
        for f, mod in self.rank_functions():
            kbd, rank, off = f.w(2), f.w(4), f.s(6)
            lo, hi = f.w(8) or 1, f.w(10) or NOTES
            if kbd not in cache:
                cache[kbd] = self.division_keys(kbd)
            pipes = self.rank_pipes.get(rank, set())
            for k in cache[kbd]:
                n = k + off
                if not (lo <= n <= hi and n in pipes):
                    continue
                mode = None
                if mod is not None and mod.type == 13:
                    ms = self.piz.get(mod.w(4), [0] * 122)[k] if 0 <= k < 122 else 0
                    mode = ("piz", ms) if ms else None
                elif mod is not None and mod.type == 14:
                    w = self.rit.get(mod.w(4), [0] * 122)[k] if 0 <= k < 122 else 0
                    if w:
                        offsets = []
                        for i in range(4):
                            v = mod.s(6 + 2 * i)
                            if i and v == 0:
                                break
                            offsets.append(v)
                        mode = ("rit", w & 0xFF, (w >> 8) or 5, offsets or [0])
                key = (rank, n)
                if key not in out or out[key] is not None and mode is None:
                    out[key] = mode
        return out

    def units_on(self):
        """Units switched on by active functions: type 5 (direct) and type 4
        (trap: on while any key sounds on its division)."""
        on, cache = set(), {}
        for n in self.active:
            f = self.fncs.get(n)
            if f is None:
                continue
            if f.type == 5 and f.w(2):
                on.add(f.w(2))
            elif f.type == 4 and f.w(4):
                kbd = f.w(2)
                if kbd not in cache:
                    cache[kbd] = self.division_keys(kbd)
                if cache[kbd]:
                    on.add(f.w(4))
        return on

    def trems_on(self, units):
        ranks = set()
        for u in units:
            ranks |= self.trem_ranks.get(u, set())
        return ranks

    def shade_levels(self, units):
        """chamber -> fraction of its shade units that are open."""
        return {ch: sum(1 for u in us if u in units) / len(us) for ch, us in self.shade_units.items() if us}

# GM percussion notes for trap names (first match wins)
PERCUSSION = [("bass drum", 36), ("kettle", 47), ("tympani", 47), ("timpani", 47), ("snare", 38),
              ("bongo", 60), ("tom", 45), ("crash", 49), ("cymbalstern", 59), ("tap cym", 51),
              ("brush cym", 51), ("ride", 51), ("cymbal", 51), ("cymba", 51), ("tambourine", 54),
              ("castanet", 75), ("chinese block", 76), ("wood block", 76), ("block", 77),
              ("sand", 69), ("triangle", 81), ("cowbell", 56), ("maracas", 70), ("sleigh", 54),
              ("gong", 52), ("whistle", 72), ("bell", 53), ("drum", 38)]
GM_PERC_CHANNEL = 9

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
    perc_track = [None]
    organ = Organ(d) if ranks else None
    sounding = {}                   # (rank, note) -> mode
    units_now = set()
    last_t = 0
    keyboards = {k.number: k for k in d.lists.get("Kbd", [])}
    chan_names = {c.number: c.name for c in d.lists.get("Chn", [])}
    stats = {"keys": 0, "stops": 0, "notes": 0, "hits": 0, "unknown_kbd": set()}
    ticks_per_ms = tempo * PPQ / 60000.0

    def ms_ticks(ms):
        return max(1, int(round(ms * ticks_per_ms)))

    def kbd_track(n):
        if n not in kbd_tracks:
            chan = CHANNELS[(n - 1) % len(CHANNELS)]
            name = keyboards[n].name if n in keyboards else f"keyboard {n}"
            tr = Track(f"Kbd {n} {name}")
            tr.add(0, [0xC0 | chan, GM_CHURCH_ORGAN])
            kbd_tracks[n] = (tr, chan); tracks.append(tr)
        return kbd_tracks[n]

    cc_state = {}

    def rank_track(n):
        if n not in rank_tracks:
            chan = CHANNELS[(len(rank_tracks)) % len(CHANNELS)]
            r = d.get("Rnk", n)
            name = r.name if r else f"rank {n}"
            tr = Track(f"Rnk {n} {name}")
            tr.add(0, [0xC0 | chan, program_for(name)])
            rank_tracks[n] = (tr, chan); tracks.append(tr)
        return rank_tracks[n]

    def cc(rank, t, ctl, val):
        tr, chan = rank_track(rank)
        if cc_state.get((chan, ctl)) == val:
            return
        cc_state[(chan, ctl)] = val
        tr.add(t, [0xB0 | chan, ctl, val])

    def percussion():
        if perc_track[0] is None:
            perc_track[0] = Track("Traps (GM percussion)"); tracks.append(perc_track[0])
        return perc_track[0]

    def hit(t, note):
        tr = percussion()
        tr.add(t, [0x90 | GM_PERC_CHANNEL, note, velocity])
        tr.add(t + ms_ticks(40), [0x80 | GM_PERC_CHANNEL, note, 0])
        stats["hits"] += 1

    # -- timers: (time, seq, callback) processed in order before each event
    timers, seq = [], [0]

    def after(t, callback):
        seq[0] += 1
        heapq.heappush(timers, (t, seq[0], callback))

    def run_timers(upto):
        while timers and timers[0][0] <= upto:
            t, _, cb = heapq.heappop(timers)
            cb(t)

    spent = set()          # piz notes already released by their timer
    rit_state = {}         # (rank, note) -> dict(idx, on, pitch, alive)
    unit_reit = {}         # unit -> alive flag for reiterating traps

    def note_on(key, t):
        rank, n = key
        tr, chan = rank_track(rank)
        sink.on(tr, t, chan, midi_note(n)); stats["notes"] += 1

    def note_off(key, t, pitch=None):
        rank, n = key
        tr, chan = rank_track(rank)
        sink.off(tr, t, chan, midi_note(pitch if pitch is not None else n))

    def start(key, mode, t):
        if mode is None:
            note_on(key, t)
        elif mode[0] == "piz":
            note_on(key, t)
            def release(t2, key=key):
                if sounding.get(key, 0) is not None and key in sounding and key not in spent:
                    spent.add(key); note_off(key, t2)
            after(t + ms_ticks(mode[1]), release)
        else:
            _, cycle, duty, offsets = mode
            on_ms = max(1, cycle * duty // 10); off_ms = max(1, cycle - on_ms)
            st = {"idx": 0, "on": True, "pitch": key[1] + offsets[0], "alive": True}
            rit_state[key] = st
            rank = key[0]
            tr, chan = rank_track(rank)
            sink.on(tr, t, chan, midi_note(st["pitch"])); stats["notes"] += 1
            def toggle(t2, key=key, st=st):
                if not st["alive"]:
                    return
                tr, chan = rank_track(key[0])
                if st["on"]:
                    sink.off(tr, t2, chan, midi_note(st["pitch"])); st["on"] = False
                    after(t2 + ms_ticks(off_ms), toggle)
                else:
                    st["idx"] = (st["idx"] + 1) % len(offsets)
                    st["pitch"] = key[1] + offsets[st["idx"]]
                    sink.on(tr, t2, chan, midi_note(st["pitch"])); st["on"] = True
                    after(t2 + ms_ticks(on_ms), toggle)
            after(t + ms_ticks(on_ms), toggle)

    def stop(key, mode, t):
        if mode is not None and mode[0] == "rit":
            st = rit_state.pop(key, None)
            if st:
                st["alive"] = False
                if st["on"]:
                    note_off(key, t, st["pitch"])
            return
        if key in spent:
            spent.discard(key); return
        note_off(key, t)

    def update_units(t):
        nonlocal units_now
        now = organ.units_on()
        for u in sorted(now - units_now):
            note = organ.perc_note.get(u)
            unit = organ.units.get(u)
            if note:
                hit(t, note)
                if unit is not None and unit.type == 3 and unit.w(6):       # reiterating trap
                    cycle = unit.w(6)
                    flag = {"alive": True}; unit_reit[u] = flag
                    def again(t2, u=u, note=note, cycle=cycle, flag=flag):
                        if flag["alive"] and u in units_now:
                            hit(t2, note); after(t2 + ms_ticks(cycle), again)
                    after(t + ms_ticks(cycle), again)
        for u in units_now - now:
            f = unit_reit.pop(u, None)
            if f:
                f["alive"] = False
        if now != units_now:
            units_now = now
            trem = organ.trems_on(now)
            for rank in rank_tracks:
                cc(rank, t, 1, 80 if rank in trem else 0)
            for ch, level in organ.shade_levels(now).items():
                for rank, rch in organ.rank_chamber.items():
                    if rch == ch and rank in rank_tracks:
                        cc(rank, t, 11, 24 + int(round(103 * level)))

    def update_sounding(t):
        nonlocal sounding
        run_timers(t)
        now = organ.sounding()
        for key in sorted(k for k in sounding if k not in now):
            stop(key, sounding[key], t)
        for key in sorted(k for k in now if k not in sounding):
            start(key, now[key], t)
        for key in sorted(k for k in now if k in sounding and now[k] != sounding[k]):
            stop(key, sounding[key], t); start(key, now[key], t)
        sounding = now
        update_units(t)

    pending = False
    for off, t, kind, info in iter_events(data):
        if ranks:
            run_timers(t)
            if pending and t != last_t:
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
                for i, v in enumerate(values or []):
                    organ.set_channel(i + 1, v)
                pending = True
        elif kind == "channel":
            c, v = info
            meta.text(t, f"Chn {c} {chan_names.get(c, '')} = {v}".replace("  ", " "))
            if ranks:
                organ.set_channel(c, v); pending = True
        elif kind == "midi":
            meta.text(t, "midi " + info.hex(" "))
        elif kind == "end":
            break
    if ranks:
        if pending:
            update_sounding(last_t)
        run_timers(last_t)
        for key in list(sounding):
            stop(key, sounding[key], last_t)
        for f in unit_reit.values():
            f["alive"] = False
    sink.all_off(last_t)                      # a track cut short
    # a rank that only ever doubled another rank on the same channel has no notes
    tracks = [tr for i, tr in enumerate(tracks)
              if i == 0 or any(e[2][0] & 0xF0 in (0x80, 0x90) for e in tr.events)]
    return tracks, last_t, stats

# ----------------------------------------------------------------------------- Hauptwerk organs
def nrpn(track, t, chan, number, value):
    track.add(t, [0xB0 | chan, 99, number >> 7])
    track.add(t, [0xB0 | chan, 98, number & 0x7F])
    track.add(t, [0xB0 | chan, 6, value])

def apply_event(organ, kind, info):
    """Feed a registration event to the organ model; True if it was one."""
    if kind == "stop":
        organ.set_stop(*info)
    elif kind == "sync":
        stops_on, values = info[0], info[1]
        for s in stops_on:
            organ.set_stop(s, True)
        for i, v in enumerate(values or []):
            organ.set_channel(i + 1, v)
    elif kind == "channel":
        organ.set_channel(*info)
    else:
        return False
    return True

def hauptwerk_profile(name):
    """The hauptwerk.Profile of an organ module ("paramount332", "friesach")."""
    import importlib, hauptwerk
    return hauptwerk.Profile(importlib.import_module(name))

def render_hauptwerk(data, d, tempo, velocity, prof):
    """One track for Hauptwerk's MIDI player with the organ of prof (a
    hauptwerk.Profile) loaded: keys on its keyboard channels, registration as
    its NRPN switches and CC swells.  Registration changes go out before the
    key presses of the same pulse, after the releases.  The lowest key held on
    a BASS keyboard also plays its bass keyboard while it is within BASS_RANGE,
    decided after each pulse."""
    import hauptwerk
    events = list(iter_events(data))
    keyboards = {k.number: k.name for k in d.lists.get("Kbd", [])}
    assign = prof.keyboard_assignment(d)
    auto = {}
    if hauptwerk.AUTO in assign.values():
        # first pass: what the Bombarde (and Echo) register while they are played
        organ = Organ(d)
        con = hauptwerk.Console(organ, prof, assign)
        seen = {k: set() for k, v in assign.items() if v == hauptwerk.AUTO}
        for _, t, kind, info in events:
            if kind == "end":
                break
            if apply_event(organ, kind, info):
                con.changed()
            elif kind == "key" and info[2] and info[0] in seen:
                seen[info[0]].update(con.requests(info[0]))
        for k, s in seen.items():
            assign[k] = con.choose(s)
            if s:
                auto[keyboards.get(k, f"keyboard {k}")] = assign[k]

    organ = Organ(d)
    played = {info[0] for _, _, kind, info in events if kind == "key" and info[2]}
    con = hauptwerk.Console(organ, prof, assign, played)
    meta = Track("Devtronix track")
    meta.meta(0, 0x51, struct.pack(">I", int(60e6 / tempo))[1:])
    meta.meta(0, 0x58, bytes([4, 2, 24, 8]))
    for name, div in sorted(auto.items()):
        meta.text(0, f"{name} plays the {prof.SHORT} {prof.KEYBOARD_NAMES[div]}")
    for kbd, div in sorted(con.bass.items()):
        meta.text(0, f"{keyboards[kbd]}: lowest key also on the {prof.SHORT} {prof.KEYBOARD_NAMES[div]}")
    tr = Track(prof.ORGAN)
    sink = NoteSink(velocity)
    stats = {"keys": 0, "stops": 0, "notes": 0, "dropped": {}, "auto": auto, "unknown_kbd": set(),
             "bass": {}}
    for name, number in sorted(prof.SWITCHES.items(), key=lambda x: x[1]):      # clear the console
        nrpn(tr, 0, prof.NRPN_CHANNEL, number, 0)
    state = {"on": set(), "cc": {}}
    held = {kbd: {} for kbd in con.bass}            # bass keyboard -> {key: depth}
    low = dict.fromkeys(con.bass)                   # bass keyboard -> key it sounds on the bass keyboard
    lowest = dict.fromkeys(con.bass)
    bass_lo, bass_hi = prof.BASS_RANGE

    def registration(t):
        want = con.switches()
        for s in sorted(state["on"] - want):
            nrpn(tr, t, prof.NRPN_CHANNEL, prof.SWITCHES[s], 0)
        for s in sorted(want - state["on"]):
            nrpn(tr, t, prof.NRPN_CHANNEL, prof.SWITCHES[s], 127)
        state["on"] = want
        for (chan, ctl), v in sorted(con.swells().items()):
            if state["cc"].get((chan, ctl)) != v:
                tr.add(t, [0xB0 | chan, ctl, v]); state["cc"][(chan, ctl)] = v

    def key(t, kbd, k, on):
        if kbd in held:
            h = held[kbd]
            if on:
                h[k] = h.get(k, 0) + 1
            elif h.get(k):
                h[k] -= 1
                if not h[k]:
                    del h[k]
        div = assign.get(kbd)
        if div is None:
            if on:
                name = keyboards.get(kbd, f"keyboard {kbd}")
                stats["dropped"][name] = stats["dropped"].get(name, 0) + 1
                con.count_key(kbd)            # anything registered there is lost with it
            return
        chan = prof.KEYBOARD_CHANNELS[div]
        if on:
            sink.on(tr, t, chan, midi_note(k)); stats["notes"] += 1
            con.count_key(kbd)
        else:
            sink.off(tr, t, chan, midi_note(k))

    def bass(t):
        for kbd, div in con.bass.items():
            k = min(held[kbd]) if held[kbd] else None
            b = stats["bass"].setdefault(keyboards[kbd], {"div": div, "notes": 0, "high": 0})
            if k is not None and k != lowest[kbd] and not bass_lo <= midi_note(k) <= bass_hi:
                b["high"] += 1                # lowest key above BASS_RANGE
            lowest[kbd] = k
            if k is not None and not bass_lo <= midi_note(k) <= bass_hi:
                k = None
            if k != low[kbd]:
                chan = prof.KEYBOARD_CHANNELS[div]
                if low[kbd] is not None:
                    sink.off(tr, t, chan, midi_note(low[kbd]))
                if k is not None:
                    sink.on(tr, t, chan, midi_note(k)); b["notes"] += 1
                low[kbd] = k

    def flush(t, tick_keys, dirty):
        first = {}
        for i, (kbd, k, on) in enumerate(tick_keys):
            first.setdefault((kbd, k), i)
        early = [i for i, (kbd, k, on) in enumerate(tick_keys) if not on and first[(kbd, k)] == i]
        for i in early:                       # releases of keys held before this pulse
            key(t, *tick_keys[i])
        if dirty:
            con.changed()
            registration(t)
        for i, e in enumerate(tick_keys):
            if i not in early:
                key(t, *e)
        if any(kbd in held for kbd, _, _ in tick_keys):
            bass(t)

    registration(0)
    tick_keys, dirty, last_t = [], False, 0
    for _, t, kind, info in events:
        if t != last_t:
            flush(last_t, tick_keys, dirty)
            tick_keys, dirty = [], False
        last_t = t
        if kind == "key":
            kbd, k, on = info
            stats["keys"] += 1
            if kbd not in keyboards:
                stats["unknown_kbd"].add(kbd)
            organ.set_key(kbd, k, on)
            tick_keys.append((kbd, k, on))
        elif kind == "stop":
            n, on = info
            stats["stops"] += 1
            meta.text(t, f"{'+' if on else '-'} {stop_label(d, n)}", 0x06)
            apply_event(organ, kind, info); dirty = True
        elif kind in ("sync", "channel"):
            apply_event(organ, kind, info); dirty = True
        elif kind == "end":
            break
    flush(last_t, tick_keys, dirty)
    sink.all_off(last_t)
    stats["tally"] = con.tally
    return [meta, tr], last_t, stats

def hauptwerk_report(stats, verbose, prof):
    """Lines summarising how the registered ranks were matched (by key-ons)."""
    lines = []
    for name, div in sorted(stats["auto"].items()):
        lines.append(f"  {name} plays the {prof.SHORT} {prof.KEYBOARD_NAMES[div]}")
    for name, n in sorted(stats["dropped"].items()):
        lines.append(f"  {n} key presses on {name} dropped (no {prof.SHORT} keyboard)")
    for name, b in sorted(stats["bass"].items()):
        lines.append(f"  {name}: lowest key also on the {prof.SHORT} {prof.KEYBOARD_NAMES[b['div']]}, "
                     f"{b['notes']} notes" + (f"; {b['high']} times higher, not played"
                                              if b["high"] else ""))
    tally = stats["tally"]
    total = sum(tally.values())
    if not total:
        return lines
    by = {}
    for (status, *_), n in tally.items():
        by[status] = by.get(status, 0) + n
    order = ["exact", "stand-in", "near", "bass", "missing", "silent", "unknown", "no keyboard"]
    lines.append("  ranks sounded per key: " + ", ".join(f"{s} {100 * by[s] / total:.0f}%"
                                                      for s in order if s in by))
    if verbose:
        for status in order[1:]:
            rows = sorted(((n, kbd, name, ft, s) for (st, kbd, name, ft, s), n in tally.items() if st == status),
                          reverse=True)
            if rows:
                lines.append(f"  {status}:")
                for n, kbd, name, ft, s in rows:
                    lines.append(f"    {n:6d}  {kbd} {name} {ft}" + (f" -> {s}" if s else ""))
    return lines

def main():
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("side0"); ap.add_argument("side1", nargs="?")
    ap.add_argument("-t", "--track", required=True, help="track slot, e.g. T8")
    ap.add_argument("-d", "--definition", default="D1", help="definition slot (default D1)")
    ap.add_argument("--def-file", help="use an extracted definition file instead of a slot")
    ap.add_argument("-o", "--out", help="output .mid (default: <disk>-<slot>.mid)")
    ap.add_argument("--tempo", type=float, default=120.0, help="BPM (default 120)")
    ap.add_argument("--velocity", type=int, default=80)
    mode = ap.add_mutually_exclusive_group()
    mode.add_argument("--ranks", action="store_true", help="render through stops and ranks")
    mode.add_argument("--paramount", action="store_true",
                      help="render for Hauptwerk's MIDI player with the Paramount 332 (see paramount332.py)")
    mode.add_argument("--friesach", action="store_true",
                      help="render for Hauptwerk's MIDI player with the Friesach organ (see friesach.py)")
    ap.add_argument("-v", "--verbose", action="store_true",
                    help="with --paramount or --friesach, list every stand-in, substitute and missing rank")
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
    organ = "paramount332" if a.paramount else "friesach" if a.friesach else None
    if organ:
        prof = hauptwerk_profile(organ)
        tracks, end, stats = render_hauptwerk(e.read(), d, a.tempo, a.velocity, prof)
    else:
        tracks, end, stats = render(e.read(), d, a.tempo, a.velocity, a.ranks)
    kind = "paramount" if a.paramount else "friesach" if a.friesach else "ranks" if a.ranks else "keyboards"
    suffix = f"-{kind}" if organ else ""
    out = a.out or f"{os.path.basename(a.side0).split('_s')[0].split('.')[0]}-{e.slot}{suffix}.mid"
    write_midi(out, tracks, end + PPQ)
    secs = end * 60 / (PPQ * a.tempo)
    print(f"{e.slot} {e.name!r} with {dname}: {stats['keys']} key events, {stats['stops']} stop changes, "
          f"{stats['notes']} notes on {len(tracks) - 1} tracks, {secs:.1f} s at {a.tempo:g} BPM"
          f" ({kind}) -> {out}")
    if organ:
        print("\n".join(hauptwerk_report(stats, a.verbose, prof)))
    if stats["unknown_kbd"]:
        print(f"  note: keyboards {sorted(stats['unknown_kbd'])} are not in the definition")

if __name__ == "__main__":
    main()
