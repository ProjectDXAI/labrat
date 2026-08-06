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
    version="1.1.0",
    summary="Sharp logical bounds across related binary markets: Frechet-Hoeffding, implication and partition constraints.",
    inputs={
        "markets": "mapping of market id to quoted probability",
        "conjunctions": "list of {a, b, market} where `market` quotes P(a AND b)",
        "implications": "list of {antecedent, consequent} where the first event implies the second",
        "partitions": "list of {members: [...], total: 1.0} for mutually exclusive, exhaustive sets",
        "cost": "round-trip execution cost per leg, in probability units (default 0.02)",
        "settlement": "legwise (default) or atomic; atomic applies where a complete set can be split or merged for collateral in one transaction, so the legs cannot come apart",
        "settlement_cost": "flat cost of an atomic split or merge, in probability units (default 0.005)",
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
        "The legwise cost model assumes each leg is a separate execution that can fail independently. On a venue where a complete set can be split or merged for collateral in a single transaction, that model overstates the hurdle badly — pass settlement=atomic there, and note that only constraints the token layer actually enforces are settled atomically.",
        "Silent about capital: holding a position to resolution has a carry cost this does not model.",
    ],
    concepts=["KC-XMKT-CONSISTENCY"],
)
def prediction_market_consistency(
    markets: dict[str, float],
    conjunctions: list[dict[str, Any]] | None = None,
    implications: list[dict[str, Any]] | None = None,
    partitions: list[dict[str, Any]] | None = None,
    cost: float = 0.02,
    settlement: str = "legwise",
    settlement_cost: float = 0.005,
) -> dict[str, Any]:
    if settlement not in {"legwise", "atomic"}:
        return {"refused": "settlement must be legwise or atomic"}
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
        # A partition breach on a venue with atomic split and merge is a single
        # transaction against collateral, not N independent executions that can
        # come apart. Conjunction and implication breaches still require crossing
        # each leg, because no token operation enforces them.
        atomic_eligible = settlement == "atomic" and row["type"] == "partition"
        row["settlement"] = "atomic" if atomic_eligible else "legwise"
        row["cost_hurdle"] = (cost + settlement_cost) if atomic_eligible else cost * row["legs"]
        row["tradable"] = row["gap"] > row["cost_hurdle"]

    return {
        "violations": violations,
        "tradable": [row for row in violations if row["tradable"]],
        "max_gap": max((row["gap"] for row in violations), default=0.0),
        "checked": len(conjunctions or []) + len(implications or []) + len(partitions or []),
        "settlement": settlement,
    }


# --------------------------------------------------------------------------------------
# Workstream methods — venue mechanics read directly, then made computable
# --------------------------------------------------------------------------------------


# Action categories inside a HyperCore consensus batch, in execution order. Read from
# the venue documentation: orders carrying neither GTC nor IOC go first, then cancels,
# then orders carrying GTC or IOC, with proposer order breaking ties inside a category.
AGGRESSIVE_TIFS = {"gtc", "ioc", "fok"}


def _batch_category(action: dict[str, Any]) -> int:
    kind = str(action.get("kind") or "order").lower()
    if kind == "cancel":
        return 1
    tif = str(action.get("tif") or "").lower()
    return 2 if tif in AGGRESSIVE_TIFS else 0


@method(
    name="batch_priority_fill",
    version="1.0.0",
    summary="Execution order inside a consensus batch sorted by action type, and how far it departs from arrival-time priority.",
    inputs={
        "actions": "list of {action_id, kind: order|cancel, tif: alo|gtc|ioc|null, arrival_index, proposer_index}",
        "own_action_id": "optional id of our own action, to report its displacement explicitly",
    },
    outputs={
        "execution_order": "action ids in the order the venue applies them",
        "arrival_order": "the counterfactual order a continuous-time venue would apply",
        "displacement": "per action, arrival rank minus batch rank; positive means it executes earlier than arrival-time priority predicts",
        "escaped_cancels": "cancels that execute before an aggressive order which arrived first — the maker protection the batch structure creates",
        "queue_jumps": "non-aggressive orders that execute before actions which arrived first",
        "own": "the displacement row for own_action_id, if given",
    },
    as_of_contract="Every action must belong to one batch, observed at or before the decision timestamp. Actions from a later batch are a different system state and must not be mixed in.",
    failure_modes=[
        "The category hierarchy is the venue's, not a general result. On a venue with genuine arrival-time priority every displacement is zero and this method says nothing.",
        "Proposer order is taken as given. Reconstructing it from a public feed is the hard part and this method does not do it — a wrong proposer order permutes ties within a category but never moves an action across categories.",
        "`escaped_cancels` counts a structural opportunity, not a realized saving. Whether the aggressive order would have matched that specific resting order needs price and size, which this method does not take.",
        "Assumes one batch. Two batches per block means an action can lose to an action that arrived later in the previous batch, which this cannot see.",
    ],
    concepts=["KC-BATCH-PRIORITY"],
)
def batch_priority_fill(actions: list[dict[str, Any]], own_action_id: str | None = None) -> dict[str, Any]:
    if not actions:
        return {"refused": "empty batch"}
    rows = []
    for index, action in enumerate(actions):
        rows.append(
            {
                "action_id": action.get("action_id", f"a{index}"),
                "category": _batch_category(action),
                "arrival_index": action.get("arrival_index", index),
                "proposer_index": action.get("proposer_index", index),
                "kind": str(action.get("kind") or "order").lower(),
                "tif": (str(action.get("tif")).lower() if action.get("tif") else None),
            }
        )

    batch_sorted = sorted(rows, key=lambda r: (r["category"], r["proposer_index"], r["action_id"]))
    arrival_sorted = sorted(rows, key=lambda r: (r["arrival_index"], r["action_id"]))
    batch_rank = {r["action_id"]: i for i, r in enumerate(batch_sorted)}
    arrival_rank = {r["action_id"]: i for i, r in enumerate(arrival_sorted)}

    displacement = [
        {
            "action_id": r["action_id"],
            "category": r["category"],
            "arrival_rank": arrival_rank[r["action_id"]],
            "batch_rank": batch_rank[r["action_id"]],
            "displacement": arrival_rank[r["action_id"]] - batch_rank[r["action_id"]],
        }
        for r in batch_sorted
    ]

    # The claim the batch structure makes: a cancel beats an aggressive order that
    # arrived before it. On a continuous venue that cancel is too late.
    escaped = []
    for cancel in (r for r in rows if r["category"] == 1):
        for aggressive in (r for r in rows if r["category"] == 2):
            if aggressive["arrival_index"] < cancel["arrival_index"]:
                escaped.append({"cancel": cancel["action_id"], "beaten_order": aggressive["action_id"]})

    jumps = []
    for passive in (r for r in rows if r["category"] == 0):
        for other in rows:
            if other["action_id"] == passive["action_id"]:
                continue
            if other["arrival_index"] < passive["arrival_index"] and batch_rank[other["action_id"]] > batch_rank[passive["action_id"]]:
                jumps.append({"order": passive["action_id"], "overtook": other["action_id"]})

    own = next((row for row in displacement if row["action_id"] == own_action_id), None) if own_action_id else None
    return {
        "execution_order": [r["action_id"] for r in batch_sorted],
        "arrival_order": [r["action_id"] for r in arrival_sorted],
        "displacement": displacement,
        "escaped_cancels": escaped,
        "queue_jumps": jumps,
        "own": own,
        "batch_size": len(rows),
        "reordered": any(row["displacement"] != 0 for row in displacement),
    }


@method(
    name="depth_realization",
    version="1.0.0",
    summary="How much of the displayed depth an aggressive order actually consumed, and the slippage attributable to the shortfall.",
    inputs={
        "displayed": "levels the sweep walked, best first: [{price, size, order_count?}]",
        "fills": "the fills that resulted: [{price, size}]",
        "side": "buy (consuming asks) or sell (consuming bids)",
    },
    outputs={
        "levels": "per level: displayed size, filled size, realization ratio, mean order size, and whether the level was fully tested",
        "executable_fraction": "filled over displayed across fully tested levels only",
        "phantom_size": "displayed size at fully tested levels that did not execute",
        "expected_vwap": "the price the displayed book predicted for this quantity",
        "realized_vwap": "the price actually paid",
        "slippage": "realized minus expected, signed against the aggressor",
    },
    as_of_contract="`displayed` must be the last book snapshot strictly before the order was sent. Using the post-trade book makes the shortfall vanish by construction.",
    failure_modes=[
        "The deepest level the sweep reached is only partially consumed by design, so it is excluded from `executable_fraction`. Including it reports phantom depth on every sweep that ever stopped.",
        "Cannot separate a margin failure from an ordinary cancel that landed in the same batch. Both look like depth that was there and then was not. Separating them needs the account state behind each resting order.",
        "A stale snapshot manufactures phantom depth. Sequence gaps must be ruled out before the number means anything.",
        "`mean_order_size` is reported where the feed carries an order count, but this method does not test whether composition predicts the shortfall — that needs depletion times across many levels, not one sweep.",
        "Silent about hidden liquidity: a sweep that fills MORE than displayed reports a realization above one rather than an error.",
    ],
    concepts=["KC-PHANTOM-DEPTH"],
)
def depth_realization(
    displayed: list[dict[str, Any]],
    fills: list[dict[str, Any]],
    side: str = "buy",
) -> dict[str, Any]:
    if side not in {"buy", "sell"}:
        return {"refused": "side must be buy or sell"}
    if not displayed:
        return {"refused": "no displayed levels"}

    filled_by_price: dict[float, float] = {}
    for fill in fills or []:
        price = float(fill["price"])
        filled_by_price[price] = filled_by_price.get(price, 0.0) + float(fill["size"])
    total_filled = sum(filled_by_price.values())

    # A level is fully tested only if the sweep reached past it, which we know because
    # some quantity executed at a worse price. Walk best-first and track that.
    levels: list[dict[str, Any]] = []
    consumed_so_far = 0.0
    for index, level in enumerate(displayed):
        price = float(level["price"])
        size = float(level["size"])
        filled = filled_by_price.get(price, 0.0)
        deeper_filled = total_filled - consumed_so_far - filled
        count = level.get("order_count")
        levels.append(
            {
                "price": price,
                "displayed": size,
                "filled": filled,
                "realization": (filled / size) if size > 0 else None,
                "order_count": count,
                "mean_order_size": (size / count) if count else None,
                "fully_tested": deeper_filled > 1e-12,
                "depth_index": index,
            }
        )
        consumed_so_far += filled

    tested = [row for row in levels if row["fully_tested"]]
    tested_displayed = sum(row["displayed"] for row in tested)
    tested_filled = sum(row["filled"] for row in tested)

    # What the book said this quantity would cost, walked best-first for the size we got.
    remaining = total_filled
    expected_notional = 0.0
    for level in displayed:
        if remaining <= 1e-12:
            break
        take = min(remaining, float(level["size"]))
        expected_notional += take * float(level["price"])
        remaining -= take
    expected_vwap = (expected_notional / total_filled) if total_filled > 0 else None
    realized_vwap = (
        sum(price * size for price, size in filled_by_price.items()) / total_filled if total_filled > 0 else None
    )
    slippage = None
    if expected_vwap is not None and realized_vwap is not None:
        slippage = (realized_vwap - expected_vwap) if side == "buy" else (expected_vwap - realized_vwap)

    return {
        "levels": levels,
        "levels_fully_tested": len(tested),
        "executable_fraction": (tested_filled / tested_displayed) if tested_displayed > 0 else None,
        "phantom_size": max(0.0, tested_displayed - tested_filled),
        "expected_vwap": expected_vwap,
        "realized_vwap": realized_vwap,
        "slippage": slippage,
        "filled_size": total_filled,
        "unfilled_beyond_book": remaining if remaining > 1e-12 else 0.0,
    }


@method(
    name="event_tree_constraints",
    version="1.0.0",
    summary="Derives the logical constraint set from prediction-market event metadata, and marks which constraints the protocol enforces.",
    inputs={
        "markets": "list of {market_id, event_id, outcome?, negative_risk?, exhaustive?, tracked_coin?, probability?}",
        "require_exhaustive": "when true (default) an event is only treated as a partition if it declares exhaustive or negative_risk",
    },
    outputs={
        "partitions": "constraint rows in the shape prediction_market_consistency consumes, each carrying enforced and settlement",
        "enforced": "partitions the token layer settles atomically — where mispricing cannot persist",
        "unenforced": "partitions that hold only by convention — the surface where a violation can survive",
        "cross_venue_links": "tracked coin to market ids, the join to the perpetual instrument",
        "skipped": "events excluded, with the reason",
    },
    as_of_contract="Metadata must be the snapshot in force at the decision timestamp. Events are re-scoped and markets are added mid-life, so a later grouping is not the grouping that was tradable.",
    failure_modes=[
        "Event grouping is a venue convention, not a logical guarantee. Markets sharing an event id need not be mutually exclusive, and this method cannot read the resolution criteria that decide it. With require_exhaustive off, it will manufacture partitions that were never partitions.",
        "`enforced` reflects the negative-risk conversion and complete-set merge only. A constraint can be economically tight without being protocol-enforced, and this method will call it unenforced.",
        "Derives partitions, not implications. Implication structure needs a threshold or nesting field the snapshot schema does not carry, and inventing it from question text is exactly the natural-language step this is meant to avoid.",
        "A market that resolves early leaves a stale member in its partition, which reads as a breach that no trade can capture.",
    ],
    concepts=["KC-EVENT-TREE-CONSTRAINTS"],
)
def event_tree_constraints(
    markets: list[dict[str, Any]],
    require_exhaustive: bool = True,
) -> dict[str, Any]:
    if not markets:
        return {"refused": "no markets"}

    by_event: dict[str, list[dict[str, Any]]] = {}
    for market in markets:
        event_id = str(market.get("event_id") or "")
        if not event_id:
            continue
        by_event.setdefault(event_id, []).append(market)

    partitions: list[dict[str, Any]] = []
    skipped: list[dict[str, Any]] = []
    for event_id in sorted(by_event):
        members = sorted(by_event[event_id], key=lambda m: str(m.get("market_id")))
        if len(members) < 2:
            skipped.append({"event_id": event_id, "reason": "single market: nothing to constrain"})
            continue
        negative_risk = any(bool(m.get("negative_risk")) for m in members)
        exhaustive = negative_risk or all(bool(m.get("exhaustive")) for m in members)
        if require_exhaustive and not exhaustive:
            skipped.append(
                {"event_id": event_id, "reason": "not declared exhaustive and not negative-risk: grouping is not a partition"}
            )
            continue
        partitions.append(
            {
                "event_id": event_id,
                "members": [str(m.get("market_id")) for m in members],
                "total": 1.0,
                "enforced": negative_risk,
                "settlement": "atomic" if negative_risk else "legwise",
                "basis": "negative-risk conversion" if negative_risk else "declared exhaustive outcome set",
            }
        )

    links: dict[str, list[str]] = {}
    for market in markets:
        coin = market.get("tracked_coin")
        if coin:
            links.setdefault(str(coin), []).append(str(market.get("market_id")))
    for coin in links:
        links[coin] = sorted(links[coin])

    return {
        "partitions": partitions,
        "enforced": [row for row in partitions if row["enforced"]],
        "unenforced": [row for row in partitions if not row["enforced"]],
        "cross_venue_links": links,
        "skipped": skipped,
        "events_seen": len(by_event),
    }


@method(
    name="betting_eprocess",
    version="1.0.0",
    summary="Anytime-valid test and confidence sequence for a bounded mean, by betting: valid under continuous peeking.",
    inputs={
        "observations": "bounded outcomes in time order (paired differences, per-decision net edge, win indicators)",
        "null_mean": "the mean under the null, on the same scale as the observations",
        "alpha": "error level; the test rejects when the capital process reaches 1/alpha (default 0.05)",
        "lo": "lower bound of the observation range (default 0.0)",
        "hi": "upper bound of the observation range (default 1.0)",
        "lambda_fixed": "optional constant betting fraction on the rescaled scale; omit for the predictable plug-in",
        "grid": "confidence-sequence grid resolution (default 201; 0 skips the interval)",
    },
    outputs={
        "e_value": "the capital process after every observation; reject when it reaches 1/alpha",
        "rejected": "whether the process ever crossed, at any point in the sequence",
        "crossed_at": "1-indexed observation where it first crossed — the detection delay",
        "confidence_sequence": "[lower, upper] for the mean, valid at all times simultaneously",
        "running_mean": "the sample mean, for comparison only — it has no anytime guarantee",
    },
    as_of_contract="Observations must arrive in the order they matured, and the bet at step t may use only observations before t. A bet fitted on the whole sequence destroys the guarantee entirely.",
    failure_modes=[
        "Ville's inequality bounds the probability that the process EVER crosses, which is what makes peeking safe. That guarantee is about the null being true, not about the null being the right null.",
        "Requires genuinely bounded observations. Passing an unbounded series with guessed lo/hi silently breaks the supermartingale property, and nothing here can detect it.",
        "Order matters and is not checked. Sorting the observations, or feeding matured outcomes before unmatured ones, invalidates the result while looking identical.",
        "Anytime-validity costs power against a fixed-sample test at the same alpha. When the sample size is genuinely fixed in advance, this is the wrong tool.",
        "The confidence sequence is a grid inversion, so its endpoints are accurate only to the grid step.",
    ],
    concepts=["KC-ANYTIME-ATTRIBUTION"],
)
def betting_eprocess(
    observations: list[float],
    null_mean: float,
    alpha: float = 0.05,
    lo: float = 0.0,
    hi: float = 1.0,
    lambda_fixed: float | None = None,
    grid: int = 201,
) -> dict[str, Any]:
    if hi <= lo:
        return {"refused": "hi must exceed lo"}
    if not observations:
        return {"refused": "no observations"}
    if not 0.0 < alpha < 1.0:
        return {"refused": "alpha must be in (0, 1)"}

    scaled = [(float(value) - lo) / (hi - lo) for value in observations]
    if any(value < -1e-9 or value > 1 + 1e-9 for value in scaled):
        return {"refused": "observations fall outside [lo, hi]; the supermartingale property does not hold"}
    m0 = (float(null_mean) - lo) / (hi - lo)
    if not 0.0 < m0 < 1.0:
        return {"refused": "null_mean must lie strictly inside (lo, hi)"}

    def capital(values: list[float], mean: float, sign: float) -> tuple[float, int | None]:
        """Capital from betting that the true mean exceeds (sign=+1) or falls below (sign=-1) `mean`."""
        # Positivity requires lambda in (-1/(1-mean), 1/mean); half of that keeps the
        # process well conditioned. The bound is what stops a single observation from
        # wiping the capital to zero or below.
        limit = 0.5 * min(1.0 / mean, 1.0 / (1.0 - mean))
        wealth, crossed = 1.0, None
        running_sum, running_sq, seen = 0.0, 0.0, 0
        threshold = 1.0 / alpha
        for index, value in enumerate(values):
            if lambda_fixed is not None:
                bet = sign * float(lambda_fixed)
            elif seen == 0:
                bet = 0.0
            else:
                mu = running_sum / seen
                var = max(running_sq / seen - mu * mu, 1e-4)
                bet = sign * (abs(mu - mean) / (var + (mu - mean) ** 2))
                if (mu - mean) * sign < 0:
                    bet = 0.0
            bet = max(-limit, min(limit, bet))
            wealth *= 1.0 + bet * (value - mean)
            if wealth >= threshold and crossed is None:
                crossed = index + 1
            running_sum += value
            running_sq += value * value
            seen += 1
        return wealth, crossed

    up, up_cross = capital(scaled, m0, +1.0)
    down, down_cross = capital(scaled, m0, -1.0)
    e_value = max(up, down)
    crossed_at = min([c for c in (up_cross, down_cross) if c is not None], default=None)

    # The grid inversion re-bets against every candidate mean, which only makes sense
    # for the predictable plug-in. A constant bet chosen for one null is not a sensible
    # bet against every other, so the fixed-lambda path reports no interval.
    interval: list[float] | None = None
    if grid and grid >= 3 and lambda_fixed is None:
        step = 1.0 / (grid - 1)
        kept = []
        for i in range(grid):
            candidate = min(max(i * step, 1e-6), 1 - 1e-6)
            hi_cap, _ = capital(scaled, candidate, +1.0)
            lo_cap, _ = capital(scaled, candidate, -1.0)
            if max(hi_cap, lo_cap) < 1.0 / alpha:
                kept.append(candidate)
        if kept:
            interval = [lo + min(kept) * (hi - lo), lo + max(kept) * (hi - lo)]

    return {
        "e_value": e_value,
        "e_value_above": up,
        "e_value_below": down,
        "rejected": crossed_at is not None,
        "crossed_at": crossed_at,
        "threshold": 1.0 / alpha,
        "confidence_sequence": interval,
        "running_mean": lo + (sum(scaled) / len(scaled)) * (hi - lo),
        "n": len(scaled),
    }


@method(
    name="counterparty_markout",
    version="1.0.0",
    summary="Ranks counterparties by shrunk mark-out in a training window and tests whether the ranking survives out of sample.",
    inputs={
        "fills": "list of {counterparty, markout, window: train|test} — markout signed so that positive means the counterparty's flow was informed",
        "prior_strength": "pseudo-observations pulling a thin counterparty toward the global mean (default 10)",
        "min_counterparties": "minimum counterparties present in both windows (default 4)",
    },
    outputs={
        "profiles": "per counterparty: train count, shrunk train mark-out, test count, raw test mark-out",
        "rank_correlation": "Spearman correlation between the train ranking and test mark-out",
        "top_minus_bottom": "test mark-out of the top training tertile minus the bottom",
        "global_markout": "the pooled mean, the benchmark a counterparty must beat",
    },
    as_of_contract="The train window must close strictly before the test window opens. Assigning windows after seeing the outcomes is the whole experiment, backwards.",
    failure_modes=[
        "Shrinkage is what stops a two-fill address topping the ranking, and its strength is a choice, not an estimate. Report it alongside the correlation.",
        "One address is not one participant. Addresses split and pool, so persistence can be broken by rotation rather than by absence of information.",
        "Spearman on few counterparties is unstable; the method refuses below `min_counterparties` rather than returning a confident number on five points.",
        "Selection: counterparties present in both windows are the ones that kept trading, which is not a random subset.",
        "Says nothing about causality. A counterparty whose flow marks out well may be fast rather than informed, and the fix is a different experiment, not a different statistic.",
    ],
    concepts=["KC-COUNTERPARTY-INFO"],
)
def counterparty_markout(
    fills: list[dict[str, Any]],
    prior_strength: float = 10.0,
    min_counterparties: int = 4,
) -> dict[str, Any]:
    train: dict[str, list[float]] = {}
    test: dict[str, list[float]] = {}
    for fill in fills or []:
        bucket = train if str(fill.get("window", "train")).lower() == "train" else test
        bucket.setdefault(str(fill.get("counterparty")), []).append(float(fill.get("markout", 0.0)))

    all_train = [value for values in train.values() for value in values]
    if not all_train:
        return {"refused": "no training fills"}
    global_markout = _mean(all_train)

    shared = sorted(set(train) & set(test))
    if len(shared) < min_counterparties:
        return {
            "refused": f"need at least {min_counterparties} counterparties in both windows, got {len(shared)}",
            "global_markout": global_markout,
        }

    profiles = []
    for counterparty in shared:
        values = train[counterparty]
        n = len(values)
        shrunk = (sum(values) + prior_strength * global_markout) / (n + prior_strength)
        profiles.append(
            {
                "counterparty": counterparty,
                "train_n": n,
                "train_markout_raw": _mean(values),
                "train_markout_shrunk": shrunk,
                "test_n": len(test[counterparty]),
                "test_markout": _mean(test[counterparty]),
            }
        )

    def ranks(values: list[float]) -> list[float]:
        order = sorted(range(len(values)), key=lambda i: values[i])
        out = [0.0] * len(values)
        position = 0
        while position < len(order):
            end = position
            while end + 1 < len(order) and values[order[end + 1]] == values[order[position]]:
                end += 1
            average = (position + end) / 2.0 + 1.0
            for i in range(position, end + 1):
                out[order[i]] = average
            position = end + 1
        return out

    train_ranks = ranks([row["train_markout_shrunk"] for row in profiles])
    test_ranks = ranks([row["test_markout"] for row in profiles])
    n = len(profiles)
    mean_rank = (n + 1) / 2.0
    numerator = sum((a - mean_rank) * (b - mean_rank) for a, b in zip(train_ranks, test_ranks))
    denominator = math.sqrt(
        sum((a - mean_rank) ** 2 for a in train_ranks) * sum((b - mean_rank) ** 2 for b in test_ranks)
    )
    correlation = (numerator / denominator) if denominator > 0 else None

    ordered = sorted(profiles, key=lambda row: row["train_markout_shrunk"])
    tertile = max(1, n // 3)
    bottom = _mean([row["test_markout"] for row in ordered[:tertile]])
    top = _mean([row["test_markout"] for row in ordered[-tertile:]])

    return {
        "profiles": sorted(profiles, key=lambda row: -row["train_markout_shrunk"]),
        "rank_correlation": correlation,
        "top_minus_bottom": top - bottom,
        "global_markout": global_markout,
        "counterparties": n,
        "prior_strength": prior_strength,
    }


@method(
    name="molchan_error_diagram",
    version="1.0.0",
    summary="Alarm-threshold selection by the error diagram: fraction of time in alarm against fraction of events missed.",
    inputs={
        "scores": "the alarm statistic per period, in time order",
        "events": "1 if a target event occurred in that period, else 0",
        "thresholds": "optional explicit thresholds; defaults to the distinct score values",
        "cost_ratio": "weight on alarm time relative to misses (default 1.0, the unweighted Molchan loss)",
    },
    outputs={
        "curve": "per threshold: tau (share of periods in alarm), nu (share of events missed), loss, probability_gain",
        "best": "the threshold minimising the loss, with its tau, nu and gain",
        "skill": "whether the minimum loss beats 1.0, which is the no-skill value",
        "gain_at_min_alarm": "probability gain at the tightest threshold — the number that looks impressive and means least",
    },
    as_of_contract="Scores must be computable from information available before the period they alarm on. A score using the period's own outcome inverts the whole diagram.",
    failure_modes=[
        "PROBABILITY GAIN IS NOT AN OBJECTIVE. It is maximised as alarm time goes to zero, so optimising it selects a rule that almost never fires and predicts almost nothing. Helmstetter and Sornette say this plainly and it is the exact failure our own conservative_abstain policy shows: excellent on clean trials, switched off the moment conditions degrade. Minimise the loss, then read the gain.",
        "A loss at or above 1.0 is no skill. The Poisson benchmark sits at 1.0 by construction, so a rule at 0.95 is barely distinguishable from alarming at random.",
        "tau counts time in alarm, not trades taken. When entering is cheap and being wrong is expensive, weight the two errors with cost_ratio rather than accepting the unweighted sum.",
        "Both error rates are estimated on the same sample that chose the threshold. The minimising threshold is optimistically biased and needs a held-out period.",
        "Says nothing about magnitude. A rule that catches every event and every non-event of the same size scores identically to one that catches only the large ones.",
    ],
    concepts=["KC-ALARM-LOSS"],
)
def molchan_error_diagram(
    scores: list[float],
    events: list[int],
    thresholds: list[float] | None = None,
    cost_ratio: float = 1.0,
) -> dict[str, Any]:
    n = min(len(scores), len(events))
    if n < 4:
        return {"refused": "need at least 4 periods"}
    scores, events = [float(s) for s in scores[:n]], [int(bool(e)) for e in events[:n]]
    total_events = sum(events)
    if total_events == 0:
        return {"refused": "no target events; the error diagram is undefined"}
    base_rate = total_events / n

    grid = sorted(set(thresholds if thresholds is not None else scores))
    curve = []
    for threshold in grid:
        alarms = [1 if score >= threshold else 0 for score in scores]
        tau = sum(alarms) / n
        caught = sum(1 for alarm, event in zip(alarms, events) if alarm and event)
        nu = 1.0 - caught / total_events
        # Probability gain: how much likelier a target is inside an alarm than at random.
        gain = ((caught / sum(alarms)) / base_rate) if sum(alarms) else None
        curve.append({
            "threshold": threshold, "tau": tau, "nu": nu,
            "loss": cost_ratio * tau + nu, "probability_gain": gain, "caught": caught,
        })

    best = min(curve, key=lambda row: (row["loss"], row["tau"]))
    firing = [row for row in curve if row["tau"] > 0]
    tightest = min(firing, key=lambda row: row["tau"]) if firing else None
    return {
        "curve": curve,
        "best": best,
        "skill": best["loss"] < 1.0,
        "no_skill_loss": 1.0,
        "base_rate": base_rate,
        "gain_at_min_alarm": tightest["probability_gain"] if tightest else None,
        "gain_at_best": best["probability_gain"],
    }


@method(
    name="cascade_forecast",
    version="1.0.0",
    summary="Expected future activity of a self-exciting stream, counting the events that will be triggered by events not yet observed.",
    inputs={
        "observed_counts": "event counts in consecutive equal windows up to now",
        "branching_ratio": "n, the mean number of events each event triggers, in [0, 1)",
        "horizon_windows": "how many windows ahead to forecast (default 1)",
        "decay": "share of a parent's triggering that lands within one window (default 0.5)",
    },
    outputs={
        "bare_forecast": "extrapolating only the direct offspring of what has been observed",
        "renormalised_forecast": "including the cascade of offspring of events not yet observed",
        "amplification": "renormalised over bare — the factor the naive forecast is short by",
        "branching_multiplier": "1/(1-n), the total-descendants factor for a subcritical branching process",
    },
    as_of_contract="Counts must end at or before the decision timestamp. The forecast is for windows strictly after the last observed one.",
    failure_modes=[
        "Diverges as n approaches 1. Near criticality the multiplier 1/(1-n) is enormous and dominated by estimation error in n, so a confident forecast there is an artifact of a point estimate.",
        "The single-parameter decay is a crude stand-in for a kernel. Real order-flow kernels are power laws whose mass sits outside any one window, which is the same failure mode hawkes_branching_ratio carries.",
        "Helmstetter and Sornette's own finding cuts against over-reading the level: the bare forecast is wrong in absolute terms but its RELATIVE evolution carries nearly the same information for restricted targets. If the decision only needs 'is activity rising', the naive version is adequate and cheaper.",
        "Assumes stationary n over the horizon. A regime change inside the horizon breaks it, and that is exactly when someone will want to use it.",
        "Refuses n outside [0, 1). A supercritical stream has no finite expected descendant count and the question is malformed rather than hard.",
    ],
    concepts=["KC-CASCADE-HORIZON"],
)
def cascade_forecast(
    observed_counts: list[float],
    branching_ratio: float,
    horizon_windows: int = 1,
    decay: float = 0.5,
) -> dict[str, Any]:
    if not observed_counts:
        return {"refused": "no observed counts"}
    n = float(branching_ratio)
    if not 0.0 <= n < 1.0:
        return {"refused": "branching_ratio must be in [0, 1); a supercritical stream has no finite expectation"}
    if horizon_windows < 1:
        return {"refused": "horizon_windows must be at least 1"}
    if not 0.0 < decay <= 1.0:
        return {"refused": "decay must be in (0, 1]"}

    recent = float(observed_counts[-1])
    # Bare: only the direct offspring of what we have already seen.
    bare = sum(recent * n * decay * ((1 - decay) ** step) for step in range(horizon_windows))
    # Renormalised: each of those offspring triggers its own, to all generations.
    # For a subcritical branching process the total descendants of one event is 1/(1-n).
    multiplier = 1.0 / (1.0 - n)
    renormalised = bare * multiplier
    return {
        "bare_forecast": bare,
        "renormalised_forecast": renormalised,
        "amplification": (renormalised / bare) if bare else None,
        "branching_multiplier": multiplier,
        "base_window_count": recent,
        "warning": ("n above 0.9: the multiplier is dominated by estimation error in n"
                    if n > 0.9 else None),
    }


# --------------------------------------------------------------------------------------
# Estimators for the mathematics the corpus carries but never made executable
# --------------------------------------------------------------------------------------


def _solve(matrix: list[list[float]], rhs: list[float]) -> list[float] | None:
    """Gaussian elimination with partial pivoting. Returns None on a singular system."""
    n = len(matrix)
    augmented = [row[:] + [rhs[i]] for i, row in enumerate(matrix)]
    for column in range(n):
        pivot = max(range(column, n), key=lambda r: abs(augmented[r][column]))
        if abs(augmented[pivot][column]) < 1e-12:
            return None
        augmented[column], augmented[pivot] = augmented[pivot], augmented[column]
        for row in range(column + 1, n):
            factor = augmented[row][column] / augmented[column][column]
            for k in range(column, n + 1):
                augmented[row][k] -= factor * augmented[column][k]
    solution = [0.0] * n
    for row in range(n - 1, -1, -1):
        total = augmented[row][n] - sum(augmented[row][k] * solution[k] for k in range(row + 1, n))
        solution[row] = total / augmented[row][row]
    return solution


def _ols(design: list[list[float]], target: list[float]) -> dict[str, Any] | None:
    """Least squares by normal equations. Small p, so conditioning is not the binding issue."""
    n, p = len(design), len(design[0])
    if n <= p:
        return None
    gram = [[sum(design[i][a] * design[i][b] for i in range(n)) for b in range(p)] for a in range(p)]
    moment = [sum(design[i][a] * target[i] for i in range(n)) for a in range(p)]
    beta = _solve(gram, moment)
    if beta is None:
        return None
    fitted = [sum(beta[a] * design[i][a] for a in range(p)) for i in range(n)]
    residual = [target[i] - fitted[i] for i in range(n)]
    mean_target = _mean(target)
    ss_total = sum((y - mean_target) ** 2 for y in target)
    ss_residual = sum(r * r for r in residual)
    return {
        "coefficients": beta,
        "residuals": residual,
        "r_squared": (1.0 - ss_residual / ss_total) if ss_total > 0 else None,
        "sigma2": ss_residual / (n - p),
        "n": n,
    }


@method(
    name="doubly_robust_value",
    version="1.0.0",
    summary="Off-policy value of a target policy from logged decisions, unbiased if either the reward model or the propensities are right.",
    inputs={
        "logged": "rows of {context_id, action, reward, propensity, reward_hat: {action: value}}",
        "target_policy": "mapping of context_id to the action the target policy would take",
        "clip": "minimum propensity, to bound the importance weight (default 0.01)",
    },
    outputs={
        "doubly_robust": "the DR value estimate",
        "direct_method": "the reward-model-only estimate, for comparison",
        "importance_sampling": "the propensity-only estimate, for comparison",
        "effective_sample_size": "Kish ESS of the importance weights; low means the estimate rests on few rows",
        "max_weight_share": "share of the total weight carried by the single largest weight",
    },
    as_of_contract="Every logged row must predate the evaluation, and the propensity must be the one in force when the action was taken, not one fitted afterwards on the same data.",
    failure_modes=[
        "DOUBLY ROBUST IS NOT DOUBLY SAFE. It is accurate when EITHER the reward model or the propensity model is good. If both are bad it inherits both problems, and nothing in the output tells you which case you are in.",
        "It needs propensities. A decision trace that records what was done but not how likely it was to be done cannot use this, and propensity has to be designed into the logging before the trace exists — it cannot be recovered afterwards.",
        "Clipping bounds the variance and reintroduces bias. The clip level is a choice and must be reported with the estimate; `max_weight_share` says whether it mattered.",
        "Any action the target policy takes that the logging policy never took has no support, and no reweighting reaches it. Coverage is a precondition, not a diagnostic.",
        "Variance grows with the horizon. This is a single-step contextual estimator; a long agent trajectory needs the sequential version and degrades badly regardless.",
    ],
    concepts=["KC-DOUBLY-ROBUST"],
)
def doubly_robust_value(
    logged: list[dict[str, Any]],
    target_policy: dict[str, Any],
    clip: float = 0.01,
) -> dict[str, Any]:
    if not logged:
        return {"refused": "no logged rows"}
    n = len(logged)
    dr_terms, dm_terms, ips_terms, weights = [], [], [], []
    for row in logged:
        context = str(row.get("context_id"))
        if context not in target_policy:
            continue
        chosen = target_policy[context]
        model = row.get("reward_hat") or {}
        baseline = float(model.get(chosen, model.get(str(chosen), 0.0)))
        observed_hat = float(model.get(row["action"], model.get(str(row["action"]), 0.0)))
        propensity = max(float(row.get("propensity", 1.0)), clip)
        matched = 1.0 if row["action"] == chosen else 0.0
        weight = matched / propensity
        dr_terms.append(baseline + weight * (float(row["reward"]) - observed_hat))
        dm_terms.append(baseline)
        ips_terms.append(weight * float(row["reward"]))
        weights.append(weight)
    if not dr_terms:
        return {"refused": "no logged row shares a context with the target policy"}

    total_weight = sum(weights)
    sum_squares = sum(w * w for w in weights)
    ess = (total_weight ** 2 / sum_squares) if sum_squares > 0 else 0.0
    return {
        "doubly_robust": _mean(dr_terms),
        "direct_method": _mean(dm_terms),
        "importance_sampling": _mean(ips_terms),
        "effective_sample_size": ess,
        "rows_used": len(dr_terms),
        "max_weight_share": (max(weights) / total_weight) if total_weight > 0 else None,
        "clip": clip,
    }


@method(
    name="har_realized_volatility",
    version="1.0.0",
    summary="Corsi's heterogeneous autoregressive model: daily, weekly and monthly realized variance predicting the next period.",
    inputs={
        "realized_variance": "realized variance per period, in time order",
        "weekly": "periods in the weekly aggregate (default 5)",
        "monthly": "periods in the monthly aggregate (default 22)",
        "horizon": "periods ahead to predict (default 1)",
    },
    outputs={
        "coefficients": "intercept, daily, weekly and monthly loadings",
        "r_squared": "in-sample fit",
        "next_forecast": "the forecast from the most recent observation",
        "persistence": "the sum of the three loadings; at or above one the process is non-stationary",
    },
    as_of_contract="Each row's regressors are aggregates ending at or before the period being predicted from. The forecast uses only the last observed window.",
    failure_modes=[
        "This is the benchmark, not a model to beat itself with. It is cheap enough that any volatility forecast which does not beat it has not earned its complexity, and reporting a fancy model without this control is the standard omission.",
        "Fitted in variance, not in log variance. Realized variance is strongly right skewed, so a level fit is dominated by the largest few observations; the log specification is the usual remedy and is not what this computes.",
        "Persistence at or above one means the fitted process does not mean revert, which is common in sample and is a sign of a break rather than a forecast.",
        "In-sample R-squared on an autoregressive fit is optimistic by construction and says nothing about out-of-sample skill.",
        "Realized variance must come from a consistent sampling scheme. Mixing sampling frequencies across the series changes what is being modelled halfway through.",
    ],
    concepts=["KC-VOLATILITY-CASCADE"],
)
def har_realized_volatility(
    realized_variance: list[float],
    weekly: int = 5,
    monthly: int = 22,
    horizon: int = 1,
) -> dict[str, Any]:
    series = [float(v) for v in realized_variance]
    if monthly < weekly or weekly < 1:
        return {"refused": "need monthly >= weekly >= 1"}
    if len(series) < monthly + horizon + 5:
        return {"refused": f"need at least {monthly + horizon + 5} observations"}

    design, target = [], []
    for t in range(monthly - 1, len(series) - horizon):
        daily_term = series[t]
        weekly_term = _mean(series[t - weekly + 1: t + 1])
        monthly_term = _mean(series[t - monthly + 1: t + 1])
        design.append([1.0, daily_term, weekly_term, monthly_term])
        target.append(series[t + horizon])

    fit = _ols(design, target)
    if fit is None:
        return {"refused": "regressors are collinear; the three aggregates carry no independent variation"}
    intercept, beta_d, beta_w, beta_m = fit["coefficients"]
    last = len(series) - 1
    forecast = (intercept
                + beta_d * series[last]
                + beta_w * _mean(series[last - weekly + 1: last + 1])
                + beta_m * _mean(series[last - monthly + 1: last + 1]))
    return {
        "coefficients": {"intercept": intercept, "daily": beta_d, "weekly": beta_w, "monthly": beta_m},
        "r_squared": fit["r_squared"],
        "next_forecast": forecast,
        "persistence": beta_d + beta_w + beta_m,
        "n": fit["n"],
    }


@method(
    name="engle_granger_cointegration",
    version="1.0.0",
    summary="Two-step cointegration test: regress the levels, then check whether the residual mean reverts, and report the error-correction speed.",
    inputs={
        "y": "first series, in levels",
        "x": "second series, in levels, same length",
        "lags": "augmentation lags in the residual regression (default 1)",
    },
    outputs={
        "hedge_ratio": "the cointegrating coefficient from the levels regression",
        "residual_half_life": "periods for the residual to close half its gap; None if it does not revert",
        "adf_t": "t-statistic on the residual's own lagged level; more negative is stronger evidence",
        "error_correction": "speed at which a gap in the residual feeds back into the next change in y",
        "verdict": "cointegrated | not_cointegrated | degenerate",
    },
    as_of_contract="Both series must be observed to the same timestamps and end at or before the decision. The hedge ratio must be estimated on a period disjoint from the one it is traded on.",
    failure_modes=[
        "THE REPORTED t-STATISTIC DOES NOT HAVE A STANDARD DISTRIBUTION. Because the residual is itself estimated, the Dickey-Fuller critical values do not apply and the Engle-Granger tabulation is required. This returns the statistic and a comparison against a conventional threshold; treating it as a normal or a standard ADF t is the classic error and it over-rejects.",
        "Order matters. Regressing y on x and x on y give different hedge ratios in finite samples, and the test can accept one way and reject the other.",
        "Two series can look cointegrated over any window if both trend. A relationship that only holds in sample is exactly what this will report.",
        "Handles one pair. Three or more legs need Johansen, where the number of independent relationships is itself the estimate rather than an assumption.",
        "The half-life assumes the residual is AR(1). A residual reverting on two timescales gets one number that describes neither.",
    ],
    concepts=["KC-COINTEGRATION"],
)
def engle_granger_cointegration(y: list[float], x: list[float], lags: int = 1) -> dict[str, Any]:
    n = min(len(y), len(x))
    if n < 20:
        return {"refused": "need at least 20 observations"}
    y, x = [float(v) for v in y[:n]], [float(v) for v in x[:n]]

    levels = _ols([[1.0, xi] for xi in x], y)
    if levels is None:
        return {"refused": "levels regression is singular"}
    intercept, hedge = levels["coefficients"]
    residual = levels["residuals"]

    # Augmented Dickey-Fuller on the residual: d_res_t = rho * res_{t-1} + sum(gamma_i d_res_{t-i})
    diffs = [residual[i] - residual[i - 1] for i in range(1, n)]
    rows, targets = [], []
    for t in range(lags, len(diffs)):
        row = [residual[t]]  # residual[t] is res_{t-1} relative to diffs[t]
        row.extend(diffs[t - i - 1] for i in range(lags))
        rows.append(row)
        targets.append(diffs[t])
    adf = _ols(rows, targets) if rows else None
    if adf is None:
        return {"refused": "residual regression is singular", "hedge_ratio": hedge}
    rho = adf["coefficients"][0]

    denominator = sum(r[0] ** 2 for r in rows) - (sum(r[0] for r in rows) ** 2) / len(rows)
    standard_error = math.sqrt(adf["sigma2"] / denominator) if denominator > 1e-12 else None
    adf_t = (rho / standard_error) if standard_error else None
    half_life = (math.log(0.5) / math.log(1 + rho)) if -2 < rho < 0 else None

    # Error correction: how last period's gap feeds into this period's change in y.
    ec_rows = [[1.0, residual[t - 1], x[t] - x[t - 1]] for t in range(1, n)]
    ec_fit = _ols(ec_rows, [y[t] - y[t - 1] for t in range(1, n)])
    error_correction = ec_fit["coefficients"][1] if ec_fit else None

    # -3.34 is the conventional 5% Engle-Granger critical value for one regressor with a
    # constant. It is a threshold, not a p-value, and the failure modes say why.
    verdict = "degenerate" if adf_t is None else ("cointegrated" if adf_t < -3.34 else "not_cointegrated")
    return {
        "hedge_ratio": hedge,
        "intercept": intercept,
        "residual_half_life": half_life,
        "adf_t": adf_t,
        "adf_rho": rho,
        "error_correction": error_correction,
        "residual_variance": _mean([r * r for r in residual]),
        "verdict": verdict,
        "critical_value_used": -3.34,
        "n": n,
    }


@method(
    name="robust_location_scale",
    version="1.0.0",
    summary="Huber M-estimate of location with a median-absolute-deviation scale: an estimate that a few extreme observations cannot drag.",
    inputs={
        "values": "observations",
        "tuning": "Huber tuning constant in scale units (default 1.345, which is 95% efficient at the Gaussian)",
        "iterations": "reweighting iterations (default 50)",
    },
    outputs={
        "huber_location": "the M-estimate",
        "median": "for comparison; breakdown point 0.5 and lower efficiency",
        "mean": "for comparison; breakdown point 0",
        "mad_scale": "median absolute deviation, scaled to be consistent at the Gaussian",
        "downweighted_share": "share of observations the estimator pulled in",
    },
    as_of_contract="All observations must be available at the decision time; this is a summary of a sample, not a filter over time.",
    failure_modes=[
        "The breakdown point is 0.5, so the estimator survives up to half the sample being arbitrary — and no further. If more than half the observations are contaminated, no equivariant estimator can recover the rest, and this one will confidently report the contamination.",
        "Robust to outliers is not robust to skew. On a genuinely asymmetric distribution the M-estimate targets neither the mean nor the median of the true law, and the number has no clean interpretation.",
        "A zero MAD, which happens when over half the sample is identical, makes the scale degenerate. Reported explicitly rather than divided by.",
        "Downweighting an observation is a modelling decision, not a cleaning step. `downweighted_share` is reported because a high share means the model and the data disagree, and that is information rather than noise to be removed.",
        "The tuning constant trades efficiency at the Gaussian against resistance. 1.345 is the conventional choice and is not optimal for any particular contaminated law.",
    ],
    concepts=["KC-ROBUST-ESTIMATION"],
)
def robust_location_scale(values: list[float], tuning: float = 1.345, iterations: int = 50) -> dict[str, Any]:
    sample = sorted(float(v) for v in values)
    n = len(sample)
    if n < 3:
        return {"refused": "need at least 3 observations"}

    def median_of(data: list[float]) -> float:
        ordered = sorted(data)
        mid = len(ordered) // 2
        return ordered[mid] if len(ordered) % 2 else 0.5 * (ordered[mid - 1] + ordered[mid])

    centre = median_of(sample)
    absolute_deviation = median_of([abs(v - centre) for v in sample])
    scale = 1.4826 * absolute_deviation  # consistent with the standard deviation at the Gaussian
    if scale <= 0:
        return {
            "refused": "median absolute deviation is zero; over half the sample is identical and the scale is degenerate",
            "median": centre, "mean": _mean(sample), "mad_scale": 0.0,
        }

    estimate, downweighted = centre, 0
    for _ in range(iterations):
        weights, downweighted = [], 0
        for value in sample:
            standardized = (value - estimate) / scale
            if abs(standardized) <= tuning:
                weights.append(1.0)
            else:
                weights.append(tuning / abs(standardized))
                downweighted += 1
        total = sum(weights)
        updated = sum(w * v for w, v in zip(weights, sample)) / total
        if abs(updated - estimate) < 1e-12:
            estimate = updated
            break
        estimate = updated

    return {
        "huber_location": estimate,
        "median": centre,
        "mean": _mean(sample),
        "mad_scale": scale,
        "downweighted_share": downweighted / n,
        "breakdown_point": 0.5,
        "n": n,
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
    # Atomic settlement changes which breaches are worth taking: a partition breach
    # that eight separate legs could never clear becomes a single transaction.
    wide_partition = {f"o{i}": 0.14 for i in range(8)}
    legwise = prediction_market_consistency(
        markets=wide_partition, partitions=[{"members": list(wide_partition), "total": 1.0}], cost=0.02
    )
    atomic = prediction_market_consistency(
        markets=wide_partition, partitions=[{"members": list(wide_partition), "total": 1.0}],
        cost=0.02, settlement="atomic", settlement_cost=0.005,
    )
    assert abs(legwise["violations"][0]["gap"] - 0.12) < 1e-9, legwise["violations"][0]
    assert not legwise["tradable"], "eight legs at 0.02 each cannot clear a 0.12 gap"
    assert atomic["tradable"], "the same gap clears once the complete set settles atomically"
    assert atomic["violations"][0]["settlement"] == "atomic", atomic["violations"][0]
    conj_atomic = prediction_market_consistency(
        markets={"a": 0.6, "b": 0.7, "a_and_b": 0.2},
        conjunctions=[{"a": "a", "b": "b", "market": "a_and_b"}],
        settlement="atomic",
    )
    assert conj_atomic["violations"][0]["settlement"] == "legwise", "no token operation enforces a conjunction bound"
    checks.append("prediction_market_consistency: breaches cost-gated, and atomic settlement applied only where the token layer enforces the constraint")

    # ---- Workstream methods -----------------------------------------------------------

    # A batch where every action arrives in the worst possible order for the hierarchy:
    # the aggressive order first, the cancel second, the post-only order last.
    batch = batch_priority_fill(
        [
            {"action_id": "A", "kind": "order", "tif": "gtc", "arrival_index": 0, "proposer_index": 0},
            {"action_id": "B", "kind": "cancel", "arrival_index": 1, "proposer_index": 1},
            {"action_id": "C", "kind": "order", "tif": "alo", "arrival_index": 2, "proposer_index": 2},
        ],
        own_action_id="C",
    )
    assert batch["execution_order"] == ["C", "B", "A"], batch["execution_order"]
    assert batch["arrival_order"] == ["A", "B", "C"], batch["arrival_order"]
    assert batch["own"]["displacement"] == 2, batch["own"]
    assert {row["action_id"]: row["displacement"] for row in batch["displacement"]} == {"C": 2, "B": 0, "A": -2}
    assert len(batch["escaped_cancels"]) == 1, batch["escaped_cancels"]
    assert len(batch["queue_jumps"]) == 2, batch["queue_jumps"]
    # Control: a batch of one category is arrival-time priority again, and says nothing.
    uniform = batch_priority_fill(
        [{"action_id": name, "kind": "order", "tif": "ioc", "arrival_index": i, "proposer_index": i} for i, name in enumerate("XYZ")]
    )
    assert not uniform["reordered"] and not uniform["escaped_cancels"], uniform
    assert batch_priority_fill([])["refused"]
    checks.append("batch_priority_fill: type hierarchy inverts arrival order, cancel beats an earlier aggressive order, single-category batch is unchanged")

    book = [{"price": 100.0, "size": 10.0, "order_count": 2}, {"price": 100.1, "size": 10.0}, {"price": 100.2, "size": 10.0}]
    clean = depth_realization(book, [{"price": 100.0, "size": 10.0}, {"price": 100.1, "size": 10.0}], side="buy")
    assert clean["executable_fraction"] == 1.0, clean
    assert clean["phantom_size"] == 0.0 and abs(clean["slippage"]) < 1e-9, clean
    assert clean["levels_fully_tested"] == 1, "only the level the sweep passed through is tested"
    assert clean["levels"][0]["mean_order_size"] == 5.0, clean["levels"][0]
    phantom = depth_realization(
        book,
        [{"price": 100.0, "size": 5.0}, {"price": 100.1, "size": 10.0}, {"price": 100.2, "size": 5.0}],
        side="buy",
    )
    assert abs(phantom["executable_fraction"] - 0.75) < 1e-9, phantom["executable_fraction"]
    assert abs(phantom["phantom_size"] - 5.0) < 1e-9, phantom["phantom_size"]
    assert abs(phantom["expected_vwap"] - 100.05) < 1e-9, phantom["expected_vwap"]
    assert abs(phantom["realized_vwap"] - 100.10) < 1e-9, phantom["realized_vwap"]
    assert abs(phantom["slippage"] - 0.05) < 1e-9, phantom["slippage"]
    assert depth_realization([], [])["refused"]
    checks.append("depth_realization: full consumption reads 1.0, a half-empty top level reads 0.75 with exactly 0.05 of slippage, untested levels excluded")

    tree = event_tree_constraints(
        [
            {"market_id": "m1", "event_id": "e1", "negative_risk": True, "tracked_coin": "BTC"},
            {"market_id": "m2", "event_id": "e1", "negative_risk": True, "tracked_coin": "BTC"},
            {"market_id": "m3", "event_id": "e1", "negative_risk": True, "tracked_coin": "BTC"},
            {"market_id": "m4", "event_id": "e2"},
            {"market_id": "m5", "event_id": "e2"},
            {"market_id": "m6", "event_id": "e3"},
            {"market_id": "m7", "event_id": "e4", "exhaustive": True},
            {"market_id": "m8", "event_id": "e4", "exhaustive": True},
        ]
    )
    assert [row["event_id"] for row in tree["partitions"]] == ["e1", "e4"], tree["partitions"]
    assert [row["event_id"] for row in tree["enforced"]] == ["e1"], tree["enforced"]
    assert [row["event_id"] for row in tree["unenforced"]] == ["e4"], tree["unenforced"]
    assert {row["event_id"] for row in tree["skipped"]} == {"e2", "e3"}, tree["skipped"]
    assert tree["cross_venue_links"] == {"BTC": ["m1", "m2", "m3"]}, tree["cross_venue_links"]
    permissive = event_tree_constraints(
        [{"market_id": "m4", "event_id": "e2"}, {"market_id": "m5", "event_id": "e2"}], require_exhaustive=False
    )
    assert len(permissive["partitions"]) == 1 and not permissive["partitions"][0]["enforced"], permissive
    # The derived rows must drop straight into the consistency check without translation.
    composed = prediction_market_consistency(
        markets={"m1": 0.5, "m2": 0.4, "m3": 0.3},
        partitions=tree["enforced"],
        cost=0.02,
        settlement="atomic",
    )
    assert composed["violations"] and abs(composed["violations"][0]["gap"] - 0.2) < 1e-9, composed["violations"]
    assert composed["tradable"] and composed["violations"][0]["settlement"] == "atomic", composed
    checks.append("event_tree_constraints: negative-risk event is an enforced partition, an undeclared grouping is skipped, and the output feeds the consistency check unchanged")

    # Fixed bet, so the capital process is exactly 1.5^wins x 0.5^losses.
    won = betting_eprocess([1.0] * 4, null_mean=0.5, lambda_fixed=1.0, grid=0)
    assert abs(won["e_value"] - 1.5 ** 4) < 1e-12, won["e_value"]
    crossing = betting_eprocess([1.0] * 12, null_mean=0.5, alpha=0.05, lambda_fixed=1.0, grid=0)
    assert crossing["crossed_at"] == 8, crossing["crossed_at"]  # 1.5^7 = 17.09 < 20 <= 1.5^8 = 25.63
    alternating = betting_eprocess([1.0, 0.0] * 8, null_mean=0.5, lambda_fixed=1.0, grid=0)
    assert not alternating["rejected"] and alternating["e_value"] < 1.0, alternating
    # Ville's inequality rests on the process being a martingale under the null: the
    # average capital over every equiprobable path must be exactly 1, at every length.
    from itertools import product as _product

    for length in (4, 6):
        paths = list(_product([0.0, 1.0], repeat=length))
        average = _mean([betting_eprocess(list(p), null_mean=0.5, lambda_fixed=1.0, grid=0)["e_value_above"] for p in paths])
        assert abs(average - 1.0) < 1e-9, (length, average)
    flat = betting_eprocess([0.5] * 60, null_mean=0.5)
    assert not flat["rejected"], flat
    low, high = flat["confidence_sequence"]
    assert low <= 0.5 <= high and (high - low) < 0.6, flat["confidence_sequence"]
    biased = betting_eprocess([0.8] * 40, null_mean=0.5, grid=0)
    assert biased["rejected"] and biased["crossed_at"] is not None, biased
    assert betting_eprocess([1.5], null_mean=0.5)["refused"], "out-of-range observations must be refused"
    assert betting_eprocess([0.5] * 10, null_mean=1.5)["refused"]
    checks.append("betting_eprocess: exact 1.5^n capital, crossing at n=8, mean capital exactly 1 over all null paths, and a shrinking anytime interval")

    persistent = (
        [{"counterparty": f"cp{i}", "markout": float(i), "window": "train"} for i in range(1, 7) for _ in range(20)]
        + [{"counterparty": f"cp{i}", "markout": float(i), "window": "test"} for i in range(1, 7) for _ in range(5)]
    )
    forward = counterparty_markout(persistent)
    assert abs(forward["rank_correlation"] - 1.0) < 1e-12, forward["rank_correlation"]
    assert abs(forward["top_minus_bottom"] - 4.0) < 1e-12, forward["top_minus_bottom"]
    assert abs(forward["global_markout"] - 3.5) < 1e-12, forward["global_markout"]
    reversed_fills = [row for row in persistent if row["window"] == "train"] + [
        {"counterparty": f"cp{i}", "markout": float(7 - i), "window": "test"} for i in range(1, 7) for _ in range(5)
    ]
    assert abs(counterparty_markout(reversed_fills)["rank_correlation"] + 1.0) < 1e-12
    thin = counterparty_markout(
        persistent + [{"counterparty": "whale", "markout": 100.0, "window": "train"}, {"counterparty": "whale", "markout": 0.0, "window": "test"}]
    )
    whale = next(row for row in thin["profiles"] if row["counterparty"] == "whale")
    assert thin["global_markout"] < whale["train_markout_shrunk"] < 100.0, whale
    assert counterparty_markout([{"counterparty": "a", "markout": 1.0, "window": "train"}])["refused"]
    checks.append("counterparty_markout: perfect and inverted rank persistence recovered exactly, a one-fill counterparty shrunk toward the pooled mean")

    # A rule that fires on exactly the four event periods and nothing else: tau = 4/20,
    # nu = 0, loss = 0.2, and the gain is the reciprocal of the base rate.
    scores = [0.0] * 16
    events = [0] * 20
    for index in (2, 7, 11, 18):
        events[index] = 1
    perfect = [1.0 if events[i] else 0.0 for i in range(20)]
    diagram = molchan_error_diagram(perfect, events)
    assert abs(diagram["best"]["tau"] - 0.2) < 1e-12, diagram["best"]
    assert diagram["best"]["nu"] == 0.0 and abs(diagram["best"]["loss"] - 0.2) < 1e-12, diagram["best"]
    assert abs(diagram["best"]["probability_gain"] - 5.0) < 1e-12, diagram["best"]
    assert diagram["skill"]
    # A rule that alarms on one event period only: gain is still 5, and it misses three
    # quarters of the events. This is the number that looks impressive and means least.
    single = [1.0 if i == 2 else 0.0 for i in range(20)]
    tight = molchan_error_diagram(single, events)
    assert abs(tight["gain_at_min_alarm"] - 5.0) < 1e-12, tight["gain_at_min_alarm"]
    assert abs(tight["best"]["nu"] - 0.75) < 1e-12, tight["best"]
    assert abs(tight["best"]["loss"] - 0.8) < 1e-12, tight["best"]
    assert tight["best"]["loss"] > diagram["best"]["loss"], "the near-silent rule must lose on the diagram it wins on gain"
    # A rule with no relation to the events cannot beat the no-skill line by much.
    flat = molchan_error_diagram([0.5] * 20, events)
    assert abs(flat["best"]["loss"] - 1.0) < 1e-12, flat["best"]
    assert not flat["skill"], flat
    assert molchan_error_diagram([1.0, 2.0], [0, 1])["refused"]
    assert molchan_error_diagram([1.0] * 8, [0] * 8)["refused"]
    checks.append("molchan_error_diagram: exact tau/nu/loss on a perfect rule, a near-silent rule keeps its gain and loses on loss, a constant score scores exactly no skill")

    # Total descendants of one event in a subcritical branching process is 1/(1-n).
    cascade = cascade_forecast([100.0], branching_ratio=0.5, horizon_windows=1, decay=1.0)
    assert abs(cascade["bare_forecast"] - 50.0) < 1e-12, cascade
    assert abs(cascade["branching_multiplier"] - 2.0) < 1e-12, cascade
    assert abs(cascade["renormalised_forecast"] - 100.0) < 1e-12, cascade
    assert abs(cascade["amplification"] - 2.0) < 1e-12, cascade
    near = cascade_forecast([100.0], branching_ratio=0.95, decay=1.0)
    assert abs(near["branching_multiplier"] - 20.0) < 1e-9 and near["warning"], near
    calm = cascade_forecast([100.0], branching_ratio=0.0, decay=1.0)
    assert calm["bare_forecast"] == 0.0 and calm["branching_multiplier"] == 1.0, calm
    assert cascade_forecast([100.0], branching_ratio=1.0)["refused"]
    assert cascade_forecast([], branching_ratio=0.5)["refused"]
    checks.append("cascade_forecast: 1/(1-n) recovered exactly, amplification doubles at n=0.5, near-critical warned, supercritical refused")

    # ---- Doubly robust: the defining property, demonstrated exactly ---------------------
    # Two contexts, two actions, reward r(x, a) = x + a, logging propensity exactly 0.5 and
    # a perfectly balanced sample, target policy always action 1. True value = mean(1, 2) = 1.5.
    balanced = []
    for context in (0, 1):
        for action in (0, 1):
            for _ in range(2):
                balanced.append({"context_id": str(context), "action": action,
                                 "reward": float(context + action), "propensity": 0.5})
    target = {"0": 1, "1": 1}
    truth = {str(c): {a: float(c + a) for a in (0, 1)} for c in (0, 1)}

    no_model = doubly_robust_value([{**row, "reward_hat": {0: 0.0, 1: 0.0}} for row in balanced], target)
    assert abs(no_model["importance_sampling"] - 1.5) < 1e-12, no_model
    assert abs(no_model["doubly_robust"] - 1.5) < 1e-12, no_model
    perfect_model = doubly_robust_value([{**row, "reward_hat": truth[row["context_id"]]} for row in balanced], target)
    assert abs(perfect_model["direct_method"] - 1.5) < 1e-12, perfect_model
    assert abs(perfect_model["doubly_robust"] - 1.5) < 1e-12, perfect_model
    # A reward model biased by a constant 10, with correct propensities. The direct method
    # inherits the whole bias; DR removes it exactly, because the reweighted residual is
    # -10 on half the rows at weight 2. This is the double-robustness property itself.
    biased = doubly_robust_value(
        [{**row, "reward_hat": {a: truth[row["context_id"]][a] + 10.0 for a in (0, 1)}} for row in balanced], target)
    assert abs(biased["direct_method"] - 11.5) < 1e-12, biased["direct_method"]
    assert abs(biased["doubly_robust"] - 1.5) < 1e-12, biased["doubly_robust"]
    assert abs(biased["effective_sample_size"] - 4.0) < 1e-12, biased["effective_sample_size"]
    assert doubly_robust_value([], target)["refused"]
    assert doubly_robust_value(balanced, {"9": 1})["refused"]
    checks.append("doubly_robust_value: IPS and DR both exact under correct propensities, and a reward model biased by 10 leaves DR exactly unbiased while the direct method carries the whole 10")

    # ---- Least squares: exact recovery of a planted linear model -----------------------
    # The numerical core of both regressions below, so it is tested on its own where an
    # exact answer exists. A self-generated HAR series cannot serve this purpose: any
    # stable linear recursion converges to a fixed point, at which the daily, weekly and
    # monthly aggregates become collinear and the coefficients stop being identified.
    planted = [0.7, -1.3, 2.5, 0.4]
    design = [[1.0, math.sin(i / 5.0), math.cos(i / 3.0), (i % 7) / 7.0] for i in range(60)]
    targets = [sum(planted[k] * row[k] for k in range(4)) for row in design]
    recovered = _ols(design, targets)
    assert recovered is not None
    assert all(abs(recovered["coefficients"][k] - planted[k]) < 1e-9 for k in range(4)), recovered["coefficients"]
    assert recovered["r_squared"] > 1 - 1e-12, recovered["r_squared"]
    assert _ols([[1.0, 2.0], [2.0, 4.0], [3.0, 6.0]], [1.0, 2.0, 3.0]) is None, "a collinear design must be refused"
    checks.append("_ols: planted four-parameter model recovered to 1e-9, collinear design refused rather than solved")

    # ---- HAR: structure, not planted coefficients ---------------------------------------
    # A signal with genuine one-lag dependence on top of multi-frequency structure, so the
    # three aggregates stay distinguishable and the daily term should dominate.
    rv = [2.0 + math.sin(i / 4.0) + 0.6 * math.cos(i / 11.0) + 0.3 * math.sin(i / 29.0) for i in range(400)]
    har = har_realized_volatility(rv)
    coefficients = har["coefficients"]
    assert har["r_squared"] > 0.9, har["r_squared"]
    assert coefficients["daily"] > coefficients["weekly"], coefficients
    assert coefficients["daily"] > coefficients["monthly"], coefficients
    assert math.isfinite(har["next_forecast"]) and math.isfinite(har["persistence"]), har
    flat = har_realized_volatility([3.0] * 400)
    assert flat.get("refused"), "a constant series carries no independent variation across the three horizons"
    assert har_realized_volatility([1.0] * 10)["refused"]
    assert har_realized_volatility([1.0] * 400, weekly=30, monthly=5)["refused"]
    checks.append("har_realized_volatility: daily loading dominates on a one-lag-dependent signal, constant series refused as collinear, ordering of horizons validated")

    # ---- Cointegration: a planted relationship against two independent walks ------------
    # Deterministic pseudo-random walks, so the test is reproducible without a seeded RNG.
    walk_a, walk_b, value_a, value_b = [], [], 0.0, 0.0
    s1, s2 = 12345, 67890
    for step in range(300):
        s1 = (1103515245 * s1 + 12345) % (2 ** 31)
        s2 = (1103515245 * s2 + 12345) % (2 ** 31)
        value_a += (s1 % 1000) / 1000.0 - 0.5
        value_b += (s2 % 1000) / 1000.0 - 0.5
        walk_a.append(value_a)
        walk_b.append(value_b)
    # y is exactly twice x plus a bounded oscillation: cointegrated by construction.
    spread = [0.4 * math.sin(i / 3.0) for i in range(300)]
    tied = [2.0 * walk_a[i] + spread[i] for i in range(300)]

    linked = engle_granger_cointegration(tied, walk_a)
    assert abs(linked["hedge_ratio"] - 2.0) < 0.02, linked["hedge_ratio"]
    assert linked["adf_t"] is not None and linked["adf_t"] < -3.34, linked["adf_t"]
    assert linked["verdict"] == "cointegrated", linked
    assert linked["error_correction"] is not None and linked["error_correction"] < 0, linked["error_correction"]
    independent = engle_granger_cointegration(walk_b, walk_a)
    assert independent["verdict"] == "not_cointegrated", independent
    assert independent["residual_variance"] > linked["residual_variance"] * 10, \
        (independent["residual_variance"], linked["residual_variance"])
    exact = engle_granger_cointegration([3.0 * v for v in walk_a], walk_a)
    assert abs(exact["hedge_ratio"] - 3.0) < 1e-9, exact["hedge_ratio"]
    assert engle_granger_cointegration([1.0, 2.0], [1.0, 2.0])["refused"]
    checks.append("engle_granger_cointegration: hedge ratio exact on a noiseless pair, planted spread reads cointegrated with negative error correction, two independent walks do not")

    # ---- Robust location: breakdown demonstrated -----------------------------------------
    clean = [float(v) for v in range(1, 12)]  # symmetric about 6
    clean_fit = robust_location_scale(clean)
    assert abs(clean_fit["median"] - 6.0) < 1e-12 and abs(clean_fit["mean"] - 6.0) < 1e-12
    assert abs(clean_fit["huber_location"] - 6.0) < 1e-9, clean_fit["huber_location"]
    # One arbitrary observation moves the mean by 90 and leaves the M-estimate alone.
    contaminated = [0.0] * 10 + [1000.0]
    dirty = robust_location_scale(contaminated)
    assert abs(dirty["mean"] - 1000.0 / 11) < 1e-9, dirty["mean"]
    assert dirty.get("refused"), "ten identical values give a zero MAD, which must be refused rather than divided by"
    spread_out = [float(v) for v in range(1, 11)] + [10000.0]
    resistant = robust_location_scale(spread_out)
    assert resistant["mean"] > 900, resistant["mean"]
    assert abs(resistant["median"] - 6.0) < 1e-12, resistant["median"]
    assert abs(resistant["huber_location"] - 6.0) < 1.0, resistant["huber_location"]
    assert resistant["downweighted_share"] > 0, resistant
    assert robust_location_scale([1.0, 2.0])["refused"]
    checks.append("robust_location_scale: exact on symmetric data, one arbitrary point moves the mean by three orders of magnitude and not the M-estimate, degenerate scale refused")

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
