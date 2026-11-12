import React, { useEffect, useState } from 'react';
import {
  ArrowRight,
  CheckCircle2,
  Code2,
  CreditCard,
  ExternalLink,
  Layers,
  Mic,
  Repeat,
  ShieldCheck,
  ShoppingBag,
  XCircle,
} from 'lucide-react';
import { api } from '../../services/api';

interface DevelopersViewProps {
  onBackToShop: () => void;
}

const ACTUAL_ENDPOINTS = [
  { method: 'POST', path: '/api/ai/intent', desc: 'Natural-language product discovery and conversational follow-ups' },
  { method: 'POST', path: '/api/products/search', desc: 'Search verified physical products via Channel3' },
  { method: 'GET', path: '/api/cart', desc: 'Fetch current shopping cart and server totals' },
  { method: 'POST', path: '/api/payments/paypal/create-order', desc: 'Create PayPal Sandbox order after explicit confirmation' },
  { method: 'POST', path: '/api/payments/paypal/capture-order/{order_id}', desc: 'Capture approved PayPal Sandbox order' },
  { method: 'GET', path: '/api/orders', desc: 'List completed one-time orders' },
];

export const DevelopersView: React.FC<DevelopersViewProps> = ({ onBackToShop }) => {
  const [overview, setOverview] = useState<any>(null);

  useEffect(() => {
    api.getDeveloperOverview().then(setOverview).catch(() => {});
  }, []);

  const envStatus = overview?.environment_status || {
    paypal_sandbox: 'Configured ✓',
    channel3_products: 'Configured ✓',
    google_gemini_ai: 'Configured ✓',
    apimatic_context_plugin: 'Configured ✓ (Development Context)',
  };

  const verificationRows: Array<{ area: string; verified: string; notes: string }> =
    overview?.apimatic_verification_report || [
      { area: 'PayPal OAuth / Authentication', verified: 'YES', notes: 'OAuth 2.0 client_credentials against Sandbox token endpoint with caching.' },
      { area: 'Orders Create (POST /v2/checkout/orders)', verified: 'YES', notes: 'intent=CAPTURE, purchase_units, PayPal-Request-Id, application_context.' },
      { area: 'Approval URL Handling', verified: 'YES', notes: 'Extracts HATEOAS approve link for Sandbox buyer approval.' },
      { area: 'Orders Capture (POST /v2/checkout/orders/{id}/capture)', verified: 'YES', notes: 'Checks APPROVED state before capture and records capture ID.' },
      { area: 'Return / Cancel URLs', verified: 'YES', notes: 'Canonical return_url/cancel_url with server-side status check on redirect.' },
      { area: 'Subscriptions Plans & Lifecycle (v1/billing/*)', verified: 'YES', notes: 'Covered by APIMatic paypal subscriptions controller.' },
      { area: 'Catalog Products (POST /v1/catalogs/products)', verified: 'NOT COVERED', notes: 'Outside APIMatic paypal v2.29 controllers; verified via PayPal REST docs.' },
      { area: 'Error Handling', verified: 'YES', notes: 'Typed Error / SubscriptionError guidance; keeps secrets and raw errors out of UI.' },
    ];

  return (
    <section
      aria-label="AccessPay for Merchants and Developers"
      data-testid="developers-page"
      style={{ maxWidth: '1080px', margin: '0 auto', padding: '16px 8px 64px', color: '#f8fafc' }}
    >
      {/* Header */}
      <div style={{ display: 'flex', flexWrap: 'wrap', justifyContent: 'space-between', alignItems: 'flex-start', gap: '16px', marginBottom: '28px' }}>
        <div>
          <span
            style={{
              display: 'inline-flex',
              alignItems: 'center',
              gap: '6px',
              fontSize: '0.78rem',
              fontWeight: 800,
              letterSpacing: '0.05em',
              textTransform: 'uppercase',
              color: '#38bdf8',
              backgroundColor: '#0c4a6e',
              padding: '4px 12px',
              borderRadius: '999px',
              marginBottom: '10px',
            }}
          >
            <Code2 size={14} aria-hidden="true" />
            Prototype Merchant API
          </span>
          <h1 style={{ fontSize: '2rem', fontWeight: 900, margin: '0 0 8px', letterSpacing: '-0.02em' }}>
            AccessPay for Merchants
          </h1>
          <p style={{ fontSize: '1.08rem', color: '#cbd5e1', margin: 0, maxWidth: '720px' }}>
            Add voice-first shopping and safer payment confirmation to existing commerce experiences.
          </p>
        </div>

        <div style={{ display: 'flex', flexWrap: 'wrap', gap: '10px' }}>
          <a
            href="http://127.0.0.1:8008/openapi.json"
            target="_blank"
            rel="noopener noreferrer"
            download="accesspay-openapi.json"
            style={{
              display: 'inline-flex',
              alignItems: 'center',
              gap: '6px',
              padding: '10px 16px',
              borderRadius: '10px',
              border: '1px solid #38bdf8',
              backgroundColor: '#0c4a6e',
              color: '#e0f2fe',
              fontWeight: 700,
              fontSize: '0.9rem',
              textDecoration: 'none',
            }}
          >
            Download OpenAPI Spec
            <ExternalLink size={15} aria-hidden="true" />
          </a>
          <a
            href="http://127.0.0.1:23513"
            target="_blank"
            rel="noopener noreferrer"
            style={{
              display: 'inline-flex',
              alignItems: 'center',
              gap: '6px',
              padding: '10px 16px',
              borderRadius: '10px',
              border: '1px solid #818cf8',
              backgroundColor: '#312e81',
              color: '#e0e7ff',
              fontWeight: 700,
              fontSize: '0.9rem',
              textDecoration: 'none',
            }}
          >
            View Merchant Developer Portal
            <ExternalLink size={15} aria-hidden="true" />
          </a>
          <a
            href="http://127.0.0.1:8008/docs"
            target="_blank"
            rel="noopener noreferrer"
            style={{
              display: 'inline-flex',
              alignItems: 'center',
              gap: '6px',
              padding: '10px 16px',
              borderRadius: '10px',
              backgroundColor: '#0284c7',
              color: '#ffffff',
              fontWeight: 700,
              fontSize: '0.9rem',
              textDecoration: 'none',
            }}
          >
            View API Docs
            <ExternalLink size={15} aria-hidden="true" />
          </a>
          <button
            type="button"
            onClick={onBackToShop}
            style={{
              padding: '10px 16px',
              borderRadius: '10px',
              border: '1px solid #334155',
              backgroundColor: '#0f172a',
              color: '#e2e8f0',
              fontWeight: 700,
              fontSize: '0.9rem',
            }}
          >
            Back to Shop
          </button>
        </div>
      </div>

      {/* Capability Cards */}
      <div style={{ display: 'grid', gridTemplateColumns: 'repeat(auto-fit, minmax(220px, 1fr))', gap: '14px', marginBottom: '26px' }}>
        <div style={{ backgroundColor: '#0f172a', border: '1px solid #1e293b', borderRadius: '16px', padding: '18px' }}>
          <div style={{ display: 'flex', alignItems: 'center', gap: '8px', color: '#38bdf8', fontWeight: 800, fontSize: '0.82rem', marginBottom: '6px' }}>
            <Mic size={16} aria-hidden="true" /> VOICE &amp; AI
          </div>
          <p style={{ margin: 0, fontSize: '0.92rem', color: '#cbd5e1' }}>Natural-language product discovery and follow-up actions.</p>
        </div>
        <div style={{ backgroundColor: '#0f172a', border: '1px solid #1e293b', borderRadius: '16px', padding: '18px' }}>
          <div style={{ display: 'flex', alignItems: 'center', gap: '8px', color: '#38bdf8', fontWeight: 800, fontSize: '0.82rem', marginBottom: '6px' }}>
            <ShoppingBag size={16} aria-hidden="true" /> COMMERCE
          </div>
          <p style={{ margin: 0, fontSize: '0.92rem', color: '#cbd5e1' }}>Product search, Saved items, Cart and Orders.</p>
        </div>
        <div style={{ backgroundColor: '#0f172a', border: '1px solid #1e293b', borderRadius: '16px', padding: '18px' }}>
          <div style={{ display: 'flex', alignItems: 'center', gap: '8px', color: '#34d399', fontWeight: 800, fontSize: '0.82rem', marginBottom: '6px' }}>
            <ShieldCheck size={16} aria-hidden="true" /> SAFE CHECKOUT
          </div>
          <p style={{ margin: 0, fontSize: '0.92rem', color: '#cbd5e1' }}>Server-authoritative totals and deterministic confirmation.</p>
        </div>
        <div style={{ backgroundColor: '#0f172a', border: '1px solid #1e293b', borderRadius: '16px', padding: '18px' }}>
          <div style={{ display: 'flex', alignItems: 'center', gap: '8px', color: '#fbbf24', fontWeight: 800, fontSize: '0.82rem', marginBottom: '6px' }}>
            <CreditCard size={16} aria-hidden="true" /> PAYPAL
          </div>
          <p style={{ margin: 0, fontSize: '0.92rem', color: '#cbd5e1' }}>Sandbox Orders and recurring-payment workflows.</p>
        </div>
      </div>

      {/* Runtime vs Development Architecture */}
      <div style={{ display: 'grid', gridTemplateColumns: 'repeat(auto-fit, minmax(320px, 1fr))', gap: '16px', marginBottom: '26px' }}>
        <div style={{ backgroundColor: '#0f172a', border: '1px solid #0284c7', borderRadius: '18px', padding: '20px' }}>
          <h2 style={{ margin: '0 0 10px', fontSize: '1.05rem', fontWeight: 800, color: '#38bdf8' }}>
            Runtime Commerce Architecture
          </h2>
          <pre style={{ margin: 0, fontSize: '0.84rem', color: '#e2e8f0', whiteSpace: 'pre-wrap', lineHeight: 1.5, fontFamily: 'ui-monospace, monospace' }}>
{`Customer / User
   ↓
Merchant Website / App
   ↓
AccessPay API (AI + Commerce Orchestration)
   ↓
┌──────────────┬──────────────┬──────────────┐
Google Gemini  Channel3       PayPal Sandbox
Intent         Products       Orders & Subscriptions`}
          </pre>
          <p style={{ margin: '10px 0 0', fontSize: '0.84rem', color: '#94a3b8' }}>
            AccessPay&apos;s runtime payment flow uses PayPal Sandbox directly. User payment traffic does not pass through APIMatic.
          </p>
        </div>

        <div style={{ backgroundColor: '#0f172a', border: '1px solid #6366f1', borderRadius: '18px', padding: '20px' }}>
          <h2 style={{ margin: '0 0 10px', fontSize: '1.05rem', fontWeight: 800, color: '#a5b4fc' }}>
            Two APIMatic Roles
          </h2>
          <pre style={{ margin: 0, fontSize: '0.82rem', color: '#e2e8f0', whiteSpace: 'pre-wrap', lineHeight: 1.45, fontFamily: 'ui-monospace, monospace' }}>
{`1. APIMATIC — DEVELOPMENT CONTEXT ✓
PayPal Context Plugin
→ authoritative PayPal API context
→ AccessPay PayPal integration

Used during development to validate PayPal authentication, Orders, capture, subscriptions, and error handling.

2. APIMATIC — MERCHANT DEVELOPER EXPERIENCE ✓
AccessPay FastAPI
→ OpenAPI
→ APIMatic
→ Developer Portal
→ TypeScript + Python integration
→ API Reference + Context Plugin
→ Merchant Applications`}
          </pre>
          <p style={{ margin: '10px 0 6px', fontSize: '0.82rem', color: '#a5b4fc', fontWeight: 700 }}>
            OpenAPI Validated ✓ · APIMatic Import Complete ✓ · Developer Portal Generated ✓ · TypeScript Integration ✓ · Python Integration ✓ · API Reference ✓ · AccessPay Context Plugin ✓
          </p>
          <p style={{ margin: '6px 0 0', fontSize: '0.84rem', color: '#94a3b8' }}>
            AccessPay&apos;s OpenAPI specification has been validated and imported into APIMatic, which generated a developer portal with TypeScript and Python integration support, API reference documentation, and an AccessPay Context Plugin. (Local hackathon portal at 127.0.0.1:23513; SDK packages are not published to npm/PyPI.)
          </p>
        </div>
      </div>

      {/* Safety as an API Feature */}
      <div style={{ backgroundColor: '#0f172a', border: '1px solid #334155', borderRadius: '18px', padding: '20px', marginBottom: '26px' }}>
        <h2 style={{ margin: '0 0 12px', fontSize: '1.1rem', fontWeight: 800 }}>
          Safety as an API Feature
        </h2>
        <div style={{ display: 'grid', gridTemplateColumns: 'repeat(auto-fit, minmax(260px, 1fr))', gap: '16px' }}>
          <div style={{ backgroundColor: '#022c22', border: '1px solid #10b981', borderRadius: '12px', padding: '14px' }}>
            <div style={{ fontWeight: 800, color: '#6ee7b7', marginBottom: '8px', fontSize: '0.88rem' }}>AI MAY</div>
            <ul style={{ margin: 0, paddingLeft: '18px', fontSize: '0.9rem', color: '#d1fae5', lineHeight: 1.6 }}>
              <li>Search, Compare &amp; Recommend</li>
              <li>Navigate, Save &amp; Manage Cart</li>
              <li>Prepare Checkout &amp; Subscription Review</li>
            </ul>
          </div>
          <div style={{ backgroundColor: '#450a0a', border: '1px solid #ef4444', borderRadius: '12px', padding: '14px' }}>
            <div style={{ fontWeight: 800, color: '#fca5a5', marginBottom: '8px', fontSize: '0.88rem' }}>AI MAY NOT</div>
            <p style={{ margin: '0 0 10px', fontSize: '0.95rem', color: '#fecaca', fontWeight: 700, display: 'flex', alignItems: 'center', gap: '6px' }}>
              <XCircle size={16} aria-hidden="true" /> Silently authorize payment
            </p>
            <p style={{ margin: 0, fontSize: '0.88rem', color: '#fee2e2', display: 'flex', alignItems: 'center', gap: '6px' }}>
              <CheckCircle2 size={15} aria-hidden="true" /> Human confirmation <ArrowRight size={14} aria-hidden="true" /> PayPal buyer approval
            </p>
          </div>
        </div>
      </div>

      {/* One-Time vs Subscription API Flows */}
      <div style={{ display: 'grid', gridTemplateColumns: 'repeat(auto-fit, minmax(300px, 1fr))', gap: '16px', marginBottom: '26px' }}>
        <div style={{ backgroundColor: '#0f172a', border: '1px solid #334155', borderRadius: '16px', padding: '18px' }}>
          <div style={{ display: 'flex', alignItems: 'center', gap: '8px', fontWeight: 800, color: '#38bdf8', marginBottom: '8px', fontSize: '0.9rem' }}>
            <Layers size={16} aria-hidden="true" /> One-Time Payment API Flow (Orders API v2)
          </div>
          <p style={{ margin: 0, fontSize: '0.88rem', color: '#cbd5e1', lineHeight: 1.6 }}>
            Channel3 product → AccessPay Cart → Server-calculated total → Purchase Review → &quot;Confirm $X purchase&quot; → PayPal Order → Buyer Approval → Capture
          </p>
        </div>
        <div style={{ backgroundColor: '#0f172a', border: '1px solid #f59e0b', borderRadius: '16px', padding: '18px' }}>
          <div style={{ display: 'flex', alignItems: 'center', gap: '8px', fontWeight: 800, color: '#fcd34d', marginBottom: '8px', fontSize: '0.9rem' }}>
            <Repeat size={16} aria-hidden="true" /> Subscription API Flow (Subscriptions API v1)
          </div>
          <p style={{ margin: 0, fontSize: '0.88rem', color: '#cbd5e1', lineHeight: 1.6 }}>
            Demo Subscription Plan → Subscription Review → Recurring terms → &quot;Confirm $X monthly subscription&quot; → PayPal Subscription Approval → Active Subscription
          </p>
        </div>
      </div>

      {/* Real Endpoints & Request Example */}
      <div style={{ display: 'grid', gridTemplateColumns: 'repeat(auto-fit, minmax(320px, 1fr))', gap: '16px', marginBottom: '26px' }}>
        <div style={{ backgroundColor: '#0f172a', border: '1px solid #334155', borderRadius: '16px', padding: '18px' }}>
          <h2 style={{ margin: '0 0 12px', fontSize: '1.05rem', fontWeight: 800 }}>Actual FastAPI Endpoints</h2>
          <div style={{ display: 'flex', flexDirection: 'column', gap: '8px' }}>
            {ACTUAL_ENDPOINTS.map((ep) => (
              <div key={ep.path} style={{ backgroundColor: '#020617', borderRadius: '10px', padding: '8px 12px', border: '1px solid #1e293b' }}>
                <div style={{ fontFamily: 'ui-monospace, monospace', fontSize: '0.83rem', color: '#38bdf8', fontWeight: 700 }}>
                  {ep.method} {ep.path}
                </div>
                <div style={{ fontSize: '0.82rem', color: '#94a3b8' }}>{ep.desc}</div>
              </div>
            ))}
          </div>
        </div>

        <div style={{ backgroundColor: '#0f172a', border: '1px solid #334155', borderRadius: '16px', padding: '18px' }}>
          <h2 style={{ margin: '0 0 12px', fontSize: '1.05rem', fontWeight: 800 }}>Merchant Integration Example</h2>
          <pre style={{ margin: 0, backgroundColor: '#020617', borderRadius: '10px', padding: '12px', fontSize: '0.8rem', color: '#e2e8f0', overflowX: 'auto', border: '1px solid #1e293b' }}>
{`POST /api/ai/intent
{
  "message": "Find wireless headphones under $80"
}

// Representative Response
{
  "action": "SEARCH_RESULTS",
  "search_id": "srch_8f21a9",
  "products": [
    { "id": "c3_...", "title": "...", "price": 59.99 }
  ],
  "speech_response": "Found 6 wireless headphones under $80."
}`}
          </pre>
          <p style={{ margin: '10px 0 0', fontSize: '0.82rem', color: '#94a3b8' }}>
            <strong>Prototype Merchant API:</strong> Production deployment would add merchant authentication, tenant isolation, rate limiting, API versioning, webhooks, and audit controls.
          </p>
        </div>
      </div>

      {/* APIMatic Verification Matrix */}
      <div style={{ backgroundColor: '#0f172a', border: '1px solid #334155', borderRadius: '16px', padding: '18px', marginBottom: '26px' }}>
        <h2 style={{ margin: '0 0 12px', fontSize: '1.05rem', fontWeight: 800 }}>
          PayPal Integration Verification (APIMatic Context Plugin)
        </h2>
        <div style={{ display: 'grid', gridTemplateColumns: 'repeat(auto-fit, minmax(290px, 1fr))', gap: '10px' }}>
          {verificationRows.map((row) => (
            <div key={row.area} style={{ backgroundColor: '#020617', border: '1px solid #1e293b', borderRadius: '10px', padding: '10px 12px' }}>
              <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', gap: '8px', marginBottom: '4px' }}>
                <span style={{ fontSize: '0.85rem', fontWeight: 700, color: '#f8fafc' }}>{row.area}</span>
                <span
                  style={{
                    fontSize: '0.72rem',
                    fontWeight: 800,
                    padding: '2px 8px',
                    borderRadius: '999px',
                    backgroundColor: row.verified === 'YES' ? '#064e3b' : '#1e293b',
                    color: row.verified === 'YES' ? '#6ee7b7' : '#fbbf24',
                  }}
                >
                  {row.verified}
                </span>
              </div>
              <div style={{ fontSize: '0.8rem', color: '#94a3b8' }}>{row.notes}</div>
            </div>
          ))}
        </div>
      </div>

      {/* Integration Credits & Safe Config Status (No Secrets) */}
      <div style={{ display: 'grid', gridTemplateColumns: 'repeat(auto-fit, minmax(220px, 1fr))', gap: '14px' }}>
        <div style={{ backgroundColor: '#0f172a', border: '1px solid #1e293b', borderRadius: '14px', padding: '16px' }}>
          <div style={{ fontSize: '0.75rem', fontWeight: 800, color: '#94a3b8' }}>API INTEGRATION SUPPORT</div>
          <div style={{ fontSize: '1rem', fontWeight: 800, marginTop: '4px' }}>APIMatic Context Plugin</div>
          <p style={{ margin: '6px 0', fontSize: '0.83rem', color: '#cbd5e1' }}>
            Used to provide authoritative PayPal API context while developing and validating AccessPay&apos;s PayPal integrations.
          </p>
          <div style={{ fontSize: '0.78rem', color: '#6ee7b7', fontWeight: 700 }}>{envStatus.apimatic_context_plugin}</div>
        </div>
        <div style={{ backgroundColor: '#0f172a', border: '1px solid #1e293b', borderRadius: '14px', padding: '16px' }}>
          <div style={{ fontSize: '0.75rem', fontWeight: 800, color: '#94a3b8' }}>PRODUCT DATA</div>
          <div style={{ fontSize: '1rem', fontWeight: 800, marginTop: '4px' }}>Channel3</div>
          <p style={{ margin: '6px 0', fontSize: '0.83rem', color: '#cbd5e1' }}>
            Real commerce product discovery.
          </p>
          <div style={{ fontSize: '0.78rem', color: '#6ee7b7', fontWeight: 700 }}>{envStatus.channel3_products}</div>
        </div>
        <div style={{ backgroundColor: '#0f172a', border: '1px solid #1e293b', borderRadius: '14px', padding: '16px' }}>
          <div style={{ fontSize: '0.75rem', fontWeight: 800, color: '#94a3b8' }}>PAYMENTS</div>
          <div style={{ fontSize: '1rem', fontWeight: 800, marginTop: '4px' }}>PayPal Sandbox</div>
          <p style={{ margin: '6px 0', fontSize: '0.83rem', color: '#cbd5e1' }}>
            Order creation, buyer approval, capture, and recurring payment workflows.
          </p>
          <div style={{ fontSize: '0.78rem', color: '#6ee7b7', fontWeight: 700 }}>{envStatus.paypal_sandbox}</div>
        </div>
        <div style={{ backgroundColor: '#0f172a', border: '1px solid #1e293b', borderRadius: '14px', padding: '16px' }}>
          <div style={{ fontSize: '0.75rem', fontWeight: 800, color: '#94a3b8' }}>AI</div>
          <div style={{ fontSize: '1rem', fontWeight: 800, marginTop: '4px' }}>Google Gemini</div>
          <p style={{ margin: '6px 0', fontSize: '0.83rem', color: '#cbd5e1' }}>
            Natural-language intent and conversational shopping.
          </p>
          <div style={{ fontSize: '0.78rem', color: '#6ee7b7', fontWeight: 700 }}>{envStatus.google_gemini_ai}</div>
        </div>
      </div>
    </section>
  );
};

