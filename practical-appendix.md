# Practical Appendix: Estimating Variability from Percentiles

Up to this point, we’ve argued that **latency variance is expected** and that queueing delay is driven by **utilization multiplied by variability**.

That argument only becomes operational once we can estimate the inputs, and in production, this is where things get uncomfortable.

In real systems, we rarely observe full service-time distributions. What we usually have are **percentiles** (p50, p95, p99) exported by telemetry systems. Turning those into something usable for queueing analysis requires care, humility, and explicit assumptions.

## A Common Notation Trap: $C_s$ vs. $C_s^2$

The coefficient of variation of service time $S$ is defined as:

$$
C_s = \frac{\sigma}{\mu}
$$

where $\mu = E[S]$ is the mean service time and $\sigma = \sqrt{\mathrm{Var}(S)}$ is the standard deviation.  

Kingman’s formula, however, uses the **squared** coefficient of variation:

$$
C_s^2 = \frac{\mathrm{Var}(S)}{E[S]^2} = \left(\frac{\sigma}{\mu}\right)^2
$$

This is not a cosmetic detail. Queueing delay scales with **variance**, not standard deviation. Confusing $C_s$ with $C_s^2$ systematically underestimates waiting time, often by a large factor.

## Percentiles Are Not Variance

In production, percentiles are what we live with day to day. They are familiar, operationally useful, and often the only thing we can easily compare across services. But they are still a thin slice of the distribution, and that slice is not enough to recover variance.

With percentiles only:

- There is **no distribution-free way** to recover variance.
- Many radically different distributions can share the same p50 and p99.
- Queueing behavior can differ by orders of magnitude.

Any attempt to estimate $C_s^2$ from percentiles therefore requires a **modeling assumption**. This is not a flaw; Kingman itself is an approximation. What matters is being explicit about the assumption instead of pretending the data is richer than it is.

## A Pragmatic Default: Log-Normal Service Times

For many RPC-style services, a log-normal distribution is a reasonable first-order model since:

- It has strictly positive support.
- It is naturally right-skewed.
- It captures moderate tail behavior without infinite variance.

Let's assume our service times exhibit a log-normal distribution and let's summarise some useful formulas:

$$
S \sim \mathrm{LogNormal}(\mu_{\ln}, \sigma_{\ln}^2)
$$

Then the following hold:

- The median is $\text{p50} = e^{\mu_{\ln}}$.
- 99th percentile is $\text{p99} = e^{\mu_{\ln} + \sigma_{\ln} z_{0.99}}, \quad z_{0.99} \approx 2.326$.

Combining these formulas and solving for $\sigma_{\ln}$ will allow us to get an estimation of $\sigma_{\ln}$ using percentiles gathered from production data:

$$
\sigma_{\ln} = \frac{\ln(\text{p99}) - \ln(\text{p50})}{2.326}
$$

## From Percentiles to $C_s^2$ (and Why This Matters)

Now that we have an estimation for $\sigma_{\ln}$ from percentiles, we can calculate an estimation of service time variability $C_s^2$ using the formulas for $E[S]$ and $\text{Var}(S)$ of a log-normal distribution (check them out in a Statistics book, or in [Wikipedia](https://en.wikipedia.org/wiki/Log-normal_distribution)):

$$
C_s^2 = e^{\sigma_{\ln}^2} - 1
$$

Two important implications of the log-normal assumption:

- **$E[S]$ is almost always larger than p50**: using p50 directly in utilization calculations underestimates $\rho$.
- **Small percentile spreads imply low variability**: a modest p99/p50 ratio often corresponds to near-deterministic service.

## A Real-World Example

Let's now ground the discussion with a concrete production example.
We observed the following percentiles in one of our production services (units of measure will be omitted in calculation from now on):

$$
\left\{
\begin{aligned}
\text{p50} &= 5\ \text{ms}\\
\text{p99} &= 9\ \text{ms}
\end{aligned}
\right.
$$

Using the formulas described in the previous sections we can estimate $\sigma_{\ln}$, $C_s^2$ and $E[S]$:

$$
\left\{
\begin{aligned}
\sigma_{\ln} &\approx 0.25 \\
C_s^2 \approx e^{0.25^2} - 1 &\approx 0.066 \\
E[S] \approx 5 \cdot e^{0.25^2 / 2} &\approx 5.16
\end{aligned}
\right.
$$

A quick log-normal sanity check:

$$
\frac{p99}{p50} = 1.8 \;\Rightarrow\; \text{low variability}
$$

This corresponds to **very low service-time variability**, much closer to deterministic or high-order Erlang behavior than to an exponential service.

If production utilization is at most 20%, and we assume roughly Poisson arrivals ($C_a^2 \approx 1$), Kingman’s approximation gives:

$$
E[W_q] \approx \frac{0.2}{1-0.2} \cdot \frac{1 + 0.066}{2} \cdot 5.16 \approx 0.69
$$

So the expected queueing delay is under 1 ms, and total latency remains close to the service time.

At 70% utilization with the same assumptions:

$$
E[W_q] \approx \frac{0.7}{1-0.7} \cdot \frac{1 + 0.066}{2} \cdot 5.16 \approx 6.41
$$

Queueing delay is now several milliseconds, and the queue starts to become visible.

At $\rho = 70\%$, the expected total request time (the expected total time in system) is almost 12 ms:

$$
E[S] + E[W_q] \approx 5.16 + 6.41 \approx 11.57
$$

The next step for the team owning this service would be running load tests and verify this model holds at different $\rho$, and iteratively adjust model and estimations. When we are comfortable with the observed behaviour, the team could consider **running this service up to $\rho \approx 70\%$ and having latency fluctuate in the range [5, 12] ms**.

A nice side-effect of this is that increasing $\rho$ three times in a CPU bounded system could result in a **reduction of provisioned CPU and related costs** of roughly three times. Obviously, this is a theoretical scenario that is accounting for no other resources being used by this service which could have other effects in how we provision this system.

**Note:** This service is CPU-bound, and results are heavily cached with a cache hit ratio close to 100%. It was expected that it had a low $C_s^2$. I do not expect most of our services to exhibit such behaviour.

## Another Real-World Example: When the Median Lies

Let's now consider a service for which we observe the following percentiles:

$$
\left\{
\begin{aligned}
\text{p50} &= 47\ \text{ms}\\
\text{p75} &= 81\ \text{ms}\\
\text{p99} &= 316\ \text{ms}
\end{aligned}
\right.
$$

At first glance, this may look *acceptable*. The median is well below 50, the 75th percentile is still under 100, and even the 99th percentile, while noticeably higher, does not look outrageous in isolation.

This is exactly the kind of distribution that routinely passes informal "latency smell tests".
And yet, from a queueing perspective, it already contains all the ingredients for instability under load.

### Step 1: Ratios Tell the First Story

Before reaching for formulas, it is useful to look at **percentile ratios**, which provide a fast intuition for variability:

$$
\frac{\text{p75}}{\text{p50}} \approx 1.72
$$

$$
\frac{\text{p99}}{\text{p50}} \approx 6.7
$$

This tells us two things:

- Variability is already present well before the extreme tail (p75 is not close to p50).
- The tail extends roughly **7 times the median**, which is enough to matter for queues.

This is not a pathological distribution, but it is also very far from deterministic.

### Step 2: Is This a "Nice" Distribution?

With three percentiles, we can now do something we could not do before: **check whether a single-shape model is plausible**.

Assuming a log-normal service-time distribution, we can independently estimate the spread parameter $\sigma_{\ln}$ from different percentile pairs:

$$
\sigma_{\ln} =
\frac{\ln(\text{p}_p) - \ln(\text{p50})}{z_p}
$$

Using:

- $z_{0.75} \approx 0.674$
- $z_{0.99} \approx 2.326$

We obtain:

- From p50 and p75:
  $$
  \sigma_{\ln} \approx 0.81
  $$
- From p50 and p99:
  $$
  \sigma_{\ln} \approx 0.82
  $$
- From p75 and p99:
  $$
  \sigma_{\ln} \approx 0.82
  $$

These estimates are remarkably consistent.
This matters: it tells us that **the tail is not being driven by a rare, separate pathology** (e.g. occasional GC pauses or retries), but by a fairly uniform, systemic variability across requests.

In other words, this service is *honestly variable*.

### Step 3: What Kingman's Law Actually Cares About

From $\sigma_{\ln}$ we can compute the quantity Kingman's law needs: the **squared coefficient of variation** of service time.

For a log-normal distribution:

$$
C_s^2 = e^{\sigma_{\ln}^2} - 1
$$

Plugging in $\sigma_{\ln} \approx 0.82$:

$$
C_s^2 \approx 0.95
$$

This number deserves attention.

- $C_s^2 = 0$: deterministic service.
- $C_s^2 = 1$: exponential service (M/M/1).
- $C_s^2 \gg 1$: heavy-tailed or pathological.

This service sits **almost exactly at exponential variability**.
That alone is enough to make queues dangerous near saturation.

**Note:** More formally, when service time is the product of many small, independent sources of jitter, its logarithm becomes a sum of random variables and converges toward a normal distribution.
The resulting service times are approximately log-normal: positive and right-skewed.
This is the reason why we started our discussion by *hypothesizing* service times were log-normally distributed.
For realistic parameters, this often puts the squared coefficient of variation near 1, meaning that from a queueing perspective the service behaves *close* to exponential, which is the natural default unless variability is actively suppressed.

Said another way:

> **This is what you get when *nothing* in the system actively smooths or shapes work.**

### Step 4: The Mean Is Not the Median

Kingman's law also depends on the *mean* service time, not the median.
For a log-normal distribution:

$$
E[S] = \text{p50} \cdot e^{\sigma_{\ln}^2 / 2}
$$

Which gives:

$$
E[S] \approx 65.6
$$

This is a crucial correction:

- Median: $\text{p50} = 47$ ms.  
- Mean: $\mu \approx 66$ ms.  

If utilization is computed using the median, as is often done implicitly, **$\rho$ is understated by ~40%**.
This error compounds brutally once queues form.

### Step 5: What This Implies for Queueing Delay

Assuming arrival variability is roughly Poisson-like at the relevant timescale ($C_a^2 \approx 1$), Kingman’s approximation becomes:

$$
\begin{aligned}
E[W_q] &\approx \frac{\rho}{1-\rho} \cdot \frac{1 + 0.95}{2} \cdot 65.6\\
       &\approx 0.98 \cdot \frac{\rho}{1-\rho} \cdot 65.6
\end{aligned}
$$

Even without extreme utilization, waiting time grows rapidly:

- $\rho = 0.6 \Rightarrow E[W_q] \approx 96$
- $\rho = 0.7 \Rightarrow E[W_q] \approx 150$
- $\rho = 0.8 \Rightarrow E[W_q] \approx 256$
- $\rho = 0.9 \Rightarrow E[W_q] \approx 575$

At this point, **queueing delay dominates total latency**, even though the raw service-time percentiles looked "reasonable".

### The Deceptive Comfort of the Median

This example illustrates a recurring failure mode in real systems:

> *The median looks fine.  
> The service looks healthy.  
> And yet the system collapses under load.*

Nothing mysterious is happening.

- Variability is moderate but real.
- The mean is substantially higher than the median.
- Utilization creeps up.
- Kingman’s law $\rho/(1-\rho)$ term does the rest.

This is not an edge case.
This is what "normal" variability looks like in production services.

### Takeaway

You do not need extreme tails for queues to hurt you.
You only need variability plus load.

Percentiles already encode this information, but only if we read them through the lens of queueing theory, rather than as isolated SLO artifacts.

## Arrival Variability: Why $C_a^2 \approx 1$ Is Usually Optimistic

In the previous back-of-the-envelope calculations, we implicitly assumed that inter-arrival times were roughly Poisson, i.e.:

$$
C_a^2 \approx 1
$$

This is a convenient baseline. It is also, in most real systems, **optimistic**.

Poisson arrivals correspond to a world in which requests arrive independently, smoothly, and without coordination. Very few production systems behave this way once they are under any meaningful load.

### Why Real Traffic Is Rarely Poisson

In practice, arrivals are shaped by multiple reinforcing mechanisms:

- **User synchronization**: humans react to the same events, refresh the same pages, and click the same buttons at roughly the same time.
- **Fan-out and aggregation**: one upstream request often fans out into many downstream requests, creating correlated bursts.
- **Retries and timeouts**: when latency increases, retries inject *additional* load precisely when the system is least able to absorb it.
- **Cron jobs and background work**: periodic tasks align in time, creating predictable spikes.
- **Autoscaling and cold starts**: scaling events change concurrency in steps, not smoothly.

Each of these effects increases **burstiness**, not just average rate.

### The Queueing Consequence of Burstiness

From Kingman’s perspective, burstiness enters through $C_a^2$:

$$
E[W_q] \;\approx\;
\frac{\rho}{1-\rho}
\cdot
\frac{C_a^2 + C_s^2}{2}
\cdot
E[S]
$$

If service-time variability is already close to exponential ($C_s^2 \approx 1$), then any increase in $C_a^2$ directly multiplies waiting time.

For example:

- If $C_a^2 = 1$ (Poisson), the variability multiplier is:
  $$
  \frac{1 + 1}{2} = 1
  $$
- If $C_a^2 = 4$ (moderate burstiness), it becomes:
  $$
  \frac{4 + 1}{2} = 2.5
  $$

Nothing else changes. The system simply waits **2.5 times longer**.

### Why This Shows Up as "Sudden" Failure

This is why systems often appear stable up to a point and then fail abruptly:

- As utilization increases, queues form.
- Queues increase latency.
- Latency triggers retries and synchronization.
- Retries increase burstiness.
- Burstiness increases $C_a^2$.
- Higher $C_a^2$ further amplifies queueing delay.

The feedback loop is multiplicative, not additive.
From the outside, it looks like a step function.  
From the inside, it is entirely predictable.

### Why Arrival Variability Is Harder to See Than Service Variability

Service-time variability leaves a clear fingerprint in percentiles. Arrival variability does not. Dashboards typically show:

- Request rate.
- Latency percentiles.
- Error rates.

They rarely show:

- Inter-arrival distributions.
- Burstiness at sub-second scales.
- Correlation across clients or tiers.

As a result, $C_a^2$ is often **invisible until it hurts**.

### Practical Implication

When doing queueing analysis from production telemetry:

> Assume $C_a^2 > 1$ unless you have strong evidence otherwise.

This is not pessimism; it is realism.

If your system behaves well even with $C_a^2 \gg 1$, it will behave extremely well when traffic is smooth. The reverse is not true.

> **Service-time variability determines how queues *can* hurt you.**
> **Arrival variability determines how often they *will*.**

Ignoring $C_a^2$ is one of the most common reasons teams underestimate how close they are to the cliff.

## Why Variability Barely Matters... Until It Suddenly Does

Kingman’s structure explains a common operational surprise:

- At low utilization, variability barely shows up.
- Near saturation, *even modest variability dominates latency*.

The amplification term:

$$
\frac{\rho}{1-\rho}
$$

does not forgive optimism. As utilization rises, variance that was previously invisible becomes decisive.

This is why systems often appear healthy... until they very abruptly are not.

## Telemetry Caveats (Datadog and Similar Systems)

When estimating variability from production percentiles, several caveats apply:

- **Aggregated percentiles are not per-request percentiles**: host-level percentiles aggregated across instances compress tails.
- **Time-windowing smooths burstiness**: rolling windows hide short-term correlation and inflate apparent regularity.
- **Timeouts and clipping truncate tails**: hard cutoffs bias variance downward.
- **Cross-instance mixing masks heterogeneity**: fast and slow instances average out, while queues still experience the full variance.

As a result, percentile-derived $C_s^2$ values should be treated as **lower bounds**, not precise measurements.

## Practical Guidance

- Percentiles alone are insufficient: assumptions must be explicit.
- Log-normal service times are a defensible default when data is sparse.
- Always estimate $E[S]$, not just the median (p50).
- Always estimate $C_s^2$, not just utilization $\rho$.
- One additional percentile (p90 or p95) dramatically improves confidence.

## Key Takeaway

> **Latency tails hurt you indirectly: through variability, and variability hurts you through queues.**

The hardest part of applying queueing theory in production is not the math.  
It is being honest about what our telemetry does, and does not, tell us.
