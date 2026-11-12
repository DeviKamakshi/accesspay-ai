# Importing AccessPay Merchant API into APIMatic

**API Name:** `AccessPay Merchant API` (`version 1.0.0`, `OpenAPI 3.1.0`)  
**Specification File:** [`accesspay-openapi.json`](./accesspay-openapi.json)

## What This File Represents

`accesspay-openapi.json` was exported directly from the running AccessPay FastAPI application (`app.openapi()`). It documents the actual implemented prototype routes across:

- **AI & Intent** (`/api/ai/intent`, `/api/ai/commands`, `/api/ai/status`, `/api/ai/reset-conversation`) — Natural-language NLU via Google Gemini (Gemini never supplies authoritative prices, totals, or payment authorization).
- **Products** (`/api/products/search`, `/api/products/...`) — Real-commerce search via Channel3 in this hackathon prototype (merchant-owned catalogs can plug in later).
- **Saved** (`/api/saved/items`, `/api/saved/searches`, `/api/saved/history`)
- **Cart** (`/api/cart`, `/api/cart/items`) — Server-authoritative cart totals.
- **Checkout** (`/api/purchase/review`, `/api/purchase/confirm`, `/api/purchase/cancel`, `/api/purchase/state`) — Deterministic exact-amount human confirmation gates.
- **Orders** (`/api/orders`, `/api/orders/{order_id}`, reorder & tracking).
- **Payments** (`/api/payments/paypal/create-order`, `/api/payments/paypal/capture-order/{order_id}`, `/api/payments/paypal/order/{order_id}`) — PayPal Sandbox Orders API v2.
- **Subscriptions** (`/api/subscriptions/products`, `/api/subscriptions/review`, `/api/subscriptions/confirm`, `/api/subscriptions/paypal/create`, `/api/subscriptions/{subscription_id}/cancel`) — Isolated Demo Subscription Catalog + PayPal Sandbox Subscriptions API v1 requiring **both exact recurring amount and billing frequency** confirmation.

### Endpoint Classification

- **Public Merchant API Candidates:** `AI & Intent` (`/api/ai/intent`), `Products` (`/api/products/search`, `/api/products/{product_id}`, `/api/products/compare`), `Saved`, `Cart`, `Checkout` (`/api/purchase/review`, `/api/purchase/confirm`, `/api/purchase/cancel`), `Orders`, `Payments` (`/api/payments/paypal/create-order`, `/api/payments/paypal/capture-order/{order_id}`), `Subscriptions`.
- **Internal Application API:** `/api/products/active-search`, `/api/products/suggestions`, `/api/products/show-more`, `/api/purchase/acknowledge-subscription`, `/api/accessibility/...`, `/api/timeline/...`, `/api/analytics/...`.
- **Development / Debug:** `/api/products/mode`, `/api/payments/mode`, `/api/payments/simulate-failure`, `/api/purchase/simulate-price-change`, `/api/demo/...`, `/api/developer/overview`.
- **System:** `/health`, `/api/health`, `/`.

> **Prototype Notice:** Prototype API. Production merchant authentication and tenant isolation are not yet implemented.

---

## How to Import into APIMatic

1. Open **APIMatic**.
2. Choose **"Import your API Spec."**
3. Upload **`accesspay-openapi.json`** from the project root.
4. Wait for APIMatic validation to complete.
5. Review any validation warnings or notices.
6. Continue to the APIMatic project.
7. Inspect the generated API documentation portal.
8. Inspect the available SDK generation options (recommended first SDKs: **TypeScript** for merchant web apps or **Python** for backend integrations).

---

## What NOT to Claim

- Do **not** claim an AccessPay SDK has already been generated until you actually generate it in APIMatic.
- Do **not** claim APIMatic sits in the runtime payment path (runtime payments use PayPal Sandbox directly).
- Do **not** claim AccessPay has production merchant auth or tenant isolation yet.

