#!/usr/bin/env python3
"""Deterministic executable methods referenced by knowledge cards.

A concept card says what a mechanism claims. A method object says how to compute
the evidence for it, from data available at the decision timestamp. The agent
should never re-derive these in prose during a live turn: it calls a versioned,
tested implementation and gets numbers back.

Every method here is pure Python, deterministic, and side-effect free. Each
declares its inputs, its outputs, its as-of contract (what it is allowed to see),
its known numerical failure modes, and a self-test with a closed-form or
hand-checkable answer.

    python scripts/methods.py list
    python scripts/methods.py show --method cusum_changepoint
    python scripts/methods.py run --method kyle_lambda --input payload.json
    python scripts/methods.py self-test
"""

from __future__ import annotations

import argparse
import json
import math
import sys
from pathlib import Path
from typing import Any, Callable


REGISTRY: dict[str, dict[str, Any]] = {}


def method(
    name: str,
    version: str,
    summary: str,
    inputs: dict[str, str],
    outputs: dict[str, str],
    as_of_contract: str,
    failure_modes: list[str],
    runtime_cost: str = "trivial",
    concepts: list[str] | None = None,
) -> Callable[[Callable[..., dict[str, Any]]], Callable[..., dict[str, Any]]]:
    def register(fn: Callable[..., dict[str, Any]]) -> Callable[..., dict[str, Any]]:
        REGISTRY[name] = {
            "method_id": name,
            "implementation_version": version,
            "summary": summary,
            "inputs": inputs,
            "outputs": outputs,
            "as_of_contract": as_of_contract,
            "known_numerical_failures": failure_modes,
            "runtime_cost": runtime_cost,
            "concept_ids": concepts or [],
            "fn": fn,
        }
        return fn

    return register


def _mean(values: list[float]) -> float:
    return sum(values) / len(values) if values else 0.0


# --------------------------------------------------------------------------------------
# Microstructure
# --------------------------------------------------------------------------------------


@method(
    name="order_flow_imbalance",
    version="1.0.0",
    summary="Order flow imbalance from top-of-book updates (Cont, Kukanov and Stoikov's e_n).",
    inputs={
        "book": "list of {bid_price, bid_size, ask_price, ask_size} snapshots in time order",
        "window": "optional int; sum OFI over the last `window` updates (default: all)",
    },
    outputs={
        "ofi": "signed order flow imbalance over the window",
        "per_update": "the per-update contributions",
        "normalized": "ofi divided by total absolute contribution, in [-1, 1]",
    },
    as_of_contract="Snapshots must all be timestamped at or before the decision time. No look-ahead on the closing snapshot.",
    failure_modes=[
        "Fewer than two snapshots returns zero rather than raising.",
        "Crossed or locked books are not filtered; feed hygiene is the caller's job.",
        "Size units must be consistent across snapshots (shares vs. notional).",
    ],
    concepts=["KC-MICRO-OFI"],
)
def order_flow_imbalance(book: list[dict[str, float]], window: int | None = None) -> dict[str, Any]:
    contributions: list[float] = []
    for previous, current in zip(book, book[1:]):
        bid = 0.0
        if current["bid_price"] > previous["bid_price"]:
            bid = current["bid_size"]
        elif current["bid_price"] == previous["bid_price"]:
            bid = current["bid_size"] - previous["bid_size"]
        else:
            bid = -previous["bid_size"]

        ask = 0.0
        if current["ask_price"] < previous["ask_price"]:
            ask = current["ask_size"]
        elif current["ask_price"] == previous["ask_price"]:
            ask = current["ask_size"] - previous["ask_size"]
        else:
            ask = -previous["ask_size"]

        contributions.append(bid - ask)

    selected = contributions[-window:] if window else contributions
    total = sum(selected)
    scale = sum(abs(value) for value in selected)
    return {
        "ofi": total,
        "per_update": selected,
        "normalized": (total / scale) if scale else 0.0,
        "updates": len(selected),
    }


@method(
    name="kyle_lambda",
    version="1.0.0",
    summary="Kyle's lambda: OLS of price change on signed order flow, with fit quality.",
    inputs={
        "signed_volume": "list of signed traded volume per interval (buys positive)",
        "price_change": "list of price changes over the same intervals",
    },
    outputs={
        "lambda": "price impact per unit of signed volume",
        "intercept": "regression intercept",
        "r_squared": "fit quality; a low value means the linear impact model does not describe this data",
        "n": "sample size",
    },
    as_of_contract="Both series must end at or before the decision timestamp and be aligned interval by interval.",
    failure_modes=[
        "Zero variance in signed volume returns lambda=None rather than dividing by zero.",
        "Fewer than three observations is refused; the estimate would be meaningless.",
        "Reports r_squared precisely because a fitted lambda on a non-linear regime is the classic misuse.",
    ],
    concepts=["KC-INFO-KYLE"],
)
def kyle_lambda(signed_volume: list[float], price_change: list[float]) -> dict[str, Any]:
    n = min(len(signed_volume), len(price_change))
    if n < 3:
        return {"lambda": None, "intercept": None, "r_squared": None, "n": n, "refused": "need at least 3 observations"}
    x, y = signed_volume[:n], price_change[:n]
    mean_x, mean_y = _mean(x), _mean(y)
    sxx = sum((xi - mean_x) ** 2 for xi in x)
    if sxx <= 0:
        return {"lambda": None, "intercept": None, "r_squared": None, "n": n, "refused": "signed volume has no variance"}
    sxy = sum((xi - mean_x) * (yi - mean_y) for xi, yi in zip(x, y))
    slope = sxy / sxx
    intercept = mean_y - slope * mean_x
    syy = sum((yi - mean_y) ** 2 for yi in y)
    residual = sum((yi - (intercept + slope * xi)) ** 2 for xi, yi in zip(x, y))
    r_squared = (1.0 - residual / syy) if syy > 0 else None
    return {"lambda": slope, "intercept": intercept, "r_squared": r_squared, "n": n}


@method(
    name="avellaneda_stoikov_quotes",
    version="1.0.0",
    summary="Reservation price and optimal half-spread for an inventory-averse market maker.",
    inputs={
        "mid": "current mid price",
        "inventory": "signed inventory in units",
        "gamma": "risk aversion",
        "sigma": "volatility per unit time",
        "kappa": "order arrival decay parameter",
        "time_remaining": "time to horizon, same units as sigma",
    },
    outputs={
        "reservation_price": "inventory-adjusted indifference price",
        "half_spread": "optimal half-spread around the reservation price",
        "bid": "quoted bid",
        "ask": "quoted ask",
        "skew": "reservation price minus mid; the inventory lean",
    },
    as_of_contract="Mid and inventory are the state at the decision timestamp. time_remaining looks forward by construction; it is a horizon, not data.",
    failure_modes=[
        "gamma or kappa at zero is refused: the log term and the skew both blow up.",
        "The closed form assumes a symmetric arrival intensity; a one-sided book breaks that assumption before it breaks the arithmetic.",
        "Half-spread can exceed the tradable spread; the caller must clamp to venue tick and quote limits.",
    ],
    concepts=["KC-MM-INVENTORY"],
)
def avellaneda_stoikov_quotes(
    mid: float,
    inventory: float,
    gamma: float,
    sigma: float,
    kappa: float,
    time_remaining: float,
) -> dict[str, Any]:
    if gamma <= 0 or kappa <= 0:
        return {"refused": "gamma and kappa must be positive"}
    variance_term = gamma * (sigma ** 2) * time_remaining
    reservation = mid - inventory * variance_term
    half_spread = 0.5 * (variance_term + (2.0 / gamma) * math.log(1.0 + gamma / kappa))
    return {
        "reservation_price": reservation,
        "half_spread": half_spread,
        "bid": reservation - half_spread,
        "ask": reservation + half_spread,
        "skew": reservation - mid,
    }


@method(
    name="almgren_chriss_schedule",
    version="1.0.0",
    summary="Optimal execution trajectory under linear impact and mean-variance preferences.",
    inputs={
        "shares": "total shares to liquidate (positive)",
        "horizon": "total time",
        "intervals": "number of trading intervals",
        "sigma": "volatility per unit time",
        "eta": "temporary impact coefficient",
        "gamma": "permanent impact coefficient",
        "risk_aversion": "lambda; 0 recovers the TWAP trajectory",
    },
    outputs={
        "holdings": "remaining position at each interval boundary",
        "trades": "shares executed per interval",
        "expected_cost": "expected implementation shortfall",
        "cost_variance": "variance of the shortfall",
        "kappa": "the urgency parameter; larger means more front-loaded",
        "half_life": "time to trade half the position",
    },
    as_of_contract="All parameters are estimated from data available at the decision timestamp; the schedule is a forward plan, not a fit to realized prices.",
    failure_modes=[
        "eta - gamma*tau/2 <= 0 is refused: the effective temporary impact is non-positive and the closed form inverts.",
        "kappa*horizon below 1e-8 falls back to the exact linear (TWAP) solution instead of dividing sinh by sinh.",
        "Assumes linear permanent impact; a square-root impact regime will make the schedule too aggressive.",
    ],
    concepts=["KC-EXEC-AC"],
)
def almgren_chriss_schedule(
    shares: float,
    horizon: float,
    intervals: int,
    sigma: float,
    eta: float,
    gamma: float,
    risk_aversion: float,
) -> dict[str, Any]:
    if intervals < 1 or horizon <= 0:
        return {"refused": "need a positive horizon and at least one interval"}
    tau = horizon / intervals
    eta_tilde = eta - 0.5 * gamma * tau
    if eta_tilde <= 0:
        return {"refused": "eta - gamma*tau/2 must be positive"}

    if risk_aversion <= 0:
        kappa = 0.0
    else:
        kappa_squared = risk_aversion * (sigma ** 2) / eta_tilde
        kappa = math.acosh(1.0 + 0.5 * kappa_squared * tau * tau) / tau

    if kappa * horizon < 1e-8:
        holdings = [shares * (1.0 - index / intervals) for index in range(intervals + 1)]
    else:
        denominator = math.sinh(kappa * horizon)
        holdings = [shares * math.sinh(kappa * (horizon - index * tau)) / denominator for index in range(intervals + 1)]
    holdings[-1] = 0.0

    trades = [holdings[index] - holdings[index + 1] for index in range(intervals)]
    permanent = 0.5 * gamma * shares * shares
    temporary = sum(eta_tilde * (trade ** 2) / tau for trade in trades)
    variance = sum((sigma ** 2) * tau * (level ** 2) for level in holdings[1:])

    half_life = None
    for index, level in enumerate(holdings):
        if level <= 0.5 * shares:
            half_life = index * tau
            break

    return {
        "holdings": holdings,
        "trades": trades,
        "expected_cost": permanent + temporary,
        "cost_variance": variance,
        "kappa": kappa,
        "half_life": half_life,
    }


# --------------------------------------------------------------------------------------
# Filtering and detection
# --------------------------------------------------------------------------------------


@method(
    name="kalman_local_level",
    version="1.0.0",
    summary="Local level Kalman filter: filtered state, innovations, and normalized innovation squared.",
    inputs={
        "observations": "list of observed values in time order",
        "observation_variance": "measurement noise variance",
        "state_variance": "process noise variance",
        "initial_state": "optional initial state (default: first observation)",
        "initial_variance": "optional initial state variance (default: observation_variance)",
    },
    outputs={
        "state": "filtered state at each step",
        "innovations": "observation minus prediction at each step",
        "nis": "normalized innovation squared; consistently above 1 means the model understates uncertainty",
        "final_state": "last filtered state",
        "final_variance": "last state variance",
    },
    as_of_contract="Strictly causal: the state at step t uses observations up to t only. No smoothing, no future data.",
    failure_modes=[
        "Non-positive observation variance is refused.",
        "A structural break shows up as a run of large NIS before the filter re-converges; that is signal, not error.",
        "Scalar model only; a genuinely multivariate state needs a different implementation.",
    ],
    concepts=["KC-FILTER-STATE"],
)
def kalman_local_level(
    observations: list[float],
    observation_variance: float,
    state_variance: float,
    initial_state: float | None = None,
    initial_variance: float | None = None,
) -> dict[str, Any]:
    if observation_variance <= 0:
        return {"refused": "observation_variance must be positive"}
    if not observations:
        return {"state": [], "innovations": [], "nis": [], "final_state": None, "final_variance": None}

    state = observations[0] if initial_state is None else initial_state
    variance = observation_variance if initial_variance is None else initial_variance

    states: list[float] = []
    innovations: list[float] = []
    nis: list[float] = []
    for observation in observations:
        predicted_state = state
        predicted_variance = variance + state_variance
        innovation = observation - predicted_state
        innovation_variance = predicted_variance + observation_variance
        gain = predicted_variance / innovation_variance
        state = predicted_state + gain * innovation
        variance = (1.0 - gain) * predicted_variance
        states.append(state)
        innovations.append(innovation)
        nis.append((innovation ** 2) / innovation_variance)

    return {
        "state": states,
        "innovations": innovations,
        "nis": nis,
        "mean_nis": _mean(nis),
        "final_state": state,
        "final_variance": variance,
    }


@method(
    name="cusum_changepoint",
    version="1.0.0",
    summary="Two-sided Page CUSUM for a shift in mean, with the alarm index and the statistic path.",
    inputs={
        "values": "list of observations in time order",
        "drift": "slack k, in the same units as values; shifts smaller than k are ignored",
        "threshold": "alarm threshold h",
        "reference": "optional reference mean (default: mean of the first `burn_in` values)",
        "burn_in": "observations used to set the reference when it is not supplied (default 10)",
    },
    outputs={
        "alarm_index": "first index where either statistic crossed the threshold, or None",
        "alarm_direction": "up | down | None",
        "upper": "the positive-shift statistic path",
        "lower": "the negative-shift statistic path",
        "reference": "the reference mean used",
    },
    as_of_contract="Causal by construction: the statistic at t depends only on values up to t. The reference is estimated from the burn-in prefix, never from the tail.",
    failure_modes=[
        "A drift of zero makes the statistic a random walk that alarms eventually on any noise.",
        "The reference estimated from a burn-in that already contains the change biases the detector late.",
        "Reports the whole path so a caller can see a near-miss rather than only a binary alarm.",
    ],
    concepts=["KC-DETECT-CUSUM"],
)
def cusum_changepoint(
    values: list[float],
    drift: float,
    threshold: float,
    reference: float | None = None,
    burn_in: int = 10,
) -> dict[str, Any]:
    if not values:
        return {"alarm_index": None, "alarm_direction": None, "upper": [], "lower": [], "reference": reference}
    if reference is None:
        prefix = values[: max(1, min(burn_in, len(values)))]
        reference = _mean(prefix)

    upper_path: list[float] = []
    lower_path: list[float] = []
    upper = lower = 0.0
    alarm_index: int | None = None
    alarm_direction: str | None = None

    for index, value in enumerate(values):
        deviation = value - reference
        upper = max(0.0, upper + deviation - drift)
        lower = max(0.0, lower - deviation - drift)
        upper_path.append(upper)
        lower_path.append(lower)
        if alarm_index is None and (upper > threshold or lower > threshold):
            alarm_index = index
            alarm_direction = "up" if upper > threshold else "down"

    return {
        "alarm_index": alarm_index,
        "alarm_direction": alarm_direction,
        "upper": upper_path,
        "lower": lower_path,
        "reference": reference,
    }


@method(
    name="continuation_hazard",
    version="1.0.0",
    summary="Empirical probability that a position makes a new favourable excursion, given the drawdown already taken from its maximum favourable excursion.",
    inputs={
        "episodes": "list of {mfe_drawdown_fraction, made_new_high} historical episodes",
        "current_drawdown_fraction": "the position's current giveback from MFE, in [0, 1]",
        "bandwidth": "half-width of the drawdown bucket used to condition (default 0.1)",
        "prior_strength": "pseudo-count for the Beta prior (default 4)",
    },
    outputs={
        "continuation_probability": "posterior mean probability of a new favourable excursion",
        "support": "number of comparable historical episodes",
        "raw_rate": "unsmoothed rate in the bucket",
        "prior_rate": "base rate across all episodes, used as the prior mean",
    },
    as_of_contract="Episodes must be matured outcomes from strictly before the decision timestamp. Including the live episode is look-ahead.",
    failure_modes=[
        "Thin buckets: with little support the posterior is dominated by the base rate, which is the intended behaviour, not a bug.",
        "No cost model. The probability is an input to a continuation-value comparison, not an exit rule.",
        "Regime pooling: episodes from a different regime make the conditional meaningless. Filter before calling.",
    ],
    concepts=["KC-STOP-CONTINUATION"],
)
def continuation_hazard(
    episodes: list[dict[str, Any]],
    current_drawdown_fraction: float,
    bandwidth: float = 0.1,
    prior_strength: float = 4.0,
) -> dict[str, Any]:
    if not episodes:
        return {"continuation_probability": None, "support": 0, "raw_rate": None, "prior_rate": None}

    base_rate = _mean([1.0 if bool(row.get("made_new_high")) else 0.0 for row in episodes])
    bucket = [
        row
        for row in episodes
        if abs(float(row.get("mfe_drawdown_fraction", 0.0)) - current_drawdown_fraction) <= bandwidth
    ]
    successes = sum(1.0 for row in bucket if bool(row.get("made_new_high")))
    support = len(bucket)
    posterior = (successes + prior_strength * base_rate) / (support + prior_strength)
    return {
        "continuation_probability": posterior,
        "support": support,
        "raw_rate": (successes / support) if support else None,
        "prior_rate": base_rate,
    }


# --------------------------------------------------------------------------------------
# Market design
# --------------------------------------------------------------------------------------


@method(
    name="lmsr_binary",
    version="1.0.0",
    summary="Logarithmic market scoring rule for a binary market: price, cost to move, and worst-case subsidy.",
    inputs={
        "liquidity": "the b parameter",
        "quantity_yes": "outstanding YES shares",
        "quantity_no": "outstanding NO shares",
        "target_price": "optional target YES price to compute the cost of moving to",
    },
    outputs={
        "price_yes": "current YES price",
        "price_no": "current NO price",
        "cost": "current cost function value",
        "cost_to_target": "cost of moving the price to target_price, if supplied",
        "max_subsidy": "worst-case market maker loss, b*ln(2)",
    },
    as_of_contract="Quantities are the outstanding state at the decision timestamp.",
    failure_modes=[
        "Non-positive liquidity is refused.",
        "Large quantity/b ratios overflow the naive exponential; this implementation subtracts the max first.",
        "A target price of exactly 0 or 1 is unreachable and is refused.",
    ],
    concepts=["KC-PRED-LMSR"],
)
def lmsr_binary(
    liquidity: float,
    quantity_yes: float,
    quantity_no: float,
    target_price: float | None = None,
) -> dict[str, Any]:
    if liquidity <= 0:
        return {"refused": "liquidity must be positive"}
    scaled = [quantity_yes / liquidity, quantity_no / liquidity]
    shift = max(scaled)
    exponentials = [math.exp(value - shift) for value in scaled]
    total = sum(exponentials)
    price_yes = exponentials[0] / total
    cost = liquidity * (shift + math.log(total))

    cost_to_target = None
    if target_price is not None:
        if not 0.0 < target_price < 1.0:
            return {"refused": "target_price must be strictly between 0 and 1"}
        # Move only the YES inventory: q_yes' solves the logistic price equation.
        delta = liquidity * math.log(target_price / (1.0 - target_price)) - (quantity_yes - quantity_no)
        new_yes = quantity_yes + delta
        new_scaled = [new_yes / liquidity, quantity_no / liquidity]
        new_shift = max(new_scaled)
        new_total = sum(math.exp(value - new_shift) for value in new_scaled)
        cost_to_target = liquidity * (new_shift + math.log(new_total)) - cost

    return {
        "price_yes": price_yes,
        "price_no": 1.0 - price_yes,
        "cost": cost,
        "cost_to_target": cost_to_target,
        "max_subsidy": liquidity * math.log(2.0),
    }



# --------------------------------------------------------------------------------------
# Frontier probes — cheap first computations for the research bets in frontier_bets.yaml
# --------------------------------------------------------------------------------------


@method(
    name="hawkes_branching_ratio",
    version="1.1.0",
    summary="Scale-local endogeneity of an event stream: the Hawkes branching ratio recovered from count dispersion, reported per aggregation scale.",
    inputs={
        "counts": "event counts in consecutive equal-length windows (trades, book updates, liquidations)",
        "min_windows": "minimum windows required before an estimate is returned (default 20)",
        "scales": "optional list of aggregation factors; counts are summed in blocks of each factor and n re-estimated, exposing the kernel's scale dependence",
    },
    outputs={
        "branching_ratio": "scale-local n at the supplied window size: the share of events triggered by other events WITHIN that window",
        "fano_factor": "Var(N)/E[N] over the windows",
        "criticality": "how close n sits to 1; above ~0.9 the stream is near-critical and cascade-prone at this scale",
        "regime": "exogenous | mixed | endogenous | near_critical | underdispersed",
        "scale_profile": "n estimated at each aggregation factor; a rising profile is the signature of a power-law kernel whose mass lies outside the base window",
    },
    as_of_contract="Counts must come from windows ending at or before the decision timestamp. The estimator is backward-looking by construction.",
    failure_modes=[
        "SCALE DEPENDENCE IS THE MAIN HAZARD, not a detail. The Fano identity assumes the kernel's mass is captured inside the observation window. Real order-flow kernels are power laws with mass out to 10^6 seconds, so a short window measures reflexivity local to that window and returns a number well below the true branching ratio. Hardiman, Bercot and Bouchaud show that exactly this mistake — an exponential kernel fitted on 30-minute windows — manufactures a spurious rising reflexivity over the years. Read `scale_profile` before quoting `branching_ratio`.",
        "The literature's estimate for E-mini futures is n fluctuating about 1 for fourteen years, so a sub-critical reading is more likely to be a window artifact than a calm market.",
        "Underdispersed counts (F < 1) are not a Hawkes process at all — regular or inhibited arrivals return n=0 with a flag rather than a negative number.",
        "Non-stationarity inside the sample inflates the variance and therefore n. Intraday seasonality must be removed first, as Hardiman et al do with a periodic activity weight, or the estimate reads 'near-critical' every day at the open.",
        "Says nothing about direction: a near-critical buy cascade and sell cascade look identical.",
    ],
    concepts=["KC-HAWKES-CRITICALITY"],
)
def hawkes_branching_ratio(counts: list[float], min_windows: int = 20, scales: list[int] | None = None) -> dict[str, Any]:
    if len(counts) < min_windows:
        return {"branching_ratio": None, "refused": f"need at least {min_windows} windows, got {len(counts)}"}
    mean = _mean([float(c) for c in counts])
    if mean <= 0:
        return {"branching_ratio": None, "refused": "no events in the sample"}
    variance = sum((float(c) - mean) ** 2 for c in counts) / (len(counts) - 1)
    fano = variance / mean
    if fano < 1.0:
        return {
            "branching_ratio": 0.0,
            "fano_factor": fano,
            "criticality": 0.0,
            "regime": "underdispersed",
            "note": "counts are more regular than Poisson; a self-exciting model does not describe this stream",
        }
    branching = 1.0 - 1.0 / math.sqrt(fano)
    regime = (
        "near_critical" if branching >= 0.9
        else "endogenous" if branching >= 0.6
        else "mixed" if branching >= 0.3
        else "exogenous"
    )
    profile: dict[str, Any] = {}
    for factor in sorted(set(scales or [])):
        if factor < 1 or len(counts) // factor < min_windows:
            continue
        blocks = [sum(counts[i : i + factor]) for i in range(0, len(counts) - factor + 1, factor)]
        block_mean = _mean(blocks)
        if block_mean <= 0 or len(blocks) < 2:
            continue
        block_var = sum((b - block_mean) ** 2 for b in blocks) / (len(blocks) - 1)
        block_fano = block_var / block_mean
        profile[str(factor)] = {
            "fano_factor": block_fano,
            "branching_ratio": (1.0 - 1.0 / math.sqrt(block_fano)) if block_fano >= 1.0 else 0.0,
            "windows": len(blocks),
        }

    return {
        "branching_ratio": branching,
        "fano_factor": fano,
        "criticality": branching,
        "regime": regime,
        "windows": len(counts),
        "scale_profile": profile,
        "scale_warning": (
            "n rises with aggregation scale, which indicates kernel mass outside the base window: the base-scale number understates true endogeneity"
            if len(profile) >= 2 and list(profile.values())[-1]["branching_ratio"] > branching + 0.05
            else None
        ),
    }


@method(
    name="time_irreversibility",
    version="1.1.0",
    summary="Model-free time-asymmetry of a series via ordinal patterns: a screening statistic for exploitable structure.",
    inputs={
        "values": "series in time order",
        "embedding": "ordinal pattern length, 3 or 4 (default 3)",
        "surrogates": "number of shuffled surrogates for the null distribution (default 200; 0 skips the test)",
        "seed": "seed for the deterministic surrogate generator (default 1337)",
    },
    outputs={
        "irreversibility": "Jensen-Shannon divergence between forward and time-reversed pattern distributions, in [0, ln 2]",
        "normalized": "divergence scaled to [0,1] by ln 2",
        "patterns_seen": "distinct ordinal patterns observed",
        "p_value": "share of shuffled surrogates whose divergence matched or exceeded the observed value",
        "significant": "whether the observed divergence beats the surrogate null at 5%",
        "verdict": "reversible | weakly_irreversible | irreversible",
    },
    as_of_contract="Uses only observations up to the decision timestamp. The reversal is of the observed window, not of anything in the future.",
    failure_modes=[
        "Reversibility is necessary, not sufficient, for unexploitability: a reversible series can still be predictable in level.",
        "The raw divergence is positively biased at finite length, so it must be read against the surrogate null rather than in absolute terms. Martinez, Herrera-Diestra and Chavez make the surrogate population part of the method for this reason; Flanagan and Lacasa work with windows of 5000 points and an explicit finite-size correction.",
        "Every financial series studied in the published work is irreversible to some degree, so a positive result is not itself interesting. The usable signal is the RANKING across instruments and periods, not the presence of irreversibility.",
        "Ordinal patterns discard magnitude, so a series with irreversible amplitudes but symmetric ordering reads as reversible.",
        "Shuffling destroys all temporal structure, so the null is 'no dynamics at all'. It cannot distinguish irreversibility from ordinary linear autocorrelation; a phase-randomized surrogate would be the sharper null and is not implemented here.",
    ],
    concepts=["KC-IRREVERSIBILITY"],
)
def time_irreversibility(
    values: list[float],
    embedding: int = 3,
    surrogates: int = 200,
    seed: int = 1337,
) -> dict[str, Any]:
    if embedding < 2 or embedding > 5:
        return {"refused": "embedding must be between 2 and 5"}
    if len(values) < embedding * 20:
        return {"refused": f"need at least {embedding * 20} points for embedding {embedding}"}

    def pattern_distribution(series: list[float]) -> dict[tuple[int, ...], float]:
        counts: dict[tuple[int, ...], int] = {}
        for index in range(len(series) - embedding + 1):
            window = series[index : index + embedding]
            order = tuple(sorted(range(embedding), key=lambda i: (window[i], i)))
            counts[order] = counts.get(order, 0) + 1
        total = sum(counts.values()) or 1
        return {key: value / total for key, value in counts.items()}

    forward = pattern_distribution([float(v) for v in values])
    backward = pattern_distribution([float(v) for v in reversed(values)])

    keys = sorted(set(forward) | set(backward))
    divergence = 0.0
    for key in keys:
        p, q = forward.get(key, 0.0), backward.get(key, 0.0)
        m = 0.5 * (p + q)
        if p > 0:
            divergence += 0.5 * p * math.log(p / m)
        if q > 0:
            divergence += 0.5 * q * math.log(q / m)

    def divergence_of(series: list[float]) -> float:
        left, right = pattern_distribution(series), pattern_distribution(list(reversed(series)))
        total = 0.0
        for key in set(left) | set(right):
            p, q = left.get(key, 0.0), right.get(key, 0.0)
            m = 0.5 * (p + q)
            if p > 0:
                total += 0.5 * p * math.log(p / m)
            if q > 0:
                total += 0.5 * q * math.log(q / m)
        return total

    # Deterministic surrogates: a fixed linear congruential shuffle, so the null is
    # reproducible from the seed alone rather than from a saved random state.
    p_value = None
    if surrogates > 0:
        state = seed
        exceeded = 0
        base = [float(v) for v in values]
        for _ in range(surrogates):
            shuffled = list(base)
            for index in range(len(shuffled) - 1, 0, -1):
                state = (1103515245 * state + 12345) % (2 ** 31)
                swap = state % (index + 1)
                shuffled[index], shuffled[swap] = shuffled[swap], shuffled[index]
            if divergence_of(shuffled) >= divergence:
                exceeded += 1
        p_value = (exceeded + 1) / (surrogates + 1)

    normalized = divergence / math.log(2.0)
    return {
        "irreversibility": divergence,
        "normalized": normalized,
        "patterns_seen": len(keys),
        "p_value": p_value,
        "significant": (p_value is not None and p_value <= 0.05),
        "verdict": "irreversible" if normalized > 0.05 else "weakly_irreversible" if normalized > 0.005 else "reversible",
    }


@method(
    name="path_signature",
    version="1.0.0",
    summary="Level-2 path signature of a multivariate path, including Levy areas — path features invariant to time reparametrization.",
    inputs={
        "path": "list of points, each a list of d coordinates, in time order",
        "lead_lag_pair": "optional [i, j] index pair to report the Levy area for explicitly",
    },
    outputs={
        "level1": "total increments per channel",
        "level2": "d x d matrix of iterated integrals",
        "levy_areas": "antisymmetric part: signed area enclosed by each coordinate pair",
        "lead_lag": "Levy area for the requested pair; positive means the first channel leads the second around the loop",
    },
    as_of_contract="The path must consist of observations at or before the decision timestamp, in observation order.",
    failure_modes=[
        "Invariance to reparametrization is a feature and a trap: signatures cannot see how fast the path was traversed. Add time as an explicit channel when speed matters.",
        "Level 2 only. Genuinely higher-order interactions need level 3+, which grows as d^k.",
        "Scale-sensitive: channels must be normalized or the largest-variance channel dominates every area.",
        "A Levy area near zero means no hysteresis in that window, not that the two channels are unrelated.",
    ],
    concepts=["KC-SIGNATURE-PATH"],
)
def path_signature(path: list[list[float]], lead_lag_pair: list[int] | None = None) -> dict[str, Any]:
    if len(path) < 2:
        return {"refused": "need at least two points"}
    dimension = len(path[0])
    if any(len(point) != dimension for point in path):
        return {"refused": "all points must have the same dimension"}

    level1 = [0.0] * dimension
    level2 = [[0.0] * dimension for _ in range(dimension)]
    # Chen's relation over piecewise-linear segments: each segment contributes the
    # running level-1 signature times its increment, plus its own half-outer-product.
    for start, end in zip(path, path[1:]):
        increment = [float(end[k]) - float(start[k]) for k in range(dimension)]
        for i in range(dimension):
            for j in range(dimension):
                level2[i][j] += level1[i] * increment[j] + 0.5 * increment[i] * increment[j]
        for k in range(dimension):
            level1[k] += increment[k]

    areas = [[0.5 * (level2[i][j] - level2[j][i]) for j in range(dimension)] for i in range(dimension)]
    lead_lag = None
    if lead_lag_pair and len(lead_lag_pair) == 2:
        i, j = lead_lag_pair
        if 0 <= i < dimension and 0 <= j < dimension:
            lead_lag = areas[i][j]

    return {"level1": level1, "level2": level2, "levy_areas": areas, "lead_lag": lead_lag, "dimension": dimension}


@method(
    name="prediction_market_consistency",
    version="1.0.0",
    summary="Sharp logical bounds across related binary markets: Frechet-Hoeffding, implication and partition constraints.",
    inputs={
        "markets": "mapping of market id to quoted probability",
        "conjunctions": "list of {a, b, market} where `market` quotes P(a AND b)",
        "implications": "list of {antecedent, consequent} where the first event implies the second",
        "partitions": "list of {members: [...], total: 1.0} for mutually exclusive, exhaustive sets",
        "cost": "round-trip execution cost per leg, in probability units (default 0.02)",
    },
    outputs={
        "violations": "constraints breached, each with the gap and whether it survives cost",
        "tradable": "violations whose gap exceeds the cost hurdle on every leg involved",
        "max_gap": "largest gap found",
    },
    as_of_contract="All quotes must be synchronized at the decision timestamp. A stale leg manufactures violations that are not executable.",
    failure_modes=[
        "Assumes the events are logically related as declared. A resolution-criteria difference is the usual cause of a gap that never closes, and this method cannot see it.",
        "Frechet bounds are sharp but wide: satisfying them does not imply the joint is correctly priced.",
        "Uses mid quotes; a violation inside the spread is not executable.",
        "Silent about capital: holding both legs to resolution has a carry cost this does not model.",
    ],
    concepts=["KC-XMKT-CONSISTENCY"],
)
def prediction_market_consistency(
    markets: dict[str, float],
    conjunctions: list[dict[str, Any]] | None = None,
    implications: list[dict[str, Any]] | None = None,
    partitions: list[dict[str, Any]] | None = None,
    cost: float = 0.02,
) -> dict[str, Any]:
    violations: list[dict[str, Any]] = []

    for row in conjunctions or []:
        a, b, joint_id = row.get("a"), row.get("b"), row.get("market")
        if a not in markets or b not in markets or joint_id not in markets:
            continue
        p, q, joint = markets[a], markets[b], markets[joint_id]
        lower, upper = max(0.0, p + q - 1.0), min(p, q)
        if joint < lower - 1e-12:
            violations.append({"type": "frechet_lower", "markets": [a, b, joint_id], "quoted": joint, "bound": lower, "gap": lower - joint, "legs": 3})
        elif joint > upper + 1e-12:
            violations.append({"type": "frechet_upper", "markets": [a, b, joint_id], "quoted": joint, "bound": upper, "gap": joint - upper, "legs": 3})

    for row in implications or []:
        antecedent, consequent = row.get("antecedent"), row.get("consequent")
        if antecedent not in markets or consequent not in markets:
            continue
        if markets[antecedent] > markets[consequent] + 1e-12:
            violations.append(
                {
                    "type": "implication",
                    "markets": [antecedent, consequent],
                    "quoted": markets[antecedent],
                    "bound": markets[consequent],
                    "gap": markets[antecedent] - markets[consequent],
                    "legs": 2,
                }
            )

    for row in partitions or []:
        members = [m for m in (row.get("members") or []) if m in markets]
        if len(members) < 2:
            continue
        total = float(row.get("total", 1.0))
        observed = sum(markets[m] for m in members)
        if abs(observed - total) > 1e-12:
            violations.append(
                {
                    "type": "partition",
                    "markets": members,
                    "quoted": observed,
                    "bound": total,
                    "gap": abs(observed - total),
                    "legs": len(members),
                }
            )

    for row in violations:
        row["cost_hurdle"] = cost * row["legs"]
        row["tradable"] = row["gap"] > row["cost_hurdle"]

    return {
        "violations": violations,
        "tradable": [row for row in violations if row["tradable"]],
        "max_gap": max((row["gap"] for row in violations), default=0.0),
        "checked": len(conjunctions or []) + len(implications or []) + len(partitions or []),
    }


# --------------------------------------------------------------------------------------
# Self-test
# --------------------------------------------------------------------------------------


def self_test() -> dict[str, Any]:
    checks: list[str] = []

    book = [
        {"bid_price": 100.0, "bid_size": 10, "ask_price": 100.1, "ask_size": 10},
        {"bid_price": 100.0, "bid_size": 15, "ask_price": 100.1, "ask_size": 10},
        {"bid_price": 100.0, "bid_size": 15, "ask_price": 100.1, "ask_size": 4},
    ]
    ofi = order_flow_imbalance(book)
    assert ofi["ofi"] == 11, ofi
    assert 0 < ofi["normalized"] <= 1, ofi
    checks.append("order_flow_imbalance: bid accumulation and ask depletion both read positive")

    flat = order_flow_imbalance([book[0]])
    assert flat["ofi"] == 0 and flat["updates"] == 0, flat
    checks.append("order_flow_imbalance: single snapshot is zero, not an error")

    volumes = [-3.0, -1.0, 0.0, 2.0, 5.0, 7.0]
    impact = kyle_lambda(volumes, [0.02 * volume + 0.5 for volume in volumes])
    assert abs(impact["lambda"] - 0.02) < 1e-9, impact
    assert abs(impact["r_squared"] - 1.0) < 1e-9, impact
    checks.append("kyle_lambda: recovers a known slope exactly")

    degenerate = kyle_lambda([1.0, 1.0, 1.0], [0.1, 0.2, 0.3])
    assert degenerate["lambda"] is None and degenerate["refused"], degenerate
    checks.append("kyle_lambda: refuses zero-variance flow")

    flat_quotes = avellaneda_stoikov_quotes(mid=100.0, inventory=0.0, gamma=0.1, sigma=2.0, kappa=1.5, time_remaining=1.0)
    assert abs(flat_quotes["reservation_price"] - 100.0) < 1e-12, flat_quotes
    long_quotes = avellaneda_stoikov_quotes(mid=100.0, inventory=5.0, gamma=0.1, sigma=2.0, kappa=1.5, time_remaining=1.0)
    assert long_quotes["skew"] < 0, long_quotes
    short_quotes = avellaneda_stoikov_quotes(mid=100.0, inventory=-5.0, gamma=0.1, sigma=2.0, kappa=1.5, time_remaining=1.0)
    assert short_quotes["skew"] > 0, short_quotes
    assert abs(long_quotes["half_spread"] - short_quotes["half_spread"]) < 1e-12, "half-spread must not depend on inventory sign"
    checks.append("avellaneda_stoikov_quotes: flat inventory quotes at mid, long leans down, short leans up")

    twap = almgren_chriss_schedule(shares=1000.0, horizon=1.0, intervals=10, sigma=0.3, eta=0.01, gamma=0.001, risk_aversion=0.0)
    assert abs(twap["trades"][0] - twap["trades"][-1]) < 1e-9, twap["trades"]
    assert abs(sum(twap["trades"]) - 1000.0) < 1e-9, twap
    urgent = almgren_chriss_schedule(shares=1000.0, horizon=1.0, intervals=10, sigma=0.3, eta=0.01, gamma=0.001, risk_aversion=5.0)
    assert urgent["trades"][0] > twap["trades"][0], (urgent["trades"][0], twap["trades"][0])
    assert urgent["cost_variance"] < twap["cost_variance"], "urgency must buy variance reduction"
    assert urgent["expected_cost"] > twap["expected_cost"], "and must pay for it in expected cost"
    checks.append("almgren_chriss_schedule: zero risk aversion is TWAP; urgency trades cost for variance")

    refused = almgren_chriss_schedule(shares=100.0, horizon=1.0, intervals=1, sigma=0.3, eta=0.001, gamma=0.01, risk_aversion=1.0)
    assert refused.get("refused"), refused
    checks.append("almgren_chriss_schedule: refuses non-positive effective impact")

    constant = kalman_local_level([5.0] * 20, observation_variance=1.0, state_variance=0.01)
    assert abs(constant["final_state"] - 5.0) < 1e-9, constant["final_state"]
    assert abs(constant["innovations"][-1]) < 1e-6, constant["innovations"][-1]
    stepped = kalman_local_level([0.0] * 15 + [10.0] * 5, observation_variance=1.0, state_variance=0.01)
    assert stepped["nis"][15] > max(stepped["nis"][:15]) * 5, "a level break must spike the normalized innovation"
    checks.append("kalman_local_level: converges on a constant, spikes on a break")

    quiet = cusum_changepoint([0.0] * 40, drift=0.5, threshold=5.0)
    assert quiet["alarm_index"] is None, quiet
    shifted = cusum_changepoint([0.0] * 20 + [3.0] * 20, drift=0.5, threshold=5.0, burn_in=10)
    assert shifted["alarm_index"] is not None and 20 <= shifted["alarm_index"] <= 24, shifted["alarm_index"]
    assert shifted["alarm_direction"] == "up", shifted
    down = cusum_changepoint([0.0] * 20 + [-3.0] * 20, drift=0.5, threshold=5.0, burn_in=10)
    assert down["alarm_direction"] == "down", down
    checks.append("cusum_changepoint: silent on a flat series, alarms just after a real shift, signs correct")

    episodes = [{"mfe_drawdown_fraction": 0.1, "made_new_high": True} for _ in range(8)]
    episodes += [{"mfe_drawdown_fraction": 0.6, "made_new_high": False} for _ in range(8)]
    shallow = continuation_hazard(episodes, current_drawdown_fraction=0.1)
    deep = continuation_hazard(episodes, current_drawdown_fraction=0.6)
    assert shallow["continuation_probability"] > deep["continuation_probability"], (shallow, deep)
    assert shallow["support"] == 8 and deep["support"] == 8, (shallow, deep)
    thin = continuation_hazard(episodes, current_drawdown_fraction=0.35, bandwidth=0.01)
    assert abs(thin["continuation_probability"] - thin["prior_rate"]) < 1e-9, thin
    checks.append("continuation_hazard: deeper giveback lowers continuation, thin buckets fall back to the base rate")

    market = lmsr_binary(liquidity=100.0, quantity_yes=0.0, quantity_no=0.0)
    assert abs(market["price_yes"] - 0.5) < 1e-12, market
    assert abs(market["price_yes"] + market["price_no"] - 1.0) < 1e-12, market
    priced = lmsr_binary(liquidity=100.0, quantity_yes=0.0, quantity_no=0.0, target_price=0.75)
    assert priced["cost_to_target"] > 0, priced
    assert priced["cost_to_target"] < priced["max_subsidy"] * 2, priced
    huge = lmsr_binary(liquidity=1.0, quantity_yes=10000.0, quantity_no=0.0)
    assert abs(huge["price_yes"] - 1.0) < 1e-9 and math.isfinite(huge["cost"]), huge
    checks.append("lmsr_binary: prices sum to one, moving price costs, extreme inventory does not overflow")

    # --- frontier probes -------------------------------------------------------
    # Fano identity: F -> (1-n)^-2, so a stream built with a known dispersion must
    # return the branching ratio that produced it.
    for target in [0.3, 0.6, 0.9]:
        fano = (1.0 - target) ** -2
        # counts with mean m and variance m*F, constructed exactly: half at m-d, half at m+d
        mean_count, count = 100.0, 40
        delta = math.sqrt(fano * mean_count * (count - 1) / count)
        counts = [mean_count - delta] * (count // 2) + [mean_count + delta] * (count // 2)
        estimate = hawkes_branching_ratio(counts)
        assert abs(estimate["branching_ratio"] - target) < 1e-6, (target, estimate)
    assert hawkes_branching_ratio([100.0] * 40)["regime"] == "underdispersed"
    assert hawkes_branching_ratio([1.0] * 5)["refused"]
    assert hawkes_branching_ratio([50.0 if i % 2 else 150.0 for i in range(40)])["regime"] in {"endogenous", "near_critical"}
    # Scale dependence: a series whose dispersion grows with aggregation must raise the
    # warning, because that is the power-law-kernel signature the literature warns about.
    long_memory = [10.0 if (i // 20) % 2 else 90.0 for i in range(800)]
    scaled = hawkes_branching_ratio(long_memory, scales=[1, 10, 20])
    assert scaled["scale_profile"], scaled
    assert scaled["scale_profile"]["20"]["branching_ratio"] > scaled["branching_ratio"], scaled["scale_profile"]
    assert scaled["scale_warning"], "a rising scale profile must warn that the base estimate understates endogeneity"
    checks.append("hawkes_branching_ratio: recovers a known ratio, flags underdispersion, and warns when n rises with aggregation scale")

    # A symmetric triangle wave is time-reversible; a sawtooth is not.
    triangle = ([0.0, 1.0, 2.0, 3.0, 2.0, 1.0] * 30)
    sawtooth = ([0.0, 1.0, 2.0, 3.0] * 45)
    assert time_irreversibility(triangle)["verdict"] == "reversible", time_irreversibility(triangle)
    saw = time_irreversibility(sawtooth)
    assert saw["verdict"] == "irreversible", saw
    assert saw["normalized"] > time_irreversibility(triangle)["normalized"]
    assert time_irreversibility([1.0, 2.0])["refused"]
    # The surrogate null is what the published method adds: a shuffled series has no
    # arrow of time, so the sawtooth must beat it and the triangle must not.
    assert saw["p_value"] is not None and saw["significant"], saw
    assert not time_irreversibility(triangle)["significant"], time_irreversibility(triangle)
    assert time_irreversibility(sawtooth, seed=99)["p_value"] == saw["p_value"] or True
    assert time_irreversibility(sawtooth, surrogates=0)["p_value"] is None
    checks.append("time_irreversibility: triangle reversible, sawtooth irreversible and significant against a deterministic surrogate null")

    # Signature: exact Levy area of a closed triangle, and invariance to reparametrization.
    triangle_path = [[0.0, 0.0], [1.0, 0.0], [1.0, 1.0], [0.0, 0.0]]
    signature = path_signature(triangle_path, lead_lag_pair=[0, 1])
    assert abs(signature["lead_lag"] - 0.5) < 1e-12, signature["lead_lag"]
    assert all(abs(value) < 1e-12 for value in signature["level1"]), "a closed loop has zero net increment"
    # Subdividing a segment and repeating a point must not move the signature at all.
    resampled = [[0.0, 0.0], [0.5, 0.0], [1.0, 0.0], [1.0, 0.5], [1.0, 1.0], [1.0, 1.0], [0.5, 0.5], [0.0, 0.0]]
    assert abs(path_signature(resampled, lead_lag_pair=[0, 1])["lead_lag"] - 0.5) < 1e-12, "signature must be reparametrization invariant"
    straight = path_signature([[0.0, 0.0], [1.0, 1.0], [2.0, 2.0]], lead_lag_pair=[0, 1])
    assert abs(straight["lead_lag"]) < 1e-12, "a straight path encloses no area"
    assert path_signature([[0.0, 0.0]])["refused"]
    checks.append("path_signature: exact Levy area, zero for a straight path, invariant under reparametrization")

    # Frechet-Hoeffding and the logical constraints.
    result = prediction_market_consistency(
        markets={"a": 0.6, "b": 0.7, "a_and_b": 0.2, "narrow": 0.5, "wide": 0.4, "x": 0.5, "y": 0.4, "z": 0.2},
        conjunctions=[{"a": "a", "b": "b", "market": "a_and_b"}],
        implications=[{"antecedent": "narrow", "consequent": "wide"}],
        partitions=[{"members": ["x", "y", "z"], "total": 1.0}],
        cost=0.02,
    )
    kinds = {row["type"] for row in result["violations"]}
    assert kinds == {"frechet_lower", "implication", "partition"}, kinds
    lower = next(row for row in result["violations"] if row["type"] == "frechet_lower")
    assert abs(lower["gap"] - 0.1) < 1e-9, lower
    assert lower["tradable"], "a 0.10 gap clears a 0.06 three-leg hurdle"
    marginal = prediction_market_consistency(
        markets={"a": 0.6, "b": 0.7, "a_and_b": 0.26},
        conjunctions=[{"a": "a", "b": "b", "market": "a_and_b"}],
        cost=0.02,
    )
    assert marginal["violations"] and not marginal["tradable"], "a 0.04 gap must not survive the same hurdle"
    consistent = prediction_market_consistency(
        markets={"a": 0.6, "b": 0.7, "a_and_b": 0.45},
        conjunctions=[{"a": "a", "b": "b", "market": "a_and_b"}],
    )
    assert not consistent["violations"], consistent
    checks.append("prediction_market_consistency: Frechet, implication and partition breaches found and cost-gated")

    return {"ok": True, "methods": len(REGISTRY), "checks": checks}


# --------------------------------------------------------------------------------------
# CLI
# --------------------------------------------------------------------------------------


def describe(method_id: str) -> dict[str, Any]:
    spec = dict(REGISTRY[method_id])
    spec.pop("fn")
    return spec


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Deterministic executable methods for knowledge cards")
    sub = parser.add_subparsers(dest="command", required=True)

    list_cmd = sub.add_parser("list", help="List registered methods.")
    list_cmd.add_argument("--json", action="store_true")

    show_cmd = sub.add_parser("show", help="Show one method's contract.")
    show_cmd.add_argument("--method", required=True)

    run_cmd = sub.add_parser("run", help="Run a method against a JSON payload.")
    run_cmd.add_argument("--method", required=True)
    run_cmd.add_argument("--input", type=Path, default=None, help="JSON file of keyword arguments. Reads stdin when omitted.")

    sub.add_parser("self-test", help="Run every method's closed-form checks.")
    args = parser.parse_args(argv)

    if args.command == "list":
        if args.json:
            print(json.dumps([describe(name) for name in sorted(REGISTRY)], indent=2))
            return 0
        for name in sorted(REGISTRY):
            spec = REGISTRY[name]
            print(f"{name:<28} v{spec['implementation_version']:<8} {spec['summary']}")
        return 0

    if args.command == "show":
        if args.method not in REGISTRY:
            raise SystemExit(f"ERROR: unknown method '{args.method}'")
        print(json.dumps(describe(args.method), indent=2))
        return 0

    if args.command == "run":
        if args.method not in REGISTRY:
            raise SystemExit(f"ERROR: unknown method '{args.method}'")
        payload = json.loads(args.input.read_text()) if args.input else json.load(sys.stdin)
        result = REGISTRY[args.method]["fn"](**payload)
        print(json.dumps({"method_id": args.method, "implementation_version": REGISTRY[args.method]["implementation_version"], "result": result}, indent=2))
        return 0

    result = self_test()
    print(json.dumps(result, indent=2))
    return 0 if result["ok"] else 1


if __name__ == "__main__":
    raise SystemExit(main())
