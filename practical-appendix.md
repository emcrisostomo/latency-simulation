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

## A real-world example

We observed the following percentiles in one of our production services:

$$
\left\{
\begin{aligned}
p50 &= 5 \\
p99 &= 9
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

## Why Variability Barely Matters... Until It Suddenly Does

Kingman’s structure explains a common operational surprise:

- At low utilization, variability barely shows up
- Near saturation, *even modest variability dominates latency*

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
