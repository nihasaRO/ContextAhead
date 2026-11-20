"""Every text the engine produced (85 situations in both unit systems, 80,000 random ones) against the real fonts
and the panel's shape, at the face's positions. Run after harness.cjs and fuzz.cjs (check.sh does)."""
import json, os, sys
import numpy as np
sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), ".."))
import preview as P

c = P.Canvas()
H = {"big": 12, "small": 11, "tiny": 7, "word": 16}


def width(font, s):
    miss = [ch for ch in s if ch not in P.F[font]]
    return (None, miss) if miss else (c.width(font, s), [])


def avail(y, font):
    # widest centred text (centre x 88) whose rows y .. y + height stay on the panel
    w = 999
    for r in range(y, y + H[font]):
        xs = np.nonzero(P.MASK[r])[0]
        w = min(w, 2 * min(88 - xs.min(), xs.max() + 1 - 88))
    return w


t = json.load(open("fuzz_texts.json"))
rows = json.load(open("texts.json")) + json.load(open("texts_imp.json"))
words = set(t[1]) | {r[0] for r in rows}
pairs = set()
probs = []
for r in rows:
    pairs.add((r[0], r[1]))
sig_details = set(t[2]) | {r[1] for r in rows}
l1s = set(t[3]) | {r[2] for r in rows}
l2s = set(t[4]) | {r[3] for r in rows}
xs = set(t[5]) | {r[5] for r in rows}

# Signal: the word ends before the circle's bezel (x 102); the detail before x 108 (the bezel curves away)
for wd in words:
    ww, miss = width("word", wd)
    if miss:
        probs.append(("word font lacks", wd, miss))
    elif 28 + ww > 101:
        probs.append(("word too wide", wd, ww))
for d in sig_details:
    dw, miss = width("small", d)
    if miss:
        probs.append(("small font lacks", d, miss))
    elif 28 + dw > 107:
        probs.append(("detail too wide", d, dw))
a1b, a1s = avail(128, "big"), avail(128, "small")
for s in l1s:
    wb, mb = width("big", s)
    ws, ms = width("small", s)
    if mb or ms:
        probs.append(("line 1 font lacks", s, mb or ms))
    elif not (wb <= 166 and wb <= a1b) and ws > a1s:
        probs.append(("line 1 too wide", s, ws))
a2, a2r = avail(150, "small"), avail(146, "small")
for s in l2s:
    w2, m2 = width("small", s)
    if m2:
        probs.append(("line 2 font lacks", s, m2))
    elif w2 > min(a2, a2r):
        probs.append(("line 2 too wide", s, w2))
a3 = avail(160, "tiny")
for s in xs:
    w3, m3 = width("tiny", s)
    if m3:
        probs.append(("raise line: tiny font lacks", s, m3))
    elif w3 > a3:
        probs.append(("raise line too wide", s, w3, a3))
print(f"widths: {len(words)} words, {len(sig_details)} details, {len(l1s)} line 1, {len(l2s)} line 2, "
      f"{len(xs)} raise lines; room: line 2 {min(a2, a2r)} px, raise line {a3} px; problems: {len(probs)}")
for p in sorted(probs, key=str)[:40]:
    print("  ", p)
