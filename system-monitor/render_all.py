#!/usr/bin/env python3
"""Render every Track/Song (T) file on every disk image to MIDI and catalogue them.

usage:
  render_all.py [--images ../disk-images --images ../decoded-images] [--out ../renders] [--tempo 120] [--no-verify]

For each disk image under --images (a *_s0/*_s1 pair, or a single 819200-byte
*.img with no such pair beside it) the directory is listed with devfs.py, a
definition is chosen for each T file, and the file is rendered twice with
dev2midi.py's render(): plain (one MIDI channel per keyboard) and through the
stops and ranks (--ranks).  Output:

  <out>/<disk>/<slot>-<name>.mid         keyboards rendering
  <out>/<disk>/<slot>-<name>-ranks.mid   ranks rendering
  <out>/INDEX.md                         one table per disk
  <out>/index.json                       the same data for programs

<disk> is the folder path relative to --images; when a folder holds more than
one image set the image's own stem is appended (cmm/cmm1, cmm/cmm2, ...).

Choosing a definition.  The monitor autoloads D1, so D1 of the same disk is
the recording's definition whenever it exists and parses.  When it does not,
the other D files of the disk, then the D files of disks with the same volume
label, then disks of the same label family ("58 Note Player #2" and "#1"),
then every definition in the collection are considered, in that order of
preference.  Within a tier the definition that covers the track best wins
(share of key events on keyboards the definition has, and of the stop numbers
it references within the definition's stop list), then D1 before other slots,
then the most specific definition (fewest stops) that still covers, then the
larger of otherwise equal ones, then the lower slot number.  The
INDEX records which was used, and from where.

Decode problems are recorded, never skipped: a file that cannot be read
(extents beyond the image), a stream without the $FF terminator or one that
ends before the recorded size, key events that do not balance, keyboards or
keys outside the definition, unknown event codes and absurd time jumps
(garbage sectors).

With verification (default) every written MIDI file is parsed back: note-on
and note-off counts must balance on every channel and note, and the length of
the file must match the last event time of the track stream.
"""
import argparse, collections, hashlib, json, os, pathlib, re, struct, sys, time

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from devfs import Disk, iter_events, SECTOR  # noqa: E402
from devdef import Definition, NOTES  # noqa: E402
from dev2midi import render, write_midi, PPQ  # noqa: E402

HERE = pathlib.Path(__file__).resolve().parent
PULSES_PER_SECOND = 192            # 96 per beat at 120 BPM

# ----------------------------------------------------------------------------- discovery
def discover(images_roots):
    """Yield (disk_name, side0, side1_or_None, root) for every image set under the roots.
    The name is the folder path relative to its root; a name already used under an earlier
    root gets the root's folder name prepended."""
    if isinstance(images_roots, (str, pathlib.Path)):
        images_roots = [images_roots]
    seen = set()
    for images_root in images_roots:
        yield from _discover_root(pathlib.Path(images_root), seen)

def _discover_root(root, seen):
    sets = collections.defaultdict(list)       # folder -> [(stem, s0, s1)]
    for p in sorted(root.rglob("*")):
        if not p.is_file():
            continue
        m = re.match(r"(.*)_s0(\.img)?$", p.name, re.I)
        if m:
            s1 = p.with_name(m.group(1) + "_s1" + (m.group(2) or ""))
            sets[p.parent].append((m.group(1), p, s1 if s1.exists() else None))
    for p in sorted(root.rglob("*.img")):
        if not p.is_file() or p.stat().st_size != 2 * 80 * 5 * SECTOR:
            continue
        stems = {s.lower() for s, _, _ in sets.get(p.parent, [])}
        if p.stem.lower() not in stems:        # a plain image without a _s0/_s1 pair
            sets[p.parent].append((p.stem, p, None))
    for folder in sorted(sets):
        rel = folder.relative_to(root).as_posix()
        for stem, s0, s1 in sorted(sets[folder]):
            name = rel if len(sets[folder]) == 1 else f"{rel}/{stem}"
            if name in seen:
                name = f"{root.name}/{name}"
            seen.add(name)
            yield name, s0, s1, root

def flux_report(s0):
    """fluxdecode.py leaves <stem>.report.txt beside the images it decodes; return (path, summary line)."""
    stem = re.sub(r"_s0(\.img)?$", "", pathlib.Path(s0).name, flags=re.I)
    rep = pathlib.Path(s0).with_name(stem + ".report.txt")
    if not rep.exists():
        return None, None
    summary = next((l[2:] for l in rep.read_text().splitlines() if l.startswith("# sectors:")), "")
    return str(rep), summary

def image_digest(s0, s1):
    h = hashlib.sha1()
    h.update(pathlib.Path(s0).read_bytes())
    if s1:
        h.update(pathlib.Path(s1).read_bytes())
    return h.hexdigest()[:12]

# ----------------------------------------------------------------------------- analysis
def analyze(data, size_on_disk):
    """Walk a track stream once; return stats and a list of problems."""
    st = {"bytes": len(data), "events": 0, "key_on": 0, "key_off": 0, "stops": 0, "sync": 0,
          "channel": 0, "midi": 0, "console": 0, "codes": 0, "last_time": 0, "end": None,
          "kbds": collections.Counter(), "stop_numbers": set(), "bad_keys": 0, "first_bad": None,
          "max_jump": 0, "unbalanced": 0, "error": None}
    held = collections.Counter()                 # (kbd, key) -> depth
    prev_t = 0
    try:
        for off, t, kind, info in iter_events(data):
            st["events"] += 1
            if t - prev_t > st["max_jump"]:
                st["max_jump"] = t - prev_t
            prev_t = t
            st["last_time"] = t
            bad = False
            if kind == "key":
                kbd, key, on = info
                st["kbds"][kbd] += 1
                if on:
                    st["key_on"] += 1; held[(kbd, key)] += 1
                else:
                    st["key_off"] += 1
                    if held[(kbd, key)] > 0:
                        held[(kbd, key)] -= 1
                    else:
                        st["unbalanced"] += 1
                if not 1 <= key <= NOTES:
                    st["bad_keys"] += 1; bad = True
            elif kind == "stop":
                st["stops"] += 1; st["stop_numbers"].add(info[0])
            elif kind == "sync":
                st["sync"] += 1; st["stop_numbers"].update(info[0])
                if info[3] is not None:
                    bad = True
            elif kind == "channel":
                st["channel"] += 1
            elif kind == "midi":
                st["midi"] += 1
            elif kind == "console":
                st["console"] += 1
            elif kind == "code":
                st["codes"] += 1; bad = True
            elif kind == "end":
                st["end"] = off
            if bad and st["first_bad"] is None:
                st["first_bad"] = off
    except (IndexError, struct.error) as e:
        st["error"] = f"stream ends mid-event ({type(e).__name__})"
    st["unbalanced"] += sum(held.values())       # keys still down at the end
    problems = []
    if st["error"]:
        problems.append(st["error"])
    if st["end"] is None:
        problems.append("no end-of-track marker (file cut short)")
    else:
        tail = data[st["end"] + 1:]              # the recorder leaves one 0 byte after the $FF
        if len(tail) > 2 or tail.strip(b"\0"):
            problems.append(f"{len(tail)} bytes after the end marker at byte {st['end']}")
    if st["bytes"] != size_on_disk:
        problems.append(f"read {st['bytes']} of {size_on_disk} bytes")
    if st["unbalanced"]:
        problems.append(f"{st['unbalanced']} key events do not balance")
    if st["codes"]:
        problems.append(f"{st['codes']} unknown event codes")
    if st["bad_keys"]:
        problems.append(f"{st['bad_keys']} key numbers outside 1..{NOTES}")
    if st["max_jump"] > 3600 * PULSES_PER_SECOND:
        problems.append(f"time jump of {st['max_jump'] / PULSES_PER_SECOND / 3600:.0f} h")
    if st["first_bad"] is not None:
        sec = st["first_bad"] // SECTOR
        problems.append(f"garbage from byte {st['first_bad']:#x} (file block {sec})")
    return st, problems

# ----------------------------------------------------------------------------- definitions
class DefEntry:
    def __init__(self, disk_name, label, slot, name, d, size):
        self.disk, self.label, self.slot, self.name, self.d, self.size = disk_name, label, slot, name, d, size
        self.kbds = {k.number for k in d.lists.get("Kbd", [])}
        self.nstops = len(d.lists.get("Stp", []))
        self.slot_number = int(slot[1:])

    def coverage(self, st):
        keys = sum(st["kbds"].values())
        kc = sum(n for k, n in st["kbds"].items() if k in self.kbds) / keys if keys else 1.0
        stops = st["stop_numbers"]
        sc = sum(1 for s in stops if 1 <= s <= self.nstops) / len(stops) if stops else 1.0
        return kc, sc

    def __str__(self):
        return f"{self.slot}{' ' + repr(self.name) if self.name else ''}"

def label_family(label):
    return re.sub(r"\s*#\s*\d+\s*$", "", label).strip().lower()

def choose_definition(pool, disk_name, label, st):
    """Pick a definition for a track; return (DefEntry, tier, reason) or (None, None, why)."""
    if not pool:
        return None, None, "no definition anywhere"
    fam = label_family(label)
    def tier(e):
        if e.disk == disk_name:
            return 0
        if e.label == label:
            return 1
        if label_family(e.label) == fam:
            return 2
        return 3
    scored = []
    for e in pool:
        kc, sc = e.coverage(st)
        # tier, best coverage, D1 first, the most specific (fewest stops) definition
        # that still covers, the larger of otherwise equal ones, the lower slot
        scored.append((tier(e), -(kc + sc), 0 if e.slot_number == 1 else 1, e.nstops, -e.size, e.slot_number, e))
    scored.sort(key=lambda x: x[:6])
    t, best = scored[0][0], scored[0][-1]
    kc, sc = best.coverage(st)
    why = {0: "same disk", 1: f"disk {best.disk} (same label)",
           2: f"disk {best.disk} (label family)", 3: f"disk {best.disk} (collection)"}[t]
    if best.slot_number == 1 and t == 0:
        why = "D1 of this disk"
    cov = "" if kc >= 0.999 and sc >= 0.999 else f"; covers {kc:.0%} of key events, {sc:.0%} of stops"
    return best, t, why + cov

# ----------------------------------------------------------------------------- MIDI read-back
def read_midi(path):
    """Minimal SMF reader: returns (division, [(abs_time, status, d1, d2) per note event], max_end)."""
    data = pathlib.Path(path).read_bytes()
    assert data[:4] == b"MThd"
    fmt, ntracks, division = struct.unpack(">HHH", data[8:14])
    pos = 14
    notes, ends = [], []
    for _ in range(ntracks):
        assert data[pos:pos + 4] == b"MTrk"
        ln = struct.unpack(">I", data[pos + 4:pos + 8])[0]
        body = data[pos + 8:pos + 8 + ln]; pos += 8 + ln
        t, i, running = 0, 0, None
        while i < len(body):
            delta, shift = 0, 0
            while True:
                b = body[i]; i += 1
                delta = (delta << 7) | (b & 0x7F)
                if not b & 0x80:
                    break
            t += delta
            b = body[i]
            if b == 0xFF:
                kind = body[i + 1]; i += 2
                ln2, shift = 0, 0
                while True:
                    c = body[i]; i += 1
                    ln2 = (ln2 << 7) | (c & 0x7F)
                    if not c & 0x80:
                        break
                i += ln2
                if kind == 0x2F:
                    ends.append(t)
                continue
            if b in (0xF0, 0xF7):
                i += 1
                ln2 = 0
                while True:
                    c = body[i]; i += 1
                    ln2 = (ln2 << 7) | (c & 0x7F)
                    if not c & 0x80:
                        break
                i += ln2
                continue
            if b & 0x80:
                running = b; i += 1
            status = running
            hi = status & 0xF0
            if hi in (0xC0, 0xD0):
                i += 1
            else:
                d1, d2 = body[i], body[i + 1]; i += 2
                if hi in (0x80, 0x90):
                    notes.append((t, status if not (hi == 0x90 and d2 == 0) else 0x80 | (status & 0x0F), d1, d2))
    return division, notes, max(ends) if ends else 0

def verify_midi(path, expected_end):
    """Return a list of problems with a rendered file (empty = good)."""
    probs = []
    try:
        division, notes, end = read_midi(path)
    except Exception as e:                       # noqa: BLE001
        return [f"unreadable: {e}"]
    if division != PPQ:
        probs.append(f"division {division}")
    depth = collections.Counter()
    neg = 0
    for t, status, note, vel in notes:
        k = (status & 0x0F, note)
        if status & 0xF0 == 0x90:
            depth[k] += 1
        else:
            if depth[k] <= 0:
                neg += 1
            else:
                depth[k] -= 1
    open_notes = sum(depth.values())
    if open_notes or neg:
        probs.append(f"{open_notes} notes never released, {neg} offs without on")
    if end != expected_end + PPQ:
        probs.append(f"length {end} pulses, expected {expected_end + PPQ}")
    return probs

# ----------------------------------------------------------------------------- main loop
def safe_name(s):
    s = re.sub(r"[^A-Za-z0-9.'&()-]+", "-", s).strip("-")
    return s[:40]

def fmt_duration(pulses):
    sec = pulses / PULSES_PER_SECOND
    if sec >= 36000:
        return f"{sec / 3600:.0f} h (!)"
    m, s = divmod(int(round(sec)), 60)
    return f"{m}:{s:02d}"

def run(images_roots, out_root, tempo, velocity, verify):
    if isinstance(images_roots, (str, pathlib.Path)):
        images_roots = [images_roots]
    out_root = pathlib.Path(out_root)
    out_root.mkdir(parents=True, exist_ok=True)
    disks = []                                   # per-disk records, in discovery order
    pool = []                                    # every usable definition in the collection
    t0 = time.time()

    # pass 1: open every image, list it, parse its definitions
    for name, s0, s1, root in discover(images_roots):
        report, flux_summary = flux_report(s0)
        rec = {"disk": name, "side0": str(s0), "side1": str(s1) if s1 else None, "root": str(root),
               "digest": image_digest(s0, s1), "label": None, "system": False, "note": None,
               "flux_report": report, "flux_summary": flux_summary,
               "definitions": [], "tracks": [], "other": 0}
        disks.append(rec)
        try:
            disk = Disk(s0, s1)
        except Exception as e:                   # noqa: BLE001
            rec["note"] = f"cannot open: {e}"; continue
        if not disk.is_system:
            rec["note"] = f"not a system disk (boot byte 1 = ${disk.boot[1]:02X}, {os.path.getsize(s0)} bytes/side)"
            continue
        rec["system"], rec["label"] = True, disk.label
        rec["_disk"] = disk
        try:
            entries = disk.directory()
        except Exception as e:                   # noqa: BLE001
            rec["note"] = f"directory unreadable: {e}"; continue
        rec["_entries"] = entries
        for e in entries:
            if e.letter == "D":
                drec = {"slot": e.slot, "name": e.name, "size": e.size, "ok": False, "summary": ""}
                rec["definitions"].append(drec)
                try:
                    d = Definition(e.read())
                    de = DefEntry(name, disk.label, e.slot, e.name, d, e.size)
                    pool.append(de)
                    drec["ok"] = True
                    drec["summary"] = (f"{len(de.kbds)} keyboards, {de.nstops} stops, "
                                       f"{len(d.lists.get('Rnk', []))} ranks")
                except Exception as ex:          # noqa: BLE001
                    drec["summary"] = f"unusable: {ex}"
            elif e.letter != "T":
                rec["other"] += 1
    # identical images
    by_digest = collections.defaultdict(list)
    for rec in disks:
        by_digest[rec["digest"]].append(rec["disk"])
    for rec in disks:
        twins = [d for d in by_digest[rec["digest"]] if d != rec["disk"]]
        rec["identical_to"] = twins

    # pass 2: analyse and render every T file
    n_tracks = n_files = 0
    for rec in disks:
        if "_entries" not in rec:
            continue
        disk = rec["_disk"]
        out_dir = out_root / rec["disk"]
        for e in rec["_entries"]:
            if e.letter != "T":
                continue
            n_tracks += 1
            tr = {"slot": e.slot, "name": e.name, "size": e.size, "sectors": len(e.sectors),
                  "problems": [], "definition": None, "definition_from": None, "duration_s": None,
                  "notes": None, "files": {}, "verify": {}}
            rec["tracks"].append(tr)
            if not e.header_ok:
                tr["problems"].append("header record contains trash")
            try:
                data = e.read()
            except Exception as ex:              # noqa: BLE001
                # read what is inside the image, so a partly readable file still renders
                good = []
                for s in e.sectors:
                    try:
                        good.append(disk.read_logical(s))
                    except Exception:            # noqa: BLE001
                        break
                data = b"".join(good)[:e.size]
                tr["problems"].append(f"extents beyond the image ({ex}); {len(data)} bytes readable")
            st, probs = analyze(data, e.size)
            tr["problems"] += probs
            tr["duration_s"] = st["last_time"] / PULSES_PER_SECOND
            tr["last_time"] = st["last_time"]
            tr["notes"] = st["key_on"]
            tr["stops"] = st["stops"]
            tr["keyboards"] = sorted(st["kbds"])
            tr["events"] = st["events"]
            if not data or st["events"] == 0:
                tr["problems"].append("no events; not rendered")
                continue
            de, tier, why = choose_definition(pool, rec["disk"], rec["label"], st)
            if de is None:
                tr["problems"].append(f"no definition ({why}); not rendered")
                continue
            tr["definition"] = str(de)
            tr["definition_from"] = why
            unknown_kbds = sorted(k for k in st["kbds"] if k not in de.kbds)
            if unknown_kbds:
                tr["problems"].append(f"keyboards {unknown_kbds} not in the definition")
            over = sorted(s for s in st["stop_numbers"] if s > de.nstops)
            if over:
                tr["problems"].append(f"{len(over)} stop numbers above the definition's {de.nstops}")
            out_dir.mkdir(parents=True, exist_ok=True)
            base = e.slot + (f"-{safe_name(e.name)}" if safe_name(e.name) else "")
            for ranks, suffix in ((False, ""), (True, "-ranks")):
                path = out_dir / f"{base}{suffix}.mid"
                try:
                    tracks, end, stats = render(data, de.d, tempo, velocity, ranks)
                    write_midi(path, tracks, end + PPQ)
                    tr["files"][suffix or "plain"] = {"path": str(path.relative_to(out_root)),
                                                      "tracks": len(tracks) - 1, "notes": stats["notes"]}
                    n_files += 1
                    if verify:
                        v = verify_midi(path, end)
                        tr["verify"][suffix or "plain"] = v
                        if v:
                            tr["problems"].append(f"{'ranks' if ranks else 'plain'} MIDI: " + "; ".join(v))
                except Exception as ex:          # noqa: BLE001
                    tr["problems"].append(f"{'ranks' if ranks else 'plain'} render failed: {type(ex).__name__}: {ex}")
            print(f"{rec['disk']:40} {e.slot:5} {e.name[:26]:26} {fmt_duration(st['last_time']):>8} "
                  f"{st['key_on']:6d} notes  {str(de):28} {'; '.join(tr['problems'])}")

    for rec in disks:
        rec.pop("_disk", None); rec.pop("_entries", None)
    summary = {"disks": len(disks), "system_disks": sum(1 for r in disks if r["system"]),
               "tracks": n_tracks, "midi_files": n_files,
               "tracks_with_problems": sum(1 for r in disks for t in r["tracks"] if t["problems"]),
               "tracks_not_rendered": sum(1 for r in disks for t in r["tracks"] if not t["files"]),
               "verify_failures": sum(1 for r in disks for t in r["tracks"] for v in t["verify"].values() if v),
               "tempo": tempo, "seconds": round(time.time() - t0, 1)}
    (out_root / "index.json").write_text(json.dumps({"summary": summary, "disks": disks}, indent=1, default=str))
    write_index(out_root / "INDEX.md", disks, summary, images_roots)
    print(f"\n{summary['tracks']} tracks on {summary['system_disks']} system disks -> {summary['midi_files']} MIDI files; "
          f"{summary['tracks_with_problems']} tracks with problems, {summary['tracks_not_rendered']} not rendered, "
          f"{summary['verify_failures']} verification failures ({summary['seconds']} s)")
    return summary

# ----------------------------------------------------------------------------- INDEX.md
def md(s):
    return str(s).replace("|", "\\|").replace("\n", " ")

def write_index(path, disks, summary, images_roots):
    L = []
    L.append("# Devtronix Model 264 recordings: MIDI renders\n")
    shown_roots = [os.path.relpath(r, pathlib.Path(path).resolve().parent) for r in images_roots]
    L.append("Generated by `system-monitor/render_all.py` from the images under "
             + " and ".join(f"`{r}`" for r in shown_roots) + ".")
    L.append(f"Every Track/Song (`T`) file was rendered twice: `<slot>-<name>.mid` plays one MIDI channel per "
             f"keyboard (what the organist's hands and feet did), `<slot>-<name>-ranks.mid` plays it through the "
             f"stops and ranks of the definition (what the organ sounded like, minus traps, tremulants and "
             f"expression). The tempo is not stored in a track; all durations assume {summary['tempo']:g} BPM "
             f"(192 pulses per second). Note count = key presses in the track; the ranks rendering sounds more "
             f"notes (one per rank and pitch).\n")
    L.append("| | |\n|---|---|")
    L.append(f"| Image sets found | {summary['disks']} |")
    L.append(f"| System disks | {summary['system_disks']} |")
    L.append(f"| Track files | {summary['tracks']} |")
    L.append(f"| MIDI files written | {summary['midi_files']} |")
    L.append(f"| Tracks with decode problems | {summary['tracks_with_problems']} |")
    L.append(f"| Tracks not rendered | {summary['tracks_not_rendered']} |")
    L.append(f"| MIDI read-back failures | {summary['verify_failures']} |\n")
    L.append("**Definition used.** The monitor autoloads `D1`, so `D1` of the same disk is used when it exists. "
             "Otherwise the best-covering definition is taken from the same disk, then from a disk with the same "
             "volume label, then the same label family, then the whole collection (see the docstring of "
             "`render_all.py`); the table says which.\n")
    L.append("**Problems** are reported per track and the track is still rendered when anything can be decoded; "
             "a MIDI read-back failure means the written file did not pass the note-balance/length check.\n")

    # contents
    L.append("## Disks\n")
    L.append("| Disk | Volume label | D files | T files | Notes |\n|---|---|---|---|---|")
    for r in disks:
        anchor = re.sub(r"[^a-z0-9-]+", "-", r["disk"].lower()).strip("-")
        notes = []
        if r["note"]:
            notes.append(r["note"])
        if r["identical_to"]:
            notes.append("identical image to " + ", ".join(f"`{d}`" for d in r["identical_to"]))
        if r.get("flux_report"):
            notes.append("decoded from the flux dump by `fluxdecode.py`")
        nd = len(r["definitions"]); nt = len(r["tracks"])
        link = f"[`{md(r['disk'])}`](#{anchor})" if r["system"] and nt else f"`{md(r['disk'])}`"
        L.append(f"| {link} | {md(r['label']) if r['label'] else ''} | {nd or ''} | {nt or ''} | {md('; '.join(notes))} |")
    L.append("")
    L.append("Folders under the image root that hold only flux dumps (`*.raw`) or `.hfe` files have no sector "
             "image to read; they are listed at the end of this file. Byte-identical images are rendered twice, "
             "once under each name.\n")

    for r in disks:
        if not r["system"] or not r["tracks"]:
            continue
        L.append(f"## {md(r['disk'])}\n")
        L.append(f"Volume label **{md(r['label'])}**, image `{md(os.path.relpath(r['side0'], r['root']))}`"
                 + (f" + `{md(os.path.relpath(r['side1'], r['root']))}`" if r["side1"] else "")
                 + (f" under `{md(os.path.relpath(r['root'], pathlib.Path(path).resolve().parent))}`"
                    if len(images_roots) > 1 else "") + ".")
        if r.get("flux_report"):
            L.append(f"Decoded from the flux-level dump by `fluxdecode.py`: {md(r['flux_summary'])}. "
                     f"Report: `{md(os.path.relpath(r['flux_report'], pathlib.Path(path).resolve().parent))}`.")
        if r["identical_to"]:
            L.append("Byte-identical to " + ", ".join(f"`{d}`" for d in r["identical_to"]) + ".")
        if r["definitions"]:
            L.append("Definitions on the disk: " + "; ".join(
                f"`{d['slot']}`{' ' + repr(d['name']) if d['name'] else ''} ({d['summary']})" for d in r["definitions"]) + ".")
        else:
            L.append("No definition file on this disk.")
        L.append("")
        L.append("| Slot | Track name | Duration | Notes | Stop changes | Keyboards | Definition used | Problems |")
        L.append("|---|---|---:|---:|---:|---|---|---|")
        for t in r["tracks"]:
            files = t["files"]
            slot = t["slot"]
            if "plain" in files:
                slot = f"[{t['slot']}]({md(files['plain']['path'])})"
            if "-ranks" in files:
                slot += f" ([ranks]({md(files['-ranks']['path'])}))"
            dur = fmt_duration(t["last_time"]) if t.get("last_time") is not None else ""
            defn = f"`{md(t['definition'])}`, {md(t['definition_from'])}" if t["definition"] else ""
            kb = ",".join(str(k) for k in t.get("keyboards", []))
            L.append(f"| {slot} | {md(t['name'])} | {dur} | {t['notes'] if t['notes'] is not None else ''} | "
                     f"{t.get('stops', '')} | {kb} | {defn} | {md('; '.join(t['problems']))} |")
        L.append("")

    L.append("## Image folders without a sector image\n")
    L.append("These hold only flux-level dumps (`.raw`, one per track and side) or an HxC `.hfe` and no decoded "
             "image under any of the roots covers them (`fluxdecode.py` decodes such folders). "
             "`devtronix-hardware/devtronix-raw-disk-images/disk-images-list.txt` notes which reads were clean.\n")
    # a folder is covered when an image set was found at the same relative path under any root
    covered = set()
    for r in disks:
        rel = pathlib.Path(r["side0"]).parent.resolve().relative_to(pathlib.Path(r["root"]).resolve()).as_posix()
        covered.add(rel)
        covered.add(r["disk"])                 # cmm/cmm3: image in the parent folder, named after the stream folder
    rows = []
    for root in images_roots:
        root = pathlib.Path(root)
        for folder in sorted(p for p in root.rglob("*") if p.is_dir()):
            rel = folder.relative_to(root).as_posix()
            if rel in covered or any(c.startswith(rel + "/") for c in covered):
                continue
            files = [f for f in folder.iterdir() if f.is_file()]
            if not files:
                continue
            kinds = collections.Counter(f.suffix.lower() or f.name for f in files)
            rows.append(f"| `{md(rel)}` | {', '.join(f'{n} {k}' for k, n in kinds.most_common())} |")
    if rows:
        L.append("| Folder | Contents |\n|---|---|")
        L.extend(rows)
    else:
        L.append("None.")
    L.append("")
    path.write_text("\n".join(L))

def main():
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--images", action="append", metavar="ROOT",
                    help="image root; may be given more than once (default: ../disk-images and ../decoded-images "
                         "when the latter exists)")
    ap.add_argument("--out", default=str(HERE.parent / "renders"))
    ap.add_argument("--tempo", type=float, default=120.0)
    ap.add_argument("--velocity", type=int, default=80)
    ap.add_argument("--no-verify", action="store_true", help="skip the MIDI read-back check")
    a = ap.parse_args()
    if not a.images:
        a.images = [str(HERE.parent / "disk-images")]
        if (HERE.parent / "decoded-images").is_dir():
            a.images.append(str(HERE.parent / "decoded-images"))
    run(a.images, a.out, a.tempo, a.velocity, not a.no_verify)

if __name__ == "__main__":
    main()
