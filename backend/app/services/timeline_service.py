from typing import List, Dict, Any, Optional
from app.db.database import db
from app.models.timeline import TimelineEvent


class TimelineService:
    def get_all_timeline_events(self) -> List[TimelineEvent]:
        raw = db.get_all_timeline_events()
        return [TimelineEvent(**item) for item in raw]

    def query_timeline(self, query: str) -> Dict[str, Any]:
        """
        AI + Bryntum conversational query responder (Section 49 & Demo Scenario 12).
        Interprets questions about upcoming payments, trial expirations, and recurring charges.
        """
        q_lower = query.lower()
        events = self.get_all_timeline_events()
        highlighted_ids: List[str] = []
        response_msg = ""

        if "next week" in q_lower or "coming" in q_lower:
            # Events in the upcoming week (Nov 8 - Nov 14)
            filtered = [e for e in events if e.category in ["delivery", "subscription"] and e.status in ["SCHEDULED", "UPCOMING"]]
            highlighted_ids = [e.id for e in filtered]
            items_str = ", ".join([f"{e.title} (${e.amount:.2f})" if e.amount else e.title for e in filtered])
            response_msg = f"Next week you have: {items_str}. Highlighted on your Bryntum Accessible Commerce Timeline."

        elif "free trial" in q_lower or "trial" in q_lower:
            trials = [e for e in events if e.category == "trial_expiration"]
            highlighted_ids = [e.id for e in trials]
            if trials:
                t = trials[0]
                response_msg = f"Your free trial for {t.title} ends on {t.display_date}. After that, it will renew at ${t.amount:.2f}/month unless cancelled."
            else:
                response_msg = "You have no active free trials ending soon."

        elif "recurring" in q_lower or "renew" in q_lower or "subscription" in q_lower:
            recurring = [e for e in events if e.is_recurring]
            highlighted_ids = [e.id for e in recurring]
            monthly_total = sum(e.amount for e in recurring if e.amount)
            response_msg = f"You have {len(recurring)} active subscriptions renewing this month totaling ${monthly_total:.2f}. Each charge is highlighted below."

        else:
            response_msg = f"Showing all {len(events)} events on your commerce timeline."

        # Mark highlights on returned events
        result_events = []
        for e in events:
            e_copy = e.model_copy()
            if e.id in highlighted_ids:
                e_copy.highlight = True
            result_events.append(e_copy)

        return {
            "query": query,
            "message": response_msg,
            "highlighted_count": len(highlighted_ids),
            "events": [e.model_dump() for e in result_events]
        }


timeline_service = TimelineService()
