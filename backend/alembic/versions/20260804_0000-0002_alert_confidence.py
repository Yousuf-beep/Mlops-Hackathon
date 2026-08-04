"""Add alert.confidence.

Revision ID: 0002_alert_confidence
Revises: 0001_initial
Create Date: 2026-08-04 00:00:00+00:00

The anomaly detectors (``app/ml/anomaly.py``) always computed a raw score used
for severity and the explanation text, but discarded it once ``alert`` was
written. The dashboard now shows a 0-1 "how anomalous is this" confidence per
alert, so the score is squashed into that range at persist time
(``confidence_from_score``) and kept instead of thrown away. Nullable because
existing rows, and any future non-ML alert type, have no detector score to
derive one from.
"""

from __future__ import annotations

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "0002_alert_confidence"
down_revision: str | None = "0001_initial"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    """Add the nullable ``alert.confidence`` column."""
    op.add_column("alert", sa.Column("confidence", sa.Float(), nullable=True))


def downgrade() -> None:
    """Drop ``alert.confidence``."""
    op.drop_column("alert", "confidence")
