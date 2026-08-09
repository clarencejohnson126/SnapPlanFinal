"""
Schicht 2 — Regelwerke. Raw geometry in, billable Positions out.

Importing this package registers every ruleset. That is the only reason the
trade imports at the bottom exist: a ruleset registers itself via the
`@register_ruleset` decorator, which only runs when its module is imported.

TO ADD A TRADE

  1. Copy app/rules/trockenbau.py as the template.
  2. Add its thresholds to app/rules/thresholds.py, `verified=False` until a
     human has checked them against the printed VOB/C.
  3. Import it at the bottom of this file.

No other file changes. Schicht 1 and Schicht 3 stay untouched — that is the
whole point of the split.
"""

from app.rules.base import (
    Calculation,
    RuleParams,
    Ruleset,
    get_ruleset,
    register_ruleset,
    registered_trades,
    ruleset_catalog,
    run_ruleset,
)
from app.rules.thresholds import (
    Threshold,
    opening_threshold,
    recess_threshold,
    unverified_thresholds,
)

# Ruleset registration — imported for side effects. Keep alphabetical.
from app.rules import bodenbelag  # noqa: F401  (registers BodenbelagRules)
from app.rules import trockenbau  # noqa: F401  (registers TrockenbauRules)

__all__ = [
    "Calculation",
    "RuleParams",
    "Ruleset",
    "Threshold",
    "get_ruleset",
    "opening_threshold",
    "recess_threshold",
    "register_ruleset",
    "registered_trades",
    "ruleset_catalog",
    "run_ruleset",
    "unverified_thresholds",
]
