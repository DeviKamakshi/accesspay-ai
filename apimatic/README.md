# AccessPay AI — APIMatic Developer Platform Integration

This directory contains the machine-readable OpenAPI specification and APIMatic metadata that powers the AccessPay Developer Platform.

## Purpose

AccessPay is not merely a single storefront application — it is designed as **Accessibility Commerce Infrastructure** that any online merchant can integrate into their existing checkout funnel.

By importing `accesspay-openapi.json` into APIMatic:
1. **Automated Multi-Language SDK Generation**: Instantly generates type-safe SDKs in TypeScript, Python, C#, Java, Go, and PHP.
2. **Accessible API Documentation Portal**: Provides an interactive developer console with built-in code samples demonstrating how third-party merchants invoke:
   - `POST /api/purchase/review`: Prepares transparent cost breakdowns and plain-language subscription warnings.
   - `POST /api/purchase/confirm`: Validates exact spoken phrases and enforces ambiguity protection before charging PayPal or other processors.
3. **Price Integrity Auditing**: Explains how merchants ensure in-flight price updates invalidate stale authorizations.

## Files
- `accesspay-openapi.json`: Validated OpenAPI 3.1 specification exported directly from FastAPI.
- `apimatic-metadata.json`: CodeGen and Portal theme configuration for APIMatic.
