#!/usr/bin/env python3
"""Hauptwerk virtual organs as playback targets for Devtronix recordings
(dev2midi.py --paramount, --friesach).

Hauptwerk's MIDI recorder/player uses a fixed MIDI implementation per virtual
organ: note on/off on one channel per keyboard, stops, couplers and
tremulants as NRPN switches (CC 99/98 number, CC 6 value, 127 = on), swell
pedals as controllers.  Each organ is a module of tables (paramount332.py,
friesach.py); this one holds what they share.  Profile indexes a module's
tables, and Console runs over the state of a dev2midi.Organ and says which of
the virtual organ's switches should be on, where its swell pedals stand and
how each registered rank was matched.

An organ module defines:

  ORGAN, SHORT        the organ's name for track names and for reports
  KEYBOARD_CHANNELS   virtual keyboard -> MIDI channel (0-based)
  KEYBOARD_NAMES      virtual keyboard -> its name
  NRPN_CHANNEL        channel of the switch NRPNs (0-based)
  STOPS               stop tabs: (switch, NRPN, voice, footage).  The voice is
                      the rank behind the tab; footage None = the tab plays at
                      any pitch (traps, mixtures)
  stop_division(s)    the virtual keyboard of stop tab s
  SWITCHES            every switch with an NRPN (the tabs, couplers, ...)
  KEYBOARDS           Devtronix keyboard -> virtual keyboard, AUTO (the one of
                      AUTO_CHOICES that has tabs for more of what the track
                      registers there; a tie goes to the first) or None (keys
                      dropped).  DEFAULT_KEYBOARD for names not in the table
  NATIVE_COUPLERS     (keys' keyboard, coupled keyboard, offset) -> switch
  RANKS               Devtronix rank -> voice spec, see parse_voice; a dict
                      {virtual keyboard: spec} gives the rank there only
  NEAR                voice -> voices to try where a keyboard lacks it
  PARENT_VOICES       voice -> voice whose tabs also serve it
  REITERATE, REITERATING_RANKS   re-iterate switches
  TRAPS, EFFECTS      trap units -> trap tabs, effect units -> switches;
                      TRAP_DEFAULT for traps not in the table
  TREMULANTS, STRING_TREMULANTS, TREMULANT_FOLLOWS   tremulant units -> switches
  SWELLS              (channel, controller) -> chambers it follows, the first
                      the definition has shades for
  BASS, BASS_RANGE    Devtronix keyboard -> virtual keyboard its lowest held
                      key also plays, and the MIDI notes it does that for
  KEYBOARD_SWITCHES   Devtronix keyboard -> switches drawn whenever the
                      definition has it (the bass keyboard's stops, couplers)
  PLAYED_ONLY         True: only the keyboards a track plays (and the
                      divisions natively coupled to them) draw their
                      registration, so nothing an unplayed keyboard registers
                      reaches a coupled manual
"""
import re

AUTO = "auto"

FEET = {"32": -24, "16": -12, "10 2/3": -5, "8": 0, "5 1/3": 7, "4": 12, "3 1/5": 16,
        "2 2/3": 19, "2": 24, "1 3/5": 28, "1 1/3": 31, "1": 36}
PITCH_FEET = {v: k for k, v in FEET.items()}

def feet(pitch):
    """Footage of a pitch offset from 8', e.g. -12 -> "16'"."""
    return PITCH_FEET[pitch] + "'" if pitch in PITCH_FEET else f"{pitch:+d}"

def norm(name):
    return " ".join(name.lower().replace("’", "'").split())

def parse_voice(spec):
    """'Tibia Clausa? @32' -> [(voice, fixed pitch or None, stand-in?)].
    "?" = stand-in, "@32" = fixed footage, "A|B" = A, else B where the
    keyboard has no A at that pitch."""
    out = []
    for part in spec.split("|"):
        part = part.strip()
        fixed = None
        if "@" in part:
            part, ft = part.split("@")
            fixed = FEET[ft.strip()]
        part = part.strip()
        guess = part.endswith("?")
        out.append((part.rstrip("?"), fixed, guess))
    return out

def parse_rank(spec):
    if isinstance(spec, dict):
        return {div: parse_rank(s) for div, s in spec.items()}
    return parse_voice(spec) if spec else None

class Profile:
    """The tables of an organ module, indexed for the Console."""
    DEFAULT_KEYBOARD = None
    NATIVE_COUPLERS = {}
    NEAR = {}
    PARENT_VOICES = {}
    REITERATE = {}
    REITERATING_RANKS = set()
    TRAPS = {}
    TRAP_DEFAULT = "unknown"
    EFFECTS = {}
    TREMULANTS = []
    STRING_TREMULANTS = {}
    TREMULANT_FOLLOWS = {}
    SWELLS = {}
    AUTO_CHOICES = ()
    BASS = {}
    BASS_RANGE = (0, 127)
    KEYBOARD_SWITCHES = {}
    PLAYED_ONLY = False

    def __init__(self, module):
        self.module = module
        for k, v in vars(module).items():
            if k.isupper():
                setattr(self, k, v)
        self.STOP_INDEX = {(module.stop_division(name), voice, FEET[ft] if ft else None): name
                           for name, _, voice, ft in self.STOPS}
        self.STOP_VOICE = {name: voice for name, _, voice, _ in self.STOPS}
        self.RANK_SPECS = {norm(k): parse_rank(v) for k, v in self.RANKS.items()}
        self.KEYBOARD_SPECS = {norm(k): v for k, v in self.KEYBOARDS.items()}
        self.TRAP_SPECS = {norm(k): v for k, v in self.TRAPS.items()}
        self.EFFECT_SPECS = {norm(k): v for k, v in self.EFFECTS.items()}
        self.BASS_SPECS = {norm(k): v for k, v in self.BASS.items()}
        self.KEYBOARD_SWITCH_SPECS = {norm(k): v for k, v in self.KEYBOARD_SWITCHES.items()}

    def fits(self, d):
        """True for a definition whose keyboards all appear in KEYBOARDS."""
        kbds = d.lists.get("Kbd", [])
        return bool(kbds) and all(norm(k.name) in self.KEYBOARD_SPECS for k in kbds)

    def keyboard_assignment(self, d):
        """Devtronix keyboard number -> virtual keyboard, AUTO or None."""
        return {k.number: self.KEYBOARD_SPECS.get(norm(k.name), self.DEFAULT_KEYBOARD)
                for k in d.lists.get("Kbd", [])}

    def bass_assignment(self, d):
        """Devtronix keyboard number -> virtual keyboard its lowest key also plays."""
        return {k.number: self.BASS_SPECS[norm(k.name)] for k in d.lists.get("Kbd", [])
                if norm(k.name) in self.BASS_SPECS}

# ----------------------------------------------------------------------------- console
class Console:
    """The switches and swells of a virtual organ (a Profile) wanted for the
    state of a dev2midi.Organ, with a tally of how each registered rank was
    matched.

    assign: Devtronix keyboard number -> virtual keyboard (AUTO resolved by
    choose()), or None.  played: the keyboards the track plays, for
    PLAYED_ONLY."""

    def __init__(self, organ, profile, assign=None, played=None):
        self.o = organ
        self.p = profile
        d = organ.d
        self.d = d
        self.kbd_names = {k.number: k.name for k in d.lists.get("Kbd", [])}
        self.assign = dict(assign) if assign is not None else profile.keyboard_assignment(d)
        self.bass = {k: div for k, div in profile.bass_assignment(d).items() if self.assign.get(k)}
        self.kbd_switches = {s for k in d.lists.get("Kbd", []) if self.assign.get(k.number)
                             for s in profile.KEYBOARD_SWITCH_SPECS.get(norm(k.name), ())}
        self.played = set(played) if profile.PLAYED_ONLY and played is not None else None
        self.rank_names = {r.number: r.name for r in d.lists.get("Rnk", [])}
        self.units = organ.units
        self.trem_units = {}
        for u in self.units.values():
            if re.search(r"trem|temolo", u.name, re.I):
                self.trem_units[u.number] = self._trem_targets(u)
        mapped = {s for ts in self.trem_units.values() for s in ts}
        self.trem_follow = {p: f for p, f in profile.TREMULANT_FOLLOWS.items() if p not in mapped}
        chambers = set(organ.shade_units)
        self.swell_source = {target: next((ch for ch in sources if ch in chambers), None)
                             for target, sources in profile.SWELLS.items()}
        self.cache = {}
        self.tally = {}                     # (status, kbd, rank, feet, switch) -> key-ons
        self.dirty = True
        self._requests = {}

    def _trem_targets(self, u):
        name = u.name.lower()
        for rx, targets in self.p.TREMULANTS:
            if re.search(rx, name):
                if targets == "strings":
                    st = self.p.STRING_TREMULANTS
                    ch = self.o.chamber_of(u.name)
                    return st.get(ch, st["main"] + st["solo"])
                return targets
        return []

    # -- relay state
    def couplers(self):
        out, unison_off = [], set()
        for n in self.o.active:
            f = self.o.fncs.get(n)
            if f is None:
                continue
            if f.type == 1:
                out.append(f)
            elif f.type == 6:
                unison_off.add(f.w(2))
        return out, unison_off

    def reach(self, kbd):
        """({(division, pitch offset)} that the keys of keyboard kbd sound on,
        [native couplers that play the rest], {divisions they couple})."""
        couplers, unison_off = self.couplers()
        native_couplers = self.p.NATIVE_COUPLERS
        here = self.assign.get(kbd)
        native = {}
        for c in couplers:
            if c.w(2) != kbd or c.b(12):
                continue
            div = c.w(4)
            if div == kbd:
                s = None if kbd in unison_off else native_couplers.get((here, here, c.s(6)))
            else:
                there = self.assign.get(div)
                s = native_couplers.get((here, there, c.s(6))) if there != here else None
            if s:
                native[id(c)] = s
        out = set() if kbd in unison_off else {(kbd, 0)}
        out |= {(c.w(4), c.s(6)) for c in couplers
                if c.w(2) == kbd and not c.b(12) and id(c) not in native}
        todo = list(out)
        while todo:                           # couplers that couple the couplers
            div, off = todo.pop()
            for c in couplers:
                if c.b(12) and c.w(2) == div:
                    nxt = (c.w(4), off + c.s(6))
                    if nxt not in out and abs(nxt[1]) <= 36:
                        out.add(nxt); todo.append(nxt)
        return out, sorted(set(native.values())), {c.w(4) for c in couplers if id(c) in native}

    def requests(self, kbd):
        """What keyboard kbd registers: [("rank", rank number, pitch, reiterate?) or
        ("trap", unit number, None, False)], cached until the registration changes.
        Ranks without pipes are left out: the relay never sounds them."""
        if self.dirty:
            self._requests = {}
            self.dirty = False
        if kbd in self._requests:
            return self._requests[kbd]
        by_div = self._by_div()
        out = []
        reach, native, _ = self.reach(kbd)
        for div, off in sorted(reach):
            for f, mod in by_div.get(div, ()):
                if f.type == 3 and self.o.rank_pipes.get(f.w(4)):
                    out.append(("rank", f.w(4), f.s(6) + off, mod is not None and mod.type == 14))
                elif f.type == 4:
                    out.append(("trap", f.w(4), None, False))
        out += [("coupler", s, None, False) for s in native]
        self._requests[kbd] = out
        return out

    def _by_div(self):
        if "_by_div" not in self._requests:
            by = {}
            for f, mod in self.o.rank_functions():
                by.setdefault(f.w(2), []).append((f, mod))
            for n in self.o.active:
                f = self.o.fncs.get(n)
                if f is not None and f.type == 4 and f.w(4):
                    by.setdefault(f.w(2), []).append((f, None))
            self._requests["_by_div"] = by
        return self._requests["_by_div"]

    def changed(self):
        self.dirty = True

    # -- matching
    def resolve(self, div, req):
        """(switch or None, status); status is exact, stand-in, near, missing,
        silent (the table says so) or unknown (not in the table)."""
        key = (div, req[0], req[1], req[2])
        if key in self.cache:
            return self.cache[key]
        kind, what, pitch, _ = req
        p = self.p
        if kind == "coupler":
            res = (what, "exact")
        elif kind == "trap":
            u = self.units.get(what)
            voices = p.TRAP_SPECS.get(norm(u.name), p.TRAP_DEFAULT) if u else "unknown"
            if voices == "unknown":
                res = (None, "unknown")
            elif voices is None:
                res = (None, "silent")
            else:
                res = (None, "missing")
                for v in voices:
                    s = p.STOP_INDEX.get((div, "trap:" + v, None))
                    if s:
                        res = (s, "exact"); break
        else:
            spec = p.RANK_SPECS.get(norm(self.rank_names.get(what, "")), "unknown")
            if isinstance(spec, dict):
                spec = spec.get(div)
            if spec == "unknown":
                res = (None, "unknown")
            elif spec is None:
                res = (None, "silent")
            else:
                res = (None, "missing")
                for voice, fixed, guess in spec:
                    pt = None if voice.startswith("trap:") else (fixed if fixed is not None else pitch)
                    s = self._tab(div, voice, pt)
                    if s:
                        res = (s, "stand-in" if guess else "exact"); break
                else:
                    voice, fixed, _ = spec[0]
                    pt = fixed if fixed is not None else pitch
                    for alt in p.NEAR.get(voice, ()):
                        s = self._tab(div, alt, pt)
                        if s:
                            res = (s, "near"); break
        self.cache[key] = res
        return res

    def _tab(self, div, voice, pitch):
        index = self.p.STOP_INDEX
        s = index.get((div, voice, pitch)) or index.get((div, voice, None))
        if s is None and voice in self.p.PARENT_VOICES:
            s = index.get((div, self.p.PARENT_VOICES[voice], pitch))
        return s

    def choose(self, seen):
        """Virtual keyboard for an AUTO keyboard, from the requests it made."""
        choices = self.p.AUTO_CHOICES
        best, score = choices[0], -1
        for div in choices:
            n = sum(1 for r in seen if self.resolve(div, r)[1] in ("exact", "stand-in"))
            if n > score:
                best, score = div, n
        return best

    # -- output
    def switches(self):
        """Switches that should be on now."""
        p = self.p
        on = set()
        for kbd in self.drawn_keyboards():
            div = self.assign[kbd]
            for req in self.requests(kbd):
                s, _ = self.resolve(div, req)
                if s:
                    on.add(s)
                    if req[0] == "rank":
                        voice = p.STOP_VOICE.get(s)
                        if voice in p.REITERATE and (req[3] or self.rank_names.get(req[1]) in p.REITERATING_RANKS):
                            on.add(p.REITERATE[voice])
        on.update(self.kbd_switches)
        direct = self.direct_units()
        for u in direct:
            on.update(self.trem_units.get(u, ()))
            unit = self.units.get(u)
            e = unit and p.EFFECT_SPECS.get(norm(unit.name))
            if e:
                on.add(e)
        for target, source in self.trem_follow.items():
            if source in on:
                on.add(target)
        return on

    def drawn_keyboards(self):
        """Keyboards whose registration is drawn: every assigned one, or with
        PLAYED_ONLY those the track plays and the divisions natively coupled
        to them."""
        kbds = [k for k, div in self.assign.items() if div is not None]
        if self.played is None:
            return kbds
        keep, todo = set(self.played), list(self.played)
        while todo:
            for div in self.reach(todo.pop())[2]:
                if div not in keep:
                    keep.add(div); todo.append(div)
        return [k for k in kbds if k in keep]

    def direct_units(self):
        return {self.o.fncs[n].w(2) for n in self.o.active
                if n in self.o.fncs and self.o.fncs[n].type == 5 and self.o.fncs[n].w(2)}

    def swells(self):
        """{(channel, controller): value} for the swell pedals."""
        levels = self.o.shade_levels(self.direct_units())
        out = {}
        for (chan, ctl), src in self.swell_source.items():
            out[(chan, ctl)] = int(round(127 * levels.get(src, 0))) if src else 127
        return out

    def count_key(self, kbd):
        """Tally what a key-on on keyboard kbd sounds through."""
        div = self.assign.get(kbd)
        for req in self.requests(kbd):
            s, status = self.resolve(div, req) if div else (None, "no keyboard")
            if req[0] == "rank":
                name, ft = self.rank_names.get(req[1], f"rank {req[1]}"), feet(req[2])
                spec = self.p.RANK_SPECS.get(norm(name))
                if status == "silent" and isinstance(spec, dict) and self.bass.get(kbd) in spec:
                    status = "bass"           # played by the lowest key on the bass keyboard
            elif req[0] == "trap":
                u = self.units.get(req[1]); name, ft = (u.name if u else f"unit {req[1]}"), ""
            else:
                name, ft = req[1], ""
            k = (status, self.kbd_names.get(kbd, str(kbd)), name.strip(), ft, s)
            self.tally[k] = self.tally.get(k, 0) + 1
