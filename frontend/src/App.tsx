import React, { useEffect, useState, useCallback, useRef } from 'react';
import { AccessibilityProvider, useAccessibility } from './context/AccessibilityContext';
import { CartProvider, useCart } from './context/CartContext';
import { VoiceCommandProvider, useVoiceCommand } from './context/VoiceCommandContext';
import { Header, PrimaryTab } from './components/layout/Header';
import { LiveAnnouncer } from './components/layout/LiveAnnouncer';
import { ShoppingView, ShopVoiceController } from './components/pages/ShoppingView';
import { SavedView } from './components/pages/SavedView';
import { OrdersView } from './components/pages/OrdersView';
import { CartView } from './components/pages/CartView';
import { DevelopersView } from './components/pages/DevelopersView';
import { api } from './services/api';
import { AppViewName, PurchaseReview } from './types';
import { Volume2 } from 'lucide-react';

interface NavEntry {
  tab: PrimaryTab;
  savedSubTab?: 'items' | 'searches';
}

const AppContent: React.FC = () => {
  const { cart, cancelPurchase, clearCart, refreshCart } = useCart();
  const { announce } = useAccessibility();
  const {
    voiceStatus,
    voiceFeedback,
    voiceError,
    lastTranscript,
    clearVoiceFeedback,
    registerVoiceHandler,
  } = useVoiceCommand();

  const [activeTab, setActiveTab] = useState<PrimaryTab>('shop');
  const [showDevelopers, setShowDevelopers] = useState<boolean>(() =>
    typeof window !== 'undefined' && window.location.pathname === '/developers'
  );
  const [savedSubTab, setSavedSubTab] = useState<'items' | 'searches'>('items');

  useEffect(() => {
    if (typeof window === 'undefined') return;
    const onPopState = () => {
      setShowDevelopers(window.location.pathname === '/developers');
    };
    window.addEventListener('popstate', onPopState);
    return () => window.removeEventListener('popstate', onPopState);
  }, []);

  const openDevelopersPage = useCallback(() => {
    if (typeof window !== 'undefined' && window.location.pathname !== '/developers') {
      window.history.pushState({}, '', '/developers');
    }
    setShowDevelopers(true);
  }, []);

  const closeDevelopersPage = useCallback(() => {
    if (typeof window !== 'undefined' && window.location.pathname === '/developers') {
      window.history.pushState({}, '', '/');
    }
    setShowDevelopers(false);
  }, []);
  const [selectedSavedItemId, setSelectedSavedItemId] = useState<string | null>(null);
  const [selectedOrderId, setSelectedOrderId] = useState<string | null>(null);
  const [ordersInitialTab, setOrdersInitialTab] = useState<'purchases' | 'subscriptions'>('purchases');
  const [savedProductIds, setSavedProductIds] = useState<Set<string>>(new Set());
  const [savedReloadNonce, setSavedReloadNonce] = useState<number>(0);
  const [ordersReloadNonce, setOrdersReloadNonce] = useState<number>(0);
  const [externalSearchSignal, setExternalSearchSignal] = useState<{ result: any; nonce: number } | null>(null);
  const [externalReviewSignal, setExternalReviewSignal] = useState<{
    review: PurchaseReview;
    message?: string;
    nonce: number;
  } | null>(null);

  const shopControllerRef = useRef<ShopVoiceController | null>(null);
  const navHistoryRef = useRef<NavEntry[]>([]);
  const activeTabRef = useRef<PrimaryTab>(activeTab);
  const savedSubTabRef = useRef<'items' | 'searches'>(savedSubTab);
  const ordersInitialTabRef = useRef<'purchases' | 'subscriptions'>(ordersInitialTab);
  const selectedSavedItemIdRef = useRef<string | null>(selectedSavedItemId);
  const selectedOrderIdRef = useRef<string | null>(selectedOrderId);

  activeTabRef.current = activeTab;
  savedSubTabRef.current = savedSubTab;
  ordersInitialTabRef.current = ordersInitialTab;
  selectedSavedItemIdRef.current = selectedSavedItemId;
  selectedOrderIdRef.current = selectedOrderId;

  const loadSavedIds = useCallback(() => {
    api.getSavedItems()
      .then((items) => setSavedProductIds(new Set(items.map((it) => it.product_id))))
      .catch(() => {});
  }, []);

  useEffect(() => {
    loadSavedIds();
  }, [loadSavedIds]);

  const navigateTo = useCallback(
    (tab: PrimaryTab, subTab?: 'items' | 'searches', recordHistory = true) => {
      closeDevelopersPage();
      if (recordHistory) {
        const cur = activeTabRef.current;
        const curSub = savedSubTabRef.current;
        if (cur !== tab || (tab === 'saved' && subTab && curSub !== subTab)) {
          navHistoryRef.current.push({ tab: cur, savedSubTab: curSub });
          if (navHistoryRef.current.length > 20) navHistoryRef.current.shift();
        }
      }
      if (subTab) {
        setSavedSubTab(subTab);
      }
      setActiveTab(tab);
      if (tab === 'saved') {
        loadSavedIds();
        setSavedReloadNonce((n) => n + 1);
      } else if (tab === 'orders') {
        setOrdersReloadNonce((n) => n + 1);
      } else if (tab === 'cart') {
        refreshCart();
      }
    },
    [loadSavedIds, refreshCart, closeDevelopersPage]
  );

  // Escape key global listener for accessible cancellation on active checkout
  useEffect(() => {
    const handleKeyDown = (e: KeyboardEvent) => {
      if (e.key === 'Escape') {
        const shopView = shopControllerRef.current?.getViewContext().currentView;
        if (
          shopView &&
          ['PURCHASE_REVIEW', 'CONFIRMATION_REQUIRED', 'PAYPAL_CHECKOUT', 'PAYMENT_FAILURE'].includes(shopView)
        ) {
          cancelPurchase();
          announce('Purchase cancelled via Escape key. No payment was made.');
        }
      }
    };
    window.addEventListener('keydown', handleKeyDown);
    return () => window.removeEventListener('keydown', handleKeyDown);
  }, [cancelPurchase, announce]);

  const handleReset = async () => {
    try {
      await api.resetDemo();
      await clearCart();
      await cancelPurchase();
      await refreshCart();
      setSavedProductIds(new Set());
      setSelectedSavedItemId(null);
      setSelectedOrderId(null);
      navHistoryRef.current = [];
      clearVoiceFeedback();
      setActiveTab('shop');
      announce('Demo reset complete. Shopping session, cart, and confirmation state cleared.');
    } catch {
      announce('Shopping assistant reset.');
    }
    window.dispatchEvent(new CustomEvent('accesspay-reset'));
  };

  const handleOpenSaved = useCallback(
    (subtab: 'items' | 'searches' = 'items') => {
      navigateTo('saved', subtab, true);
    },
    [navigateTo]
  );

  const handleReopenSearch = (searchResult: any) => {
    setExternalSearchSignal({ result: searchResult, nonce: Date.now() });
    navigateTo('shop', undefined, true);
  };

  const handleReorderReview = (review: PurchaseReview, message: string) => {
    setExternalReviewSignal({ review, message, nonce: Date.now() });
    navigateTo('shop', undefined, true);
  };

  const handleCartProceedToReview = (review: PurchaseReview) => {
    navigateTo('shop', undefined, true);
    shopControllerRef.current?.openPurchaseReview(
      review,
      `Purchase review ready for $${review.total_today.toFixed(2)}.`
    );
  };

  // Register unified app-level Voice Command Handler across ALL views
  useEffect(() => {
    return registerVoiceHandler({
      getContext: () => {
        const tab = activeTabRef.current;
        if (tab === 'shop') {
          return (
            shopControllerRef.current?.getViewContext() || {
              currentView: 'SHOP',
            }
          );
        }
        if (tab === 'saved') {
          const itemIds = Array.from(document.querySelectorAll('[data-saved-item-id]'))
            .map((el) => el.getAttribute('data-saved-item-id') || '')
            .filter(Boolean);
          const searchIds = Array.from(document.querySelectorAll('[data-saved-search-id]'))
            .map((el) => el.getAttribute('data-saved-search-id') || '')
            .filter(Boolean);
          return {
            currentView: savedSubTabRef.current === 'searches' ? 'SAVED_SEARCHES' : 'SAVED_ITEMS',
            visibleSavedItemIds: itemIds,
            visibleSavedSearchIds: searchIds,
            selectedSavedItemId: selectedSavedItemIdRef.current,
          };
        }
        if (tab === 'orders') {
          const orderIds = Array.from(document.querySelectorAll('[data-order-id]'))
            .map((el) => el.getAttribute('data-order-id') || '')
            .filter(Boolean);
          return {
            currentView:
              ordersInitialTabRef.current === 'subscriptions'
                ? 'SUBSCRIPTIONS'
                : selectedOrderIdRef.current
                ? 'ORDER_DETAILS'
                : 'ORDERS',
            visibleOrderIds: orderIds,
            selectedOrderId: selectedOrderIdRef.current,
          };
        }
        const cartIds = Array.from(document.querySelectorAll('[data-cart-product-id]'))
          .map((el) => el.getAttribute('data-cart-product-id') || '')
          .filter(Boolean);
        return {
          currentView: 'CART',
          visibleCartProductIds: cartIds,
        };
      },

      onIntentResult: async (res: any) => {
        const action = res?.action || 'INFO';
        const msg = res?.speech_response || res?.message || '';

        if (action === 'OPEN_SHOP') {
          navigateTo('shop', undefined, true);
          await shopControllerRef.current?.applyIntentResult(res);
          return 'SHOP';
        }

        if (action === 'OPEN_CART' || action === 'VIEW_CART') {
          await refreshCart();
          navigateTo('cart', undefined, true);
          if (msg) announce(msg);
          return 'CART';
        }

        if (action === 'CART_UPDATED') {
          await refreshCart();
          if (msg) announce(msg);
          return activeTabRef.current === 'cart' ? 'CART' : 'SHOP';
        }

        if (action === 'OPEN_SAVED_ITEMS') {
          navigateTo('saved', 'items', true);
          if (msg) announce(msg);
          return 'SAVED_ITEMS';
        }

        if (action === 'OPEN_SAVED_SEARCHES') {
          navigateTo('saved', 'searches', true);
          if (msg) announce(msg);
          return 'SAVED_SEARCHES';
        }

        if (action === 'OPEN_SAVED_ITEM') {
          setSelectedSavedItemId(res.saved_item_id || null);
          navigateTo('saved', 'items', true);
          if (msg) announce(msg);
          return 'SAVED_ITEMS';
        }

        if (action === 'SAVED_ITEM_ADDED_TO_CART') {
          await refreshCart();
          setSavedReloadNonce((n) => n + 1);
          if (msg) announce(msg);
          return activeTabRef.current === 'saved' ? 'SAVED_ITEMS' : 'CART';
        }

        if (action === 'SAVED_ITEM_REMOVED') {
          loadSavedIds();
          setSavedReloadNonce((n) => n + 1);
          await shopControllerRef.current?.applyIntentResult(res);
          if (msg) announce(msg);
          return activeTabRef.current === 'saved' ? 'SAVED_ITEMS' : 'SHOP';
        }

        if (action === 'OPEN_ORDERS') {
          setSelectedOrderId(null);
          navigateTo('orders', undefined, true);
          if (msg) announce(msg);
          return 'ORDERS';
        }

        if (action === 'OPEN_ORDER') {
          setSelectedOrderId(res.order_id || null);
          navigateTo('orders', undefined, true);
          if (msg) announce(msg);
          return res.order_id ? 'ORDER_DETAILS' : 'ORDERS';
        }

        if (action === 'ORDER_DETAILS' || action === 'READ_ORDER_ID') {
          if (res.order_id) {
            setSelectedOrderId(res.order_id);
          }
          if (activeTabRef.current !== 'orders' && res.order_id) {
            navigateTo('orders', undefined, true);
          }
          if (msg) announce(msg);
          return 'ORDER_DETAILS';
        }

        if (action === 'NAVIGATE_BACK') {
          if (activeTabRef.current !== 'shop') {
            const prev = navHistoryRef.current.pop();
            if (prev) {
              navigateTo(prev.tab, prev.savedSubTab, false);
              announce(`Returned to ${prev.tab}.`);
              return prev.tab.toUpperCase() as AppViewName;
            }
            navigateTo('shop', undefined, false);
            announce('Returned to Shop.');
            return 'SHOP';
          }
          await shopControllerRef.current?.applyIntentResult(res);
          return shopControllerRef.current?.getViewContext().currentView || 'SHOP';
        }

        if (action === 'SUBSCRIPTION_VOICE_INTENT') {
          const subIntent = res.subscriptionIntent;
          if (subIntent?.kind === 'open_subscriptions') {
            setOrdersInitialTab('subscriptions');
            navigateTo('orders', undefined, true);
            announce('Showing your subscriptions.');
            return 'SUBSCRIPTIONS';
          }
          if (subIntent?.kind === 'open_purchases') {
            setOrdersInitialTab('purchases');
            navigateTo('orders', undefined, true);
            announce('Showing your one-time purchases.');
            return 'ORDERS';
          }
          if (subIntent?.kind === 'subscription_record_qa') {
            const subs = await api.listSubscriptions().catch(() => []);
            const target = subs.find((s) => s.status === 'ACTIVE') || subs[0];
            if (!target) {
              announce('You have no subscriptions on file.');
            } else if ((subIntent.question || '').toLowerCase().includes('often')) {
              announce(`Your ${target.plan_name} subscription is billed ${target.billing_frequency} at $${target.recurring_amount.toFixed(2)}.`);
            } else {
              announce(`Your ${target.plan_name} subscription is $${target.recurring_amount.toFixed(2)} ${target.billing_frequency} (${target.status}).`);
            }
            return 'SUBSCRIPTIONS';
          }
          if (subIntent?.kind === 'cancel_subscription_start' && activeTabRef.current === 'orders') {
            const subs = await api.listSubscriptions().catch(() => []);
            const target = subs.find((s) => s.status !== 'CANCELLED');
            if (!target) {
              announce('No active subscription found to cancel.');
            } else {
              setOrdersInitialTab('subscriptions');
              announce(`To cancel ${target.plan_name}, say or type: Confirm cancellation of ${target.plan_name}.`);
            }
            return 'SUBSCRIPTIONS';
          }
          if (subIntent?.kind === 'cancel_subscription_confirm') {
            const subs = await api.listSubscriptions().catch(() => []);
            const target = subs.find((s) => s.status !== 'CANCELLED');
            if (!target) {
              announce('No active subscription found to cancel.');
              return 'SUBSCRIPTIONS';
            }
            try {
              await api.cancelSubscription(target.subscription_id, subIntent.phrase);
              setOrdersInitialTab('subscriptions');
              setOrdersReloadNonce((n) => n + 1);
              announce(`Subscription ${target.plan_name} has been cancelled.`);
            } catch (err: any) {
              announce(err?.message || `Please say: Confirm cancellation of ${target.plan_name}.`, true);
            }
            return 'SUBSCRIPTIONS';
          }
          if (activeTabRef.current !== 'shop') {
            navigateTo('shop', undefined, true);
          }
          await shopControllerRef.current?.applyIntentResult(res);
          return shopControllerRef.current?.getViewContext().currentView || 'SHOP';
        }

        if (action === 'SHOW_RECENT_SEARCHES') {
          navigateTo('shop', undefined, true);
          await shopControllerRef.current?.applyIntentResult(res);
          return 'SHOP';
        }

        if (action === 'RECENT_SEARCH_SAVED') {
          setSavedReloadNonce((n) => n + 1);
          await shopControllerRef.current?.applyIntentResult(res);
          return activeTabRef.current === 'saved' ? 'SAVED_SEARCHES' : 'SHOP';
        }

        if (action === 'RECENT_SEARCH_CLEARED') {
          setSavedReloadNonce((n) => n + 1);
          await shopControllerRef.current?.applyIntentResult(res);
          return activeTabRef.current === 'saved' ? 'SAVED_SEARCHES' : 'SHOP';
        }

        // Actions that transition into Shop results, review, confirmation, PayPal, or payment retry
        const shopTransitionActions = new Set([
          'SEARCH_RESULTS',
          'COMPARE',
          'CHEAPER_ALTERNATIVE_FOUND',
          'PRODUCT_SELECTED',
          'PAYMENT_REVIEW_READY',
          'TOTAL_SUMMARY',
          'READ_REVIEW',
          'PROCEED_TO_CONFIRMATION',
          'PAYMENT_CONFIRMED',
          'PAYPAL_APPROVAL_NAVIGATION',
          'RETRY_PAYMENT',
          'CANCELLED',
        ]);

        if (shopTransitionActions.has(action)) {
          if (activeTabRef.current !== 'shop') {
            navigateTo('shop', undefined, true);
          }
          await shopControllerRef.current?.applyIntentResult(res);
          return shopControllerRef.current?.getViewContext().currentView || 'SHOP';
        }

        // Stay on current tab if non-Shop view got an INFO/guard reply; otherwise forward to Shop
        if (activeTabRef.current === 'shop') {
          await shopControllerRef.current?.applyIntentResult(res);
          return shopControllerRef.current?.getViewContext().currentView || 'SHOP';
        }

        if (msg) announce(msg);
        return activeTabRef.current === 'orders'
          ? 'ORDERS'
          : activeTabRef.current === 'cart'
          ? 'CART'
          : savedSubTabRef.current === 'searches'
          ? 'SAVED_SEARCHES'
          : 'SAVED_ITEMS';
      },
    });
  }, [announce, loadSavedIds, navigateTo, refreshCart, registerVoiceHandler]);

  const cartItemCount = cart?.item_count || 0;

  return (
    <div style={{ minHeight: '100vh', display: 'flex', flexDirection: 'column', backgroundColor: '#0a0f1d' }}>
      <LiveAnnouncer />

      <Header
        activeTab={activeTab}
        onSelectTab={(tab) => navigateTo(tab, tab === 'saved' ? savedSubTab : undefined, true)}
        savedCount={savedProductIds.size}
        cartCount={cartItemCount}
      />

      {/* Global voice response banner when viewing Saved / Orders / Cart */}
      {activeTab !== 'shop' && (voiceStatus !== 'idle' || voiceFeedback || voiceError) && (
        <div
          role="status"
          aria-live="polite"
          style={{
            maxWidth: '1040px',
            width: 'calc(100% - 40px)',
            margin: '14px auto 0',
            backgroundColor: voiceError ? '#451a03' : '#0f172a',
            border: voiceError ? '1px solid #f59e0b' : '1px solid #38bdf8',
            borderRadius: '14px',
            padding: '12px 16px',
            display: 'flex',
            alignItems: 'center',
            justifyContent: 'space-between',
            gap: '12px',
            color: '#f8fafc',
          }}
        >
          <div style={{ display: 'flex', alignItems: 'center', gap: '10px' }}>
            <Volume2 size={18} color={voiceError ? '#fbbf24' : '#38bdf8'} style={{ flexShrink: 0 }} />
            <div style={{ fontSize: '0.96rem', fontWeight: 500 }}>
              {lastTranscript && (
                <span style={{ color: '#94a3b8', marginRight: '8px' }}>&ldquo;{lastTranscript}&rdquo; &rarr;</span>
              )}
              <span>
                {voiceStatus === 'listening'
                  ? 'Listening...'
                  : voiceStatus === 'processing'
                  ? 'Processing voice command...'
                  : voiceError || voiceFeedback}
              </span>
            </div>
          </div>
          <button
            type="button"
            onClick={clearVoiceFeedback}
            style={{
              backgroundColor: 'transparent',
              border: '1px solid #334155',
              color: '#94a3b8',
              borderRadius: '8px',
              padding: '4px 10px',
              fontSize: '0.8rem',
              minHeight: '32px',
            }}
          >
            Dismiss
          </button>
        </div>
      )}

      {/* Main Views (ShoppingView stays mounted so search & checkout session never resets across tabs) */}
      <main style={{ flex: 1 }}>
        {showDevelopers ? (
          <DevelopersView onBackToShop={() => navigateTo('shop', undefined, false)} />
        ) : null}
        <div style={{ display: !showDevelopers && activeTab === 'shop' ? 'block' : 'none' }}>
          <ShoppingView
            isActiveTab={activeTab === 'shop'}
            onNavigateSaved={handleOpenSaved}
            onNavigateOrders={() => navigateTo('orders', undefined, true)}
            onNavigateCart={() => navigateTo('cart', undefined, true)}
            externalSearchSignal={externalSearchSignal}
            externalReviewSignal={externalReviewSignal}
            savedProductIds={savedProductIds}
            onSavedChanged={setSavedProductIds}
            onOrderCompleted={() => setOrdersReloadNonce((n) => n + 1)}
            onRegisterShopController={(ctrl) => {
              shopControllerRef.current = ctrl;
            }}
          />
        </div>
        {!showDevelopers && activeTab === 'saved' && (
          <SavedView
            initialSubTab={savedSubTab}
            onReopenSearch={handleReopenSearch}
            onSavedChanged={setSavedProductIds}
            selectedSavedItemId={selectedSavedItemId}
            onSelectSavedItem={setSelectedSavedItemId}
            onSubTabChange={setSavedSubTab}
            reloadNonce={savedReloadNonce}
          />
        )}
        {!showDevelopers && activeTab === 'orders' && (
          <OrdersView
            onReorderReview={handleReorderReview}
            selectedOrderId={selectedOrderId}
            onSelectOrder={setSelectedOrderId}
            reloadNonce={ordersReloadNonce}
            initialTab={ordersInitialTab}
            onTabChange={setOrdersInitialTab}
          />
        )}
        {!showDevelopers && activeTab === 'cart' && (
          <CartView
            onProceedToReview={handleCartProceedToReview}
            onBackToShop={() => navigateTo('shop', undefined, true)}
          />
        )}
      </main>

      <footer
        style={{
          borderTop: '1px solid #1e293b',
          padding: '24px 20px',
          textAlign: 'center',
          fontSize: '0.85rem',
          color: '#64748b',
          backgroundColor: '#0a0f1d',
        }}
      >
        <div
          style={{
            maxWidth: '1100px',
            margin: '0 auto',
            display: 'flex',
            justifyContent: 'center',
            alignItems: 'center',
            gap: '14px',
            flexWrap: 'wrap',
          }}
        >
          <span>
            <strong>AccessPay AI</strong> &bull; Voice-First Accessible AI Shopping Assistant &bull;{' '}
            <em>AI does the navigating. You make the decisions.</em>
          </span>
          <button
            type="button"
            onClick={openDevelopersPage}
            style={{
              backgroundColor: 'transparent',
              border: '1px solid #334155',
              color: '#94a3b8',
              padding: '4px 12px',
              borderRadius: '999px',
              fontSize: '0.78rem',
              fontWeight: 600,
              minHeight: '30px',
            }}
            aria-label="For Developers"
          >
            For Developers
          </button>
          <button
            type="button"
            onClick={handleReset}
            style={{
              backgroundColor: 'transparent',
              border: '1px solid #334155',
              color: '#94a3b8',
              padding: '4px 12px',
              borderRadius: '999px',
              fontSize: '0.78rem',
              fontWeight: 600,
              minHeight: '30px',
            }}
            aria-label="Reset Demo"
          >
            Reset Demo
          </button>
        </div>
      </footer>
    </div>
  );
};

export default function App() {
  return (
    <AccessibilityProvider>
      <CartProvider>
        <VoiceCommandProvider>
          <AppContent />
        </VoiceCommandProvider>
      </CartProvider>
    </AccessibilityProvider>
  );
}
