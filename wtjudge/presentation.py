"""Shared score and verdict presentation; never changes judging or raw scores."""
from __future__ import annotations

from collections.abc import Mapping


# Sampled from the user's references. Intermediate score bands use the same
# green hue; custom problem scores are normalised against their own full mark.
SCORE_COLOURS = ("#ffffff", "#cbeecb", "#9fdf9f", "#7ed57e", "#5cc95c")
SCORE_FOREGROUND = "#16221b"
STATUS_COLOURS = {
    "AC": ("#5cc95c", SCORE_FOREGROUND),
    "WA": ("#ffffff", SCORE_FOREGROUND),
    "RE": ("#8e44ad", "#ffffff"),
    "CE": ("#ff9900", "#ffffff"),
    "TLE": ("#052242", "#ffffff"),
    "MLE": ("#052242", "#ffffff"),
    "OUTPUT_LIMIT": ("#052242", "#ffffff"),
    "NO_OUTPUT": ("#eee2f4", "#6f348a"),
    "NO_SOURCE": ("#f1f3f0", "#697565"),
    "AMBIGUOUS_SOURCE": ("#fff1cf", "#805c13"),
    "SYSTEM_ERROR": ("#fbe9e4", "#a84432"),
    "CANCELLED": ("#f0f3ed", "#63705d"),
}
UNIFORM_ERRORS = frozenset({"RE", "CE", "TLE", "MLE", "NO_OUTPUT", "OUTPUT_LIMIT", "NO_SOURCE"})


def score_colours(score, full_score):
    """Return opaque background and readable text for a proportional score."""
    if score <= 0 or full_score <= 0:
        index = 0
    elif score >= full_score:
        index = 4
    elif score * 100 <= full_score * 30:
        index = 1
    elif score * 100 <= full_score * 60:
        index = 2
    else:
        index = 3
    return SCORE_COLOURS[index], SCORE_FOREGROUND


def _field(point, name):
    return point[name] if isinstance(point, Mapping) else getattr(point, name)


def uniform_error(points, expected_ids=None):
    """Label a complete homogeneous execution error, with no scoring changes.

    Callers with a recorded testcase manifest must pass it, so a few finished
    errors in a still-running submission cannot masquerade as a complete RE.
    Older saved batches may have no manifest; their completed-record guard is
    the caller's responsibility. Duplicate or foreign identities never qualify.
    All-WA stays a numeric zero on white, as in the reference score table.
    """
    points = list(points)
    if not points:
        return ""
    identities = [(_field(p, "student_id"), _field(p, "problem_id"), _field(p, "testcase_id")) for p in points]
    if len(set(identities)) != len(identities) or len({key[:2] for key in identities}) != 1:
        return ""
    if expected_ids is not None:
        expected = list(expected_ids)
        if len(expected) != len(set(expected)) or {key[2] for key in identities} != set(expected):
            return ""
    statuses = {_field(p, "status") for p in points}
    status = next(iter(statuses)) if len(statuses) == 1 else ""
    return status if status in UNIFORM_ERRORS else ""
