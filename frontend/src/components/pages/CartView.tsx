import React, { useMemo, useState, useCallback } from 'react';
import { useCart } from '../../context/CartContext';
import { useRegisterVoiceControls } from '../../context/VoiceCommandContext';
import { VoiceControlDescriptor } from '../../utils/voiceControlMatcher';
import { PurchaseReview } from '../../types';
import { ContextualVoiceTips } from '../common/ContextualVoiceTips';
import { ShoppingCart, Plus, Minus, Trash2, ArrowRight, AlertTriangle } from 'lucide-react';

interface CartViewProps {
  onProceedToReview: (review: PurchaseReview) => void;
  onBackToShop: () => void;
}

export const CartView: React.FC<CartViewProps> = ({ onProceedToReview, onBackToShop }) => {
  const { cart, isLoading, updateQuantity, removeFromCart, clearCart, prepareReview } = useCart();
  const [busy, setBusy] = useState(false);

  const items = cart?.items || [];

  const handleCheckout = useCallback(async () => {
    setBusy(true);
    try {
      const review = await prepareReview();
      if (review) {
        onProceedToReview(review);
      }
    } finally {
      setBusy(false);
    }
  }, [onProceedToReview, prepareReview]);

  const cartControls = useMemo<VoiceControlDescriptor[]>(() => {
    const list: VoiceControlDescriptor[] = [
      {
        id: 'cart-back-to-shop',
        type: 'cart-action',
        accessibleName: 'Back to Shop',
        aliases: ['back to shop', 'browse products', 'back'],
        currentView: 'CART',
        enabled: true,
        feedbackText: 'Returning to Shop.',
        action: onBackToShop,
      },
      {
        id: 'cart-clear',
        type: 'cart-action',
        accessibleName: 'Clear Cart',
        aliases: ['clear cart', 'clear my cart', 'empty cart'],
        currentView: 'CART',
        enabled: items.length > 0 && !isLoading && !busy,
        disabledReason: 'Your cart is already empty.',
        feedbackText: 'Cart cleared.',
        action: () => clearCart(),
      },
      {
        id: 'cart-checkout',
        type: 'checkout-action',
        accessibleName: 'Continue to Checkout',
        aliases: ['checkout', 'continue to checkout', 'proceed to checkout'],
        currentView: 'CART',
        enabled: items.length > 0 && !isLoading && !busy,
        disabledReason: "Checkout isn't available because your cart is empty.",
        feedbackText: 'Opening purchase review.',
        action: () => handleCheckout(),
      },
    ];

    items.forEach((item, idx) => {
      list.push(
        {
          id: `cart-inc-${item.product_id}`,
          type: 'cart-action',
          accessibleName: 'Increase quantity',
          aliases: ['increase quantity', 'add one', 'plus'],
          entityId: item.product_id,
          entityTitle: item.product.title,
          entityIndex: idx,
          currentView: 'CART',
          enabled: !isLoading,
          feedbackText: `Increased quantity to ${item.quantity + 1}.`,
          action: () => updateQuantity(item.product_id, item.quantity + 1),
        },
        {
          id: `cart-dec-${item.product_id}`,
          type: 'cart-action',
          accessibleName: 'Decrease quantity',
          aliases: ['decrease quantity', 'reduce quantity', 'minus'],
          entityId: item.product_id,
          entityTitle: item.product.title,
          entityIndex: idx,
          currentView: 'CART',
          enabled: item.quantity > 1 && !isLoading,
          disabledReason: 'Quantity is already 1.',
          feedbackText: `Decreased quantity to ${Math.max(1, item.quantity - 1)}.`,
          action: () => updateQuantity(item.product_id, Math.max(1, item.quantity - 1)),
        },
        {
          id: `cart-remove-${item.product_id}`,
          type: 'cart-action',
          accessibleName: 'Remove',
          aliases: ['remove', 'remove item', 'delete'],
          entityId: item.product_id,
          entityTitle: item.product.title,
          entityIndex: idx,
          currentView: 'CART',
          enabled: !isLoading,
          feedbackText: `Removed ${item.product.title} from cart.`,
          action: () => removeFromCart(item.product_id),
        }
      );
    });

    return list;
  }, [busy, clearCart, handleCheckout, isLoading, items, onBackToShop, removeFromCart, updateQuantity]);

  useRegisterVoiceControls('cart-view', cartControls, [cartControls]);

  return (
    <section
      aria-label="Shopping Cart"
      style={{ maxWidth: '1040px', margin: '0 auto', padding: '16px 20px 56px' }}
    >
      <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', flexWrap: 'wrap', gap: '12px', marginBottom: '24px' }}>
        <div>
          <div style={{ display: 'flex', alignItems: 'center', gap: '10px' }}>
            <ShoppingCart size={24} color="#38bdf8" aria-hidden="true" />
            <h2 style={{ fontSize: '1.75rem', fontWeight: 800, color: '#f8fafc', margin: 0 }}>
              Your Cart
            </h2>
          </div>
          <p style={{ color: '#94a3b8', marginTop: '4px', fontSize: '0.96rem', marginBottom: 0 }}>
            Review your items before checkout.
          </p>
        </div>
        <button
          type="button"
          onClick={onBackToShop}
          style={{
            backgroundColor: '#1e293b',
            color: '#e2e8f0',
            border: '1px solid #334155',
            borderRadius: '12px',
            padding: '10px 18px',
            fontWeight: 700,
            minHeight: '44px',
          }}
        >
          Back to Shop
        </button>
      </div>

      {items.length === 0 ? (
        <div className="app-card" style={{ textAlign: 'center', padding: '28px 24px', backgroundColor: '#111827' }}>
          <h3 style={{ color: '#f8fafc', margin: '0 0 6px', fontSize: '1.05rem', fontWeight: 700 }}>
            Your cart is empty.
          </h3>
          <p style={{ color: '#94a3b8', maxWidth: '460px', margin: '0 auto 16px', fontSize: '0.92rem' }}>
            Try saying: &ldquo;Find wireless headphones under $80.&rdquo;
          </p>
          <button
            type="button"
            onClick={onBackToShop}
            style={{
              backgroundColor: '#0284c7',
              color: '#ffffff',
              border: 'none',
              borderRadius: '12px',
              padding: '10px 20px',
              fontWeight: 800,
              minHeight: '44px',
            }}
          >
            Browse Products
          </button>
        </div>
      ) : (
        <div style={{ display: 'flex', flexDirection: 'column', gap: '16px' }}>
          <ContextualVoiceTips
            commands={[
              "What's my total?",
              'Remove the second item',
              'Set the first quantity to two',
              'Checkout',
            ]}
          />
          {cart?.warnings && cart.warnings.length > 0 && (
            <div
              role="note"
              style={{
                backgroundColor: '#451a03',
                border: '1px solid #f59e0b',
                borderRadius: '14px',
                padding: '14px 18px',
                color: '#fef3c7',
                display: 'flex',
                alignItems: 'flex-start',
                gap: '10px',
              }}
            >
              <AlertTriangle size={20} color="#f59e0b" style={{ flexShrink: 0, marginTop: '2px' }} />
              <div style={{ display: 'flex', flexDirection: 'column', gap: '4px' }}>
                {cart.warnings.map((w, i) => (
                  <span key={i} style={{ fontSize: '0.95rem', fontWeight: 600 }}>{w}</span>
                ))}
              </div>
            </div>
          )}

          {items.map((item, idx) => (
            <article
              key={item.id || item.product_id}
              data-cart-product-id={item.product_id}
              className="app-card"
              style={{
                backgroundColor: '#111827',
                display: 'flex',
                flexWrap: 'wrap',
                justifyContent: 'space-between',
                alignItems: 'center',
                gap: '16px',
              }}
            >
              <div style={{ display: 'flex', alignItems: 'center', gap: '14px', flex: '1 1 320px' }}>
                {item.product.image_url && (
                  <img
                    src={item.product.image_url}
                    alt={item.product.title}
                    style={{ width: '72px', height: '72px', objectFit: 'contain', backgroundColor: '#fff', borderRadius: '10px', padding: '4px' }}
                  />
                )}
                <div>
                  <span style={{ fontSize: '0.78rem', fontWeight: 800, color: '#38bdf8', textTransform: 'uppercase' }}>
                    Item #{idx + 1} &bull; {item.product.merchant}
                  </span>
                  <h3 style={{ fontSize: '1.08rem', fontWeight: 700, color: '#f8fafc', margin: '2px 0 4px' }}>
                    {item.product.title}
                  </h3>
                  <div style={{ color: '#94a3b8', fontSize: '0.94rem' }}>
                    ${item.product.price.toFixed(2)} each &bull; Line total:{' '}
                    <strong style={{ color: '#e2e8f0' }}>${item.item_total.toFixed(2)}</strong>
                  </div>
                </div>
              </div>

              <div style={{ display: 'flex', alignItems: 'center', gap: '10px' }}>
                <button
                  type="button"
                  onClick={() => updateQuantity(item.product_id, Math.max(1, item.quantity - 1))}
                  disabled={item.quantity <= 1 || isLoading}
                  aria-label={`Decrease quantity for ${item.product.title}`}
                  style={{
                    backgroundColor: '#1e293b',
                    color: '#f8fafc',
                    border: '1px solid #334155',
                    borderRadius: '10px',
                    width: '44px',
                    height: '44px',
                    display: 'inline-flex',
                    alignItems: 'center',
                    justifyContent: 'center',
                  }}
                >
                  <Minus size={18} />
                </button>
                <span
                  aria-label={`Quantity ${item.quantity}`}
                  style={{ minWidth: '34px', textAlign: 'center', fontWeight: 800, fontSize: '1.05rem', color: '#f8fafc' }}
                >
                  {item.quantity}
                </span>
                <button
                  type="button"
                  onClick={() => updateQuantity(item.product_id, item.quantity + 1)}
                  disabled={isLoading}
                  aria-label={`Increase quantity for ${item.product.title}`}
                  style={{
                    backgroundColor: '#1e293b',
                    color: '#f8fafc',
                    border: '1px solid #334155',
                    borderRadius: '10px',
                    width: '44px',
                    height: '44px',
                    display: 'inline-flex',
                    alignItems: 'center',
                    justifyContent: 'center',
                  }}
                >
                  <Plus size={18} />
                </button>
                <button
                  type="button"
                  onClick={() => removeFromCart(item.product_id)}
                  disabled={isLoading}
                  aria-label={`Remove ${item.product.title} from cart`}
                  style={{
                    backgroundColor: '#450a0a',
                    color: '#fecaca',
                    border: '1px solid #dc2626',
                    borderRadius: '10px',
                    padding: '10px 14px',
                    minHeight: '44px',
                    display: 'inline-flex',
                    alignItems: 'center',
                    gap: '6px',
                    fontWeight: 700,
                  }}
                >
                  <Trash2 size={16} />
                  <span>Remove</span>
                </button>
              </div>
            </article>
          ))}

          {/* Order Cost Breakdown & Checkout */}
          <div
            className="app-card"
            style={{
              backgroundColor: '#0f172a',
              border: '2px solid #0284c7',
              display: 'flex',
              flexDirection: 'column',
              gap: '12px',
            }}
          >
            <div style={{ display: 'flex', justifyContent: 'space-between', color: '#cbd5e1' }}>
              <span>Subtotal ({cart?.item_count || 0} items)</span>
              <strong>${(cart?.subtotal || 0).toFixed(2)}</strong>
            </div>
            <div style={{ display: 'flex', justifyContent: 'space-between', color: '#cbd5e1' }}>
              <span>Shipping</span>
              <strong>${(cart?.shipping_total || 0).toFixed(2)}</strong>
            </div>
            <div style={{ display: 'flex', justifyContent: 'space-between', color: '#cbd5e1' }}>
              <span>Estimated Tax</span>
              <strong>${(cart?.tax_total || 0).toFixed(2)}</strong>
            </div>
            {cart && cart.discount_total > 0 && (
              <div style={{ display: 'flex', justifyContent: 'space-between', color: '#34d399' }}>
                <span>Discounts</span>
                <strong>-${cart.discount_total.toFixed(2)}</strong>
              </div>
            )}
            <div
              style={{
                borderTop: '1px solid #1e293b',
                paddingTop: '12px',
                display: 'flex',
                justifyContent: 'space-between',
                alignItems: 'center',
                fontSize: '1.28rem',
                fontWeight: 900,
                color: '#f8fafc',
              }}
            >
              <span>Total Today</span>
              <span style={{ color: '#38bdf8' }}>${(cart?.total_today || 0).toFixed(2)}</span>
            </div>

            <div style={{ display: 'flex', flexWrap: 'wrap', justifyContent: 'space-between', gap: '12px', marginTop: '8px' }}>
              <button
                type="button"
                onClick={clearCart}
                disabled={isLoading || busy}
                style={{
                  backgroundColor: 'transparent',
                  color: '#f87171',
                  border: '1px solid #7f1d1d',
                  borderRadius: '12px',
                  padding: '12px 18px',
                  fontWeight: 700,
                  minHeight: '48px',
                }}
              >
                Clear Cart
              </button>
              <button
                type="button"
                onClick={handleCheckout}
                disabled={isLoading || busy}
                style={{
                  backgroundColor: '#0284c7',
                  color: '#ffffff',
                  border: 'none',
                  borderRadius: '12px',
                  padding: '14px 26px',
                  fontSize: '1.05rem',
                  fontWeight: 800,
                  minHeight: '50px',
                  display: 'inline-flex',
                  alignItems: 'center',
                  gap: '8px',
                }}
              >
                <span>{busy ? 'Preparing Review...' : 'Continue to Checkout'}</span>
                <ArrowRight size={18} />
              </button>
            </div>
          </div>
        </div>
      )}
    </section>
  );
};

