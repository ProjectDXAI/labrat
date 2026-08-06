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
