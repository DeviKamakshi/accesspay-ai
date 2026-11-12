import React, { useEffect, useState, useCallback, useMemo } from 'react';
import { OrderRecord, PurchaseReview, SubscriptionRecord } from '../../types';
import { api } from '../../services/api';
import { useAccessibility } from '../../context/AccessibilityContext';
import { useCart } from '../../context/CartContext';
import { useRegisterVoiceControls } from '../../context/VoiceCommandContext';
import { VoiceControlDescriptor } from '../../utils/voiceControlMatcher';
import { ContextualVoiceTips } from '../common/ContextualVoiceTips';
import { Package, RefreshCw, ChevronDown, ChevronUp, ShieldCheck, ReceiptText, Repeat, XCircle } from 'lucide-react';

interface OrdersViewProps {
  onReorderReview: (review: PurchaseReview, message: string) => void;
  selectedOrderId?: string | null;
  onSelectOrder?: (orderId: string | null) => void;
  reloadNonce?: number;
  initialTab?: 'purchases' | 'subscriptions';
  onTabChange?: (tab: 'purchases' | 'subscriptions') => void;
}

export const OrdersView: React.FC<OrdersViewProps> = ({
  onReorderReview,
  selectedOrderId = null,
  onSelectOrder,
  reloadNonce = 0,
  initialTab = 'purchases',
  onTabChange,
}) => {
  const { announce } = useAccessibility();
  const { refreshCart } = useCart();

  const [orders, setOrders] = useState<OrderRecord[]>([]);
  const [subscriptions, setSubscriptions] = useState<SubscriptionRecord[]>([]);
  const [activeTab, setActiveTab] = useState<'purchases' | 'subscriptions'>(initialTab);
  const [loading, setLoading] = useState<boolean>(true);
  const [expandedOrderIds, setExpandedOrderIds] = useState<Record<string, boolean>>({});
  const [busyOrderId, setBusyOrderId] = useState<string | null>(null);
  const [cancellingSubId, setCancellingSubId] = useState<string | null>(null);
  const [cancelPhrase, setCancelPhrase] = useState<string>('');
  const [cancelBusy, setCancelBusy] = useState<boolean>(false);
  const [errorMsg, setErrorMsg] = useState<string | null>(null);

  useEffect(() => {
    setActiveTab(initialTab);
  }, [initialTab]);

  const switchTab = (tab: 'purchases' | 'subscriptions') => {
    setActiveTab(tab);
    onTabChange?.(tab);
  };

  const loadOrders = useCallback(async () => {
    setLoading(true);
    setErrorMsg(null);
    try {
      const [list, subList] = await Promise.all([
        api.getOrders(),
        api.listSubscriptions().catch(() => [] as SubscriptionRecord[]),
      ]);
      setOrders(list);
      setSubscriptions(subList);
    } catch (err: any) {
      setErrorMsg(err?.message || 'Unable to load orders right now.');
    } finally {
      setLoading(false);
    }
  }, []);

  useEffect(() => {
    loadOrders();
  }, [loadOrders, reloadNonce]);

  useEffect(() => {
    if (selectedOrderId) {
      setExpandedOrderIds((prev) => ({
        ...prev,
        [selectedOrderId]: true,
      }));
    }
  }, [selectedOrderId]);

  const toggleDetails = (orderId: string) => {
    const nextExpanded = !expandedOrderIds[orderId];
    setExpandedOrderIds((prev) => ({
      ...prev,
      [orderId]: nextExpanded,
    }));
    onSelectOrder?.(nextExpanded ? orderId : null);
  };

  const handleBuyAgain = async (order: OrderRecord) => {
    setBusyOrderId(order.order_id);
    setErrorMsg(null);
    try {
      const res = await api.reorderOrder(order.order_id);
      await refreshCart();
      const msg =
        res.message ||
        `Reorder prepared for ${order.product_title}. Total today is $${res.review.total_today.toFixed(2)}. Confirmation is required.`;
      announce(msg);
      onReorderReview(res.review, msg);
    } catch (err: any) {
      const msg = err?.message || 'Unable to prepare reorder right now.';
      setErrorMsg(msg);
      announce(msg, true);
    } finally {
      setBusyOrderId(null);
    }
  };

  const activeOrderView =
    selectedOrderId || Object.values(expandedOrderIds).some(Boolean)
      ? 'ORDER_DETAILS'
      : 'ORDERS';

  const orderControls = useMemo<VoiceControlDescriptor[]>(() => {
    const controls: VoiceControlDescriptor[] = [];

    orders.forEach((order, idx) => {
      const isExpanded = Boolean(expandedOrderIds[order.order_id]);
      controls.push(
        {
          id: `order-details-${order.order_id}`,
          type: 'order-action',
          accessibleName: isExpanded ? 'Hide Details' : 'View Details',
          aliases: isExpanded
            ? ['hide details', 'collapse', 'collapse this order', 'close', 'close details']
            : ['view details', 'details', 'open', 'open order', 'expand'],
          currentView: activeOrderView,
          enabled: true,
          entityId: order.order_id,
          entityTitle: order.product_title,
          entityIndex: idx,
          action: () => toggleDetails(order.order_id),
        },
        {
          id: `order-buy-again-${order.order_id}`,
          type: 'order-action',
          accessibleName: 'Buy Again',
          aliases: ['buy again', 'buy this again', 'reorder', 'order again'],
          currentView: activeOrderView,
          enabled: busyOrderId !== order.order_id,
          disabledReason: 'Still preparing reorder for this order.',
          entityId: order.order_id,
          entityTitle: order.product_title,
          entityIndex: idx,
          action: () => handleBuyAgain(order),
        },
      );
    });

    return controls;
  }, [orders, expandedOrderIds, busyOrderId, activeOrderView]);

  useRegisterVoiceControls('orders-view', orderControls, [orderControls]);

  return (
    <section
      aria-label="Order History"
      style={{ maxWidth: '1040px', margin: '0 auto', padding: '8px 4px 48px' }}
    >
      <div style={{ marginBottom: '24px', display: 'flex', flexWrap: 'wrap', justifyContent: 'space-between', alignItems: 'center', gap: '16px' }}>
        <div>
          <div style={{ display: 'flex', alignItems: 'center', gap: '10px' }}>
            <ReceiptText size={24} color="#38bdf8" aria-hidden="true" />
            <h2 style={{ fontSize: '1.75rem', fontWeight: 800, color: '#f8fafc', margin: 0 }}>
              Orders
            </h2>
          </div>
          <p style={{ color: '#94a3b8', marginTop: '4px', fontSize: '0.98rem', marginBottom: 0 }}>
            {activeTab === 'subscriptions'
              ? 'Manage recurring subscriptions separately from one-time purchases.'
              : 'Review past purchases or buy again.'}
          </p>
        </div>

        <div
          role="tablist"
          aria-label="Orders view filter"
          style={{
            display: 'inline-flex',
            backgroundColor: '#0f172a',
            border: '1px solid #334155',
            borderRadius: '12px',
            padding: '4px',
            gap: '4px',
          }}
        >
          <button
            type="button"
            role="tab"
            aria-selected={activeTab === 'purchases'}
            onClick={() => switchTab('purchases')}
            style={{
              padding: '8px 14px',
              borderRadius: '9px',
              border: 'none',
              cursor: 'pointer',
              fontWeight: 700,
              fontSize: '0.88rem',
              backgroundColor: activeTab === 'purchases' ? '#1e293b' : 'transparent',
              color: activeTab === 'purchases' ? '#f8fafc' : '#94a3b8',
            }}
          >
            Purchases ({orders.length})
          </button>
          <button
            type="button"
            role="tab"
            aria-selected={activeTab === 'subscriptions'}
            onClick={() => switchTab('subscriptions')}
            style={{
              padding: '8px 14px',
              borderRadius: '9px',
              border: 'none',
              cursor: 'pointer',
              fontWeight: 700,
              fontSize: '0.88rem',
              display: 'inline-flex',
              alignItems: 'center',
              gap: '6px',
              backgroundColor: activeTab === 'subscriptions' ? '#451a03' : 'transparent',
              color: activeTab === 'subscriptions' ? '#fcd34d' : '#94a3b8',
            }}
          >
            <Repeat size={15} aria-hidden="true" />
            Subscriptions ({subscriptions.length})
          </button>
        </div>
      </div>

      {errorMsg && (
        <div
          role="alert"
          style={{
            backgroundColor: '#450a0a',
            border: '2px solid #ef4444',
            color: '#fecaca',
            borderRadius: '14px',
            padding: '14px 18px',
            marginBottom: '18px',
            fontWeight: 600,
          }}
        >
          {errorMsg}
        </div>
      )}

      {loading ? (
        <div
          style={{
            backgroundColor: '#111827',
            borderRadius: '16px',
            padding: '32px',
            textAlign: 'center',
            color: '#94a3b8',
            border: '2px solid #1e293b',
          }}
        >
          Loading your orders...
        </div>
      ) : activeTab === 'subscriptions' ? (
        <div style={{ display: 'flex', flexDirection: 'column', gap: '16px' }}>
          <ContextualVoiceTips
            commands={[
              'How much is my subscription?',
              'How often am I charged?',
              'Cancel this subscription',
              'Go back to purchases',
            ]}
          />
          {subscriptions.length === 0 ? (
            <div
              style={{
                backgroundColor: '#111827',
                borderRadius: '16px',
                padding: '28px 24px',
                textAlign: 'center',
                color: '#cbd5e1',
                border: '1px solid #1e293b',
              }}
            >
              <p style={{ fontSize: '1.05rem', fontWeight: 700, color: '#f8fafc', margin: 0 }}>
                No active or past subscriptions yet.
              </p>
              <p style={{ fontSize: '0.9rem', color: '#94a3b8', marginTop: '6px' }}>
                Try searching in Shop for "Show me a developer subscription".
              </p>
            </div>
          ) : (
            subscriptions.map((sub) => {
              const isActive = sub.status === 'ACTIVE';
              const isCancelled = sub.status === 'CANCELLED';
              const isPromptingCancel = cancellingSubId === sub.subscription_id;
              const expectedCancelPhrase = `Confirm cancellation of ${sub.plan_name}.`;

              return (
                <article
                  key={sub.subscription_id}
                  data-subscription-id={sub.subscription_id}
                  style={{
                    backgroundColor: '#111827',
                    border: isActive ? '2px solid #10b981' : isCancelled ? '2px solid #475569' : '2px solid #f59e0b',
                    borderRadius: '18px',
                    padding: '20px 22px',
                    display: 'flex',
                    flexDirection: 'column',
                    gap: '12px',
                  }}
                >
                  <div style={{ display: 'flex', flexWrap: 'wrap', justifyContent: 'space-between', alignItems: 'flex-start', gap: '12px' }}>
                    <div>
                      <div style={{ display: 'flex', flexWrap: 'wrap', alignItems: 'center', gap: '8px', marginBottom: '6px' }}>
                        <span
                          style={{
                            fontSize: '0.78rem',
                            fontWeight: 800,
                            letterSpacing: '0.04em',
                            padding: '3px 10px',
                            borderRadius: '9999px',
                            backgroundColor: isActive ? '#064e3b' : isCancelled ? '#1e293b' : '#451a03',
                            color: isActive ? '#6ee7b7' : isCancelled ? '#94a3b8' : '#fcd34d',
                          }}
                        >
                          {isActive ? 'SUBSCRIPTION ACTIVE' : sub.status}
                        </span>
                        <span
                          style={{
                            fontSize: '0.78rem',
                            fontWeight: 700,
                            padding: '3px 10px',
                            borderRadius: '9999px',
                            backgroundColor: '#1e293b',
                            color: '#cbd5e1',
                          }}
                        >
                          DEMO CATALOG • PAYPAL SANDBOX
                        </span>
                      </div>
                      <h3 style={{ fontSize: '1.15rem', fontWeight: 800, color: '#f8fafc', margin: 0 }}>
                        {sub.plan_name}
                      </h3>
                      <p style={{ fontSize: '0.9rem', color: '#94a3b8', margin: '4px 0 0' }}>
                        Provider: {sub.provider} • PayPal Subscription ID: <code style={{ color: '#e2e8f0' }}>{sub.paypal_subscription_id}</code>
                      </p>
                    </div>

                    <div style={{ textAlign: 'right' }}>
                      <p style={{ fontSize: '1.35rem', fontWeight: 800, color: '#fcd34d', margin: 0 }}>
                        ${sub.recurring_amount.toFixed(2)}{' '}
                        <span style={{ fontSize: '0.85rem', fontWeight: 700 }}>/ {sub.billing_frequency}</span>
                      </p>
                      <p style={{ fontSize: '0.8rem', color: '#94a3b8', margin: '2px 0 0' }}>
                        Due at signup: ${sub.amount_due_today.toFixed(2)}
                      </p>
                    </div>
                  </div>

                  {!isCancelled && (
                    <div style={{ display: 'flex', flexWrap: 'wrap', gap: '10px', paddingTop: '6px' }}>
                      <button
                        type="button"
                        onClick={() => {
                          setCancellingSubId(isPromptingCancel ? null : sub.subscription_id);
                          setCancelPhrase('');
                          setErrorMsg(null);
                        }}
                        style={{
                          display: 'inline-flex',
                          alignItems: 'center',
                          gap: '6px',
                          padding: '8px 14px',
                          borderRadius: '10px',
                          border: '1px solid #ef4444',
                          backgroundColor: '#450a0a',
                          color: '#fecaca',
                          fontWeight: 700,
                          fontSize: '0.85rem',
                          cursor: 'pointer',
                        }}
                      >
                        <XCircle size={15} aria-hidden="true" />
                        {isPromptingCancel ? 'Close Cancellation' : 'Cancel Subscription'}
                      </button>
                    </div>
                  )}

                  {isPromptingCancel && !isCancelled && (
                    <div
                      style={{
                        backgroundColor: '#0f172a',
                        border: '1px solid #ef4444',
                        borderRadius: '12px',
                        padding: '14px',
                        marginTop: '4px',
                      }}
                    >
                      <p style={{ margin: '0 0 8px', fontSize: '0.88rem', color: '#fecaca', fontWeight: 600 }}>
                        Explicit cancellation confirmation required. Type or say:
                        <br />
                        <code style={{ color: '#fde68a' }}>{expectedCancelPhrase}</code>
                      </p>
                      <div style={{ display: 'flex', flexWrap: 'wrap', gap: '8px' }}>
                        <input
                          type="text"
                          value={cancelPhrase}
                          onChange={(e) => setCancelPhrase(e.target.value)}
                          placeholder={expectedCancelPhrase}
                          aria-label="Subscription cancellation confirmation phrase"
                          style={{
                            flex: 1,
                            minWidth: '220px',
                            padding: '9px 12px',
                            borderRadius: '8px',
                            border: '1px solid #334155',
                            backgroundColor: '#020617',
                            color: '#f8fafc',
                            fontSize: '0.88rem',
                          }}
                        />
                        <button
                          type="button"
                          disabled={cancelBusy}
                          onClick={async () => {
                            setCancelBusy(true);
                            setErrorMsg(null);
                            try {
                              const updated = await api.cancelSubscription(sub.subscription_id, cancelPhrase);
                              setSubscriptions((prev) =>
                                prev.map((item) => (item.subscription_id === updated.subscription_id ? updated : item))
                              );
                              setCancellingSubId(null);
                              setCancelPhrase('');
                              announce(`Subscription ${sub.plan_name} has been cancelled.`);
                            } catch (err: any) {
                              const msg = err?.message || 'Unable to cancel subscription.';
                              setErrorMsg(msg);
                              announce(msg, true);
                            } finally {
                              setCancelBusy(false);
                            }
                          }}
                          style={{
                            padding: '9px 16px',
                            borderRadius: '8px',
                            border: 'none',
                            backgroundColor: '#dc2626',
                            color: '#ffffff',
                            fontWeight: 700,
                            fontSize: '0.88rem',
                            cursor: cancelBusy ? 'not-allowed' : 'pointer',
                          }}
                        >
                          {cancelBusy ? 'Cancelling...' : 'Confirm Cancellation'}
                        </button>
                      </div>
                    </div>
                  )}
                </article>
              );
            })
          )}
        </div>
      ) : orders.length === 0 ? (
        <div
          style={{
            backgroundColor: '#111827',
            borderRadius: '16px',
            padding: '28px 24px',
            textAlign: 'center',
            color: '#cbd5e1',
            border: '1px solid #1e293b',
          }}
        >
          <p style={{ fontSize: '1.05rem', fontWeight: 700, color: '#f8fafc', margin: 0 }}>
            No completed orders yet.
          </p>
        </div>
      ) : (
        <div style={{ display: 'flex', flexDirection: 'column', gap: '16px' }}>
          <ContextualVoiceTips
            commands={[
              'Open my last order',
              'What was my total?',
              'What did I buy?',
              'Buy this again',
            ]}
          />
          {orders.map((order) => {
            const isExpanded = Boolean(expandedOrderIds[order.order_id]);
            const lineItems = order.items && order.items.length > 0 ? order.items : [];
            const itemCount =
              lineItems.length > 0
                ? lineItems.reduce((sum, it) => sum + (it.quantity || 1), 0)
                : order.quantity || 1;
            const isPayPalSandbox = Boolean(order.paypal_order_id) || order.payment_status.toLowerCase().includes('sandbox');

            return (
              <article
                key={order.order_id}
                data-order-id={order.order_id}
                style={{
                  backgroundColor: '#111827',
                  border: selectedOrderId === order.order_id ? '2px solid #38bdf8' : '2px solid #334155',
                  borderRadius: '18px',
                  padding: '20px 22px',
                  display: 'flex',
                  flexDirection: 'column',
                  gap: '14px',
                }}
              >
                <div
                  style={{
                    display: 'flex',
                    flexWrap: 'wrap',
                    justifyContent: 'space-between',
                    alignItems: 'flex-start',
                    gap: '14px',
                  }}
                >
                  <div style={{ flex: 1, minWidth: '240px' }}>
                    <div
                      style={{
                        display: 'flex',
                        flexWrap: 'wrap',
                        alignItems: 'center',
                        gap: '10px',
                        marginBottom: '6px',
                      }}
                    >
                      <span
                        style={{
                          fontSize: '0.82rem',
                          fontWeight: 700,
                          color: '#38bdf8',
                          backgroundColor: '#0c4a6e',
                          padding: '3px 10px',
                          borderRadius: '9999px',
                        }}
                      >
                        {order.date}
                      </span>
                      <span
                        style={{
                          fontSize: '0.82rem',
                          fontWeight: 700,
                          color: '#cbd5e1',
                          backgroundColor: '#1e293b',
                          padding: '3px 10px',
                          borderRadius: '9999px',
                        }}
                      >
                        {itemCount} {itemCount === 1 ? 'item' : 'items'}
                      </span>
                      {isPayPalSandbox && (
                        <span
                          style={{
                            fontSize: '0.82rem',
                            fontWeight: 700,
                            color: '#6ee7b7',
                            backgroundColor: '#064e3b',
                            padding: '3px 10px',
                            borderRadius: '9999px',
                            display: 'inline-flex',
                            alignItems: 'center',
                            gap: '4px',
                          }}
                        >
                          <ShieldCheck size={13} />
                          <span>PayPal Sandbox</span>
                        </span>
                      )}
                    </div>

                    <h3
                      style={{
                        fontSize: '1.12rem',
                        fontWeight: 800,
                        color: '#f8fafc',
                        margin: '0 0 4px',
                      }}
                    >
                      {order.product_title}
                    </h3>
                    <div style={{ color: '#94a3b8', fontSize: '0.92rem' }}>
                      Merchant: {order.merchant} | Status: {order.payment_status} | Order ID:{' '}
                      <span style={{ color: '#cbd5e1', fontFamily: 'monospace' }}>{order.order_id}</span>
                    </div>
                  </div>

                  <div style={{ textAlign: 'right' }}>
                    <div style={{ fontSize: '1.35rem', fontWeight: 900, color: '#38bdf8' }}>
                      ${order.total.toFixed(2)}
                    </div>
                    <div style={{ display: 'flex', gap: '8px', marginTop: '10px', flexWrap: 'wrap', justifyContent: 'flex-end' }}>
                      <button
                        type="button"
                        aria-expanded={isExpanded}
                        onClick={() => toggleDetails(order.order_id)}
                        style={{
                          backgroundColor: '#1e293b',
                          color: '#f8fafc',
                          border: '1px solid #475569',
                          borderRadius: '10px',
                          padding: '10px 14px',
                          fontWeight: 700,
                          display: 'inline-flex',
                          alignItems: 'center',
                          gap: '6px',
                        }}
                      >
                        <Package size={15} />
                        <span>{isExpanded ? 'Hide Details' : 'Details'}</span>
                        {isExpanded ? <ChevronUp size={15} /> : <ChevronDown size={15} />}
                      </button>

                      <button
                        type="button"
                        disabled={busyOrderId === order.order_id}
                        onClick={() => handleBuyAgain(order)}
                        aria-label={`Buy again from order ${order.order_id}`}
                        style={{
                          backgroundColor: '#0284c7',
                          color: '#ffffff',
                          border: 'none',
                          borderRadius: '10px',
                          padding: '10px 16px',
                          fontWeight: 700,
                          display: 'inline-flex',
                          alignItems: 'center',
                          gap: '6px',
                        }}
                      >
                        <RefreshCw size={15} />
                        <span>{busyOrderId === order.order_id ? 'Preparing...' : 'Buy Again'}</span>
                      </button>
                    </div>
                  </div>
                </div>

                {isExpanded && (
                  <div
                    style={{
                      backgroundColor: '#0f172a',
                      border: '1px solid #334155',
                      borderRadius: '12px',
                      padding: '14px 16px',
                      display: 'flex',
                      flexDirection: 'column',
                      gap: '10px',
                    }}
                  >
                    <div style={{ fontWeight: 700, color: '#e2e8f0', fontSize: '0.95rem' }}>
                      Items in this order
                    </div>
                    {lineItems.length > 0 ? (
                      <ul style={{ listStyle: 'none', margin: 0, padding: 0, display: 'flex', flexDirection: 'column', gap: '8px' }}>
                        {lineItems.map((it, idx) => (
                          <li
                            key={`${it.product_id}-${idx}`}
                            style={{
                              display: 'flex',
                              justifyContent: 'space-between',
                              gap: '12px',
                              color: '#cbd5e1',
                              fontSize: '0.94rem',
                              borderBottom: '1px solid #1e293b',
                              paddingBottom: '6px',
                            }}
                          >
                            <span>
                              {it.product_title} ({it.merchant}) × {it.quantity} @ ${it.unit_price.toFixed(2)}
                            </span>
                            <strong style={{ color: '#f8fafc' }}>${it.line_total.toFixed(2)}</strong>
                          </li>
                        ))}
                      </ul>
                    ) : (
                      <div style={{ color: '#cbd5e1', fontSize: '0.94rem' }}>
                        {order.product_title} × {order.quantity} — ${order.item_price.toFixed(2)} each
                      </div>
                    )}

                    <div
                      style={{
                        display: 'flex',
                        flexWrap: 'wrap',
                        justifyContent: 'space-between',
                        gap: '12px',
                        paddingTop: '6px',
                        color: '#94a3b8',
                        fontSize: '0.9rem',
                      }}
                    >
                      <span>
                        Subtotal: ${(order.item_subtotal ?? order.item_price * order.quantity).toFixed(2)} | Shipping: ${order.shipping.toFixed(2)} | Tax: ${order.tax.toFixed(2)}
                      </span>
                      <span>
                        Confirmation: {order.confirmation_method}
                        {order.paypal_order_id ? ` | PayPal Order: ${order.paypal_order_id}` : ''}
                        {order.paypal_capture_id ? ` | Capture: ${order.paypal_capture_id}` : ''}
                      </span>
                    </div>
                    <ContextualVoiceTips
                      commands={['Read this order', "What's the total?", 'Buy this again']}
                    />
                  </div>
                )}
              </article>
            );
          })}
        </div>
      )}
    </section>
  );
};
