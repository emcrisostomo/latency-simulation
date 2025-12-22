#!/usr/bin/env python3
"""
Sweep rho, C_s, or retries and plot latency metrics using the queue_sim.py discrete-event simulator.

Requires:
  - queue_sim.py in same directory (the simulator you already have)
  - matplotlib

Examples:
  python sweep_plot.py --dist mixture --mean-ms 10 --k 1 --n 200000 --out sweep_mixture_k1.png
  python sweep_plot.py --dist lognormal --lognorm-sigma 1.2 --out sweep_lognorm.png
  python sweep_plot.py --dist const --out sweep_const.png
  python sweep_plot.py --sweep cs --dist lognormal --rho 0.7 --cs-min 0.5 --cs-max 2.0 --cs-step 0.1 --out sweep_cs.png
  python sweep_plot.py --sweep retries --dist const --mean-ms 10 --retry-p 0.1 --rho-min 0.2 --rho-max 0.9 --rho-step 0.05 --out sweep_retries.png
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
from queue_sim import inservice_retry_sampler, lognorm_sigma_from_cs2, service_sampler, simulate_mgk, summarize


@dataclass
class Point:
    rho: float
    cs: float
    cs2: float
    p50_ms: float
    p95_ms: float
    p99_ms: float
    p999_ms: float
    mean_ms: float
    mean_q_ms: float


@dataclass
class RetryPoint:
    rho: float
    scenario: str
    p50_ms: float
    p95_ms: float
    p99_ms: float
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


def run_rho_sweep(args) -> List[Point]:
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
                cs=math.sqrt(summ.cs2),
                p50_ms=summ.p50_ms,
                p95_ms=summ.p95_ms,
                p99_ms=summ.p99_ms,
                p999_ms=summ.p999_ms,
                mean_ms=summ.mean_latency_ms,
                mean_q_ms=summ.mean_queue_ms,
                cs2=summ.cs2,
            )
        )

        if args.verbose:
            print(
                f"rho={rho:.3f} p50={summ.p50_ms:.2f} p95={summ.p95_ms:.2f} "
                f"p99={summ.p99_ms:.2f} p999={summ.p999_ms:.2f} mean={summ.mean_latency_ms:.2f}"
            )

    return points


def run_cs_sweep(args) -> List[Point]:
    if args.dist != "lognormal":
        raise SystemExit("--sweep cs currently supports only --dist lognormal")

    rng = random.Random(args.seed)
    mean_s = args.mean_ms / 1000.0
    cs_vals = frange(args.cs_min, args.cs_max, args.cs_step)
    points: List[Point] = []

    for cs in cs_vals:
        cs2 = cs * cs
        sigma = lognorm_sigma_from_cs2(cs2)
        sample_svc, _ = service_sampler(
            dist="lognormal",
            mean_s=mean_s,
            rng=rng,
            lognorm_sigma=sigma,
            mix_p=args.mix_p,
            slow_mult=args.slow_mult,
        )
        lam = args.rho * args.k / mean_s

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
            rho=args.rho,
            dist=args.dist,
        )

        points.append(
            Point(
                rho=args.rho,
                cs=cs,
                cs2=summ.cs2,
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
                f"cs2={summ.cs2:.3f} p50={summ.p50_ms:.2f} p95={summ.p95_ms:.2f} "
                f"p99={summ.p99_ms:.2f} p999={summ.p999_ms:.2f} mean={summ.mean_latency_ms:.2f}"
            )

    return points


def run_retries_sweep(args) -> List[RetryPoint]:
    rng = random.Random(args.seed)
    mean_s = args.mean_ms / 1000.0
    rhos = frange(args.rho_min, args.rho_max, args.rho_step)

    base_sampler, _ = service_sampler(
        dist=args.dist,
        mean_s=mean_s,
        rng=rng,
        lognorm_sigma=args.lognorm_sigma,
        mix_p=args.mix_p,
        slow_mult=args.slow_mult,
    )
    inservice_sampler = inservice_retry_sampler(base_sampler, args.retry_p, rng)

    points: List[RetryPoint] = []
    retry_factor = 1.0 + args.retry_p

    for rho in rhos:
        lam_base = rho * args.k / mean_s
        rho_eff = rho * retry_factor

        # Caller-side retries: increase arrival rate.
        lat_s, q_s, s_s = simulate_mgk(
            k=args.k,
            n=args.n,
            lam=lam_base * retry_factor,
            sample_service=base_sampler,
            rng=rng,
        )
        summ = summarize(
            lat_s, q_s, s_s,
            k=args.k,
            n=args.n,
            mean_s=mean_s,
            lam=lam_base * retry_factor,
            rho=rho_eff,
            dist=args.dist,
        )
        points.append(
            RetryPoint(
                rho=rho_eff,
                scenario="caller",
                p50_ms=summ.p50_ms,
                p95_ms=summ.p95_ms,
                p99_ms=summ.p99_ms,
                mean_ms=summ.mean_latency_ms,
                mean_q_ms=summ.mean_queue_ms,
            )
        )

        # In-service retries: increase service time.
        lat_s, q_s, s_s = simulate_mgk(
            k=args.k,
            n=args.n,
            lam=lam_base,
            sample_service=inservice_sampler,
            rng=rng,
        )
        summ = summarize(
            lat_s, q_s, s_s,
            k=args.k,
            n=args.n,
            mean_s=mean_s,
            lam=lam_base,
            rho=rho_eff,
            dist=args.dist,
        )
        points.append(
            RetryPoint(
                rho=rho_eff,
                scenario="in_service",
                p50_ms=summ.p50_ms,
                p95_ms=summ.p95_ms,
                p99_ms=summ.p99_ms,
                mean_ms=summ.mean_latency_ms,
                mean_q_ms=summ.mean_queue_ms,
            )
        )

        if args.verbose:
            print(
                f"rho_eff={rho_eff:.3f} caller_p99={points[-2].p99_ms:.2f} "
                f"in_service_p99={points[-1].p99_ms:.2f}"
            )

    return points


def write_csv(path: str, points: List[Point], meta: Dict[str, str]) -> None:
    with open(path, "w", newline="") as f:
        w = csv.writer(f)
        # metadata header (easy to keep provenance)
        for k, v in meta.items():
            w.writerow([f"# {k}={v}"])
        w.writerow(["rho", "cs", "cs2", "p50_ms", "p95_ms", "p99_ms", "p999_ms", "mean_ms", "mean_queue_ms"])
        for p in points:
            w.writerow([p.rho, p.cs, p.cs2, p.p50_ms, p.p95_ms, p.p99_ms, p.p999_ms, p.mean_ms, p.mean_q_ms])


def plot_rho(points: List[Point], title: str, out_path: str) -> None:
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


def plot_cs(points: List[Point], title: str, out_path: str) -> None:
    xs = [p.cs for p in points]
    mean_q = [p.mean_q_ms for p in points]

    plt.figure()
    plt.plot(xs, mean_q, label="mean queue delay")
    plt.xlabel("service-time variability C_s")
    plt.ylabel("mean queue delay (ms)")
    plt.title(title)
    plt.grid(True)
    plt.legend()
    plt.tight_layout()
    plt.savefig(out_path, dpi=160)
    print(f"Wrote plot to {out_path}")


def write_csv_retries(path: str, points: List[RetryPoint], meta: Dict[str, str]) -> None:
    with open(path, "w", newline="") as f:
        w = csv.writer(f)
        for k, v in meta.items():
            w.writerow([f"# {k}={v}"])
        w.writerow(["rho", "scenario", "p50_ms", "p95_ms", "p99_ms", "mean_ms", "mean_queue_ms"])
        for p in points:
            w.writerow([p.rho, p.scenario, p.p50_ms, p.p95_ms, p.p99_ms, p.mean_ms, p.mean_q_ms])


def plot_retries(points: List[RetryPoint], title: str, out_path: str) -> None:
    caller = [p for p in points if p.scenario == "caller"]
    in_service = [p for p in points if p.scenario == "in_service"]

    caller.sort(key=lambda p: p.rho)
    in_service.sort(key=lambda p: p.rho)

    plt.figure()
    plt.plot([p.rho for p in caller], [p.p99_ms for p in caller], label="caller-side retries")
    plt.plot([p.rho for p in in_service], [p.p99_ms for p in in_service], label="in-service retries")
    plt.xlabel("utilization ρ")
    plt.ylabel("p99 latency (ms)")
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

    ap.add_argument("--sweep", type=str, default="rho", choices=["rho", "cs", "retries"])

    ap.add_argument("--rho-min", type=float, default=0.20)
    ap.add_argument("--rho-max", type=float, default=0.95)
    ap.add_argument("--rho-step", type=float, default=0.05)
    ap.add_argument("--rho", type=float, default=0.70, help="fixed rho for --sweep cs2")

    ap.add_argument("--cs-min", type=float, default=0.5)
    ap.add_argument("--cs-max", type=float, default=2.0)
    ap.add_argument("--cs-step", type=float, default=0.1)

    ap.add_argument("--retry-p", type=float, default=0.1)

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

    if args.sweep == "rho":
        if not (0.0 < args.rho_min < 1.0 and 0.0 < args.rho_max < 1.0 and args.rho_min < args.rho_max):
            raise SystemExit("rho range must satisfy 0 < rho-min < rho-max < 1")
        if args.rho_step <= 0:
            raise SystemExit("rho-step must be > 0")
    elif args.sweep == "cs":
        if not (0.0 < args.rho < 1.0):
            raise SystemExit("--rho must be in (0,1) for --sweep cs")
        if not (args.cs_min >= 0.0 and args.cs_max > args.cs_min):
            raise SystemExit("cs range must satisfy 0 <= cs-min < cs-max")
        if args.cs_step <= 0:
            raise SystemExit("cs-step must be > 0")
    else:
        if not (0.0 <= args.retry_p < 1.0):
            raise SystemExit("--retry-p must be in [0,1)")
        if not (0.0 < args.rho_min < 1.0 and 0.0 < args.rho_max < 1.0 and args.rho_min <= args.rho_max):
            raise SystemExit("rho range must satisfy 0 < rho-min <= rho-max < 1")
        max_rho = 1.0 / (1.0 + args.retry_p)
        if args.rho_max > max_rho:
            raise SystemExit(
                f"rho-max must be <= {max_rho:.3f} for retry_p={args.retry_p:.3f} "
                f"so that rho_eff stays < 1"
            )
        if args.rho_step <= 0:
            raise SystemExit("rho-step must be > 0")

    if args.sweep == "rho":
        points = run_rho_sweep(args)
    elif args.sweep == "cs":
        points = run_cs_sweep(args)
    else:
        points = run_retries_sweep(args)

    meta = {
        "k": str(args.k),
        "n": str(args.n),
        "mean_ms": str(args.mean_ms),
        "dist": args.dist,
        "sweep": args.sweep,
        "rho_min": str(args.rho_min),
        "rho_max": str(args.rho_max),
        "rho_step": str(args.rho_step),
        "rho": str(args.rho),
        "cs_min": str(args.cs_min),
        "cs_max": str(args.cs_max),
        "cs_step": str(args.cs_step),
        "retry_p": str(args.retry_p),
        "seed": str(args.seed),
        "lognorm_sigma": str(args.lognorm_sigma),
        "mix_p": str(args.mix_p),
        "slow_mult": str(args.slow_mult),
    }

    if args.sweep == "rho":
        write_csv(args.csv, points, meta)
        title = f"Sweep ρ (M/G/{args.k}), dist={args.dist}, E[S]={args.mean_ms:.1f}ms, n={args.n:,}"
        plot_rho(points, title, args.out)
    elif args.sweep == "cs":
        write_csv(args.csv, points, meta)
        title = f"Sweep C_s (M/G/{args.k}), rho={args.rho:.2f}, dist={args.dist}, E[S]={args.mean_ms:.1f}ms, n={args.n:,}"
        plot_cs(points, title, args.out)
    else:
        write_csv_retries(args.csv, points, meta)
        title = f"Retries vs ρ (M/G/{args.k}), retry_p={args.retry_p:.2f}, E[S]={args.mean_ms:.1f}ms, n={args.n:,}"
        plot_retries(points, title, args.out)
    print(f"Wrote data to {args.csv}")


if __name__ == "__main__":
    main()
