"""Routes: give railway_tracks a stable route code and key schedules by track.

A line can now have several routes (Central forks at Kalyan into Kasara
and Karjat), so a schedule template has to name the route it runs on, not
just the line.

Revision ID: 0002
Revises: 0001
Create Date: 2026-09-23
"""

from collections.abc import Sequence

import sqlalchemy as sa

from alembic import op

revision: str = "0002"
down_revision: str | None = "0001"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.add_column("railway_tracks", sa.Column("code", sa.String(length=16), nullable=True))
    # Before this revision every line had exactly one track, so the line
    # code is a unique, meaningful route code for existing rows.
    op.execute(
        "UPDATE railway_tracks SET code = railway_lines.code "
        "FROM railway_lines WHERE railway_lines.id = railway_tracks.line_id"
    )
    op.alter_column("railway_tracks", "code", nullable=False)
    op.create_index("ix_railway_tracks_code", "railway_tracks", ["code"], unique=True)

    op.add_column(
        "schedules",
        sa.Column("track_id", sa.Integer(), sa.ForeignKey("railway_tracks.id"), nullable=True),
    )
    op.execute(
        "UPDATE schedules SET track_id = railway_tracks.id "
        "FROM railway_tracks WHERE railway_tracks.line_id = schedules.line_id"
    )
    op.alter_column("schedules", "track_id", nullable=False)
    op.create_index("ix_schedules_track_id", "schedules", ["track_id"])


def downgrade() -> None:
    op.drop_index("ix_schedules_track_id", table_name="schedules")
    op.drop_column("schedules", "track_id")
    op.drop_index("ix_railway_tracks_code", table_name="railway_tracks")
    op.drop_column("railway_tracks", "code")
