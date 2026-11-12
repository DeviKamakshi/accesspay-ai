from typing import Dict, Any, List
from app.models.accessibility import AccessibilityPreferences
from app.db.database import db

# Default Demo User "Alex" as requested in Section 72
DEFAULT_PREFERENCES = AccessibilityPreferences(
    user_name="Alex",
    current_mode="VOICE",
    read_important_aloud=True,
    read_total_aloud=True,
    simplified_interface=False,
    one_action_per_screen=False,
    reduced_motion=False,
    extra_response_time=False,
    warn_subscriptions=True,
    always_show_total_cost=True,
    suggest_cheaper_alternatives=True,
    cheaper_alternative_threshold=50.0,
    exact_price_confirmation=True,
    double_confirmation_threshold=500.0,
    warn_quantity_greater_one=True,
    warn_shipping_exceeds=15.0,
    switch_scan_speed_ms=1800
)


class AccessibilityService:
    def __init__(self):
        self._current_preferences = DEFAULT_PREFERENCES.model_copy()

    def get_preferences(self) -> AccessibilityPreferences:
        return self._current_preferences

    def update_preferences(self, updates: Dict[str, Any]) -> AccessibilityPreferences:
        current_dict = self._current_preferences.model_dump()
        current_dict.update(updates)
        self._current_preferences = AccessibilityPreferences(**current_dict)
        db.log_audit_event(
            "PREFERENCES_UPDATED",
            f"Mode: {self._current_preferences.current_mode}, ExactConfirm: {self._current_preferences.exact_price_confirmation}",
            self._current_preferences.current_mode
        )
        return self._current_preferences

    def set_mode(self, mode: str) -> AccessibilityPreferences:
        valid_modes = ["VOICE", "LARGE_CONTROLS", "KEYBOARD", "SWITCH"]
        if mode.upper() in valid_modes:
            self._current_preferences.current_mode = mode.upper()
            db.log_audit_event("MODE_SWITCHED", f"Switched to {mode.upper()} mode", mode.upper())
        return self._current_preferences

    def reset_to_defaults(self):
        self._current_preferences = DEFAULT_PREFERENCES.model_copy()
        db.log_audit_event("PREFERENCES_RESET", "Reset preferences to default demo profile Alex", "SYSTEM")


accessibility_service = AccessibilityService()
