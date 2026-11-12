import re
import logging
import httpx
from typing import List, Optional, Dict, Any
from app.config import settings
from app.db.database import db
from app.models.product import Product
from app.services.search_engine import (
    StructuredSearchIntent,
    build_broadened_queries,
    extract_category_info,
    extract_search_intent_rules,
    score_and_filter_candidates,
)

logger = logging.getLogger("accesspay.products")


class Channel3APIError(Exception):
    """Raised when the Channel3 API request fails or credentials are missing/invalid."""
    pass


class Channel3ProductService:
    """
    Real Product Search Service backed by the official Channel3 API:
    - Endpoint: POST https://api.trychannel3.com/v1/search
    - Auth Header: x-api-key: <CHANNEL3_API_KEY>
    - Normalizes real Channel3 canonical products & merchant offers into internal Product model.
    - Never invents products, prices, or missing attributes.
    - Caches retrieved session candidates to avoid unnecessary repeated API calls.
    """
    def __init__(self, api_key: Optional[str] = None, base_url: Optional[str] = None):
        self.api_key = api_key if api_key is not None else settings.CHANNEL3_API_KEY
        self.base_url = (base_url or settings.CHANNEL3_BASE_URL or "https://api.trychannel3.com/v1").rstrip("/")
        self.session_candidates: List[Product] = []
        self.session_raw_candidates: List[Product] = []
        self.above_budget_candidates: List[Product] = []
        self.cached_by_id: Dict[str, Product] = {}
        self.last_search_signature: Optional[str] = None
        self.last_search_debug: Dict[str, Any] = {}
        self.api_call_count: int = 0

    def is_configured(self) -> bool:
        key = self.api_key or settings.CHANNEL3_API_KEY
        return bool(key and key.strip())

    def reset_cache(self):
        self.session_candidates = []
        self.session_raw_candidates = []
        self.above_budget_candidates = []
        self.cached_by_id = {}
        self.last_search_signature = None
        self.last_search_debug = {}

    def get_cached_product(self, product_id: str) -> Optional[Product]:
        return self.cached_by_id.get(product_id)

    def normalize_product(self, raw: Dict[str, Any]) -> Optional[Product]:
        """
        Convert a raw Channel3 product item into the internal Product model.
        Only includes fields actually returned by Channel3. Never invents missing information.
        """
        if not isinstance(raw, dict):
            return None

        raw_id = str(raw.get("id") or "").strip()
        title = str(raw.get("title") or raw.get("name") or "").strip()
        if not raw_id or not title:
            return None

        product_id = raw_id if raw_id.startswith("c3_") else f"c3_{raw_id}"

        # Extract primary merchant offer (prefer first InStock dict offer so title/price/merchant/url stay consistent)
        offers = raw.get("offers") if isinstance(raw.get("offers"), list) else []
        dict_offers = [o for o in offers if isinstance(o, dict)]
        instock_offers = [
            o for o in dict_offers
            if str(o.get("availability") or "InStock").lower() not in ("outofstock", "out_of_stock", "unavailable")
        ]
        primary_offer: Dict[str, Any] = (
            instock_offers[0] if instock_offers else (dict_offers[0] if dict_offers else {})
        )

        # Extract price strictly as numeric float from offer or root (supports both 'amount' and 'price')
        def _extract_numeric_price(obj: Any) -> Optional[float]:
            if isinstance(obj, dict):
                for key_name in ("price", "amount", "value"):
                    if obj.get(key_name) is not None:
                        try:
                            return float(obj[key_name])
                        except (ValueError, TypeError):
                            continue
                return None
            if obj is not None:
                try:
                    return float(obj)
                except (ValueError, TypeError):
                    return None
            return None

        price_val: Optional[float] = _extract_numeric_price(primary_offer.get("price"))
        if price_val is None and raw.get("price") is not None:
            price_val = _extract_numeric_price(raw.get("price"))

        if price_val is None or price_val < 0:
            return None

        # Extract merchant / retailer name
        merchant = ""
        offer_merchant = primary_offer.get("merchant")
        if isinstance(offer_merchant, dict):
            merchant = str(offer_merchant.get("name") or offer_merchant.get("domain") or "").strip()
        elif isinstance(offer_merchant, str):
            merchant = offer_merchant.strip()

        if not merchant:
            merchant = str(
                primary_offer.get("domain")
                or primary_offer.get("merchant_domain")
                or raw.get("merchant_name")
                or raw.get("merchant")
                or raw.get("website_id")
                or ""
            ).strip()

        brands = raw.get("brands") if isinstance(raw.get("brands"), list) else []
        brand_names = [
            str(b.get("name")).strip()
            for b in brands
            if isinstance(b, dict) and b.get("name")
        ]
        brand_name = brand_names[0] if brand_names else ""
        if not brand_name and isinstance(raw.get("brand"), str):
            brand_name = raw["brand"].strip()
            if brand_name:
                brand_names = [brand_name]

        if not merchant:
            merchant = brand_name or "Verified Retailer"

        # Extract image & alt text
        image_url = ""
        image_alt = None
        images = raw.get("images") if isinstance(raw.get("images"), list) else []
        if images and isinstance(images[0], dict):
            # Prefer main image if flagged
            main_imgs = [img for img in images if isinstance(img, dict) and img.get("is_main_image")]
            chosen_img = main_imgs[0] if main_imgs else images[0]
            image_url = str(chosen_img.get("cleaned_url") or chosen_img.get("url") or "").strip()
            if chosen_img.get("alt_text"):
                image_alt = str(chosen_img["alt_text"]).strip()
        elif isinstance(raw.get("image_url"), str):
            image_url = raw["image_url"].strip()
        elif isinstance(raw.get("image"), str):
            image_url = raw["image"].strip()

        if not image_alt:
            image_alt = f"{title} from {merchant}"

        # Extract original product URL
        product_url = str(primary_offer.get("url") or raw.get("url") or raw.get("product_url") or "").strip() or None

        # Availability
        availability_str = str(
            primary_offer.get("availability")
            or raw.get("availability")
            or ("InStock" if raw.get("in_stock", True) else "OutOfStock")
        ).strip()
        is_available = availability_str.lower() not in ["outofstock", "out_of_stock", "unavailable", "false"]

        # Description (only what Channel3 actually provides)
        description = str(raw.get("description") or "").strip()

        # Attributes & factual features (strictly from returned data)
        attributes: Dict[str, Any] = {}
        if isinstance(raw.get("attributes"), dict):
            attributes.update(raw["attributes"])
        elif isinstance(raw.get("attributes"), list):
            for attr in raw["attributes"]:
                if isinstance(attr, dict) and attr.get("name") and attr.get("value") is not None:
                    attributes[str(attr["name"])] = attr["value"]
        if isinstance(raw.get("structured_attributes"), dict):
            for k, v in raw["structured_attributes"].items():
                if v is not None:
                    attributes.setdefault(str(k), v)
        dims = primary_offer.get("dimensions") if isinstance(primary_offer.get("dimensions"), dict) else {}
        weight_info = dims.get("weight") if isinstance(dims.get("weight"), dict) else {}
        if weight_info.get("number") is not None:
            attributes.setdefault("weight", f"{weight_info['number']} {weight_info.get('unit', '')}".strip())

        if brand_name:
            attributes.setdefault("brand", brand_name)
        if brand_names:
            attributes["brands"] = brand_names
        if isinstance(raw.get("colors"), list) and raw["colors"]:
            attributes["color_swatches"] = raw["colors"]
        if isinstance(raw.get("materials"), list) and raw["materials"]:
            attributes["materials"] = ", ".join(str(m) for m in raw["materials"] if m)
        if primary_offer.get("condition"):
            attributes.setdefault("condition", primary_offer["condition"])

        features: List[str] = []
        raw_features = raw.get("features") or raw.get("key_features") or raw.get("highlights") or raw.get("accessibility_features")
        if isinstance(raw_features, list):
            for f in raw_features:
                if isinstance(f, str) and f.strip():
                    features.append(f.strip())

        for k, v in attributes.items():
            if len(features) >= 3:
                break
            if v is not None and str(v).strip():
                label = str(k).replace("_", " ").capitalize()
                val_str = str(v).strip()
                feat_entry = f"{label}: {val_str}"
                if feat_entry not in features:
                    features.append(feat_entry)

        if len(features) < 3 and description:
            # Extract short factual sentences from actual description without inventing
            sentences = [s.strip() for s in re.split(r"[.;•\n]+", description) if 8 <= len(s.strip()) <= 110]
            for s in sentences:
                if len(features) >= 3:
                    break
                if s not in features:
                    features.append(s)

        shipping_cost = 0.0
        if primary_offer.get("shipping_cost") is not None:
            try:
                shipping_cost = float(primary_offer["shipping_cost"])
            except (ValueError, TypeError):
                shipping_cost = 0.0
        elif raw.get("shipping_cost") is not None:
            try:
                shipping_cost = float(raw["shipping_cost"])
            except (ValueError, TypeError):
                shipping_cost = 0.0

        estimated_tax = round(price_val * 0.08, 2)
        category, category_path = extract_category_info(raw.get("category"))
        if category_path:
            attributes["category_path"] = category_path

        rating_val = None
        review_count_val = None
        ratings_obj = raw.get("ratings") if isinstance(raw.get("ratings"), dict) else {}
        raw_rating = raw.get("rating") if raw.get("rating") is not None else (ratings_obj.get("average") or ratings_obj.get("rating"))
        raw_reviews = raw.get("review_count") if raw.get("review_count") is not None else (ratings_obj.get("count") or ratings_obj.get("review_count"))
        if raw_rating is not None:
            try:
                rating_val = float(raw_rating)
            except (ValueError, TypeError):
                rating_val = None

        if raw_reviews is not None:
            try:
                review_count_val = int(raw_reviews)
            except (ValueError, TypeError):
                review_count_val = None

        return Product(
            id=product_id,
            title=title,
            name=title,
            description=description,
            price=round(price_val, 2),
            shipping=round(shipping_cost, 2),
            estimated_tax=estimated_tax,
            category=category,
            merchant=merchant,
            image_url=image_url,
            image_alt=image_alt,
            product_url=product_url,
            rating=rating_val,
            review_count=review_count_val,
            is_available=is_available,
            availability=availability_str,
            attributes=attributes,
            source="channel3",
            documented_accessibility_features=features[:3],
            ai_inferred_accessibility=[],
        )

    async def _fetch_raw_channel3(
        self,
        client: httpx.AsyncClient,
        key: str,
        search_str: str,
        limit: int,
        budget_limit: Optional[float],
        min_price: Optional[float],
    ) -> List[Product]:
        payload: Dict[str, Any] = {
            "query": search_str,
            "limit": limit,
        }
        filters: Dict[str, Any] = {
            "availability": ["InStock"]
        }
        if budget_limit is not None or min_price is not None:
            price_filter: Dict[str, float] = {}
            if min_price is not None:
                price_filter["min_price"] = float(min_price)
            if budget_limit is not None:
                price_filter["max_price"] = float(budget_limit)
            filters["price"] = price_filter

        payload["filters"] = filters
        headers = {
            "x-api-key": key,
            "Content-Type": "application/json",
        }
        url = f"{self.base_url}/search"

        try:
            self.api_call_count += 1
            response = await client.post(url, json=payload, headers=headers)
        except Exception as exc:
            logger.error("Channel3 API connection failure: %s", exc)
            raise Channel3APIError("Product search is temporarily unavailable.") from exc

        if response.status_code != 200:
            if response.status_code in (401, 403):
                logger.error(
                    "Channel3 authentication failed (HTTP %s). Verify CHANNEL3_API_KEY in backend/.env.",
                    response.status_code,
                )
            else:
                logger.error("Channel3 API returned HTTP %s: %s", response.status_code, response.text[:200])
            raise Channel3APIError("Product search is temporarily unavailable.")

        try:
            data = response.json()
        except Exception as exc:
            raise Channel3APIError("Product search is temporarily unavailable.") from exc

        raw_list = data.get("products") if isinstance(data, dict) else (data if isinstance(data, list) else [])
        if not isinstance(raw_list, list):
            return []

        normalized: List[Product] = []
        for item in raw_list:
            prod = self.normalize_product(item)
            if prod is not None:
                normalized.append(prod)
        return normalized

    async def search(
        self,
        query: str,
        budget_limit: Optional[float] = None,
        min_price: Optional[float] = None,
        requirements: Optional[List[str]] = None,
        limit: int = 18,
        force_refresh: bool = False,
        intent: Optional[StructuredSearchIntent] = None,
    ) -> List[Product]:
        """
        Generic Channel3 search pipeline:
        1. Build/use StructuredSearchIntent preserving brand/model/color/compatibility.
        2. Query Channel3 POST /v1/search with budget & availability filters.
        3. Normalize, score by relevance, and filter irrelevant products/accessories.
        4. Apply controlled progressive broadening only if < 2 strong matches exist.
        5. Detect when relevant matches exist only above budget.
        6. Log full trace in development logs (never shown in UI).
        """
        key = (self.api_key or settings.CHANNEL3_API_KEY or "").strip()
        if not key:
            logger.error("Channel3 API key missing. Set CHANNEL3_API_KEY in backend/.env.")
            raise Channel3APIError("Channel3 API key is not configured.")

        active_intent = intent or extract_search_intent_rules(query)
        if budget_limit is not None:
            active_intent.max_price = budget_limit
        if min_price is not None:
            active_intent.min_price = min_price
        for r_term in (requirements or []):
            r_clean = r_term.strip()
            if r_clean and r_clean.lower() not in [f.lower() for f in active_intent.features]:
                active_intent.features.append(r_clean)
            if r_clean and r_clean.lower() not in active_intent.search_query.lower():
                active_intent.search_query = f"{active_intent.search_query} {r_clean}".strip()

        active_intent.broaden_queries = build_broadened_queries(active_intent)
        query_sequence = active_intent.broaden_queries or [active_intent.search_query]
        effective_query = query_sequence[0]

        signature = "|".join([
            effective_query.lower(),
            f"max:{active_intent.max_price}",
            f"min:{active_intent.min_price}",
            f"color:{active_intent.color or ''}",
            f"excl:{','.join(sorted(active_intent.exclude_brands))}",
            f"sort:{active_intent.sort_preference}",
        ])
        if not force_refresh and self.last_search_signature == signature and self.session_candidates:
            return self.session_candidates

        self.above_budget_candidates = []
        raw_by_id: Dict[str, Product] = {}
        queries_attempted: List[str] = []
        raw_titles_seen: List[str] = []

        async with httpx.AsyncClient(timeout=8.0) as client:
            for q_idx, q_candidate in enumerate(query_sequence[:4]):
                queries_attempted.append(q_candidate)
                batch = await self._fetch_raw_channel3(
                    client=client,
                    key=key,
                    search_str=q_candidate,
                    limit=limit,
                    budget_limit=active_intent.max_price,
                    min_price=active_intent.min_price,
                )
                for p in batch:
                    if p.id not in raw_by_id:
                        raw_by_id[p.id] = p
                        raw_titles_seen.append(f"{p.title} (${p.price:.2f})")

                ranked, removed_log, score_log = score_and_filter_candidates(
                    list(raw_by_id.values()),
                    active_intent,
                    enforce_budget=True,
                )
                # Stop early once we have >= 2 strong matches (prevents redundant API calls)
                if len(ranked) >= 2:
                    break
                # Stop if first query already returned plenty of raw hits and still 0 relevant under budget
                if q_idx == 0 and len(batch) == 0 and len(query_sequence) == 1:
                    break

            # If budget was set and 0 relevant products matched within budget,
            # check without max_price so user is offered matching options above budget.
            if not ranked and active_intent.max_price is not None:
                queries_attempted.append(f"{effective_query} [no-budget-check]")
                unbounded_batch = await self._fetch_raw_channel3(
                    client=client,
                    key=key,
                    search_str=effective_query,
                    limit=12,
                    budget_limit=None,
                    min_price=active_intent.min_price,
                )
                for p in unbounded_batch:
                    if p.id not in raw_by_id:
                        raw_by_id[p.id] = p
                above_ranked, _, _ = score_and_filter_candidates(
                    unbounded_batch,
                    active_intent,
                    enforce_budget=False,
                )
                self.above_budget_candidates = [
                    p for p in above_ranked if p.price > active_intent.max_price
                ]
                for p in self.above_budget_candidates:
                    self.cached_by_id[p.id] = p
                    db.save_product(p.model_dump())

        self.session_raw_candidates = list(raw_by_id.values())
        self.session_candidates = ranked
        self.last_search_signature = signature
        self.last_search_debug = {
            "original_query": active_intent.raw_query,
            "structured_intent": active_intent.model_dump(),
            "channel3_queries": queries_attempted,
            "raw_result_count": len(raw_by_id),
            "top_raw_titles": raw_titles_seen[:8],
            "relevance_scores": score_log[:8],
            "removed_products": removed_log[:8],
            "final_displayed": [(p.title, p.price, p.merchant) for p in ranked[:3]],
            "above_budget_count": len(self.above_budget_candidates),
        }

        logger.info(
            "[SearchDebug] raw=%r intent=%s c3_queries=%s raw_count=%d top_raw=%s scores=%s removed=%s final=%s",
            active_intent.raw_query,
            {
                "search_query": active_intent.search_query,
                "product_type": active_intent.product_type,
                "color": active_intent.color,
                "features": active_intent.features,
                "compatibility": active_intent.compatibility,
                "max_price": active_intent.max_price,
                "exclude_brands": active_intent.exclude_brands,
            },
            queries_attempted,
            len(raw_by_id),
            raw_titles_seen[:5],
            score_log[:5],
            removed_log[:5],
            [(p.title, p.price) for p in ranked[:3]],
        )

        for p in ranked:
            self.cached_by_id[p.id] = p
            db.save_product(p.model_dump())

        return ranked


class MockProductService:
    """
    Deterministic Demo / Mock Product Service:
    Used when PRODUCT_PROVIDER=mock or when Demo Mode is explicitly enabled.
    """
    def __init__(self):
        self.session_candidates: List[Product] = []

    def get_all_products(self) -> List[Product]:
        raw_items = db.get_all_products()
        products = []
        for item in raw_items:
            # Filter out cached c3_ items when listing pure mock catalog
            if str(item.get("id", "")).startswith("c3_"):
                continue
            p = Product(**item)
            p.source = "mock"
            products.append(p)
        return products

    def get_product_by_id(self, product_id: str) -> Optional[Product]:
        raw = db.get_product(product_id)
        if raw:
            return Product(**raw)
        return None

    async def search(
        self,
        query: str,
        budget_limit: Optional[float] = None,
        min_price: Optional[float] = None,
        requirements: Optional[List[str]] = None
    ) -> List[Product]:
        all_products = self.get_all_products()
        query_lower = query.lower()
        req_list = [r.lower() for r in (requirements or []) if r.strip()]

        results: List[Product] = []
        for p in all_products:
            searchable_blob = " ".join([
                p.title.lower(),
                p.description.lower(),
                p.category.lower(),
                " ".join(f.lower() for f in p.documented_accessibility_features)
            ])

            category_specified = False
            category_matched = False
            if "headphone" in query_lower:
                category_specified = True
                category_matched = "Audio" in p.category or "headphone" in searchable_blob
            elif "keyboard" in query_lower:
                category_specified = True
                category_matched = "Keyboard" in p.category or "keyboard" in searchable_blob
            elif "laptop" in query_lower:
                category_specified = True
                category_matched = "Computer" in p.category or "laptop" in searchable_blob
            elif "mouse" in query_lower or "trackball" in query_lower:
                category_specified = True
                category_matched = "Pointing" in p.category or "mouse" in searchable_blob or "trackball" in searchable_blob
            elif "subscri" in query_lower or "audiobook" in query_lower:
                category_specified = True
                category_matched = bool(p.is_subscription)

            if category_specified:
                matches_query = category_matched
            else:
                matches_query = (
                    query_lower in searchable_blob
                    or any(word in searchable_blob for word in query_lower.split() if len(word) >= 4 and word not in ["find", "show", "want", "need", "with", "under", "only", "ones"])
                )

            if matches_query and req_list:
                # Prefer items matching requirements if specified
                pass

            if matches_query:
                if budget_limit is not None and p.price > budget_limit:
                    continue
                if min_price is not None and p.price < min_price:
                    continue
                results.append(p)

        ranked = rank_and_annotate_candidates(results, query, requirements or [])
        self.session_candidates = ranked
        return ranked


def rank_and_annotate_candidates(
    candidates: List[Product],
    query: str,
    requirements: List[str]
) -> List[Product]:
    """
    Ranks candidate products according to query & requirements using ONLY actual product data.
    Assigns factual badges ('BEST MATCH', 'BEST VALUE', 'LOWEST PRICE') and links cheaper alternatives.
    Never modifies prices or invents product facts.
    """
    if not candidates:
        return []

    query_terms = [
        w.lower() for w in re.findall(r"\w+", query)
        if len(w) >= 3 and w.lower() not in {"find", "show", "under", "for", "the", "and", "with", "need", "want"}
    ]
    req_terms = [r.lower().strip() for r in requirements if r.strip()]

    def score_product(p: Product) -> float:
        blob = " ".join([
            p.title.lower(),
            p.description.lower(),
            " ".join(f.lower() for f in p.documented_accessibility_features),
            " ".join(f"{k} {v}".lower() for k, v in (p.attributes or {}).items())
        ])
        score = 0.0
        for qt in query_terms:
            if qt in p.title.lower():
                score += 3.0
            elif qt in blob:
                score += 1.5
        for rt in req_terms:
            if rt in blob:
                score += 4.0
            else:
                for word in rt.split():
                    if len(word) >= 3 and word in blob:
                        score += 1.5
        if p.is_available:
            score += 1.0
        return score

    # Sort primarily by relevance score descending, preserving provider relevance order on ties
    indexed = list(enumerate(candidates))
    scored = [p for _, p in sorted(indexed, key=lambda item: (-score_product(item[1]), item[0]))]

    # Find lowest price product across all candidates
    cheapest_overall = min(scored, key=lambda p: p.price)

    for idx, prod in enumerate(scored):
        matched_Source_facts = []
        blob_lower = " ".join([prod.title, prod.description] + prod.documented_accessibility_features).lower()
        for rt in req_terms:
            if rt in blob_lower:
                matched_Source_facts.append(f"lists {rt}")

        if idx == 0:
            prod.ranking_badge = "BEST MATCH"
            if matched_Source_facts:
                prod.ranking_reason = f"Best match: {', '.join(matched_Source_facts)} at ${prod.price:.2f} from {prod.merchant}."
            else:
                prod.ranking_reason = f"Best match for your search at ${prod.price:.2f} from {prod.merchant}."
        elif prod.id == cheapest_overall.id:
            prod.ranking_badge = "LOWEST PRICE"
            prod.ranking_reason = f"Lowest price option at ${prod.price:.2f} from {prod.merchant}."
        elif idx == 1:
            prod.ranking_badge = "BEST VALUE"
            prod.ranking_reason = f"Strong value option at ${prod.price:.2f} from {prod.merchant}."
        else:
            prod.ranking_badge = prod.ranking_badge or "OPTION"
            prod.ranking_reason = f"${prod.price:.2f} from {prod.merchant}."

        # Link cheaper alternative if a strictly cheaper candidate exists
        cheaper_candidates = [c for c in scored if c.price < prod.price and c.id != prod.id]
        if cheaper_candidates:
            best_cheaper = min(cheaper_candidates, key=lambda c: c.price)
            prod.cheaper_alternative_id = best_cheaper.id
            prod.savings_amount = round(prod.price - best_cheaper.price, 2)

    return scored


class ProductService:
    """
    Unified Product Service Facade:
    Delegates between Channel3ProductService (REAL PRODUCT MODE) and
    MockProductService (DEMO PRODUCT MODE).
    """
    def __init__(self):
        self.channel3_service = Channel3ProductService()
        self.mock_service = MockProductService()
        self._provider_override: Optional[str] = None
        self._fallback_override: Optional[bool] = None
        self.allow_auto_fallback: bool = True
        self.last_search_candidates: List[Product] = []
        self.last_query_context: Dict[str, Any] = {
            "query": "",
            "product_type": "",
            "budget_limit": None,
            "requirements": []
        }

    def set_provider_mode(self, provider: Optional[str], allow_fallback: Optional[bool] = None):
        """Allows explicit switching between 'channel3', 'mock', or None (use settings)."""
        self._provider_override = provider.lower() if provider else None
        self._fallback_override = allow_fallback
        if allow_fallback is not None:
            self.allow_auto_fallback = allow_fallback
        elif provider is None:
            self.allow_auto_fallback = True

    def get_active_provider_mode(self) -> str:
        """
        Returns 'channel3' or 'mock'.
        - If explicitly overridden or set via PRODUCT_PROVIDER='mock' or 'channel3', honors it.
        - If PRODUCT_PROVIDER='auto', uses 'channel3' if CHANNEL3_API_KEY is present, else 'mock'.
        """
        mode = (self._provider_override or settings.PRODUCT_PROVIDER or "auto").lower()
        if mode == "mock":
            return "mock"
        if mode == "channel3":
            return "channel3"
        # 'auto'
        if self.channel3_service.is_configured():
            return "channel3"
        return "mock"

    def get_mode_status(self) -> Dict[str, Any]:
        active = self.get_active_provider_mode()
        return {
            "product_mode": "REAL PRODUCT MODE" if active == "channel3" else "DEMO PRODUCT MODE",
            "provider": active,
            "channel3_configured": self.channel3_service.is_configured(),
            "demo_mode_enabled": settings.DEMO_MODE or active == "mock",
            "cached_candidate_count": len(self.last_search_candidates),
            "channel3_api_calls": self.channel3_service.api_call_count
        }

    def reset_session(self):
        self.channel3_service.reset_cache()
        self.last_search_candidates = []
        self.last_query_context = {
            "query": "",
            "product_type": "",
            "budget_limit": None,
            "requirements": []
        }

    def get_all_products(self) -> List[Product]:
        if self.last_search_candidates:
            return self.last_search_candidates
        return self.mock_service.get_all_products()

    def get_product_by_id(self, product_id: str) -> Optional[Product]:
        # 1. Check Channel3 session cache first
        cached = self.channel3_service.get_cached_product(product_id)
        if cached:
            return cached
        # 2. Check last search candidates
        for p in self.last_search_candidates:
            if p.id == product_id:
                return p
        # 3. Check database / mock service
        return self.mock_service.get_product_by_id(product_id)

    async def search_products(
        self,
        query: str,
        budget_limit: Optional[float] = None,
        accessibility_need: Optional[str] = None,
        min_price: Optional[float] = None,
        requirements: Optional[List[str]] = None,
        force_refresh: bool = False,
        intent: Optional[StructuredSearchIntent] = None,
        display_limit: int = 6,
    ) -> Dict[str, Any]:
        """
        Searches products using Channel3ProductService (when in channel3 mode)
        or MockProductService (when in mock/demo mode).
        Never silently pretends mock products are real Channel3 results.
        """
        reqs = list(requirements or [])
        if accessibility_need and accessibility_need not in reqs:
            reqs.append(accessibility_need)

        provider = self.get_active_provider_mode()
        fetch_limit = max(24, display_limit * 3)

        self.last_query_context = {
            "query": query,
            "product_type": query,
            "budget_limit": budget_limit,
            "min_price": min_price,
            "requirements": reqs
        }

        if provider == "channel3":
            try:
                candidates = await self.channel3_service.search(
                    query=query,
                    budget_limit=budget_limit,
                    min_price=min_price,
                    requirements=reqs,
                    limit=fetch_limit,
                    force_refresh=force_refresh,
                    intent=intent,
                )
                self.last_search_candidates = candidates
                top_results = candidates[:display_limit]
                above_budget = self.channel3_service.above_budget_candidates[:display_limit]
                return {
                    "source": "Channel3 Real Product Search",
                    "product_mode": "REAL PRODUCT MODE",
                    "channel3_integrated": True,
                    "is_mock_fallback": False,
                    "error": False,
                    "query": query,
                    "count": len(top_results),
                    "total_candidates": len(candidates),
                    "has_more": len(candidates) > len(top_results),
                    "products": top_results,
                    "budget_exceeded": bool(not top_results and above_budget and budget_limit is not None),
                    "above_budget_products": above_budget if not top_results else [],
                }
            except Exception as err:
                logger.warning("Channel3 search unavailable (%s); checking fallback configuration.", err)
                db.log_audit_event("CHANNEL3_ERROR", str(err), "SYSTEM")
                should_fallback = (
                    self._fallback_override
                    if self._fallback_override is not None
                    else (
                        self.allow_auto_fallback
                        and (settings.DEMO_MODE or settings.PRODUCT_PROVIDER.lower() == "auto")
                    )
                )
                if should_fallback:
                    # Automatically use safe mock/fallback service when external service is unavailable
                    candidates = await self.mock_service.search(
                        query=query,
                        budget_limit=budget_limit,
                        min_price=min_price,
                        requirements=reqs
                    )
                    self.last_search_candidates = candidates
                    top_results = candidates[:display_limit]
                    return {
                        "source": "Demo Product Mode (Channel3 Unavailable Fallback)",
                        "product_mode": "DEMO PRODUCT MODE",
                        "channel3_integrated": False,
                        "is_mock_fallback": True,
                        "error": False,
                        "warning": "Channel3 API unavailable; showing Demo Mode products.",
                        "query": query,
                        "count": len(top_results),
                        "total_candidates": len(candidates),
                        "has_more": len(candidates) > len(top_results),
                        "products": top_results
                    }
                return {
                    "source": "Channel3 Real Product Search",
                    "product_mode": "REAL PRODUCT MODE",
                    "channel3_integrated": True,
                    "is_mock_fallback": False,
                    "error": True,
                    "error_message": "I'm having trouble searching right now.\nPlease try again.",
                    "query": query,
                    "count": 0,
                    "total_candidates": 0,
                    "has_more": False,
                    "products": []
                }

        # DEMO PRODUCT MODE ('mock')
        candidates = await self.mock_service.search(
            query=query,
            budget_limit=budget_limit,
            min_price=min_price,
            requirements=reqs
        )
        self.last_search_candidates = candidates
        top_results = candidates[:display_limit]
        return {
            "source": "Demo Product Mode (Mock Catalog)",
            "product_mode": "DEMO PRODUCT MODE",
            "channel3_integrated": False,
            "is_mock_fallback": True,
            "error": False,
            "query": query,
            "count": len(top_results),
            "total_candidates": len(candidates),
            "has_more": len(candidates) > len(top_results),
            "products": top_results
        }

    def filter_cached_candidates(
        self,
        budget_limit: Optional[float] = None,
        requirements: Optional[List[str]] = None,
        cheaper_than: Optional[float] = None,
        intent: Optional[StructuredSearchIntent] = None,
    ) -> List[Product]:
        """
        Filters already-retrieved session candidates in memory without making new API calls.
        Uses generic relevance & color/brand/budget constraints when StructuredSearchIntent is provided.
        """
        pool = self.last_search_candidates or []
        if not pool:
            return []

        if intent is not None:
            work_pool = [p for p in pool if cheaper_than is None or p.price < cheaper_than]
            filtered, _, _ = score_and_filter_candidates(work_pool, intent, enforce_budget=True)
            return filtered

        filtered: List[Product] = []
        req_terms = [r.lower().strip() for r in (requirements or []) if r.strip()]

        for p in pool:
            if budget_limit is not None and p.price > budget_limit:
                continue
            if cheaper_than is not None and p.price >= cheaper_than:
                continue
            if req_terms:
                blob = " ".join([
                    p.title.lower(),
                    p.description.lower(),
                    " ".join(f.lower() for f in p.documented_accessibility_features),
                    " ".join(f"{k} {v}".lower() for k, v in (p.attributes or {}).items() if k != "color_swatches")
                ])
                if not any(rt in blob or all(w in blob for w in rt.split()) for rt in req_terms):
                    continue
            filtered.append(p)

        return filtered

    def compare_products(self, product_ids: List[str]) -> Dict[str, Any]:
        """
        Compares two products using ONLY attributes supported by actual product data.
        Does NOT make any new Channel3 API calls.
        """
        products = [self.get_product_by_id(pid) for pid in product_ids]
        valid_products = [p for p in products if p is not None]

        if len(valid_products) < 2:
            return {"error": "At least 2 valid products are required for comparison"}

        prod1 = valid_products[0]
        prod2 = valid_products[1]

        cheaper_prod = prod1 if prod1.price <= prod2.price else prod2
        diff_price = round(abs(prod1.price - prod2.price), 2)

        def get_factual_feature(p: Product) -> str:
            if p.documented_accessibility_features:
                return p.documented_accessibility_features[0].rstrip(".")
            if p.description:
                first_clause = re.split(r"[.;\n]+", p.description)[0].strip()
                if first_clause:
                    return first_clause[:80]
            return f"Sold by {p.merchant}"

        feat1 = get_factual_feature(prod1)
        feat2 = get_factual_feature(prod2)

        line1_diff = f" and ${diff_price:.2f} cheaper" if diff_price > 0 and cheaper_prod.id == prod1.id else ""
        line2_diff = f" and ${diff_price:.2f} cheaper" if diff_price > 0 and cheaper_prod.id == prod2.id else ""

        better_opt = "Option 2" if cheaper_prod.id == prod2.id else "Option 1"

        summary = (
            f"Option 1 — ${prod1.price:.2f}\n"
            f"{feat1}{line1_diff}.\n\n"
            f"Option 2 — ${prod2.price:.2f}\n"
            f"{feat2}{line2_diff}.\n\n"
            f"Recommendation:\n"
            f"{better_opt} is the lower-cost choice."
        )

        comparison_matrix = []
        for idx, p in enumerate(valid_products[:2]):
            total_estimated = round(p.price + p.shipping + p.estimated_tax, 2)
            comparison_matrix.append({
                "option_number": idx + 1,
                "id": p.id,
                "title": p.title,
                "merchant": p.merchant,
                "price": p.price,
                "shipping": p.shipping,
                "estimated_tax": p.estimated_tax,
                "total_estimated": total_estimated,
                "rating": p.rating,
                "feature": get_factual_feature(p),
                "is_cheaper": p.id == cheaper_prod.id
            })

        return {
            "summary": summary,
            "products": comparison_matrix,
            "recommendation": f"{better_opt} is the lower-cost choice."
        }

    def answer_attribute_question(self, user_text: str, current_products: List[Dict[str, Any]]) -> Dict[str, Any]:
        """
        Checks whether the requested attribute/feature is actually supported by the
        returned Channel3/catalog data. If missing, explicitly says:
        "I don't have reliable information about that feature."
        """
        text_lower = user_text.lower()

        if any(w in text_lower for w in ["review", "reviews", "rating", "rated", "stars"]):
            rated = [
                (idx, p)
                for idx, p in enumerate(current_products[:3])
                if p.get("rating") is not None
            ]
            if rated:
                best_idx, best_prod = max(
                    rated,
                    key=lambda pair: (float(pair[1].get("rating") or 0.0), int(pair[1].get("review_count") or 0)),
                )
                lines = []
                for idx, p in rated:
                    rc = p.get("review_count")
                    rc_text = f" across {rc} reviews" if rc else ""
                    lines.append(f"Option {idx + 1} ({p.get('title')}) is rated {p.get('rating')} out of 5{rc_text}.")
                summary = (
                    f"Option {best_idx + 1} ({best_prod.get('title')}) has the highest listed rating at {best_prod.get('rating')} out of 5.\n"
                    + "\n".join(lines)
                )
                return {"found": True, "message": summary, "speech_response": summary}
            no_rating_msg = "Ratings and reviews are not listed in the product catalog for these options."
            return {"found": False, "message": no_rating_msg, "speech_response": no_rating_msg}

        # Identify target attribute regex patterns from question
        attribute_patterns: List[str] = []
        if any(w in text_lower for w in ["lightest", "weight", "heavy", "light", "grams", "ounces", "lbs"]):
            attribute_patterns = [
                r"\b\d+(?:\.\d+)?\s*(?:g|grams|oz|ounces|lb|lbs|pounds)\b",
                r"\b(?:weight|lightweight|ultra-light|featherweight)\b",
            ]
        elif any(w in text_lower for w in ["battery", "hours", "charge"]):
            attribute_patterns = [r"\b(?:battery|hour|hours|hr|mah|charging)\b"]
        elif any(w in text_lower for w in ["waterproof", "water resistant", "ipx", "sweat"]):
            attribute_patterns = [r"\b(?:waterproof|water-resistant|water resistant|ipx\d*|sweatproof)\b"]
        elif any(w in text_lower for w in ["bluetooth", "version", "multipoint"]):
            attribute_patterns = [r"\b(?:bluetooth|multipoint|multi-point)\b"]
        elif any(w in text_lower for w in ["warranty", "guarantee"]):
            attribute_patterns = [r"\b(?:warranty|guarantee)\b"]
        else:
            stop_words = {
                "which", "what", "does", "have", "the", "one", "is", "are", "this", "that",
                "first", "second", "third", "option", "about", "tell", "me", "most", "best"
            }
            words = [
                w for w in re.findall(r"\w+", text_lower)
                if len(w) >= 4 and w not in stop_words
            ]
            attribute_patterns = [rf"\b{re.escape(w)}\b" for w in words]

        matches: List[str] = []
        for idx, p in enumerate(current_products[:3]):
            title = p.get("title", f"Option {idx + 1}")
            desc = str(p.get("description") or "")
            feats = p.get("documented_accessibility_features") or []
            attrs = p.get("attributes") or {}

            combined_lines = [desc] + [str(f) for f in feats] + [f"{k}: {v}" for k, v in attrs.items()]
            for line in combined_lines:
                line_lower = line.lower()
                if any(re.search(pat, line_lower) for pat in attribute_patterns):
                    matches.append(f"Option {idx + 1} ({title}) lists: {line.strip()}.")
                    break

        if matches:
            msg = "\n".join(matches)
            return {
                "found": True,
                "message": msg,
                "speech_response": msg
            }

        missing_msg = "I don't have reliable information about that feature."
        return {
            "found": False,
            "message": missing_msg,
            "speech_response": missing_msg
        }

    def get_search_suggestions(self, query: str, limit: int = 6) -> List[str]:
        """
        Generates generic, lightweight search suggestions from partial typed queries,
        recent search history, saved searches, and in-memory cached catalog products
        without making expensive live Channel3 calls per keystroke.
        """
        from app.db.database import db

        raw = re.sub(r"\s+", " ", (query or "").strip())
        if len(raw) < 2:
            return []

        cleaned = re.sub(r"^(?:find|search\s+for|look\s+for|show\s+me)\s+", "", raw, flags=re.IGNORECASE).strip()
        if len(cleaned) < 2:
            cleaned = raw
        q_lower = cleaned.lower()
        q_tokens = [tok for tok in re.findall(r"[a-z0-9]+", q_lower) if len(tok) >= 2]
        if not q_tokens:
            return []

        scored: List[tuple[int, str]] = []
        seen_lower: set[str] = set()

        def add_candidate(text: str, score: int) -> None:
            candidate = re.sub(r"\s+", " ", str(text or "").strip())
            if not candidate or len(candidate) > 64:
                return
            key = candidate.lower()
            if key in seen_lower:
                return
            seen_lower.add(key)
            scored.append((score, candidate))

        # 1. Saved searches & recent search history matching query tokens/prefix
        for s in db.get_all_saved_searches():
            dq = (s.get("display_query") or s.get("original_query") or "").strip()
            dq_lower = dq.lower()
            if dq and (dq_lower.startswith(q_lower) or all(t in dq_lower for t in q_tokens)):
                add_candidate(dq, 95 if dq_lower.startswith(q_lower) else 80)

        for h in db.get_recent_search_history(limit=25):
            hq = (h.get("display_query") or h.get("query") or "").strip()
            hq_lower = hq.lower()
            if hq and (hq_lower.startswith(q_lower) or all(t in hq_lower for t in q_tokens)):
                add_candidate(hq, 85 if hq_lower.startswith(q_lower) else 72)

        # 2. Cached Channel3 / mock catalog / saved item titles & concise noun phrases
        catalog_pool: List[Product] = []
        seen_prod_ids: set[str] = set()
        for prod in (
            list(self.last_search_candidates)
            + list(self.channel3_service.cached_by_id.values())
            + list(self.mock_service.get_all_products())
        ):
            if prod.id not in seen_prod_ids:
                seen_prod_ids.add(prod.id)
                catalog_pool.append(prod)

        for prod in catalog_pool:
            title = (prod.title or "").strip()
            cat = (prod.category or "").strip()
            title_lower = title.lower()
            cat_lower = cat.lower()
            if all(t in title_lower for t in q_tokens):
                # Prefer clean 2-5 word sub-phrases centered around the matched query tokens
                words = re.findall(r"[A-Za-z0-9][A-Za-z0-9&'-]*", title)
                phrase = " ".join(words[:5]) if len(words) > 5 else title
                add_candidate(phrase, 68 if phrase.lower().startswith(q_lower) else 58)
            elif cat and any(t in cat_lower for t in q_tokens):
                add_candidate(f"{cleaned} in {cat.lower()}" if q_lower not in cat_lower else cat.lower(), 52)

        for sav in db.get_all_saved_items():
            st = (sav.get("product_title") or "").strip()
            if st and all(t in st.lower() for t in q_tokens):
                words = re.findall(r"[A-Za-z0-9][A-Za-z0-9&'-]*", st)
                add_candidate(" ".join(words[:5]), 64)

        # 3. Generic query completions & refinements (zero hardcoded brands/items)
        has_budget = bool(re.search(r"\b(?:under|below|max|less than)\b|\$\d+", q_lower))
        has_quality = any(w in q_lower for w in ("best", "top", "rated", "affordable", "cheap", "gift"))
        add_candidate(cleaned, 90)
        if not has_budget:
            add_candidate(f"{cleaned} under $30", 48)
            add_candidate(f"{cleaned} under $50", 46)
        if not has_quality:
            add_candidate(f"best rated {cleaned}", 44)
            add_candidate(f"{cleaned} gift", 40)

        scored.sort(key=lambda item: (-item[0], len(item[1])))
        cap = max(1, min(int(limit or 6), 8))
        return [text for _, text in scored[:cap]]


product_service = ProductService()
channel3_product_service = product_service.channel3_service
mock_product_service = product_service.mock_service
