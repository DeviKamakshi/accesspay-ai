---
title: AccessPay Merchant API
description: "Voice-first accessible shopping and safer PayPal-powered checkout APIs."
---

# AccessPay Merchant API

Add voice-first, accessible shopping and safer payment experiences to your existing application.

AccessPay provides APIs for conversational product discovery, shopping context, saved items, cart operations, purchase review, recurring-payment awareness, and PayPal-powered checkout.

## What is AccessPay?

AccessPay is an accessibility and commerce layer designed to reduce the physical interaction required during online shopping.

A merchant can keep its existing website or application while integrating AccessPay capabilities through APIs.

## What can you integrate?

- Conversational product discovery
- Context-aware product comparison
- Saved products and searches
- Cart management
- Voice-controlled commerce actions
- Purchase review
- Exact-amount purchase confirmation
- Recurring subscription confirmation
- PayPal checkout
- Order and subscription history

## How it works

```text
Customer
   ↓
Merchant Website / App
   ↓
AccessPay API
   ↓
┌─────────────────────────────────┐
│ Gemini   │ Channel3 │ PayPal    │
│ Intent   │ Products │ Payments  │
└─────────────────────────────────┘
```

- **Google Gemini:** Understands natural-language shopping intent.
- **Channel3:** Provides real commerce product information in this hackathon implementation.
- **PayPal:** Handles buyer approval and one-time/recurring Sandbox payment workflows.
- **AccessPay:** Maintains shopping context and enforces transaction safety.

## Human-controlled payments

AccessPay allows AI to help search, compare, navigate, and prepare a transaction.

It does not allow conversational AI to silently authorize payment.

For a one-time purchase, confirmation is bound to the exact amount:

```text
Confirm $53.99 purchase
```

For recurring payments, confirmation is bound to both amount and frequency:

```text
Confirm $19.99 monthly subscription
```

## Start integrating

Use the generated APIMatic portal features:

1. Open **SDKs** to explore TypeScript and Python integration.
2. Open **API Reference** to browse AccessPay endpoints and schemas.
3. Use the **Context Plugin** section for AI-assisted developer integration where supported.

APIMatic-generated integration documentation and SDK tooling are available for TypeScript and Python.

## Prototype status

AccessPay Merchant API is currently a hackathon prototype.

Production deployment would require merchant authentication, tenant isolation, rate limiting, webhooks, monitoring, audit controls, and additional production security.

## Built with

- **Google Gemini** — conversational intent
- **Channel3** — real commerce product discovery
- **PayPal Sandbox** — one-time and recurring payment workflows
- **APIMatic** — API developer experience, SDK/documentation tooling, and PayPal API context during development
- **FastAPI** — AccessPay API
