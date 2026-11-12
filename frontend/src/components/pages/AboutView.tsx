import React from 'react';
import {
  Mic,
  Search,
  MessageSquare,
  ArrowLeftRight,
  Bookmark,
  History,
  ShoppingCart,
  Receipt,
  Repeat,
  ShieldCheck,
  Calendar,
  Compass,
  Keyboard,
  User,
  ArrowRight,
  CheckCircle2,
  XCircle,
  ExternalLink,
  Lock,
  Layers,
  Building2,
  BookOpen,
  Cpu,
  ShoppingBag,
  ArrowDown,
  Sparkles,
  HelpCircle,
  Check,
  Code2,
} from 'lucide-react';

interface AboutViewProps {
  onStartShopping: () => void;
  onNavigateDevelopers: () => void;
}

export const AboutView: React.FC<AboutViewProps> = ({
  onStartShopping,
  onNavigateDevelopers,
}) => {
  return (
    <article
      aria-label="About AccessPay AI"
      data-testid="about-page"
      style={{
        maxWidth: '1080px',
        margin: '0 auto',
        padding: '24px 16px 80px',
        color: '#f8fafc',
        lineHeight: 1.6,
      }}
    >
      {/* 4. HERO SECTION */}
      <header
        style={{
          textAlign: 'center',
          padding: '40px 16px 32px',
          marginBottom: '32px',
          background: 'linear-gradient(180deg, rgba(2, 132, 199, 0.12) 0%, rgba(10, 15, 29, 0) 100%)',
          borderRadius: '24px',
          border: '1px solid rgba(56, 189, 248, 0.2)',
        }}
      >
        <span
          style={{
            display: 'inline-flex',
            alignItems: 'center',
            gap: '6px',
            fontSize: '0.8rem',
            fontWeight: 800,
            letterSpacing: '0.06em',
            textTransform: 'uppercase',
            color: '#38bdf8',
            backgroundColor: '#0c4a6e',
            padding: '4px 14px',
            borderRadius: '999px',
            marginBottom: '16px',
          }}
        >
          <Sparkles size={14} aria-hidden="true" />
          About AccessPay AI
        </span>

        <h1
          style={{
            fontSize: 'clamp(1.85rem, 4vw, 2.75rem)',
            fontWeight: 900,
            letterSpacing: '-0.03em',
            margin: '0 auto 16px',
            maxWidth: '840px',
            lineHeight: 1.2,
          }}
        >
          AccessPay makes online shopping easier to control by voice.
        </h1>

        <p
          style={{
            fontSize: 'clamp(1.05rem, 2vw, 1.25rem)',
            color: '#cbd5e1',
            margin: '0 auto 14px',
            maxWidth: '780px',
            fontWeight: 500,
          }}
        >
          Find products, compare choices, save items, manage your cart, review purchases, and pay with fewer clicks and taps.
        </p>

        <p
          style={{
            fontSize: '0.98rem',
            color: '#94a3b8',
            margin: '0 auto 28px',
            maxWidth: '720px',
          }}
        >
          Designed with people with limited mobility in mind, while remaining useful for anyone who prefers a conversational shopping experience.
        </p>

        {/* 5. HERO VISUAL: PERSON -> VOICE -> ACCESSPAY -> SHOPPING */}
        <div
          role="region"
          aria-label="Core interaction flow"
          style={{
            display: 'flex',
            alignItems: 'center',
            justifyContent: 'center',
            gap: '12px',
            flexWrap: 'wrap',
            margin: '24px auto 0',
            maxWidth: '740px',
            padding: '16px',
            backgroundColor: '#0f172a',
            border: '1px solid #1e293b',
            borderRadius: '16px',
          }}
        >
          <div style={{ display: 'flex', alignItems: 'center', gap: '8px', padding: '8px 14px', backgroundColor: '#020617', borderRadius: '12px', border: '1px solid #334155' }}>
            <User size={20} color="#38bdf8" aria-hidden="true" />
            <span style={{ fontWeight: 700, fontSize: '0.9rem' }}>Person</span>
          </div>

          <ArrowRight size={18} color="#64748b" aria-hidden="true" />

          <div style={{ display: 'flex', alignItems: 'center', gap: '8px', padding: '8px 14px', backgroundColor: '#020617', borderRadius: '12px', border: '1px solid #334155' }}>
            <Mic size={20} color="#38bdf8" aria-hidden="true" />
            <span style={{ fontWeight: 700, fontSize: '0.9rem' }}>Voice</span>
          </div>

          <ArrowRight size={18} color="#64748b" aria-hidden="true" />

          <div style={{ display: 'flex', alignItems: 'center', gap: '8px', padding: '8px 14px', backgroundColor: '#0c4a6e', borderRadius: '12px', border: '1px solid #0284c7' }}>
            <ShieldCheck size={20} color="#ffffff" aria-hidden="true" />
            <span style={{ fontWeight: 800, fontSize: '0.9rem', color: '#ffffff' }}>AccessPay AI</span>
          </div>

          <ArrowRight size={18} color="#64748b" aria-hidden="true" />

          <div style={{ display: 'flex', alignItems: 'center', gap: '8px', padding: '8px 14px', backgroundColor: '#020617', borderRadius: '12px', border: '1px solid #334155' }}>
            <ShoppingBag size={20} color="#10b981" aria-hidden="true" />
            <span style={{ fontWeight: 700, fontSize: '0.9rem' }}>Shopping</span>
          </div>
        </div>
      </header>

      {/* 6. WHY ACCESSPAY & 7. VISUAL COMPARISON */}
      <section
        aria-labelledby="why-accesspay-heading"
        style={{
          backgroundColor: '#0f172a',
          border: '1px solid #1e293b',
          borderRadius: '20px',
          padding: '32px 24px',
          marginBottom: '36px',
        }}
      >
        <div style={{ display: 'grid', gridTemplateColumns: 'repeat(auto-fit, minmax(300px, 1fr))', gap: '28px', alignItems: 'center' }}>
          <div>
            <h2 id="why-accesspay-heading" style={{ fontSize: '1.6rem', fontWeight: 900, margin: '0 0 16px', letterSpacing: '-0.02em' }}>
              Why AccessPay?
            </h2>
            <p style={{ margin: '0 0 12px', color: '#cbd5e1', fontSize: '0.96rem' }}>
              Online shopping can involve many small actions: typing searches, opening products, comparing options, navigating pages, changing quantities, and moving through checkout.
            </p>
            <p style={{ margin: '0 0 12px', color: '#cbd5e1', fontSize: '0.96rem' }}>
              For people with muscular dystrophy, limited mobility, or other disabilities, repeated physical interaction can make those steps more difficult.
            </p>
            <p style={{ margin: 0, color: '#38bdf8', fontSize: '1rem', fontWeight: 700 }}>
              AccessPay allows more of the shopping journey to happen through conversation.
            </p>
          </div>

          {/* Visual Comparison */}
          <div style={{ display: 'flex', flexDirection: 'column', gap: '14px' }}>
            {/* Traditional */}
            <div style={{ backgroundColor: '#020617', border: '1px solid #334155', borderRadius: '14px', padding: '16px' }}>
              <div style={{ fontSize: '0.78rem', fontWeight: 800, textTransform: 'uppercase', letterSpacing: '0.05em', color: '#94a3b8', marginBottom: '8px' }}>
                Traditional Shopping (many repetitive steps)
              </div>
              <div style={{ display: 'flex', flexWrap: 'wrap', gap: '6px', alignItems: 'center', fontSize: '0.82rem', color: '#94a3b8' }}>
                <span>Type</span> &rarr; <span>Click</span> &rarr; <span>Open</span> &rarr; <span>Compare</span> &rarr; <span>Back</span> &rarr; <span>Select</span> &rarr; <span>Cart</span> &rarr; <span>Navigate</span> &rarr; <span>Checkout</span>
              </div>
            </div>

            {/* AccessPay */}
            <div style={{ backgroundColor: '#082f49', border: '1px solid #0284c7', borderRadius: '14px', padding: '16px' }}>
              <div style={{ fontSize: '0.78rem', fontWeight: 800, textTransform: 'uppercase', letterSpacing: '0.05em', color: '#38bdf8', marginBottom: '8px' }}>
                AccessPay (fewer repeated interactions)
              </div>
              <div style={{ display: 'flex', flexWrap: 'wrap', gap: '6px', alignItems: 'center', fontSize: '0.88rem', fontWeight: 700, color: '#f0f9ff' }}>
                <span>Speak</span> &rarr; <span>Find</span> &rarr; <span>Compare</span> &rarr; <span>Choose</span> &rarr; <span>Review</span> &rarr; <span style={{ color: '#38bdf8' }}>Confirm</span>
              </div>
            </div>
            <p style={{ margin: 0, fontSize: '0.8rem', color: '#64748b' }}>
              * AccessPay does not eliminate every physical touchpoint, but significantly reduces repeated physical friction.
            </p>
          </div>
        </div>
      </section>

      {/* 9. VISUAL SHOPPING JOURNEY */}
      <section
        aria-labelledby="journey-heading"
        style={{
          backgroundColor: '#0a0f1d',
          border: '1px solid #1e293b',
          borderRadius: '20px',
          padding: '28px 20px',
          marginBottom: '36px',
        }}
      >
        <h2 id="journey-heading" style={{ fontSize: '1.4rem', fontWeight: 900, margin: '0 0 6px', textAlign: 'center' }}>
          From an idea to a purchase
        </h2>
        <p style={{ textAlign: 'center', color: '#94a3b8', margin: '0 0 24px', fontSize: '0.94rem' }}>
          AccessPay stays with the user throughout the shopping journey.
        </p>

        <div
          style={{
            display: 'grid',
            gridTemplateColumns: 'repeat(auto-fit, minmax(110px, 1fr))',
            gap: '10px',
          }}
        >
          {[
            { icon: Mic, step: '1. SPEAK', desc: 'Say what you want', color: '#38bdf8' },
            { icon: Search, step: '2. FIND', desc: 'Real products appear', color: '#38bdf8' },
            { icon: ArrowLeftRight, step: '3. COMPARE', desc: 'Side-by-side specs', color: '#38bdf8' },
            { icon: Bookmark, step: '4. SAVE', desc: 'Keep for later', color: '#a855f7' },
            { icon: ShoppingCart, step: '5. CART', desc: 'Manage basket', color: '#a855f7' },
            { icon: Receipt, step: '6. REVIEW', desc: 'Itemized totals', color: '#f59e0b' },
            { icon: ShieldCheck, step: '7. CONFIRM', desc: 'Exact-amount check', color: '#10b981' },
            { icon: Lock, step: '8. PAY', desc: 'PayPal Sandbox', color: '#10b981' },
          ].map((item, idx) => (
            <div
              key={idx}
              style={{
                backgroundColor: '#0f172a',
                border: '1px solid #1e293b',
                borderRadius: '14px',
                padding: '14px 10px',
                textAlign: 'center',
                display: 'flex',
                flexDirection: 'column',
                alignItems: 'center',
                gap: '6px',
              }}
            >
              <item.icon size={22} color={item.color} aria-hidden="true" />
              <div style={{ fontSize: '0.78rem', fontWeight: 800, color: '#f8fafc', letterSpacing: '0.04em' }}>{item.step}</div>
              <div style={{ fontSize: '0.72rem', color: '#94a3b8' }}>{item.desc}</div>
            </div>
          ))}
        </div>
      </section>

      {/* 8. COMPLETE CAPABILITY OVERVIEW (14 CARDS) */}
      <section aria-labelledby="capabilities-heading" style={{ marginBottom: '40px' }}>
        <div style={{ textAlign: 'center', marginBottom: '24px' }}>
          <h2 id="capabilities-heading" style={{ fontSize: '1.6rem', fontWeight: 900, margin: '0 0 8px' }}>
            What can AccessPay do?
          </h2>
          <p style={{ color: '#94a3b8', margin: 0, fontSize: '0.95rem' }}>
            Every major capability can be controlled by voice or direct interaction.
          </p>
        </div>

        <div
          style={{
            display: 'grid',
            gridTemplateColumns: 'repeat(auto-fit, minmax(240px, 1fr))',
            gap: '14px',
          }}
        >
          {/* Card 1: Voice Product Search */}
          <div style={{ backgroundColor: '#0f172a', border: '1px solid #1e293b', borderRadius: '16px', padding: '18px' }}>
            <div style={{ display: 'flex', alignItems: 'center', gap: '8px', color: '#38bdf8', marginBottom: '8px' }}>
              <Mic size={18} aria-hidden="true" />
              <Search size={16} aria-hidden="true" />
              <h3 style={{ fontSize: '0.98rem', fontWeight: 800, margin: 0, color: '#f8fafc' }}>Find products naturally</h3>
            </div>
            <p style={{ margin: '0 0 8px', fontSize: '0.86rem', color: '#cbd5e1' }}>
              Describe what you&apos;re looking for in your own words.
            </p>
            <div style={{ fontSize: '0.8rem', color: '#38bdf8', backgroundColor: '#020617', padding: '6px 10px', borderRadius: '8px', border: '1px solid #1e293b' }}>
              &ldquo;Find wireless headphones under $80.&rdquo;
            </div>
          </div>

          {/* Card 2: Conversational Follow-ups */}
          <div style={{ backgroundColor: '#0f172a', border: '1px solid #1e293b', borderRadius: '16px', padding: '18px' }}>
            <div style={{ display: 'flex', alignItems: 'center', gap: '8px', color: '#38bdf8', marginBottom: '8px' }}>
              <MessageSquare size={18} aria-hidden="true" />
              <h3 style={{ fontSize: '0.98rem', fontWeight: 800, margin: 0, color: '#f8fafc' }}>Keep the conversation going</h3>
            </div>
            <p style={{ margin: '0 0 8px', fontSize: '0.86rem', color: '#cbd5e1' }}>
              Ask follow-up questions without repeating your original search.
            </p>
            <div style={{ fontSize: '0.8rem', color: '#38bdf8', backgroundColor: '#020617', padding: '6px 10px', borderRadius: '8px', border: '1px solid #1e293b' }}>
              &ldquo;Which one is cheaper?&rdquo; &bull; &ldquo;Tell me about the second one.&rdquo;
            </div>
          </div>

          {/* Card 3: Product Comparison */}
          <div style={{ backgroundColor: '#0f172a', border: '1px solid #1e293b', borderRadius: '16px', padding: '18px' }}>
            <div style={{ display: 'flex', alignItems: 'center', gap: '8px', color: '#38bdf8', marginBottom: '8px' }}>
              <ArrowLeftRight size={18} aria-hidden="true" />
              <h3 style={{ fontSize: '0.98rem', fontWeight: 800, margin: 0, color: '#f8fafc' }}>Compare choices</h3>
            </div>
            <p style={{ margin: '0 0 8px', fontSize: '0.86rem', color: '#cbd5e1' }}>
              Compare products currently on the screen side-by-side.
            </p>
            <div style={{ fontSize: '0.8rem', color: '#38bdf8', backgroundColor: '#020617', padding: '6px 10px', borderRadius: '8px', border: '1px solid #1e293b' }}>
              &ldquo;Compare the first two.&rdquo;
            </div>
          </div>

          {/* Card 4: Relevant Alternatives */}
          <div style={{ backgroundColor: '#0f172a', border: '1px solid #1e293b', borderRadius: '16px', padding: '18px' }}>
            <div style={{ display: 'flex', alignItems: 'center', gap: '8px', color: '#38bdf8', marginBottom: '8px' }}>
              <Search size={18} aria-hidden="true" />
              <h3 style={{ fontSize: '0.98rem', fontWeight: 800, margin: 0, color: '#f8fafc' }}>Find alternatives</h3>
            </div>
            <p style={{ margin: '0 0 8px', fontSize: '0.86rem', color: '#cbd5e1' }}>
              Ask for something cheaper or refine what you&apos;re looking for while keeping the current shopping context.
            </p>
            <div style={{ fontSize: '0.8rem', color: '#38bdf8', backgroundColor: '#020617', padding: '6px 10px', borderRadius: '8px', border: '1px solid #1e293b' }}>
              &ldquo;Show me something cheaper.&rdquo;
            </div>
          </div>

          {/* Card 5: Saved Items */}
          <div style={{ backgroundColor: '#0f172a', border: '1px solid #1e293b', borderRadius: '16px', padding: '18px' }}>
            <div style={{ display: 'flex', alignItems: 'center', gap: '8px', color: '#a855f7', marginBottom: '8px' }}>
              <Bookmark size={18} aria-hidden="true" />
              <h3 style={{ fontSize: '0.98rem', fontWeight: 800, margin: 0, color: '#f8fafc' }}>Save products for later</h3>
            </div>
            <p style={{ margin: '0 0 8px', fontSize: '0.86rem', color: '#cbd5e1' }}>
              Keep products you may want to revisit without putting them in your cart.
            </p>
            <div style={{ fontSize: '0.8rem', color: '#c084fc', backgroundColor: '#020617', padding: '6px 10px', borderRadius: '8px', border: '1px solid #1e293b' }}>
              &ldquo;Save the first one for later.&rdquo;
            </div>
          </div>

          {/* Card 6: Recent Searches */}
          <div style={{ backgroundColor: '#0f172a', border: '1px solid #1e293b', borderRadius: '16px', padding: '18px' }}>
            <div style={{ display: 'flex', alignItems: 'center', gap: '8px', color: '#a855f7', marginBottom: '8px' }}>
              <History size={18} aria-hidden="true" />
              <h3 style={{ fontSize: '0.98rem', fontWeight: 800, margin: 0, color: '#f8fafc' }}>Return to recent searches</h3>
            </div>
            <p style={{ margin: '0 0 8px', fontSize: '0.86rem', color: '#cbd5e1' }}>
              Quickly revisit something you searched for earlier with a single click or phrase.
            </p>
            <div style={{ fontSize: '0.8rem', color: '#c084fc', backgroundColor: '#020617', padding: '6px 10px', borderRadius: '8px', border: '1px solid #1e293b' }}>
              &ldquo;Search again for wireless headphones.&rdquo;
            </div>
          </div>

          {/* Card 7: Saved Searches */}
          <div style={{ backgroundColor: '#0f172a', border: '1px solid #1e293b', borderRadius: '16px', padding: '18px' }}>
            <div style={{ display: 'flex', alignItems: 'center', gap: '8px', color: '#a855f7', marginBottom: '8px' }}>
              <Bookmark size={16} aria-hidden="true" />
              <Search size={16} aria-hidden="true" />
              <h3 style={{ fontSize: '0.98rem', fontWeight: 800, margin: 0, color: '#f8fafc' }}>Keep important searches</h3>
            </div>
            <p style={{ margin: '0 0 8px', fontSize: '0.86rem', color: '#cbd5e1' }}>
              Save a search intentionally and run it again later using current product information.
            </p>
            <div style={{ fontSize: '0.8rem', color: '#c084fc', backgroundColor: '#020617', padding: '6px 10px', borderRadius: '8px', border: '1px solid #1e293b' }}>
              &ldquo;Save this search.&rdquo;
            </div>
          </div>

          {/* Card 8: Cart */}
          <div style={{ backgroundColor: '#0f172a', border: '1px solid #1e293b', borderRadius: '16px', padding: '18px' }}>
            <div style={{ display: 'flex', alignItems: 'center', gap: '8px', color: '#38bdf8', marginBottom: '8px' }}>
              <ShoppingCart size={18} aria-hidden="true" />
              <h3 style={{ fontSize: '0.98rem', fontWeight: 800, margin: 0, color: '#f8fafc' }}>Manage your cart</h3>
            </div>
            <p style={{ margin: '0 0 8px', fontSize: '0.86rem', color: '#cbd5e1' }}>
              Add products, add several items, change quantities, remove items, and ask for your total.
            </p>
            <div style={{ fontSize: '0.8rem', color: '#38bdf8', backgroundColor: '#020617', padding: '6px 10px', borderRadius: '8px', border: '1px solid #1e293b' }}>
              &ldquo;Add to cart&rdquo; &bull; &ldquo;What&apos;s my total?&rdquo;
            </div>
          </div>

          {/* Card 9: Orders */}
          <div style={{ backgroundColor: '#0f172a', border: '1px solid #1e293b', borderRadius: '16px', padding: '18px' }}>
            <div style={{ display: 'flex', alignItems: 'center', gap: '8px', color: '#fbbf24', marginBottom: '8px' }}>
              <Receipt size={18} aria-hidden="true" />
              <h3 style={{ fontSize: '0.98rem', fontWeight: 800, margin: 0, color: '#f8fafc' }}>Review previous purchases</h3>
            </div>
            <p style={{ margin: '0 0 8px', fontSize: '0.86rem', color: '#cbd5e1' }}>
              Open past orders, inspect what you bought, tracking status, and prepare a reorder.
            </p>
            <div style={{ fontSize: '0.8rem', color: '#fde68a', backgroundColor: '#020617', padding: '6px 10px', borderRadius: '8px', border: '1px solid #1e293b' }}>
              &ldquo;Show my orders.&rdquo;
            </div>
          </div>

          {/* Card 10: Reorder */}
          <div style={{ backgroundColor: '#0f172a', border: '1px solid #1e293b', borderRadius: '16px', padding: '18px' }}>
            <div style={{ display: 'flex', alignItems: 'center', gap: '8px', color: '#fbbf24', marginBottom: '8px' }}>
              <Repeat size={18} aria-hidden="true" />
              <h3 style={{ fontSize: '0.98rem', fontWeight: 800, margin: 0, color: '#f8fafc' }}>Buy again safely</h3>
            </div>
            <p style={{ margin: '0 0 8px', fontSize: '0.86rem', color: '#cbd5e1' }}>
              Prepare a previous purchase again without reusing the old payment authorization.
            </p>
            <div style={{ fontSize: '0.8rem', color: '#fde68a', backgroundColor: '#020617', padding: '6px 10px', borderRadius: '8px', border: '1px solid #1e293b' }}>
              &ldquo;Reorder last purchase.&rdquo;
            </div>
          </div>

          {/* Card 11: One-Time Payments */}
          <div style={{ backgroundColor: '#0f172a', border: '1px solid #1e293b', borderRadius: '16px', padding: '18px' }}>
            <div style={{ display: 'flex', alignItems: 'center', gap: '8px', color: '#10b981', marginBottom: '8px' }}>
              <ShieldCheck size={18} aria-hidden="true" />
              <h3 style={{ fontSize: '0.98rem', fontWeight: 800, margin: 0, color: '#f8fafc' }}>Confirm before paying</h3>
            </div>
            <p style={{ margin: '0 0 8px', fontSize: '0.86rem', color: '#cbd5e1' }}>
              Review the complete purchase and explicitly confirm the exact amount before PayPal.
            </p>
            <div style={{ fontSize: '0.8rem', color: '#6ee7b7', backgroundColor: '#020617', padding: '6px 10px', borderRadius: '8px', border: '1px solid #1e293b' }}>
              &ldquo;Confirm $53.99 purchase.&rdquo;
            </div>
          </div>

          {/* Card 12: Subscriptions */}
          <div style={{ backgroundColor: '#0f172a', border: '1px solid #1e293b', borderRadius: '16px', padding: '18px' }}>
            <div style={{ display: 'flex', alignItems: 'center', gap: '8px', color: '#10b981', marginBottom: '8px' }}>
              <Repeat size={16} aria-hidden="true" />
              <Calendar size={16} aria-hidden="true" />
              <h3 style={{ fontSize: '0.98rem', fontWeight: 800, margin: 0, color: '#f8fafc' }}>Understand recurring payments</h3>
            </div>
            <p style={{ margin: '0 0 8px', fontSize: '0.86rem', color: '#cbd5e1' }}>
              Review the recurring amount and billing frequency before agreeing to a subscription.
            </p>
            <div style={{ fontSize: '0.8rem', color: '#6ee7b7', backgroundColor: '#020617', padding: '6px 10px', borderRadius: '8px', border: '1px solid #1e293b' }}>
              &ldquo;Confirm $19.99 monthly subscription.&rdquo;
            </div>
          </div>

          {/* Card 13: Voice Navigation */}
          <div style={{ backgroundColor: '#0f172a', border: '1px solid #1e293b', borderRadius: '16px', padding: '18px' }}>
            <div style={{ display: 'flex', alignItems: 'center', gap: '8px', color: '#38bdf8', marginBottom: '8px' }}>
              <Compass size={18} aria-hidden="true" />
              <h3 style={{ fontSize: '0.98rem', fontWeight: 800, margin: 0, color: '#f8fafc' }}>Navigate by voice</h3>
            </div>
            <p style={{ margin: '0 0 8px', fontSize: '0.86rem', color: '#cbd5e1' }}>
              Move between Shop, Saved, Cart, Orders, and other supported areas using voice commands.
            </p>
            <div style={{ fontSize: '0.8rem', color: '#38bdf8', backgroundColor: '#020617', padding: '6px 10px', borderRadius: '8px', border: '1px solid #1e293b' }}>
              &ldquo;Go to Cart&rdquo; &bull; &ldquo;Open Orders&rdquo; &bull; &ldquo;Go Home&rdquo;
            </div>
          </div>

          {/* Card 14: Typed Search Suggestions */}
          <div style={{ backgroundColor: '#0f172a', border: '1px solid #1e293b', borderRadius: '16px', padding: '18px' }}>
            <div style={{ display: 'flex', alignItems: 'center', gap: '8px', color: '#94a3b8', marginBottom: '8px' }}>
              <Keyboard size={18} aria-hidden="true" />
              <h3 style={{ fontSize: '0.98rem', fontWeight: 800, margin: 0, color: '#f8fafc' }}>Type when you want to</h3>
            </div>
            <p style={{ margin: '0 0 8px', fontSize: '0.86rem', color: '#cbd5e1' }}>
              Start typing a product request and choose from suggested searches. AccessPay is voice-first, not voice-only.
            </p>
            <div style={{ fontSize: '0.8rem', color: '#cbd5e1', backgroundColor: '#020617', padding: '6px 10px', borderRadius: '8px', border: '1px solid #1e293b' }}>
              Type: &ldquo;water b...&rdquo; &rarr; click suggestion
            </div>
          </div>
        </div>
      </section>

      {/* 10. HOW CONVERSATION WORKS & 11. AI + PRODUCT DATA */}
      <section
        style={{
          display: 'grid',
          gridTemplateColumns: 'repeat(auto-fit, minmax(320px, 1fr))',
          gap: '20px',
          marginBottom: '36px',
        }}
      >
        {/* Conversation Context */}
        <div
          style={{
            backgroundColor: '#0f172a',
            border: '1px solid #1e293b',
            borderRadius: '20px',
            padding: '24px',
          }}
        >
          <div style={{ display: 'flex', alignItems: 'center', gap: '8px', color: '#38bdf8', marginBottom: '12px' }}>
            <MessageSquare size={20} aria-hidden="true" />
            <h2 style={{ fontSize: '1.15rem', fontWeight: 800, margin: 0, color: '#f8fafc' }}>
              AccessPay remembers what you&apos;re talking about
            </h2>
          </div>
          <p style={{ margin: '0 0 16px', color: '#94a3b8', fontSize: '0.9rem' }}>
            You don&apos;t have to repeat the original search every time. AccessPay keeps track of the current shopping context.
          </p>

          {/* Visual Dialogue */}
          <div style={{ display: 'flex', flexDirection: 'column', gap: '10px' }}>
            <div style={{ alignSelf: 'flex-start', maxWidth: '85%', backgroundColor: '#1e293b', padding: '8px 14px', borderRadius: '12px', fontSize: '0.86rem' }}>
              <span style={{ fontSize: '0.72rem', color: '#38bdf8', fontWeight: 700, display: 'block' }}>USER</span>
              &ldquo;Find wireless headphones under $80.&rdquo;
            </div>
            <div style={{ alignSelf: 'flex-end', maxWidth: '85%', backgroundColor: '#0c4a6e', border: '1px solid #0284c7', padding: '8px 14px', borderRadius: '12px', fontSize: '0.86rem' }}>
              <span style={{ fontSize: '0.72rem', color: '#7dd3fc', fontWeight: 700, display: 'block' }}>ACCESSPAY</span>
              Displays candidate headphones with prices and merchants.
            </div>
            <div style={{ alignSelf: 'flex-start', maxWidth: '85%', backgroundColor: '#1e293b', padding: '8px 14px', borderRadius: '12px', fontSize: '0.86rem' }}>
              <span style={{ fontSize: '0.72rem', color: '#38bdf8', fontWeight: 700, display: 'block' }}>USER</span>
              &ldquo;Compare the first two.&rdquo;
            </div>
            <div style={{ alignSelf: 'flex-start', maxWidth: '85%', backgroundColor: '#1e293b', padding: '8px 14px', borderRadius: '12px', fontSize: '0.86rem' }}>
              <span style={{ fontSize: '0.72rem', color: '#38bdf8', fontWeight: 700, display: 'block' }}>USER</span>
              &ldquo;Which one is cheaper?&rdquo;
            </div>
            <div style={{ alignSelf: 'flex-start', maxWidth: '85%', backgroundColor: '#1e293b', padding: '8px 14px', borderRadius: '12px', fontSize: '0.86rem' }}>
              <span style={{ fontSize: '0.72rem', color: '#38bdf8', fontWeight: 700, display: 'block' }}>USER</span>
              &ldquo;Save the second one.&rdquo;
            </div>
          </div>
        </div>

        {/* AI + Grounded Product Data */}
        <div
          style={{
            backgroundColor: '#0f172a',
            border: '1px solid #1e293b',
            borderRadius: '20px',
            padding: '24px',
          }}
        >
          <div style={{ display: 'flex', alignItems: 'center', gap: '8px', color: '#10b981', marginBottom: '12px' }}>
            <Cpu size={20} aria-hidden="true" />
            <h2 style={{ fontSize: '1.15rem', fontWeight: 800, margin: 0, color: '#f8fafc' }}>
              AI understands. Product data stays grounded.
            </h2>
          </div>
          <p style={{ margin: '0 0 16px', color: '#94a3b8', fontSize: '0.9rem' }}>
            Gemini helps understand natural-language requests. Channel3 provides real commerce product information such as products, merchants, images, and prices. <strong>AI does not invent the product prices.</strong>
          </p>

          {/* Split Visual */}
          <div style={{ display: 'flex', flexDirection: 'column', gap: '12px' }}>
            <div style={{ backgroundColor: '#020617', border: '1px solid #1e293b', borderRadius: '12px', padding: '12px' }}>
              <div style={{ fontWeight: 800, color: '#38bdf8', fontSize: '0.86rem' }}>GOOGLE GEMINI</div>
              <div style={{ fontSize: '0.82rem', color: '#cbd5e1' }}>Understands: &ldquo;What does the user mean?&rdquo;</div>
            </div>

            <div style={{ backgroundColor: '#020617', border: '1px solid #1e293b', borderRadius: '12px', padding: '12px' }}>
              <div style={{ fontWeight: 800, color: '#34d399', fontSize: '0.86rem' }}>CHANNEL3</div>
              <div style={{ fontSize: '0.82rem', color: '#cbd5e1' }}>Provides: &ldquo;What products are actually available?&rdquo;</div>
            </div>

            <div style={{ backgroundColor: '#0c4a6e', border: '1px solid #0284c7', borderRadius: '12px', padding: '12px' }}>
              <div style={{ fontWeight: 800, color: '#ffffff', fontSize: '0.86rem' }}>ACCESSPAY</div>
              <div style={{ fontSize: '0.82rem', color: '#e0f2fe' }}>Connects the conversation to the shopping experience.</div>
            </div>
          </div>
        </div>
      </section>

      {/* 12. SAVED / RECENT / CART DISTINCTION */}
      <section
        style={{
          backgroundColor: '#0a0f1d',
          border: '1px solid #1e293b',
          borderRadius: '20px',
          padding: '28px 20px',
          marginBottom: '36px',
        }}
      >
        <h2 style={{ fontSize: '1.35rem', fontWeight: 900, margin: '0 0 16px', textAlign: 'center' }}>
          Understanding Recent, Saved, and Cart
        </h2>

        <div
          style={{
            display: 'grid',
            gridTemplateColumns: 'repeat(auto-fit, minmax(220px, 1fr))',
            gap: '14px',
          }}
        >
          <div style={{ backgroundColor: '#0f172a', border: '1px solid #334155', borderRadius: '14px', padding: '16px' }}>
            <div style={{ display: 'flex', alignItems: 'center', gap: '8px', color: '#94a3b8', fontWeight: 800, fontSize: '0.82rem', marginBottom: '6px' }}>
              <History size={16} aria-hidden="true" /> RECENT SEARCH
            </div>
            <div style={{ fontSize: '1rem', fontWeight: 700, color: '#f8fafc', marginBottom: '4px' }}>&ldquo;I looked for this.&rdquo;</div>
            <p style={{ margin: 0, fontSize: '0.82rem', color: '#94a3b8' }}>Browsing history to quickly pick up where you left off.</p>
          </div>

          <div style={{ backgroundColor: '#0f172a', border: '1px solid #a855f7', borderRadius: '14px', padding: '16px' }}>
            <div style={{ display: 'flex', alignItems: 'center', gap: '8px', color: '#c084fc', fontWeight: 800, fontSize: '0.82rem', marginBottom: '6px' }}>
              <Bookmark size={16} aria-hidden="true" /> SAVED SEARCH
            </div>
            <div style={{ fontSize: '1rem', fontWeight: 700, color: '#f8fafc', marginBottom: '4px' }}>&ldquo;I want to keep this search.&rdquo;</div>
            <p style={{ margin: 0, fontSize: '0.82rem', color: '#94a3b8' }}>Reusable search criteria you intentionally pinned.</p>
          </div>

          <div style={{ backgroundColor: '#0f172a', border: '1px solid #38bdf8', borderRadius: '14px', padding: '16px' }}>
            <div style={{ display: 'flex', alignItems: 'center', gap: '8px', color: '#38bdf8', fontWeight: 800, fontSize: '0.82rem', marginBottom: '6px' }}>
              <ShoppingBag size={16} aria-hidden="true" /> SAVED ITEM
            </div>
            <div style={{ fontSize: '1rem', fontWeight: 700, color: '#f8fafc', marginBottom: '4px' }}>&ldquo;I may want this product.&rdquo;</div>
            <p style={{ margin: 0, fontSize: '0.82rem', color: '#94a3b8' }}>Bookmarked product saved without adding it to the cart.</p>
          </div>

          <div style={{ backgroundColor: '#0f172a', border: '1px solid #10b981', borderRadius: '14px', padding: '16px' }}>
            <div style={{ display: 'flex', alignItems: 'center', gap: '8px', color: '#34d399', fontWeight: 800, fontSize: '0.82rem', marginBottom: '6px' }}>
              <ShoppingCart size={16} aria-hidden="true" /> CART
            </div>
            <div style={{ fontSize: '1rem', fontWeight: 700, color: '#f8fafc', marginBottom: '4px' }}>&ldquo;I&apos;m considering buying this.&rdquo;</div>
            <p style={{ margin: 0, fontSize: '0.82rem', color: '#94a3b8' }}>Active items ready for purchase review and checkout.</p>
          </div>
        </div>
      </section>

      {/* 13. PAYMENT SAFETY & 14. PAYPAL FLOW */}
      <section
        style={{
          backgroundColor: '#0f172a',
          border: '1px solid #10b981',
          borderRadius: '20px',
          padding: '28px 24px',
          marginBottom: '36px',
        }}
      >
        <div style={{ textAlign: 'center', maxWidth: '780px', margin: '0 auto 24px' }}>
          <span
            style={{
              display: 'inline-flex',
              alignItems: 'center',
              gap: '6px',
              fontSize: '0.78rem',
              fontWeight: 800,
              letterSpacing: '0.05em',
              textTransform: 'uppercase',
              color: '#34d399',
              backgroundColor: '#064e3b',
              padding: '4px 12px',
              borderRadius: '999px',
              marginBottom: '10px',
            }}
          >
            <ShieldCheck size={14} aria-hidden="true" />
            Precise Confirmation Gate
          </span>
          <h2 style={{ fontSize: '1.5rem', fontWeight: 900, margin: '0 0 10px', letterSpacing: '-0.02em' }}>
            Shopping can be conversational. Payment confirmation is precise.
          </h2>
          <p style={{ margin: 0, color: '#cbd5e1', fontSize: '0.94rem' }}>
            AccessPay requires confirmation of the actual purchase amount before continuing to PayPal. Casual affirmations never trigger charges.
          </p>
        </div>

        {/* Visual: Rejected vs Accepted */}
        <div style={{ display: 'grid', gridTemplateColumns: 'repeat(auto-fit, minmax(260px, 1fr))', gap: '16px', marginBottom: '24px' }}>
          {/* Rejected */}
          <div style={{ backgroundColor: '#450a0a', border: '1px solid #ef4444', borderRadius: '14px', padding: '16px' }}>
            <div style={{ fontSize: '0.84rem', fontWeight: 800, color: '#fca5a5', marginBottom: '10px' }}>
              CASUAL PHRASES REJECTED
            </div>
            <div style={{ display: 'flex', flexDirection: 'column', gap: '8px' }}>
              <div style={{ display: 'flex', alignItems: 'center', gap: '8px', color: '#fee2e2', fontSize: '0.88rem' }}>
                <XCircle size={16} color="#f87171" aria-hidden="true" />
                <span>&ldquo;Yes&rdquo; &mdash; <em>Not enough</em></span>
              </div>
              <div style={{ display: 'flex', alignItems: 'center', gap: '8px', color: '#fee2e2', fontSize: '0.88rem' }}>
                <XCircle size={16} color="#f87171" aria-hidden="true" />
                <span>&ldquo;Okay&rdquo; &mdash; <em>Not enough</em></span>
              </div>
              <div style={{ display: 'flex', alignItems: 'center', gap: '8px', color: '#fee2e2', fontSize: '0.88rem' }}>
                <XCircle size={16} color="#f87171" aria-hidden="true" />
                <span>&ldquo;Go ahead&rdquo; &mdash; <em>Not enough</em></span>
              </div>
            </div>
          </div>

          {/* Accepted */}
          <div style={{ backgroundColor: '#064e3b', border: '1px solid #10b981', borderRadius: '14px', padding: '16px' }}>
            <div style={{ fontSize: '0.84rem', fontWeight: 800, color: '#6ee7b7', marginBottom: '10px' }}>
              EXPLICIT EXACT-AMOUNT REQUIRED
            </div>
            <div style={{ display: 'flex', alignItems: 'center', gap: '8px', color: '#ecfdf5', fontSize: '1rem', fontWeight: 800, marginBottom: '6px' }}>
              <CheckCircle2 size={20} color="#34d399" aria-hidden="true" />
              <span>&ldquo;Confirm $53.99 purchase&rdquo;</span>
            </div>
            <p style={{ margin: 0, fontSize: '0.82rem', color: '#a7f3d0' }}>
              Binds the exact server-calculated total today.
            </p>
          </div>
        </div>

        {/* 14. PayPal Flow */}
        <div style={{ backgroundColor: '#020617', border: '1px solid #1e293b', borderRadius: '14px', padding: '16px' }}>
          <h3 style={{ fontSize: '0.98rem', fontWeight: 800, margin: '0 0 10px', color: '#38bdf8' }}>
            PayPal still handles buyer approval
          </h3>
          <div style={{ display: 'flex', flexWrap: 'wrap', gap: '10px', alignItems: 'center', fontSize: '0.88rem', fontWeight: 700, color: '#f8fafc', marginBottom: '10px' }}>
            <span style={{ padding: '6px 12px', backgroundColor: '#0f172a', borderRadius: '8px', border: '1px solid #334155' }}>Purchase Review</span>
            <ArrowRight size={16} color="#64748b" aria-hidden="true" />
            <span style={{ padding: '6px 12px', backgroundColor: '#0f172a', borderRadius: '8px', border: '1px solid #334155' }}>Exact Confirmation</span>
            <ArrowRight size={16} color="#64748b" aria-hidden="true" />
            <span style={{ padding: '6px 12px', backgroundColor: '#0c4a6e', borderRadius: '8px', border: '1px solid #0284c7', color: '#38bdf8' }}>PayPal Approval</span>
            <ArrowRight size={16} color="#64748b" aria-hidden="true" />
            <span style={{ padding: '6px 12px', backgroundColor: '#064e3b', borderRadius: '8px', border: '1px solid #10b981', color: '#6ee7b7' }}>Payment Complete</span>
          </div>
          <p style={{ margin: 0, fontSize: '0.84rem', color: '#94a3b8' }}>
            AccessPay does not bypass PayPal approval. After successful payment, the order is recorded and can be inspected anytime in Order History.
          </p>
        </div>
      </section>

      {/* 15. SUBSCRIPTION SAFETY & 16. ORDERS + SUBSCRIPTIONS */}
      <section
        style={{
          display: 'grid',
          gridTemplateColumns: 'repeat(auto-fit, minmax(320px, 1fr))',
          gap: '20px',
          marginBottom: '36px',
        }}
      >
        {/* Subscription Safety */}
        <div
          style={{
            backgroundColor: '#0f172a',
            border: '1px solid #f59e0b',
            borderRadius: '20px',
            padding: '24px',
          }}
        >
          <div style={{ display: 'flex', alignItems: 'center', gap: '8px', color: '#fbbf24', marginBottom: '10px' }}>
            <Repeat size={20} aria-hidden="true" />
            <h2 style={{ fontSize: '1.15rem', fontWeight: 800, margin: 0, color: '#f8fafc' }}>
              A subscription is not the same as a one-time purchase
            </h2>
          </div>
          <p style={{ margin: '0 0 16px', color: '#94a3b8', fontSize: '0.88rem' }}>
            AccessPay checks both the amount and billing frequency before recurring payment approval.
          </p>

          {/* Visual: One-Time vs Subscription */}
          <div style={{ display: 'grid', gridTemplateColumns: '1fr 1fr', gap: '10px', marginBottom: '14px' }}>
            <div style={{ backgroundColor: '#020617', border: '1px solid #334155', borderRadius: '10px', padding: '12px', textAlign: 'center' }}>
              <div style={{ fontSize: '0.72rem', color: '#94a3b8', fontWeight: 800 }}>ONE-TIME</div>
              <div style={{ fontSize: '1.2rem', fontWeight: 900, color: '#38bdf8' }}>$19.99</div>
              <div style={{ fontSize: '0.75rem', color: '#cbd5e1' }}>once</div>
            </div>
            <div style={{ backgroundColor: '#451a03', border: '1px solid #f59e0b', borderRadius: '10px', padding: '12px', textAlign: 'center' }}>
              <div style={{ fontSize: '0.72rem', color: '#fcd34d', fontWeight: 800 }}>SUBSCRIPTION</div>
              <div style={{ fontSize: '1.2rem', fontWeight: 900, color: '#fbbf24' }}>$19.99</div>
              <div style={{ fontSize: '0.75rem', color: '#fde68a' }}>every month</div>
            </div>
          </div>

          <div style={{ fontSize: '0.84rem', color: '#f8fafc', display: 'flex', flexDirection: 'column', gap: '6px' }}>
            <div style={{ color: '#6ee7b7', display: 'flex', alignItems: 'center', gap: '6px' }}>
              <Check size={16} /> &ldquo;Confirm $19.99 monthly subscription&rdquo; &mdash; <strong>Accepted</strong>
            </div>
            <div style={{ color: '#fca5a5', display: 'flex', alignItems: 'center', gap: '6px' }}>
              <XCircle size={16} /> &ldquo;Confirm $9.99 monthly subscription&rdquo; &mdash; <strong>Rejected</strong> (wrong amount)
            </div>
            <div style={{ color: '#fca5a5', display: 'flex', alignItems: 'center', gap: '6px' }}>
              <XCircle size={16} /> &ldquo;Confirm $19.99 yearly subscription&rdquo; &mdash; <strong>Rejected</strong> (wrong frequency)
            </div>
          </div>

          <div style={{ marginTop: '14px', fontSize: '0.76rem', color: '#94a3b8', backgroundColor: '#020617', padding: '8px 10px', borderRadius: '8px' }}>
            * Evaluated on a <strong>Demo subscription catalog</strong> with real <strong>PayPal Sandbox Subscriptions API v1</strong> workflows.
          </div>
        </div>

        {/* Orders + Subscriptions Separation */}
        <div
          style={{
            backgroundColor: '#0f172a',
            border: '1px solid #1e293b',
            borderRadius: '20px',
            padding: '24px',
          }}
        >
          <div style={{ display: 'flex', alignItems: 'center', gap: '8px', color: '#38bdf8', marginBottom: '10px' }}>
            <Receipt size={20} aria-hidden="true" />
            <h2 style={{ fontSize: '1.15rem', fontWeight: 800, margin: 0, color: '#f8fafc' }}>
              Know what you&apos;ve paid for
            </h2>
          </div>
          <p style={{ margin: '0 0 16px', color: '#94a3b8', fontSize: '0.88rem' }}>
            AccessPay keeps ordinary purchases and recurring subscriptions clearly separated.
          </p>

          <div style={{ display: 'flex', flexDirection: 'column', gap: '12px' }}>
            <div style={{ backgroundColor: '#020617', border: '1px solid #1e293b', borderRadius: '12px', padding: '14px' }}>
              <div style={{ display: 'flex', alignItems: 'center', gap: '6px', fontWeight: 800, color: '#38bdf8', fontSize: '0.88rem' }}>
                <ShoppingBag size={16} /> PURCHASES
              </div>
              <p style={{ margin: '4px 0 0', fontSize: '0.84rem', color: '#cbd5e1' }}>
                Previous one-time orders with item breakdown, PayPal capture IDs, and reorder capability.
              </p>
            </div>

            <div style={{ backgroundColor: '#020617', border: '1px solid #1e293b', borderRadius: '12px', padding: '14px' }}>
              <div style={{ display: 'flex', alignItems: 'center', gap: '6px', fontWeight: 800, color: '#fbbf24', fontSize: '0.88rem' }}>
                <Repeat size={16} /> SUBSCRIPTIONS
              </div>
              <p style={{ margin: '4px 0 0', fontSize: '0.84rem', color: '#cbd5e1' }}>
                Recurring commitments with renewal frequency, status, and phrase-verified cancellation.
              </p>
            </div>
          </div>
        </div>
      </section>

      {/* 17. MICROPHONE CONTROL & 18. ACCESSIBILITY */}
      <section
        style={{
          display: 'grid',
          gridTemplateColumns: 'repeat(auto-fit, minmax(320px, 1fr))',
          gap: '20px',
          marginBottom: '36px',
        }}
      >
        {/* Microphone Control */}
        <div
          style={{
            backgroundColor: '#0f172a',
            border: '1px solid #1e293b',
            borderRadius: '20px',
            padding: '24px',
          }}
        >
          <div style={{ display: 'flex', alignItems: 'center', gap: '8px', color: '#38bdf8', marginBottom: '10px' }}>
            <Mic size={20} aria-hidden="true" />
            <h2 style={{ fontSize: '1.15rem', fontWeight: 800, margin: 0, color: '#f8fafc' }}>
              You choose when AccessPay listens
            </h2>
          </div>

          {/* Visual: Speak -> Listening -> Complete -> Idle */}
          <div style={{ display: 'flex', flexWrap: 'wrap', gap: '8px', alignItems: 'center', margin: '14px 0', fontSize: '0.82rem', fontWeight: 700 }}>
            <span style={{ padding: '6px 10px', backgroundColor: '#0284c7', color: '#ffffff', borderRadius: '8px' }}>[ Speak ]</span>
            <ArrowRight size={14} color="#64748b" aria-hidden="true" />
            <span style={{ padding: '6px 10px', backgroundColor: '#0c4a6e', color: '#38bdf8', borderRadius: '8px' }}>Listening</span>
            <ArrowRight size={14} color="#64748b" aria-hidden="true" />
            <span style={{ padding: '6px 10px', backgroundColor: '#1e293b', color: '#cbd5e1', borderRadius: '8px' }}>Command complete</span>
            <ArrowRight size={14} color="#64748b" aria-hidden="true" />
            <span style={{ padding: '6px 10px', backgroundColor: '#020617', color: '#94a3b8', borderRadius: '8px', border: '1px solid #334155' }}>Microphone idle</span>
          </div>

          <p style={{ margin: '0 0 10px', color: '#cbd5e1', fontSize: '0.88rem' }}>
            AccessPay starts listening only after you choose Speak. It does not automatically activate the microphone when the page loads or when you return from PayPal.
          </p>
          <p style={{ margin: 0, color: '#94a3b8', fontSize: '0.84rem' }}>
            Browser microphone permission remains strictly under your control.
          </p>
        </div>

        {/* Accessibility Multi-Mode */}
        <div
          style={{
            backgroundColor: '#0f172a',
            border: '1px solid #1e293b',
            borderRadius: '20px',
            padding: '24px',
          }}
        >
          <div style={{ display: 'flex', alignItems: 'center', gap: '8px', color: '#34d399', marginBottom: '10px' }}>
            <Compass size={20} aria-hidden="true" />
            <h2 style={{ fontSize: '1.15rem', fontWeight: 800, margin: 0, color: '#f8fafc' }}>
              Designed for more than one way of interacting
            </h2>
          </div>

          <ul style={{ margin: 0, paddingLeft: '20px', color: '#cbd5e1', fontSize: '0.88rem', display: 'flex', flexDirection: 'column', gap: '6px' }}>
            <li><strong>Voice-first interaction</strong> across every view and button</li>
            <li><strong>Typed search suggestions</strong> for quick input</li>
            <li><strong>Keyboard-accessible controls</strong> with visible focus rings</li>
            <li><strong>Semantic navigation</strong> and clean landmarks</li>
            <li><strong>Screen-reader-friendly labels</strong> and live announcer</li>
            <li><strong>Clear payment information</strong> without hidden charges</li>
          </ul>
        </div>
      </section>

      {/* 19. OTHER COMPANIES & 20. APIMATIC (TWO ROLES) */}
      <section
        style={{
          backgroundColor: '#0f172a',
          border: '1px solid #6366f1',
          borderRadius: '20px',
          padding: '28px 24px',
          marginBottom: '36px',
        }}
      >
        <div style={{ textAlign: 'center', maxWidth: '780px', margin: '0 auto 24px' }}>
          <span
            style={{
              display: 'inline-flex',
              alignItems: 'center',
              gap: '6px',
              fontSize: '0.78rem',
              fontWeight: 800,
              letterSpacing: '0.05em',
              textTransform: 'uppercase',
              color: '#a5b4fc',
              backgroundColor: '#312e81',
              padding: '4px 12px',
              borderRadius: '999px',
              marginBottom: '10px',
            }}
          >
            <Building2 size={14} aria-hidden="true" />
            Merchant Integration &amp; APIMatic
          </span>
          <h2 style={{ fontSize: '1.5rem', fontWeight: 900, margin: '0 0 10px', letterSpacing: '-0.02em' }}>
            AccessPay can also work with other shopping experiences
          </h2>
          <p style={{ margin: 0, color: '#cbd5e1', fontSize: '0.94rem' }}>
            A company would not necessarily need to replace its existing storefront. AccessPay&apos;s capabilities can be exposed through APIs and integrated into an existing commerce experience.
          </p>
        </div>

        {/* Visual: Customer -> Existing Merchant App -> AccessPay API */}
        <div
          style={{
            display: 'flex',
            flexDirection: 'column',
            alignItems: 'center',
            gap: '8px',
            backgroundColor: '#020617',
            border: '1px solid #1e293b',
            borderRadius: '14px',
            padding: '16px',
            marginBottom: '28px',
            maxWidth: '680px',
            margin: '0 auto 28px',
          }}
        >
          <div style={{ fontWeight: 800, color: '#f8fafc', fontSize: '0.9rem' }}>CUSTOMER</div>
          <ArrowDown size={16} color="#64748b" aria-hidden="true" />
          <div style={{ fontWeight: 800, color: '#38bdf8', fontSize: '0.9rem' }}>EXISTING MERCHANT WEBSITE / APP</div>
          <ArrowDown size={16} color="#64748b" aria-hidden="true" />
          <div style={{ fontWeight: 800, color: '#a5b4fc', fontSize: '0.9rem' }}>ACCESSPAY API</div>
          <ArrowDown size={16} color="#64748b" aria-hidden="true" />
          <div style={{ display: 'flex', flexWrap: 'wrap', gap: '8px', justifyContent: 'center', fontSize: '0.8rem', color: '#cbd5e1' }}>
            <span style={{ backgroundColor: '#0f172a', padding: '4px 10px', borderRadius: '6px', border: '1px solid #334155' }}>Voice shopping</span>
            <span style={{ backgroundColor: '#0f172a', padding: '4px 10px', borderRadius: '6px', border: '1px solid #334155' }}>Conversational commerce</span>
            <span style={{ backgroundColor: '#0f172a', padding: '4px 10px', borderRadius: '6px', border: '1px solid #334155' }}>Cart</span>
            <span style={{ backgroundColor: '#0f172a', padding: '4px 10px', borderRadius: '6px', border: '1px solid #334155' }}>Safer checkout</span>
            <span style={{ backgroundColor: '#0f172a', padding: '4px 10px', borderRadius: '6px', border: '1px solid #334155' }}>Payments</span>
          </div>
        </div>

        {/* 20. APIMatic Two Roles */}
        <h3 style={{ fontSize: '1.15rem', fontWeight: 800, margin: '0 0 14px', textAlign: 'center', color: '#f8fafc' }}>
          Making AccessPay easier for developers to integrate
        </h3>

        <div style={{ display: 'grid', gridTemplateColumns: 'repeat(auto-fit, minmax(300px, 1fr))', gap: '16px' }}>
          {/* Role 1 */}
          <div style={{ backgroundColor: '#020617', border: '1px solid #1e293b', borderRadius: '14px', padding: '18px' }}>
            <div style={{ fontSize: '0.78rem', fontWeight: 800, color: '#38bdf8', marginBottom: '6px' }}>ROLE 1: BUILDING ACCESSPAY</div>
            <h4 style={{ margin: '0 0 8px', fontSize: '0.96rem', fontWeight: 800 }}>Development Context</h4>
            <div style={{ fontSize: '0.82rem', color: '#94a3b8', marginBottom: '10px' }}>
              AI Coding Workflow &rarr; APIMatic PayPal Context Plugin &rarr; Authoritative PayPal API Context &rarr; AccessPay PayPal Integration
            </div>
            <p style={{ margin: 0, fontSize: '0.84rem', color: '#cbd5e1' }}>
              APIMatic helped the development workflow use authoritative PayPal API context.
            </p>
          </div>

          {/* Role 2 */}
          <div style={{ backgroundColor: '#020617', border: '1px solid #1e293b', borderRadius: '14px', padding: '18px' }}>
            <div style={{ fontSize: '0.78rem', fontWeight: 800, color: '#a5b4fc', marginBottom: '6px' }}>ROLE 2: EXTENDING ACCESSPAY</div>
            <h4 style={{ margin: '0 0 8px', fontSize: '0.96rem', fontWeight: 800 }}>Merchant Developer Experience</h4>
            <div style={{ fontSize: '0.82rem', color: '#94a3b8', marginBottom: '10px' }}>
              AccessPay API &rarr; OpenAPI &rarr; APIMatic &rarr; Developer Portal &rarr; TypeScript + Python Integration &rarr; Merchant Applications
            </div>
            <p style={{ margin: 0, fontSize: '0.84rem', color: '#cbd5e1' }}>
              AccessPay&apos;s real API definition was imported into APIMatic to create developer-facing integration resources. (User payment traffic does NOT pass through APIMatic.)
            </p>
          </div>
        </div>
      </section>

      {/* 21. DEVELOPER PORTAL CARD */}
      <section
        style={{
          backgroundColor: '#0a0f1d',
          border: '1px solid #334155',
          borderRadius: '20px',
          padding: '24px',
          marginBottom: '36px',
        }}
      >
        <div style={{ display: 'flex', flexWrap: 'wrap', justifyContent: 'space-between', alignItems: 'center', gap: '16px' }}>
          <div>
            <div style={{ fontSize: '0.78rem', fontWeight: 800, color: '#a5b4fc', textTransform: 'uppercase', letterSpacing: '0.05em', marginBottom: '4px' }}>
              Developer Integration Portal
            </div>
            <h3 style={{ fontSize: '1.25rem', fontWeight: 900, margin: '0 0 6px' }}>
              AccessPay Merchant API Portal
            </h3>
            <p style={{ margin: 0, fontSize: '0.88rem', color: '#94a3b8', maxWidth: '640px' }}>
              The APIMatic-generated portal provides TypeScript and Python integration support, API reference documentation, and AI-ready AccessPay context.
            </p>
            <div style={{ display: 'flex', gap: '8px', marginTop: '10px', fontSize: '0.8rem', color: '#38bdf8' }}>
              <span style={{ backgroundColor: '#0f172a', padding: '2px 8px', borderRadius: '6px' }}>Home</span>
              <span style={{ backgroundColor: '#0f172a', padding: '2px 8px', borderRadius: '6px' }}>SDKs (TS &amp; Py)</span>
              <span style={{ backgroundColor: '#0f172a', padding: '2px 8px', borderRadius: '6px' }}>Context Plugin</span>
              <span style={{ backgroundColor: '#0f172a', padding: '2px 8px', borderRadius: '6px' }}>API Reference</span>
            </div>
          </div>

          <a
            href="http://127.0.0.1:23513"
            target="_blank"
            rel="noopener noreferrer"
            style={{
              display: 'inline-flex',
              alignItems: 'center',
              gap: '6px',
              padding: '12px 20px',
              borderRadius: '12px',
              border: '1px solid #818cf8',
              backgroundColor: '#312e81',
              color: '#ffffff',
              fontWeight: 800,
              fontSize: '0.94rem',
              textDecoration: 'none',
              boxShadow: '0 4px 14px rgba(49, 46, 129, 0.4)',
            }}
          >
            View Merchant Developer Portal
            <ExternalLink size={16} aria-hidden="true" />
          </a>
        </div>
      </section>

      {/* 22. TECHNOLOGY SECTION (COMPACT CARDS) */}
      <section aria-labelledby="technology-heading" style={{ marginBottom: '36px' }}>
        <h2 id="technology-heading" style={{ fontSize: '1.4rem', fontWeight: 900, margin: '0 0 16px', textAlign: 'center' }}>
          What powers AccessPay?
        </h2>

        <div
          style={{
            display: 'grid',
            gridTemplateColumns: 'repeat(auto-fit, minmax(210px, 1fr))',
            gap: '12px',
          }}
        >
          {[
            { name: 'React + TypeScript + Vite', role: 'Interface' },
            { name: 'Web Speech API', role: 'Voice interaction' },
            { name: 'Python + FastAPI', role: 'Backend / API' },
            { name: 'SQLite', role: 'Prototype persistence' },
            { name: 'Google Gemini', role: 'Conversational understanding' },
            { name: 'Channel3', role: 'Commerce product data' },
            { name: 'PayPal Sandbox', role: 'One-time + recurring workflows' },
            { name: 'APIMatic', role: 'API context + developer tooling' },
            { name: 'Pytest + Playwright', role: 'Testing & verification' },
          ].map((tech) => (
            <div
              key={tech.name}
              style={{
                backgroundColor: '#0f172a',
                border: '1px solid #1e293b',
                borderRadius: '12px',
                padding: '12px 14px',
              }}
            >
              <div style={{ fontWeight: 800, fontSize: '0.88rem', color: '#f8fafc', marginBottom: '2px' }}>{tech.name}</div>
              <div style={{ fontSize: '0.78rem', color: '#38bdf8' }}>{tech.role}</div>
            </div>
          ))}
        </div>
      </section>

      {/* 23. PROTOTYPE TRANSPARENCY */}
      <section
        style={{
          backgroundColor: '#020617',
          border: '1px dashed #334155',
          borderRadius: '16px',
          padding: '20px 24px',
          marginBottom: '36px',
          textAlign: 'center',
        }}
      >
        <h3 style={{ fontSize: '1rem', fontWeight: 800, margin: '0 0 6px', color: '#94a3b8' }}>
          Built as a hackathon prototype
        </h3>
        <p style={{ margin: 0, fontSize: '0.86rem', color: '#64748b', maxWidth: '780px', marginInline: 'auto' }}>
          AccessPay demonstrates the complete concept, but a production merchant platform would require additional infrastructure such as merchant authentication, tenant isolation, rate limiting, monitoring, webhooks, and production security controls.
        </p>
      </section>

      {/* 24. BOTTOM NAVIGATION LINKS */}
      <nav
        aria-label="About page destination links"
        style={{
          display: 'flex',
          flexWrap: 'wrap',
          gap: '12px',
          justifyContent: 'center',
          alignItems: 'center',
          paddingTop: '16px',
          borderTop: '1px solid #1e293b',
        }}
      >
        <button
          type="button"
          onClick={onStartShopping}
          style={{
            display: 'inline-flex',
            alignItems: 'center',
            gap: '8px',
            padding: '12px 20px',
            borderRadius: '12px',
            backgroundColor: '#0284c7',
            color: '#ffffff',
            fontWeight: 800,
            fontSize: '0.94rem',
            border: 'none',
            cursor: 'pointer',
          }}
        >
          <ShoppingBag size={18} aria-hidden="true" />
          Start Shopping
        </button>

        <button
          type="button"
          onClick={onNavigateDevelopers}
          style={{
            display: 'inline-flex',
            alignItems: 'center',
            gap: '8px',
            padding: '12px 20px',
            borderRadius: '12px',
            border: '1px solid #38bdf8',
            backgroundColor: '#0c4a6e',
            color: '#e0f2fe',
            fontWeight: 800,
            fontSize: '0.94rem',
            cursor: 'pointer',
          }}
        >
          <Code2 size={18} aria-hidden="true" />
          AccessPay for Merchants
        </button>

        <a
          href="http://127.0.0.1:23513"
          target="_blank"
          rel="noopener noreferrer"
          style={{
            display: 'inline-flex',
            alignItems: 'center',
            gap: '8px',
            padding: '12px 20px',
            borderRadius: '12px',
            border: '1px solid #818cf8',
            backgroundColor: '#312e81',
            color: '#e0e7ff',
            fontWeight: 800,
            fontSize: '0.94rem',
            textDecoration: 'none',
          }}
        >
          <ExternalLink size={18} aria-hidden="true" />
          Merchant Developer Portal
        </a>

        <a
          href="https://github.com/DeviKamakshi/accesspay-ai"
          target="_blank"
          rel="noopener noreferrer"
          style={{
            display: 'inline-flex',
            alignItems: 'center',
            gap: '8px',
            padding: '12px 20px',
            borderRadius: '12px',
            border: '1px solid #334155',
            backgroundColor: '#0f172a',
            color: '#e2e8f0',
            fontWeight: 800,
            fontSize: '0.94rem',
            textDecoration: 'none',
          }}
        >
          <BookOpen size={18} aria-hidden="true" />
          GitHub
        </a>
      </nav>
    </article>
  );
};
