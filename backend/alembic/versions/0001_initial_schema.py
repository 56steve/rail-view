"""Initial schema: stations, railway_lines, railway_tracks, track_segments,
stations_on_routes, trains, train_runs, train_positions, schedules.

Revision ID: 0001
Revises:
Create Date: 2026-09-18
"""

from collections.abc import Sequence

import geoalchemy2
import sqlalchemy as sa

from alembic import op

revision: str = "0001"
down_revision: str | None = None
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.execute("CREATE EXTENSION IF NOT EXISTS postgis")

    op.create_table(
        "stations",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("code", sa.String(length=8), nullable=False),
        sa.Column("name", sa.String(length=80), nullable=False),
        sa.Column(
            "geom",
            geoalchemy2.Geometry(geometry_type="POINT", srid=4326),
            nullable=False,
        ),
    )
    op.create_index("ix_stations_code", "stations", ["code"], unique=True)

    op.create_table(
        "railway_lines",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("code", sa.String(length=8), nullable=False),
        sa.Column("name", sa.String(length=80), nullable=False),
        sa.Column("color_hex", sa.String(length=7), nullable=False),
    )
    op.create_index("ix_railway_lines_code", "railway_lines", ["code"], unique=True)

    op.create_table(
        "railway_tracks",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("line_id", sa.Integer(), sa.ForeignKey("railway_lines.id"), nullable=False),
        sa.Column("name", sa.String(length=120), nullable=False),
        sa.Column(
            "geom",
            geoalchemy2.Geometry(geometry_type="LINESTRING", srid=4326),
            nullable=False,
        ),
        sa.Column("length_m", sa.Float(), nullable=False),
    )
    op.create_index("ix_railway_tracks_line_id", "railway_tracks", ["line_id"])

    op.create_table(
        "track_segments",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("track_id", sa.Integer(), sa.ForeignKey("railway_tracks.id"), nullable=False),
        sa.Column("from_station_id", sa.Integer(), sa.ForeignKey("stations.id"), nullable=False),
        sa.Column("to_station_id", sa.Integer(), sa.ForeignKey("stations.id"), nullable=False),
        sa.Column("sequence", sa.Integer(), nullable=False),
        sa.Column(
            "geom",
            geoalchemy2.Geometry(geometry_type="LINESTRING", srid=4326),
            nullable=False,
        ),
        sa.Column("length_m", sa.Float(), nullable=False),
    )
    op.create_index("ix_track_segments_track_id", "track_segments", ["track_id"])

    op.create_table(
        "stations_on_routes",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("track_id", sa.Integer(), sa.ForeignKey("railway_tracks.id"), nullable=False),
        sa.Column("station_id", sa.Integer(), sa.ForeignKey("stations.id"), nullable=False),
        sa.Column("sequence", sa.Integer(), nullable=False),
        sa.Column("chainage_m", sa.Float(), nullable=False),
    )
    op.create_index("ix_stations_on_routes_track_id", "stations_on_routes", ["track_id"])
    op.create_index("ix_stations_on_routes_station_id", "stations_on_routes", ["station_id"])

    op.create_table(
        "trains",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("identifier", sa.String(length=16), nullable=False),
        sa.Column("train_type", sa.String(length=8), nullable=False),
        sa.Column("rake_length", sa.Integer(), nullable=False, server_default="12"),
    )
    op.create_index("ix_trains_identifier", "trains", ["identifier"], unique=True)

    op.create_table(
        "train_runs",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("train_id", sa.Integer(), sa.ForeignKey("trains.id"), nullable=False),
        sa.Column("line_id", sa.Integer(), sa.ForeignKey("railway_lines.id"), nullable=False),
        sa.Column("direction_forward", sa.Boolean(), nullable=False),
        sa.Column("scheduled_start", sa.DateTime(timezone=True), nullable=False),
        sa.Column("scheduled_end", sa.DateTime(timezone=True), nullable=False),
        sa.Column("actual_start", sa.DateTime(timezone=True), nullable=True),
        sa.Column("status", sa.String(length=16), nullable=False, server_default="scheduled"),
    )
    op.create_index("ix_train_runs_train_id", "train_runs", ["train_id"])

    op.create_table(
        "train_positions",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("train_run_id", sa.Integer(), sa.ForeignKey("train_runs.id"), nullable=False),
        sa.Column("recorded_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("chainage_m", sa.Float(), nullable=False),
        sa.Column("speed_kmh", sa.Float(), nullable=False),
        sa.Column(
            "geom",
            geoalchemy2.Geometry(geometry_type="POINT", srid=4326),
            nullable=False,
        ),
    )
    op.create_index("ix_train_positions_train_run_id", "train_positions", ["train_run_id"])
    op.create_index("ix_train_positions_recorded_at", "train_positions", ["recorded_at"])

    op.create_table(
        "schedules",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("line_id", sa.Integer(), sa.ForeignKey("railway_lines.id"), nullable=False),
        sa.Column("train_type", sa.String(length=8), nullable=False),
        sa.Column("direction_forward", sa.Boolean(), nullable=False),
        sa.Column("station_id", sa.Integer(), sa.ForeignKey("stations.id"), nullable=False),
        sa.Column("sequence", sa.Integer(), nullable=False),
        sa.Column("scheduled_offset_s", sa.Float(), nullable=False),
        sa.Column("dwell_s", sa.Float(), nullable=False, server_default="0"),
    )
    op.create_index("ix_schedules_line_id", "schedules", ["line_id"])


def downgrade() -> None:
    op.drop_table("schedules")
    op.drop_table("train_positions")
    op.drop_table("train_runs")
    op.drop_table("trains")
    op.drop_table("stations_on_routes")
    op.drop_table("track_segments")
    op.drop_table("railway_tracks")
    op.drop_table("railway_lines")
    op.drop_table("stations")
