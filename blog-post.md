# Latency Variance Is Not a Bug  

## It’s the Price of Utilization

There is a persistent belief in software engineering that **latency variance is a sign of poor engineering**.

When latency becomes noisy, when p95 or p99 moves around, the reflex is often:

> “Something is wrong. We need to lower utilization.”

This belief has quietly pushed many teams to operate production systems at **10–20% CPU utilization**, forever afraid of the queue.

This post argues the opposite:

> **Latency variance is not a defect.  
> It is a mathematical consequence of utilization.**

And not only is it expected — it is **predictable, quantifiable, and plannable**.

---

## Utilization Is Not a Tuning Knob

There is a subtle but important misunderstanding in how we talk about utilization.

Utilization is not a parameter you tune.  
It is an **accounting identity**.

If your system:

- receives work at rate **λ** (requests per second)
- requires **E[S]** CPU-seconds per request

then utilization is:

$$
\rho = \lambda E[S]
$$

This is not a choice.  
It is a consequence.

You don’t “decide” to run at 65% CPU any more than you decide gravity applies today.  
If load increases or service time grows, utilization increases. Full stop.

The real choice engineers have is not *whether* there is utilization, but:

- whether that utilization is **safe**
- or **dangerous**

Safe utilization means short queues and predictable latency.  
Dangerous utilization means long queues and exploding tail latency.

The difference is **variance**, not virtue.

---

## Why Variance Shows Up Even in Healthy Systems

Here is the uncomfortable truth:

> **Any system that shares a finite resource will exhibit queueing delay.**

If a system:

- shares CPU, threads, or connections
- runs at non-zero utilization
- experiences non-zero variability

then queues are inevitable.

This is not a software problem.  
It is queueing theory.

And the most useful tool we have to reason about it is **Kingman’s approximation**.

---

## Kingman’s Formula (The One You Actually Need)

Kingman’s approximation estimates the **mean waiting time in queue** for a very general class of systems (GI/G/1):

$$
E[W_q]
\;\approx\;
\frac{\rho}{1 - \rho}
\cdot
\frac{c_a^2 + c_s^2}{2}
\cdot
E[S]
$$

Where:

- $\rho = \lambda E[SS]$ is utilization
- $E[S]$ is mean service time
- $c_a^2$ is arrival-time variability
- $c_s^2$ is service-time variability

Kingman's formula in an _approximation_ that is asymptotically exact when $\rho\rightarrow 1$ and it applies to the GI/G/1 queue:

| Component | Meaning                                 |
|-----------|-----------------------------------------|
| GI        | General inter-arrival time distribution |
| G         | General service time distribution       |

In plain English, this is the queue length in a system with a single server where interarrival times have a general (meaning **arbitrary**) distribution and service times have a (different) general distribution.

So, this model is valid for:

* **Any arrival distribution:** Poisson, bursty, scheduled, etc.
* **Any service distribution:** constant, log-normal, normal, heavy-tailed, etc.

It is empirically _very accurate_ across a wide range of systems:

- CPUs
- thread pools
- database connections
- message consumers

In other words: **most backend bottlenecks**.

> This generality is **exactly** why it’s powerful for software systems.

---

## Why is it so useful to software engineers?

The reality of software systems is not so orderly and disciplined, and most production systems are not M/M/1:

* Requests are **bursty**: customers are noisy, scheduled batch jobs start, retries happen, GC pauses.
* Service times have a **high variance**: cache hits vs. misses, service time highly influence by the size of the data set being processed, I/O activity, slow downstreams.

Kingman's law gives us a way to reason about **latency inflation** without pretending the our world is exponential.

But what does this mean?

_Latency inflation_ is the phenomenon where **observed latency** (by the customer) is much larger than the service time.  The gap between the two is latency inflation caused by _queueing_.

> Latency inflation is not about slow code: it's about **waiting** before our code actually runs.

Pretending the world is exponential means pretending our intuitions are correct, when they are based on a model which is too simple:

- "But... average latency should scale linearly!"
- "But... the CPU is not saturated, queues shouldn't be forming!"
- "But... this variance is too high, something is broken!"

This is _bad_ because it leads to:

- **Overconfidence:** "Our average latency is low, we're fine!"
- **Overcompensation:** "Latency variance is scary, let's scale up! (and keep utilisation low)"

This _works_ (sort of)... at a huge cost, and little understanding.

Kingman's law gives us a third path: **quantitative realism**.

---

## What Kingman's law really says, in plain English

This is dense, I know. Let's try to look at the formula under a different light:

$$
\text{Queueing delay} \propto \frac{\rho}{1 - \rho} \cdot (\text{arrival variability} + \text{service variability}) \cdot \text{average service time}
$$

There are three terms.
Three **unavoidable facts**.
Three levers.
And only **one** of them is under direct operational control.

1. **Utilization creates non-linear latency increase**: as $\rho\rightarrow 1$, waiting time _explodes_. Even with zero variance.
2. **Variance amplifies waiting times**: variance doesn't _cause_ queues, variance _magnifies_ queues when utilization increases.
3. **Latency variance is not a bug**: it's a _mathematical consequence_ of shared resources and utilization. You cannot remove variance without either:

    * Overprovisioning
    * Operating a system where arrivals and service times are deterministic (which is unrealistic).
    * Eliminating shared resources (which is also unrealistic).

Guess which one we're choosing?

---

## The Curve We All Rediscover the Hard Way

The most important term in Kingman’s formula is this one:

$$
\frac{\rho}{1 - \rho}
$$

It grows slowly… until it doesn’t.

| Utilization | Queueing factor |
|-------------|-----------------|
| 0.30        | 0.43            |
| 0.50        | 1.00            |
| 0.65        | 1.86            |
| 0.75        | 3.00            |
| 0.85        | 5.67            |
| 0.90        | 9.00            |

This is why:

- 60 → 70% feels fine
- 70 → 80% feels scary
- 80 → 85% feels like a cliff

Nothing broke.  
**The math just became visible.**

---

## “But Our p99 Exploded”

Yes. Of course it did.

Kingman estimates the *mean*, but queueing does not politely stay in the mean.

Queueing:

- stretches the right tail
- amplifies bursts
- punishes long service times

This is why:

- p99 degrades before p50 looks bad
- tail latency becomes noisy under load
- systems “feel flaky” long before averages change

This is not a failure of the model.  
It is exactly what the model predicts.

> **Tail latency is a utilization problem, not a mystery.**

---

## Numeric Example: The Cost of Utilization

Let’s put numbers on this.

Assume a single bottleneck (one CPU core, one DB connection, one worker).

From production measurements:

- Mean service time: **E[S] = 20 ms**
- Standard deviation: **σ = 20 ms**

So service-time variability is:

$$
c_s^2
=
\left(\frac{20}{20}\right)^2
=
1
$$

Arrivals are bursty (very normal in real systems):

$$
c_a^2 = 2.25
$$

### What happens as utilization increases?

| Utilization | Throughput (req/s) | Mean queue wait | Mean total latency |
|-------------|--------------------|-----------------|--------------------|
| 0.20        | 10.0               | 8.1 ms          | 28.1 ms            |
| 0.50        | 25.0               | 32.5 ms         | 52.5 ms            |
| 0.70        | 35.0               | 75.8 ms         | 95.8 ms            |
| 0.80        | 40.0               | 130.0 ms        | 150.0 ms           |
| 0.85        | 42.5               | 184.2 ms        | 204.2 ms           |

At 80% utilization, the *queue* dominates the latency.

Nothing is broken.  
This is the expected cost of efficiency.

---

## Same Load, Same Utilization — Different Variance

At 70% utilization:

| Service variability $c_s^2$ | Interpretation         | Mean total latency |
|-----------------------------|------------------------|--------------------|
| 0.25                        | Stable service         | 78 ms              |
| 1.00                        | Typical mixed workload | 96 ms              |
| 4.00                        | Heavy-tailed service   | 166 ms             |

Variance is not evil.  
But it is not free.

---

## Retries: Variance Multipliers in Disguise, and where they happen matters

Retries feel safe. Mathematically, they are **gasoline**.
When engineers talk about "retries", they often lump together **two very different mechanisms** that affect queueing in different ways.

### Caller-side retries (new arrivals)

When a client times out and sends another request, the system observes a **new arrival**.

From the queue’s perspective, this means:

- The arrival rate $\lambda$ increases.
- Arrivals become burstier
- Arrival-time variance $c_a^2$ grows.

Even if each client’s retry logic is deterministic, retries often **synchronize at the system level**: many callers observe the same slowdown and retry **at the same time**. This correlation is what makes retry storms so destructive.

This is why exponential backoff and jitter are **not** "nice to have". They are mechanisms to **break correlation** and keep arrival variability bounded.

### In-service retries (longer service times)

When a service retries work *inside* the request handling path, no new arrival is created, but the **service time increases**.

From the queue’s perspective, this means:

- The mean service time $E[S]$ grows.
- The service-time variance $c_s^2$ widens.
- Long requests block everything behind them.

This manifests as heavier tails and p99 inflation even when arrivals are smooth.

### Where determinism fits in

Determinism does not eliminate cost: it **bounds it**.

- Deterministic retries cap variance.
- Correlated or unbounded retries amplify it.

The key distinction is not that "retries are bad", but **where the retry occurs and how correlated it is**.

A useful rule of thumb is the following:

> **Retries outside the queue attack arrivals.  
> Retries inside the queue stretch the tail.**

Kingman's law does not forbid us to use retries.  
It simply tells you **which bill they add to**.

---

## Thread Pools vs Async: Physics Still Applies

Async systems don’t eliminate queueing.

They relocate it.

- Thread pools have visible queues
- Async systems have implicit queues (buffers, schedulers, event loops)

Kingman's law applies equally to:

- Blocking threads.
- Asynchronous pipelines.
- Coroutines.
- Virtual threads.

If a resource is finite and shared, it queues. Full stop.

> **Async changes how you pay for waiting, not whether you pay.**

---

## Capacity Planning Without Superstition

A sane capacity-planning loop looks like this:

1. Identify the bottleneck  
2. Measure mean service time  
3. Measure arrival and service variability  
4. Pick a utilization target intentionally  
5. Decide whether the resulting latency is acceptable  

Not:

> “Let’s stay under 20% CPU.”

But:

> “At 75% utilization, expected queueing delay is 3× service time. Is that acceptable?”

That is engineering.

---

## The Cultural Shift This Enables

Once teams internalize this:

- utilization stops being scary
- variance stops being shameful
- latency becomes explainable

You move from:

> “Why is prod flaky?”

to:

> “We’re at 78% utilization with high variance. This is expected.”

That’s not lowering standards.  
That’s raising understanding.

---

## Final Thought

Latency variance is not a sign that our system is broken.

It is a sign that our system is **alive, shared, and doing useful work**.

The goal of engineering is not to eliminate variance.  
Our job is to understand it well enough that it stops surprising us.

When variance surprises you, you page people.  
When it doesn’t, you plan.

That difference is not tooling.  
It is literacy.
