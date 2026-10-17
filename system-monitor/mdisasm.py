#!/usr/bin/env python3
"""Flow-following 68000 disassembler for the Devtronix System Monitor 2.6 (183).

usage: mdisasm.py monitor-183.bin [--base 0x1032] [--sym monitor-183.sym] [-o out.asm]

The monitor is position independent: it starts with `lea 0(pc),a5`, so A5 is the
relocation base (0 when the image is loaded at $1032 as the boot ROM does) and
every variable lives at a small offset from A5 (= absolute low RAM).  Three
calling conventions are followed:

  * `move.l #addr,d7 ; jsr/jmp (a5,d7.l)`      relocatable call to `addr`
  * `moveq #n,d7 ; trap #0`                    system call n (table at $356A)
    - n = $35 with d6 bit 0 set, n = $0B, n = $03: a NUL-terminated string
      follows the trap inline (padded to a word); the handler skips it.
  * `moveq #n,d7 ; trap #1`                    disk/file service n (table $3F48)
  * `move.w T(pc,d7.w),d7 ; jsr/jmp T(pc,d7.w)` word-offset jump tables
  * `move.l T(pc,d7.w),d7 ; jmp (a5,d7.l)`      long-address jump tables

Everything not reached is printed as data (strings where printable).  Names and
comments come from the symbol file; see monitor-183.sym for the format:

  ADDR  name            ; comment            label (code or data)
  =ADDR name            ; comment            A5-relative variable
  T0 n  name            ; comment            trap #0 function n
  T1 n  name            ; comment            trap #1 function n
  ADDR  ;; text                               block comment printed before ADDR
  ADDR  ; text                                end-of-line comment at ADDR
  !ADDR len                                   force a data range of len bytes
  ~ADDR                                       force code at ADDR (extra entry)
  #ADDR count                                 jump table at ADDR has `count` entries
  @ADDR count stride off                      table of `count` records of `stride` bytes at
                                              ADDR, each holding a code address (long) at `off`
"""
import argparse, pathlib, re, struct, sys
from capstone import Cs, CS_ARCH_M68K, CS_MODE_M68K_000

ap = argparse.ArgumentParser()
ap.add_argument("bin")
ap.add_argument("--base", type=lambda x: int(x, 16), default=0x1032)
ap.add_argument("--sym", default=None)
ap.add_argument("-o", "--out", default=None)
ap.add_argument("--entries", nargs="*", default=[], type=lambda x: int(x, 16))
ap.add_argument("--trap0", type=lambda x: int(x, 16), default=0x356A, help="address of the trap #0 table")
ap.add_argument("--trap1", type=lambda x: int(x, 16), default=0x3F48, help="address of the trap #1 table")
ap.add_argument("--speculate", action="store_true",
                help="after the flow pass, treat untraced regions that decode cleanly as code (labels spec_XXXXX)")
args = ap.parse_args()

img = pathlib.Path(args.bin).read_bytes()
raw = bytearray(len(img)); raw[0::2] = img[1::2]; raw[1::2] = img[0::2]   # byte-address order (strings)
BASE = args.base
END = BASE + len(img)
md = Cs(CS_ARCH_M68K, CS_MODE_M68K_000)

def rd16(a): return struct.unpack_from(">H", img, a - BASE)[0]
def rd32(a): return struct.unpack_from(">I", img, a - BASE)[0]
def inimg(a): return BASE <= a < END

# ---------------------------------------------------------------- symbols
labels, varnames, trap0n, trap1n = {}, {}, {}, {}
blockc, eolc, forced_data, forced_code, table_count = {}, {}, {}, set(), {}
ptr_tables = []   # (addr, count, stride, off)
hdr_text = []
if args.sym:
    for ln in pathlib.Path(args.sym).read_text().splitlines():
        if ln.startswith("%"):            # header prose
            hdr_text.append(ln[1:]); continue
        s = ln.rstrip()
        if not s or s.lstrip().startswith("#!") or s.startswith("# ") or s == "#":
            continue
        m = re.match(r"^(=?)([0-9A-Fa-f]+)\s+;;\s?(.*)$", s)
        if m and not m.group(1):
            blockc.setdefault(int(m.group(2), 16), []).append(m.group(3)); continue
        m = re.match(r"^([0-9A-Fa-f]+)\s+;\s?(.*)$", s)
        if m:
            eolc[int(m.group(1), 16)] = m.group(2); continue
        m = re.match(r"^T([01])\s+([0-9A-Fa-f]+)\s+(\S+)\s*(?:;\s?(.*))?$", s)
        if m:
            (trap0n if m.group(1) == "0" else trap1n)[int(m.group(2), 16)] = (m.group(3), m.group(4) or "")
            continue
        m = re.match(r"^!([0-9A-Fa-f]+)\s+([0-9A-Fa-f]+)", s)
        if m:
            forced_data[int(m.group(1), 16)] = int(m.group(2), 16); continue
        m = re.match(r"^~([0-9A-Fa-f]+)", s)
        if m:
            forced_code.add(int(m.group(1), 16)); continue
        m = re.match(r"^#([0-9A-Fa-f]+)\s+(\d+)", s)
        if m:
            table_count[int(m.group(1), 16)] = int(m.group(2)); continue
        m = re.match(r"^@([0-9A-Fa-f]+)\s+(\d+)\s+(\d+)\s+(\d+)", s)
        if m:
            ptr_tables.append(tuple(int(x, 16 if i == 0 else 10) for i, x in enumerate(m.groups()))); continue
        m = re.match(r"^(=?)([0-9A-Fa-f]+)\s+(\S+)\s*(?:;\s?(.*))?$", s)
        if m:
            a = int(m.group(2), 16)
            if m.group(1):
                varnames[a] = (m.group(3), m.group(4) or "")
            else:
                labels[a] = m.group(3)
                if m.group(4):
                    eolc.setdefault(a, m.group(4))
            continue
        print("sym: cannot parse:", ln, file=sys.stderr)

# ---------------------------------------------------------------- traversal
code = {}          # addr -> (size, mnemonic, opstr, bytes, comment)
is_code = bytearray(len(img))   # 1 = instruction start, 2 = instruction body, 3 = inline string
inline_str = {}    # addr -> (bytes, length incl pad)
tables = {}        # addr -> (kind, count)
worklist = []
calls = set(); jumps = set()
TRAP0_TABLE, TRAP0_N = args.trap0, 62
TRAP1_TABLE, TRAP1_N = args.trap1, 28
INLINE_T0 = {0x0B}          # unconditional inline string
INLINE_T0_D6 = {0x35, 0x03}  # inline string when d6 bit 0 is set

def push(a, kind="jump"):
    if inimg(a) and not (a & 1) and is_code[a - BASE] == 0 and a not in forced_data:
        worklist.append(a)
    elif inimg(a) and (a & 1):
        print(f"warning: odd target ${a:05X}", file=sys.stderr)
    if kind == "call": calls.add(a)
    else: jumps.add(a)

def decode(a):
    off = a - BASE
    w = rd16(a)
    if w == 0x4E7B:                                  # movec Rn,CRn (68020)
        ext = rd16(a + 2)
        reg = ("d" if ext >> 15 == 0 else "a") + str((ext >> 12) & 7)
        cr = {0x002: "cacr", 0x000: "sfc", 0x001: "dfc", 0x801: "vbr"}.get(ext & 0xFFF, f"${ext&0xfff:03x}")
        return (4, "movec", f"{reg}, {cr}")
    ins = list(md.disasm(img[off:off + 10], a, count=1))
    if not ins:
        return None
    i = ins[0]
    return (i.size, i.mnemonic, i.op_str)

def reads_table(t, count_hint, kind):
    """Follow a jump table at t. kind 'w' = word offsets rel. to t, 'l' = long addrs."""
    n = count_hint or table_count.get(t)
    targets = []
    i = 0
    lowest = None
    while True:
        if n is not None and i >= n:
            break
        ea = t + (2 if kind == "w" else 4) * i
        if n is None and lowest is not None and ea >= lowest:
            break
        if not inimg(ea + 3):
            break
        if kind == "w":
            v = rd16(ea); tgt = (t + (v - 0x10000 if v & 0x8000 else v))
        else:
            tgt = rd32(ea)
        if n is None and not (inimg(tgt) and not tgt & 1):
            break
        if n is None and is_code[ea - BASE]:
            break
        targets.append(tgt)
        if inimg(tgt) and (lowest is None or tgt < lowest) and tgt > t:
            lowest = tgt
        i += 1
    if not targets:
        print(f"warning: empty jump table at ${t:05X}", file=sys.stderr)
        return targets
    tables[t] = (kind, len(targets))
    for k in range(len(targets) * (2 if kind == "w" else 4)):
        if is_code[t - BASE + k] == 0: is_code[t - BASE + k] = 4
    for k, tgt in enumerate(targets):
        if inimg(tgt) and not tgt & 1 and tgt != t:
            push(tgt, "call")
            labels.setdefault(tgt, f"tbl_{t:05X}_{k}")
    return targets

def trace(start):
    a = start
    d7 = None; d6 = None; last_tbl = None
    while inimg(a) and is_code[a - BASE] == 0 and a not in forced_data:
        d = decode(a)
        if d and any(is_code[a - BASE + k] for k in range(1, d[0])):
            d = None
        if d is None:
            code[a] = (2, "dc.w", f"${rd16(a):04x}", img[a-BASE:a-BASE+2], "")
            is_code[a - BASE] = 1; is_code[a - BASE + 1] = 2
            return
        size, mn, op = d
        if a + size > END:
            return
        comment = ""
        bs = img[a - BASE:a - BASE + size]
        for k in range(size):
            is_code[a - BASE + k] = 1 if k == 0 else 2
        # constants tracked for the calling conventions
        m = re.match(r"^#\$?([0-9a-f]+), d7$", op)
        if mn in ("moveq", "move.l", "move.w") and m:
            d7 = int(m.group(1), 16)
            if mn == "moveq" and d7 >= 0x80: d7 -= 0x100
        m = re.match(r"^#\$?([0-9a-f]+), d6$", op)
        if mn in ("moveq", "move.l", "move.w") and m:
            d6 = int(m.group(1), 16)
            if mn == "moveq" and d6 >= 0x80: d6 -= 0x100
        if re.match(r"^(d7|d6)$", op.split(",")[-1].strip()) and not m and mn not in ("cmp.b","cmp.w","cmp.l","tst.b","tst.w","tst.l","cmpi.b","cmpi.w","cmpi.l","btst"):
            if op.endswith("d7") and not re.match(r"^#", op): d7 = None
            if op.endswith("d6") and not re.match(r"^#", op): d6 = None
        # word-offset table read:  move.w $T(pc, d7.w), d7
        m = re.match(r"^\$([0-9a-f]+)\(pc, d\d\.w\), d7$", op)
        if mn == "move.w" and m:
            last_tbl = ("w", int(m.group(1), 16))
        m = re.match(r"^\$([0-9a-f]+)\(pc, d\d\.w\), d7$", op)
        if mn == "move.l" and m:
            last_tbl = ("l", int(m.group(1), 16))
        nxt = a + size
        stop = False
        if mn in ("jsr", "jmp", "bsr.b", "bsr.w", "bsr", "bra.b", "bra.w", "bra") or mn.startswith("b") and mn not in ("bset.b","bclr.b","bchg.b","btst.b","bset.l","bclr.l","bchg.l","btst.l","bset","bclr","bchg","btst","bkpt","bfchg","bfclr","bfexts","bfextu","bfffo","bfins","bfset","bftst"):
            m = re.match(r"^\$([0-9a-f]+)$", op)
            if m:                                   # pc-relative branch/call with absolute target
                tgt = int(m.group(1), 16)
                iscall = mn.startswith("bsr")
                push(tgt, "call" if iscall else "jump")
                if mn.startswith("bra") or mn == "jmp":
                    stop = True
            m = re.match(r"^\$([0-9a-f]+)\(pc\)$", op)
            if m and mn in ("jsr", "jmp"):
                tgt = int(m.group(1), 16)
                push(tgt, "call" if mn == "jsr" else "jump")
                op = f"${tgt:05x}(pc)"
                if mn == "jmp": stop = True
            if op == "(a5, d7.l)" and mn in ("jsr", "jmp"):
                if d7 is not None and last_tbl is None:
                    push(d7, "call")
                    comment = f"-> {labels.get(d7, f'${d7:05X}')}"
                elif last_tbl and last_tbl[0] == "l":
                    reads_table(last_tbl[1], None, "l"); last_tbl = None
                    comment = "long jump table"
                if mn == "jmp": stop = True
            m = re.match(r"^\$([0-9a-f]+)\(pc, d\d\.w\)$", op)
            if m and mn in ("jsr", "jmp"):
                t = int(m.group(1), 16)
                if last_tbl and last_tbl[0] == "w" and last_tbl[1] == t:
                    reads_table(t, None, "w"); last_tbl = None
                    comment = "word-offset jump table"
                else:
                    # jump into a table of code stubs: treat following words as code anyway
                    pass
                if mn == "jmp": stop = True
            if mn == "jmp" and op in ("(a6)", "(a0)", "(a1)", "(a2)", "(a3)", "(a4)"):
                stop = True
        if mn in ("rts", "rte", "rtr"):
            stop = True
        if mn == "trap":
            n = int(op.lstrip("#$"), 16)
            if n == 0 and d7 is not None:
                name = trap0n.get(d7 & 0xFF, (None,))[0]
                comment = f"sys ${d7&0xff:02X}" + (f" {name}" if name else "")
                inline = (d7 & 0xFF) in INLINE_T0 or ((d7 & 0xFF) in INLINE_T0_D6 and d6 is not None and d6 & 1)
                if (d7 & 0xFF) in INLINE_T0_D6 and d6 is None:
                    comment += "  ?? d6 unknown"
                if inline:
                    s = a + size
                    e = s
                    while inimg(e) and img[e - BASE] != 0: e += 1
                    e += 1
                    if e & 1: e += 1
                    inline_str[s] = bytes(raw[s - BASE:e - BASE])
                    for k in range(s, min(e, END)): is_code[k - BASE] = 3
                    nxt = e
            elif n == 1 and d7 is not None:
                name = trap1n.get(d7 & 0xFF, (None,))[0]
                comment = f"dsk ${d7&0xff:02X}" + (f" {name}" if name else "")
            elif n in (0, 1):
                comment = "sys ? (d7 not constant)" if n == 0 else "dsk ? (d7 not constant)"
            d7 = None
        code[a] = (size, mn, op, bs, comment)
        if stop:
            return
        a = nxt

# entries
push(BASE, "call")
for i in range(TRAP0_N):
    t = rd32(TRAP0_TABLE + 4 * i)
    if inimg(t): push(t, "call"); labels.setdefault(t, trap0n.get(i, (f"sys_{i:02X}",))[0])
for i in range(TRAP1_N):
    v = rd16(TRAP1_TABLE + 2 * i); t = TRAP1_TABLE + (v - 0x10000 if v & 0x8000 else v)
    if inimg(t): push(t, "call"); labels.setdefault(t, trap1n.get(i, (f"dsk_{i:02X}",))[0])
tables[TRAP0_TABLE] = ("l", TRAP0_N); tables[TRAP1_TABLE] = ("w", TRAP1_N)
for k in range(TRAP0_N * 4): is_code[TRAP0_TABLE - BASE + k] = 4
for k in range(TRAP1_N * 2): is_code[TRAP1_TABLE - BASE + k] = 4
for (ta, cnt, stride, off) in ptr_tables:
    for k in range(cnt):
        rec = ta + k * stride
        tgt = rd32(rec + off)
        if inimg(tgt) and not tgt & 1:
            push(tgt, "call")
    for k in range(cnt * stride): is_code[ta - BASE + k] = 4
    forced_data.setdefault(ta, cnt * stride)
for a in forced_code: push(a, "call")
for a in args.entries: push(a, "call")
# vector installs:  lea X(pc),aN ; move.l aN,$VV.w   -> X is code
for a in range(BASE, END - 8, 2):
    if rd16(a) & 0xF1FF == 0x41FA:          # lea d16(pc),aN
        disp = rd16(a + 2); disp = disp - 0x10000 if disp & 0x8000 else disp
        tgt = a + 2 + disp
        w2 = rd16(a + 4)
        if w2 & 0xFFF8 == 0x21C8 and (rd16(a + 6) < 0x400):   # move.l aN,$xx.w
            if inimg(tgt): push(tgt, "call"); labels.setdefault(tgt, f"vec_{rd16(a+6):02X}_{tgt:05X}")

while worklist:
    a = worklist.pop()
    if is_code[a - BASE] == 0:
        trace(a)

# speculative pass: untraced gaps that decode cleanly into a terminated block
BAD = {"movep.w", "movep.l", "illegal", "bkpt", "chk.w", "trapv", "rtd", "bgnd", "callm", "rtm", "reset", "stop",
       "ori.b", "ori.w", "ori.l", "andi.b", "eori.b", "subi.b", "addi.b", "nbcd.b", "abcd.b", "sbcd.b", "movea.w",
       "exg.l", "unlk", "link.w", "divs.w", "chk.l", "pack", "unpk", "cmpi.b", "negx.b", "negx.w", "negx.l", "bfchg", "bftst"}
def looks_like_code(a):
    n = 0; e = a
    while inimg(e) and n < 60:
        if is_code[e - BASE] or e in forced_data:
            return False
        d = decode(e)
        if d is None or d[1] in BAD or d[1].startswith("dc"):
            return False
        if d[1] in ("movea.l", "move.l", "move.w", "move.b") and re.match(r"^\$[0-9a-f]+\([ad]\d(, .*)?\), -\(a[0-6]\)$", d[2]):
            return False
        if "(a7)" in d[2] and d[1] not in ("movem.l", "movem.w", "move.l", "move.w", "pea", "lea.l", "movea.l", "unlk", "link.w", "cmpa.l", "tst.l", "addq.l", "subq.l", "clr.w", "move.b", "addq.w", "cmp.l", "adda.l"):
            return False
        if re.search(r"\$[0-9a-f]{5,}", d[2]) and "(pc" not in d[2] and not (d[1][0] == "b" or d[1] in ("jsr", "jmp", "dbra", "dbf")) and not d[1].startswith("db") and not re.search(r"#\$[0-9a-f]+", d[2]) and ".w" not in d[2] and ".l" not in d[2]:
            return False
        n += 1; e += d[0]
        if d[1] in ("rts", "rte", "rtr", "jmp") or d[1].startswith("bra"):
            return n >= 3
    return False
if args.speculate:
    found = 1
    while found:
        found = 0
        a = BASE
        while a < END - 8:
            if is_code[a - BASE] == 0 and a not in forced_data and (a - 2 < BASE or is_code[a - 2 - BASE] in (1, 2, 3, 4)) and looks_like_code(a):
                labels.setdefault(a, f"spec_{a:05X}")
                push(a, "call"); found += 1
                while worklist:
                    x = worklist.pop()
                    if is_code[x - BASE] == 0: trace(x)
            a += 2 if is_code[a - BASE] == 0 else (code[a][0] if a in code else 2)

# lea X(pc) data references -> labels
lea_refs = {}
for a, (size, mn, op, bs, c) in code.items():
    m = re.match(r"^\$([0-9a-f]+)\(pc\), a\d$", op)
    if mn == "lea.l" and m:
        t = int(m.group(1), 16)
        lea_refs.setdefault(t, []).append(a)
        if inimg(t) and is_code[t - BASE] == 0:
            labels.setdefault(t, f"dat_{t:05X}")
        elif inimg(t):
            labels.setdefault(t, f"L_{t:05X}")
for t in calls:
    if inimg(t): labels.setdefault(t, f"sub_{t:05X}")
for t in jumps:
    if inimg(t): labels.setdefault(t, f"L_{t:05X}")

# ---------------------------------------------------------------- output
def fmt_op(op):
    # name a5-relative variables, branch targets, pc-relative data
    def var(m):
        a = int(m.group(1), 16)
        if a in varnames: return f"{varnames[a][0]}(a5)"
        return m.group(0)
    op = re.sub(r"\$([0-9a-f]+)\(a5\)", var, op)
    def lab(m):
        a = int(m.group(1), 16)
        return labels.get(a, m.group(0))
    op = re.sub(r"(?<![\w$(])\$([0-9a-f]{4,5})(?![\w(])", lambda m: labels.get(int(m.group(1), 16), m.group(0)) if inimg(int(m.group(1), 16)) else m.group(0), op)
    op = re.sub(r"\$([0-9a-f]+)\(pc\)", lambda m: labels.get(int(m.group(1),16), m.group(0)) + "(pc)" if int(m.group(1),16) in labels else m.group(0), op)
    op = re.sub(r"\$([0-9a-f]+)\(pc, (d\d\.w)\)", lambda m: labels.get(int(m.group(1),16), "$"+m.group(1)) + f"(pc,{m.group(2)})", op)
    op = op.replace("#$", "#$").replace(", ", ",")
    return op

def strlit(bs):
    out, cur = [], ""
    for c in bs:
        if 32 <= c < 127 and c != ord("'"):
            cur += chr(c)
        else:
            if cur: out.append(f"'{cur}'"); cur = ""
            out.append(f"${c:02X}")
    if cur: out.append(f"'{cur}'")
    return ",".join(out)

lines = []
if hdr_text:
    lines += hdr_text
lines.append("")
a = BASE
while a < END:
    if a in blockc:
        lines.append("")
        lines.append("; " + "-" * 77)
        for t in blockc[a]: lines.append(f"; {t}")
        lines.append("; " + "-" * 77)
    lab = labels.get(a)
    if a in tables and tables[a][1] > 0:
        kind, n = tables[a]
        if lab: lines.append(f"{a:05X}  {'':<22} {lab}:")
        for i in range(n):
            ea = a + (2 if kind == "w" else 4) * i
            if kind == "w":
                v = rd16(ea); tgt = a + (v - 0x10000 if v & 0x8000 else v)
                lines.append(f"{ea:05X}  {v:04X}{'':<18} dc.w    {labels.get(tgt, f'${tgt:05X}')}-{lab or f'${a:05X}'}  ; {i:2d} (${i:02X})" + (f" {trap1n[i][1]}" if a == TRAP1_TABLE and i in trap1n and trap1n[i][1] else ""))
            else:
                tgt = rd32(ea)
                extra = ""
                if a == TRAP0_TABLE and i in trap0n and trap0n[i][1]: extra = " " + trap0n[i][1]
                lines.append(f"{ea:05X}  {tgt:08X}{'':<14} dc.l    {labels.get(tgt, f'${tgt:05X}')}  ; {i:2d} (${i:02X}){extra}")
        a += (2 if kind == "w" else 4) * n
        continue
    st = is_code[a - BASE]
    if st == 1:
        size, mn, op, bs, c = code[a]
        hx = " ".join(f"{bs[i]:02X}{bs[i+1]:02X}" for i in range(0, size, 2))
        com = []
        if c: com.append(c)
        if a in eolc: com.append(eolc[a])
        if lab:
            lines.append(f"{a:05X}  {'':<22} {lab}:")
        txt = f"{a:05X}  {hx:<22} {mn:<8}{fmt_op(op)}"
        if com: txt = f"{txt:<60} ; {'  '.join(com)}"
        lines.append(txt)
        a += size
    elif st == 3:
        bs = inline_str[a]
        lines.append(f"{a:05X}  {'':<22} dc.b    {strlit(bs)}")
        a += len(bs)
    else:
        # data run until next code / label / forced range end
        if lab: lines.append(f"{a:05X}  {'':<22} {lab}:")
        e = a
        limit = forced_data.get(a)
        while True:
            e += 1
            if e >= END or is_code[e - BASE] in (1, 3) or e in tables or e in labels or e in blockc:
                break
            if limit is not None and e >= a + limit:
                break
            if e in forced_data:
                break
        chunk = bytes(raw[a - BASE:e - BASE])
        # print as string if mostly printable, else hex rows
        printable = sum(1 for c in chunk if 32 <= c < 127 or c in (0,))
        if len(chunk) >= 4 and printable >= 0.85 * len(chunk):
            # split on NULs
            pos = 0
            while pos < len(chunk):
                nul = chunk.find(b"\0", pos)
                if nul < 0: nul = len(chunk)
                seg = chunk[pos:nul + 1] if nul < len(chunk) else chunk[pos:]
                # also absorb runs of NUL padding
                nn = nul + 1
                while nn < len(chunk) and chunk[nn] == 0: nn += 1
                seg = chunk[pos:nn]
                for k in range(0, len(seg), 64):
                    part = seg[k:k + 64]
                    txt = f"{a+pos+k:05X}  {'':<22} dc.b    {strlit(part)}"
                    if a + pos + k in eolc: txt = f"{txt:<60} ; {eolc[a+pos+k]}"
                    lines.append(txt)
                pos = nn
        else:
            for k in range(0, len(chunk), 16):
                part = img[a - BASE + k:min(a - BASE + k + 16, e - BASE)]      # hex in word order
                asc = "".join(chr(c) if 32 <= c < 127 else "." for c in chunk[k:k + 16])  # text in byte order
                hx = " ".join(f"{part[i]:02X}{part[i+1]:02X}" if i + 1 < len(part) else f"{part[i]:02X}" for i in range(0, len(part), 2))
                txt = f"{a+k:05X}  {hx:<40} |{asc}|"
                if a + k in eolc: txt = f"{txt:<60} ; {eolc[a+k]}"
                lines.append(txt)
        a = e

out = "\n".join(lines) + "\n"
if args.out:
    pathlib.Path(args.out).write_text(out)
    ncode = sum(1 for v in is_code if v in (1, 2))
    print(f"{args.out}: {len(lines)} lines, {ncode} code bytes of {len(img)}, {len(code)} instructions, {len(inline_str)} inline strings, {len(tables)} tables", file=sys.stderr)
else:
    sys.stdout.write(out)
