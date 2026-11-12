from pydantic import BaseModel
from typing import List, Optional


class AccessibilityPreferences(BaseModel):
    user_name: str = "Alex"
    current_mode: str = "VOICE"  # 'VOICE', 'LARGE_CONTROLS', 'KEYBOARD', 'SWITCH'
    read_important_aloud: bool = True
    read_total_aloud: bool = True
    simplified_interface: bool = False
    one_action_per_screen: bool = False
    reduced_motion: bool = False
    extra_response_time: bool = False
    warn_subscriptions: bool = True
    always_show_total_cost: bool = True
    suggest_cheaper_alternatives: bool = True
    cheaper_alternative_threshold: float = 50.0
    exact_price_confirmation: bool = True
    double_confirmation_threshold: float = 500.0
    warn_quantity_greater_one: bool = True
    warn_shipping_exceeds: float = 15.0
    switch_scan_speed_ms: int = 1800


class ModeSwitchRequest(BaseModel):
    mode: str
