"""ESEA FOI data cleaning pipeline — raw attachments → ONS 18+1 long format.

See `research/esea-cleaning-analysis.md` for the coverage/shape analysis that
motivated this pipeline and the plan at
`.claude/plans/precious-snuggling-iverson.md` for the design.
"""

from esea_cleaning.force_registry import ForceEntry, list_forces
from esea_cleaning.ethnicity import (
    ONS_CATEGORIES,
    apply_mapping,
    load_force_config,
    load_ons_categories,
)

__all__ = [
    "ForceEntry",
    "ONS_CATEGORIES",
    "apply_mapping",
    "list_forces",
    "load_force_config",
    "load_ons_categories",
]
