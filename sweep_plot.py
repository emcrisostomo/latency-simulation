#!/usr/bin/env python3
"""
Sweep rho and plot latency percentiles using the queue_sim.py discrete-event simulator.

Requires:
  - queue_sim.py in same directory (the simulator you already have)
  - matplotlib

Examples:
  python sweep_plot.py --dist mixture --mean-ms 10 --k 1 --n 200000 --out sweep_mixture_k1.png
  python sweep_plot.py --dist lognormal --lognorm-sigma 1.2 --out sweep_lognorm.png
  python sweep_plot.py --dist const --out sweep_const.png
"""

from __future__ import annotations

import argparse
import csv
import math
import random
from dataclasses import dataclass
from typing import List, Dict

import matplotlib.pyplot as plt

# Import from your simulator file
from queue_sim import service_sampler, simulate_mgk, summarize


@dataclass
class Point:
    rho: float
    p50_ms: float
    p95_ms: float
    p99_ms: float
    p999_ms: float
    mean_ms: float
    mean_q_ms: float


def frange(start: float, stop: float, step: float) -> List[float]:
    vals = []
    x = start
    # avoid floating drift making us miss stop
    while x <= stop + 1e-12:
        vals.append(round(x, 6))
        x += step
    return vals


def run_sweep(args) -> List[Point]:
    rng = random.Random(args.seed)
    mean_s = args.mean_ms / 1000.0

    rhos = frange(args.rho_min, args.rho_max, args.rho_step)
    points: List[Point] = []

    # Build the service sampler once; it uses rng, which advances as we sample.
    sample_svc, _ = service_sampler(
        dist=args.dist,
        mean_s=mean_s,
        rng=rng,
        lognorm_sigma=args.lognorm_sigma,
        mix_p=args.mix_p,
        slow_mult=args.slow_mult,
    )

    for rho in rhos:
        lam = rho * args.k / mean_s  # rho = lambda * E[S] / k

        lat_s, q_s, s_s = simulate_mgk(
            k=args.k,
            n=args.n,
            lam=lam,
            sample_service=sample_svc,
            rng=rng,
        )

        summ = summarize(
            lat_s, q_s, s_s,
            k=args.k,
            n=args.n,
            mean_s=mean_s,
            lam=lam,
            rho=rho,
            dist=args.dist,
        )

        points.append(
            Point(
                rho=rho,
                p50_ms=summ.p50_ms,
                p95_ms=summ.p95_ms,
                p99_ms=summ.p99_ms,
                p999_ms=summ.p999_ms,
                mean_ms=summ.mean_latency_ms,
                mean_q_ms=summ.mean_queue_ms,
            )
        )

        if args.verbose:
            print(
                f"rho={rho:.3f} p50={summ.p50_ms:.2f} p95={summ.p95_ms:.2f} "
                f"p99={summ.p99_ms:.2f} p999={summ.p999_ms:.2f} mean={summ.mean_latency_ms:.2f}"
            )

    return points


def write_csv(path: str, points: List[Point], meta: Dict[str, str]) -> None:
    with open(path, "w", newline="") as f:
        w = csv.writer(f)
        # metadata header (easy to keep provenance)
        for k, v in meta.items():
            w.writerow([f"# {k}={v}"])
        w.writerow(["rho", "p50_ms", "p95_ms", "p99_ms", "p999_ms", "mean_ms", "mean_queue_ms"])
        for p in points:
            w.writerow([p.rho, p.p50_ms, p.p95_ms, p.p99_ms, p.p999_ms, p.mean_ms, p.mean_q_ms])


def plot(points: List[Point], title: str, out_path: str) -> None:
    xs = [p.rho for p in points]
    p50 = [p.p50_ms for p in points]
    p95 = [p.p95_ms for p in points]
    p99 = [p.p99_ms for p in points]
    p999 = [p.p999_ms for p in points]

    plt.figure()
    plt.plot(xs, p50, label="p50")
    plt.plot(xs, p95, label="p95")
    plt.plot(xs, p99, label="p99")
    plt.plot(xs, p999, label="p99.9")
    plt.xlabel("utilization ρ")
    plt.ylabel("latency (ms)")
    plt.title(title)
    plt.grid(True)
    plt.legend()
    plt.tight_layout()
    plt.savefig(out_path, dpi=160)
    print(f"Wrote plot to {out_path}")


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--k", type=int, default=1)
    ap.add_argument("--n", type=int, default=200_000)
    ap.add_argument("--mean-ms", type=float, default=10.0)

    ap.add_argument("--rho-min", type=float, default=0.20)
    ap.add_argument("--rho-max", type=float, default=0.95)
    ap.add_argument("--rho-step", type=float, default=0.05)

    ap.add_argument("--dist", type=str, default="mixture",
                    choices=["const", "exp", "lognormal", "mixture"])

    ap.add_argument("--lognorm-sigma", type=float, default=1.2)
    ap.add_argument("--mix-p", type=float, default=0.01)
    ap.add_argument("--slow-mult", type=float, default=100.0)

    ap.add_argument("--out", type=str, default="sweep.png")
    ap.add_argument("--csv", type=str, default="sweep.csv")
    ap.add_argument("--seed", type=int, default=7)
    ap.add_argument("--verbose", action="store_true")

    args = ap.parse_args()

    if not (0.0 < args.rho_min < 1.0 and 0.0 < args.rho_max < 1.0 and args.rho_min < args.rho_max):
        raise SystemExit("rho range must satisfy 0 < rho-min < rho-max < 1")
    if args.rho_step <= 0:
        raise SystemExit("rho-step must be > 0")

    points = run_sweep(args)

    meta = {
        "k": str(args.k),
        "n": str(args.n),
        "mean_ms": str(args.mean_ms),
        "dist": args.dist,
        "rho_min": str(args.rho_min),
        "rho_max": str(args.rho_max),
        "rho_step": str(args.rho_step),
        "seed": str(args.seed),
        "lognorm_sigma": str(args.lognorm_sigma),
        "mix_p": str(args.mix_p),
        "slow_mult": str(args.slow_mult),
    }
    write_csv(args.csv, points, meta)

    title = f"Sweep ρ (M/G/{args.k}), dist={args.dist}, E[S]={args.mean_ms:.1f}ms, n={args.n:,}"
    plot(points, title, args.out)
    print(f"Wrote data to {args.csv}")


if __name__ == "__main__":
    main()
