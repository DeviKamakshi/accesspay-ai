import datetime
import re
import uuid
from enum import Enum
from typing import Any, Dict, List, Optional
from pydantic import BaseModel, Field

from app.services.search_engine import (
    GENERIC_COLORS,
    StructuredSearchIntent,
    TypedConstraint,
    build_broadened_queries,
    build_typed_constraints,
    contains_word,
    extract_search_intent_rules,
    is_followup_refinement_command,
    tokenize_meaningful,
)


class ConversationalAction(str, Enum):
    NEW_SEARCH = "NEW_SEARCH"
    REFINE_SEARCH = "REFINE_SEARCH"
    FILTER_RESULTS = "FILTER_RESULTS"
    SORT_RESULTS = "SORT_RESULTS"
    COMPARE = "COMPARE"
    SELECT = "SELECT"
    PRODUCT_DETAILS = "PRODUCT_DETAILS"
    CHEAPER_ALTERNATIVE = "CHEAPER_ALTERNATIVE"
    OTHER_ALTERNATIVE = "OTHER_ALTERNATIVE"
    SHOW_MORE = "SHOW_MORE"
    NEXT_OPTION = "NEXT_OPTION"
    PREVIOUS_OPTION = "PREVIOUS_OPTION"
    ADD_TO_CART = "ADD_TO_CART"
    REMOVE_FROM_CART = "REMOVE_FROM_CART"
    CHANGE_QUANTITY = "CHANGE_QUANTITY"
    VIEW_CART = "VIEW_CART"
    CHECK_TOTAL = "CHECK_TOTAL"
    PREPARE_CHECKOUT = "PREPARE_CHECKOUT"
    SAVE_ITEM = "SAVE_ITEM"
    VIEW_SAVED_ITEMS = "VIEW_SAVED_ITEMS"
    REMOVE_SAVED_ITEM = "REMOVE_SAVED_ITEM"
    SAVE_SEARCH = "SAVE_SEARCH"
    VIEW_SAVED_SEARCHES = "VIEW_SAVED_SEARCHES"
    OPEN_SAVED_SEARCH = "OPEN_SAVED_SEARCH"
    OPEN_SAVED_ITEM = "OPEN_SAVED_ITEM"
    ADD_SAVED_ITEM_TO_CART = "ADD_SAVED_ITEM_TO_CART"
    VIEW_ORDERS = "VIEW_ORDERS"
    OPEN_ORDER = "OPEN_ORDER"
    OPEN_PREVIOUS_ORDER = "OPEN_PREVIOUS_ORDER"
    ORDER_DETAIL_QUERY = "ORDER_DETAIL_QUERY"
    REORDER = "REORDER"
    OPEN_SHOP = "OPEN_SHOP"
    OPEN_CART = "OPEN_CART"
    CLEAR_CART = "CLEAR_CART"
    READ_REVIEW = "READ_REVIEW"
    PROCEED_TO_CONFIRMATION = "PROCEED_TO_CONFIRMATION"
    PAYPAL_APPROVAL_NAVIGATION = "PAYPAL_APPROVAL_NAVIGATION"
    READ_RECEIPT = "READ_RECEIPT"
    READ_ORDER_ID = "READ_ORDER_ID"
    RETRY_PAYMENT = "RETRY_PAYMENT"
    CONFIRMATION_ATTEMPT = "CONFIRMATION_ATTEMPT"
    CANCEL = "CANCEL"
    GO_BACK = "GO_BACK"
    HELP = "HELP"
    CLARIFICATION_NEEDED = "CLARIFICATION_NEEDED"
    UNKNOWN = "UNKNOWN"


class StructuredActionOutput(BaseModel):
    action: ConversationalAction
    references: List[str] = Field(default_factory=list)
    constraint_updates: Dict[str, Any] = Field(default_factory=dict)
    typed_constraints: List[TypedConstraint] = Field(default_factory=list)
    starts_new_search: bool = False
    needs_clarification: bool = False
    clarification_question: Optional[str] = None
    search_query: Optional[str] = None
    product_type: Optional[str] = None
    brand: Optional[str] = None
    model: Optional[str] = None
    category: Optional[str] = None
    character_or_franchise: Optional[str] = None
    max_price: Optional[float] = None
    min_price: Optional[float] = None
    color: Optional[str] = None
    size: Optional[str] = None
    features: List[str] = Field(default_factory=list)
    compatibility: Optional[str] = None
    recipient_or_use_case: Optional[str] = None
    sort_preference: Optional[str] = None


def _utc_now_iso() -> str:
    return datetime.datetime.now(datetime.timezone.utc).isoformat()


class ShoppingSession(BaseModel):
    """
    Single authoritative ActiveSearchSession state.
    Maintains the current search universe, displayed/candidate products,
    constraints, comparison/selection state, and search generation counter.
    """
    session_id: str = Field(default_factory=lambda: uuid.uuid4().hex[:12])
    search_id: str = Field(default_factory=lambda: f"search_{uuid.uuid4().hex[:10]}")
    search_generation: int = 0
    original_user_query: str = ""
    original_query: str = ""
    display_query: str = ""
    structured_search_intent: Optional[StructuredSearchIntent] = None
    hard_constraints: List[Dict[str, Any]] = Field(default_factory=list)
    soft_constraints: List[Dict[str, Any]] = Field(default_factory=list)
    product_type: str = ""
    brand: Optional[str] = None
    model: Optional[str] = None
    category: Optional[str] = None
    character_or_franchise: Optional[str] = None
    price_constraints: Dict[str, Optional[float]] = Field(
        default_factory=lambda: {"min_price": None, "max_price": None}
    )
    features: List[str] = Field(default_factory=list)
    color: Optional[str] = None
    size: Optional[str] = None
    compatibility: Optional[str] = None
    recipient_or_use_case: Optional[str] = None
    active_filters: Dict[str, Any] = Field(default_factory=dict)
    filters: Dict[str, Any] = Field(default_factory=dict)
    sort: Optional[str] = None
    candidate_products: List[Dict[str, Any]] = Field(default_factory=list)
    displayed_products: List[Dict[str, Any]] = Field(default_factory=list)
    selected_product: Optional[Dict[str, Any]] = None
    comparison_products: List[Dict[str, Any]] = Field(default_factory=list)
    last_discussed_product: Optional[Dict[str, Any]] = None
    alternative_product: Optional[Dict[str, Any]] = None
    pending_clarification: Optional[Dict[str, Any]] = None
    cart: Dict[str, Any] = Field(default_factory=dict)
    last_action: str = "NONE"
    last_user_message: str = ""
    candidate_offset: int = 0
    has_more: bool = False
    total_available: int = 0
    created_at: str = Field(default_factory=_utc_now_iso)
    updated_at: str = Field(default_factory=_utc_now_iso)

    @property
    def structured_intent(self) -> Optional[StructuredSearchIntent]:
        return self.structured_search_intent

    def reset(self):
        self.session_id = uuid.uuid4().hex[:12]
        self.search_id = f"search_{uuid.uuid4().hex[:10]}"
        self.search_generation = 0
        self.original_user_query = ""
        self.original_query = ""
        self.display_query = ""
        self.structured_search_intent = None
        self.hard_constraints = []
        self.soft_constraints = []
        self.product_type = ""
        self.brand = None
        self.model = None
        self.category = None
        self.character_or_franchise = None
        self.price_constraints = {"min_price": None, "max_price": None}
        self.features = []
        self.color = None
        self.size = None
        self.compatibility = None
        self.recipient_or_use_case = None
        self.active_filters = {}
        self.filters = {}
        self.sort = None
        self.candidate_products = []
        self.displayed_products = []
        self.selected_product = None
        self.comparison_products = []
        self.last_discussed_product = None
        self.alternative_product = None
        self.pending_clarification = None
        self.cart = {}
        self.last_action = "NONE"
        self.last_user_message = ""
        self.candidate_offset = 0
        self.has_more = False
        self.total_available = 0
        now = _utc_now_iso()
        self.created_at = now
        self.updated_at = now

    def start_new_generation(self, query: str, intent: StructuredSearchIntent) -> int:
        """
        Begins a fresh ActiveSearchSession generation, incrementing search_generation and
        clearing stale comparison/selection/alternative/candidate data from prior generations.
        Never touches Cart, Saved Items, Saved Searches, or Order History.
        """
        self.search_generation += 1
        self.search_id = f"search_{self.search_generation}_{uuid.uuid4().hex[:8]}"
        self.original_user_query = query
        self.original_query = query
        self.display_query = (intent.search_query or query or "").strip()
        if intent.max_price is not None and f"${int(intent.max_price)}" not in self.display_query and "under" not in self.display_query.lower():
            budget_disp = f"${int(intent.max_price)}" if float(intent.max_price).is_integer() else f"${intent.max_price:.2f}"
            self.display_query = f"{self.display_query} under {budget_disp}".strip()
        self.candidate_products = []
        self.displayed_products = []
        self.selected_product = None
        self.comparison_products = []
        self.last_discussed_product = None
        self.alternative_product = None
        self.pending_clarification = None
        self.candidate_offset = 0
        self.has_more = False
        self.total_available = 0
        self.created_at = _utc_now_iso()
        self.sync_from_intent(intent)
        return self.search_generation

    def sync_from_intent(self, intent: StructuredSearchIntent):
        if not intent.constraints:
            intent.constraints = build_typed_constraints(intent)
        self.structured_search_intent = intent
        self.product_type = intent.product_type
        self.brand = intent.brand
        self.model = intent.model
        self.category = intent.category
        self.character_or_franchise = intent.character_or_franchise
        self.price_constraints = {"min_price": intent.min_price, "max_price": intent.max_price}
        self.features = list(intent.features)
        self.color = intent.color
        self.size = intent.size
        self.compatibility = intent.compatibility
        self.recipient_or_use_case = intent.recipient_or_use_case
        self.hard_constraints = [c.model_dump() for c in intent.constraints if getattr(c, "hard", True)]
        self.soft_constraints = [c.model_dump() for c in intent.constraints if not getattr(c, "hard", True)]
        filter_dict = {
            "max_price": intent.max_price,
            "min_price": intent.min_price,
            "color": intent.color,
            "size": intent.size,
            "features": list(intent.features),
            "compatibility": intent.compatibility,
            "exclude_brands": list(intent.exclude_brands),
            "sort_preference": intent.sort_preference,
        }
        self.active_filters = filter_dict
        self.filters = filter_dict
        self.sort = intent.sort_preference
        self.updated_at = _utc_now_iso()

    def build_invariant_cheaper_intent(self, reference_price: float) -> Optional[StructuredSearchIntent]:
        """
        Builds a constrained intent for finding a cheaper alternative matching ALL active
        product identity / brand / model / franchise / feature / compatibility requirements.
        """
        base = self.structured_search_intent
        if not base:
            return None
        strict_cap = round(max(0.5, reference_price - 0.01), 2)
        if base.max_price is not None:
            strict_cap = min(strict_cap, float(base.max_price))
        cloned = base.model_copy(deep=True)
        cloned.max_price = strict_cap
        cloned.sort_preference = "price_asc"
        cloned.is_followup = True
        cloned.constraints = build_typed_constraints(cloned)
        return cloned

    def shown_brands(self) -> List[str]:
        brands: List[str] = []
        for p in self.displayed_products:
            attrs = p.get("attributes") or {}
            b = attrs.get("brand")
            if b and str(b) not in brands:
                brands.append(str(b))
        return brands

    def synchronize_visible_products(
        self,
        active_search_id: Optional[str] = None,
        search_generation: Optional[int] = None,
        visible_product_ids: Optional[List[str]] = None,
    ) -> List[str]:
        """
        Ensures session.displayed_products preserves the exact visual card order shown
        on the client when those IDs exist in the current ActiveSearchSession.
        """
        if not visible_product_ids:
            return [p.get("id") for p in self.displayed_products if p.get("id")]
        if active_search_id and self.search_id and active_search_id != self.search_id:
            return [p.get("id") for p in self.displayed_products if p.get("id")]
        if search_generation is not None and search_generation != self.search_generation:
            return [p.get("id") for p in self.displayed_products if p.get("id")]

        pool_by_id: Dict[str, Dict[str, Any]] = {}
        for item in self.candidate_products + self.displayed_products:
            pid = item.get("id")
            if pid and pid not in pool_by_id:
                pool_by_id[pid] = item

        reordered: List[Dict[str, Any]] = []
        seen: set[str] = set()
        for pid in visible_product_ids:
            if pid in pool_by_id and pid not in seen:
                reordered.append(pool_by_id[pid])
                seen.add(pid)

        if reordered:
            for item in self.displayed_products:
                pid = item.get("id")
                if pid and pid not in seen:
                    reordered.append(item)
                    seen.add(pid)
            self.displayed_products = reordered

        return [p.get("id") for p in self.displayed_products if p.get("id")]


def normalize_conversational_transcript(text: Optional[str]) -> str:
    """
    Normalizes spoken/typed command transcripts safely without stripping product keywords,
    numbers, or ordinals. Preserves '?' for attribute/clarification questions.
    """
    if not text:
        return ""
    cleaned = re.sub(r"\s+", " ", str(text)).strip()
    if not cleaned:
        return ""
    # Strip harmless trailing dictation punctuation while keeping '?' intact
    cleaned = re.sub(r"[.,;!]+$", "", cleaned).strip()
    # Fix unambiguous speech homophones only inside explicit ordinal phrases
    cleaned = re.sub(
        r"\b(first|top|last|cheapest)\s+to\s+(options?|products?|items?|results?|ones?)\b",
        r"\1 two \2",
        cleaned,
        flags=re.IGNORECASE,
    )
    cleaned = re.sub(
        r"\b(option|number)\s+won\b",
        r"\1 one",
        cleaned,
        flags=re.IGNORECASE,
    )
    return re.sub(r"\s+", " ", cleaned).strip()


ActiveSearchSession = ShoppingSession


CONVERSATIONAL_FILLER_TOKENS = {
    "a", "an", "the", "of", "in", "on", "to", "for", "with", "at", "by", "from", "into",
    "and", "or", "under", "over", "below", "above", "than", "less", "more", "my", "me", "i", "we", "you", "your",
    "hi", "hello", "hey", "thanks", "thank", "please", "ok", "okay", "sure", "yes", "yeah",
    "no", "nope", "maybe", "hmm", "well", "wait", "actually", "tell", "more", "about",
    "this", "that", "these", "those", "them", "they", "it", "its", "which", "what", "who",
    "where", "when", "why", "how", "can", "could", "would", "should", "will", "do", "does",
    "did", "is", "are", "was", "were", "be", "have", "has", "had", "one", "ones", "option",
    "options", "product", "products", "item", "items", "thing", "things", "something",
    "anything", "everything", "nothing", "else", "other", "another", "same", "different",
    "better", "best", "good", "great", "nice", "fine", "compare", "comparison", "versus",
    "difference", "between", "choose", "select", "pick", "take", "keep", "details", "detail",
    "info", "information", "describe", "explain", "specs", "specification", "specifications",
    "feature", "features", "first", "second", "third", "fourth", "last", "final", "cheapest",
    "cheaper", "expensive", "priciest", "lowest", "highest", "price", "cost", "sort", "order",
    "filter", "only", "instead", "again", "back", "next", "previous", "earlier", "later",
    "help", "cart", "bag", "total", "checkout", "review", "confirm", "cancel", "stop", "abort",
    "repeat", "say", "mean", "looking", "recommend", "recommendation", "suggest", "suggestion",
    "show", "give", "find", "search",
}

EXPLICIT_SEARCH_STARTERS = re.compile(
    r"^\s*(?:now\s+)?(?:find(?:\s+me)?|search(?:\s+for)?|look(?:ing)?\s+for|i\s+(?:need|want)|get\s+me|shop(?:\s+for)?|show\s+me\s+(?:a|an|some))\b",
    re.IGNORECASE,
)


def _has_product_search_substance(user_text: str) -> bool:
    """Returns True when text contains non-filler nouns/modifiers suitable for a product search."""
    cleaned = re.sub(r"(?:under|below|less than|max|up to|above|over|more than)\s*\$?\d+(?:\.\d+)?", " ", user_text.lower())
    tokens = re.findall(r"[a-z0-9]+(?:-[a-z0-9]+)*", cleaned)
    meaningful = [
        t for t in tokens
        if t not in CONVERSATIONAL_FILLER_TOKENS and len(t) >= 2
    ]
    return len(meaningful) > 0


def resolve_product_references(
    user_text: str,
    session: ShoppingSession,
    expected_count: int = 1,
    explicit_refs: Optional[List[str]] = None,
) -> Dict[str, Any]:
    """
    Generically resolves ordinal, price-relative, selected/discussed, and name/brand
    references strictly against products stored in the active ShoppingSession.
    Never guesses silently and never triggers an external search.
    """
    pool = session.displayed_products or session.candidate_products
    if not pool:
        return {
            "products": [],
            "indices": [],
            "ids": [],
            "ambiguous": False,
            "empty_pool": True,
            "question": "There are no active products in your current search yet. Tell me what you would like to search for.",
        }

    search_text = " ".join([user_text] + list(explicit_refs or [])).lower().strip()
    indices: List[int] = []

    def add_idx(i: int):
        if 0 <= i < len(pool) and i not in indices:
            indices.append(i)

    # Multi-item shorthands
    if re.search(r"\b(?:first\s+(?:two|2)|top\s+(?:two|2)|both)\b", search_text):
        add_idx(0)
        add_idx(1)
    elif re.search(r"\b(?:last\s+(?:two|2))\b", search_text) and len(pool) >= 2:
        add_idx(len(pool) - 2)
        add_idx(len(pool) - 1)
    elif re.search(r"\b(?:cheapest\s+(?:two|2)|lowest\s+(?:two|2))\b", search_text) and len(pool) >= 2:
        by_price = sorted(range(len(pool)), key=lambda i: pool[i].get("price", 0.0))
        add_idx(by_price[0])
        add_idx(by_price[1])

    # Individual ordinals up to 12 (avoid matching bare "one" inside "cheaper one" / "which one")
    ordinal_patterns = [
        (0, r"\b(?:first|1st|option\s*1|number\s*1|#1)\b"),
        (1, r"\b(?:second|2nd|option\s*2|number\s*2|#2|two)\b"),
        (2, r"\b(?:third|3rd|option\s*3|number\s*3|#3|three)\b"),
        (3, r"\b(?:fourth|4th|option\s*4|number\s*4|#4|four)\b"),
        (4, r"\b(?:fifth|5th|option\s*5|number\s*5|#5|five)\b"),
        (5, r"\b(?:sixth|6th|option\s*6|number\s*6|#6|six)\b"),
        (6, r"\b(?:seventh|7th|option\s*7|number\s*7|#7)\b"),
        (7, r"\b(?:eighth|8th|option\s*8|number\s*8|#8)\b"),
        (8, r"\b(?:ninth|9th|option\s*9|number\s*9|#9)\b"),
        (9, r"\b(?:tenth|10th|option\s*10|number\s*10|#10)\b"),
        (10, r"\b(?:eleventh|11th|option\s*11|number\s*11|#11)\b"),
        (11, r"\b(?:twelfth|12th|option\s*12|number\s*12|#12)\b"),
    ]
    for idx_val, pat in ordinal_patterns:
        if idx_val == 1 and re.search(r"\b(?:first|last|top|cheapest)\s+two\b", search_text):
            continue
        if re.search(pat, search_text):
            add_idx(idx_val)
    if re.search(r"\b(?:last|final)\b", search_text) and not re.search(r"\blast\s+two\b", search_text):
        add_idx(len(pool) - 1)

    # Price-relative references (e.g. "cheapest", "cheaper one", "less expensive", "most expensive")
    if not indices:
        comp_ids = {p.get("id") for p in session.comparison_products if p.get("id")}
        price_scope = [i for i, p in enumerate(pool) if p.get("id") in comp_ids] if len(comp_ids) >= 2 else list(range(len(pool)))
        if re.search(r"\b(?:cheapest|cheaper|lowest\s+priced?|lower\s+priced?|least\s+expensive|less\s+expensive)\b", search_text):
            add_idx(min(price_scope, key=lambda i: pool[i].get("price", float("inf"))))
        elif re.search(r"\b(?:most\s+expensive|more\s+expensive|priciest|pricier|highest\s+priced?|higher\s+priced?|costliest)\b", search_text):
            add_idx(max(price_scope, key=lambda i: pool[i].get("price", float("-inf"))))

    # Context / pronoun / other-one references
    if not indices:
        if re.search(r"\b(?:other\s+one|the\s+other)\b", search_text):
            anchor = session.last_discussed_product or session.selected_product
            anchor_id = anchor.get("id") if anchor else None
            others = [i for i, p in enumerate(pool) if p.get("id") != anchor_id]
            if len(others) == 1:
                add_idx(others[0])
            elif anchor_id and len(others) > 1:
                return {
                    "products": [],
                    "indices": [],
                    "ids": [],
                    "ambiguous": True,
                    "empty_pool": False,
                    "question": f"I currently have {len(pool)} options shown. Which of the other options do you mean?",
                }

    if not indices and re.search(r"\b(?:selected\s+one|currently\s+selected|my\s+selection)\b", search_text):
        if session.selected_product:
            sel_idx = next((i for i, p in enumerate(pool) if p.get("id") == session.selected_product.get("id")), None)
            if sel_idx is not None:
                add_idx(sel_idx)
            else:
                return {
                    "products": [session.selected_product],
                    "indices": [],
                    "ids": [session.selected_product["id"]],
                    "ambiguous": False,
                    "empty_pool": False,
                    "question": None,
                }

    # Product name / brand / model token matching against displayed products
    if not indices:
        ref_tokens = [
            t for t in tokenize_meaningful(search_text, keep_short_models=True)
            if t not in CONVERSATIONAL_FILLER_TOKENS and len(t) >= 2
        ]
        if ref_tokens:
            scored_hits = []
            for idx, prod in enumerate(pool):
                attrs = prod.get("attributes") or {}
                surface = " ".join([
                    str(prod.get("title") or ""),
                    str(attrs.get("brand") or ""),
                    " ".join(str(b) for b in (attrs.get("brands") or [])),
                    str(prod.get("merchant") or ""),
                ]).lower()
                hits = sum(1 for tok in ref_tokens if contains_word(surface, tok))
                if hits > 0:
                    scored_hits.append((hits, idx))
            if scored_hits:
                scored_hits.sort(key=lambda x: -x[0])
                best_score = scored_hits[0][0]
                top_matches = [idx for sc, idx in scored_hits if sc == best_score]
                if expected_count >= 2:
                    for _, idx in scored_hits[:expected_count]:
                        add_idx(idx)
                elif len(top_matches) == 1:
                    add_idx(top_matches[0])
                elif len(top_matches) > 1:
                    opts_desc = ", ".join([f"Option {i+1} ({pool[i]['title']})" for i in top_matches])
                    return {
                        "products": [],
                        "indices": [],
                        "ids": [],
                        "ambiguous": True,
                        "empty_pool": False,
                        "question": f"Multiple current options match that name: {opts_desc}. Which option number do you want?",
                    }

    # Pronoun / implicit comparison / implicit detail fallback
    if not indices:
        if expected_count >= 2:
            if len(pool) == 2:
                add_idx(0)
                add_idx(1)
            else:
                return {
                    "products": [],
                    "indices": [],
                    "ids": [],
                    "ambiguous": True,
                    "empty_pool": False,
                    "question": f"I currently have {len(pool)} products. Which ones would you like to compare (for example, the first two, or 1 and 3)?",
                }
        else:
            if len(pool) == 1:
                add_idx(0)
            elif re.search(r"\b(?:it|that\s+one|this\s+one|same\s+one)\b", search_text):
                target = session.last_discussed_product or session.selected_product
                if target:
                    t_idx = next((i for i, p in enumerate(pool) if p.get("id") == target.get("id")), None)
                    if t_idx is not None:
                        add_idx(t_idx)
                    else:
                        return {
                            "products": [target],
                            "indices": [],
                            "ids": [target["id"]],
                            "ambiguous": False,
                            "empty_pool": False,
                            "question": None,
                        }
                else:
                    return {
                        "products": [],
                        "indices": [],
                        "ids": [],
                        "ambiguous": True,
                        "empty_pool": False,
                        "question": f"I currently have {len(pool)} options shown. Which option do you mean (1 to {len(pool)})?",
                    }
            else:
                return {
                    "products": [],
                    "indices": [],
                    "ids": [],
                    "ambiguous": True,
                    "empty_pool": False,
                    "question": f"I currently have {len(pool)} options shown. Which option do you mean (1 to {len(pool)})?",
                }

    resolved_prods = [pool[i] for i in indices]
    resolved_ids = [p["id"] for p in resolved_prods]

    if expected_count >= 2 and len(resolved_prods) < 2:
        if len(pool) == 2:
            resolved_prods = list(pool[:2])
            indices = [0, 1]
            resolved_ids = [p["id"] for p in resolved_prods]
        else:
            return {
                "products": [],
                "indices": [],
                "ids": [],
                "ambiguous": True,
                "empty_pool": False,
                "question": f"Please pick two current options to compare (1 to {len(pool)}).",
            }

    return {
        "products": resolved_prods,
        "indices": indices,
        "ids": resolved_ids,
        "ambiguous": False,
        "empty_pool": False,
        "question": None,
    }


def parse_ordinal_index(text: str) -> Optional[int]:
    """Generic 0-based ordinal parser for items, saved entries, cart lines, or orders."""
    t = (text or "").lower()
    ordinal_patterns = [
        (0, r"\b(?:first|1st|option\s*#?1|item\s*#?1|order\s*#?1|search\s*#?1|#1)\b"),
        (1, r"\b(?:second|2nd|option\s*#?2|item\s*#?2|order\s*#?2|search\s*#?2|#2)\b"),
        (2, r"\b(?:third|3rd|option\s*#?3|item\s*#?3|order\s*#?3|search\s*#?3|#3)\b"),
        (3, r"\b(?:fourth|4th|option\s*#?4|item\s*#?4|order\s*#?4|search\s*#?4|#4)\b"),
        (4, r"\b(?:fifth|5th|option\s*#?5|item\s*#?5|order\s*#?5|search\s*#?5|#5)\b"),
        (-1, r"\b(?:last|latest|most recent|previous)\b"),
    ]
    for idx, pat in ordinal_patterns:
        if re.search(pat, t):
            return idx
    num_match = re.search(r"(?:item|order|search|option|saved\s+item|saved\s+search)\s+(\d+)\b", t)
    if num_match:
        val = int(num_match.group(1))
        if 1 <= val <= 20:
            return val - 1
    return None


def parse_quantity_number(text: str) -> Optional[int]:
    """Extract numeric quantity from digits or spoken English number words."""
    t = (text or "").lower()
    digit_match = re.search(
        r"\b(?:to\s+quantity|quantity\s+(?:to|of)?|qty(?:\s+to)?|to|make\s+it|want)\s+(\d+)\b|\b(\d+)\s+(?:units?|pieces?|items?|of\b)",
        t,
    )
    if digit_match:
        raw_num = digit_match.group(1) or digit_match.group(2)
        if raw_num:
            return max(1, min(99, int(raw_num)))
    word_map = {
        "one": 1, "two": 2, "to": 2, "too": 2, "three": 3, "four": 4, "for": 4,
        "five": 5, "six": 6, "seven": 7, "eight": 8, "nine": 9, "ten": 10,
    }
    word_match = re.search(
        r"\b(?:quantity\s+(?:to|of)?|qty(?:\s+to)?|to\s+quantity|make\s+it)\s+(one|two|to|too|three|four|for|five|six|seven|eight|nine|ten)\b",
        t,
    )
    if word_match:
        return word_map.get(word_match.group(1))
    return None


def classify_user_action(
    user_text: str,
    session: ShoppingSession,
    context: Optional[Dict[str, Any]] = None,
) -> StructuredActionOutput:
    """
    Generic, product-agnostic, context-aware global voice/text intent classifier.
    Resolves navigation, view-scoped entities (Shop / Saved / Orders / Cart / Review / PayPal / Result),
    and active ShoppingSession follow-ups BEFORE permitting a new Channel3 search.
    """
    text = user_text.strip()
    t = text.lower()
    clean_cmd = re.sub(r"[^\w\s]", "", t).strip()
    view = str((context or {}).get("current_view") or "SHOP").upper()

    # 1. Explicit exact-dollar confirmation vs view-specific checkout progression & ambiguity guard
    is_explicit_dollar_confirm = "confirm" in t and ("$" in t or any(ch.isdigit() for ch in t))
    if is_explicit_dollar_confirm:
        return StructuredActionOutput(action=ConversationalAction.CONFIRMATION_ATTEMPT)

    if view == "PURCHASE_REVIEW":
        if re.search(r"\b(?:read\s+(?:my\s+)?(?:order|review|summary)|what\s+am\s+i\s+buying)\b", t):
            return StructuredActionOutput(action=ConversationalAction.READ_REVIEW)
        if "total" in t:
            return StructuredActionOutput(action=ConversationalAction.CHECK_TOTAL)
        if clean_cmd in ("continue", "proceed", "next", "confirm purchase", "confirm order"):
            return StructuredActionOutput(action=ConversationalAction.PROCEED_TO_CONFIRMATION)

    if view == "PAYPAL_CHECKOUT":
        if re.search(r"\b(?:continue\s+to\s+paypal|open\s+paypal|paypal|approve|pay\s+now|complete\s+payment|continue|proceed)\b", t):
            return StructuredActionOutput(action=ConversationalAction.PAYPAL_APPROVAL_NAVIGATION)
        if "total" in t:
            return StructuredActionOutput(action=ConversationalAction.CHECK_TOTAL)

    if view == "PAYMENT_SUCCESS":
        if re.search(r"\b(?:read\s+(?:my\s+)?receipt|show\s+(?:my\s+)?receipt|receipt\s+details)\b", t):
            return StructuredActionOutput(action=ConversationalAction.READ_RECEIPT)
        if re.search(r"\b(?:order\s+id|what\s+(?:was|is)\s+(?:the\s+)?order\s+id|order\s+number)\b", t):
            return StructuredActionOutput(action=ConversationalAction.READ_ORDER_ID)

    if view == "PAYMENT_FAILURE":
        if re.search(r"\b(?:try\s+again|retry(?:\s+payment)?)\b", t):
            return StructuredActionOutput(action=ConversationalAction.RETRY_PAYMENT)

    # Ambiguous checkout / confirmation triggers (must NEVER authorize payment; on CONFIRMATION_REQUIRED "continue" is also guarded)
    ambiguous_regex = re.compile(
        r"\b(?:that\s+one\s+looks\s+good|that\s+looks\s+good|looks\s+good|i\s+like\s+that|i\s+want\s+that|"
        r"get\s+that|choose\s+that|take\s+that|yes|yeah|yep|sure|ok|okay|thats\s+fine|that's\s+fine|"
        r"get\s+it|buy\s+it|go\s+ahead|do\s+it|order\s+it|authorize\s+now|confirm\s+purchase)\b",
        re.IGNORECASE,
    )
    standalone_checkout_ambiguous = clean_cmd in ("buy", "order") or (
        view == "CONFIRMATION_REQUIRED" and clean_cmd in ("continue", "proceed")
    )
    if ambiguous_regex.search(t) or standalone_checkout_ambiguous:
        return StructuredActionOutput(action=ConversationalAction.CONFIRMATION_ATTEMPT)

    # 2. Cancel & Global App Navigation (NEVER triggers Channel3 search)
    if re.search(r"\b(?:cancel|stop|abort|start over)\b", t):
        return StructuredActionOutput(action=ConversationalAction.CANCEL)

    if re.search(r"\b(?:go\s+back\s+to\s+shop|back\s+to\s+shop|back\s+to\s+shopping|go\s+to\s+shop|open\s+shop|show\s+shop|go\s+home)\b", t):
        return StructuredActionOutput(action=ConversationalAction.OPEN_SHOP)

    if clean_cmd in ("go back", "back", "previous step", "return"):
        return StructuredActionOutput(action=ConversationalAction.GO_BACK)

    if any(w in t for w in ("repeat that", "repeat", "say again", "what did you say")):
        return StructuredActionOutput(action=ConversationalAction.HELP)

    if clean_cmd in ("hi", "hello", "hey", "thanks", "thank you", "help", "what can you do", "how does this work"):
        return StructuredActionOutput(action=ConversationalAction.HELP)

    # 3. Order History, Previous Order, Order Detail Queries & Reorder (never trigger Channel3 product search)
    if re.search(r"\b(?:reorder|buy\s+this\s+again|buy\s+it\s+again|order\s+this\s+again)\b", t):
        return StructuredActionOutput(action=ConversationalAction.REORDER)

    if re.search(
        r"\b(?:go\s+to|open|show|view)\s+(?:my\s+)?(?:previous|last|latest|recent)\s+order\b"
        r"|^previous\s+order$",
        t,
    ):
        return StructuredActionOutput(action=ConversationalAction.OPEN_PREVIOUS_ORDER)

    if re.search(
        r"\b(?:what\s+did\s+i\s+buy|show\s+(?:the\s+)?items|what\s+was\s+(?:my\s+)?(?:previous|last|latest|recent)\s+order|"
        r"how\s+much\s+was\s+(?:my\s+)?(?:previous|last|latest|recent)\s+order|"
        r"how\s+much\s+was\s+shipping|how\s+much\s+tax|what\s+was\s+the\s+total|tell\s+me\s+about\s+(?:my\s+)?(?:last|previous|recent|this)\s+order)\b",
        t,
    ) or (
        view in ("ORDERS", "ORDER_DETAILS")
        and re.search(r"\b(?:total|shipping|tax|items|what\s+did\s+i\s+buy|tell\s+me\s+about)\b", t)
    ):
        return StructuredActionOutput(action=ConversationalAction.ORDER_DETAIL_QUERY)

    if view in ("ORDERS", "ORDER_DETAILS") and re.search(r"\b(?:open|show|view|select|expand|details?\s+(?:for|of))\b", t) and parse_ordinal_index(t) is not None:
        return StructuredActionOutput(action=ConversationalAction.OPEN_ORDER)

    if re.search(
        r"\b(?:show\s+(?:my\s+)?orders|open\s+(?:my\s+)?orders|go\s+to\s+(?:my\s+)?orders|view\s+(?:my\s+)?orders|"
        r"order\s+history|open\s+order\s+history|my\s+orders)\b",
        t,
    ):
        return StructuredActionOutput(action=ConversationalAction.VIEW_ORDERS)

    if re.search(r"\b(?:open|show|view)\s+(?:the\s+)?(?:\w+\s+)?order\b", t):
        return StructuredActionOutput(action=ConversationalAction.OPEN_ORDER)

    # 4. Saved Searches & Saved Items (context-aware & global)
    if re.search(r"\b(?:save\s+this\s+search|save\s+search(?:\s+for\s+later)?)\b", t):
        return StructuredActionOutput(action=ConversationalAction.SAVE_SEARCH)

    if re.search(r"\b(?:show\s+(?:my\s+)?saved\s+searches|open\s+(?:my\s+)?saved\s+searches|go\s+to\s+(?:my\s+)?saved\s+searches|view\s+saved\s+searches|my\s+saved\s+searches)\b", t):
        return StructuredActionOutput(action=ConversationalAction.VIEW_SAVED_SEARCHES)

    if re.search(r"\b(?:open|re-?open|run|re-?run)\s+(?:(?:my|the)\s+)?(?:saved\b.*\bsearch|(?:\w+\s+)?saved\s+search|that\s+search(?:\s+again)?)\b", t) or (
        view == "SAVED_SEARCHES" and re.search(r"\b(?:open|run|re-?run)\b", t) and parse_ordinal_index(t) is not None
    ):
        return StructuredActionOutput(action=ConversationalAction.OPEN_SAVED_SEARCH)

    if re.search(r"\b(?:remove|delete)\b.*\bsaved\b|\bunsave\b", t) or (
        view == "SAVED_ITEMS" and re.search(r"\b(?:remove|delete)\b", t)
    ):
        return StructuredActionOutput(action=ConversationalAction.REMOVE_SAVED_ITEM)

    if view == "SAVED_ITEMS" and re.search(r"\b(?:add\b.*\bcart|put\b.*\bcart)\b", t):
        return StructuredActionOutput(action=ConversationalAction.ADD_SAVED_ITEM_TO_CART)

    if re.search(r"\badd\b.*\bsaved\s+item\b.*\bcart\b", t):
        return StructuredActionOutput(action=ConversationalAction.ADD_SAVED_ITEM_TO_CART)

    if view == "SAVED_ITEMS" and re.search(r"\b(?:open|view|show|details?|tell\s+me\s+about)\b", t) and parse_ordinal_index(t) is not None:
        return StructuredActionOutput(action=ConversationalAction.OPEN_SAVED_ITEM)

    if re.search(r"\bopen\b.*\bsaved\s+item\b", t):
        return StructuredActionOutput(action=ConversationalAction.OPEN_SAVED_ITEM)

    if re.search(r"\b(?:open|show|view|go\s+to)\s+(?:my\s+)?saved(?:\s+items)?\b|\b(?:what\s+did\s+i\s+save|my\s+saved\s+items)\b", t):
        return StructuredActionOutput(action=ConversationalAction.VIEW_SAVED_ITEMS)

    if re.search(r"\bsave\s+(?:this|that|it|them|these|option|number|the\b)|\bbookmark\s+(?:this|it)\b", t) and "search" not in t:
        return StructuredActionOutput(action=ConversationalAction.SAVE_ITEM)

    # 5. Cart & Checkout operations
    if re.search(r"\b(?:go\s+to\s+(?:my\s+)?cart|open\s+(?:my\s+)?cart|view\s+cart|show\s+(?:my\s+)?cart|what\s+is\s+in\s+(?:my\s+)?cart|what's\s+in\s+(?:my\s+)?cart|my\s+cart)\b", t):
        return StructuredActionOutput(action=ConversationalAction.OPEN_CART)

    if re.search(r"\b(?:clear|empty)\s+(?:my\s+)?cart\b", t):
        return StructuredActionOutput(action=ConversationalAction.CLEAR_CART)

    if re.search(r"\b(?:remove|delete)\b.*\b(?:cart|item|it)\b", t) or t.startswith("remove from cart") or (
        view == "CART" and re.search(r"\b(?:remove|delete)\b", t)
    ):
        return StructuredActionOutput(action=ConversationalAction.REMOVE_FROM_CART)

    parsed_qty = parse_quantity_number(t)
    if parsed_qty is not None and (
        "quantity" in t or "qty" in t or "cart" in t or view == "CART" or session.selected_product
    ):
        return StructuredActionOutput(
            action=ConversationalAction.CHANGE_QUANTITY,
            constraint_updates={"quantity": parsed_qty},
        )

    if re.search(r"\b(?:add\b.*\bcart|put\b.*\bcart)\b", t):
        return StructuredActionOutput(action=ConversationalAction.ADD_TO_CART)

    if "total" in t:
        return StructuredActionOutput(action=ConversationalAction.CHECK_TOTAL)

    if any(w in t for w in ("checkout", "check out", "review purchase", "purchase review", "continue to checkout", "continue to payment", "proceed")):
        return StructuredActionOutput(action=ConversationalAction.PREPARE_CHECKOUT)

    # 4. If awaiting clarification on a prior conversational turn and no new search was requested
    if session.pending_clarification and not EXPLICIT_SEARCH_STARTERS.match(text):
        has_ref = bool(re.search(r"\b(?:first|second|third|fourth|last|1st|2nd|3rd|option|number|#?\d+|cheapest|expensive|both|1|2|3)\b", t))
        if has_ref:
            pending_act = ConversationalAction(session.pending_clarification["action"])
            return StructuredActionOutput(action=pending_act, references=[text])

    # 5. Compare intent
    if re.search(r"\b(?:compare|comparison|versus|vs|side by side|difference between|which is better|which one is better|recommend)\b", t):
        return StructuredActionOutput(action=ConversationalAction.COMPARE)

    # 6. Explicit selection intent ("choose the second one", "select option 1", "pick the cheaper one")
    if re.search(r"\b(?:choose|select|pick|go with|i'll take|i want option)\b", t) and not EXPLICIT_SEARCH_STARTERS.match(text):
        return StructuredActionOutput(action=ConversationalAction.SELECT)

    # 6b. Check if user is asking to refine/filter active results ("What about only black ones?", "Only black ones", "Under $50 instead")
    # before ordinal/detail matching when a filter constraint is clearly present.
    active_intent_for_followup = session.structured_search_intent
    if not active_intent_for_followup and session.displayed_products:
        fallback_q = session.display_query or session.original_query or session.product_type or ""
        if fallback_q:
            active_intent_for_followup = extract_search_intent_rules(fallback_q, last_intent=None)

    # 7. Product details / attribute inquiry intent
    if (
        re.search(r"\b(?:tell me about|tell me more|more about|details|specs|specifications|describe|information about|how much is|what is the price of)\b", t)
        or (
            re.search(r"\b(?:what about|how about)\b", t)
            and not (active_intent_for_followup and is_followup_refinement_command(text, active_intent_for_followup))
        )
        or re.search(
            r"\b(?:which one is|which is|which has|which one has|is it |is the |does it have|does the |do they have|"
            r"what is the weight|how heavy|lightest|waterproof|battery|warranty|material|cheapest|better reviews|highest rated)\b",
            t,
        )
    ) and not EXPLICIT_SEARCH_STARTERS.match(text):
        return StructuredActionOutput(action=ConversationalAction.PRODUCT_DETAILS)

    # 8. Sorting within active session
    if re.search(r"\b(?:sort by|order by|cheapest first|lowest price first|highest price first|most expensive first|best rated|highest rated)\b", t):
        sort_pref = "price_asc"
        if any(w in t for w in ("highest price", "most expensive", "price desc", "priciest")):
            sort_pref = "price_desc"
        elif any(w in t for w in ("rating", "best rated", "highest rated", "stars")):
            sort_pref = "rating_desc"
        return StructuredActionOutput(
            action=ConversationalAction.SORT_RESULTS,
            sort_preference=sort_pref,
            constraint_updates={"sort_preference": sort_pref},
        )

    # 9. Show more / Pagination through candidates (within same active search)
    if re.search(r"\b(?:show\s+more|more\s+options|next\s+results|see\s+more|load\s+more|more\s+results)\b", t):
        return StructuredActionOutput(action=ConversationalAction.SHOW_MORE)
    if re.search(r"\b(?:next option|next options)\b", t):
        return StructuredActionOutput(action=ConversationalAction.NEXT_OPTION)
    if re.search(r"\b(?:previous option|previous options|earlier options)\b", t):
        return StructuredActionOutput(action=ConversationalAction.PREVIOUS_OPTION)

    # 10. Cheaper alternative (single option suggestion vs filtered list refinement)
    if any(w in t for w in ("cheaper", "less expensive", "lower price", "lower-priced", "save money")):
        if not EXPLICIT_SEARCH_STARTERS.match(text) and (session.structured_search_intent or session.displayed_products):
            # Explicit list filter ("show cheaper ones", "cheaper options") -> FILTER_RESULTS / REFINE_SEARCH
            if any(p in t for p in ("cheaper ones", "cheaper options", "lower priced ones")):
                return StructuredActionOutput(
                    action=ConversationalAction.FILTER_RESULTS,
                    constraint_updates={"sort_preference": "price_asc", "cheaper_list": True},
                    sort_preference="price_asc",
                )
            # Single cheaper alternative against active universe ("show something cheaper", "any cheaper alternative?")
            if not _has_product_search_substance(text) or "something" in t or "alternative" in t or "option" in t or "one" in t or "anything" in t:
                return StructuredActionOutput(action=ConversationalAction.CHEAPER_ALTERNATIVE)

    # 11. Other alternative requests ("another option", "different brand", "something else", "something similar", "different color")
    if any(p in t for p in (
        "another option", "more option", "other option", "something else", "different one",
        "something similar", "similar options", "similar ones", "similar products",
        "another brand", "different brand", "other brand", "different color", "other color",
    )):
        return StructuredActionOutput(action=ConversationalAction.OTHER_ALTERNATIVE)

    # 12. Refinement / Filtering against active session intent
    if active_intent_for_followup and is_followup_refinement_command(text, active_intent_for_followup):
        parsed = extract_search_intent_rules(
            text,
            last_intent=active_intent_for_followup,
            shown_brands=session.shown_brands(),
        )
        updates: Dict[str, Any] = {}
        if parsed.max_price != active_intent_for_followup.max_price:
            updates["max_price"] = parsed.max_price
        if parsed.min_price != active_intent_for_followup.min_price:
            updates["min_price"] = parsed.min_price
        if parsed.color != active_intent_for_followup.color:
            updates["color"] = parsed.color
        if parsed.features != active_intent_for_followup.features:
            updates["features"] = parsed.features
        if parsed.compatibility != active_intent_for_followup.compatibility:
            updates["compatibility"] = parsed.compatibility
        action_kind = (
            ConversationalAction.FILTER_RESULTS
            if (parsed.color or parsed.max_price is not None or parsed.features or parsed.exclude_brands)
            else ConversationalAction.REFINE_SEARCH
        )
        return StructuredActionOutput(
            action=action_kind,
            constraint_updates=updates,
            typed_constraints=parsed.constraints,
            starts_new_search=False,
            search_query=parsed.search_query,
            product_type=parsed.product_type,
            brand=parsed.brand,
            model=parsed.model,
            character_or_franchise=parsed.character_or_franchise,
            max_price=parsed.max_price,
            min_price=parsed.min_price,
            color=parsed.color,
            features=parsed.features,
            compatibility=parsed.compatibility,
            recipient_or_use_case=parsed.recipient_or_use_case,
            sort_preference=parsed.sort_preference,
        )

    # 13. Follow-up attribute / constraint questions on active displayed products (avoid spurious Channel3 searches)
    if (
        session.displayed_products
        and not EXPLICIT_SEARCH_STARTERS.match(text)
        and (
            re.search(r"\b(?:only\s+(?:in\s+stock|wireless|bluetooth|black|white|blue|red|pink|green|silver|gray|grey)|in\s+stock\s+only)\b", t)
            or (
                (text.endswith("?") or re.match(r"^(?:does|do|is|are|what|which|how|any)\b", t))
                and re.search(r"\b(?:warranty|battery|weight|heavy|material|color|colors|bluetooth|wireless|waterproof|size|compatible|compatibility|features?|stock|available|rating|reviews?)\b", t)
            )
        )
    ):
        if re.search(r"\b(?:only|under|below|max)\b", t):
            parsed = extract_search_intent_rules(text, last_intent=session.structured_search_intent, shown_brands=session.shown_brands())
            return StructuredActionOutput(
                action=ConversationalAction.FILTER_RESULTS,
                starts_new_search=False,
                search_query=parsed.search_query,
                product_type=parsed.product_type,
                brand=parsed.brand,
                model=parsed.model,
                character_or_franchise=parsed.character_or_franchise,
                max_price=parsed.max_price,
                min_price=parsed.min_price,
                color=parsed.color,
                features=parsed.features,
                compatibility=parsed.compatibility,
                recipient_or_use_case=parsed.recipient_or_use_case,
                sort_preference=parsed.sort_preference,
            )
        return StructuredActionOutput(action=ConversationalAction.PRODUCT_DETAILS)

    # 14. Unclear conversational fragment without product substance -> NEVER default to Channel3 search!
    if not EXPLICIT_SEARCH_STARTERS.match(text) and not _has_product_search_substance(text):
        opts_hint = f"1 to {len(session.displayed_products)}" if session.displayed_products else "1, 2, or 3"
        return StructuredActionOutput(
            action=ConversationalAction.UNKNOWN,
            needs_clarification=True,
            clarification_question=(
                f"I'm not sure whether you want to search for a new product or ask about the current options. "
                f"Please tell me what product to find, or say an option number ({opts_hint})."
            ),
        )

    # 14. New product search request -> starts a fresh search generation
    parsed_new = extract_search_intent_rules(text, last_intent=None)
    return StructuredActionOutput(
        action=ConversationalAction.NEW_SEARCH,
        typed_constraints=parsed_new.constraints,
        starts_new_search=True,
        search_query=parsed_new.search_query,
        product_type=parsed_new.product_type,
        brand=parsed_new.brand,
        model=parsed_new.model,
        character_or_franchise=parsed_new.character_or_franchise,
        max_price=parsed_new.max_price,
        min_price=parsed_new.min_price,
        color=parsed_new.color,
        size=parsed_new.size,
        features=parsed_new.features,
        compatibility=parsed_new.compatibility,
        recipient_or_use_case=parsed_new.recipient_or_use_case,
        sort_preference=parsed_new.sort_preference,
    )
