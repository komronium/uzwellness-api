"""Add core data integrity checks.

Revision ID: f9f0a1b2c3d4
Revises: f8e3a4b5c6d7
Create Date: 2026-06-07 00:00:00.000000
"""

from collections.abc import Sequence

from alembic import op

revision: str = "f9f0a1b2c3d4"
down_revision: str | None = "f8e3a4b5c6d7"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


CHECKS: tuple[tuple[str, str, str], ...] = (
    (
        "bookings",
        "ck_bookings_date_order",
        "(booking_type = 'session' AND check_out >= check_in) "
        "OR (booking_type <> 'session' AND check_out > check_in)",
    ),
    ("bookings", "ck_bookings_guests_positive", "guests > 0"),
    ("bookings", "ck_bookings_adults_non_negative", "adults IS NULL OR adults >= 0"),
    (
        "bookings",
        "ck_bookings_children_non_negative",
        "children IS NULL OR children >= 0",
    ),
    # ck_bookings_rooms_count_positive already exists (b6c4d9e3f0a2).
    ("bookings", "ck_bookings_final_price_non_negative", "final_price >= 0"),
    (
        "bookings",
        "ck_bookings_original_price_non_negative",
        "original_price IS NULL OR original_price >= 0",
    ),
    (
        "bookings",
        "ck_bookings_commission_non_negative",
        "commission_snapshot IS NULL OR commission_snapshot >= 0",
    ),
    (
        "bookings",
        "ck_bookings_commission_percent_range",
        "commission_percent_snapshot IS NULL "
        "OR commission_percent_snapshot BETWEEN 0 AND 100",
    ),
    (
        "bookings",
        "ck_bookings_agent_discount_percent_range",
        "agent_discount_percent_snapshot IS NULL "
        "OR agent_discount_percent_snapshot BETWEEN 0 AND 100",
    ),
    (
        "bookings",
        "ck_bookings_free_cancellation_days_non_negative",
        "free_cancellation_days IS NULL OR free_cancellation_days >= 0",
    ),
    (
        "bookings",
        "ck_bookings_cancellation_penalty_percent_range",
        "cancellation_penalty_percent IS NULL "
        "OR cancellation_penalty_percent BETWEEN 0 AND 100",
    ),
    (
        "bookings",
        "ck_bookings_cancellation_penalty_amount_non_negative",
        "cancellation_penalty_amount IS NULL OR cancellation_penalty_amount >= 0",
    ),
    (
        "bookings",
        "ck_bookings_promo_percent_range",
        "promo_percent_snapshot IS NULL OR promo_percent_snapshot BETWEEN 0 AND 100",
    ),
    (
        "bookings",
        "ck_bookings_board_guests_positive",
        "board_guests IS NULL OR board_guests > 0",
    ),
    ("rooms", "ck_rooms_capacity_positive", "capacity > 0"),
    ("rooms", "ck_rooms_inventory_count_non_negative", "inventory_count >= 0"),
    ("rooms", "ck_rooms_base_price_non_negative", "base_price >= 0"),
    (
        "rooms",
        "ck_rooms_base_price_weekend_non_negative",
        "base_price_weekend IS NULL OR base_price_weekend >= 0",
    ),
    ("rooms", "ck_rooms_markup_percent_non_negative", "markup_percent >= 0"),
    (
        "rooms",
        "ck_rooms_discount_percent_range",
        "discount_percent IS NULL OR discount_percent BETWEEN 0 AND 100",
    ),
    ("rooms", "ck_rooms_min_nights_positive", "min_nights > 0"),
    ("rooms", "ck_rooms_size_sqm_positive", "size_sqm IS NULL OR size_sqm > 0"),
    (
        "rooms",
        "ck_rooms_max_adults_non_negative",
        "max_adults IS NULL OR max_adults >= 0",
    ),
    (
        "rooms",
        "ck_rooms_max_children_non_negative",
        "max_children IS NULL OR max_children >= 0",
    ),
    (
        "rooms",
        "ck_rooms_max_child_rate_children_non_negative",
        "max_child_rate_children IS NULL OR max_child_rate_children >= 0",
    ),
    ("room_price_periods", "ck_room_price_periods_date_order", "date_to >= date_from"),
    (
        "room_price_periods",
        "ck_room_price_periods_base_price_non_negative",
        "base_price >= 0",
    ),
    (
        "room_price_periods",
        "ck_room_price_periods_base_price_weekend_non_negative",
        "base_price_weekend IS NULL OR base_price_weekend >= 0",
    ),
    (
        "room_price_periods",
        "ck_room_price_periods_discount_percent_range",
        "discount_percent IS NULL OR discount_percent BETWEEN 0 AND 100",
    ),
    (
        "rate_plans",
        "ck_rate_plans_board_price_non_negative",
        "board_price IS NULL OR board_price >= 0",
    ),
    (
        "rate_plans",
        "ck_rate_plans_board_guests_positive",
        "board_guests IS NULL OR board_guests > 0",
    ),
    (
        "rate_plans",
        "ck_rate_plans_free_cancellation_days_non_negative",
        "free_cancellation_days IS NULL OR free_cancellation_days >= 0",
    ),
    (
        "rate_plans",
        "ck_rate_plans_cancellation_penalty_percent_range",
        "cancellation_penalty_percent IS NULL "
        "OR cancellation_penalty_percent BETWEEN 0 AND 100",
    ),
    (
        "rate_plans",
        "ck_rate_plans_cancellation_penalty_amount_non_negative",
        "cancellation_penalty_amount IS NULL OR cancellation_penalty_amount >= 0",
    ),
    (
        "rate_plans",
        "ck_rate_plans_price_adjustment_percent_range",
        "price_adjustment_percent IS NULL "
        "OR price_adjustment_percent BETWEEN -100 AND 100",
    ),
    (
        "rate_plans",
        "ck_rate_plans_promo_percent_range",
        "promo_percent IS NULL OR promo_percent BETWEEN 0 AND 100",
    ),
    (
        "rate_plans",
        "ck_rate_plans_promo_date_order",
        "promo_ends_at IS NULL OR promo_starts_at IS NULL "
        "OR promo_ends_at >= promo_starts_at",
    ),
    (
        "rate_plans",
        "ck_rate_plans_min_nights_positive",
        "min_nights IS NULL OR min_nights > 0",
    ),
    (
        "rate_plans",
        "ck_rate_plans_max_nights_positive",
        "max_nights IS NULL OR max_nights > 0",
    ),
    (
        "rate_plans",
        "ck_rate_plans_nights_order",
        "max_nights IS NULL OR min_nights IS NULL OR max_nights >= min_nights",
    ),
    (
        "rate_plan_date_rules",
        "ck_rate_plan_date_rules_selling_rate_non_negative",
        "selling_rate IS NULL OR selling_rate >= 0",
    ),
    (
        "rate_plan_date_rules",
        "ck_rate_plan_date_rules_min_advance_non_negative",
        "min_advance_hours IS NULL OR min_advance_hours >= 0",
    ),
    (
        "rate_plan_date_rules",
        "ck_rate_plan_date_rules_max_advance_non_negative",
        "max_advance_hours IS NULL OR max_advance_hours >= 0",
    ),
    (
        "rate_plan_date_rules",
        "ck_rate_plan_date_rules_advance_order",
        "max_advance_hours IS NULL OR min_advance_hours IS NULL "
        "OR max_advance_hours >= min_advance_hours",
    ),
    (
        "rate_plan_date_rules",
        "ck_rate_plan_date_rules_min_stay_positive",
        "min_stay_nights IS NULL OR min_stay_nights > 0",
    ),
    (
        "rate_plan_date_rules",
        "ck_rate_plan_date_rules_min_stay_arrival_positive",
        "min_stay_arrival_nights IS NULL OR min_stay_arrival_nights > 0",
    ),
    (
        "room_availability",
        "ck_room_availability_units_blocked_non_negative",
        "units_blocked >= 0",
    ),
    (
        "room_availability",
        "ck_room_availability_units_booked_non_negative",
        "units_booked >= 0",
    ),
    ("sanatorium_reviews", "ck_reviews_rating_range", "rating BETWEEN 1 AND 10"),
    (
        "sanatorium_reviews",
        "ck_reviews_cleanliness_range",
        "cleanliness IS NULL OR cleanliness BETWEEN 1 AND 10",
    ),
    (
        "sanatorium_reviews",
        "ck_reviews_amenities_range",
        "amenities IS NULL OR amenities BETWEEN 1 AND 10",
    ),
    (
        "sanatorium_reviews",
        "ck_reviews_location_range",
        "location IS NULL OR location BETWEEN 1 AND 10",
    ),
    (
        "sanatorium_reviews",
        "ck_reviews_service_range",
        "service IS NULL OR service BETWEEN 1 AND 10",
    ),
    (
        "sanatorium_reviews",
        "ck_reviews_treatment_range",
        "treatment IS NULL OR treatment BETWEEN 1 AND 10",
    ),
    (
        "sanatorium_reviews",
        "ck_reviews_value_range",
        "value IS NULL OR value BETWEEN 1 AND 10",
    ),
    (
        "sanatorium_reviews",
        "ck_reviews_food_range",
        "food IS NULL OR food BETWEEN 1 AND 10",
    ),
    ("payments", "ck_payments_amount_non_negative", "amount >= 0"),
    ("packages", "ck_packages_duration_positive", "duration_nights > 0"),
    ("packages", "ck_packages_base_price_non_negative", "base_price >= 0"),
    (
        "package_items",
        "ck_package_items_extra_price_non_negative",
        "extra_price IS NULL OR extra_price >= 0",
    ),
    (
        "treatment_programs",
        "ck_treatment_programs_min_nights_positive",
        "min_nights IS NULL OR min_nights > 0",
    ),
    (
        "treatment_programs",
        "ck_treatment_programs_max_nights_positive",
        "max_nights IS NULL OR max_nights > 0",
    ),
    (
        "treatment_programs",
        "ck_treatment_programs_nights_order",
        "max_nights IS NULL OR min_nights IS NULL OR max_nights >= min_nights",
    ),
    (
        "treatment_programs",
        "ck_treatment_programs_duration_positive",
        "duration_minutes IS NULL OR duration_minutes > 0",
    ),
    (
        "treatment_programs",
        "ck_treatment_programs_price_non_negative",
        "price IS NULL OR price >= 0",
    ),
    (
        "treatment_programs",
        "ck_treatment_programs_group_size_min_positive",
        "group_size_min IS NULL OR group_size_min > 0",
    ),
    (
        "treatment_programs",
        "ck_treatment_programs_group_size_max_positive",
        "group_size_max IS NULL OR group_size_max > 0",
    ),
    (
        "treatment_programs",
        "ck_treatment_programs_group_size_order",
        "group_size_max IS NULL OR group_size_min IS NULL "
        "OR group_size_max >= group_size_min",
    ),
    (
        "treatment_programs",
        "ck_treatment_programs_medical_exam_count_non_negative",
        "medical_exam_count >= 0",
    ),
    (
        "treatment_programs",
        "ck_treatment_programs_medical_procedure_count_non_negative",
        "medical_procedure_count >= 0",
    ),
    (
        "treatment_programs",
        "ck_treatment_programs_sauna_entries_non_negative",
        "sauna_entries IS NULL OR sauna_entries >= 0",
    ),
    (
        "extra_bed_configs",
        "ck_extra_bed_configs_price_per_night_non_negative",
        "price_per_night >= 0",
    ),
    ("extra_bed_configs", "ck_extra_bed_configs_max_count_positive", "max_count > 0"),
    (
        "booking_extra_beds",
        "ck_booking_extra_beds_price_per_night_non_negative",
        "price_per_night_snapshot >= 0",
    ),
    ("booking_extra_beds", "ck_booking_extra_beds_count_positive", "count > 0"),
    (
        "booking_extra_beds",
        "ck_booking_extra_beds_total_price_non_negative",
        "total_price >= 0",
    ),
    (
        "promotions",
        "ck_promotions_discount_percent_range",
        "discount_percent BETWEEN 0 AND 100",
    ),
    (
        "promotions",
        "ck_promotions_booking_date_order",
        "booking_date_to IS NULL OR booking_date_from IS NULL "
        "OR booking_date_to >= booking_date_from",
    ),
    (
        "promotions",
        "ck_promotions_stay_date_order",
        "stay_date_to IS NULL OR stay_date_from IS NULL "
        "OR stay_date_to >= stay_date_from",
    ),
)


def upgrade() -> None:
    for table, name, expression in CHECKS:
        op.execute(
            f"ALTER TABLE {table} ADD CONSTRAINT {name} CHECK ({expression}) NOT VALID"
        )


def downgrade() -> None:
    for table, name, _expression in reversed(CHECKS):
        op.execute(f"ALTER TABLE {table} DROP CONSTRAINT IF EXISTS {name}")
