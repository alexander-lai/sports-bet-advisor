import pytest

from app.services.kelly import (
    edge_pct,
    evaluate_prop,
    expected_value,
    grade,
    kelly_fraction,
    over_probability,
    profit_for,
)


def test_kelly_matches_formula():
    # b = 1.0, p = 0.6 -> f = (0.6 - 0.4) / 1 = 0.2
    assert kelly_fraction(0.6, 2.0) == pytest.approx(0.2)
    # b = 0.909, p = 0.55 -> (0.909*0.55 - 0.45) / 0.909
    expected = (0.909 * 0.55 - 0.45) / 0.909
    assert kelly_fraction(0.55, 1.909) == pytest.approx(expected)


def test_kelly_never_negative():
    assert kelly_fraction(0.4, 1.909) == 0.0
    assert kelly_fraction(0.9, 1.0) == 0.0


def test_over_probability_is_half_at_the_line():
    assert over_probability(20.5, 20.5, 5) == pytest.approx(0.5)
    assert over_probability(25, 20.5, 5) > 0.8


def test_evaluate_prop_picks_better_side():
    over = evaluate_prop(28, 22.5, 5, 1.909, 1.909)
    under = evaluate_prop(17, 22.5, 5, 1.909, 1.909)
    assert over["side"] == "over" and over["kelly_fraction"] > 0
    assert under["side"] == "under" and under["edge_pct"] > 0
    assert over["expected_value"] == pytest.approx(
        expected_value(over["win_prob"], 1.909)
    )


def test_edge_pct_is_signed_toward_side():
    assert edge_pct(22, 20, "over") == pytest.approx(10)
    assert edge_pct(18, 20, "under") == pytest.approx(10)


def test_grading_and_profit():
    assert grade("over", 20.5, 21) == "win"
    assert grade("under", 20.5, 21) == "loss"
    assert grade("over", 20, 20) == "push"
    assert profit_for("win", 10, 1.909) == pytest.approx(9.09)
    assert profit_for("loss", 10, 1.909) == -10
    assert profit_for("push", 10, 1.909) == 0
