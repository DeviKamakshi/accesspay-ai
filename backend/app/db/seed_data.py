from typing import List, Dict, Any
from app.db.database import db

INITIAL_PRODUCTS: List[Dict[str, Any]] = [
    {
        "id": "prod_headphone_sony",
        "title": "Sony WH-CH520 Lightweight Wireless Headphones",
        "description": "Ergonomic over-ear wireless headphones with oversized physical tactile buttons, 50-hour battery, and ultra-lightweight headband designed for all-day fatigue-free wear.",
        "price": 49.99,
        "original_price": 69.99,
        "shipping": 5.00,
        "estimated_tax": 4.37,
        "category": "Audio",
        "merchant": "AudioDirect Store",
        "image_url": "https://images.unsplash.com/photo-1505740420928-5e560c06d30e?w=600&auto=format&fit=crop&q=80",
        "rating": 4.8,
        "review_count": 1420,
        "is_available": True,
        "is_subscription": False,
        "is_trial": False,
        "documented_accessibility_features": [
            "Raised high-relief physical control buttons (no touch gestures required)",
            "Ultra-light 147g chassis minimizing neck and head fatigue",
            "Low clamping force for easy one-handed placement"
        ],
        "ai_inferred_accessibility": [
            "Likely suitable for users with fine-motor tremors due to distinct tactile separation between buttons"
        ],
        "ranking_badge": "BEST MATCH",
        "ranking_reason": "Ranked first: exactly matches your under-$80 wireless requirement, verified physical buttons for effortless control, total cost is $59.36.",
        "cheaper_alternative_id": "prod_headphone_anker",
        "savings_amount": 18.00,
        "variants": {"Color": ["Black", "Midnight Blue", "Soft Cream"]}
    },
    {
        "id": "prod_headphone_anker",
        "title": "Soundcore Q20i Active Noise Cancelling Headphones",
        "description": "Wireless headphones with deep physical toggle switch and high-contrast color indicators for power and mute.",
        "price": 39.99,
        "original_price": 49.99,
        "shipping": 0.00,
        "estimated_tax": 3.60,
        "category": "Audio",
        "merchant": "PrimeRetail",
        "image_url": "https://images.unsplash.com/photo-1546435770-a3e426bf472b?w=600&auto=format&fit=crop&q=80",
        "rating": 4.6,
        "review_count": 890,
        "is_available": True,
        "is_subscription": False,
        "is_trial": False,
        "documented_accessibility_features": [
            "Large mechanical click switches",
            "High-contrast white markings on dark casing",
            "Zero shipping fee"
        ],
        "ai_inferred_accessibility": [
            "Easier to grip earcups with generous textured edges"
        ],
        "ranking_badge": "LOWEST TOTAL COST",
        "ranking_reason": "Ranked for maximum economy: $39.99 with free shipping, saving $18.00 compared to premium brand alternatives.",
        "cheaper_alternative_id": None,
        "savings_amount": None,
        "variants": {"Color": ["Matte Black", "Graphite"]}
    },
    {
        "id": "prod_headphone_jbl",
        "title": "JBL Tune 720BT Wireless Over-Ear Headphones",
        "description": "Lightweight wireless Bluetooth headphones with 76-hour battery life and distinct tactile volume and playback buttons.",
        "price": 69.00,
        "original_price": 79.95,
        "shipping": 5.00,
        "estimated_tax": 5.52,
        "category": "Audio",
        "merchant": "SoundHub Official",
        "image_url": "https://images.unsplash.com/photo-1484704849700-f032a568e944?w=600&auto=format&fit=crop&q=80",
        "rating": 4.7,
        "review_count": 1150,
        "is_available": True,
        "is_subscription": False,
        "is_trial": False,
        "documented_accessibility_features": [
            "76-hour extended battery life requiring fewer charging cycles",
            "Distinct raised physical buttons on right earcup",
            "Soft padded headband for low-pressure wear"
        ],
        "ai_inferred_accessibility": [
            "Long battery life reduces physical effort of frequent cable plugging"
        ],
        "ranking_badge": "LONGEST BATTERY",
        "ranking_reason": "Under $80 budget with 76-hour battery life and tactile buttons.",
        "cheaper_alternative_id": "prod_headphone_sony",
        "savings_amount": 19.01,
        "variants": {"Color": ["Blue", "Black", "White"]}
    },
    {
        "id": "prod_headphone_bose",
        "title": "Bose QuietComfort 45 Accessible Edition",
        "description": "Premium wireless headphones with multi-device seamless switching and soft touch physical volume rocker.",
        "price": 199.00,
        "original_price": 279.00,
        "shipping": 0.00,
        "estimated_tax": 17.91,
        "category": "Audio",
        "merchant": "SoundCraft Official",
        "image_url": "https://images.unsplash.com/photo-1583394838336-acd977736f90?w=600&auto=format&fit=crop&q=80",
        "rating": 4.9,
        "review_count": 3100,
        "is_available": True,
        "is_subscription": False,
        "is_trial": False,
        "documented_accessibility_features": [
            "Voice-guided connection prompts",
            "Physical slider power switch with distinct click detent"
        ],
        "ai_inferred_accessibility": [
            "High acoustic fidelity beneficial for screen reader audio clarity"
        ],
        "ranking_badge": "PREMIUM PICK",
        "ranking_reason": "Highest audio clarity and voice prompt integration, but exceeds standard economy budget.",
        "cheaper_alternative_id": "prod_headphone_sony",
        "savings_amount": 139.01
    },
    {
        "id": "prod_keyboard_logitech",
        "title": "Logitech Wave Keys Wireless Ergonomic Keyboard",
        "description": "Cushioned palm rest keyboard with naturally curved keyframe and enlarged high-contrast keys requiring minimal actuation force.",
        "price": 54.99,
        "original_price": 69.99,
        "shipping": 4.00,
        "estimated_tax": 4.95,
        "category": "Keyboards",
        "merchant": "OfficeTech Direct",
        "image_url": "https://images.unsplash.com/photo-1587829741301-dc798b83add3?w=600&auto=format&fit=crop&q=80",
        "rating": 4.7,
        "review_count": 920,
        "is_available": True,
        "is_subscription": False,
        "is_trial": False,
        "documented_accessibility_features": [
            "Large deep-dished keycaps with high-visibility white-on-slate typography",
            "Low 45g actuation force reducing joint stress",
            "Multi-angle tilt legs with 0°, +4°, and +7° accessible adjustments"
        ],
        "ai_inferred_accessibility": [
            "Waved layout aligns naturally with resting wrists, reducing wrist rotation demand"
        ],
        "ranking_badge": "BEST MATCH",
        "ranking_reason": "Top match: under $70 budget limit, oversized keys, feather-light actuation force.",
        "cheaper_alternative_id": "prod_keyboard_eztype",
        "savings_amount": 19.00
    },
    {
        "id": "prod_keyboard_eztype",
        "title": "EZ-See Vision Large Print Wireless Keyboard",
        "description": "High-visibility 1-inch jumbo keycaps with bold yellow background and black lettering for effortless targeting.",
        "price": 35.99,
        "original_price": 45.00,
        "shipping": 4.00,
        "estimated_tax": 3.24,
        "category": "Keyboards",
        "merchant": "AccessLiving Supplies",
        "image_url": "https://images.unsplash.com/photo-1618384887929-16ec33fab9ef?w=600&auto=format&fit=crop&q=80",
        "rating": 4.8,
        "review_count": 450,
        "is_available": True,
        "is_subscription": False,
        "is_trial": False,
        "documented_accessibility_features": [
            "400% larger key characters than standard keyboards",
            "High-contrast color scheme certified for low vision / motor assistance",
            "Spill-resistant membrane design"
        ],
        "ai_inferred_accessibility": [
            "Enlarged hit areas reduce typing errors caused by motor tremors or imprecise reach"
        ],
        "ranking_badge": "LOWEST TOTAL COST",
        "ranking_reason": "Lowest total cost in category: $35.99, saves $19 over Logitech Wave Keys, largest physical key targets.",
        "cheaper_alternative_id": None,
        "savings_amount": None
    },
    {
        "id": "prod_subscription_music",
        "title": "Audible Access Unlimited Audiobooks Plan",
        "description": "Monthly recurring access to accessible audio books, screen-reader optimized player, and tactile voice bookmarks.",
        "price": 9.99,
        "original_price": None,
        "shipping": 0.00,
        "estimated_tax": 0.00,
        "category": "Subscriptions",
        "merchant": "AudioMedia Corp",
        "image_url": "https://images.unsplash.com/photo-1512820790803-83ca734da794?w=600&auto=format&fit=crop&q=80",
        "rating": 4.9,
        "review_count": 5200,
        "is_available": True,
        "is_subscription": True,
        "subscription_period": "month",
        "is_trial": False,
        "documented_accessibility_features": [
            "Full hands-free voice bookmarking",
            "Variable narration speed from 0.5x to 3.5x without pitch distortion"
        ],
        "ai_inferred_accessibility": [
            "Zero physical book turning required"
        ],
        "ranking_badge": "RECURRING PLAN",
        "ranking_reason": "Billed at $9.99 every month until cancelled. Transparent recurring billing guard active.",
        "cheaper_alternative_id": None,
        "savings_amount": None
    },
    {
        "id": "prod_trial_speechify",
        "title": "Speechify Voice Reader Pro (30-Day Free Trial)",
        "description": "High-clarity AI text-to-speech reader for web, PDF, and print. Free for 30 days, then renews at $19.99/month.",
        "price": 0.00,
        "original_price": 19.99,
        "shipping": 0.00,
        "estimated_tax": 0.00,
        "category": "Subscriptions",
        "merchant": "Speechify Inc",
        "image_url": "https://images.unsplash.com/photo-1516321318423-f06f85e504b3?w=600&auto=format&fit=crop&q=80",
        "rating": 4.8,
        "review_count": 1890,
        "is_available": True,
        "is_subscription": True,
        "subscription_period": "month",
        "is_trial": True,
        "trial_days": 30,
        "trial_post_price": 19.99,
        "documented_accessibility_features": [
            "Reads any digital text aloud with human-sounding AI voices",
            "Automated optical character recognition for physical mail"
        ],
        "ai_inferred_accessibility": [
            "Completely eliminates fatigue associated with reading long visual documents"
        ],
        "ranking_badge": "FREE TRIAL",
        "ranking_reason": "$0.00 due today. Renews at $19.99/month after 30 days unless cancelled. Trial Guardian will notify 7 days prior.",
        "cheaper_alternative_id": None,
        "savings_amount": None
    },
    {
        "id": "prod_laptop_dell",
        "title": "Dell XPS 13 Motor-Assist Ultra Laptop",
        "description": "Flagship 13.4-inch laptop with one-finger magnetic lid open, zero-resistance hinge, and integrated infrared facial login.",
        "price": 799.00,
        "original_price": 999.00,
        "shipping": 0.00,
        "estimated_tax": 71.91,
        "category": "Computers",
        "merchant": "Dell Technologies",
        "image_url": "https://images.unsplash.com/photo-1593642632823-8f785ba67e45?w=600&auto=format&fit=crop&q=80",
        "rating": 4.9,
        "review_count": 870,
        "is_available": True,
        "is_subscription": False,
        "is_trial": False,
        "documented_accessibility_features": [
            "Easy-open single-finger chamfered lid groove",
            "Windows Hello infrared facial login requiring zero manual password typing",
            "High-contrast OLED screen with 500-nit luminance for outdoor readability"
        ],
        "ai_inferred_accessibility": [
            "Extremely low physical travel keys reduce fatigue during extended work sessions"
        ],
        "ranking_badge": "HIGH VALUE",
        "ranking_reason": "High-value purchase ($799.00). Requires two-step confirmation because total exceeds the $500 threshold.",
        "cheaper_alternative_id": None,
        "savings_amount": None
    },
    {
        "id": "prod_mouse_trackball",
        "title": "Kensington Expert Wireless Stationary Trackball",
        "description": "Stationary 55mm trackball mouse requiring zero hand or wrist movement. Large programmable buttons with low-click force.",
        "price": 84.99,
        "original_price": 109.99,
        "shipping": 0.00,
        "estimated_tax": 7.65,
        "category": "Pointing Devices",
        "merchant": "Kensington Direct",
        "image_url": "https://images.unsplash.com/photo-1615663245857-ac93bb7c39e7?w=600&auto=format&fit=crop&q=80",
        "rating": 4.7,
        "review_count": 1650,
        "is_available": True,
        "is_subscription": False,
        "is_trial": False,
        "documented_accessibility_features": [
            "Large 55mm precision ball operable with fingertip, palm, or foot",
            "4 oversized mechanical switches with remappable click-lock functions",
            "Detachable cushioned wrist rest supporting neutral arm posture"
        ],
        "ai_inferred_accessibility": [
            "Eliminates repetitive wrist swiping across desk; ideal for limited desk space and limited range of arm motion"
        ],
        "ranking_badge": "BEST MATCH",
        "ranking_reason": "Zero arm movement required, oversized buttons, customizable dwell-click compatible.",
        "cheaper_alternative_id": None,
        "savings_amount": None
    }
]

INITIAL_ORDERS: List[Dict[str, Any]] = [
    {
        "order_id": "ORD-84920",
        "date": "2026-11-01",
        "product_title": "Sony WH-CH520 Lightweight Wireless Headphones",
        "merchant": "AudioDirect Store",
        "category": "Audio",
        "item_price": 49.99,
        "shipping": 5.00,
        "tax": 4.37,
        "total": 59.36,
        "quantity": 1,
        "variant": "Midnight Blue",
        "is_recurring": False,
        "interaction_mode": "VOICE",
        "confirmation_method": "Exact Voice Phrase: 'Confirm $59.36 purchase'",
        "payment_status": "PAID",
        "paypal_order_id": "PAYID-MN67894A82",
        "tracking_status": "DELIVERED",
        "tracking_number": "1Z9999999999999999",
        "return_eligible": True,
        "return_window_days": 28
    },
    {
        "order_id": "ORD-73194",
        "date": "2026-10-24",
        "product_title": "EZ-See Vision Large Print Wireless Keyboard",
        "merchant": "AccessLiving Supplies",
        "category": "Keyboards",
        "item_price": 35.99,
        "shipping": 4.00,
        "tax": 3.24,
        "total": 43.23,
        "quantity": 1,
        "variant": "Yellow/Black High Contrast",
        "is_recurring": False,
        "interaction_mode": "SWITCH",
        "confirmation_method": "Switch Scanner Activation (Space bar simulation)",
        "payment_status": "PAID",
        "paypal_order_id": "PAYID-MN54321B19",
        "tracking_status": "DELIVERED",
        "tracking_number": "1Z8888888888888888",
        "return_eligible": True,
        "return_window_days": 20
    },
    {
        "order_id": "ORD-68214",
        "date": "2026-10-12",
        "product_title": "Audible Access Unlimited Audiobooks Plan",
        "merchant": "AudioMedia Corp",
        "category": "Subscriptions",
        "item_price": 9.99,
        "shipping": 0.00,
        "tax": 0.00,
        "total": 9.99,
        "quantity": 1,
        "variant": "Monthly Auto-Renew",
        "is_recurring": True,
        "interaction_mode": "VOICE",
        "confirmation_method": "Exact Phrase + Recurring Payment Acknowledgement",
        "payment_status": "PAID",
        "paypal_order_id": "PAYID-MN33221C45",
        "tracking_status": "ACTIVE_SUBSCRIPTION",
        "tracking_number": None,
        "return_eligible": False,
        "return_window_days": 0
    },
    {
        "order_id": "ORD-51928",
        "date": "2026-09-30",
        "product_title": "Kensington Expert Wireless Stationary Trackball",
        "merchant": "Kensington Direct",
        "category": "Pointing Devices",
        "item_price": 84.99,
        "shipping": 0.00,
        "tax": 7.65,
        "total": 92.64,
        "quantity": 1,
        "variant": "Standard Gray Ball",
        "is_recurring": False,
        "interaction_mode": "KEYBOARD",
        "confirmation_method": "Keyboard Modal Enter Key",
        "payment_status": "PAID",
        "paypal_order_id": "PAYID-MN11299D78",
        "tracking_status": "DELIVERED",
        "tracking_number": "1Z7777777777777777",
        "return_eligible": False,
        "return_window_days": 0
    },
    {
        "order_id": "ORD-42001",
        "date": "2026-09-18",
        "product_title": "Energizer Industrial AA Batteries (24-Pack)",
        "merchant": "BatteryPower Supply",
        "category": "Accessories",
        "item_price": 18.99,
        "shipping": 3.50,
        "tax": 1.71,
        "total": 24.20,
        "quantity": 1,
        "variant": "24 Pack Box",
        "is_recurring": False,
        "interaction_mode": "VOICE",
        "confirmation_method": "Voice Reorder Flow with Exact Confirmation",
        "payment_status": "PAID",
        "paypal_order_id": "PAYID-MN99887E12",
        "tracking_status": "DELIVERED",
        "tracking_number": "1Z6666666666666666",
        "return_eligible": False,
        "return_window_days": 0
    }
]

INITIAL_TIMELINE: List[Dict[str, Any]] = [
    {
        "id": "time-1",
        "date": "2026-11-04",
        "display_date": "NOV 4",
        "title": "Headphones Purchased",
        "category": "purchase",
        "amount": 59.36,
        "merchant": "AudioDirect Store",
        "description": "Sony WH-CH520 Wireless Headphones order authorized via exact-amount voice confirmation.",
        "status": "COMPLETED",
        "is_recurring": False,
        "highlight": True
    },
    {
        "id": "time-2",
        "date": "2026-11-08",
        "display_date": "NOV 8",
        "title": "Expected Delivery: Sony Headphones",
        "category": "delivery",
        "amount": None,
        "merchant": "AudioDirect Store (UPS Ground)",
        "description": "Scheduled front-door delivery with contactless drop-off verification.",
        "status": "SCHEDULED",
        "is_recurring": False,
        "highlight": False
    },
    {
        "id": "time-3",
        "date": "2026-11-12",
        "display_date": "NOV 12",
        "title": "Music Subscription Renewal",
        "category": "subscription",
        "amount": 9.99,
        "merchant": "AudioMedia Corp",
        "description": "Monthly renewal for Audible Access Unlimited audio stream plan.",
        "status": "UPCOMING",
        "is_recurring": True,
        "recurring_interval": "Monthly",
        "highlight": True
    },
    {
        "id": "time-4",
        "date": "2026-11-18",
        "display_date": "NOV 18",
        "title": "Free Trial Ends: Speechify Pro",
        "category": "trial_expiration",
        "amount": 19.99,
        "merchant": "Speechify Inc",
        "description": "30-day trial expires. Renews at $19.99/month unless cancelled in settings.",
        "status": "UPCOMING",
        "is_recurring": True,
        "highlight": True
    },
    {
        "id": "time-5",
        "date": "2026-11-25",
        "display_date": "NOV 25",
        "title": "Projected Monthly Subscriptions Total",
        "category": "subscription",
        "amount": 29.98,
        "merchant": "AccessPay Account Consolidated",
        "description": "Combined monthly recurring commitments for AudioMedia ($9.99) and Speechify ($19.99).",
        "status": "SCHEDULED",
        "is_recurring": True,
        "highlight": False
    }
]


def seed_database():
    """Populate database with deterministic initial data."""
    db.clear_all()
    for product in INITIAL_PRODUCTS:
        db.save_product(product)
    for order in INITIAL_ORDERS:
        db.save_order(order)
    for event in INITIAL_TIMELINE:
        db.save_timeline_event(event)
    db.log_audit_event("SYSTEM_INIT", "Database seeded with deterministic demo data and WCAG 2.2 profiles.", "SYSTEM")


def ensure_database_seeded():
    """
    Ensures the SQLite database has baseline catalog products and initial orders on first boot,
    without wiping existing purchase history across normal application restarts.
    """
    existing_products = db.get_all_products()
    if not existing_products:
        seed_database()
        return

    # Ensure all baseline catalog products exist while preserving existing orders
    for product in INITIAL_PRODUCTS:
        db.save_product(product)


if __name__ == "__main__":
    seed_database()
    print("Database seeded successfully!")
