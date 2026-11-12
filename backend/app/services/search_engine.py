import colorsys
import logging
import re
from enum import Enum
from typing import Any, Dict, List, Optional, Tuple
from pydantic import BaseModel, Field
from app.models.product import Product

logger = logging.getLogger("accesspay.search")

STOP_WORDS = {
    "a", "an", "the", "some", "any", "for", "with", "that", "have", "has", "to", "of",
    "in", "on", "at", "by", "or", "and", "is", "it", "my", "me", "i", "we", "you",
    "find", "search", "show", "give", "get", "look", "looking", "need", "want", "buy",
    "shop", "please", "now", "ones", "one", "products", "product", "options", "option",
    "items", "item", "good", "best", "great", "nice", "easy", "only", "under", "below",
    "less", "than", "max", "up", "above", "over", "more", "budget", "around", "about",
    "instead", "please", "can", "could", "would", "something", "else", "other", "another",
}

GENERIC_COLORS = {
    "black", "white", "pink", "blue", "red", "green", "gray", "grey", "silver",
    "gold", "purple", "orange", "yellow", "brown", "beige", "navy", "rose",
}

GENERIC_FEATURES = [
    ("noise cancelling", ("noise cancelling", "noise canceling", "anc", "noise-cancelling")),
    ("wireless", ("wireless", "bluetooth", "cordless")),
    ("lightweight", ("lightweight", "light weight", "ultra-light")),
    ("ergonomic", ("ergonomic",)),
    ("waterproof", ("waterproof", "water resistant", "water-resistant", "ipx")),
    ("usb-c", ("usb-c", "usb c", "type-c", "type c")),
    ("fast charging", ("fast charging", "fast charger", "quick charge", "pd")),
    ("large keys", ("large key", "big key", "oversized key")),
    ("physical controls", ("physical control", "physical button", "tactile button")),
    ("backlit", ("backlit", "illuminated")),
    ("mini", ("mini", "compact", "travel size", "portable")),
    ("plush", ("plush", "stuffed")),
    ("insulated", ("insulated", "stainless steel")),
]

GENERIC_COMPATIBILITIES = [
    ("iphone", ("for iphone", "iphone", "ios", "lightning")),
    ("mac", ("for mac", "macbook", "macos", "mac")),
    ("ipad", ("for ipad", "ipad")),
    ("android", ("for android", "android")),
    ("windows", ("for windows", "windows", "pc")),
    ("laptop", ("for laptop", "laptop")),
    ("travel", ("for travel", "travel")),
    ("school", ("for school", "school")),
    ("kids", ("for kids", "kids", "child", "children", "toddler")),
]

ACCESSORY_ONLY_MARKERS = (
    "protective case", "carrying case", "hard case", "travel case", "travel pouch", "case for",
    "replacement ear", "earpads", "ear pad", "ear cushion", "ear tips",
    "screen protector", "tempered glass", "dust cover", "cover for", "sleeve for",
    "skin for", "sticker for", "replacement cable", "charging cable only", "strap for",
    "band for", "mount for", "stand for", "holder for", "mousepad", "mouse pad",
    "palm rest", "wrist rest", "keycap", "keycaps", "desk mat", "mx mat",
    "cleaning brush", "bottle brush", "cleaner brush", "brush for",
    "shoe bag", "boot bag", "shoe horn", "shoe tree", "shoelace", "shoelaces",
    "insole", "insoles", "replacement lid", "replacement straw",
    "carry bag", "storage bag", "toy box", "toy chest", "toy organizer", "toy storage",
    "doll stand", "charger cord", "charging cord", "power cord", "charging cable",
    "braided cable", "usb cable",
)

DECORATION_MARKERS = (
    "banner", "bunting", "garland", "decoration", "decorations", "party decor",
    "party supplies", "party supply", "party pack", "tablecloth", "table cover",
    "paper plate", "paper plates", "napkin", "napkins", "cake topper",
    "cupcake topper", "centerpiece", "backdrop", "balloon", "balloons",
    "inflatable", "blow mold", "yard stake", "confetti", "streamer", "streamers",
    "pinata", "piñata", "poster", "posters", "wall art", "wall decal", "window cling",
    "wrapping paper", "gift bag", "greeting card", "invitation", "invitations",
)

APPAREL_COSTUME_MISMATCH_MARKERS = (
    "costume", "cosplay", "halloween costume", "t-shirt", "t shirt", "tee shirt",
    "sweatshirt", "hoodie", "pajama", "pajamas", "sleepwear", "socks", "beanie",
)

BUNDLE_MARKERS = (
    "and mouse", "and laser mouse", "with mouse", "with mx master",
    "keyboard & mouse", "keyboard and mouse", "combo", "bundle",
)

# Semantic family equivalents so broad queries don't over-filter valid variants
# while clearly rejecting completely unrelated categories.
FAMILY_SYNONYMS: Dict[str, Tuple[str, ...]] = {
    "headphone": ("headphone", "headphones", "headset", "headsets", "on-ear", "over-ear", "earbud", "earbuds"),
    "earbud": ("earbud", "earbuds", "earphone", "earphones", "headphone", "headphones"),
    "keyboard": ("keyboard", "keyboards", "keys", "keypad"),
    "mouse": ("mouse", "mice", "trackball", "trackballs"),
    "charger": ("charger", "chargers", "wall charger", "power adapter", "power block", "charging block", "gan charger"),
    "backpack": ("backpack", "backpacks", "rucksack", "daypack", "bookbag"),
    "bottle": ("bottle", "bottles", "water bottle", "flask", "tumbler", "canteen"),
    "shoe": ("shoe", "shoes", "sneaker", "sneakers", "trainer", "trainers", "running shoe", "running shoes"),
    "doll": ("doll", "dolls", "fashion doll", "playset"),
    "toy": ("toy", "toys", "playset", "playsets", "figure", "figures", "plush", "plushie", "stuffed animal", "action figure", "doll", "dolls", "building kit", "building set", "vehicle", "puzzle", "game", "board game"),
    "set": ("set", "sets", "kit", "building", "brick", "blocks"),
    "gift": ("toy", "toys", "playset", "game", "kit", "board", "figure", "plush", "gift"),
}

# Controlled product-type broadening alternatives derived generically from FAMILY_SYNONYMS roots
PRODUCT_BROADEN_SYNONYMS: Dict[str, Tuple[str, ...]] = {
    "toy": ("toy", "plush", "figure", "playset"),
    "doll": ("doll", "fashion doll", "playset"),
    "shoe": ("shoe", "sneaker", "running shoe"),
    "headphone": ("headphones", "wireless headphones", "earbuds"),
    "bottle": ("water bottle", "bottle", "tumbler"),
    "backpack": ("backpack", "daypack"),
    "charger": ("charger", "wall charger", "power adapter"),
}


class ConstraintStrength(str, Enum):
    HARD = "hard"
    SOFT = "soft"
    DERIVED = "derived"


class TypedConstraint(BaseModel):
    field: str
    value: Any
    strength: ConstraintStrength = ConstraintStrength.HARD


class StructuredSearchIntent(BaseModel):
    raw_query: str
    search_query: str
    product_type: str = ""
    brand: Optional[str] = None
    character_or_franchise: Optional[str] = None
    model: Optional[str] = None
    category: Optional[str] = None
    max_price: Optional[float] = None
    min_price: Optional[float] = None
    color: Optional[str] = None
    size: Optional[str] = None
    features: List[str] = Field(default_factory=list)
    compatibility: Optional[str] = None
    recipient_or_use_case: Optional[str] = None
    sort_preference: str = "relevance"
    exclude_brands: List[str] = Field(default_factory=list)
    broaden_queries: List[str] = Field(default_factory=list)
    constraints: List[TypedConstraint] = Field(default_factory=list)
    is_followup: bool = False


def build_typed_constraints(intent: StructuredSearchIntent) -> List[TypedConstraint]:
    """
    Classifies intent fields into HARD, SOFT, and DERIVED constraints generically.
    Derived constraints (e.g. translating 'birthday gift for 5 year old' -> 'toys')
    guide ranking/querying without inventing factual product attributes.
    """
    out: List[TypedConstraint] = []
    if intent.product_type:
        strength = ConstraintStrength.DERIVED if intent.recipient_or_use_case else ConstraintStrength.HARD
        out.append(TypedConstraint(field="product_type", value=intent.product_type, strength=strength))
    if intent.brand:
        out.append(TypedConstraint(field="brand", value=intent.brand, strength=ConstraintStrength.HARD))
    if intent.character_or_franchise:
        out.append(TypedConstraint(field="character_or_franchise", value=intent.character_or_franchise, strength=ConstraintStrength.HARD))
    if intent.model:
        out.append(TypedConstraint(field="model", value=intent.model, strength=ConstraintStrength.HARD))
    if intent.max_price is not None:
        out.append(TypedConstraint(field="max_price", value=intent.max_price, strength=ConstraintStrength.HARD))
    if intent.min_price is not None:
        out.append(TypedConstraint(field="min_price", value=intent.min_price, strength=ConstraintStrength.HARD))
    if intent.color:
        out.append(TypedConstraint(field="color", value=intent.color, strength=ConstraintStrength.SOFT))
    if intent.size:
        out.append(TypedConstraint(field="size", value=intent.size, strength=ConstraintStrength.SOFT))
    if intent.compatibility:
        out.append(TypedConstraint(field="compatibility", value=intent.compatibility, strength=ConstraintStrength.HARD))
    for feat in intent.features:
        out.append(TypedConstraint(field="feature", value=feat, strength=ConstraintStrength.SOFT))
    if intent.recipient_or_use_case:
        out.append(TypedConstraint(field="recipient_or_use_case", value=intent.recipient_or_use_case, strength=ConstraintStrength.DERIVED))
    if intent.sort_preference and intent.sort_preference != "relevance":
        out.append(TypedConstraint(field="sort_preference", value=intent.sort_preference, strength=ConstraintStrength.SOFT))
    return out


def stem_token(tok: str) -> str:
    w = tok.lower().strip()
    if w == "mice":
        return "mouse"
    if len(w) <= 3:
        return w
    if w.endswith("ies") and len(w) > 4:
        return w[:-3] + "y"
    if w.endswith(("ches", "shes", "xes", "zes")) and len(w) > 4:
        return w[:-2]
    if w.endswith("s") and not w.endswith(("ss", "us", "is", "ies")):
        return w[:-1]
    return w


def tokenize_meaningful(text: str, keep_short_models: bool = True) -> List[str]:
    raw_tokens = re.findall(r"[a-zA-Z0-9]+(?:-[a-zA-Z0-9]+)*", text.lower())
    out: List[str] = []
    for tok in raw_tokens:
        if tok in STOP_WORDS:
            continue
        if len(tok) == 1 and not tok.isdigit():
            continue
        if len(tok) == 2 and not keep_short_models and not any(c.isdigit() for c in tok):
            continue
        if tok not in out:
            out.append(tok)
    return out


def contains_word(blob_lower: str, term: str) -> bool:
    t = term.lower().strip()
    if not t:
        return False
    # Support hyphen/space variations like usb-c / usb c / usbc
    variants = {t, t.replace("-", " "), t.replace("-", "")}
    stemmed = stem_token(t)
    if stemmed != t:
        variants.add(stemmed)
        variants.add(stemmed + "s")
    for v in variants:
        if re.search(rf"(?<![a-z0-9]){re.escape(v)}(?![a-z0-9])", blob_lower):
            return True
    return False


def classify_hex_color(hex_str: str) -> Optional[str]:
    """Maps a #RRGGBB swatch from Channel3 to a basic generic color category."""
    if not hex_str or not isinstance(hex_str, str):
        return None
    h = hex_str.strip().lstrip("#")
    if len(h) != 6:
        return None
    try:
        r = int(h[0:2], 16) / 255.0
        g = int(h[2:4], 16) / 255.0
        b = int(h[4:6], 16) / 255.0
    except ValueError:
        return None

    hue, sat, val = colorsys.rgb_to_hsv(r, g, b)
    hue_deg = hue * 360.0

    if val <= 0.22:
        return "black"
    if sat <= 0.14:
        if val >= 0.85:
            return "white"
        return "gray"
    if val <= 0.35 and sat <= 0.40 and (200 <= hue_deg <= 255):
        return "navy"
    if (hue_deg >= 300 or hue_deg <= 15) and val >= 0.55 and sat <= 0.72:
        return "pink"
    if hue_deg <= 15 or hue_deg >= 340:
        return "red" if val < 0.75 or sat > 0.65 else "pink"
    if 15 < hue_deg <= 42:
        return "brown" if val < 0.55 else "orange"
    if 42 < hue_deg <= 68:
        return "yellow"
    if 68 < hue_deg <= 165:
        return "green"
    if 165 < hue_deg <= 255:
        return "navy" if val < 0.42 else "blue"
    if 255 < hue_deg < 300:
        return "purple"
    return None


def product_color_score(product: Product, target_color: str) -> Tuple[int, str]:
    """
    Returns (score_tier, reason):
      2 = color word explicitly named in title/attributes/description
      1 = dominant visual hex swatch from Channel3 matches target color
      0 = no color evidence
    """
    color_norm = "gray" if target_color.lower() == "grey" else target_color.lower()
    synonyms = [color_norm]
    if color_norm == "gray":
        synonyms.append("grey")
        synonyms.append("silver")
    elif color_norm == "pink":
        synonyms.append("rose")
    elif color_norm == "blue":
        synonyms.append("navy")

    title_lower = product.title.lower()
    for syn in synonyms:
        if contains_word(title_lower, syn):
            return 2, f"title lists {syn}"

    attr_blob = " ".join([
        product.description.lower(),
        " ".join(f"{k} {v}".lower() for k, v in (product.attributes or {}).items() if k != "color_swatches"),
        " ".join(f.lower() for f in product.documented_accessibility_features),
    ])
    for syn in synonyms:
        if contains_word(attr_blob, syn):
            return 2, f"listing specifies {syn}"

    swatches = (product.attributes or {}).get("color_swatches") or []
    matched_pct = 0.0
    for sw in swatches:
        if isinstance(sw, dict):
            mapped = classify_hex_color(sw.get("hex", ""))
            if mapped in synonyms:
                matched_pct += float(sw.get("percentage") or 0.0)
    if matched_pct >= 0.18:
        return 1, f"dominant color swatch matches {color_norm}"

    return 0, ""


def extract_category_info(raw_cat: Any) -> Tuple[str, str]:
    """Parses Channel3 hierarchical category dict or string into (title, full_path)."""
    if isinstance(raw_cat, dict):
        title = str(raw_cat.get("title") or raw_cat.get("slug") or "").strip()
        path_items = raw_cat.get("path") if isinstance(raw_cat.get("path"), list) else []
        path_titles = [
            str(node.get("title") or "").strip()
            for node in path_items
            if isinstance(node, dict) and node.get("title")
        ]
        full_path = " > ".join(path_titles) if path_titles else title
        return (title or "General"), full_path
    if isinstance(raw_cat, str) and raw_cat.strip():
        return raw_cat.strip(), raw_cat.strip()
    return "General", ""


def is_followup_refinement_command(
    user_text: str,
    last_intent: Optional[StructuredSearchIntent],
) -> bool:
    """
    Distinguishes follow-up refinements ('Only black ones', 'Under $50 instead',
    'Show cheaper ones', 'Show another brand') from brand-new topic searches
    ('Now find a backpack under $40', 'LEGO Star Wars sets').
    """
    if not last_intent or not last_intent.search_query:
        return False

    t = user_text.strip().lower()

    # Explicit new-search starters override follow-up unless it says "above $X" retry
    if re.search(r"\b(?:now find|now search|new search|find me|find a|search for)\b", t):
        return False

    if re.search(r"\b(?:another brand|different brand|other brand|other brands)\b", t):
        return True

    if re.search(r"\b(?:above|over|more than)\s*\$?\d+", t) and "matching" in t:
        return True

    if t.startswith("only ") or "only show" in t or "instead" in t:
        return True

    if any(p in t for p in ["cheaper one", "cheaper ones", "show cheaper", "lower price"]):
        return True

    # Pure price or color constraint without a new product noun (e.g. "Under $50", "In black")
    without_price = re.sub(r"(?:under|below|less than|max|up to|above|over)\s*\$?\d+(?:\.\d+)?", "", t)
    without_fillers = re.sub(
        r"\b(only|show|me|in|the|ones|one|products|options|instead|cheaper|please|color)\b",
        " ",
        without_price,
    )
    remaining_tokens = tokenize_meaningful(without_fillers)
    if not remaining_tokens:
        return True
    if len(remaining_tokens) <= 2 and all(tok in GENERIC_COLORS or tok in {"wireless", "wired", "black", "white"} for tok in remaining_tokens):
        return True

    return False


def extract_search_intent_rules(
    user_text: str,
    last_intent: Optional[StructuredSearchIntent] = None,
    shown_brands: Optional[List[str]] = None,
) -> StructuredSearchIntent:
    """
    Generic deterministic search intent extractor.
    Preserves meaningful brand/franchise/model/color/compatibility keywords without
    hardcoding any specific brand or product.
    """
    text = user_text.strip()
    text_lower = text.lower()

    # Extract price constraints
    max_price: Optional[float] = None
    min_price: Optional[float] = None
    max_match = re.search(r"(?:under|below|less than|max|up to|budget(?: of)?)\s*\$?(\d+(?:\.\d+)?)", text_lower)
    if max_match:
        max_price = float(max_match.group(1))
    min_match = re.search(r"(?:above|over|more than|at least)\s*\$?(\d+(?:\.\d+)?)", text_lower)
    if min_match:
        min_price = float(min_match.group(1))

    # Extract color
    color: Optional[str] = None
    for c in GENERIC_COLORS:
        if contains_word(text_lower, c):
            color = "gray" if c == "grey" else c
            break

    # Extract generic features
    features: List[str] = []
    for canonical, triggers in GENERIC_FEATURES:
        if any(tr in text_lower for tr in triggers):
            if canonical not in features:
                features.append(canonical)

    # Extract generic compatibility / use-case
    compatibility: Optional[str] = None
    for canonical, triggers in GENERIC_COMPATIBILITIES:
        if any(tr in text_lower for tr in triggers):
            compatibility = canonical
            break

    # Detect follow-up refinement vs new search
    followup = is_followup_refinement_command(text, last_intent)
    if followup and last_intent:
        updated_exclude = list(last_intent.exclude_brands)
        if re.search(r"\b(?:another brand|different brand|other brand|other brands)\b", text_lower) and shown_brands:
            for b in shown_brands:
                if b and b not in updated_exclude:
                    updated_exclude.append(b)

        updated_color = color or last_intent.color
        updated_features = list(dict.fromkeys(last_intent.features + features))
        updated_max = max_price if max_price is not None else (None if min_price is not None else last_intent.max_price)
        updated_min = min_price if min_price is not None else last_intent.min_price
        sort_pref = "price_asc" if "cheap" in text_lower else last_intent.sort_preference
        updated = StructuredSearchIntent(
            raw_query=text,
            search_query=last_intent.search_query,
            product_type=last_intent.product_type,
            brand=last_intent.brand,
            character_or_franchise=last_intent.character_or_franchise,
            model=last_intent.model,
            category=last_intent.category,
            max_price=updated_max,
            min_price=updated_min,
            color=updated_color,
            size=last_intent.size,
            features=updated_features,
            compatibility=compatibility or last_intent.compatibility,
            recipient_or_use_case=last_intent.recipient_or_use_case,
            sort_preference=sort_pref,
            exclude_brands=updated_exclude,
            broaden_queries=list(last_intent.broaden_queries),
            is_followup=True,
        )
        updated.constraints = build_typed_constraints(updated)
        return updated

    # --- NEW SEARCH EXTRACTION ---
    # Natural-language recipient/age gift interpretation (e.g. "birthday gift for a 5 year old")
    recipient_use_case: Optional[str] = None
    age_gift_match = re.search(
        r"(?:birthday\s+)?gift\s+for\s+(?:a\s+)?(\d+\s*(?:-|\s)?year(?:-|\s)?old|\bkids?\b|\btoddler\b|\bchild\b)",
        text_lower,
    )
    cleaned = re.sub(r"(?:under|below|less than|max|up to|above|over|more than)\s*\$?\d+(?:\.\d+)?", " ", text)
    cleaned = re.sub(
        r"^\s*(?:now\s+)?(?:find(?:\s+me)?|search(?:\s+for)?|show(?:\s+me)?|i\s+(?:need|want)|(?:i'm\s+)?looking\s+for|get\s+me)\s+",
        "",
        cleaned,
        flags=re.IGNORECASE,
    )
    cleaned = re.sub(r"^\s*(?:a|an|the|some)\s+", "", cleaned, flags=re.IGNORECASE)
    cleaned = re.sub(r"\s+(?:for\s+my|with)\s*$", "", cleaned, flags=re.IGNORECASE)
    cleaned = re.sub(r"[?.!,]+$", "", cleaned).strip()

    if age_gift_match:
        recipient_phrase = age_gift_match.group(1).strip()
        recipient_use_case = f"birthday gift for {recipient_phrase}"
        # Express as an actionable toy/gift query instead of literal "birthday" apparel
        search_query = f"toys gift for {recipient_phrase}"
        product_type = "toys"
    else:
        search_query = re.sub(r"\s+", " ", cleaned).strip() or text
        # Derive core product_type by keeping last 1-2 meaningful noun tokens
        meaningful = tokenize_meaningful(search_query)
        product_type = " ".join(meaningful[-2:]) if len(meaningful) >= 2 else (meaningful[0] if meaningful else search_query)

    # Extract alphanumeric model codes (e.g., MX, 75379, Q20i, WH-CH520) if present
    model_tokens = [
        tok for tok in re.findall(r"\b[A-Za-z0-9-]{2,}\b", search_query)
        if any(c.isdigit() for c in tok) or (tok.isupper() and len(tok) >= 2)
    ]
    model_str = " ".join(model_tokens) if model_tokens else None

    intent = StructuredSearchIntent(
        raw_query=text,
        search_query=search_query,
        product_type=product_type,
        model=model_str,
        max_price=max_price,
        min_price=min_price,
        color=color,
        features=features,
        compatibility=compatibility,
        recipient_or_use_case=recipient_use_case,
        is_followup=False,
    )
    intent.broaden_queries = build_broadened_queries(intent)
    intent.constraints = build_typed_constraints(intent)
    return intent


def build_broadened_queries(intent: StructuredSearchIntent) -> List[str]:
    """
    Generates ordered, gradually broadened Channel3 search queries while preserving
    anchor keywords (e.g. 'Bluey plush toys' -> 'Bluey plush' -> 'Bluey toys' -> 'Bluey').
    """
    candidates: List[str] = []

    def add(q: str):
        q_clean = re.sub(r"\s+", " ", q).strip()
        if q_clean and q_clean.lower() not in {c.lower() for c in candidates}:
            candidates.append(q_clean)

    base = intent.search_query
    if intent.color and not contains_word(base.lower(), intent.color):
        add(f"{base} {intent.color}")
    add(base)

    # Remove 'for <target>' suffix as first gentle broadening if present
    no_for = re.sub(r"\s+for\s+(?:a\s+)?[a-z0-9\s-]+$", "", base, flags=re.IGNORECASE).strip()
    if no_for and no_for.lower() != base.lower():
        add(no_for)

    tokens = [t for t in base.split() if t.lower() not in {"for", "with", "and", "the", "a", "an", "sets", "set"}]
    if len(tokens) >= 2:
        anchor_prefix = " ".join(tokens[:-1])
        last_stem = stem_token(tokens[-1])
        for fam_alt in PRODUCT_BROADEN_SYNONYMS.get(last_stem, ()):
            add(f"{anchor_prefix} {fam_alt}")

    if len(tokens) >= 3:
        # Preserve anchor + core product noun first (e.g. "Bluey toys", "ApexGear mixer")
        add(f"{tokens[0]} {tokens[-1]}")
        # Then try dropping last modifier token (e.g. "Logitech MX Keys Mini" -> "Logitech MX Keys")
        add(" ".join(tokens[:-1]))

    return candidates


def _expand_subject_terms(terms: List[str]) -> List[str]:
    expanded: List[str] = []
    for t in terms:
        st = stem_token(t)
        if st not in expanded:
            expanded.append(st)
        for fam_root, fam_words in FAMILY_SYNONYMS.items():
            if st == fam_root or st in fam_words or t in fam_words:
                for fw in fam_words:
                    if fw not in expanded:
                        expanded.append(fw)
    return expanded


def _detect_query_brand_anchors(candidates: List[Product], query_tokens: List[str]) -> List[str]:
    """
    Generically detects which tokens in the user's query match actual Channel3
    product `brands` metadata across the candidate pool. Zero hardcoded brand names.
    """
    discovered: List[str] = []
    q_stems = {stem_token(t) for t in query_tokens if len(t) >= 2}
    for p in candidates:
        raw_brands = (p.attributes or {}).get("brands") or []
        if p.attributes.get("brand"):
            raw_brands = list(raw_brands) + [p.attributes["brand"]]
        for b in raw_brands:
            b_str = str(b).strip().lower()
            for bt in tokenize_meaningful(b_str, keep_short_models=True):
                if bt in q_stems or bt in {q.lower() for q in query_tokens}:
                    if bt not in discovered:
                        discovered.append(bt)
    return discovered


def score_and_filter_candidates(
    candidates: List[Product],
    intent: StructuredSearchIntent,
    enforce_budget: bool = True,
) -> Tuple[List[Product], List[Dict[str, Any]], List[Dict[str, Any]]]:
    """
    Generic relevance scoring and filtering pipeline:
    Returns (kept_ranked_products, removed_debug_items, score_debug_items).
    Never invents product data and never pads weak results with unrelated junk.
    """
    if not candidates:
        return [], [], []

    query_tokens = tokenize_meaningful(intent.search_query, keep_short_models=True)
    if intent.brand:
        for bt in tokenize_meaningful(intent.brand, keep_short_models=True):
            if bt not in query_tokens:
                query_tokens.insert(0, bt)
    if intent.character_or_franchise:
        for ct in tokenize_meaningful(intent.character_or_franchise, keep_short_models=True):
            if ct not in query_tokens:
                query_tokens.insert(0, ct)

    discovered_brands = _detect_query_brand_anchors(candidates, query_tokens)
    model_tokens = tokenize_meaningful(intent.model or "", keep_short_models=True)

    # Identify core subject / product-type words (words in query not purely color/feature/brand/compatibility)
    feature_words = {w for f in intent.features for w in tokenize_meaningful(f, keep_short_models=True)}
    compat_words = set(tokenize_meaningful(intent.compatibility or "", keep_short_models=True))
    explicit_brand_words = {
        w
        for src in (intent.brand, intent.character_or_franchise)
        if src
        for w in tokenize_meaningful(src, keep_short_models=True)
    }
    color_word = (intent.color or "").lower()
    raw_subject_tokens = [
        t for t in query_tokens
        if t not in discovered_brands
        and t not in explicit_brand_words
        and t != color_word
        and t not in feature_words
        and t not in compat_words
    ]
    # If query combines a leading qualifier/untagged brand/character with a known product-type noun
    # (e.g. "Bluey toys" even if Channel3 lacks a brand tag), keep ONLY the product-type noun(s) in subject_tokens
    # so the brand/character name alone cannot satisfy product-type relevance.
    inferred_anchors: List[str] = []
    family_subject_tokens = [t for t in raw_subject_tokens if stem_token(t) in FAMILY_SYNONYMS]
    if family_subject_tokens and len(raw_subject_tokens) > len(family_subject_tokens):
        subject_tokens = family_subject_tokens
        if not discovered_brands and not explicit_brand_words and not intent.recipient_or_use_case:
            candidate_inferred = [
                t for t in raw_subject_tokens
                if t not in family_subject_tokens
                and t not in model_tokens
                and not t.isdigit()
                and len(t) >= 3
                and t not in {
                    "year", "old", "new", "best", "good", "kids", "kid", "child",
                    "running", "walking", "training", "sports", "water", "gaming",
                    "travel", "smart", "soft", "small", "large", "mini", "portable",
                }
            ]
            if candidate_inferred:
                for p_chk in candidates:
                    blob_chk = f"{p_chk.title} {p_chk.category} {p_chk.description}".lower()
                    if all(contains_word(blob_chk, ca) for ca in candidate_inferred):
                        inferred_anchors = candidate_inferred
                        break
    else:
        subject_tokens = raw_subject_tokens

    if not subject_tokens and intent.product_type:
        pt_tokens = tokenize_meaningful(intent.product_type, keep_short_models=True)
        pt_non_brand = [t for t in pt_tokens if t not in discovered_brands and t not in explicit_brand_words]
        subject_tokens = pt_non_brand or pt_tokens
    subject_expanded = _expand_subject_terms(subject_tokens)

    wants_accessory = any(w in intent.search_query.lower() for w in (
        "case", "cover", "sleeve", "cable", "cord", "strap", "band", "pad", "stand",
        "mount", "replacement", "brush", "cleaner", "bag", "organizer", "storage", "mat", "rest", "keycap",
    ))
    wants_decor = any(w in intent.search_query.lower() for w in (
        "banner", "bunting", "garland", "decor", "decoration", "decorations", "party",
        "balloon", "balloons", "inflatable", "blow mold", "poster", "posters", "backdrop",
        "tablecloth", "cake topper", "costume", "decal", "wrapping", "invitation", "card",
    ))
    wants_apparel = any(w in intent.search_query.lower() for w in (
        "shirt", "t-shirt", "hoodie", "sweatshirt", "costume", "cosplay", "jacket",
        "pants", "shorts", "pajama", "pajamas", "socks", "hat", "cap", "beanie", "clothing",
    ))
    wants_speaker = contains_word(intent.search_query.lower(), "speaker")
    wants_combo = any(w in intent.search_query.lower() for w in ("combo", "bundle", "with mouse", "and mouse", "set"))

    scored_pool: List[Tuple[float, int, Product]] = []
    removed_log: List[Dict[str, Any]] = []
    score_log: List[Dict[str, Any]] = []

    for orig_idx, prod in enumerate(candidates):
        if enforce_budget:
            if intent.max_price is not None and prod.price > intent.max_price:
                removed_log.append({"title": prod.title, "reason": f"over_budget (${prod.price:.2f} > ${intent.max_price:.2f})"})
                continue
            if intent.min_price is not None and prod.price < intent.min_price:
                removed_log.append({"title": prod.title, "reason": f"below_min_price (${prod.price:.2f})"})
                continue

        # Exclude previously shown brands when user requested 'another brand'
        prod_brands = [str(b).lower() for b in ((prod.attributes or {}).get("brands") or [])]
        if prod.attributes.get("brand"):
            prod_brands.append(str(prod.attributes["brand"]).lower())
        if intent.exclude_brands:
            excl_lower = {eb.lower() for eb in intent.exclude_brands}
            if any(pb in excl_lower or any(eb in pb for eb in excl_lower) for pb in prod_brands):
                removed_log.append({"title": prod.title, "reason": "excluded_brand"})
                continue

        title_lower = prod.title.lower()
        cat_lower = f"{prod.category} {prod.attributes.get('category_path', '')}".lower()
        brand_lower = " ".join(prod_brands)
        feat_attr_lower = " ".join(
            [f.lower() for f in prod.documented_accessibility_features]
            + [f"{k} {v}".lower() for k, v in (prod.attributes or {}).items() if k != "color_swatches"]
        )
        desc_lower = prod.description.lower()

        # Filter obvious mismatched accessories (e.g. headphone case / palm rest / keycaps / shoe bag / cleaning brush)
        if not wants_accessory and any(contains_word(title_lower, marker) for marker in ACCESSORY_ONLY_MARKERS):
            removed_log.append({"title": prod.title, "reason": "irrelevant_accessory"})
            continue

        # Filter party/seasonal decorations, posters, banners, inflatables unless user asked for decor
        if not wants_decor and any(contains_word(f"{title_lower} {cat_lower}", dm) for dm in DECORATION_MARKERS):
            removed_log.append({"title": prod.title, "reason": "irrelevant_decoration"})
            continue

        # Filter clothing/costumes when searching toys/dolls/shoes/electronics unless user asked for apparel
        if not wants_apparel and any(contains_word(f"{title_lower} {cat_lower}", am) for am in APPAREL_COSTUME_MISMATCH_MARKERS):
            removed_log.append({"title": prod.title, "reason": "irrelevant_apparel_or_costume"})
            continue

        # Reject standalone speakers when user specifically asked for headphones/earbuds
        if not wants_speaker and any(st in ("headphone", "earbud") for st in subject_expanded):
            if contains_word(f"{title_lower} {cat_lower}", "speaker") and not any(
                contains_word(title_lower, hw) for hw in ("headphone", "headphones", "headset", "earbud", "earbuds")
            ):
                removed_log.append({"title": prod.title, "reason": "wrong_audio_device_speaker"})
                continue

        # Check discovered brand/franchise anchor (e.g., Bluey, Nike, Barbie, LEGO, Logitech)
        brand_hit_count = 0
        for db_tok in discovered_brands:
            if contains_word(brand_lower, db_tok) or contains_word(title_lower, db_tok):
                brand_hit_count += 1
        if discovered_brands and brand_hit_count == 0:
            removed_log.append({"title": prod.title, "reason": f"missing_anchor_brand ({','.join(discovered_brands)})"})
            continue

        # Check core subject / category family match in title, category, or structured features
        subject_hit = True
        if subject_expanded:
            title_cat_feat = f"{title_lower} {cat_lower} {feat_attr_lower}"
            subject_hit = any(contains_word(title_cat_feat, st) for st in subject_expanded)
            if not subject_hit:
                removed_log.append({"title": prod.title, "reason": "unrelated_product_type"})
                continue

        # Enforce explicit character/franchise, brand, or inferred leading keyword anchors
        explicit_anchors: List[str] = list(inferred_anchors)
        for anchor_src in (intent.brand, intent.character_or_franchise):
            if anchor_src:
                for tok in tokenize_meaningful(anchor_src, keep_short_models=True):
                    if tok not in discovered_brands and tok not in explicit_anchors:
                        explicit_anchors.append(tok)
        if explicit_anchors:
            anchor_surface = f"{title_lower} {brand_lower} {cat_lower} {desc_lower}"
            if not all(contains_word(anchor_surface, at) for at in explicit_anchors):
                removed_log.append({"title": prod.title, "reason": f"missing_explicit_anchor ({','.join(explicit_anchors)})"})
                continue

        # Enforce explicit alphanumeric/code model tokens when present (e.g. MX, Q20i, 75379)
        specific_model_tokens = [
            mt for mt in model_tokens
            if mt not in discovered_brands
            and mt not in {"usb", "usbc", "c", "led", "hd", "4k", "tv", "pc", "pro", "max", "mini"}
        ]
        if specific_model_tokens:
            model_surface = f"{title_lower} {brand_lower} {feat_attr_lower}"
            if not any(contains_word(model_surface, mt) for mt in specific_model_tokens):
                removed_log.append({"title": prod.title, "reason": f"missing_model_token ({','.join(specific_model_tokens)})"})
                continue

        # Calculate generic relevance score
        score = 0.0
        clean_q = re.sub(r"\s+", " ", intent.search_query.lower()).strip()
        if clean_q and clean_q in title_lower:
            score += 45.0

        for mt in model_tokens:
            if contains_word(title_lower, mt):
                score += 28.0

        score += brand_hit_count * 25.0

        matched_q = 0
        for qt in query_tokens:
            if contains_word(title_lower, qt):
                score += 14.0
                matched_q += 1
            elif contains_word(cat_lower, qt):
                score += 10.0
                matched_q += 1
            elif contains_word(brand_lower, qt):
                score += 10.0
                matched_q += 1
            elif contains_word(feat_attr_lower, qt):
                score += 7.0
                matched_q += 1
            elif contains_word(desc_lower, qt):
                score += 3.5
                matched_q += 1

        if query_tokens:
            score += (matched_q / len(query_tokens)) * 24.0

        # Product Type is #1 priority: strongly reward primary product-type noun appearing in title or category
        if subject_expanded:
            if any(contains_word(title_lower, st) for st in subject_tokens):
                score += 40.0
            elif any(contains_word(title_lower, st) for st in subject_expanded):
                score += 32.0
            elif any(contains_word(cat_lower, st) for st in subject_expanded):
                score += 22.0
            elif not subject_hit:
                score -= 25.0

        # Penalize multi-item combos when a standalone product matches (e.g., Logitech MX Keys Keyboard vs Keyboard + Mouse combo)
        if not wants_combo and any(bm in title_lower for bm in BUNDLE_MARKERS):
            score -= 16.0

        # Feature constraints
        for ft in intent.features:
            if contains_word(title_lower, ft) or contains_word(feat_attr_lower, ft):
                score += 15.0
            elif contains_word(desc_lower, ft):
                score += 7.0
            elif ft == "wireless" and contains_word(f"{title_lower} {feat_attr_lower}", "bluetooth"):
                score += 14.0

        # Compatibility constraints (e.g., iPhone, Mac)
        if intent.compatibility:
            if contains_word(title_lower, intent.compatibility) or contains_word(feat_attr_lower, intent.compatibility):
                score += 16.0
            elif contains_word(desc_lower, intent.compatibility):
                score += 8.0
            elif intent.compatibility == "iphone" and contains_word(f"{title_lower} {desc_lower}", "apple"):
                score += 6.0

        # Color constraint
        if intent.color:
            tier, _ = product_color_score(prod, intent.color)
            if tier == 2:
                score += 22.0
            elif tier == 1:
                score += 10.0
            else:
                score -= 8.0

        if prod.is_available:
            score += 2.0

        # Reject weak matches with too little relevance
        min_score = 18.0 if len(query_tokens) >= 2 else 12.0
        if score < min_score:
            removed_log.append({"title": prod.title, "reason": f"low_relevance_score ({score:.1f})"})
            continue

        scored_pool.append((score, orig_idx, prod))
        score_log.append({"title": prod.title, "score": round(score, 1), "price": prod.price})

    # If user explicitly asked for a color and we found explicit text-verified color matches,
    # filter out non-matching color items so wrong-color items don't dilute results.
    if intent.color and scored_pool:
        explicit_color = [(sc, idx, p) for sc, idx, p in scored_pool if product_color_score(p, intent.color)[0] == 2]
        swatch_color = [(sc, idx, p) for sc, idx, p in scored_pool if product_color_score(p, intent.color)[0] >= 1]
        if explicit_color:
            scored_pool = explicit_color
        elif swatch_color:
            scored_pool = swatch_color

    # Sort by relevance first (preserving provider order on relevance ties unless explicit sort requested)
    if intent.sort_preference == "price_asc":
        scored_pool.sort(key=lambda item: (item[2].price, -item[0], item[1]))
    elif intent.sort_preference == "price_desc":
        scored_pool.sort(key=lambda item: (-item[2].price, -item[0], item[1]))
    elif intent.sort_preference == "rating_desc":
        scored_pool.sort(key=lambda item: (-(item[2].rating or 0.0), -item[0], item[1]))
    else:
        scored_pool.sort(key=lambda item: (-round(item[0], 1), item[1]))

    ranked_products = [p for _, _, p in scored_pool]
    if ranked_products:
        cheapest = min(ranked_products, key=lambda p: p.price)
        for idx, p in enumerate(ranked_products):
            if idx == 0:
                p.ranking_badge = "BEST MATCH"
                p.ranking_reason = f"Best match for '{intent.search_query}' at ${p.price:.2f} from {p.merchant}."
            elif p.id == cheapest.id:
                p.ranking_badge = "LOWEST PRICE"
                p.ranking_reason = f"Lowest price matching option at ${p.price:.2f} from {p.merchant}."
            elif idx == 1:
                p.ranking_badge = "BEST VALUE"
                p.ranking_reason = f"Strong match at ${p.price:.2f} from {p.merchant}."
            else:
                p.ranking_badge = "OPTION"
                p.ranking_reason = f"${p.price:.2f} from {p.merchant}."

            cheaper_opts = [c for c in ranked_products if c.price < p.price and c.id != p.id]
            if cheaper_opts:
                best_cheaper = min(cheaper_opts, key=lambda c: c.price)
                p.cheaper_alternative_id = best_cheaper.id
                p.savings_amount = round(p.price - best_cheaper.price, 2)

    return ranked_products, removed_log, score_log
