from abc import ABC, abstractmethod
from typing import Any, List, Optional
from app.models.subscription import SubscriptionOffer


class CommerceProvider(ABC):
    """Base abstraction showing how AccessPay separates physical products from recurring subscriptions."""

    provider_type: str = "generic"

    @abstractmethod
    def search(self, query: Optional[str] = None) -> List[Any]:
        raise NotImplementedError


DEMO_SUBSCRIPTION_CATALOG: List[SubscriptionOffer] = [
    SubscriptionOffer(
        id="sub_dev_api_pro",
        provider="AccessPay Demo Cloud Services",
        name="Developer API Pro — Demo Subscription",
        description=(
            "DEMO SUBSCRIPTION: Simulated recurring API & developer tooling plan for demonstrating "
            "AccessPay recurring-payment disclosure and PayPal Sandbox subscription approval."
        ),
        currency="USD",
        amount_due_today=19.99,
        recurring_amount=19.99,
        billing_frequency="monthly",
        billing_interval="MONTH",
        interval_count=1,
        trial_period=None,
        setup_fee=None,
        renewal_behavior="Automatically renews every month at $19.99/month until cancelled.",
        cancellation_information="You can cancel anytime via AccessPay or PayPal to stop future monthly charges.",
        source="demo_subscription_catalog",
        is_demo=True,
    ),
    SubscriptionOffer(
        id="sub_dev_sandbox_team",
        provider="AccessPay Demo Cloud Services",
        name="API Docs & Sandbox Team — Demo Subscription",
        description=(
            "DEMO SUBSCRIPTION: Simulated team developer portal and sandbox quota subscription "
            "with recurring monthly billing."
        ),
        currency="USD",
        amount_due_today=39.00,
        recurring_amount=39.00,
        billing_frequency="monthly",
        billing_interval="MONTH",
        interval_count=1,
        trial_period=None,
        setup_fee=None,
        renewal_behavior="Automatically renews every month at $39.00/month until cancelled.",
        cancellation_information="You can cancel anytime via AccessPay or PayPal to stop future monthly charges.",
        source="demo_subscription_catalog",
        is_demo=True,
    ),
    SubscriptionOffer(
        id="sub_cloud_annual",
        provider="AccessPay Demo Cloud Services",
        name="Developer Cloud Annual — Demo Subscription",
        description=(
            "DEMO SUBSCRIPTION: Simulated annual developer cloud infrastructure plan billed once per year."
        ),
        currency="USD",
        amount_due_today=149.00,
        recurring_amount=149.00,
        billing_frequency="yearly",
        billing_interval="YEAR",
        interval_count=1,
        trial_period=None,
        setup_fee=None,
        renewal_behavior="Automatically renews every year at $149.00/year until cancelled.",
        cancellation_information="You can cancel anytime via AccessPay or PayPal before the next annual renewal.",
        source="demo_subscription_catalog",
        is_demo=True,
    ),
]


class SubscriptionProvider(CommerceProvider):
    """Deterministic Demo Subscription Catalog provider (never routed through Channel3)."""

    provider_type = "subscription"

    def __init__(self):
        self._offers = list(DEMO_SUBSCRIPTION_CATALOG)

    def search(self, query: Optional[str] = None) -> List[SubscriptionOffer]:
        q = (query or "").strip().lower()
        if not q:
            return list(self._offers)

        if "annual" in q or "yearly" in q or "year" in q:
            yearly = [o for o in self._offers if o.billing_frequency == "yearly"]
            if yearly:
                return yearly + [o for o in self._offers if o not in yearly]

        if "monthly" in q or "month" in q:
            monthly = [o for o in self._offers if o.billing_frequency == "monthly"]
            if monthly:
                return monthly

        tokens = [
            tok
            for tok in q.split()
            if tok not in {"show", "me", "find", "a", "an", "the", "subscription", "subscriptions", "services", "plan", "plans", "for"}
            and len(tok) >= 2
        ]
        if not tokens:
            return list(self._offers)

        scored = []
        for offer in self._offers:
            hay = f"{offer.name} {offer.provider} {offer.description} {offer.billing_frequency}".lower()
            hits = sum(1 for tok in tokens if tok in hay)
            scored.append((hits, offer))
        scored.sort(key=lambda item: -item[0])
        matched = [o for h, o in scored if h > 0]
        return matched if matched else list(self._offers)

    def get_offer(self, offer_id: str) -> Optional[SubscriptionOffer]:
        return next((o for o in self._offers if o.id == offer_id), None)

    @staticmethod
    def answer_question(offer: SubscriptionOffer, question: str) -> str:
        """Answers subscription questions strictly from authoritative offer terms."""
        q = (question or "").strip().lower()
        if "trial" in q:
            if offer.trial_period:
                return f"This demo subscription includes a {offer.trial_period} trial, then ${offer.recurring_amount:.2f} {offer.billing_frequency}."
            return f"No free trial is listed. Due today is ${offer.amount_due_today:.2f}, then ${offer.recurring_amount:.2f} {offer.billing_frequency}."
        if "today" in q or "now" in q:
            return f"You will pay ${offer.amount_due_today:.2f} today for {offer.name}, then ${offer.recurring_amount:.2f} {offer.billing_frequency}."
        if "every month" in q or "monthly" in q or "recurring" in q or "how much" in q:
            return f"This is a recurring {offer.billing_frequency} demo subscription: ${offer.amount_due_today:.2f} due today and ${offer.recurring_amount:.2f} {offer.billing_frequency} until cancelled."
        if "often" in q or "frequency" in q or "renew" in q or "when" in q:
            return f"Billing is {offer.billing_frequency}. {offer.renewal_behavior}"
        if "cancel" in q:
            return offer.cancellation_information
        if "is this a subscription" in q:
            return f"Yes. {offer.name} is a recurring {offer.billing_frequency} demo subscription (${offer.recurring_amount:.2f} {offer.billing_frequency}), not a one-time purchase."
        return (
            f"You are reviewing {offer.name} from {offer.provider} (Demo Subscription). "
            f"Due today: ${offer.amount_due_today:.2f}. Recurring charge: ${offer.recurring_amount:.2f} {offer.billing_frequency}. "
            f"{offer.renewal_behavior} {offer.cancellation_information}"
        )


subscription_provider = SubscriptionProvider()

