import React, { useState, useEffect, useRef, useCallback, useMemo } from 'react';
import { AppViewName, Product, PurchaseReview, PayPalOrderCreationResponse, OrderLineItem, SearchHistoryEntry, SubscriptionOffer, SubscriptionReview, SubscriptionRecord } from '../../types';
import { api, InteractionInputMode, SAFE_PAYMENT_ERROR_MESSAGE } from '../../services/api';
import { useAccessibility } from '../../context/AccessibilityContext';
import { useCart } from '../../context/CartContext';
import { useVoiceCommand, useRegisterVoiceControls } from '../../context/VoiceCommandContext';
import { VoiceControlDescriptor } from '../../utils/voiceControlMatcher';
import { ProductCard } from '../shopping/ProductCard';
import { SubscriptionCard } from '../shopping/SubscriptionCard';
import { ContextualVoiceTips } from '../common/ContextualVoiceTips';
import { getCanonicalFrontendOrigin } from '../../utils/origin';
import { parseSubscriptionVoiceIntent } from '../../utils/subscriptionVoiceCommands';
import {
  Search,
  Volume2,
  CheckCircle2,
  AlertCircle,
  ShieldCheck,
  ShieldAlert,
  AlertTriangle,
  Layers,
  Sparkles,
  Lock,
  Bookmark,
  PlusCircle,
  Mic,
  CreditCard,
  History,
  Repeat,
  ExternalLink,
} from 'lucide-react';

export interface ShopVoiceController {
  getViewContext: () => {
    currentView: AppViewName;
    activeSearchId: string | null;
    searchGeneration: number;
    visibleProductIds: string[];
  };
  applyIntentResult: (res: any, rawTranscript?: string) => Promise<void>;
  openPurchaseReview: (review: PurchaseReview, message?: string) => void;
  setShopStepSearch: () => void;
}

interface ShoppingViewProps {
  isActiveTab?: boolean;
  onNavigateSaved?: (subtab?: 'items' | 'searches') => void;
  onNavigateOrders?: () => void;
  onNavigateCart?: () => void;
  externalSearchSignal?: { result: any; nonce: number } | null;
  externalReviewSignal?: { review: PurchaseReview; message?: string; nonce: number } | null;
  savedProductIds?: Set<string>;
  onSavedChanged?: (ids: Set<string>) => void;
  onOrderCompleted?: () => void;
  onRegisterShopController?: (controller: ShopVoiceController | null) => void;
}

export const ShoppingView: React.FC<ShoppingViewProps> = ({
  isActiveTab = true,
  onNavigateSaved,
  onNavigateOrders,
  onNavigateCart,
  externalSearchSignal,
  externalReviewSignal,
  savedProductIds,
  onSavedChanged,
  onOrderCompleted,
  onRegisterShopController,
}) => {
  const { announce } = useAccessibility();
  const { voiceStatus, voiceError } = useVoiceCommand();
  const { cart, addToCart, prepareReview, confirmPurchase, cancelPurchase, refreshCart } = useCart();

  // Search & Voice state (listening state comes from global VoiceCommandProvider)
  const [queryInput, setQueryInput] = useState<string>('');
  const [hasUserSearched, setHasUserSearched] = useState<boolean>(false);
  const isListening = voiceStatus === 'listening';
  const [isProcessing, setIsProcessing] = useState<boolean>(false);
  const [processingLabel, setProcessingLabel] = useState<string>('Finding products...');
  const [aiMessage, setAiMessage] = useState<string>('Ready. Tap Speak in the header or type what you are looking for.');

  // Generic typed product search suggestions (debounced, cached, non-Channel3)
  const [suggestions, setSuggestions] = useState<string[]>([]);
  const [showSuggestions, setShowSuggestions] = useState<boolean>(false);
  const [activeSuggestionIdx, setActiveSuggestionIdx] = useState<number>(-1);
  const suggestionCacheRef = useRef<Map<string, string[]>>(new Map());
  const skipNextSuggestFetchRef = useRef<boolean>(false);

  // Synchronous lock to prevent duplicate payment submissions from rapid clicks/keys/voice
  const paymentInFlightRef = useRef<boolean>(false);
  // Prevent stale initial load or overlapping searches from resurrecting old products/no-results banners
  const hasUserSearchedRef = useRef<boolean>(false);
  const searchRequestSeqRef = useRef<number>(0);
  const latestSearchGenerationRef = useRef<number>(0);
  const activeSearchIdRef = useRef<string | null>(null);
  const visibleProductsRef = useRef<Product[]>([]);
  const voiceTurnCountRef = useRef<number>(0);

  // Shopping flow state + isolated Subscription Commerce state
  const [currentStep, setCurrentStep] = useState<
    | 'search'
    | 'compare'
    | 'selected'
    | 'review'
    | 'confirm'
    | 'paypal'
    | 'payment_failed'
    | 'outcome'
    | 'subscription_results'
    | 'subscription_review'
    | 'subscription_confirm'
    | 'subscription_paypal'
    | 'subscription_outcome'
  >('search');
  const [subscriptionOffers, setSubscriptionOffers] = useState<SubscriptionOffer[]>([]);
  const [selectedSubscription, setSelectedSubscription] = useState<SubscriptionOffer | null>(null);
  const [subscriptionReview, setSubscriptionReview] = useState<SubscriptionReview | null>(null);
  const [subscriptionConfirmPhrase, setSubscriptionConfirmPhrase] = useState<string>('');
  const [subscriptionConfirmError, setSubscriptionConfirmError] = useState<string | null>(null);
  const [paypalSubscription, setPaypalSubscription] = useState<SubscriptionRecord | null>(null);
  const [subscriptionOutcome, setSubscriptionOutcome] = useState<{
    success: boolean;
    message: string;
    record?: SubscriptionRecord;
  } | null>(null);
  const subscriptionOffersRef = useRef<SubscriptionOffer[]>([]);
  const selectedSubscriptionRef = useRef<SubscriptionOffer | null>(null);
  const subscriptionReviewRef = useRef<SubscriptionReview | null>(null);
  subscriptionOffersRef.current = subscriptionOffers;
  selectedSubscriptionRef.current = selectedSubscription;
  subscriptionReviewRef.current = subscriptionReview;
  const [products, setProducts] = useState<Product[]>([]);
  const [hasMoreResults, setHasMoreResults] = useState<boolean>(false);
  const [totalCandidates, setTotalCandidates] = useState<number>(0);
  const [localSavedIds, setLocalSavedIds] = useState<Set<string>>(new Set());
  const [selectedForCompare, setSelectedForCompare] = useState<Product[]>([]);
  const [comparisonData, setComparisonData] = useState<any>(null);
  const [selectedProduct, setSelectedProduct] = useState<Product | null>(null);
  const [activeReview, setActiveReview] = useState<PurchaseReview | null>(null);
  const [subscriptionAck, setSubscriptionAck] = useState<boolean>(false);
  const [cheaperAlert, setCheaperAlert] = useState<{ alternative: Product; original: Product; savings: number } | null>(null);
  const [confirmationError, setConfirmationError] = useState<string | null>(null);
  const [searchError, setSearchError] = useState<string | null>(null);
  const [noResultsMessage, setNoResultsMessage] = useState<string | null>(null);
  const [aboveBudgetOffer, setAboveBudgetOffer] = useState<{ limit: number; products: Product[] } | null>(null);
  const [searchSavedNotice, setSearchSavedNotice] = useState<string | null>(null);
  const [recentSearches, setRecentSearches] = useState<SearchHistoryEntry[]>([]);
  const [showAllRecentHistory, setShowAllRecentHistory] = useState<boolean>(false);
  const [historyNotice, setHistoryNotice] = useState<string | null>(null);
  const [busyHistoryId, setBusyHistoryId] = useState<string | null>(null);
  const [isLoadingMore, setIsLoadingMore] = useState<boolean>(false);
  const [paymentFailureMessage, setPaymentFailureMessage] = useState<string>(SAFE_PAYMENT_ERROR_MESSAGE);

  // PayPal Sandbox Checkout state
  const [paypalConfig, setPaypalConfig] = useState<{
    paypal_client_id: string;
    environment: string;
    provider: string;
    is_configured: boolean;
  } | null>(null);
  const [paypalOrder, setPaypalOrder] = useState<PayPalOrderCreationResponse | null>(null);
  const paypalButtonsContainerRef = useRef<HTMLDivElement | null>(null);
  const currentStepRef = useRef(currentStep);
  const activeReviewRef = useRef(activeReview);
  const paypalOrderRef = useRef(paypalOrder);
  const savedProductIdsRef = useRef(savedProductIds);
  const localSavedIdsRef = useRef(localSavedIds);

  currentStepRef.current = currentStep;
  activeReviewRef.current = activeReview;
  paypalOrderRef.current = paypalOrder;
  savedProductIdsRef.current = savedProductIds;
  localSavedIdsRef.current = localSavedIds;
  visibleProductsRef.current = products;

  // Final outcome state
  const [outcome, setOutcome] = useState<{
    success: boolean;
    message: string;
    orderId?: string;
    paypalOrderId?: string;
    paypalCaptureId?: string | null;
    productTitle?: string;
    merchant?: string;
    amountPaid?: number;
    itemSubtotal?: number;
    shipping?: number;
    tax?: number;
    items?: OrderLineItem[];
    isSubscription?: boolean;
  } | null>(null);

  // Load public PayPal Sandbox config on mount
  useEffect(() => {
    api.getPayPalConfig()
      .then((cfg) => setPaypalConfig(cfg))
      .catch(() => {
        setPaypalConfig({
          paypal_client_id: '',
          environment: 'sandbox',
          provider: 'mock',
          is_configured: false,
        });
      });
  }, []);

  // Handle return or cancellation redirect from PayPal Sandbox buyer approval
  useEffect(() => {
    if (typeof window === 'undefined') return;
    const params = new URLSearchParams(window.location.search);
    const ppReturn = params.get('paypal_return');
    const ppCancel = params.get('paypal_cancel');
    const ppToken = params.get('token');

    if (ppCancel !== '1' && !(ppReturn === '1' && ppToken)) {
      return;
    }

    let cancelled = false;

    if (ppCancel === '1') {
      Promise.resolve().then(() => {
        if (cancelled) return;
        if ((import.meta as any).env?.DEV) {
          console.info('[AccessPay Origin] Post-PayPal cancel window.location.origin:', window.location.origin);
        }
        window.history.replaceState({}, document.title, window.location.pathname);
        void handleCancelFlow('Payment cancelled. Nothing was charged.');
      });
      return () => {
        cancelled = true;
      };
    }

    if (ppReturn === '1' && ppToken) {
      Promise.resolve().then(async () => {
        if (cancelled) return;
        if ((import.meta as any).env?.DEV) {
          console.info('[AccessPay Origin] Post-PayPal return window.location.origin:', window.location.origin);
        }
        window.history.replaceState({}, document.title, window.location.pathname);
        setIsProcessing(true);
        setProcessingLabel('Verifying PayPal Sandbox approval...');
        try {
          const statusRes = await api.getPayPalOrderStatus(ppToken);
          if (cancelled) return;
          if (statusRes.success && (statusRes.status === 'APPROVED' || statusRes.status === 'COMPLETED')) {
            await handleCapturePayPalOrder(ppToken);
          } else {
            setPaymentFailureMessage(SAFE_PAYMENT_ERROR_MESSAGE);
            setAiMessage(SAFE_PAYMENT_ERROR_MESSAGE);
            setCurrentStep('payment_failed');
            announce('Your payment could not be completed. Nothing was charged.', true);
          }
        } catch (err) {
          if (cancelled) return;
          console.error('[AccessPay Dev Log] PayPal return verification error:', err);
          setPaymentFailureMessage(SAFE_PAYMENT_ERROR_MESSAGE);
          setAiMessage(SAFE_PAYMENT_ERROR_MESSAGE);
          setCurrentStep('payment_failed');
          announce('Your payment could not be completed. Nothing was charged.', true);
        } finally {
          if (!cancelled) {
            setIsProcessing(false);
          }
        }
      });
    }

    return () => {
      cancelled = true;
    };
  }, []);

  // Handle return or cancellation redirect from PayPal Sandbox Subscription approval (keeps mic idle)
  useEffect(() => {
    if (typeof window === 'undefined') return;
    const params = new URLSearchParams(window.location.search);
    const subReturn = params.get('paypal_sub_return');
    const subCancel = params.get('paypal_sub_cancel');
    const subId = params.get('subscription_id');

    if (subCancel !== '1' && subReturn !== '1') {
      return;
    }

    let cancelled = false;

    if (subCancel === '1') {
      Promise.resolve().then(() => {
        if (cancelled) return;
        window.history.replaceState({}, document.title, window.location.pathname);
        const msg = 'Subscription cancelled. No new subscription was created.';
        setSubscriptionOutcome({ success: false, message: msg });
        setCurrentStep('subscription_outcome');
        setAiMessage(msg);
        announce(msg);
      });
      return () => {
        cancelled = true;
      };
    }

    if (subReturn === '1') {
      Promise.resolve().then(async () => {
        if (cancelled) return;
        window.history.replaceState({}, document.title, window.location.pathname);
        setIsProcessing(true);
        setProcessingLabel('Verifying PayPal Sandbox subscription...');
        try {
          let record: SubscriptionRecord | undefined;
          if (subId) {
            record = await api.getPayPalSubscriptionStatus(subId);
          } else {
            const list = await api.listSubscriptions();
            record = list[0];
          }
          if (cancelled) return;
          if (record) {
            setPaypalSubscription(record);
            const msg =
              record.status === 'ACTIVE'
                ? `Subscription active: ${record.plan_name} ($${record.recurring_amount.toFixed(2)} ${record.billing_frequency}).`
                : `Subscription status: ${record.status} (${record.paypal_subscription_id}).`;
            setSubscriptionOutcome({ success: true, message: msg, record });
            setCurrentStep('subscription_outcome');
            setAiMessage(msg);
            announce(msg);
            onOrderCompleted?.();
          } else {
            const msg = 'Subscription approval could not be verified. Please check Orders -> Subscriptions.';
            setSubscriptionOutcome({ success: false, message: msg });
            setCurrentStep('subscription_outcome');
            setAiMessage(msg);
            announce(msg, true);
          }
        } catch {
          if (cancelled) return;
          const msg = 'Unable to verify PayPal Sandbox subscription status right now.';
          setSubscriptionOutcome({ success: false, message: msg });
          setCurrentStep('subscription_outcome');
          setAiMessage(msg);
          announce(msg, true);
        } finally {
          if (!cancelled) {
            setIsProcessing(false);
          }
        }
      });
    }

    return () => {
      cancelled = true;
    };
  }, []);

  // Cancel action (accessible anytime before capture)
  const handleCancelFlow = useCallback(async (customMessage?: unknown) => {
    paymentInFlightRef.current = false;
    setIsProcessing(false);
    try {
      await cancelPurchase();
    } catch {
      // ignore network error on cancel
    }
    setSelectedProduct(null);
    setActiveReview(null);
    setPaypalOrder(null);
    setSubscriptionAck(false);
    setSelectedForCompare([]);
    setConfirmationError(null);
    const msgText = typeof customMessage === 'string' && customMessage ? customMessage : null;
    const cancelMsg = msgText || 'Purchase cancelled.\n\nNo payment was made.';
    setAiMessage(msgText || 'Purchase cancelled. No payment was made.');
    setOutcome({
      success: false,
      message: cancelMsg,
    });
    setCurrentStep('outcome');
    announce(msgText || 'Purchase cancelled. No payment was made.', true);
  }, [cancelPurchase, announce]);

  const refreshRecentSearches = useCallback(async () => {
    try {
      const entries = await api.getSearchHistory(20);
      setRecentSearches(entries);
    } catch {
      // ignore non-fatal history load errors
    }
  }, []);

  useEffect(() => {
    void refreshRecentSearches();
  }, [refreshRecentSearches]);

  // Keyboard Escape handler for cancelling before payment capture
  useEffect(() => {
    const handleKeyDown = (e: KeyboardEvent) => {
      if (e.key === 'Escape') {
        if (['selected', 'review', 'confirm', 'paypal', 'payment_failed'].includes(currentStep) && !paymentInFlightRef.current) {
          e.preventDefault();
          handleCancelFlow();
        }
      }
    };
    window.addEventListener('keydown', handleKeyDown);
    return () => window.removeEventListener('keydown', handleKeyDown);
  }, [currentStep, handleCancelFlow]);

  const normalizeTranscript = useCallback((rawText: string): string => {
    if (!rawText) return '';
    let cleaned = rawText.replace(/\s+/g, ' ').trim();
    if (!cleaned) return '';
    // Strip harmless trailing dictation punctuation while keeping '?' intact
    cleaned = cleaned.replace(/[.,;!]+$/, '').trim();
    cleaned = cleaned.replace(
      /\b(first|top|last|cheapest)\s+to\s+(options?|products?|items?|results?|ones?)\b/gi,
      '$1 two $2'
    );
    cleaned = cleaned.replace(/\b(option|number)\s+won\b/gi, '$1 one');
    return cleaned.replace(/\s+/g, ' ').trim();
  }, []);

  // Debounced, cached typed search suggestions (NEVER calls Channel3)
  useEffect(() => {
    if (skipNextSuggestFetchRef.current) {
      skipNextSuggestFetchRef.current = false;
      return;
    }
    const q = queryInput.trim();
    if (q.length < 2) {
      setSuggestions([]);
      setShowSuggestions(false);
      setActiveSuggestionIdx(-1);
      return;
    }

    const cacheKey = q.toLowerCase();
    const cached = suggestionCacheRef.current.get(cacheKey);
    if (cached) {
      setSuggestions(cached);
      setShowSuggestions(cached.length > 0);
      setActiveSuggestionIdx(-1);
      return;
    }

    let cancelled = false;
    const timer = setTimeout(() => {
      api.getSearchSuggestions(q, 6)
        .then((res) => {
          if (cancelled) return;
          const list = Array.isArray(res?.suggestions) ? res.suggestions : [];
          suggestionCacheRef.current.set(cacheKey, list);
          setSuggestions(list);
          setShowSuggestions(list.length > 0);
          setActiveSuggestionIdx(-1);
        })
        .catch(() => {
          if (!cancelled) {
            setSuggestions([]);
            setShowSuggestions(false);
          }
        });
    }, 180);

    return () => {
      cancelled = true;
      clearTimeout(timer);
    };
  }, [queryInput]);

  // Load initial products (~6 good results) synchronized with ActiveSearchSession
  useEffect(() => {
    let cancelled = false;
    api.searchProducts('wireless headphones', 80)
      .then((res) => {
        if (cancelled || hasUserSearchedRef.current) return;
        if (res.error) {
          setSearchError(res.error_message || "I'm having trouble searching right now.\nPlease try again.");
          setNoResultsMessage(null);
          setAboveBudgetOffer(null);
          setProducts([]);
          setHasMoreResults(false);
          setTotalCandidates(0);
        } else {
          const initialProducts = res.products || [];
          visibleProductsRef.current = initialProducts;
          if ((res as any).search_id) activeSearchIdRef.current = (res as any).search_id;
          if (typeof (res as any).search_generation === 'number') {
            latestSearchGenerationRef.current = (res as any).search_generation;
          }
          setProducts(initialProducts);
          setHasMoreResults(Boolean(res.has_more));
          setTotalCandidates(res.total_candidates ?? initialProducts.length);
          setSearchError(null);
          setNoResultsMessage(null);
          setAboveBudgetOffer(null);
        }
      })
      .catch(() => {
        if (cancelled || hasUserSearchedRef.current) return;
        api.listProducts().then((all) => {
          if (cancelled || hasUserSearchedRef.current) return;
          const sliced = all.slice(0, 6);
          visibleProductsRef.current = sliced;
          setProducts(sliced);
          setHasMoreResults(all.length > 6);
          setTotalCandidates(all.length);
          setSearchError(null);
          setNoResultsMessage(null);
        });
      });
    return () => {
      cancelled = true;
    };
  }, []);

  // Sync external search reopening (from Saved Searches or Recent History)
  useEffect(() => {
    if (!externalSearchSignal) return;
    const res = externalSearchSignal.result;
    if (!res) return;
    hasUserSearchedRef.current = true;
    const reopenedProducts: Product[] = res.products || [];
    visibleProductsRef.current = reopenedProducts;
    if (res.search_id) activeSearchIdRef.current = res.search_id;
    if (typeof res.search_generation === 'number') {
      latestSearchGenerationRef.current = res.search_generation;
    }
    setProducts(reopenedProducts);
    setHasMoreResults(Boolean(res.has_more));
    setTotalCandidates(res.total_candidates ?? reopenedProducts.length);
    setSearchError(null);
    setNoResultsMessage(reopenedProducts.length === 0 ? (res.message || 'No matching products were found.') : null);
    setAboveBudgetOffer(null);
    setCheaperAlert(null);
    setSelectedForCompare([]);
    setSearchSavedNotice(null);
    const label = res.reopened_saved_search?.display_query || res.display_query || res.query;
    if (label) setQueryInput(label);
    if (res.message) setAiMessage(res.message);
    setCurrentStep('search');
  }, [externalSearchSignal]);

  // Sync external reorder review (from Order History Buy Again -> direct to PurchaseReview requiring confirmation)
  useEffect(() => {
    if (!externalReviewSignal) return;
    const { review, message } = externalReviewSignal;
    setActiveReview(review);
    setSubscriptionAck(review.subscription_acknowledged);
    setSelectedProduct(null);
    setPaypalOrder(null);
    setConfirmationError(null);
    setAiMessage(message || `Reorder prepared. Total today is $${review.total_today.toFixed(2)}. Confirmation is required.`);
    setCurrentStep('review');
  }, [externalReviewSignal]);

  // Dynamically load & render official PayPal JS SDK Buttons when on 'paypal' step and client ID is configured
  useEffect(() => {
    if (
      currentStep !== 'paypal' ||
      !paypalOrder?.paypal_order_id ||
      !paypalConfig?.is_configured ||
      !paypalConfig.paypal_client_id ||
      !paypalButtonsContainerRef.current
    ) {
      return;
    }

    let cancelled = false;
    let buttonsInstance: any = null;
    const clientId = paypalConfig.paypal_client_id;

    const renderPayPalButtons = () => {
      if (cancelled) return;
      const paypalGlobal = (window as any).paypal;
      if (!paypalGlobal || !paypalGlobal.Buttons || !paypalButtonsContainerRef.current) return;
      paypalButtonsContainerRef.current.innerHTML = '';

      buttonsInstance = paypalGlobal.Buttons({
        style: {
          layout: 'vertical',
          color: 'gold',
          shape: 'rect',
          label: 'paypal',
          height: 50,
        },
        createOrder: async () => {
          return paypalOrder.paypal_order_id;
        },
        onApprove: async (data: any) => {
          await handleCapturePayPalOrder(data.orderID || paypalOrder.paypal_order_id!);
        },
        onCancel: () => {
          handleCancelFlow();
        },
        onError: (err: any) => {
          console.error('[AccessPay Dev Log] PayPal SDK onError:', err);
          setPaymentFailureMessage(SAFE_PAYMENT_ERROR_MESSAGE);
          setCurrentStep('payment_failed');
          announce('Your payment could not be completed. Nothing was charged.', true);
        },
      });
      buttonsInstance.render(paypalButtonsContainerRef.current).catch((err: any) => {
        console.error('[AccessPay Dev Log] PayPal SDK render failed:', err);
      });
    };

    const existingScript = document.getElementById('paypal-js-sdk') as HTMLScriptElement | null;
    if (existingScript && existingScript.dataset.failed === '1') {
      existingScript.remove();
    }

    const activeScript = document.getElementById('paypal-js-sdk') as HTMLScriptElement | null;
    if (activeScript && (window as any).paypal) {
      renderPayPalButtons();
    } else if (activeScript) {
      activeScript.addEventListener('load', renderPayPalButtons);
    } else {
      const script = document.createElement('script');
      script.id = 'paypal-js-sdk';
      script.src = `https://www.paypal.com/sdk/js?client-id=${encodeURIComponent(clientId)}&currency=USD&intent=capture`;
      script.async = true;
      script.onload = renderPayPalButtons;
      script.onerror = () => {
        script.dataset.failed = '1';
        console.error('[AccessPay Dev Log] Could not load PayPal JS SDK script; using accessible PayPal Sandbox redirect checkout.');
      };
      document.body.appendChild(script);
    }

    return () => {
      cancelled = true;
      if (activeScript && !(window as any).paypal) {
        activeScript.removeEventListener('load', renderPayPalButtons);
      }
      try {
        if (buttonsInstance && typeof buttonsInstance.close === 'function') {
          buttonsInstance.close();
        }
      } catch {
        // ignore close errors when container unmounts
      }
    };
  }, [currentStep, paypalOrder, paypalConfig]);

  // Start server-controlled PayPal Sandbox Order creation after AccessPay confirmation succeeds
  const startPayPalSandboxCheckout = async (reviewToken?: string) => {
    if (paymentInFlightRef.current) return;
    paymentInFlightRef.current = true;
    setIsProcessing(true);
    setProcessingLabel('Processing payment...');
    setConfirmationError(null);
    announce('Confirmation verified. Opening PayPal Sandbox checkout.');

    try {
      const origin = getCanonicalFrontendOrigin();
      const returnUrl = origin ? `${origin}/?paypal_return=1` : '';
      const cancelUrl = origin ? `${origin}/?paypal_cancel=1` : '';
      if ((import.meta as any).env?.DEV && typeof window !== 'undefined') {
        console.info('[AccessPay Origin] Pre-PayPal window.location.origin:', window.location.origin);
        console.info('[AccessPay Origin] PayPal return_url:', returnUrl, 'cancel_url:', cancelUrl);
      }
      const orderRes = await api.createPayPalOrder(
        reviewToken || activeReview?.review_token,
        origin
          ? {
              returnUrl,
              cancelUrl,
            }
          : undefined
      );
      if (orderRes.price_changed) {
        const msg = orderRes.message || 'The price changed.\n\nPlease review the updated total.';
        setConfirmationError(msg);
        setAiMessage(msg);
        announce(msg, true);
        const refreshed = await prepareReview();
        if (refreshed) {
          setActiveReview(refreshed);
        }
        setCurrentStep('review');
        return;
      }

      if (!orderRes.success || !orderRes.paypal_order_id) {
        if (orderRes.duplicate) {
          return;
        }
        setPaymentFailureMessage(SAFE_PAYMENT_ERROR_MESSAGE);
        setAiMessage(SAFE_PAYMENT_ERROR_MESSAGE);
        setCurrentStep('payment_failed');
        announce('Your payment could not be completed. Nothing was charged.', true);
        return;
      }

      setPaypalOrder(orderRes);
      setCurrentStep('paypal');
      const readyMsg = `PayPal Sandbox order ready for $${(orderRes.amount ?? activeReview?.total_today ?? 0).toFixed(2)}. Approve payment in PayPal Sandbox or cancel.`;
      setAiMessage(readyMsg);
      announce(readyMsg);
    } catch (err) {
      console.error('[AccessPay Dev Log] createPayPalOrder error:', err);
      setPaymentFailureMessage(SAFE_PAYMENT_ERROR_MESSAGE);
      setAiMessage(SAFE_PAYMENT_ERROR_MESSAGE);
      setCurrentStep('payment_failed');
      announce('Your payment could not be completed. Nothing was charged.', true);
    } finally {
      paymentInFlightRef.current = false;
      setIsProcessing(false);
    }
  };

  // Handle accessible PayPal approval/capture without capturing unapproved Sandbox orders
  const handlePayPalSandboxApprovalAction = async () => {
    const targetOrderId = paypalOrder?.paypal_order_id;
    if (!targetOrderId || paymentInFlightRef.current) return;

    const isMockOrder = paypalOrder?.provider === 'mock' || targetOrderId.startsWith('PAYID-SBX-');
    if (isMockOrder) {
      await handleCapturePayPalOrder(targetOrderId);
      return;
    }

    paymentInFlightRef.current = true;
    setIsProcessing(true);
    setProcessingLabel('Checking PayPal Sandbox approval...');
    try {
      const statusRes = await api.getPayPalOrderStatus(targetOrderId);
      if (statusRes.success && (statusRes.status === 'APPROVED' || statusRes.status === 'COMPLETED')) {
        paymentInFlightRef.current = false;
        setIsProcessing(false);
        await handleCapturePayPalOrder(targetOrderId);
        return;
      }

      if (paypalOrder?.approval_url) {
        announce('Opening PayPal Sandbox checkout so you can sign in and approve this payment.');
        window.location.assign(paypalOrder.approval_url);
        return;
      }

      setPaymentFailureMessage(SAFE_PAYMENT_ERROR_MESSAGE);
      setAiMessage(SAFE_PAYMENT_ERROR_MESSAGE);
      setCurrentStep('payment_failed');
      announce('Your payment could not be completed. Nothing was charged.', true);
    } catch (err) {
      console.error('[AccessPay Dev Log] PayPal status/approval error:', err);
      if (paypalOrder?.approval_url) {
        window.location.assign(paypalOrder.approval_url);
        return;
      }
      setPaymentFailureMessage(SAFE_PAYMENT_ERROR_MESSAGE);
      setAiMessage(SAFE_PAYMENT_ERROR_MESSAGE);
      setCurrentStep('payment_failed');
      announce('Your payment could not be completed. Nothing was charged.', true);
    } finally {
      paymentInFlightRef.current = false;
      setIsProcessing(false);
    }
  };

  // Capture approved PayPal Sandbox order via backend
  const handleCapturePayPalOrder = async (orderIdToCapture?: string) => {
    const targetOrderId = orderIdToCapture || paypalOrder?.paypal_order_id;
    if (!targetOrderId || paymentInFlightRef.current) return;

    paymentInFlightRef.current = true;
    setIsProcessing(true);
    setProcessingLabel('Processing payment...');
    setAiMessage('Processing payment...');
    announce('Processing payment...');

    try {
      const capRes = await api.capturePayPalOrder(targetOrderId, {
        reviewToken: activeReview?.review_token,
        interactionMode: 'VOICE',
        confirmationMethod: 'VOICE',
      });

      if (capRes.price_changed) {
        const msg = capRes.message || 'The price changed.\n\nPlease review the updated total.';
        setConfirmationError(msg);
        setAiMessage(msg);
        announce(msg, true);
        const refreshed = await prepareReview();
        if (refreshed) setActiveReview(refreshed);
        setCurrentStep('review');
        return;
      }

      if (!capRes.success) {
        if (capRes.duplicate) return;
        setPaymentFailureMessage(SAFE_PAYMENT_ERROR_MESSAGE);
        setAiMessage(SAFE_PAYMENT_ERROR_MESSAGE);
        setCurrentStep('payment_failed');
        announce('Your payment could not be completed. Nothing was charged.', true);
        return;
      }

      const paidAmount = capRes.amount_charged ?? paypalOrder?.amount ?? activeReview?.total_today ?? 0;
      const prodTitle = capRes.product_title || paypalOrder?.product_title || selectedProduct?.title || 'AccessPay Order';
      const merchantName = capRes.merchant || paypalOrder?.merchant || selectedProduct?.merchant || 'Verified Merchant';
      const ppOrderId = capRes.paypal_order_id || targetOrderId;
      const isSub = capRes.is_subscription ?? paypalOrder?.is_subscription ?? false;
      const lineItems: OrderLineItem[] =
        (capRes.items && capRes.items.length > 0 ? capRes.items : undefined) ||
        (paypalOrder?.items && paypalOrder.items.length > 0 ? paypalOrder.items : undefined) ||
        (activeReview?.cart.items || []).map((ci) => ({
          product_id: ci.product_id,
          product_title: ci.product.title,
          merchant: ci.product.merchant,
          category: ci.product.category,
          unit_price: ci.product.price,
          quantity: ci.quantity,
          line_total: ci.item_total,
          variant: Object.keys(ci.selected_variant || {}).length > 0 ? Object.values(ci.selected_variant || {}).join(', ') : 'Standard Option',
        }));

      setOutcome({
        success: true,
        message: 'Payment successful',
        orderId: capRes.order_id,
        paypalOrderId: ppOrderId,
        paypalCaptureId: capRes.paypal_capture_id,
        productTitle: prodTitle,
        merchant: merchantName,
        amountPaid: paidAmount,
        itemSubtotal: capRes.item_subtotal ?? paypalOrder?.item_subtotal ?? activeReview?.item_subtotal,
        shipping: capRes.shipping ?? paypalOrder?.shipping ?? activeReview?.shipping,
        tax: capRes.tax ?? paypalOrder?.tax ?? activeReview?.tax,
        items: lineItems,
        isSubscription: isSub,
      });
      setCurrentStep('outcome');
      const speechSuccess = `Payment successful. ${prodTitle}. Paid $${paidAmount.toFixed(2)} to ${merchantName}. PayPal order ${ppOrderId}.`;
      setAiMessage(speechSuccess);
      announce(speechSuccess, true);
      refreshCart();
      onOrderCompleted?.();
    } catch (err) {
      console.error('[AccessPay Dev Log] capturePayPalOrder error:', err);
      setPaymentFailureMessage(SAFE_PAYMENT_ERROR_MESSAGE);
      setAiMessage(SAFE_PAYMENT_ERROR_MESSAGE);
      setCurrentStep('payment_failed');
      announce('Your payment could not be completed. Nothing was charged.', true);
    } finally {
      paymentInFlightRef.current = false;
      setIsProcessing(false);
    }
  };

  const handleOpenSubscriptionReview = useCallback(
    async (offer: SubscriptionOffer) => {
      setIsProcessing(true);
      setProcessingLabel('Preparing subscription review...');
      setSubscriptionConfirmError(null);
      setSubscriptionConfirmPhrase('');
      try {
        const rev = await api.prepareSubscriptionReview(offer.id);
        setSelectedSubscription(offer);
        setSubscriptionReview(rev);
        setCurrentStep('subscription_review');
        const msg = `Subscription review ready for ${offer.name}. Due today: $${rev.due_today.toFixed(2)}. Recurring: $${rev.recurring_amount.toFixed(2)} ${rev.billing_frequency}. This is a recurring payment. No subscription has been created yet.`;
        setAiMessage(msg);
        announce(msg);
      } catch (err: any) {
        const msg = err?.message || 'Unable to prepare subscription review.';
        setAiMessage(msg);
        announce(msg, true);
      } finally {
        setIsProcessing(false);
      }
    },
    [announce]
  );

  const handleSubmitSubscriptionConfirmation = useCallback(
    async (phrase: string, method: 'VOICE' | 'BUTTON' = 'VOICE') => {
      const rev = subscriptionReviewRef.current;
      if (!rev) return;
      setIsProcessing(true);
      setProcessingLabel('Verifying recurring commitment...');
      setSubscriptionConfirmError(null);
      try {
        const res = await api.confirmSubscription({
          reviewToken: rev.review_token,
          spokenPhrase: phrase,
          method,
        });
        if (!res.success) {
          setSubscriptionConfirmError(res.message);
          setAiMessage(res.message);
          announce(res.message, true);
          return;
        }
        const origin = getCanonicalFrontendOrigin();
        const returnUrl = origin ? `${origin}/?paypal_sub_return=1` : undefined;
        const cancelUrl = origin ? `${origin}/?paypal_sub_cancel=1` : undefined;
        const subRecord = await api.createPayPalSubscription({
          reviewToken: rev.review_token,
          returnUrl,
          cancelUrl,
        });
        setPaypalSubscription(subRecord);
        setCurrentStep('subscription_paypal');
        const readyMsg = `PayPal Sandbox subscription created (${subRecord.paypal_subscription_id}). Approve in PayPal Sandbox to activate.`;
        setAiMessage(readyMsg);
        announce(readyMsg);
        onOrderCompleted?.();
      } catch (err: any) {
        const msg = err?.message || 'Unable to create PayPal Sandbox subscription.';
        setSubscriptionConfirmError(msg);
        setAiMessage(msg);
        announce(msg, true);
      } finally {
        setIsProcessing(false);
      }
    },
    [announce, onOrderCompleted]
  );

  const applyIntentResult = useCallback(
    async (res: any, activeSearchIdSnapshot: string | null = activeSearchIdRef.current) => {
      if (!res) return;
      if (res.stale || res.action === 'STALE_DISCARDED') return;

      if (res.action === 'SUBSCRIPTION_VOICE_INTENT') {
        const subIntent = res.subscriptionIntent;
        if (!subIntent) return;
        if (subIntent.kind === 'search_subscriptions') {
          setIsProcessing(true);
          setProcessingLabel('Finding demo subscription plans...');
          try {
            const offers = await api.getSubscriptionProducts(subIntent.query);
            setSubscriptionOffers(offers);
            setSelectedSubscription(offers[0] || null);
            setSubscriptionReview(null);
            setSubscriptionConfirmError(null);
            setCurrentStep('subscription_results');
            const msg = `Found ${offers.length} demo subscription plans. Remember: these are recurring demo subscriptions, not one-time purchases.`;
            setAiMessage(msg);
            announce(msg);
          } finally {
            setIsProcessing(false);
          }
          return;
        }
        if (subIntent.kind === 'select_subscription') {
          const offer = subscriptionOffersRef.current[subIntent.index] || subscriptionOffersRef.current[0];
          if (offer) {
            setSelectedSubscription(offer);
            const msg = `Selected ${offer.name} ($${offer.recurring_amount.toFixed(2)} ${offer.billing_frequency}). Say "Review this subscription" to inspect terms.`;
            setAiMessage(msg);
            announce(msg);
          }
          return;
        }
        if (subIntent.kind === 'review_subscription') {
          const offer =
            (typeof subIntent.index === 'number'
              ? subscriptionOffersRef.current[subIntent.index]
              : selectedSubscriptionRef.current) || subscriptionOffersRef.current[0];
          if (offer) {
            await handleOpenSubscriptionReview(offer);
          }
          return;
        }
        if (subIntent.kind === 'subscription_qa') {
          const offer =
            (typeof subIntent.index === 'number'
              ? subscriptionOffersRef.current[subIntent.index]
              : subscriptionReviewRef.current?.offer || selectedSubscriptionRef.current) ||
            subscriptionOffersRef.current[0];
          if (offer) {
            const qa = await api.askSubscriptionQuestion(offer.id, subIntent.question);
            setAiMessage(qa.answer);
            announce(qa.answer);
          }
          return;
        }
        if (subIntent.kind === 'subscription_confirm_attempt') {
          await handleSubmitSubscriptionConfirmation(subIntent.phrase, 'VOICE');
          return;
        }
        if (subIntent.kind === 'cancel_subscription_flow') {
          const msg = 'Subscription cancelled. No new subscription was created.';
          setSubscriptionOutcome({ success: false, message: msg });
          setCurrentStep('subscription_outcome');
          setAiMessage(msg);
          announce(msg);
          return;
        }
        return;
      }

      if (res.search_id) {
        activeSearchIdRef.current = res.search_id;
      }

      if (typeof res.search_generation === 'number') {
        if (res.search_generation < latestSearchGenerationRef.current) {
          return;
        }
        if (res.search_generation > latestSearchGenerationRef.current) {
          latestSearchGenerationRef.current = res.search_generation;
          setSelectedProduct(null);
          setComparisonData(null);
          setSelectedForCompare([]);
          setCheaperAlert(null);
          setConfirmationError(null);
          setNoResultsMessage(null);
          setAboveBudgetOffer(null);
        }
      }

      const msg = res.message || res.speech_response || 'Done';
      setAiMessage(msg);
      announce(res.speech_response || msg);

      if (res.action === 'SHOW_RECENT_SEARCHES') {
        if (Array.isArray(res.history)) {
          setRecentSearches(res.history);
        }
        setShowAllRecentHistory(true);
        setCurrentStep('search');
        return;
      }

      if (res.action === 'RECENT_SEARCH_SAVED') {
        setHistoryNotice(msg);
        return;
      }

      if (res.action === 'RECENT_SEARCH_CLEARED') {
        setRecentSearches([]);
        setShowAllRecentHistory(false);
        setHistoryNotice(msg);
        return;
      }

      if (res.action === 'SEARCH_RESULTS') {
        setHasUserSearched(true);
        hasUserSearchedRef.current = true;
        setShowAllRecentHistory(false);
        void refreshRecentSearches();
        const nextProducts = res.products || [];
        setSearchSavedNotice(null);
        if (nextProducts.length > 0) {
          visibleProductsRef.current = nextProducts;
          setProducts(nextProducts);
          setHasMoreResults(Boolean(res.has_more));
          setTotalCandidates(res.total_candidates ?? nextProducts.length);
          setSelectedProduct(null);
          setComparisonData(null);
          setNoResultsMessage(null);
          setSearchError(null);
          setAboveBudgetOffer(null);
          setSelectedForCompare([]);
          setCheaperAlert(null);
          setCurrentStep('search');
        } else {
          visibleProductsRef.current = [];
          setProducts([]);
          setSelectedProduct(null);
          setComparisonData(null);
          setSearchError(null);
          setAboveBudgetOffer(null);
          setSelectedForCompare([]);
          setCheaperAlert(null);
          setNoResultsMessage(
            "I couldn't find a good match.\n\nNo matching products were found in the available product catalog. Try changing your budget or product requirements."
          );
          setCurrentStep('search');
        }
      } else if (res.action === 'INFO' && res.preserve_active_products) {
        if (visibleProductsRef.current.length === 0 && Array.isArray(res.products) && res.products.length > 0) {
          visibleProductsRef.current = res.products;
          setProducts(res.products);
        }
        setNoResultsMessage(null);
        setSearchError(null);
        setAboveBudgetOffer(null);
      } else if (res.action === 'NO_RESULTS') {
        if (visibleProductsRef.current.length > 0 && res.preserve_active_products) {
          setNoResultsMessage(null);
          setSearchError(null);
        } else {
          visibleProductsRef.current = [];
          setProducts([]);
          setSelectedProduct(null);
          setComparisonData(null);
          setSearchError(null);
          setSelectedForCompare([]);
          setCheaperAlert(null);
          setNoResultsMessage(msg);
          if (res.budget_exceeded && res.above_budget_products?.length && res.budget_limit) {
            setAboveBudgetOffer({
              limit: res.budget_limit,
              products: res.above_budget_products.slice(0, 6),
            });
          } else {
            setAboveBudgetOffer(null);
          }
          setCurrentStep('search');
        }
      } else if (res.action === 'SEARCH_ERROR') {
        if (visibleProductsRef.current.length > 0 && activeSearchIdSnapshot !== null) {
          const keepMsg = 'I had trouble updating that request right now. Keeping your current results active.';
          setNoResultsMessage(null);
          setSearchError(null);
          setAiMessage(keepMsg);
          announce(keepMsg, true);
        } else {
          const safeMsg = "I'm having trouble searching right now.\nPlease try again.";
          visibleProductsRef.current = [];
          setProducts([]);
          setNoResultsMessage(null);
          setAboveBudgetOffer(null);
          setAiMessage(safeMsg);
          setSearchError(safeMsg);
          announce("I'm having trouble searching right now. Please try again.", true);
          setCurrentStep('search');
        }
      } else if (res.action === 'COMPARE') {
        if (res.comparison?.products && res.comparison.products.length >= 2) {
          setComparisonData(res.comparison);
          const currentVisible = visibleProductsRef.current;
          const comp0 = res.comparison.products[0];
          const comp1 = res.comparison.products[1];
          const p1 = currentVisible.find((p) => p.id === comp0.id) || comp0;
          const p2 = currentVisible.find((p) => p.id === comp1.id) || comp1;
          if (p1 && p2) {
            setSelectedForCompare([p1, p2]);
          }
          setCurrentStep('compare');
        }
      } else if (res.action === 'CHEAPER_ALTERNATIVE_FOUND') {
        setCheaperAlert({
          alternative: res.alternative_product,
          original: res.original_product,
          savings: res.savings,
        });
        if (currentStepRef.current !== 'search' && currentStepRef.current !== 'compare') {
          setCurrentStep('search');
        }
      } else if (res.action === 'PRODUCT_SELECTED' && res.product) {
        setSelectedProduct(res.product);
        setActiveReview(null);
        setPaypalOrder(null);
        await refreshCart();
        setCurrentStep('selected');
      } else if (res.action === 'VIEW_CART' || res.action === 'OPEN_CART') {
        await refreshCart();
        onNavigateCart?.();
      } else if (
        res.action === 'PAYMENT_REVIEW_READY' ||
        res.action === 'TOTAL_SUMMARY' ||
        res.action === 'READ_REVIEW'
      ) {
        await refreshCart();
        const review = res.review || (await prepareReview());
        if (review) {
          setActiveReview(review);
          setSubscriptionAck(Boolean(review.subscription_acknowledged));
          setConfirmationError(null);
          setCurrentStep('review');
        }
      } else if (res.action === 'PROCEED_TO_CONFIRMATION') {
        const rev = res.review || activeReviewRef.current || (await prepareReview());
        if (rev) {
          setActiveReview(rev);
          setSubscriptionAck(Boolean(rev.subscription_acknowledged));
          if (rev.is_subscription && !rev.subscription_acknowledged) {
            setConfirmationError('Please acknowledge the recurring monthly payment before continuing to confirmation.');
            setCurrentStep('review');
          } else {
            setConfirmationError(null);
            setCurrentStep('confirm');
          }
        }
      } else if (res.action === 'PAYPAL_APPROVAL_NAVIGATION') {
        if (currentStepRef.current === 'paypal' && paypalOrderRef.current?.paypal_order_id) {
          await handlePayPalSandboxApprovalAction();
        }
      } else if (res.action === 'RETRY_PAYMENT') {
        if (activeReviewRef.current) {
          setConfirmationError(null);
          setCurrentStep('confirm');
        } else {
          const rev = await prepareReview();
          if (rev) {
            setActiveReview(rev);
            setCurrentStep('review');
          } else {
            setCurrentStep('search');
          }
        }
      } else if (res.action === 'READ_RECEIPT') {
        // outcome speech handled cleanly by announce above
      } else if (res.action === 'OPEN_SHOP') {
        if (currentStepRef.current === 'outcome' || currentStepRef.current === 'payment_failed') {
          setCurrentStep('search');
        }
      } else if (res.action === 'CANCELLED') {
        await handleCancelFlow();
      } else if (res.action === 'NAVIGATE_BACK') {
        handleBackStep();
      } else if (res.action === 'AMBIGUITY_GUARD' || res.action === 'CONFIRMATION_FAILED') {
        setConfirmationError(res.message);
        const latestReview = activeReviewRef.current;
        if (res.requires_step === 2 && latestReview) {
          setActiveReview({ ...latestReview, high_value_step: 2 });
        }
      } else if (res.action === 'PRODUCT_SAVED') {
        const savedProdId = res.saved_item?.product_id || res.product?.id;
        if (savedProdId) {
          const next = new Set(savedProductIdsRef.current || localSavedIdsRef.current);
          next.add(savedProdId);
          setLocalSavedIds(next);
          onSavedChanged?.(next);
        }
        announce('Product saved.');
      } else if (res.action === 'SAVED_ITEM_REMOVED') {
        if (res.removed_id) {
          const next = new Set(savedProductIdsRef.current || localSavedIdsRef.current);
          next.delete(res.removed_id);
          setLocalSavedIds(next);
          onSavedChanged?.(next);
        }
        announce('Product removed from saved items.');
      } else if (res.action === 'SEARCH_SAVED') {
        setSearchSavedNotice('Saved search created.');
        announce('Saved search created.');
      } else if (res.action === 'OPEN_SAVED_ITEMS') {
        onNavigateSaved?.('items');
      } else if (res.action === 'OPEN_SAVED_SEARCHES') {
        onNavigateSaved?.('searches');
      } else if (res.action === 'OPEN_ORDERS') {
        onNavigateOrders?.();
      } else if (res.action === 'PAYMENT_CONFIRMED') {
        setIsProcessing(false);
        await startPayPalSandboxCheckout(res.review_token || activeReviewRef.current?.review_token);
      }
    },
    // eslint-disable-next-line react-hooks/exhaustive-deps
    [announce, handleCancelFlow, onNavigateCart, onNavigateOrders, onNavigateSaved, onSavedChanged, prepareReview, refreshCart]
  );

  // Direct catalog search triggered when the user clicks a typed suggestion
  const runSuggestedSearch = useCallback(
    async (suggestedQuery: string) => {
      const cleaned = suggestedQuery.trim();
      if (!cleaned) return;
      skipNextSuggestFetchRef.current = true;
      setShowSuggestions(false);
      setSuggestions([]);
      setActiveSuggestionIdx(-1);
      setQueryInput(cleaned);
      hasUserSearchedRef.current = true;
      const reqSeq = ++searchRequestSeqRef.current;
      setIsProcessing(true);
      setProcessingLabel('Finding products...');
      setConfirmationError(null);
      setSearchError(null);
      setNoResultsMessage(null);
      setAboveBudgetOffer(null);
      setSearchSavedNotice(null);
      announce(`Searching for ${cleaned}...`);
      try {
        const res = await api.searchProducts(cleaned);
        if (reqSeq !== searchRequestSeqRef.current) return;
        const nextProducts = res.products || [];
        if (res.search_id) activeSearchIdRef.current = res.search_id;
        if (typeof res.search_generation === 'number') {
          latestSearchGenerationRef.current = res.search_generation;
        }
        if (nextProducts.length > 0) {
          visibleProductsRef.current = nextProducts;
          setProducts(nextProducts);
          setHasMoreResults(Boolean(res.has_more));
          setTotalCandidates(res.total_candidates ?? nextProducts.length);
          setSelectedProduct(null);
          setComparisonData(null);
          setSelectedForCompare([]);
          setCheaperAlert(null);
          setNoResultsMessage(null);
          setSearchError(null);
          const msg = `Showing ${nextProducts.length} options for "${cleaned}".`;
          setAiMessage(msg);
          announce(msg);
          setCurrentStep('search');
        } else {
          visibleProductsRef.current = [];
          setProducts([]);
          setNoResultsMessage(
            "I couldn't find a good match.\n\nNo matching products were found in the available product catalog. Try changing your budget or product requirements."
          );
          setCurrentStep('search');
        }
      } catch {
        if (reqSeq !== searchRequestSeqRef.current) return;
        const safeMsg = "I'm having trouble searching right now.\nPlease try again.";
        setSearchError(safeMsg);
        setAiMessage(safeMsg);
      } finally {
        if (reqSeq === searchRequestSeqRef.current) {
          setIsProcessing(false);
        }
      }
    },
    [announce]
  );

  // Unified conversational message entry point shared by voice, typed text, and command chips.
  const submitUserMessage = async (
    rawMessage: string,
    inputMode: InteractionInputMode = 'text',
    rawTranscript?: string
  ) => {
    setShowSuggestions(false);
    setHasUserSearched(true);
    const text = normalizeTranscript(rawMessage);
    if (!text) {
      const repeatMsg = "I didn't catch a clear command. Please repeat what you would like to do.";
      setAiMessage(repeatMsg);
      announce(repeatMsg, true);
      return;
    }

    // Prevent duplicate confirmation while payment is already processing
    if (paymentInFlightRef.current) {
      announce('Processing payment...');
      return;
    }

    // Route subscription queries & actions identically for typed text and voice
    const subIntent = parseSubscriptionVoiceIntent(text, activeShopView);
    if (subIntent) {
      await applyIntentResult(
        { action: 'SUBSCRIPTION_VOICE_INTENT', subscriptionIntent: subIntent },
        activeSearchIdRef.current
      );
      return;
    }

    // Approval shortcut when on the PayPal Sandbox Checkout step
    const lower = text.toLowerCase();
    if (
      currentStepRef.current === 'paypal' &&
      paypalOrderRef.current?.paypal_order_id &&
      (lower.includes('approve') || lower.includes('complete payment') || lower.includes('pay now'))
    ) {
      await handlePayPalSandboxApprovalAction();
      return;
    }

    hasUserSearchedRef.current = true;
    const reqSeq = ++searchRequestSeqRef.current;
    const voiceTurn = inputMode === 'voice' ? ++voiceTurnCountRef.current : null;
    const visibleIdsSnapshot = visibleProductsRef.current.map((p) => p.id);
    const activeSearchIdSnapshot = activeSearchIdRef.current;
    const generationSnapshot = latestSearchGenerationRef.current;

    setIsProcessing(true);
    setProcessingLabel('Finding products...');
    setConfirmationError(null);
    setSearchError(null);
    setNoResultsMessage(null);
    setAboveBudgetOffer(null);
    announce('Finding products...');
    try {
      const currentShopView: AppViewName =
        currentStepRef.current === 'review'
          ? 'PURCHASE_REVIEW'
          : currentStepRef.current === 'confirm'
          ? 'CONFIRMATION_REQUIRED'
          : currentStepRef.current === 'paypal'
          ? 'PAYPAL_CHECKOUT'
          : currentStepRef.current === 'payment_failed'
          ? 'PAYMENT_FAILURE'
          : currentStepRef.current === 'outcome'
          ? outcome?.success
            ? 'PAYMENT_SUCCESS'
            : 'SHOP'
          : 'SHOP';

      const res = await api.sendAiIntent(text, {
        inputMode,
        activeSearchId: activeSearchIdSnapshot,
        searchGeneration: generationSnapshot,
        visibleProductIds: visibleIdsSnapshot,
        currentView: currentShopView,
        rawTranscript: inputMode === 'voice' ? (rawTranscript ?? rawMessage) : undefined,
      });
      if (reqSeq !== searchRequestSeqRef.current) return;

      if (import.meta.env.DEV) {
        console.info('[AccessPay VoiceTrace Turn]', {
          VOICE_TURN: voiceTurn,
          RAW_VOICE_TRANSCRIPT: inputMode === 'voice' ? (rawTranscript ?? rawMessage) : null,
          NORMALIZED_TRANSCRIPT: text,
          INPUT_MODE: inputMode,
          ACTIVE_SEARCH_ID: res.search_id ?? activeSearchIdSnapshot,
          SEARCH_GENERATION: res.search_generation ?? generationSnapshot,
          VISIBLE_PRODUCT_IDS: visibleIdsSnapshot,
          BACKEND_DISPLAYED_IDS: Array.isArray(res.products) ? res.products.map((p: any) => p.id) : visibleIdsSnapshot,
          DETECTED_ACTION: res.classified_action ?? res.action,
          CHANNEL3_CALLED: Boolean(res.channel3_called),
          RESOLVED_PRODUCT_IDS: res.resolved_product_ids ?? res.referenced_product_ids ?? [],
        });
      }

      await applyIntentResult(res, activeSearchIdSnapshot);
    } catch (err: any) {
      if (reqSeq !== searchRequestSeqRef.current) return;
      console.error('[AccessPay Dev Log] Search/intent execution error:', err);
      if (visibleProductsRef.current.length > 0 && activeSearchIdSnapshot !== null) {
        const keepMsg = 'I had trouble completing that command right now. Keeping your current results active.';
        setNoResultsMessage(null);
        setSearchError(null);
        setAiMessage(keepMsg);
        announce(keepMsg, true);
      } else {
        const safeMsg = "I'm having trouble searching right now.\nPlease try again.";
        visibleProductsRef.current = [];
        setProducts([]);
        setNoResultsMessage(null);
        setAboveBudgetOffer(null);
        setAiMessage(safeMsg);
        setSearchError(safeMsg);
        announce("I'm having trouble searching right now. Please try again.", true);
      }
    } finally {
      if (reqSeq === searchRequestSeqRef.current) {
        setIsProcessing(false);
      }
    }
  };

  useEffect(() => {
    if (!onRegisterShopController) return;
    const outcomeSuccess = Boolean(outcome?.success);
    onRegisterShopController({
      getViewContext: () => {
        const step = currentStepRef.current;
        const currentView: AppViewName =
          step === 'review'
            ? 'PURCHASE_REVIEW'
            : step === 'confirm'
            ? 'CONFIRMATION_REQUIRED'
            : step === 'paypal'
            ? 'PAYPAL_CHECKOUT'
            : step === 'payment_failed'
            ? 'PAYMENT_FAILURE'
            : step === 'outcome'
            ? outcomeSuccess
              ? 'PAYMENT_SUCCESS'
              : 'SHOP'
            : step === 'subscription_results'
            ? 'SUBSCRIPTION_RESULTS'
            : step === 'subscription_review'
            ? 'SUBSCRIPTION_REVIEW'
            : step === 'subscription_confirm'
            ? 'SUBSCRIPTION_CONFIRMATION'
            : step === 'subscription_paypal'
            ? 'SUBSCRIPTION_PAYPAL'
            : step === 'subscription_outcome'
            ? 'SUBSCRIPTION_OUTCOME'
            : 'SHOP';
        return {
          currentView,
          activeSearchId: activeSearchIdRef.current,
          searchGeneration: latestSearchGenerationRef.current,
          visibleProductIds: visibleProductsRef.current.map((p) => p.id),
        };
      },
      applyIntentResult: async (res: any) => {
        await applyIntentResult(res, activeSearchIdRef.current);
      },
      openPurchaseReview: (rev: PurchaseReview, msg?: string) => {
        setActiveReview(rev);
        setSubscriptionAck(Boolean(rev.subscription_acknowledged));
        setConfirmationError(null);
        setCurrentStep('review');
        if (msg) setAiMessage(msg);
      },
      setShopStepSearch: () => {
        setCurrentStep('search');
      },
    });
    return () => onRegisterShopController(null);
  }, [applyIntentResult, onRegisterShopController, outcome?.success]);

  const executeAiIntent = (commandText: string, inputMode: InteractionInputMode = 'text') =>
    submitUserMessage(commandText, inputMode);

  const handleSaveProduct = async (product: Product) => {
    try {
      await api.saveItem(product.id, product);
      const next = new Set(savedProductIds || localSavedIds);
      next.add(product.id);
      setLocalSavedIds(next);
      onSavedChanged?.(next);
      setAiMessage(`Saved ${product.title} to your Saved Items.`);
      announce('Product saved.');
    } catch (err: any) {
      announce(err?.message || 'Unable to save product.', true);
    }
  };

  const handleSaveCurrentSearch = async () => {
    try {
      await api.saveCurrentSearch();
      setSearchSavedNotice('Saved search created.');
      setAiMessage('Search saved. You can re-run it anytime under Saved.');
      announce('Saved search created.');
    } catch (err: any) {
      announce(err?.message || 'Unable to save search.', true);
    }
  };

  const handleRunRecentSearch = async (entry: SearchHistoryEntry) => {
    if (isProcessing || busyHistoryId) return;
    setBusyHistoryId(entry.history_id);
    setHasUserSearched(true);
    hasUserSearchedRef.current = true;
    setIsProcessing(true);
    setProcessingLabel(`Searching "${entry.display_query}"...`);
    setHistoryNotice(null);
    try {
      const res = await api.runSearchHistory(entry.history_id);
      setQueryInput(entry.display_query);
      await applyIntentResult(res);
    } catch (err: any) {
      const errMsg = err?.message || 'Unable to rerun that recent search right now.';
      setAiMessage(errMsg);
      announce(errMsg, true);
    } finally {
      setBusyHistoryId(null);
      setIsProcessing(false);
    }
  };

  const handleSaveRecentSearch = async (entry: SearchHistoryEntry) => {
    if (busyHistoryId) return;
    setBusyHistoryId(entry.history_id);
    try {
      await api.saveRecentSearch(entry.history_id);
      const notice = `Saved "${entry.display_query}" to Saved Searches.`;
      setHistoryNotice(notice);
      announce(notice);
    } catch (err: any) {
      announce(err?.message || 'Unable to save that recent search.', true);
    } finally {
      setBusyHistoryId(null);
    }
  };

  const handleShowMore = async () => {
    if (isLoadingMore) return;
    setIsLoadingMore(true);
    try {
      const res = await api.showMoreProducts();
      const nextProducts: Product[] = res.products || [];
      visibleProductsRef.current = nextProducts;
      setProducts(nextProducts);
      setHasMoreResults(Boolean(res.has_more));
      if (typeof res.total_candidates === 'number') {
        setTotalCandidates(res.total_candidates);
      }
      if (res.message) {
        setAiMessage(res.message);
      }
      announce(res.speech_response || `Now showing ${nextProducts.length} options.`);
    } catch (err: any) {
      announce(err?.message || 'Could not load more options.', true);
    } finally {
      setIsLoadingMore(false);
    }
  };

  // Compare toggle from card buttons
  const handleToggleCompare = (product: Product) => {
    setSelectedForCompare((prev) => {
      const exists = prev.some((p) => p.id === product.id);
      let updated: Product[];
      if (exists) {
        updated = prev.filter((p) => p.id !== product.id);
      } else {
        updated = [...prev, product].slice(-2);
      }
      if (updated.length === 2) {
        api.compareProducts([updated[0].id, updated[1].id]).then((data) => {
          setComparisonData(data);
          setAiMessage(data.summary);
          announce(data.summary);
          setCurrentStep('compare');
        });
      }
      return updated;
    });
  };

  // Select product action (MUST NOT purchase)
  const handleSelectProduct = async (product: Product) => {
    setSelectedProduct(product);
    setActiveReview(null);
    setPaypalOrder(null);
    await addToCart(product.id, 1);
    setConfirmationError(null);
    const msg = `Selected ${product.title}. No payment has been made yet.`;
    setAiMessage(msg);
    announce(msg);
    setCurrentStep('selected');
  };

  // Proceed to review
  const handleProceedToReview = async () => {
    try {
      const review = await prepareReview();
      if (review) {
        setActiveReview(review);
        setSubscriptionAck(review.subscription_acknowledged);
        setConfirmationError(null);
        setCurrentStep('review');
        announce(`Purchase review ready. Total is $${review.total_today.toFixed(2)}. No payment has been made yet.`);
      }
    } catch (err: any) {
      announce('Could not prepare review.');
    }
  };

  // Toggle recurring subscription acknowledgement
  const handleToggleSubscriptionAck = async (checked: boolean) => {
    setSubscriptionAck(checked);
    if (activeReview) {
      setActiveReview({ ...activeReview, subscription_acknowledged: checked });
    }
    try {
      await api.acknowledgeSubscription(checked);
    } catch (e) {
      console.error('[AccessPay Dev Log] Failed to sync subscription acknowledgement:', e);
    }
  };

  // Proceed from Purchase Review to Accessible Payment Confirmation
  const handleProceedToConfirm = () => {
    if (!activeReview) return;
    if (activeReview.is_subscription && !subscriptionAck) {
      const subErr = 'Please acknowledge the recurring monthly payment before continuing to confirmation.';
      setConfirmationError(subErr);
      announce(subErr, true);
      return;
    }
    setConfirmationError(null);
    setCurrentStep('confirm');
    announce(
      `Your total is $${activeReview.total_today.toFixed(2)}. No payment has been made yet. Say '${activeReview.expected_phrase}' to continue.`
    );
  };

  // AccessPay Explicit Payment Confirmation -> Opens PayPal Sandbox Checkout
  const handleConfirmPayment = async (phraseToUse?: string) => {
    if (!activeReview || paymentInFlightRef.current || isProcessing) return;
    paymentInFlightRef.current = true;
    setIsProcessing(true);
    setProcessingLabel('Processing payment...');
    setConfirmationError(null);

    const phrase = phraseToUse !== undefined ? phraseToUse : activeReview.expected_phrase;

    try {
      const res = await confirmPurchase(
        phrase,
        'VOICE',
        activeReview.is_subscription ? subscriptionAck : true,
        activeReview.is_free_trial ? subscriptionAck : true,
        activeReview.high_value_step,
        true // authorizeOnly = true -> transitions to PayPal Sandbox Checkout step
      );

      if (res.requires_step === 2) {
        setActiveReview({ ...activeReview, high_value_step: 2 });
        setConfirmationError(res.message);
        paymentInFlightRef.current = false;
        setIsProcessing(false);
        return;
      }

      if (!res.success) {
        setConfirmationError(res.message);
        if (res.state === 'PAYMENT_REVIEW') {
          const updated = await prepareReview();
          if (updated) setActiveReview(updated);
          setCurrentStep('review');
        }
        paymentInFlightRef.current = false;
        setIsProcessing(false);
        return;
      }

      // Release lock before calling startPayPalSandboxCheckout which acquires its own lock
      paymentInFlightRef.current = false;
      setIsProcessing(false);
      await startPayPalSandboxCheckout(activeReview.review_token);
    } catch (err: any) {
      paymentInFlightRef.current = false;
      setIsProcessing(false);
      setConfirmationError("Your payment could not be completed.\n\nNothing was charged.");
    }
  };

  // Back step
  const handleBackStep = () => {
    if (paymentInFlightRef.current) return;
    setConfirmationError(null);
    if (currentStep === 'outcome' || currentStep === 'payment_failed') {
      setCurrentStep('search');
    } else if (currentStep === 'paypal') {
      setCurrentStep('confirm');
    } else if (currentStep === 'confirm') {
      setCurrentStep('review');
    } else if (currentStep === 'review') {
      setCurrentStep('selected');
    } else if (currentStep === 'selected' || currentStep === 'compare') {
      setCurrentStep('search');
    }
  };

  const activeShopView: AppViewName = (() => {
    if (currentStep === 'review') return 'PURCHASE_REVIEW';
    if (currentStep === 'confirm') return 'CONFIRMATION_REQUIRED';
    if (currentStep === 'paypal') return 'PAYPAL_CHECKOUT';
    if (currentStep === 'payment_failed') return 'PAYMENT_FAILURE';
    if (currentStep === 'outcome') return outcome?.success ? 'PAYMENT_SUCCESS' : 'SHOP';
    if (currentStep === 'subscription_results') return 'SUBSCRIPTION_RESULTS';
    if (currentStep === 'subscription_review') return 'SUBSCRIPTION_REVIEW';
    if (currentStep === 'subscription_confirm') return 'SUBSCRIPTION_CONFIRMATION';
    if (currentStep === 'subscription_paypal') return 'SUBSCRIPTION_PAYPAL';
    if (currentStep === 'subscription_outcome') return 'SUBSCRIPTION_OUTCOME';
    return 'SHOP';
  })();

  const shopControls = useMemo<VoiceControlDescriptor[]>(() => {
    if (!isActiveTab) return [];
    const controls: VoiceControlDescriptor[] = [];

    if (currentStep === 'search') {
      if (searchError) {
        controls.push(
          {
            id: 'shop-search-try-again',
            type: 'button',
            accessibleName: 'Try Again',
            aliases: ['try again', 'retry'],
            currentView: 'SHOP',
            enabled: !isProcessing,
            action: () => {
              if (queryInput.trim()) {
                void submitUserMessage(queryInput, 'voice');
              }
            },
          },
          {
            id: 'shop-search-cancel-error',
            type: 'button',
            accessibleName: 'Cancel',
            aliases: ['cancel', 'dismiss'],
            currentView: 'SHOP',
            enabled: true,
            action: () => {
              setSearchError(null);
              handleCancelFlow();
            },
          },
        );
      }

      if (products.length > 0) {
        controls.push(
          {
            id: 'shop-save-search',
            type: 'button',
            accessibleName: 'Save Search',
            aliases: ['save search', 'save this search', 'bookmark search'],
            currentView: 'SHOP',
            enabled: !isProcessing,
            disabledReason: 'Please wait for the current search to finish.',
            action: () => {
              void handleSaveCurrentSearch();
            },
          },
          {
            id: 'shop-show-more',
            type: 'button',
            accessibleName: 'Show More',
            aliases: ['show more', 'more options', 'load more', 'more products'],
            currentView: 'SHOP',
            enabled: hasMoreResults && !isLoadingMore,
            disabledReason: isLoadingMore
              ? 'Already loading more options.'
              : 'All matching products are already displayed.',
            action: () => {
              void handleShowMore();
            },
          },
        );

        products.forEach((product, idx) => {
          controls.push(
            {
              id: `shop-product-save-${product.id}`,
              type: 'product-action',
              accessibleName: 'Save',
              aliases: ['save', 'save product', 'bookmark'],
              currentView: 'SHOP',
              enabled: true,
              entityId: product.id,
              entityTitle: product.title,
              entityIndex: idx,
              action: () => {
                void handleSaveProduct(product);
              },
            },
            {
              id: `shop-product-compare-${product.id}`,
              type: 'product-action',
              accessibleName: 'Compare',
              aliases: ['compare', 'toggle compare', 'compare product'],
              currentView: 'SHOP',
              enabled: true,
              entityId: product.id,
              entityTitle: product.title,
              entityIndex: idx,
              action: () => handleToggleCompare(product),
            },
            {
              id: `shop-product-select-${product.id}`,
              type: 'product-action',
              accessibleName: 'Select',
              aliases: ['select', 'choose', 'open', 'add to cart', 'add', 'view'],
              currentView: 'SHOP',
              enabled: !isProcessing,
              disabledReason: 'Please wait for the current action to finish.',
              entityId: product.id,
              entityTitle: product.title,
              entityIndex: idx,
              action: () => {
                void handleSelectProduct(product);
              },
            },
          );
        });
      }
    } else if (currentStep === 'compare') {
      const compareItems: Product[] = comparisonData?.products || selectedForCompare;
      compareItems.forEach((product: Product, idx: number) => {
        controls.push({
          id: `shop-compare-select-${product.id}`,
          type: 'product-action',
          accessibleName: 'Select',
          aliases: ['select', 'choose', 'open', 'add to cart'],
          currentView: 'SHOP',
          enabled: !isProcessing,
          entityId: product.id,
          entityTitle: product.title,
          entityIndex: idx,
          action: () => {
            void handleSelectProduct(product);
          },
        });
      });
      controls.push(
        {
          id: 'shop-compare-back',
          type: 'button',
          accessibleName: 'Back',
          aliases: ['back', 'go back'],
          currentView: 'SHOP',
          enabled: true,
          action: handleBackStep,
        },
        {
          id: 'shop-compare-cancel',
          type: 'button',
          accessibleName: 'Cancel',
          aliases: ['cancel'],
          currentView: 'SHOP',
          enabled: true,
          action: () => {
            void handleCancelFlow();
          },
        },
      );
    } else if (currentStep === 'selected') {
      controls.push(
        {
          id: 'shop-selected-continue',
          type: 'checkout-action',
          accessibleName: 'Continue',
          aliases: ['continue', 'continue to review', 'review', 'proceed'],
          currentView: 'SHOP',
          enabled: !isProcessing,
          action: () => {
            void handleProceedToReview();
          },
        },
        {
          id: 'shop-selected-cancel',
          type: 'checkout-action',
          accessibleName: 'Cancel',
          aliases: ['cancel'],
          currentView: 'SHOP',
          enabled: !isProcessing,
          action: () => {
            void handleCancelFlow();
          },
        },
        {
          id: 'shop-selected-back',
          type: 'checkout-action',
          accessibleName: 'Back',
          aliases: ['back', 'go back'],
          currentView: 'SHOP',
          enabled: !isProcessing,
          action: handleBackStep,
        },
      );
    } else if (currentStep === 'review' && activeReview) {
      const needsSubAck = activeReview.is_subscription && !subscriptionAck;
      controls.push(
        {
          id: 'shop-review-continue',
          type: 'checkout-action',
          accessibleName: 'Continue',
          aliases: ['continue', 'proceed', 'proceed to confirmation', 'next'],
          currentView: 'PURCHASE_REVIEW',
          enabled: !needsSubAck && !isProcessing,
          disabledReason: needsSubAck
            ? 'Please acknowledge the recurring subscription terms before continuing.'
            : undefined,
          action: () => {
            void handleProceedToConfirm();
          },
        },
        {
          id: 'shop-review-cancel',
          type: 'checkout-action',
          accessibleName: 'Cancel',
          aliases: ['cancel', 'cancel purchase'],
          currentView: 'PURCHASE_REVIEW',
          enabled: !isProcessing,
          action: () => {
            void handleCancelFlow();
          },
        },
        {
          id: 'shop-review-back',
          type: 'checkout-action',
          accessibleName: 'Back',
          aliases: ['back', 'go back'],
          currentView: 'PURCHASE_REVIEW',
          enabled: !isProcessing,
          action: handleBackStep,
        },
      );
    } else if (currentStep === 'confirm' && activeReview) {
      const needsSubAck = activeReview.is_subscription && !subscriptionAck;
      controls.push(
        {
          id: 'shop-confirm-payment',
          type: 'checkout-action',
          accessibleName: `CONFIRM $${activeReview.total_today.toFixed(2)}`,
          aliases: ['confirm'],
          currentView: 'CONFIRMATION_REQUIRED',
          enabled: !needsSubAck && !isProcessing,
          sensitivePaymentAuth: true,
          action: () => {
            void handleConfirmPayment();
          },
        },
        {
          id: 'shop-confirm-cancel',
          type: 'checkout-action',
          accessibleName: 'Cancel',
          aliases: ['cancel', 'cancel purchase'],
          currentView: 'CONFIRMATION_REQUIRED',
          enabled: !isProcessing,
          action: () => {
            void handleCancelFlow();
          },
        },
        {
          id: 'shop-confirm-back',
          type: 'checkout-action',
          accessibleName: 'Back',
          aliases: ['back', 'go back'],
          currentView: 'CONFIRMATION_REQUIRED',
          enabled: !isProcessing,
          action: handleBackStep,
        },
      );
    } else if (currentStep === 'paypal') {
      controls.push(
        {
          id: 'shop-paypal-continue',
          type: 'checkout-action',
          accessibleName: 'Continue to PayPal',
          aliases: ['continue to paypal', 'approve paypal', 'open paypal', 'paypal', 'continue'],
          currentView: 'PAYPAL_CHECKOUT',
          enabled: !isProcessing,
          disabledReason: 'PayPal checkout is currently processing.',
          action: () => {
            void handlePayPalSandboxApprovalAction();
          },
        },
        {
          id: 'shop-paypal-cancel',
          type: 'checkout-action',
          accessibleName: 'Cancel',
          aliases: ['cancel', 'cancel purchase'],
          currentView: 'PAYPAL_CHECKOUT',
          enabled: !isProcessing,
          action: () => {
            void handleCancelFlow();
          },
        },
        {
          id: 'shop-paypal-back',
          type: 'checkout-action',
          accessibleName: 'Back',
          aliases: ['back', 'go back'],
          currentView: 'PAYPAL_CHECKOUT',
          enabled: !isProcessing,
          action: handleBackStep,
        },
      );
    } else if (currentStep === 'payment_failed') {
      controls.push(
        {
          id: 'shop-failed-try-again',
          type: 'checkout-action',
          accessibleName: 'Try Again',
          aliases: ['try again', 'retry'],
          currentView: 'PAYMENT_FAILURE',
          enabled: !isProcessing,
          action: async () => {
            setConfirmationError(null);
            if (!activeReview) {
              const refreshed = await prepareReview();
              if (refreshed) {
                setActiveReview(refreshed);
                setCurrentStep('confirm');
                return;
              }
              setCurrentStep('search');
              return;
            }
            setCurrentStep('confirm');
          },
        },
        {
          id: 'shop-failed-cancel',
          type: 'checkout-action',
          accessibleName: 'Cancel',
          aliases: ['cancel'],
          currentView: 'PAYMENT_FAILURE',
          enabled: true,
          action: () => {
            void handleCancelFlow();
          },
        },
      );
    } else if (currentStep === 'outcome') {
      controls.push({
        id: 'shop-outcome-done',
        type: 'button',
        accessibleName: 'Done',
        aliases: ['done', 'continue shopping', 'back to shop', 'close'],
        currentView: activeShopView,
        enabled: true,
        action: () => {
          setCurrentStep('search');
          setOutcome(null);
          setPaypalOrder(null);
        },
      });
    }

    return controls;
  }, [
    isActiveTab,
    currentStep,
    activeShopView,
    searchError,
    isProcessing,
    queryInput,
    products,
    hasMoreResults,
    isLoadingMore,
    comparisonData,
    selectedForCompare,
    activeReview,
    subscriptionAck,
  ]);

  useRegisterVoiceControls('shopping-view', shopControls, [shopControls]);

  const isLandingState =
    currentStep === 'search' && !hasUserSearched && !noResultsMessage && !searchError;

  const selectedColor =
    selectedProduct?.variants?.Color?.[1] ||
    selectedProduct?.variants?.Color?.[0] ||
    'Blue';

  return (
    <div style={{ maxWidth: '1060px', margin: '0 auto', padding: isLandingState ? '20px 20px 72px' : '24px 20px 96px' }}>

      {/* ==================================================
          CENTER: CONVERSATIONAL & TYPED SEARCH BAR
          ================================================== */}
      <section
        style={{
          backgroundColor: '#111827',
          border: isListening ? '2px solid #38bdf8' : '1px solid #1e293b',
          borderRadius: '24px',
          padding: '28px',
          marginBottom: '36px',
          boxShadow: '0 10px 30px rgba(0,0,0,0.45)',
        }}
        aria-label="Conversational AI Shopping Input"
      >
        <label
          htmlFor="ai-search-input"
          style={{
            display: 'block',
            fontSize: '1.4rem',
            fontWeight: 800,
            color: '#f8fafc',
            marginBottom: '4px',
            letterSpacing: '-0.01em',
          }}
        >
          What are you looking for?
        </label>
        <p style={{ fontSize: '0.92rem', color: '#94a3b8', margin: '0 0 14px' }}>
          Search or speak to find, compare, save, and shop.
        </p>

        <div style={{ position: 'relative' }}>
          <form
            onSubmit={(e) => {
              e.preventDefault();
              if (activeSuggestionIdx >= 0 && suggestions[activeSuggestionIdx]) {
                void runSuggestedSearch(suggestions[activeSuggestionIdx]);
                return;
              }
              setShowSuggestions(false);
              void submitUserMessage(queryInput, 'text');
            }}
            style={{ display: 'flex', gap: '12px', flexWrap: 'wrap' }}
          >
            <input
              id="ai-search-input"
              type="text"
              role="combobox"
              aria-autocomplete="list"
              aria-expanded={showSuggestions && suggestions.length > 0}
              aria-controls="search-suggestions-listbox"
              aria-activedescendant={
                activeSuggestionIdx >= 0 ? `search-suggestion-${activeSuggestionIdx}` : undefined
              }
              value={queryInput}
              onChange={(e) => setQueryInput(e.target.value)}
              onFocus={() => {
                if (suggestions.length > 0 && queryInput.trim().length >= 2) {
                  setShowSuggestions(true);
                }
              }}
              onKeyDown={(e) => {
                if (!showSuggestions || suggestions.length === 0) return;
                if (e.key === 'ArrowDown') {
                  e.preventDefault();
                  setActiveSuggestionIdx((prev) => (prev + 1) % suggestions.length);
                } else if (e.key === 'ArrowUp') {
                  e.preventDefault();
                  setActiveSuggestionIdx((prev) => (prev <= 0 ? suggestions.length - 1 : prev - 1));
                } else if (e.key === 'Escape') {
                  setShowSuggestions(false);
                  setActiveSuggestionIdx(-1);
                }
              }}
              placeholder="Find wireless headphones under $80"
              style={{
                flex: 1,
                minWidth: '240px',
                backgroundColor: '#0a0f1d',
                border: '2px solid #334155',
                borderRadius: '16px',
                padding: '16px 20px',
                color: '#ffffff',
                fontSize: '1.15rem',
                fontWeight: 500,
              }}
              aria-label="What are you looking for"
            />

            <button
              type="submit"
              disabled={isProcessing}
              style={{
                backgroundColor: '#0284c7',
                border: 'none',
                color: '#ffffff',
                padding: '16px 26px',
                borderRadius: '16px',
                fontSize: '1.05rem',
                fontWeight: 700,
                display: 'inline-flex',
                alignItems: 'center',
                gap: '8px',
                minHeight: '52px',
              }}
              aria-label="Search"
            >
              <Search size={20} />
              <span>Search</span>
            </button>
          </form>

          {showSuggestions && suggestions.length > 0 && (
            <ul
              id="search-suggestions-listbox"
              role="listbox"
              aria-label="Search suggestions"
              style={{
                position: 'absolute',
                left: 0,
                right: 0,
                top: 'calc(100% + 6px)',
                zIndex: 35,
                listStyle: 'none',
                margin: 0,
                padding: '8px',
                backgroundColor: '#0f172a',
                border: '2px solid #38bdf8',
                borderRadius: '16px',
                boxShadow: '0 16px 36px rgba(0, 0, 0, 0.65)',
                display: 'flex',
                flexDirection: 'column',
                gap: '4px',
              }}
            >
              {suggestions.map((suggestion, idx) => {
                const isSelectedOpt = idx === activeSuggestionIdx;
                return (
                  <li key={`${suggestion}-${idx}`} role="presentation">
                    <button
                      id={`search-suggestion-${idx}`}
                      type="button"
                      role="option"
                      aria-selected={isSelectedOpt}
                      onMouseDown={(ev) => {
                        ev.preventDefault();
                        void runSuggestedSearch(suggestion);
                      }}
                      style={{
                        width: '100%',
                        textAlign: 'left',
                        backgroundColor: isSelectedOpt ? '#0284c7' : 'transparent',
                        color: isSelectedOpt ? '#ffffff' : '#e2e8f0',
                        border: 'none',
                        borderRadius: '10px',
                        padding: '12px 14px',
                        fontSize: '1rem',
                        fontWeight: 600,
                        minHeight: '46px',
                        display: 'flex',
                        alignItems: 'center',
                        gap: '10px',
                      }}
                    >
                      <Search size={16} color={isSelectedOpt ? '#ffffff' : '#38bdf8'} />
                      <span>{suggestion}</span>
                    </button>
                  </li>
                );
              })}
            </ul>
          )}
        </div>

        {voiceError && (
          <div
            role="status"
            style={{
              marginTop: '12px',
              backgroundColor: '#451a03',
              border: '1px solid #f59e0b',
              color: '#fef3c7',
              borderRadius: '12px',
              padding: '10px 14px',
              fontSize: '0.94rem',
              fontWeight: 600,
            }}
          >
            {voiceError}
          </div>
        )}

        {isLandingState && (
          <div style={{ marginTop: '14px' }}>
            <ContextualVoiceTips
              commands={[
                'Find wireless headphones under $80',
                'Find a birthday gift under $30',
              ]}
              showVoiceTipsButton
              disabled={isProcessing}
            />
          </div>
        )}

        {/* Compact Recent Searches (visually distinct from Voice Tips & Saved Searches) */}
        {(isLandingState || recentSearches.length > 0) && (
          <div
            aria-label="Recent Searches"
            style={{
              marginTop: '12px',
              padding: '8px 12px',
              backgroundColor: '#0c1322',
              border: '1px solid #1e293b',
              borderRadius: '12px',
            }}
          >
            <div
              style={{
                display: 'flex',
                alignItems: 'center',
                justifyContent: 'space-between',
                gap: '8px',
                flexWrap: 'wrap',
              }}
            >
              <div style={{ display: 'flex', alignItems: 'center', gap: '8px', flexWrap: 'wrap', flex: 1, minWidth: 0 }}>
                <span
                  style={{
                    display: 'inline-flex',
                    alignItems: 'center',
                    gap: '6px',
                    fontSize: '0.78rem',
                    fontWeight: 700,
                    color: '#94a3b8',
                    letterSpacing: '0.02em',
                    flexShrink: 0,
                  }}
                >
                  <History size={13} color="#94a3b8" aria-hidden="true" />
                  <span>Recent Searches:</span>
                </span>

                {recentSearches.length === 0 ? (
                  <span style={{ fontSize: '0.8rem', color: '#64748b' }}>No recent searches yet.</span>
                ) : (
                  (showAllRecentHistory ? recentSearches : recentSearches.slice(0, 4)).map((entry) => {
                    const isBusy = busyHistoryId === entry.history_id;
                    return (
                      <span
                        key={entry.history_id}
                        style={{
                          display: 'inline-flex',
                          alignItems: 'center',
                          backgroundColor: '#111827',
                          border: '1px solid #293548',
                          borderRadius: '8px',
                          overflow: 'hidden',
                        }}
                      >
                        <button
                          type="button"
                          disabled={isProcessing || isBusy}
                          onClick={() => void handleRunRecentSearch(entry)}
                          style={{
                            backgroundColor: 'transparent',
                            border: 'none',
                            color: '#cbd5e1',
                            padding: '4px 9px',
                            fontSize: '0.8rem',
                            fontWeight: 500,
                            display: 'inline-flex',
                            alignItems: 'center',
                            gap: '5px',
                            cursor: isProcessing || isBusy ? 'not-allowed' : 'pointer',
                          }}
                          title={`Run recent search: ${entry.display_query}`}
                        >
                          <History size={11} color="#64748b" aria-hidden="true" />
                          <span>{entry.display_query}</span>
                        </button>
                        <button
                          type="button"
                          disabled={isBusy}
                          onClick={() => void handleSaveRecentSearch(entry)}
                          aria-label={`Save recent search ${entry.display_query}`}
                          title="Save to Saved Searches"
                          style={{
                            backgroundColor: 'transparent',
                            border: 'none',
                            borderLeft: '1px solid #1e293b',
                            color: '#94a3b8',
                            padding: '4px 7px',
                            display: 'inline-flex',
                            alignItems: 'center',
                            cursor: isBusy ? 'not-allowed' : 'pointer',
                          }}
                        >
                          <Bookmark size={12} aria-hidden="true" />
                        </button>
                      </span>
                    );
                  })
                )}
              </div>

              {showAllRecentHistory && (
                <button
                  type="button"
                  onClick={() => setShowAllRecentHistory(false)}
                  style={{
                    backgroundColor: 'transparent',
                    border: 'none',
                    color: '#94a3b8',
                    fontSize: '0.76rem',
                    fontWeight: 600,
                    cursor: 'pointer',
                    padding: '2px 6px',
                  }}
                >
                  Show less
                </button>
              )}
            </div>

            {historyNotice && (
              <div role="status" style={{ marginTop: '6px', fontSize: '0.78rem', color: '#6ee7b7', fontWeight: 600 }}>
                {historyNotice}
              </div>
            )}
          </div>
        )}

        {/* Concise AI Assistant Response */}
        <div
          style={{
            marginTop: '18px',
            backgroundColor: '#0a0f1d',
            border: '1px solid #1e293b',
            borderRadius: '14px',
            padding: '16px 20px',
            display: 'flex',
            alignItems: 'flex-start',
            gap: '12px',
          }}
          role="status"
          aria-live="polite"
        >
          <Volume2 size={22} color="#38bdf8" style={{ marginTop: '2px', flexShrink: 0 }} />
          <p style={{ fontSize: '1.08rem', color: '#f8fafc', margin: 0, fontWeight: 500, whiteSpace: 'pre-line', lineHeight: 1.55 }}>
            {isProcessing ? processingLabel : aiMessage}
          </p>
        </div>
      </section>

      {/* Accessible Search Error Banner */}
      {searchError && (
        <div
          style={{
            backgroundColor: '#182235',
            border: '2px solid #ef4444',
            borderRadius: '18px',
            padding: '24px',
            marginBottom: '28px',
            textAlign: 'center',
          }}
          role="alert"
          aria-live="assertive"
        >
          <p
            style={{
              fontSize: '1.2rem',
              fontWeight: 800,
              color: '#f8fafc',
              marginBottom: '18px',
              whiteSpace: 'pre-line',
              lineHeight: 1.5,
            }}
          >
            {"I'm having trouble searching right now.\nPlease try again."}
          </p>
          <div style={{ display: 'flex', justifyContent: 'center', gap: '12px', flexWrap: 'wrap' }}>
            <button
              type="button"
              onClick={() => {
                void submitUserMessage(queryInput, 'text');
              }}
              className="btn-confirm"
              style={{
                backgroundColor: '#0284c7',
                color: '#ffffff',
                fontWeight: 800,
                padding: '12px 24px',
                borderRadius: '12px',
                border: 'none',
              }}
            >
              Try Again
            </button>
            <button
              type="button"
              onClick={() => {
                setSearchError(null);
                handleCancelFlow();
              }}
              className="btn-cancel"
              style={{
                backgroundColor: 'transparent',
                border: '2px solid #ef4444',
                color: '#ef4444',
                fontWeight: 800,
                padding: '12px 24px',
                borderRadius: '12px',
              }}
            >
              Cancel
            </button>
          </div>
        </div>
      )}

      {/* No Results Found Message (only when zero products are displayed) */}
      {noResultsMessage && !searchError && products.length === 0 && (
        <div
          style={{
            backgroundColor: '#182235',
            border: '1px solid #334155',
            borderRadius: '18px',
            padding: '28px',
            marginBottom: '28px',
            textAlign: 'center',
          }}
          role="status"
        >
          <p style={{ fontSize: '1.15rem', fontWeight: 700, color: '#f8fafc', whiteSpace: 'pre-line', margin: 0 }}>
            {noResultsMessage}
          </p>
          {aboveBudgetOffer && (
            <button
              type="button"
              onClick={() => {
                setProducts(aboveBudgetOffer.products);
                setNoResultsMessage(null);
                setSearchError(null);
                setAiMessage(`Showing ${aboveBudgetOffer.products.length} matching options above $${aboveBudgetOffer.limit}.`);
                announce(`Showing ${aboveBudgetOffer.products.length} matching options above ${aboveBudgetOffer.limit} dollars.`);
                setAboveBudgetOffer(null);
              }}
              style={{
                marginTop: '16px',
                backgroundColor: '#0284c7',
                color: '#ffffff',
                fontWeight: 700,
                padding: '12px 22px',
                borderRadius: '12px',
                border: 'none',
              }}
            >
              Show matching products above ${aboveBudgetOffer.limit}
            </button>
          )}
        </div>
      )}

      {/* Ambiguity / Safety Guard Alert (if user said "Yes", "That looks good", etc.) */}
      {confirmationError && currentStep !== 'confirm' && (
        <div
          style={{
            backgroundColor: 'rgba(239, 68, 68, 0.15)',
            border: '2px solid #ef4444',
            borderRadius: '16px',
            padding: '16px 22px',
            marginBottom: '28px',
            color: '#fca5a5',
            fontSize: '1rem',
            fontWeight: 600,
            whiteSpace: 'pre-line',
          }}
          role="alert"
          aria-live="assertive"
        >
          {confirmationError}
        </div>
      )}

      {/* Cheaper Alternative Banner */}
      {cheaperAlert && (currentStep === 'search' || currentStep === 'compare') && (
        <div
          style={{
            backgroundColor: '#182235',
            border: '2px solid #10b981',
            borderRadius: '18px',
            padding: '20px 24px',
            marginBottom: '28px',
            display: 'flex',
            flexWrap: 'wrap',
            alignItems: 'center',
            justifyContent: 'space-between',
            gap: '16px',
          }}
          role="alert"
        >
          <div style={{ display: 'flex', alignItems: 'center', gap: '12px' }}>
            <Sparkles size={24} color="#10b981" />
            <div>
              <div style={{ fontWeight: 800, color: '#10b981', fontSize: '1.05rem' }}>
                Cheaper Alternative Available
              </div>
              <p style={{ fontSize: '0.98rem', color: '#f8fafc', margin: '2px 0 0' }}>
                <strong>{cheaperAlert.alternative.title}</strong> —{' '}
                <strong style={{ color: '#38bdf8' }}>${cheaperAlert.alternative.price.toFixed(2)}</strong>{' '}
                (${cheaperAlert.savings.toFixed(2)} cheaper)
              </p>
            </div>
          </div>
          <div style={{ display: 'flex', gap: '10px' }}>
            <button
              type="button"
              onClick={() => handleSelectProduct(cheaperAlert.alternative)}
              style={{
                backgroundColor: '#10b981',
                color: '#0a0f1d',
                fontWeight: 800,
                padding: '10px 18px',
                borderRadius: '12px',
                border: 'none',
              }}
            >
              Select ${cheaperAlert.alternative.price.toFixed(2)} Option
            </button>
          </div>
        </div>
      )}

      {/* ==================================================
          BELOW: ONLY SHOW INFORMATION RELEVANT TO CURRENT STEP
          ================================================== */}

      {/* STEP 1: PRODUCT SEARCH RESULTS */}
      {currentStep === 'search' && (
        <section aria-label="Product Search Results">
          {products.length > 0 && !noResultsMessage && !searchError && (
            <>
              <div style={{ marginBottom: '16px' }}>
                <ContextualVoiceTips
                  title="Ask about these products"
                  commands={[
                    'Compare the first two',
                    'Show something cheaper',
                    'Save the second one',
                    'Add the first one to cart',
                  ]}
                  showVoiceTipsButton
                />
              </div>
              <div
                style={{
                  display: 'flex',
                  flexWrap: 'wrap',
                  justifyContent: 'space-between',
                  alignItems: 'center',
                  gap: '12px',
                  marginBottom: '16px',
                }}
              >
                <div style={{ color: '#cbd5e1', fontSize: '0.96rem', fontWeight: 600 }}>
                  Showing {products.length}
                  {totalCandidates > products.length ? ` of ${totalCandidates}` : ''} option{products.length === 1 ? '' : 's'}
                </div>
                <div style={{ display: 'flex', alignItems: 'center', gap: '10px' }}>
                  {searchSavedNotice && (
                    <span role="status" style={{ color: '#6ee7b7', fontSize: '0.9rem', fontWeight: 700 }}>
                      {searchSavedNotice}
                    </span>
                  )}
                  <button
                    type="button"
                    onClick={handleSaveCurrentSearch}
                    style={{
                      backgroundColor: '#1e293b',
                      color: '#e2e8f0',
                      border: '1px solid #475569',
                      borderRadius: '10px',
                      padding: '8px 14px',
                      fontWeight: 700,
                      fontSize: '0.92rem',
                      display: 'inline-flex',
                      alignItems: 'center',
                      gap: '6px',
                    }}
                  >
                    <Bookmark size={15} />
                    <span>Save Search</span>
                  </button>
                </div>
              </div>

              <div
                style={{
                  display: 'grid',
                  gridTemplateColumns: 'repeat(auto-fit, minmax(290px, 1fr))',
                  gap: '24px',
                }}
              >
                {products.map((product, index) => (
                  <ProductCard
                    key={product.id}
                    product={product}
                    onCompare={handleToggleCompare}
                    onSelect={handleSelectProduct}
                    onSave={handleSaveProduct}
                    isCompared={selectedForCompare.some((p) => p.id === product.id)}
                    isSelected={selectedProduct?.id === product.id}
                    isSaved={(savedProductIds || localSavedIds).has(product.id)}
                  />
                ))}
              </div>

              {hasMoreResults && (
                <div style={{ display: 'flex', justifyContent: 'center', marginTop: '24px' }}>
                  <button
                    type="button"
                    disabled={isLoadingMore}
                    onClick={handleShowMore}
                    style={{
                      backgroundColor: '#1e293b',
                      color: '#f8fafc',
                      border: '2px solid #0284c7',
                      borderRadius: '14px',
                      padding: '12px 26px',
                      fontWeight: 800,
                      fontSize: '1rem',
                      display: 'inline-flex',
                      alignItems: 'center',
                      gap: '8px',
                    }}
                  >
                    <PlusCircle size={18} />
                    <span>{isLoadingMore ? 'Loading more...' : 'Show More'}</span>
                  </button>
                </div>
              )}
            </>
          )}

          {/* Accessible Cancel & Back hooks for Switch Mode on Search screen */}
          <div style={{ display: 'flex', justifyContent: 'flex-end', gap: '12px', marginTop: '24px' }}>
            <button
              type="button"
              onClick={handleCancelFlow}
              className="btn-cancel"
              style={{
                backgroundColor: 'transparent',
                border: '1px solid #ef4444',
                color: '#ef4444',
                padding: '10px 18px',
                borderRadius: '12px',
                fontWeight: 700,
              }}
            >
              CANCEL
            </button>
            <button
              type="button"
              onClick={handleBackStep}
              className="btn-back"
              style={{
                backgroundColor: 'transparent',
                border: '1px solid #334155',
                color: '#cbd5e1',
                padding: '10px 18px',
                borderRadius: '12px',
                fontWeight: 700,
              }}
            >
              BACK
            </button>
          </div>
        </section>
      )}

      {/* STEP 2: AI PRODUCT COMPARISON */}
      {currentStep === 'compare' && (
        <section
          style={{
            backgroundColor: '#111827',
            border: '2px solid #38bdf8',
            borderRadius: '24px',
            padding: '32px',
          }}
          aria-label="Product Comparison"
        >
          <div style={{ display: 'flex', alignItems: 'center', gap: '10px', marginBottom: '20px' }}>
            <Layers size={24} color="#38bdf8" />
            <h2 style={{ fontSize: '1.45rem', fontWeight: 800, color: '#f8fafc', margin: 0 }}>
              Comparison
            </h2>
          </div>

          {comparisonData?.summary && (
            <div
              style={{
                backgroundColor: '#182235',
                borderLeft: '4px solid #38bdf8',
                padding: '20px 24px',
                borderRadius: '12px',
                marginBottom: '28px',
                whiteSpace: 'pre-line',
                fontSize: '1.12rem',
                lineHeight: 1.65,
                color: '#f8fafc',
                fontWeight: 500,
              }}
            >
              {comparisonData.summary}
            </div>
          )}

          <div
            style={{
              display: 'grid',
              gridTemplateColumns: 'repeat(auto-fit, minmax(260px, 1fr))',
              gap: '20px',
              marginBottom: '28px',
            }}
          >
            {selectedForCompare.map((prod, idx) => (
              <div
                key={prod.id}
                style={{
                  backgroundColor: '#182235',
                  border: '1px solid #24324d',
                  borderRadius: '16px',
                  padding: '24px',
                  display: 'flex',
                  flexDirection: 'column',
                  justifyContent: 'space-between',
                }}
              >
                <div>
                  <span style={{ fontSize: '0.85rem', fontWeight: 800, color: '#38bdf8', textTransform: 'uppercase' }}>
                    Option {idx + 1} — ${prod.price.toFixed(2)}
                  </span>
                  <h3 style={{ fontSize: '1.2rem', fontWeight: 800, color: '#f8fafc', margin: '8px 0 10px' }}>
                    {prod.title}
                  </h3>
                  <p style={{ fontSize: '0.95rem', color: '#cbd5e1', lineHeight: 1.5 }}>
                    {prod.documented_accessibility_features?.[0] || prod.description}
                  </p>
                </div>

                <button
                  type="button"
                  onClick={() => handleSelectProduct(prod)}
                  className={idx === 0 ? 'btn-confirm' : undefined}
                  style={{
                    marginTop: '20px',
                    backgroundColor: '#0284c7',
                    color: '#ffffff',
                    fontWeight: 800,
                    padding: '14px',
                    borderRadius: '12px',
                    border: 'none',
                    width: '100%',
                  }}
                >
                  Choose Option {idx + 1}
                </button>
              </div>
            ))}
          </div>

          <div style={{ display: 'flex', gap: '12px' }}>
            <button
              type="button"
              onClick={handleCancelFlow}
              className="btn-cancel"
              style={{
                flex: 1,
                backgroundColor: 'transparent',
                border: '2px solid #ef4444',
                color: '#ef4444',
                padding: '14px',
                borderRadius: '14px',
                fontWeight: 800,
              }}
            >
              CANCEL
            </button>
            <button
              type="button"
              onClick={handleBackStep}
              className="btn-back"
              style={{
                flex: 1,
                backgroundColor: 'transparent',
                border: '2px solid #334155',
                color: '#cbd5e1',
                padding: '14px',
                borderRadius: '14px',
                fontWeight: 800,
              }}
            >
              BACK
            </button>
          </div>
        </section>
      )}

      {/* STEP 3: PRODUCT SELECTION REVIEW */}
      {currentStep === 'selected' && selectedProduct && (
        <section
          style={{
            backgroundColor: '#111827',
            border: '2px solid #0284c7',
            borderRadius: '24px',
            padding: '36px',
            maxWidth: '640px',
            margin: '0 auto',
          }}
          aria-label="Product Selection Review"
        >
          <div style={{ marginBottom: '24px' }}>
            <h2 style={{ fontSize: '1.75rem', fontWeight: 900, color: '#f8fafc', margin: '0 0 6px' }}>
              {selectedProduct.title}
            </h2>
            <p style={{ fontSize: '0.98rem', color: '#94a3b8', margin: '0 0 10px', fontWeight: 600 }}>
              From: <span style={{ color: '#cbd5e1' }}>{selectedProduct.merchant}</span>
            </p>
            <div style={{ fontSize: '2rem', fontWeight: 900, color: '#38bdf8' }}>
              ${selectedProduct.price.toFixed(2)}
            </div>
          </div>

          <div
            style={{
              backgroundColor: '#182235',
              border: '1px solid #24324d',
              borderRadius: '16px',
              padding: '20px 24px',
              marginBottom: '24px',
            }}
          >
            <div style={{ fontSize: '0.95rem', color: '#94a3b8', marginBottom: '6px' }}>You selected:</div>
            <div style={{ fontSize: '1.15rem', color: '#f8fafc', fontWeight: 800 }}>
              {selectedColor}
            </div>
            <div style={{ fontSize: '1.15rem', color: '#f8fafc', fontWeight: 800, marginTop: '4px' }}>
              Quantity: {cart?.items.find((ci) => ci.product_id === selectedProduct.id)?.quantity ?? 1}
            </div>
            {cart && cart.item_count > 1 && (
              <div style={{ fontSize: '0.95rem', color: '#38bdf8', fontWeight: 700, marginTop: '8px' }}>
                Cart: {cart.items.length} product{cart.items.length === 1 ? '' : 's'} ({cart.item_count} items) — Total ${cart.total_today.toFixed(2)}
              </div>
            )}
          </div>

          <p style={{ fontSize: '1rem', color: '#10b981', fontWeight: 700, marginBottom: '16px' }}>
            No payment has been made yet.
          </p>

          <div style={{ marginBottom: '22px' }}>
            <ContextualVoiceTips
              title={`Selected: ${selectedProduct.title}`}
              commands={['Add this to cart', 'Tell me more', 'Show something cheaper']}
            />
          </div>

          <div style={{ display: 'flex', flexDirection: 'column', gap: '12px' }}>
            <button
              type="button"
              onClick={handleProceedToReview}
              className="btn-confirm"
              style={{
                backgroundColor: '#0284c7',
                color: '#ffffff',
                padding: '18px',
                borderRadius: '14px',
                fontWeight: 900,
                fontSize: '1.15rem',
                border: 'none',
              }}
            >
              Continue
            </button>

            <div style={{ display: 'flex', gap: '12px' }}>
              <button
                type="button"
                onClick={handleCancelFlow}
                className="btn-cancel"
                style={{
                  flex: 1,
                  backgroundColor: 'transparent',
                  border: '2px solid #ef4444',
                  color: '#ef4444',
                  padding: '14px',
                  borderRadius: '14px',
                  fontWeight: 800,
                  fontSize: '1rem',
                }}
              >
                CANCEL
              </button>

              <button
                type="button"
                onClick={handleBackStep}
                className="btn-back"
                style={{
                  flex: 1,
                  backgroundColor: 'transparent',
                  border: '2px solid #334155',
                  color: '#cbd5e1',
                  padding: '14px',
                  borderRadius: '14px',
                  fontWeight: 800,
                  fontSize: '1rem',
                }}
              >
                BACK
              </button>
            </div>
          </div>
        </section>
      )}

      {/* STEP 4: ACCESSIBLE PURCHASE REVIEW */}
      {currentStep === 'review' && activeReview && (
        <section
          style={{
            backgroundColor: '#111827',
            border: '2px solid #38bdf8',
            borderRadius: '24px',
            padding: '36px',
            maxWidth: '640px',
            margin: '0 auto',
          }}
          aria-label="Accessible Purchase Review"
        >
          <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', marginBottom: '6px', flexWrap: 'wrap', gap: '8px' }}>
            <div>
              <div style={{ fontSize: '0.76rem', fontWeight: 800, color: '#38bdf8', letterSpacing: '0.06em', textTransform: 'uppercase', marginBottom: '4px' }}>
                REVIEW YOUR PURCHASE
              </div>
              <h2 style={{ fontSize: '1.75rem', fontWeight: 900, color: '#f8fafc', margin: 0 }}>
                {activeReview.cart.items.length > 1
                  ? `Purchase Review (${activeReview.cart.item_count} items)`
                  : activeReview.cart.items[0]?.product.title || 'Purchase Review'}
              </h2>
            </div>
            <span
              style={{
                backgroundColor: '#1e293b',
                border: '1px solid #38bdf8',
                color: '#38bdf8',
                fontSize: '0.78rem',
                fontWeight: 700,
                padding: '4px 10px',
                borderRadius: '999px',
              }}
            >
              Demo payment — PayPal Sandbox
            </span>
          </div>
          <p style={{ fontSize: '0.94rem', color: '#cbd5e1', margin: '0 0 18px', fontWeight: 500 }}>
            Nothing is charged until you confirm the exact total.
          </p>

          {activeReview.is_invalidated && (
            <div
              style={{
                backgroundColor: 'rgba(239, 68, 68, 0.15)',
                border: '2px solid #ef4444',
                borderRadius: '16px',
                padding: '18px 22px',
                marginBottom: '24px',
                color: '#fca5a5',
                fontWeight: 700,
                whiteSpace: 'pre-line',
              }}
              role="alert"
              aria-live="assertive"
            >
              {activeReview.invalidation_reason || 'The price changed.\n\nPlease review the updated total.'}
              <div style={{ marginTop: '12px' }}>
                <button
                  type="button"
                  onClick={handleProceedToReview}
                  style={{
                    backgroundColor: '#0284c7',
                    color: '#ffffff',
                    padding: '10px 18px',
                    borderRadius: '10px',
                    fontWeight: 800,
                    border: 'none',
                  }}
                >
                  Review Updated Total
                </button>
              </div>
            </div>
          )}

          <div
            style={{
              backgroundColor: '#182235',
              border: '1px solid #24324d',
              borderRadius: '16px',
              padding: '24px',
              marginBottom: '20px',
            }}
          >
            {activeReview.cart.items.map((item) => (
              <div
                key={item.id}
                style={{
                  display: 'flex',
                  justifyContent: 'space-between',
                  alignItems: 'baseline',
                  gap: '12px',
                  marginBottom: '12px',
                  fontSize: '1.05rem',
                  color: '#f8fafc',
                  fontWeight: 700,
                }}
              >
                <span>
                  {item.product.title}
                  <span style={{ display: 'block', fontSize: '0.88rem', color: '#94a3b8', fontWeight: 600 }}>
                    ${item.product.price.toFixed(2)} × {item.quantity} ({item.product.merchant})
                  </span>
                </span>
                <span>${item.item_total.toFixed(2)}</span>
              </div>
            ))}

            <div
              style={{
                display: 'flex',
                justifyContent: 'space-between',
                marginBottom: '10px',
                paddingTop: '10px',
                borderTop: '1px solid #24324d',
                fontSize: '1rem',
                color: '#cbd5e1',
                fontWeight: 700,
              }}
            >
              <span>Subtotal ({activeReview.cart.item_count} {activeReview.cart.item_count === 1 ? 'item' : 'items'})</span>
              <span>${activeReview.item_subtotal.toFixed(2)}</span>
            </div>

            <div style={{ display: 'flex', justifyContent: 'space-between', marginBottom: '10px', fontSize: '1rem', color: '#cbd5e1' }}>
              <span>Shipping</span>
              <span>${activeReview.shipping.toFixed(2)}</span>
            </div>

            <div style={{ display: 'flex', justifyContent: 'space-between', marginBottom: '16px', fontSize: '1rem', color: '#cbd5e1' }}>
              <span>Tax</span>
              <span>${activeReview.tax.toFixed(2)}</span>
            </div>

            <div
              style={{
                borderTop: '2px solid #24324d',
                paddingTop: '16px',
                display: 'flex',
                justifyContent: 'space-between',
                alignItems: 'baseline',
              }}
            >
              <span style={{ fontSize: '1.35rem', fontWeight: 900, color: '#ffffff' }}>TOTAL</span>
              <span style={{ fontSize: '1.85rem', fontWeight: 900, color: '#38bdf8' }}>
                ${activeReview.total_today.toFixed(2)}
              </span>
            </div>

            {!activeReview.is_subscription && (
              <div style={{ marginTop: '14px', fontSize: '0.95rem', color: '#94a3b8', fontWeight: 800, letterSpacing: '0.04em' }}>
                ONE-TIME PURCHASE
              </div>
            )}
          </div>

          <div
            style={{
              backgroundColor: 'rgba(16, 185, 129, 0.1)',
              border: '1px solid rgba(16, 185, 129, 0.4)',
              borderRadius: '14px',
              padding: '14px 18px',
              marginBottom: '20px',
              display: 'flex',
              alignItems: 'flex-start',
              gap: '12px',
            }}
          >
            <ShieldCheck size={22} color="#10b981" aria-hidden="true" style={{ flexShrink: 0, marginTop: '2px' }} />
            <div>
              <div style={{ fontSize: '1.02rem', color: '#10b981', fontWeight: 800 }}>
                Nothing is charged until you confirm the exact amount.
              </div>
              <div style={{ fontSize: '0.94rem', color: '#e2e8f0', marginTop: '4px', fontWeight: 600 }}>
                Next step &mdash; Say: <strong style={{ color: '#38bdf8' }}>&ldquo;Confirm ${activeReview.total_today.toFixed(2)} purchase&rdquo;</strong>
              </div>
            </div>
          </div>

          {/* HIGH-VALUE PURCHASE NOTICE (> $500) */}
          {activeReview.is_high_value && (
            <div
              style={{
                backgroundColor: 'rgba(56, 189, 248, 0.12)',
                border: '2px solid #38bdf8',
                borderRadius: '16px',
                padding: '16px 20px',
                marginBottom: '20px',
              }}
              role="status"
            >
              <strong style={{ color: '#38bdf8', display: 'block', fontSize: '1rem', marginBottom: '4px' }}>
                HIGH-VALUE PURCHASE PROTECTION (${activeReview.total_today.toFixed(2)})
              </strong>
              <span style={{ color: '#f8fafc', fontSize: '0.95rem' }}>
                Step 1: Review ${activeReview.total_today.toFixed(2)} purchase. Step 2: Explicit confirmation before PayPal checkout.
              </span>
            </div>
          )}

          {/* SUBSCRIPTION WARNING */}
          {activeReview.is_subscription && (
            <div
              style={{
                backgroundColor: 'rgba(245, 158, 11, 0.15)',
                border: '2px solid #f59e0b',
                borderRadius: '16px',
                padding: '20px 24px',
                marginBottom: '24px',
              }}
              role="alert"
            >
              <div style={{ display: 'flex', alignItems: 'center', gap: '10px', marginBottom: '10px' }}>
                <AlertTriangle size={24} color="#f59e0b" />
                <strong style={{ fontSize: '1.15rem', color: '#f59e0b', letterSpacing: '0.05em' }}>
                  RECURRING PAYMENT
                </strong>
              </div>
              <p style={{ fontSize: '1.15rem', color: '#f8fafc', margin: '6px 0', fontWeight: 800 }}>
                ${activeReview.total_today.toFixed(2)} today
              </p>
              <p style={{ fontSize: '1.15rem', color: '#f8fafc', margin: '6px 0 14px', fontWeight: 800 }}>
                ${activeReview.total_today.toFixed(2)} every month
              </p>
              <label
                style={{
                  display: 'flex',
                  alignItems: 'center',
                  gap: '12px',
                  cursor: 'pointer',
                  backgroundColor: '#111827',
                  padding: '12px 16px',
                  borderRadius: '12px',
                  border: '1px solid #f59e0b',
                  color: '#f8fafc',
                  fontWeight: 700,
                }}
              >
                <input
                  type="checkbox"
                  checked={subscriptionAck}
                  onChange={(e) => handleToggleSubscriptionAck(e.target.checked)}
                  style={{ width: '22px', height: '22px' }}
                />
                <span>I acknowledge this recurring monthly payment (${activeReview.total_today.toFixed(2)} every month)</span>
              </label>
              <p style={{ fontSize: '0.82rem', color: '#cbd5e1', marginTop: '10px', marginBottom: 0 }}>
                Demo safety scenario: Recurring billing requires explicit acknowledgement before PayPal Sandbox checkout.
              </p>
            </div>
          )}

          <div style={{ display: 'flex', flexDirection: 'column', gap: '14px' }}>
            <button
              type="button"
              onClick={handleProceedToConfirm}
              className="btn-confirm"
              style={{
                backgroundColor: '#0284c7',
                color: '#ffffff',
                padding: '18px',
                borderRadius: '14px',
                fontWeight: 900,
                fontSize: '1.15rem',
                border: 'none',
              }}
            >
              Continue
            </button>

            <div style={{ display: 'flex', gap: '12px' }}>
              <button
                type="button"
                onClick={handleCancelFlow}
                className="btn-cancel"
                style={{
                  flex: 1,
                  backgroundColor: 'transparent',
                  border: '2px solid #ef4444',
                  color: '#ef4444',
                  padding: '14px',
                  borderRadius: '14px',
                  fontWeight: 800,
                  fontSize: '1rem',
                }}
              >
                Cancel
              </button>

              <button
                type="button"
                onClick={handleBackStep}
                className="btn-back"
                style={{
                  flex: 1,
                  backgroundColor: 'transparent',
                  border: '2px solid #334155',
                  color: '#cbd5e1',
                  padding: '14px',
                  borderRadius: '14px',
                  fontWeight: 800,
                  fontSize: '1rem',
                }}
              >
                BACK
              </button>
            </div>
          </div>
        </section>
      )}

      {/* STEP 5: ACCESSIBLE PAYMENT CONFIRMATION */}
      {currentStep === 'confirm' && activeReview && (
        <section
          style={{
            backgroundColor: '#111827',
            border: '3px solid #38bdf8',
            borderRadius: '24px',
            padding: '36px',
            maxWidth: '640px',
            margin: '0 auto',
          }}
          aria-label="Accessible Payment Confirmation"
        >
          <div style={{ textAlign: 'center', marginBottom: '28px' }}>
            <div
              style={{
                width: '64px',
                height: '64px',
                borderRadius: '50%',
                backgroundColor: 'rgba(2, 132, 199, 0.2)',
                display: 'flex',
                alignItems: 'center',
                justifyContent: 'center',
                margin: '0 auto 16px',
              }}
            >
              <ShieldCheck size={36} color="#38bdf8" />
            </div>

            <h2 style={{ fontSize: '1.85rem', fontWeight: 900, color: '#f8fafc', marginBottom: '8px' }}>
              Your total is ${activeReview.total_today.toFixed(2)}.
            </h2>
            <p style={{ fontSize: '1.15rem', color: '#10b981', fontWeight: 800, marginBottom: '8px' }}>
              No payment has been made yet.
            </p>
            <div
              style={{
                backgroundColor: 'rgba(16, 185, 129, 0.1)',
                border: '1px solid rgba(16, 185, 129, 0.35)',
                borderRadius: '12px',
                padding: '10px 14px',
                margin: '10px auto 12px',
                maxWidth: '460px',
                textAlign: 'left',
              }}
            >
              <div style={{ fontSize: '0.88rem', fontWeight: 800, color: '#6ee7b7', marginBottom: '2px' }}>
                You&apos;re in control
              </div>
              <div style={{ fontSize: '0.84rem', color: '#cbd5e1', lineHeight: 1.4 }}>
                Casual responses like &lsquo;yes&rsquo; or &lsquo;okay&rsquo; will not authorize payment.
              </div>
            </div>
            <span
              style={{
                display: 'inline-flex',
                alignItems: 'center',
                gap: '6px',
                backgroundColor: '#1e293b',
                border: '1px solid #38bdf8',
                color: '#38bdf8',
                fontSize: '0.8rem',
                fontWeight: 700,
                padding: '5px 12px',
                borderRadius: '999px',
              }}
            >
              <CreditCard size={14} aria-hidden="true" />
              PayPal Sandbox
            </span>
            <p style={{ fontSize: '0.88rem', color: '#94a3b8', margin: '8px 0 0' }}>
              Secure payment approval through PayPal Sandbox.
            </p>
          </div>

          {activeReview.is_high_value && (
            <div
              style={{
                backgroundColor: 'rgba(56, 189, 248, 0.12)',
                border: '2px solid #38bdf8',
                borderRadius: '14px',
                padding: '14px 18px',
                marginBottom: '20px',
                textAlign: 'center',
                color: '#f8fafc',
                fontWeight: 700,
              }}
            >
              High-Value Confirmation — Step {activeReview.high_value_step} of {activeReview.high_value_total_steps}
            </div>
          )}

          {activeReview.is_subscription && (
            <div
              style={{
                backgroundColor: 'rgba(245, 158, 11, 0.15)',
                border: '2px solid #f59e0b',
                borderRadius: '14px',
                padding: '16px 20px',
                marginBottom: '20px',
                textAlign: 'center',
              }}
            >
              <strong style={{ color: '#f59e0b', display: 'block', fontSize: '1rem' }}>RECURRING PAYMENT</strong>
              <span style={{ color: '#f8fafc', fontWeight: 700 }}>
                ${activeReview.total_today.toFixed(2)} today &bull; ${activeReview.total_today.toFixed(2)} every month
              </span>
            </div>
          )}

          <div
            style={{
              backgroundColor: '#182235',
              border: '2px dashed #38bdf8',
              borderRadius: '16px',
              padding: '20px 22px',
              textAlign: 'center',
              marginBottom: '24px',
            }}
          >
            <div style={{ fontSize: '0.78rem', fontWeight: 800, color: '#38bdf8', textTransform: 'uppercase', letterSpacing: '0.06em', marginBottom: '6px' }}>
              Explicit Authorization Required
            </div>
            <p style={{ fontSize: '1.25rem', fontWeight: 900, color: '#f8fafc', margin: 0 }}>
              Say: &ldquo;{activeReview.expected_phrase}&rdquo;
            </p>
          </div>

          {confirmationError && (
            <div
              style={{
                backgroundColor: 'rgba(239, 68, 68, 0.15)',
                border: '2px solid #ef4444',
                borderRadius: '12px',
                padding: '16px 20px',
                marginBottom: '24px',
                color: '#fca5a5',
                fontSize: '0.98rem',
                lineHeight: 1.5,
                whiteSpace: 'pre-line',
              }}
              role="alert"
              aria-live="assertive"
            >
              {confirmationError}
            </div>
          )}

          <div style={{ display: 'flex', flexDirection: 'column', gap: '14px' }}>
            <button
              type="button"
              disabled={isProcessing}
              onClick={() => handleConfirmPayment()}
              className="btn-confirm"
              style={{
                backgroundColor: '#10b981',
                color: '#0a0f1d',
                padding: '20px',
                borderRadius: '16px',
                fontSize: '1.25rem',
                fontWeight: 900,
                border: 'none',
                letterSpacing: '0.04em',
              }}
              aria-label={`CONFIRM $${activeReview.total_today.toFixed(2)}`}
            >
              {isProcessing ? 'Processing payment...' : `CONFIRM $${activeReview.total_today.toFixed(2)}`}
            </button>

            <div style={{ display: 'flex', gap: '12px' }}>
              <button
                type="button"
                disabled={isProcessing}
                onClick={handleCancelFlow}
                className="btn-cancel"
                style={{
                  flex: 1,
                  backgroundColor: '#182235',
                  border: '2px solid #ef4444',
                  color: '#ef4444',
                  padding: '16px',
                  borderRadius: '14px',
                  fontSize: '1.1rem',
                  fontWeight: 800,
                }}
                aria-label="CANCEL"
              >
                CANCEL
              </button>

              <button
                type="button"
                disabled={isProcessing}
                onClick={handleBackStep}
                className="btn-back"
                style={{
                  flex: 1,
                  backgroundColor: '#182235',
                  border: '2px solid #334155',
                  color: '#cbd5e1',
                  padding: '16px',
                  borderRadius: '14px',
                  fontSize: '1.1rem',
                  fontWeight: 800,
                }}
                aria-label="BACK"
              >
                BACK
              </button>
            </div>
          </div>
        </section>
      )}

      {/* STEP 6: PAYPAL SANDBOX CHECKOUT */}
      {currentStep === 'paypal' && paypalOrder && (
        <section
          style={{
            backgroundColor: '#111827',
            border: '3px solid #38bdf8',
            borderRadius: '24px',
            padding: '36px',
            maxWidth: '640px',
            margin: '0 auto',
          }}
          aria-label="PayPal Sandbox Checkout"
        >
          <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', marginBottom: '20px', flexWrap: 'wrap', gap: '8px' }}>
            <div style={{ display: 'flex', alignItems: 'center', gap: '10px' }}>
              <Lock size={24} color="#38bdf8" />
              <h2 style={{ fontSize: '1.65rem', fontWeight: 900, color: '#f8fafc', margin: 0 }}>
                PayPal Sandbox Checkout
              </h2>
            </div>
            <span
              style={{
                display: 'inline-flex',
                alignItems: 'center',
                gap: '6px',
                backgroundColor: '#1e293b',
                border: '1px solid #38bdf8',
                color: '#38bdf8',
                fontSize: '0.8rem',
                fontWeight: 700,
                padding: '5px 12px',
                borderRadius: '999px',
              }}
            >
              <CreditCard size={14} aria-hidden="true" />
              PayPal Sandbox
            </span>
          </div>
          <p style={{ fontSize: '0.92rem', color: '#94a3b8', margin: '-12px 0 18px' }}>
            You confirmed the amount. PayPal handles buyer approval.
          </p>

          <div
            style={{
              backgroundColor: '#182235',
              border: '1px solid #24324d',
              borderRadius: '16px',
              padding: '22px 24px',
              marginBottom: '24px',
            }}
          >
            <div style={{ fontSize: '1.15rem', fontWeight: 800, color: '#f8fafc', marginBottom: '6px' }}>
              {paypalOrder.product_title}
            </div>
            <div style={{ fontSize: '0.95rem', color: '#94a3b8', marginBottom: '12px' }}>
              Merchant: <strong style={{ color: '#cbd5e1' }}>{paypalOrder.merchant}</strong>
            </div>
            {(paypalOrder.items?.length ?? activeReview?.cart.items.length ?? 0) > 1 && (
              <div style={{ borderTop: '1px solid #24324d', paddingTop: '10px', marginBottom: '10px' }}>
                {(paypalOrder.items || []).map((li) => (
                  <div
                    key={li.product_id}
                    style={{
                      display: 'flex',
                      justifyContent: 'space-between',
                      fontSize: '0.9rem',
                      color: '#cbd5e1',
                      marginBottom: '6px',
                    }}
                  >
                    <span>
                      {li.product_title} (${li.unit_price.toFixed(2)} × {li.quantity})
                    </span>
                    <span>${li.line_total.toFixed(2)}</span>
                  </div>
                ))}
              </div>
            )}
            <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'baseline', borderTop: '1px solid #24324d', paddingTop: '12px' }}>
              <span style={{ fontSize: '1.1rem', fontWeight: 800, color: '#cbd5e1' }}>PayPal Order Total</span>
              <span style={{ fontSize: '1.65rem', fontWeight: 900, color: '#38bdf8' }}>
                ${(paypalOrder.amount ?? activeReview?.total_today ?? 0).toFixed(2)}
              </span>
            </div>
            <div style={{ fontSize: '0.82rem', color: '#94a3b8', marginTop: '8px' }}>
              PayPal Sandbox Order ID: <code>{paypalOrder.paypal_order_id}</code>
            </div>
          </div>

          {/* Official PayPal JS SDK Buttons container (rendered when live Sandbox Client ID is configured) */}
          <div ref={paypalButtonsContainerRef} id="paypal-button-container" style={{ marginBottom: '16px' }} />

          <div style={{ display: 'flex', flexDirection: 'column', gap: '14px' }}>
            <button
              type="button"
              disabled={isProcessing}
              onClick={handlePayPalSandboxApprovalAction}
              className="btn-confirm"
              style={{
                backgroundColor: '#fbbf24',
                color: '#0a0f1d',
                padding: '18px 24px',
                borderRadius: '16px',
                fontSize: '1.18rem',
                fontWeight: 900,
                border: 'none',
              }}
              aria-label={`Approve PayPal Sandbox Payment of $${(paypalOrder.amount ?? activeReview?.total_today ?? 0).toFixed(2)}`}
            >
              {isProcessing
                ? 'Processing payment...'
                : paypalOrder.provider === 'mock' || paypalOrder.paypal_order_id?.startsWith('PAYID-SBX-')
                  ? `Approve with PayPal Sandbox ($${(paypalOrder.amount ?? activeReview?.total_today ?? 0).toFixed(2)})`
                  : `Continue to PayPal Sandbox Buyer Login ($${(paypalOrder.amount ?? activeReview?.total_today ?? 0).toFixed(2)})`}
            </button>

            <div style={{ display: 'flex', gap: '12px' }}>
              <button
                type="button"
                disabled={isProcessing}
                onClick={handleCancelFlow}
                className="btn-cancel"
                style={{
                  flex: 1,
                  backgroundColor: '#182235',
                  border: '2px solid #ef4444',
                  color: '#ef4444',
                  padding: '15px',
                  borderRadius: '14px',
                  fontSize: '1.05rem',
                  fontWeight: 800,
                }}
              >
                Cancel
              </button>

              <button
                type="button"
                disabled={isProcessing}
                onClick={handleBackStep}
                className="btn-back"
                style={{
                  flex: 1,
                  backgroundColor: '#182235',
                  border: '2px solid #334155',
                  color: '#cbd5e1',
                  padding: '15px',
                  borderRadius: '14px',
                  fontSize: '1.05rem',
                  fontWeight: 800,
                }}
              >
                BACK
              </button>
            </div>
          </div>
        </section>
      )}

      {/* ACCESSIBLE PAYMENT FAILURE SCREEN */}
      {currentStep === 'payment_failed' && (
        <section
          style={{
            backgroundColor: '#111827',
            border: '3px solid #ef4444',
            borderRadius: '24px',
            padding: '40px 32px',
            maxWidth: '620px',
            margin: '0 auto',
            textAlign: 'center',
          }}
          role="alert"
          aria-live="assertive"
          aria-label="Payment Failed"
        >
          <div
            style={{
              width: '72px',
              height: '72px',
              borderRadius: '50%',
              backgroundColor: 'rgba(239, 68, 68, 0.15)',
              display: 'flex',
              alignItems: 'center',
              justifyContent: 'center',
              margin: '0 auto 20px',
            }}
          >
            <AlertCircle size={44} color="#ef4444" />
          </div>

          <div style={{ fontSize: '0.78rem', fontWeight: 800, color: '#fca5a5', letterSpacing: '0.06em', textTransform: 'uppercase', marginBottom: '8px' }}>
            PAYMENT COULD NOT BE COMPLETED
          </div>

          <p
            style={{
              fontSize: '1.35rem',
              fontWeight: 800,
              color: '#f8fafc',
              lineHeight: 1.45,
              marginBottom: '6px',
              whiteSpace: 'pre-line',
            }}
          >
            {paymentFailureMessage}
          </p>
          <p style={{ fontSize: '0.96rem', color: '#94a3b8', margin: '0 0 20px', fontWeight: 600 }}>
            Nothing was charged.
          </p>

          <div style={{ display: 'flex', justifyContent: 'center', marginBottom: '22px' }}>
            <ContextualVoiceTips commands={['Try again', 'Cancel']} />
          </div>

          <div style={{ display: 'flex', justifyContent: 'center', gap: '16px', flexWrap: 'wrap' }}>
            <button
              type="button"
              onClick={async () => {
                setConfirmationError(null);
                if (!activeReview) {
                  const refreshed = await prepareReview();
                  if (refreshed) {
                    setActiveReview(refreshed);
                    setCurrentStep('confirm');
                    return;
                  }
                  setCurrentStep('search');
                  return;
                }
                setCurrentStep('confirm');
              }}
              className="btn-confirm"
              style={{
                backgroundColor: '#0284c7',
                color: '#ffffff',
                padding: '16px 28px',
                borderRadius: '14px',
                fontSize: '1.1rem',
                fontWeight: 800,
                border: 'none',
              }}
            >
              Try Again
            </button>

            <button
              type="button"
              onClick={handleCancelFlow}
              className="btn-cancel"
              style={{
                backgroundColor: 'transparent',
                border: '2px solid #ef4444',
                color: '#ef4444',
                padding: '16px 28px',
                borderRadius: '14px',
                fontSize: '1.1rem',
                fontWeight: 800,
              }}
            >
              Cancel
            </button>
          </div>
        </section>
      )}

      {/* OUTCOME STEP (CANCELLED OR PAYMENT SUCCESS) */}
      {currentStep === 'outcome' && outcome && (
        <section
          style={{
            backgroundColor: '#111827',
            border: outcome.success ? '3px solid #10b981' : '3px solid #ef4444',
            borderRadius: '24px',
            padding: '40px 32px',
            maxWidth: '620px',
            margin: '0 auto',
            textAlign: 'center',
          }}
          role="status"
          aria-live="polite"
          aria-label="Purchase Outcome"
        >
          <div
            style={{
              width: '72px',
              height: '72px',
              borderRadius: '50%',
              backgroundColor: outcome.success ? 'rgba(16, 185, 129, 0.15)' : 'rgba(239, 68, 68, 0.15)',
              display: 'flex',
              alignItems: 'center',
              justifyContent: 'center',
              margin: '0 auto 20px',
            }}
          >
            {outcome.success ? (
              <CheckCircle2 size={44} color="#10b981" />
            ) : (
              <AlertCircle size={44} color="#ef4444" />
            )}
          </div>

          {outcome.success ? (
            <div style={{ textAlign: 'left', maxWidth: '440px', margin: '0 auto 28px' }}>
              <div style={{ textAlign: 'center', marginBottom: '20px' }}>
                <div style={{ fontSize: '0.78rem', fontWeight: 800, color: '#10b981', letterSpacing: '0.06em', textTransform: 'uppercase', marginBottom: '4px' }}>
                  PAYMENT SUCCESSFUL
                </div>
                <h2 style={{ fontSize: '1.75rem', fontWeight: 900, color: '#f8fafc', margin: '0 0 8px' }}>
                  Receipt Ready
                </h2>
                <p style={{ fontSize: '0.9rem', color: '#cbd5e1', margin: '0 0 10px' }}>
                  Use Speak to ask me to read your receipt, open Orders, or return to Shop.
                </p>
                <span
                  style={{
                    display: 'inline-block',
                    backgroundColor: '#1e293b',
                    border: '1px solid #38bdf8',
                    color: '#38bdf8',
                    fontSize: '0.78rem',
                    fontWeight: 700,
                    padding: '4px 10px',
                    borderRadius: '999px',
                  }}
                >
                  Demo payment — PayPal Sandbox
                </span>
              </div>

              <div
                style={{
                  backgroundColor: '#182235',
                  border: '1px solid #24324d',
                  borderRadius: '16px',
                  padding: '22px 24px',
                }}
              >
                <div style={{ fontSize: '1.3rem', fontWeight: 900, color: '#f8fafc', marginBottom: '16px' }}>
                  {outcome.productTitle}
                </div>

                {outcome.items && outcome.items.length > 0 && (
                  <div style={{ borderTop: '1px solid #24324d', borderBottom: '1px solid #24324d', padding: '12px 0', marginBottom: '14px' }}>
                    {outcome.items.map((li) => (
                      <div
                        key={li.product_id}
                        style={{
                          display: 'flex',
                          justifyContent: 'space-between',
                          alignItems: 'baseline',
                          gap: '12px',
                          marginBottom: '6px',
                          fontSize: '0.98rem',
                          color: '#cbd5e1',
                        }}
                      >
                        <span>
                          {li.product_title} — ${li.unit_price.toFixed(2)} × {li.quantity}
                        </span>
                        <span style={{ fontWeight: 700, color: '#f8fafc' }}>${li.line_total.toFixed(2)}</span>
                      </div>
                    ))}
                    {outcome.itemSubtotal !== undefined && outcome.shipping !== undefined && outcome.tax !== undefined && (
                      <div style={{ fontSize: '0.86rem', color: '#94a3b8', marginTop: '6px' }}>
                        Subtotal ${outcome.itemSubtotal.toFixed(2)} • Shipping ${outcome.shipping.toFixed(2)} • Tax ${outcome.tax.toFixed(2)}
                      </div>
                    )}
                  </div>
                )}

                <div style={{ marginBottom: '12px' }}>
                  <div style={{ fontSize: '0.88rem', color: '#94a3b8' }}>Paid:</div>
                  <div style={{ fontSize: '1.35rem', fontWeight: 900, color: '#38bdf8' }}>
                    ${(outcome.amountPaid ?? 0).toFixed(2)}
                  </div>
                </div>

                <div style={{ marginBottom: '12px' }}>
                  <div style={{ fontSize: '0.88rem', color: '#94a3b8' }}>Merchant:</div>
                  <div style={{ fontSize: '1.08rem', fontWeight: 700, color: '#f8fafc' }}>
                    {outcome.merchant}
                  </div>
                </div>

                <div style={{ marginBottom: '14px' }}>
                  <div style={{ fontSize: '0.88rem', color: '#94a3b8' }}>PayPal Sandbox Order ID:</div>
                  <div style={{ fontSize: '1rem', fontWeight: 700, color: '#cbd5e1' }}>
                    {outcome.paypalOrderId}
                  </div>
                </div>

                {outcome.paypalCaptureId && (
                  <div style={{ marginBottom: '14px' }}>
                    <div style={{ fontSize: '0.88rem', color: '#94a3b8' }}>PayPal Capture ID:</div>
                    <div style={{ fontSize: '1rem', fontWeight: 700, color: '#cbd5e1' }}>
                      {outcome.paypalCaptureId}
                    </div>
                  </div>
                )}

                <div style={{ borderTop: '1px solid #24324d', paddingTop: '12px', fontSize: '0.95rem', fontWeight: 700, color: '#10b981' }}>
                  {outcome.isSubscription
                    ? 'Recurring payment demo scenario (PayPal Sandbox).'
                    : 'This was a one-time payment.'}
                </div>
              </div>

              <div style={{ marginTop: '18px' }}>
                <ContextualVoiceTips
                  commands={['Read my receipt', 'Go to my orders', 'Go back to shop']}
                />
              </div>
            </div>
          ) : (
            <p
              style={{
                fontSize: '1.5rem',
                fontWeight: 800,
                color: '#f8fafc',
                lineHeight: 1.5,
                marginBottom: '28px',
                whiteSpace: 'pre-line',
              }}
            >
              {outcome.message}
            </p>
          )}

          <button
            type="button"
            onClick={() => {
              setCurrentStep('search');
              setOutcome(null);
              setPaypalOrder(null);
            }}
            className="btn-confirm"
            style={{
              backgroundColor: '#0284c7',
              color: '#ffffff',
              padding: '16px 32px',
              borderRadius: '14px',
              fontSize: '1.1rem',
              fontWeight: 800,
              border: 'none',
            }}
          >
            Done
          </button>
        </section>
      )}

      {/* SUBSCRIPTION STEP 1: ISOLATED DEMO SUBSCRIPTION CATALOG RESULTS */}
      {currentStep === 'subscription_results' && (
        <section
          aria-label="Demo Subscription Catalog Results"
          data-testid="subscription-results-section"
          style={{ display: 'flex', flexDirection: 'column', gap: '20px' }}
        >
          <div
            style={{
              backgroundColor: '#1e1b4b',
              border: '2px solid #f59e0b',
              borderRadius: '18px',
              padding: '18px 22px',
              display: 'flex',
              flexWrap: 'wrap',
              justifyContent: 'space-between',
              alignItems: 'center',
              gap: '12px',
            }}
          >
            <div>
              <span
                style={{
                  display: 'inline-flex',
                  alignItems: 'center',
                  gap: '6px',
                  fontSize: '0.78rem',
                  fontWeight: 800,
                  textTransform: 'uppercase',
                  letterSpacing: '0.05em',
                  color: '#fcd34d',
                }}
              >
                <Repeat size={15} aria-hidden="true" />
                SUBSCRIPTION COMMERCE • DEMO CATALOG (ISOLATED FROM CHANNEL3)
              </span>
              <h3 style={{ margin: '4px 0 0', fontSize: '1.35rem', fontWeight: 800, color: '#f8fafc' }}>
                Recurring Subscription Plans
              </h3>
              <p style={{ margin: '4px 0 0', fontSize: '0.92rem', color: '#cbd5e1' }}>
                These are simulated recurring plans backed by real PayPal Sandbox Subscriptions API approval.
              </p>
            </div>
            <button
              type="button"
              onClick={() => setCurrentStep('search')}
              style={{
                padding: '10px 16px',
                borderRadius: '10px',
                border: '1px solid #475569',
                backgroundColor: '#0f172a',
                color: '#e2e8f0',
                fontWeight: 700,
                fontSize: '0.88rem',
              }}
            >
              Back to Physical Products
            </button>
          </div>

          <ContextualVoiceTips
            commands={[
              'Is this a subscription?',
              'How much will I pay every month?',
              'Review this subscription',
              'Subscribe',
            ]}
          />

          <div
            style={{
              display: 'grid',
              gridTemplateColumns: 'repeat(auto-fill, minmax(310px, 1fr))',
              gap: '18px',
            }}
          >
            {subscriptionOffers.map((offer, idx) => (
              <SubscriptionCard
                key={offer.id}
                offer={offer}
                index={idx}
                isSelected={selectedSubscription?.id === offer.id}
                onSelect={(o) => {
                  setSelectedSubscription(o);
                  const msg = `Selected ${o.name} ($${o.recurring_amount.toFixed(2)} ${o.billing_frequency}).`;
                  setAiMessage(msg);
                  announce(msg);
                }}
                onReview={(o) => void handleOpenSubscriptionReview(o)}
              />
            ))}
          </div>
        </section>
      )}

      {/* SUBSCRIPTION STEP 2: RECURRING COMMITMENT REVIEW + DETERMINISTIC CONFIRMATION */}
      {(currentStep === 'subscription_review' || currentStep === 'subscription_confirm') && subscriptionReview && (
        <section
          aria-label="Subscription Review and Explicit Recurring Confirmation"
          data-testid="subscription-review-section"
          style={{
            backgroundColor: '#0f172a',
            border: '2px solid #f59e0b',
            borderRadius: '22px',
            padding: '26px',
            maxWidth: '780px',
            margin: '0 auto',
            display: 'flex',
            flexDirection: 'column',
            gap: '18px',
          }}
        >
          <div style={{ display: 'flex', flexWrap: 'wrap', justifyContent: 'space-between', alignItems: 'center', gap: '10px' }}>
            <span
              style={{
                display: 'inline-flex',
                alignItems: 'center',
                gap: '6px',
                fontSize: '0.82rem',
                fontWeight: 800,
                letterSpacing: '0.05em',
                color: '#fcd34d',
                backgroundColor: '#451a03',
                padding: '5px 12px',
                borderRadius: '999px',
                border: '1px solid #f59e0b',
              }}
            >
              <ShieldAlert size={16} aria-hidden="true" />
              SUBSCRIPTION REVIEW • RECURRING PAYMENT
            </span>
            <span style={{ fontSize: '0.82rem', color: '#94a3b8', fontWeight: 700 }}>
              No subscription has been created yet.
            </span>
          </div>

          <div>
            <h3 style={{ margin: 0, fontSize: '1.5rem', fontWeight: 800, color: '#f8fafc' }}>
              {subscriptionReview.offer.name}
            </h3>
            <p style={{ margin: '4px 0 0', color: '#cbd5e1', fontSize: '0.95rem' }}>
              Provider: {subscriptionReview.offer.provider} ({subscriptionReview.offer.source})
            </p>
          </div>

          <div
            style={{
              backgroundColor: '#1e293b',
              borderRadius: '16px',
              padding: '18px',
              display: 'grid',
              gridTemplateColumns: 'repeat(auto-fit, minmax(170px, 1fr))',
              gap: '14px',
            }}
          >
            <div>
              <div style={{ fontSize: '0.78rem', color: '#94a3b8', fontWeight: 700 }}>DUE TODAY</div>
              <div style={{ fontSize: '1.45rem', fontWeight: 800, color: '#f8fafc' }}>
                ${subscriptionReview.due_today.toFixed(2)}
              </div>
            </div>
            <div>
              <div style={{ fontSize: '0.78rem', color: '#fcd34d', fontWeight: 700 }}>RECURRING CHARGE</div>
              <div style={{ fontSize: '1.45rem', fontWeight: 800, color: '#fcd34d' }}>
                ${subscriptionReview.recurring_amount.toFixed(2)} / {subscriptionReview.billing_frequency}
              </div>
            </div>
            <div>
              <div style={{ fontSize: '0.78rem', color: '#94a3b8', fontWeight: 700 }}>FREE TRIAL</div>
              <div style={{ fontSize: '1.05rem', fontWeight: 700, color: '#f8fafc', marginTop: '4px' }}>
                {subscriptionReview.offer.trial_period || 'None'}
              </div>
            </div>
          </div>

          <div style={{ fontSize: '0.92rem', color: '#cbd5e1', lineHeight: 1.55 }}>
            <div><strong>This is a recurring payment.</strong> {subscriptionReview.offer.renewal_behavior}</div>
            <div style={{ marginTop: '4px' }}><strong>Cancellation:</strong> {subscriptionReview.offer.cancellation_information}</div>
          </div>

          <div
            style={{
              backgroundColor: '#111827',
              border: '1px solid #334155',
              borderRadius: '14px',
              padding: '16px',
            }}
          >
            <p style={{ margin: '0 0 8px', fontSize: '0.92rem', fontWeight: 700, color: '#f8fafc' }}>
              Explicit Recurring Confirmation Required (Amount + Billing Frequency):
            </p>
            <p style={{ margin: '0 0 12px', fontSize: '0.88rem', color: '#fcd34d' }}>
              Say or type: <code>{subscriptionReview.expected_phrase}</code>
            </p>

            {subscriptionConfirmError && (
              <div
                role="alert"
                data-testid="subscription-confirm-error"
                style={{
                  backgroundColor: '#450a0a',
                  border: '1px solid #ef4444',
                  color: '#fecaca',
                  borderRadius: '10px',
                  padding: '10px 14px',
                  marginBottom: '12px',
                  fontSize: '0.9rem',
                  fontWeight: 600,
                }}
              >
                {subscriptionConfirmError}
              </div>
            )}

            <form
              onSubmit={(e) => {
                e.preventDefault();
                void handleSubmitSubscriptionConfirmation(subscriptionConfirmPhrase, 'VOICE');
              }}
              style={{ display: 'flex', flexWrap: 'wrap', gap: '10px' }}
            >
              <input
                type="text"
                value={subscriptionConfirmPhrase}
                onChange={(e) => setSubscriptionConfirmPhrase(e.target.value)}
                placeholder={subscriptionReview.expected_phrase}
                aria-label="Confirm recurring subscription amount and frequency"
                data-testid="subscription-confirm-input"
                style={{
                  flex: 1,
                  minWidth: '240px',
                  padding: '12px 14px',
                  borderRadius: '10px',
                  border: '1px solid #475569',
                  backgroundColor: '#020617',
                  color: '#f8fafc',
                  fontSize: '0.95rem',
                }}
              />
              <button
                type="submit"
                disabled={isProcessing}
                data-testid="subscription-confirm-submit"
                style={{
                  padding: '12px 20px',
                  borderRadius: '10px',
                  border: 'none',
                  backgroundColor: '#f59e0b',
                  color: '#020617',
                  fontWeight: 800,
                  fontSize: '0.95rem',
                  cursor: 'pointer',
                }}
              >
                {isProcessing ? 'Verifying...' : 'Confirm & Continue to PayPal'}
              </button>
            </form>
          </div>

          <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', gap: '12px' }}>
            <button
              type="button"
              onClick={() => setCurrentStep('subscription_results')}
              style={{
                padding: '10px 16px',
                borderRadius: '10px',
                border: '1px solid #475569',
                backgroundColor: '#1e293b',
                color: '#e2e8f0',
                fontWeight: 700,
              }}
            >
              Back to Plans
            </button>
            <button
              type="button"
              onClick={() => {
                const msg = 'Subscription cancelled. No new subscription was created.';
                setSubscriptionOutcome({ success: false, message: msg });
                setCurrentStep('subscription_outcome');
                setAiMessage(msg);
                announce(msg);
              }}
              style={{
                padding: '10px 16px',
                borderRadius: '10px',
                border: '1px solid #ef4444',
                backgroundColor: 'transparent',
                color: '#fca5a5',
                fontWeight: 700,
              }}
            >
              Cancel Subscription Setup
            </button>
          </div>
        </section>
      )}

      {/* SUBSCRIPTION STEP 3: PAYPAL SANDBOX SUBSCRIPTION APPROVAL */}
      {currentStep === 'subscription_paypal' && paypalSubscription && (
        <section
          aria-label="PayPal Sandbox Subscription Approval"
          data-testid="subscription-paypal-section"
          style={{
            backgroundColor: '#0f172a',
            border: '2px solid #38bdf8',
            borderRadius: '22px',
            padding: '28px',
            maxWidth: '720px',
            margin: '0 auto',
            display: 'flex',
            flexDirection: 'column',
            gap: '16px',
          }}
        >
          <span
            style={{
              alignSelf: 'flex-start',
              fontSize: '0.78rem',
              fontWeight: 800,
              letterSpacing: '0.05em',
              color: '#38bdf8',
              backgroundColor: '#0c4a6e',
              padding: '4px 12px',
              borderRadius: '999px',
            }}
          >
            PAYPAL SANDBOX SUBSCRIPTIONS API v1
          </span>
          <h3 style={{ margin: 0, fontSize: '1.45rem', fontWeight: 800, color: '#f8fafc' }}>
            Approve Recurring Subscription in PayPal Sandbox
          </h3>
          <p style={{ margin: 0, color: '#cbd5e1', fontSize: '0.95rem' }}>
            Plan: <strong>{paypalSubscription.plan_name}</strong> •{' '}
            <strong>${paypalSubscription.recurring_amount.toFixed(2)} / {paypalSubscription.billing_frequency}</strong>
            <br />
            PayPal Subscription ID: <code>{paypalSubscription.paypal_subscription_id}</code> ({paypalSubscription.status})
          </p>

          <div style={{ display: 'flex', flexWrap: 'wrap', gap: '12px', marginTop: '6px' }}>
            {paypalSubscription.approval_url && (
              <a
                href={paypalSubscription.approval_url}
                data-testid="paypal-subscription-approve-link"
                style={{
                  display: 'inline-flex',
                  alignItems: 'center',
                  gap: '8px',
                  padding: '14px 22px',
                  borderRadius: '12px',
                  backgroundColor: '#0070ba',
                  color: '#ffffff',
                  fontWeight: 800,
                  textDecoration: 'none',
                }}
              >
                Approve in PayPal Sandbox
                <ExternalLink size={16} aria-hidden="true" />
              </a>
            )}
            <button
              type="button"
              onClick={async () => {
                const updated = await api.getPayPalSubscriptionStatus(paypalSubscription.paypal_subscription_id);
                setPaypalSubscription(updated);
                if (updated.status === 'ACTIVE') {
                  const msg = `Subscription active: ${updated.plan_name}.`;
                  setSubscriptionOutcome({ success: true, message: msg, record: updated });
                  setCurrentStep('subscription_outcome');
                  announce(msg);
                  onOrderCompleted?.();
                } else {
                  announce(`Current PayPal subscription status: ${updated.status}`);
                }
              }}
              style={{
                padding: '14px 18px',
                borderRadius: '12px',
                border: '1px solid #38bdf8',
                backgroundColor: '#1e293b',
                color: '#e0f2fe',
                fontWeight: 700,
              }}
            >
              Check Subscription Status
            </button>
            <button
              type="button"
              onClick={() => {
                const msg = 'Subscription cancelled. No new subscription was created.';
                setSubscriptionOutcome({ success: false, message: msg });
                setCurrentStep('subscription_outcome');
                announce(msg);
              }}
              style={{
                padding: '14px 18px',
                borderRadius: '12px',
                border: '1px solid #ef4444',
                backgroundColor: 'transparent',
                color: '#fca5a5',
                fontWeight: 700,
              }}
            >
              Cancel
            </button>
          </div>
        </section>
      )}

      {/* SUBSCRIPTION STEP 4: OUTCOME (NEVER FABRICATES CAPTURE ID) */}
      {currentStep === 'subscription_outcome' && subscriptionOutcome && (
        <section
          aria-label="Subscription Outcome"
          data-testid="subscription-outcome-section"
          style={{
            backgroundColor: '#0f172a',
            border: subscriptionOutcome.success ? '2px solid #10b981' : '2px solid #f59e0b',
            borderRadius: '22px',
            padding: '28px',
            maxWidth: '720px',
            margin: '0 auto',
            display: 'flex',
            flexDirection: 'column',
            gap: '14px',
          }}
        >
          <span
            style={{
              alignSelf: 'flex-start',
              fontSize: '0.82rem',
              fontWeight: 800,
              letterSpacing: '0.05em',
              padding: '4px 12px',
              borderRadius: '999px',
              backgroundColor: subscriptionOutcome.success ? '#064e3b' : '#451a03',
              color: subscriptionOutcome.success ? '#6ee7b7' : '#fcd34d',
            }}
          >
            {subscriptionOutcome.success ? 'SUBSCRIPTION ACTIVE' : 'SUBSCRIPTION CANCELLED'}
          </span>

          <h3 style={{ margin: 0, fontSize: '1.4rem', fontWeight: 800, color: '#f8fafc' }}>
            {subscriptionOutcome.message}
          </h3>

          {subscriptionOutcome.record && (
            <dl
              style={{
                backgroundColor: '#111827',
                borderRadius: '14px',
                padding: '16px',
                margin: 0,
                display: 'grid',
                gridTemplateColumns: 'repeat(auto-fit, minmax(200px, 1fr))',
                gap: '12px',
                fontSize: '0.9rem',
              }}
            >
              <div>
                <dt style={{ color: '#94a3b8' }}>Provider</dt>
                <dd style={{ margin: 0, fontWeight: 700, color: '#f8fafc' }}>{subscriptionOutcome.record.provider}</dd>
              </div>
              <div>
                <dt style={{ color: '#94a3b8' }}>Plan</dt>
                <dd style={{ margin: 0, fontWeight: 700, color: '#f8fafc' }}>{subscriptionOutcome.record.plan_name}</dd>
              </div>
              <div>
                <dt style={{ color: '#94a3b8' }}>Recurring Amount</dt>
                <dd style={{ margin: 0, fontWeight: 700, color: '#fcd34d' }}>
                  ${subscriptionOutcome.record.recurring_amount.toFixed(2)} / {subscriptionOutcome.record.billing_frequency}
                </dd>
              </div>
              <div>
                <dt style={{ color: '#94a3b8' }}>PayPal Subscription ID</dt>
                <dd style={{ margin: 0, fontWeight: 700, color: '#38bdf8' }}>
                  {subscriptionOutcome.record.paypal_subscription_id}
                </dd>
              </div>
              <div>
                <dt style={{ color: '#94a3b8' }}>Status</dt>
                <dd style={{ margin: 0, fontWeight: 700, color: '#6ee7b7' }}>{subscriptionOutcome.record.status}</dd>
              </div>
            </dl>
          )}

          <div style={{ display: 'flex', flexWrap: 'wrap', gap: '12px', marginTop: '6px' }}>
            <button
              type="button"
              onClick={() => {
                setCurrentStep('search');
                setSubscriptionOutcome(null);
              }}
              style={{
                padding: '12px 22px',
                borderRadius: '12px',
                border: 'none',
                backgroundColor: '#0284c7',
                color: '#ffffff',
                fontWeight: 800,
              }}
            >
              Done
            </button>
            <button
              type="button"
              onClick={() => onNavigateOrders?.()}
              style={{
                padding: '12px 22px',
                borderRadius: '12px',
                border: '1px solid #475569',
                backgroundColor: '#1e293b',
                color: '#e2e8f0',
                fontWeight: 700,
              }}
            >
              View Orders &amp; Subscriptions
            </button>
          </div>
        </section>
      )}

    </div>
  );
};
