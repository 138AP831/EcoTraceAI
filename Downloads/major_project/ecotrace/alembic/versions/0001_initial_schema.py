"""Initial schema — all tables from Step 1.

Revision ID: 0001
Revises:
Create Date: 2026-10-20 00:00:00
"""
from __future__ import annotations

from alembic import op
import sqlalchemy as sa

revision = "0001"
down_revision = None
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "users",
        sa.Column("id",              sa.String(), primary_key=True),
        sa.Column("email",           sa.String(), nullable=False, unique=True),
        sa.Column("hashed_password", sa.String(), nullable=False),
        sa.Column("role",            sa.String(), nullable=False, server_default="viewer"),
        sa.Column("is_active",       sa.Boolean(), nullable=False, server_default="1"),
        sa.Column("full_name",       sa.String(), nullable=True),
        sa.Column("created_at",      sa.DateTime(), nullable=False),
        sa.Column("updated_at",      sa.DateTime(), nullable=False),
    )

    op.create_table(
        "facilities",
        sa.Column("id",                       sa.String(), primary_key=True),
        sa.Column("name",                     sa.String(), nullable=False),
        sa.Column("registration_no",          sa.String(), nullable=False, unique=True),
        sa.Column("authority",                sa.String(), nullable=False),
        sa.Column("state",                    sa.String(), nullable=False),
        sa.Column("registration_status",      sa.String(), nullable=False),
        sa.Column("registration_valid_until", sa.Date(),   nullable=True),
        sa.Column("geofence_lat",             sa.Float(),  nullable=True),
        sa.Column("geofence_lng",             sa.Float(),  nullable=True),
        sa.Column("geofence_radius_m",        sa.Float(),  nullable=True),
        sa.Column("authorized_categories",    sa.JSON(),   nullable=False),
        sa.Column("daily_capacity_kg",        sa.Float(),  nullable=True),
        sa.Column("booked_capacity_kg",       sa.Float(),  nullable=True),
        sa.Column("created_at",               sa.DateTime(), nullable=False),
        sa.Column("updated_at",               sa.DateTime(), nullable=False),
    )

    op.create_table(
        "pickers",
        sa.Column("id",                sa.String(),  primary_key=True),
        sa.Column("name",              sa.String(),  nullable=False),
        sa.Column("phone",             sa.String(),  nullable=False, unique=True),
        sa.Column("is_blocked",        sa.Boolean(), nullable=False, server_default="0"),
        sa.Column("risk_flag",         sa.String(),  nullable=True),
        sa.Column("total_submissions", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("total_rejections",  sa.Integer(), nullable=False, server_default="0"),
        sa.Column("created_at",        sa.DateTime(), nullable=False),
        sa.Column("updated_at",        sa.DateTime(), nullable=False),
    )

    op.create_table(
        "producers",
        sa.Column("id",         sa.String(), primary_key=True),
        sa.Column("name",       sa.String(), nullable=False),
        sa.Column("state",      sa.String(), nullable=False),
        sa.Column("created_at", sa.DateTime(), nullable=False),
        sa.Column("updated_at", sa.DateTime(), nullable=False),
    )

    op.create_table(
        "obligations",
        sa.Column("id",                sa.String(), primary_key=True),
        sa.Column("producer_id",       sa.String(), sa.ForeignKey("producers.id"), nullable=False),
        sa.Column("category",          sa.String(), nullable=False),
        sa.Column("compliance_period", sa.String(), nullable=False),
        sa.Column("target_kg",         sa.Float(),  nullable=False),
        sa.Column("fulfilled_kg",      sa.Float(),  nullable=False, server_default="0"),
        sa.Column("created_at",        sa.DateTime(), nullable=False),
        sa.Column("updated_at",        sa.DateTime(), nullable=False),
        sa.UniqueConstraint("producer_id", "category", "compliance_period",
                            name="uq_obligation_period"),
    )

    op.create_table(
        "collections",
        sa.Column("id",                    sa.String(),  primary_key=True),
        sa.Column("picker_id",             sa.String(),  sa.ForeignKey("pickers.id"),   nullable=False),
        sa.Column("facility_id",           sa.String(),  sa.ForeignKey("facilities.id"), nullable=False),
        sa.Column("item_state",            sa.String(),  nullable=False),
        sa.Column("category",              sa.String(),  nullable=False),
        sa.Column("serial_or_imei",        sa.String(),  nullable=True),
        sa.Column("declared_weight_kg",    sa.Float(),   nullable=False),
        sa.Column("weighbridge_weight_kg", sa.Float(),   nullable=True),
        sa.Column("collection_state",      sa.String(),  nullable=False),
        sa.Column("facility_state",        sa.String(),  nullable=False),
        sa.Column("inter_state",           sa.Boolean(), nullable=False, server_default="0"),
        sa.Column("image_hash",            sa.String(),  nullable=False),
        sa.Column("intake_at",             sa.DateTime(), nullable=False),
        sa.Column("status",                sa.String(),  nullable=False, server_default="submitted"),
        sa.Column("unit_normalised",       sa.Boolean(), nullable=False, server_default="0"),
        sa.Column("created_at",            sa.DateTime(), nullable=False),
        sa.Column("updated_at",            sa.DateTime(), nullable=False),
    )

    op.create_table(
        "evidence_assessments",
        sa.Column("id",               sa.String(), primary_key=True),
        sa.Column("collection_id",    sa.String(), sa.ForeignKey("collections.id"), nullable=False),
        sa.Column("mode",             sa.String(), nullable=False),
        sa.Column("component_scores", sa.JSON(),   nullable=False),
        sa.Column("gates",            sa.JSON(),   nullable=False),
        sa.Column("score",            sa.Float(),  nullable=True),
        sa.Column("decision",         sa.String(), nullable=False),
        sa.Column("reason",           sa.String(), nullable=False),
        sa.Column("weight_source",    sa.String(), nullable=True),
        sa.Column("created_at",       sa.DateTime(), nullable=False),
        sa.Column("updated_at",       sa.DateTime(), nullable=False),
    )

    op.create_table(
        "completion_records",
        sa.Column("id",                   sa.String(),  primary_key=True),
        sa.Column("collection_id",        sa.String(),  sa.ForeignKey("collections.id"), nullable=False),
        sa.Column("evidence_type",        sa.String(),  nullable=True),
        sa.Column("submitted_at",         sa.DateTime(), nullable=True),
        sa.Column("invoice_weight_kg",    sa.Float(),   nullable=True),
        sa.Column("invoice_buyer_id",     sa.String(),  nullable=True),
        sa.Column("invoice_number",       sa.String(),  nullable=True, unique=True),
        sa.Column("facility_revalidated", sa.Boolean(), nullable=False, server_default="0"),
        sa.Column("manifest_present",     sa.Boolean(), nullable=False, server_default="0"),
        sa.Column("passed",               sa.Boolean(), nullable=False, server_default="0"),
        sa.Column("failure_reasons",      sa.JSON(),    nullable=False),
        sa.Column("created_at",           sa.DateTime(), nullable=False),
        sa.Column("updated_at",           sa.DateTime(), nullable=False),
    )

    op.create_table(
        "narration_assessments",
        sa.Column("id",               sa.String(),  primary_key=True),
        sa.Column("collection_id",    sa.String(),  sa.ForeignKey("collections.id"), nullable=False),
        sa.Column("hard_gates",       sa.JSON(),    nullable=False),
        sa.Column("soft_scores",      sa.JSON(),    nullable=False),
        sa.Column("score",            sa.Float(),   nullable=True),
        sa.Column("decision",         sa.String(),  nullable=False),
        sa.Column("reason",           sa.String(),  nullable=False),
        sa.Column("corpus_version",   sa.String(),  nullable=False),
        sa.Column("sanitizer_passed", sa.Boolean(), nullable=False, server_default="1"),
        sa.Column("created_at",       sa.DateTime(), nullable=False),
        sa.Column("updated_at",       sa.DateTime(), nullable=False),
    )

    op.create_table(
        "badges",
        sa.Column("id",               sa.String(),  primary_key=True),
        sa.Column("collection_id",    sa.String(),  sa.ForeignKey("collections.id"), nullable=False, unique=True),
        sa.Column("facility_id",      sa.String(),  sa.ForeignKey("facilities.id"), nullable=False),
        sa.Column("category",         sa.String(),  nullable=False),
        sa.Column("weight_kg",        sa.Float(),   nullable=False),
        sa.Column("evidence_score",   sa.Float(),   nullable=True),
        sa.Column("narration_score",  sa.Float(),   nullable=True),
        sa.Column("status",           sa.String(),  nullable=False, server_default="unconsumed"),
        sa.Column("issued_at",        sa.DateTime(), nullable=False),
        sa.Column("revoked_at",       sa.DateTime(), nullable=True),
        sa.Column("revocation_reason",sa.String(),  nullable=True),
        sa.Column("created_at",       sa.DateTime(), nullable=False),
        sa.Column("updated_at",       sa.DateTime(), nullable=False),
    )

    op.create_table(
        "badge_references",
        sa.Column("id",              sa.String(), primary_key=True),
        sa.Column("badge_id",        sa.String(), sa.ForeignKey("badges.id"), nullable=False, unique=True),
        sa.Column("producer_id",     sa.String(), sa.ForeignKey("producers.id"), nullable=False),
        sa.Column("obligation_id",   sa.String(), sa.ForeignKey("obligations.id"), nullable=False),
        sa.Column("referenced_at",   sa.DateTime(), nullable=False),
        sa.Column("weight_kg_applied",sa.Float(), nullable=False),
        sa.Column("created_at",      sa.DateTime(), nullable=False),
        sa.Column("updated_at",      sa.DateTime(), nullable=False),
    )

    op.create_table(
        "media_files",
        sa.Column("id",             sa.String(),  primary_key=True),
        sa.Column("collection_id",  sa.String(),  sa.ForeignKey("collections.id"), nullable=False),
        sa.Column("filename",       sa.String(),  nullable=False),
        sa.Column("content_type",   sa.String(),  nullable=False),
        sa.Column("size_bytes",     sa.Integer(), nullable=False),
        sa.Column("storage_path",   sa.String(),  nullable=False),
        sa.Column("file_purpose",   sa.String(),  nullable=False, server_default="evidence_media"),
        sa.Column("uploaded_by",    sa.String(),  sa.ForeignKey("users.id"), nullable=True),
        sa.Column("created_at",     sa.DateTime(), nullable=False),
        sa.Column("updated_at",     sa.DateTime(), nullable=False),
    )

    op.create_table(
        "audit_logs",
        sa.Column("id",          sa.String(),  primary_key=True),
        sa.Column("entity_type", sa.String(),  nullable=False),
        sa.Column("entity_id",   sa.String(),  nullable=False),
        sa.Column("action",      sa.String(),  nullable=False),
        sa.Column("payload",     sa.JSON(),    nullable=False),
        sa.Column("at",          sa.DateTime(), nullable=False),
    )


def downgrade() -> None:
    for table in [
        "audit_logs", "media_files", "badge_references", "badges",
        "narration_assessments", "completion_records", "evidence_assessments",
        "collections", "obligations", "producers", "pickers",
        "facilities", "users",
    ]:
        op.drop_table(table)
