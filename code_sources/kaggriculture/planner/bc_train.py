"""Train the behavioural-cloning MLP in pure numpy.

numpy only, deliberately: the submitted agent must be stdlib-only, so the
trained weights have to be exportable as plain Python lists and evaluated with
a hand-written forward pass. Training with torch and then reimplementing
inference invites a silent mismatch between the two; training the same forward
pass we will ship removes that risk entirely.

Reported accuracy is not the number that matters. 47% of the tape's actions are
moves (N/S/E/W) whose direction is nearly arbitrary given local features -- two
routes of equal length differ only in tie-breaking -- so a high move-confusion
rate costs little, while getting WATER or FEED wrong kills a crop or an animal.
Per-class recall is printed for that reason, and the real test is
planner/bc_play.py: what does a policy made only of this network actually bank?
"""
import argparse
import json
import os
import sys
import time

import numpy as np

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, ROOT)
BC_DIR = os.path.join(ROOT, "planner", "bc")


def softmax(z):
    z = z - z.max(axis=1, keepdims=True)
    e = np.exp(z)
    return e / e.sum(axis=1, keepdims=True)


def train(X, Y, n_out, hidden=(128, 96), epochs=14, batch=4096, lr=3e-3,
          seed=0, l2=1e-6, val_frac=0.08):
    rng = np.random.default_rng(seed)
    n, d = X.shape
    idx = rng.permutation(n)
    n_val = int(n * val_frac)
    vi, ti = idx[:n_val], idx[n_val:]
    Xtr, Ytr, Xva, Yva = X[ti], Y[ti], X[vi], Y[vi]

    mu, sd = Xtr.mean(0), Xtr.std(0) + 1e-6
    Xtr = (Xtr - mu) / sd
    Xva = (Xva - mu) / sd

    sizes = [d] + list(hidden) + [n_out]
    W = [rng.normal(0, np.sqrt(2.0 / sizes[i]), (sizes[i], sizes[i + 1])).astype(np.float32)
         for i in range(len(sizes) - 1)]
    B = [np.zeros(sizes[i + 1], dtype=np.float32) for i in range(len(sizes) - 1)]
    mW = [np.zeros_like(w) for w in W]; vW = [np.zeros_like(w) for w in W]
    mB = [np.zeros_like(b) for b in B]; vB = [np.zeros_like(b) for b in B]
    b1, b2, eps = 0.9, 0.999, 1e-8
    step = 0

    def forward(Xb):
        acts = [Xb]
        for i in range(len(W) - 1):
            acts.append(np.maximum(acts[-1] @ W[i] + B[i], 0))
        acts.append(acts[-1] @ W[-1] + B[-1])
        return acts

    for ep in range(epochs):
        perm = rng.permutation(len(Xtr))
        tot = 0.0
        for s in range(0, len(perm), batch):
            bi = perm[s:s + batch]
            xb, yb = Xtr[bi], Ytr[bi]
            acts = forward(xb)
            p = softmax(acts[-1])
            m = len(bi)
            loss = -np.log(p[np.arange(m), yb] + 1e-9).mean()
            tot += loss * m
            g = p
            g[np.arange(m), yb] -= 1.0
            g /= m
            step += 1
            for i in range(len(W) - 1, -1, -1):
                gW = acts[i].T @ g + l2 * W[i]
                gB = g.sum(0)
                if i > 0:
                    g = (g @ W[i].T) * (acts[i] > 0)
                mW[i] = b1 * mW[i] + (1 - b1) * gW
                vW[i] = b2 * vW[i] + (1 - b2) * gW * gW
                mB[i] = b1 * mB[i] + (1 - b1) * gB
                vB[i] = b2 * vB[i] + (1 - b2) * gB * gB
                lr_t = lr * np.sqrt(1 - b2 ** step) / (1 - b1 ** step)
                W[i] -= lr_t * mW[i] / (np.sqrt(vW[i]) + eps)
                B[i] -= lr_t * mB[i] / (np.sqrt(vB[i]) + eps)
        va = forward(Xva)[-1].argmax(1)
        acc = (va == Yva).mean()
        print(f"  epoch {ep+1:>2}  train_loss {tot/len(Xtr):.4f}  val_acc {acc:.4f}", flush=True)
    return W, B, mu, sd, Xva, Yva


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--data", default="bc_dataset.npz")
    ap.add_argument("--epochs", type=int, default=14)
    ap.add_argument("--hidden", default="128,96")
    ap.add_argument("--out", default="bc_model.json")
    args = ap.parse_args()

    z = np.load(os.path.join(BC_DIR, args.data), allow_pickle=True)
    X, Y, OPS = z["X"], z["Y"].astype(np.int64), list(z["ops"])
    print(f"{X.shape[0]:,} samples x {X.shape[1]} features, {len(OPS)} action classes")
    hidden = tuple(int(h) for h in args.hidden.split(","))
    t0 = time.time()
    W, B, mu, sd, Xva, Yva = train(X, Y, len(OPS), hidden=hidden, epochs=args.epochs)
    print(f"trained in {time.time()-t0:.0f}s")

    acts = [Xva]
    for i in range(len(W) - 1):
        acts.append(np.maximum(acts[-1] @ W[i] + B[i], 0))
    pred = (acts[-1] @ W[-1] + B[-1]).argmax(1)
    print()
    print(f"{'action':<20} {'support':>9} {'recall':>8} {'precision':>10}")
    MOVES = {"NORTH", "SOUTH", "EAST", "WEST"}
    for i, op in enumerate(OPS):
        sup = int((Yva == i).sum())
        if not sup:
            continue
        rec = float((pred[Yva == i] == i).mean())
        pp = int((pred == i).sum())
        prec = float((Yva[pred == i] == i).mean()) if pp else 0.0
        print(f"{op:<20} {sup:>9,} {rec:>8.3f} {prec:>10.3f}")
    move_mask = np.isin(Yva, [i for i, o in enumerate(OPS) if o in MOVES])
    print()
    print(f"overall val accuracy      {(pred == Yva).mean():.4f}")
    print(f"accuracy on NON-move ops  {(pred[~move_mask] == Yva[~move_mask]).mean():.4f}"
          f"   ({int((~move_mask).sum()):,} samples)")
    print(f"accuracy on move ops      {(pred[move_mask] == Yva[move_mask]).mean():.4f}")
    print("(move direction is often an arbitrary tie-break; non-move accuracy is what matters)")

    model = {"ops": [str(o) for o in OPS], "mu": mu.tolist(), "sd": sd.tolist(),
             "W": [w.tolist() for w in W], "B": [b.tolist() for b in B]}
    p = os.path.join(BC_DIR, args.out)
    json.dump(model, open(p, "w"))
    print(f"\nsaved {p} ({os.path.getsize(p)/1e6:.1f} MB)")


if __name__ == "__main__":
    main()
