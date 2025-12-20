#!/usr/bin/env python3
"""
Discrete-event queue simulator: M/G/k with Poisson arrivals.

Focus: show how utilization (rho) and service-time variability inflate tail latency.

Usage examples:
  python queue_sim.py --k 1 --mean-ms 10 --rho 0.8  --dist const     --n 200000
  python queue_sim.py --k 1 --mean-ms 10 --rho 0.8  --dist mixture   --n 200000 --mix-p 0.01 --slow-mult 100 
  python queue_sim.py --k 4 --mean-ms 10 --rho 0.85 --dist lognormal --n 300000 --lognorm-sigma 1.2  --csv out.csv
"""

from __future__ import annotations

import argparse
import csv
import math
import random
import statistics
from dataclasses import dataclass
from typing import Callable, List, Optional, Tuple


# --------------------------
# Distributions
# --------------------------

def service_sampler(
    dist: str,
    mean_s: float,
    rng: random.Random,
    lognorm_sigma: float,
    mix_p: float,
    slow_mult: float,
) -> Tuple[Callable[[], float], float]:
    """
    Returns (sampler(), expected_mean) in seconds.

    For distributions, we ensure E[S] = mean_s (within floating error).
    """
    if mean_s <= 0:
        raise ValueError("mean_s must be > 0")

    if dist == "const":
        def sample() -> float:
            return mean_s
        return sample, mean_s

    if dist == "exp":
        # Exponential with mean mean_s
        def sample() -> float:
            return rng.expovariate(1.0 / mean_s)
        return sample, mean_s

    if dist == "lognormal":
        # If X ~ LogNormal(mu, sigma), then E[X] = exp(mu + 0.5*sigma^2)
        # Choose mu such that E[X]=mean_s.
        sigma = float(lognorm_sigma)
        if sigma <= 0:
            raise ValueError("--lognorm-sigma must be > 0")
        mu = math.log(mean_s) - 0.5 * sigma * sigma

        def sample() -> float:
            return rng.lognormvariate(mu, sigma)
        return sample, mean_s

    if dist == "mixture":
        # Rare-slow mixture: with prob mix_p, slow = fast * slow_mult.
        # Choose fast so that E[S]=mean_s:
        # mean = (1-p)*fast + p*(fast*slow_mult) = fast * [(1-p) + p*slow_mult]
        p = float(mix_p)
        if not (0.0 < p < 1.0):
            raise ValueError("--mix-p must be in (0,1)")
        if slow_mult <= 1.0:
            raise ValueError("--slow-mult must be > 1")
        denom = (1.0 - p) + p * slow_mult
        fast = mean_s / denom
        slow = fast * slow_mult

        def sample() -> float:
            return slow if (rng.random() < p) else fast
        return sample, mean_s

    raise ValueError(f"Unknown dist: {dist}")


# --------------------------
# Simulator
# --------------------------

@dataclass
class Summary:
    k: int
    n: int
    mean_s: float
    lam: float
    rho: float
    dist: str
    p50_ms: float
    p95_ms: float
    p99_ms: float
    p999_ms: float
    mean_latency_ms: float
    mean_queue_ms: float
    mean_service_ms: float
    cs2: float

def percentile(sorted_values: List[float], p: float) -> float:
    """p in [0,100]. Returns linear-interpolated percentile."""
    if not sorted_values:
        return float("nan")
    if p <= 0:
        return sorted_values[0]
    if p >= 100:
        return sorted_values[-1]
    n = len(sorted_values)
    # rank in [0, n-1]
    r = (p / 100.0) * (n - 1)
    lo = int(math.floor(r))
    hi = int(math.ceil(r))
    if lo == hi:
        return sorted_values[lo]
    frac = r - lo
    return sorted_values[lo] * (1.0 - frac) + sorted_values[hi] * frac


def simulate_mgk(
    k: int,
    n: int,
    lam: float,
    sample_service: Callable[[], float],
    rng: random.Random,
) -> Tuple[List[float], List[float], List[float]]:
    """
    Simulate M/G/k with FCFS discipline via "next-free server" method.

    Returns: (latencies, queue_delays, service_times) all in seconds.

    Model:
      arrivals are generated as a Poisson process: inter-arrival ~ Exp(lam)
      each job chooses the server that becomes available earliest
      start = max(arrival, earliest_server_free_time)
      end = start + S
    """
    if k <= 0:
        raise ValueError("k must be >= 1")
    if n <= 0:
        raise ValueError("n must be >= 1")
    if lam <= 0:
        raise ValueError("lam must be > 0")

    server_free: List[float] = [0.0] * k  # time each server becomes free
    t = 0.0  # current arrival time
    latencies: List[float] = []
    qdelays: List[float] = []
    stimes: List[float] = []

    for _ in range(n):
        # next arrival
        t += rng.expovariate(lam)
        s = sample_service()
        # assign to earliest available server
        i = min(range(k), key=server_free.__getitem__)
        start = t if t >= server_free[i] else server_free[i]
        q = start - t
        end = start + s
        server_free[i] = end

        latencies.append(end - t)
        qdelays.append(q)
        stimes.append(s)

    return latencies, qdelays, stimes


def summarize(
    lat_s: List[float],
    q_s: List[float],
    s_s: List[float],
    *,
    k: int,
    n: int,
    mean_s: float,
    lam: float,
    rho: float,
    dist: str,
) -> Summary:
    lat_sorted = sorted(lat_s)
    p50 = percentile(lat_sorted, 50) * 1000.0
    p95 = percentile(lat_sorted, 95) * 1000.0
    p99 = percentile(lat_sorted, 99) * 1000.0
    p999 = percentile(lat_sorted, 99.9) * 1000.0
    mean_lat = statistics.fmean(lat_s) * 1000.0
    mean_q = statistics.fmean(q_s) * 1000.0
    mean_serv = statistics.fmean(s_s) * 1000.0

    # Service-time variability: C_s^2 = Var(S) / E[S]^2
    # Use population variance since we have a full simulated sample.
    if len(s_s) >= 2:
        var_serv = statistics.pvariance(s_s)
    else:
        var_serv = 0.0
    
    mean_serv_s = statistics.fmean(s_s) if s_s else 0.0
    cs2 = (var_serv / (mean_serv_s * mean_serv_s)) if mean_serv_s > 0 else float("nan")

    return Summary(
        k=k,
        n=n,
        mean_s=mean_s,
        lam=lam,
        rho=rho,
        dist=dist,
        p50_ms=p50,
        p95_ms=p95,
        p99_ms=p99,
        p999_ms=p999,
        mean_latency_ms=mean_lat,
        mean_queue_ms=mean_q,
        mean_service_ms=mean_serv,
        cs2=cs2,
    )


def print_summary(s: Summary) -> None:
    print("\n=== M/G/k discrete-event simulation ===")
    print(f"k={s.k}  n={s.n:,}")
    print(f"dist={s.dist}")
    print(f"E[S] target={s.mean_s*1000:.3f} ms  observed_mean_S={s.mean_service_ms:.3f} ms")
    print(f"lambda={s.lam:.3f} req/s")
    print(f"rho≈lambda*E[S]/k = {s.rho:.3f}")
    print("")
    print("Service-time variability:")
    print(f"  C_s^2 = Var(S) / E[S]^2 = {s.cs2:.6f}")
    print("")
    print("Latency percentiles (ms):")
    print(f"  p50   {s.p50_ms:.3f}")
    print(f"  p95   {s.p95_ms:.3f}")
    print(f"  p99   {s.p99_ms:.3f}")
    print(f"  p99.9 {s.p999_ms:.3f}")
    print("")
    print(f"Mean latency:      {s.mean_latency_ms:.3f} ms")
    print(f"Mean queue delay:  {s.mean_queue_ms:.3f} ms")
    print("")


def write_csv(path: str, lat_s: List[float], q_s: List[float], s_s: List[float]) -> None:
    with open(path, "w", newline="") as f:
        w = csv.writer(f)
        w.writerow(["latency_ms", "queue_ms", "service_ms"])
        for lat, q, s in zip(lat_s, q_s, s_s):
            w.writerow([lat * 1000.0, q * 1000.0, s * 1000.0])


# --------------------------
# CLI
# --------------------------

def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--k", type=int, default=1, help="number of servers/workers")
    ap.add_argument("--n", type=int, default=200_000, help="number of requests to simulate")
    ap.add_argument("--seed", type=int, default=7)

    # Parameterize by rho because it's what you want to talk about in the blog
    ap.add_argument("--rho", type=float, default=0.8, help="target utilization rho in (0,1)")
    ap.add_argument("--mean-ms", type=float, default=10.0, help="target mean service time E[S] in ms")

    ap.add_argument("--dist", type=str, default="const",
                    choices=["const", "exp", "lognormal", "mixture"])

    # lognormal
    ap.add_argument("--lognorm-sigma", type=float, default=1.0,
                    help="sigma for lognormal (higher => heavier tail)")

    # mixture
    ap.add_argument("--mix-p", type=float, default=0.01,
                    help="probability of slow request in mixture")
    ap.add_argument("--slow-mult", type=float, default=100.0,
                    help="slow service-time multiplier in mixture")

    ap.add_argument("--csv", type=str, default=None, help="optional path to write per-request samples")

    args = ap.parse_args()

    if not (0.0 < args.rho < 1.0):
        raise SystemExit("--rho must be in (0,1)")

    rng = random.Random(args.seed)

    mean_s = args.mean_ms / 1000.0
    # rho = lambda * E[S] / k  => lambda = rho * k / E[S]
    lam = args.rho * args.k / mean_s

    sample_svc, _ = service_sampler(
        dist=args.dist,
        mean_s=mean_s,
        rng=rng,
        lognorm_sigma=args.lognorm_sigma,
        mix_p=args.mix_p,
        slow_mult=args.slow_mult,
    )

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
    print_summary(summ)

    if args.csv:
        write_csv(args.csv, lat_s, q_s, s_s)
        print(f"Wrote samples to {args.csv}")


if __name__ == "__main__":
    main()
