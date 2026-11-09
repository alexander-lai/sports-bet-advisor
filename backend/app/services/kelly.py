"""Win probability, edge and Kelly criterion sizing.

Kelly: f = (b*p - q) / b, where b = decimal odds - 1, p = win
probability and q = 1 - p. Negative values mean "don't bet" and are
clamped to 0.
"""
import math

import numpy as np
from scipy.stats import norm


def kelly_fraction(win_prob, decimal_odds):
    b = decimal_odds - 1.0
    if b <= 0:
        return 0.0
    q = 1.0 - win_prob
    return max(0.0, (b * win_prob - q) / b)


def kelly_fraction_vec(win_prob, decimal_odds):
    b = np.asarray(decimal_odds, dtype=float) - 1.0
    p = np.asarray(win_prob, dtype=float)
    with np.errstate(divide="ignore", invalid="ignore"):
        f = np.where(b > 0, (b * p - (1.0 - p)) / b, 0.0)
    return np.clip(f, 0.0, None)


def expected_value(win_prob, decimal_odds):
    """Expected profit per 1 unit staked."""
    return win_prob * decimal_odds - 1.0


def over_probability(predicted, line, sigma):
    """P(actual > line) assuming a normal error around the prediction."""
    sigma = max(float(sigma), 1e-6)
    z = (line - predicted) / sigma
    return 0.5 * (1.0 - math.erf(z / math.sqrt(2.0)))


def over_probability_vec(predicted, line, sigma):
    sigma = np.maximum(np.asarray(sigma, dtype=float), 1e-6)
    return 1.0 - norm.cdf((np.asarray(line) - predicted) / sigma)


def edge_pct(predicted, line, side):
    """How far the projection sits from the line, in the bet's favour."""
    if not line:
        return 0.0
    diff = predicted - line if side == "over" else line - predicted
    return diff / line * 100.0


def evaluate_prop(predicted, line, sigma, over_odds, under_odds):
    """Pick the side with the higher expected value and size it."""
    p_over = over_probability(predicted, line, sigma)
    ev_over = expected_value(p_over, over_odds)
    ev_under = expected_value(1.0 - p_over, under_odds)
    if ev_over >= ev_under:
        side, prob, odds, ev = "over", p_over, over_odds, ev_over
    else:
        side, prob, odds, ev = "under", 1 - p_over, under_odds, ev_under
    return {
        "side": side,
        "win_prob": prob,
        "odds": odds,
        "expected_value": ev,
        "kelly_fraction": kelly_fraction(prob, odds),
        "edge_pct": edge_pct(predicted, line, side),
    }


def grade(side, line, actual):
    if actual == line:
        return "push"
    went_over = actual > line
    return "win" if went_over == (side == "over") else "loss"


def profit_for(outcome, stake, odds):
    if outcome == "win":
        return stake * (odds - 1.0)
    if outcome == "loss":
        return -stake
    return 0.0


def confidence_label(win_prob):
    if win_prob >= 0.62:
        return "high"
    if win_prob >= 0.56:
        return "medium"
    return "low"
