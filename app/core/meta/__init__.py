from app.core.meta.amenities import amenity_meta
from app.core.meta.availability import availability_meta
from app.core.meta.promotions import promotion_meta
from app.core.meta.reviews import review_meta
from app.core.meta.rooms import room_meta
from app.core.meta.sanatoriums import sanatorium_meta
from app.core.meta.shared import Option
from app.core.meta.travel import travel_meta

_AVAILABILITY = availability_meta()
_PROMOTION = promotion_meta()
_REVIEW = review_meta()
_ROOM = room_meta()
_AMENITY = amenity_meta()
_SANATORIUM = sanatorium_meta()
_TRAVEL = travel_meta()

META: dict[str, list[Option]] = {
    "booking_date_filters": _AVAILABILITY["booking_date_filters"],
    "weekdays": _AVAILABILITY["weekdays"],
    "weekend_days": _AVAILABILITY["weekend_days"],
    "bulk_restriction_fields": _AVAILABILITY["bulk_restriction_fields"],
    "copy_rate_alignments": _AVAILABILITY["copy_rate_alignments"],
    "copy_rate_adjustments": _AVAILABILITY["copy_rate_adjustments"],
    "reservation_fallback_processing_methods": _AVAILABILITY[
        "reservation_fallback_processing_methods"
    ],
    "availability_room_statuses": _AVAILABILITY["availability_room_statuses"],
    "availability_log_categories": _AVAILABILITY["availability_log_categories"],
    "promotion_categories": _PROMOTION["promotion_categories"],
    "promotion_statuses": _PROMOTION["promotion_statuses"],
    "promotion_audiences": _PROMOTION["promotion_audiences"],
    "promotion_cancellation_policy_modes": _PROMOTION[
        "promotion_cancellation_policy_modes"
    ],
    "review_sources": _REVIEW["review_sources"],
    "review_reply_statuses": _REVIEW["review_reply_statuses"],
    "review_appeal_statuses": _REVIEW["review_appeal_statuses"],
    "review_sort_options": _REVIEW["review_sort_options"],
    "board_types": _ROOM["board_types"],
    "payment_timings": _ROOM["payment_timings"],
    "confirmation_types": _ROOM["confirmation_types"],
    "room_views": _ROOM["room_views"],
    "accommodation_types": _ROOM["accommodation_types"],
    "gender_restrictions": _ROOM["gender_restrictions"],
    "room_size_policies": _ROOM["room_size_policies"],
    "smoking_policies": _ROOM["smoking_policies"],
    "window_policies": _ROOM["window_policies"],
    "room_amenity_groups": _ROOM["room_amenity_groups"],
    "amenity_scopes": _AMENITY["amenity_scopes"],
    "amenity_statuses": _AMENITY["amenity_statuses"],
    "amenity_costs": _AMENITY["amenity_costs"],
    "property_types": _SANATORIUM["property_types"],
    "wellness_categories": _SANATORIUM["wellness_categories"],
    "host_types": _SANATORIUM["host_types"],
    "booking_types": _TRAVEL["booking_types"],
    "booking_statuses": _TRAVEL["booking_statuses"],
    "bed_types": _ROOM["bed_types"],
    "treatment_focuses": _SANATORIUM["treatment_focuses"],
    "payment_methods": _SANATORIUM["payment_methods"],
    "amenity_categories": _AMENITY["amenity_categories"],
    "surrounding_types": _SANATORIUM["surrounding_types"],
    "venue_types": _SANATORIUM["venue_types"],
    "meal_types": _SANATORIUM["meal_types"],
    "traveler_types": _TRAVEL["traveler_types"],
    "currencies": _TRAVEL["currencies"],
    "natural_resources": _SANATORIUM["natural_resources"],
    "medical_procedure_categories": _SANATORIUM["medical_procedure_categories"],
    "medical_procedures": _SANATORIUM["medical_procedures"],
    "stay_durations": _SANATORIUM["stay_durations"],
    "stay_program_categories": _SANATORIUM["stay_program_categories"],
    "stay_program_inclusions": _SANATORIUM["stay_program_inclusions"],
    "policy_includes": _SANATORIUM["policy_includes"],
    "image_categories": _SANATORIUM["image_categories"],
    "promo_badge_kinds": _SANATORIUM["promo_badge_kinds"],
    "child_rate_modes": _SANATORIUM["child_rate_modes"],
    "child_pricing_methods": _SANATORIUM["child_pricing_methods"],
    "breakfast_serving_styles": _SANATORIUM["breakfast_serving_styles"],
    "pet_fee_frequencies": _SANATORIUM["pet_fee_frequencies"],
    "deposit_types": _SANATORIUM["deposit_types"],
    "payment_guarantee_methods": _SANATORIUM["payment_guarantee_methods"],
    "facility_service_groups": _SANATORIUM["facility_service_groups"],
    "tax_pricing_modes": _SANATORIUM["tax_pricing_modes"],
    "tax_fee_types": _SANATORIUM["tax_fee_types"],
    "tax_fee_levels": _SANATORIUM["tax_fee_levels"],
    "tax_fee_calculation_methods": _SANATORIUM["tax_fee_calculation_methods"],
}

__all__ = ("META", "Option")
