# README.md

This repository contains **small, executable simulations** designed to make a single point painfully clear:

> **Latency variance is not a bug.  
> It is a mathematical consequence of utilization and service-time variability.**

The code demonstrates, empirically and visually, why tail latency explodes as systems approach saturation, even when *average service time stays constant*.

---

## What this repository is (and is not)

**This is not:**

- A performance benchmarking tool.
- A production-ready load tester.
- A realistic model of any specific system.

**This *is*:**

- A didactic simulator of classical queueing systems.
- A way to make queueing theory *felt*, not just cited.
- A companion to blog posts and design discussions about latency, capacity, and risk.

---

## Conceptual model

All simulations are variations of:

- **Poisson arrivals** (open-loop traffic).
- **FIFO queue**.
- **k identical servers**.
- **Configurable service-time distributions**.

This corresponds to an **M/G/k** queue in classical queueing theory.

The key parameters are:

| Symbol    | Meaning                            |
| --------- | ---------------------------------- |
| $\lambda$ | Arrival rate (requests per second) |
| $S$       | Service time random variable       |
| $E[S]$    | Mean service time                  |
| $k$       | Number of workers / servers        |
| $\rho$    | Utilization                        |

Utilization is defined as:

$$
\rho = \frac{\lambda \cdot E[S]}{k}
$$

**Important:**  
In these simulations, *utilization is not tuned indirectly*.  
You choose $\rho$, and the simulator derives $\lambda$ from it.

---

## Why utilization is the control variable

A central thesis of this repo is:

> **Utilization is not a tuning parameter.  
> It is an accounting identity.**

If:

- requests arrive at rate $\lambda$
- each request requires $E[S]$ seconds of work
- you have $k$ workers

then utilization is fixed by physics:

$$
\rho = \lambda E[S] / k
$$

Everything else, queueing, waiting time, tail latency, follows.

---

## Discrete-event simulation

The Python simulator is a **discrete-event simulation**, not a real service.

For each request:

1. An arrival time is generated from an exponential inter-arrival distribution.
2. A service time is sampled from the chosen distribution.
3. The request is assigned to the next available server.
4. Queueing delay, service time, and total latency are recorded.

This gives clean, reproducible results without OS noise, GC, or scheduler artifacts.

---

## Supported service-time distributions

All distributions are parameterized to have **the same mean service time** $E[S]$.  
Any difference in latency comes purely from **variance and tail behavior**.

### 1. Constant (`const`)

Deterministic service time.

$$
S = E[S]
$$

- Zero variance
- Best possible case
- Unrealistic, but a useful baseline

---

### 2. Exponential (`exp`)

Memoryless service time.

$$
S \sim \text{Exponential}(1/E[S])
$$

- Coefficient of variation $C_s^2 = 1$
- Classic M/M/k model
- Often used implicitly (and incorrectly) in intuition

---

### 3. Lognormal (`lognormal`)

Heavy-tailed service time.

$$
S \sim \text{LogNormal}(\mu, \sigma)
$$

- Mean preserved by construction
- Variance controlled via `sigma`
- Models multiplicative slowdowns (serialization, retries, amplification)

---

### 4. Mixture (`mixture`)

A **two-point mixture distribution**:

$$
S =
\begin{cases}
S_{\text{fast}} & \text{with probability } 1 - p \\
S_{\text{slow}} & \text{with probability } p
\end{cases}
$$

Where:

- $S_{\text{slow}} = S_{\text{fast}} \times \text{slow\\_mult}$
- $S_{\text{fast}}$ is chosen so that $E[S]$ is preserved

This models the most common real-world pattern:

> **99% of requests are fast,  
> 1% are catastrophically slow,  
> and the average lies to you.**

Examples include:

- cache misses
- cold starts
- GC pauses
- page faults
- leader elections
- network retries

---

## Why variance matters (the theory)

Kingman’s approximation for an M/G/1 queue:

$$
E[W_q] \approx
\frac{\rho}{1 - \rho}
\cdot
\frac{1 + C_s^2}{2}
\cdot
E[S]
$$

Where:

$$
C_s^2 = \frac{\mathrm{Var}(S)}{E[S]^2}
$$

This equation explains almost everything you observe in production:

- latency grows non-linearly with utilization
- high-variance workloads suffer earlier
- tail latency explodes *before* CPU hits 100%

The simulations in this repo are simply this equation, made visible.

---

## What the plots show

The sweep plots:

- x-axis: utilization $\rho$
- y-axis: latency (p50, p95, p99, p99.9)

What you should notice:

- p50 remains deceptively flat
- p95 bends upward
- p99 and p99.9 diverge violently as $\rho \to 1$
- higher-variance distributions blow up *earlier*

Nothing is broken.
Nothing is misconfigured.
This is how queues behave.

---

## Scripts

### `queue_sim.py`

Core discrete-event simulator.

- M/G/k queue
- configurable service distributions
- prints latency percentiles
- optional per-request CSV output

### `sweep_plot.py`

Runs parameter sweeps over utilization $\rho$.

- generates CSV data
- produces matplotlib plots suitable for blog posts
- optional log-scale to make the cliff undeniable

---

## How to use this repo

Typical workflow:

1. Pick a distribution
2. Sweep utilization from ~0.2 to ~0.95
3. Plot latency percentiles
4. Compare shapes, not averages

This is most effective when paired with a real system discussion:

- thread pools
- connection pools
- rate limits
- retries
- autoscaling delays

---

## Key takeaway

> **Latency variance is not a sign of bad engineering.  
> It is a sign of finite resources under stochastic load.**

If a system operates close to saturation,  
**tail latency is not optional** — it is inevitable.
