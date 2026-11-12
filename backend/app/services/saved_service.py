import datetime
import uuid
from typing import Any, Dict, List, Optional

from app.db.database import db
from app.models.product import Product
from app.models.saved import SavedItem, SavedSearch, SearchHistoryEntry
from app.services.cart_service import cart_service
from app.services.product_service import product_service


class SavedService:
    """
    Manages persisted Saved Items, Saved Searches, and bounded Search History.
    Explicitly separate from temporary ActiveSearchSession, Cart, and Order History.
    Saving NEVER adds to cart or authorizes payment.
    """

    def save_item(self, product_data: Dict[str, Any] | Product) -> SavedItem:
        raw = product_data.model_dump() if isinstance(product_data, Product) else dict(product_data)
        product_id = str(raw["id"])
        attrs = list(raw.get("documented_accessibility_features") or [])
        extra_attrs = raw.get("attributes") or {}
        if isinstance(extra_attrs, dict):
            brand = extra_attrs.get("brand")
            if brand and str(brand) not in " ".join(attrs):
                attrs.append(f"Brand: {brand}")
        if raw.get("category"):
            cat_note = f"Category: {raw['category']}"
            if cat_note not in attrs:
                attrs.append(cat_note)

        # Preserve existing saved_item_id if already saved by product_id
        existing = next(
            (i for i in self.list_saved_items() if i.product_id == product_id),
            None,
        )
        saved_item = SavedItem(
            saved_item_id=existing.saved_item_id if existing else f"sav_{uuid.uuid4().hex[:10]}",
            product_id=product_id,
            product_title=str(raw.get("title") or "Saved Product"),
            merchant=str(raw.get("merchant") or "Verified Merchant"),
            price_at_save=round(float(raw.get("price") or 0.0), 2),
            image_url=raw.get("image_url"),
            product_url=raw.get("product_url"),
            important_attributes=attrs[:5],
            product_snapshot=raw,
            saved_at=datetime.datetime.now(datetime.timezone.utc).isoformat(),
        )
        db.save_saved_item(saved_item.model_dump())
        db.log_audit_event("ITEM_SAVED", f"Saved '{saved_item.product_title}' (${saved_item.price_at_save:.2f})", "USER")
        return saved_item

    def list_saved_items(self) -> List[SavedItem]:
        return [SavedItem(**row) for row in db.get_all_saved_items()]

    def get_saved_item(self, saved_item_id: str) -> Optional[SavedItem]:
        for item in self.list_saved_items():
            if item.saved_item_id == saved_item_id or item.product_id == saved_item_id:
                return item
        return None

    def remove_saved_item(self, saved_item_id_or_product_id: str) -> bool:
        removed = db.delete_saved_item(saved_item_id_or_product_id)
        if removed:
            db.log_audit_event("ITEM_UNSAVED", f"Removed saved item {saved_item_id_or_product_id}", "USER")
        return removed

    async def add_saved_item_to_cart(self, saved_item_id: str) -> Dict[str, Any]:
        """
        Adds a saved item to the active cart using live/refreshed product pricing when available.
        Never trusts an old saved price blindly for payment authority.
        """
        saved = self.get_saved_item(saved_item_id)
        if not saved:
            raise ValueError("Saved item not found.")

        live_product = product_service.get_product_by_id(saved.product_id)
        # Attempt lightweight live Channel3 refresh by exact product title when Channel3 is active
        if product_service.get_active_provider_mode() == "channel3" and product_service.channel3_service.is_configured():
            try:
                refresh_res = await product_service.channel3_service.search(
                    query=saved.product_title,
                    limit=8,
                    force_refresh=True,
                )
                matched = next((p for p in refresh_res if p.id == saved.product_id), None)
                if matched:
                    live_product = matched
            except Exception:
                pass

        if not live_product and saved.product_snapshot:
            try:
                live_product = Product(**saved.product_snapshot)
                product_service.channel3_service.cached_by_id[live_product.id] = live_product
            except Exception:
                live_product = None

        if not live_product:
            raise ValueError("Product details for this saved item are unavailable.")

        # Ensure live_product is registered in lookup cache so cart_service sees its current price
        if product_service.get_product_by_id(live_product.id) is None:
            product_service.channel3_service.cached_by_id[live_product.id] = live_product

        current_price = round(float(live_product.price), 2)
        saved_price = round(float(saved.price_at_save), 2)
        price_changed = current_price != saved_price

        updated_cart = cart_service.add_item(live_product.id, quantity=1)
        msg = (
            f"Added {live_product.title} to your cart. Note: price updated from ${saved_price:.2f} to ${current_price:.2f}."
            if price_changed
            else f"Added {live_product.title} (${current_price:.2f}) to your cart."
        )
        return {
            "success": True,
            "product": live_product.model_dump(),
            "saved_item_id": saved.saved_item_id,
            "price_at_save": saved_price,
            "current_price": current_price,
            "price_changed": price_changed,
            "cart": updated_cart.model_dump(),
            "message": msg,
        }

    def save_search(
        self,
        original_query: str,
        display_query: str,
        structured_intent: Dict[str, Any],
        filters: Dict[str, Any],
        sort: Optional[str],
        reference_product_ids: Optional[List[str]] = None,
    ) -> SavedSearch:
        # Upsert if exact same display_query already exists so user doesn't accumulate duplicates
        existing = next(
            (
                s for s in self.list_saved_searches()
                if s.display_query.strip().lower() == display_query.strip().lower()
                and s.sort == sort
                and s.filters == filters
            ),
            None,
        )
        saved_search = SavedSearch(
            saved_search_id=existing.saved_search_id if existing else f"srch_{uuid.uuid4().hex[:10]}",
            original_query=original_query,
            display_query=display_query or original_query,
            structured_intent=structured_intent,
            filters=filters,
            sort=sort,
            reference_product_ids=list(reference_product_ids or []),
            saved_at=datetime.datetime.now(datetime.timezone.utc).isoformat(),
        )
        db.save_saved_search(saved_search.model_dump())
        db.log_audit_event("SEARCH_SAVED", f"Saved search '{saved_search.display_query}'", "USER")
        return saved_search

    def list_saved_searches(self) -> List[SavedSearch]:
        return [SavedSearch(**row) for row in db.get_all_saved_searches()]

    def get_saved_search(self, saved_search_id: str) -> Optional[SavedSearch]:
        return next((s for s in self.list_saved_searches() if s.saved_search_id == saved_search_id), None)

    def delete_saved_search(self, saved_search_id: str) -> bool:
        removed = db.delete_saved_search(saved_search_id)
        if removed:
            db.log_audit_event("SAVED_SEARCH_DELETED", f"Deleted saved search {saved_search_id}", "USER")
        return removed

    def find_matching_saved_searches(self, query_text: str) -> List[SavedSearch]:
        searches = self.list_saved_searches()
        if not searches:
            return []
        t = query_text.lower().strip()
        if any(p in t for p in ("run that search", "that search again", "last saved search")):
            return [searches[0]]

        stop = {
            "open", "reopen", "re-open", "run", "rerun", "re-run", "my", "saved",
            "search", "searches", "again", "please", "show", "for", "the", "a",
            "an", "that", "one",
        }
        tokens = [w for w in t.split() if w not in stop and len(w) >= 2]
        if not tokens:
            return searches

        scored = []
        for s in searches:
            hay = f"{s.display_query} {s.original_query} {s.structured_intent.get('product_type', '')}".lower()
            hits = sum(1 for tok in tokens if tok in hay)
            if hits > 0:
                scored.append((hits, s))
        scored.sort(key=lambda x: -x[0])
        if not scored:
            return []
        best = scored[0][0]
        return [s for h, s in scored if h == best]

    def record_search_history(
        self,
        search_id: str,
        query: str,
        display_query: str,
        result_count: int,
        structured_intent: Optional[Dict[str, Any]] = None,
        filters: Optional[Dict[str, Any]] = None,
        sort: Optional[str] = None,
    ) -> SearchHistoryEntry:
        clean_q = (query or "").strip()
        if not clean_q:
            raise ValueError("Search query cannot be empty.")
        entry = SearchHistoryEntry(
            history_id=f"hist_{uuid.uuid4().hex[:10]}",
            search_id=search_id,
            query=clean_q,
            display_query=(display_query or clean_q).strip(),
            result_count=result_count,
            structured_intent=dict(structured_intent or {}),
            filters=dict(filters or {}),
            sort=sort,
            searched_at=datetime.datetime.now(datetime.timezone.utc).isoformat(),
        )
        db.record_search_history(entry.model_dump(), max_entries=20)
        return entry

    def list_search_history(self, limit: int = 20) -> List[SearchHistoryEntry]:
        return [SearchHistoryEntry(**row) for row in db.get_recent_search_history(limit=limit)]

    def get_search_history_entry(self, history_id: str) -> Optional[SearchHistoryEntry]:
        return next((h for h in self.list_search_history(limit=25) if h.history_id == history_id), None)

    def save_history_entry_as_saved_search(self, history_id: str) -> SavedSearch:
        entry = self.get_search_history_entry(history_id)
        if not entry:
            raise ValueError("Recent search entry not found.")
        return self.save_search(
            original_query=entry.query,
            display_query=entry.display_query,
            structured_intent=dict(entry.structured_intent or {}),
            filters=dict(entry.filters or {}),
            sort=entry.sort,
            reference_product_ids=[],
        )

    def clear_search_history(self) -> None:
        db.clear_search_history()


saved_service = SavedService()
