from app.core.meta.amenities import amenity_meta
from app.core.meta.rooms import room_meta
from app.core.meta.sanatoriums import sanatorium_meta
from app.core.meta.shared import Option
from app.core.meta.travel import travel_meta

_ROOM = room_meta()
_AMENITY = amenity_meta()
_SANATORIUM = sanatorium_meta()
_TRAVEL = travel_meta()

META: dict[str, list[Option]] = {
    "board_types": _ROOM["board_types"],
    "payment_timings": _ROOM["payment_timings"],
    "confirmation_types": _ROOM["confirmation_types"],
    "room_views": _ROOM["room_views"],
    "amenity_costs": _AMENITY["amenity_costs"],
    "property_types": _SANATORIUM["property_types"],
    "wellness_categories": _SANATORIUM["wellness_categories"],
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
}

__all__ = ("META", "Option")
