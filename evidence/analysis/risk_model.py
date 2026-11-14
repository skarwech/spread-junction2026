"""Small, dependency-free tools for the lateness model: a ridge logistic regression fitted by Newton steps,
AUC, log-loss and calibration. Pure Python because the venv has no numpy."""
from __future__ import annotations

import math
from dataclasses import dataclass
from typing import Callable, Sequence


def sigmoid(z: float) -> float:
    if z >= 0:
        return 1.0 / (1.0 + math.exp(-z))
    e = math.exp(z)
    return e / (1.0 + e)


def logit(p: float) -> float:
    p = min(max(p, 1e-6), 1 - 1e-6)
    return math.log(p / (1 - p))


def solve(a: list[list[float]], b: list[float]) -> list[float]:
    """Gaussian elimination with partial pivoting (a is k x k, small)."""
    k = len(b)
    m = [row[:] + [b[i]] for i, row in enumerate(a)]
    for c in range(k):
        piv = max(range(c, k), key=lambda r: abs(m[r][c]))
        m[c], m[piv] = m[piv], m[c]
        d = m[c][c]
        for r in range(c + 1, k):
            f = m[r][c] / d
            if f:
                mr, mc = m[r], m[c]
                for j in range(c, k + 1):
                    mr[j] -= f * mc[j]
    x = [0.0] * k
    for r in range(k - 1, -1, -1):
        x[r] = (m[r][k] - sum(m[r][j] * x[j] for j in range(r + 1, k))) / m[r][r]
    return x


@dataclass(frozen=True)
class Logit:
    names: tuple[str, ...]
    mean: tuple[float, ...]
    sd: tuple[float, ...]
    beta: tuple[float, ...]  # intercept first, then one per standardised feature

    def eta(self, x: Sequence[float]) -> float:
        return self.beta[0] + sum(b * (v - m) / s for b, v, m, s in zip(self.beta[1:], x, self.mean, self.sd))

    def prob(self, x: Sequence[float]) -> float:
        return sigmoid(self.eta(x))

    def per_unit(self) -> list[tuple[str, float]]:
        """Log-odds change per unit of each raw feature."""
        return [(n, b / s) for n, b, s in zip(self.names, self.beta[1:], self.sd)]

    def raw_intercept(self) -> float:
        return self.beta[0] - sum(b * m / s for b, m, s in zip(self.beta[1:], self.mean, self.sd))


def fit_logit(names: Sequence[str], xs: list[list[float]], ys: list[int], l2: float = 1.0, iters: int = 40) -> Logit:
    n, p = len(xs), len(names)
    mean = [sum(r[j] for r in xs) / n for j in range(p)]
    sd = [max(1e-9, math.sqrt(sum((r[j] - mean[j]) ** 2 for r in xs) / n)) for j in range(p)]
    zs = [[1.0] + [(r[j] - mean[j]) / sd[j] for j in range(p)] for r in xs]
    k = p + 1
    beta = [logit(sum(ys) / n)] + [0.0] * p
    for _ in range(iters):
        g = [0.0] * k
        h = [[0.0] * k for _ in range(k)]
        for z, y in zip(zs, ys):
            pr = sigmoid(sum(b * v for b, v in zip(beta, z)))
            w, res = pr * (1 - pr), y - pr
            for i in range(k):
                zi = z[i]
                g[i] += res * zi
                wzi, hi = w * zi, h[i]
                for j in range(i, k):
                    hi[j] += wzi * z[j]
        for i in range(k):
            for j in range(i):
                h[i][j] = h[j][i]
        for i in range(1, k):
            g[i] -= l2 * beta[i]
            h[i][i] += l2
        step = solve(h, g)
        beta = [b + s for b, s in zip(beta, step)]
        if max(abs(s) for s in step) < 1e-7:
            break
    return Logit(tuple(names), tuple(mean), tuple(sd), tuple(beta))


def auc(scores: Sequence[float], ys: Sequence[int]) -> float:
    pairs = sorted(zip(scores, ys))
    n1 = sum(ys)
    n0 = len(ys) - n1
    if not n1 or not n0:
        return float("nan")
    rank_sum, i = 0.0, 0
    while i < len(pairs):
        j = i
        while j < len(pairs) and pairs[j][0] == pairs[i][0]:
            j += 1
        avg = (i + j + 1) / 2
        rank_sum += avg * sum(1 for t in range(i, j) if pairs[t][1])
        i = j
    return (rank_sum - n1 * (n1 + 1) / 2) / (n1 * n0)


def logloss(ps: Sequence[float], ys: Sequence[int]) -> float:
    return -sum(math.log(max(p, 1e-9)) if y else math.log(max(1 - p, 1e-9)) for p, y in zip(ps, ys)) / len(ys)


def brier(ps: Sequence[float], ys: Sequence[int]) -> float:
    return sum((p - y) ** 2 for p, y in zip(ps, ys)) / len(ys)


def calibration_line(ps: Sequence[float], ys: Sequence[int]) -> tuple[float, float]:
    """(intercept, slope) of logit P(y) = a + b logit(p) on held-out data: slope 1, intercept 0 is perfect."""
    a, b = 0.0, 1.0
    xs = [logit(p) for p in ps]
    for _ in range(50):
        g0 = g1 = h00 = h01 = h11 = 0.0
        for x, y in zip(xs, ys):
            pr = sigmoid(a + b * x)
            w, r = pr * (1 - pr), y - pr
            g0 += r
            g1 += r * x
            h00 += w
            h01 += w * x
            h11 += w * x * x
        det = h00 * h11 - h01 * h01
        da, db = (h11 * g0 - h01 * g1) / det, (h00 * g1 - h01 * g0) / det
        a, b = a + da, b + db
        if abs(da) + abs(db) < 1e-9:
            break
    return a, b


def bins(ps: Sequence[float], ys: Sequence[int], edges: Sequence[float]) -> list[dict]:
    out = []
    for lo, hi in zip(edges, edges[1:]):
        sel = [(p, y) for p, y in zip(ps, ys) if lo <= p < hi]
        if sel:
            out.append({"bin": f"{lo:.2f}-{hi:.2f}", "n": len(sel), "pred": sum(p for p, _ in sel) / len(sel),
                        "obs": sum(y for _, y in sel) / len(sel)})
    return out


Feature = Callable[[dict, dict], float]
