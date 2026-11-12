import {
  Product,
  Cart,
  PurchaseReview,
  PurchaseResponse,
  PayPalOrderCreationResponse,
  PayPalCaptureResponse,
  AccessibilityPreferences,
  AccessibilityMode,
  TimelineEvent,
  OrderRecord,
  AccessibilityActivitySummary,
  DemoScenario,
  SavedItem,
  SavedSearch,
  SearchHistoryEntry,
  ActiveSearchSnapshot,
  AppViewName
} from '../types';

export type InteractionInputMode = 'voice' | 'text' | 'command_chip' | 'keyboard' | 'switch';

export interface AiIntentContext {
  inputMode?: InteractionInputMode;
  activeSearchId?: string | null;
  searchGeneration?: number;
  visibleProductIds?: string[];
  rawTranscript?: string;
  currentView?: AppViewName;
  visibleSavedItemIds?: string[];
  visibleSavedSearchIds?: string[];
  visibleOrderIds?: string[];
  selectedOrderId?: string | null;
  selectedSavedItemId?: string | null;
  visibleCartProductIds?: string[];
}

function resolveApiBaseUrl(): string {
  const envObj = (import.meta as any).env || {};
  const configured = (envObj.VITE_API_BASE_URL || envObj.VITE_API_URL || '').trim().replace(/\/+$/, '');
  if (configured) {
    return configured.endsWith('/api') ? configured : `${configured}/api`;
  }
  if (
    typeof window !== 'undefined' &&
    (window.location.hostname === 'localhost' || window.location.hostname === '127.0.0.1') &&
    window.location.port === '5173'
  ) {
    return 'http://127.0.0.1:8008/api';
  }
  return '/api';
}

const BASE_URL = resolveApiBaseUrl();

export const SAFE_SEARCH_ERROR_MESSAGE = "I'm having trouble searching right now.\nPlease try again.";
export const SAFE_PAYMENT_ERROR_MESSAGE = "Your payment could not be completed.\n\nNothing was charged.";
export const SAFE_BACKEND_UNAVAILABLE_MESSAGE = "AccessPay is temporarily unavailable.\nPlease try again.";

export function sanitizeUserFacingError(rawMessage?: string): string {
  if (!rawMessage) return SAFE_SEARCH_ERROR_MESSAGE;
  const technicalPattern = /(http\s*\d{3}|bad gateway|internal server error|unprocessable_entity|instrument_declined|failed to fetch|networkerror|syntaxerror|json|traceback|exception|eperm|econnrefused|timeout|aborted)/i;
  if (technicalPattern.test(rawMessage)) {
    return SAFE_SEARCH_ERROR_MESSAGE;
  }
  return rawMessage;
}

export function sanitizePaymentError(rawMessage?: string): string {
  if (!rawMessage) return SAFE_PAYMENT_ERROR_MESSAGE;
  const technicalPattern = /(http\s*\d{3}|bad gateway|internal server error|unprocessable_entity|instrument_declined|paypal_|failed to fetch|networkerror|syntaxerror|json|traceback|exception|eperm|econnrefused|timeout|aborted)/i;
  if (technicalPattern.test(rawMessage)) {
    return SAFE_PAYMENT_ERROR_MESSAGE;
  }
  return rawMessage;
}

async function fetchJson<T>(url: string, options?: RequestInit): Promise<T> {
  let res: Response;
  try {
    res = await fetch(`${BASE_URL}${url}`, {
      headers: {
        'Content-Type': 'application/json',
        ...options?.headers,
      },
      ...options,
    });
  } catch (networkErr: any) {
    console.error(`[AccessPay Dev Log] Network error on ${url}:`, networkErr);
    throw new Error(SAFE_SEARCH_ERROR_MESSAGE);
  }

  if (!res.ok) {
    let rawDetail = `HTTP ${res.status}: ${res.statusText}`;
    try {
      const errData = await res.json();
      rawDetail = errData.detail || errData.message || rawDetail;
    } catch (parseErr) {
      console.error(`[AccessPay Dev Log] Non-JSON error response on ${url} (${res.status}):`, parseErr);
    }
    console.error(`[AccessPay Dev Log] API error on ${url}:`, rawDetail);
    throw new Error(sanitizeUserFacingError(rawDetail));
  }

  try {
    return await res.json();
  } catch (jsonErr: any) {
    console.error(`[AccessPay Dev Log] Invalid JSON response on ${url}:`, jsonErr);
    throw new Error(SAFE_SEARCH_ERROR_MESSAGE);
  }
}

export const api = {
  // Products
  async listProducts(): Promise<Product[]> {
    return fetchJson<Product[]>('/products');
  },

  async getSearchSuggestions(query: string, limit = 6): Promise<{ query: string; suggestions: string[] }> {
    return fetchJson(`/products/suggestions?q=${encodeURIComponent(query)}&limit=${limit}`);
  },

  async searchProducts(query: string, budgetLimit?: number): Promise<{
    count: number;
    products: Product[];
    channel3_integrated: boolean;
    source: string;
    product_mode?: string;
    search_id?: string;
    search_generation?: number;
    has_more?: boolean;
    total_candidates?: number;
    displayed_product_ids?: string[];
    error?: boolean;
    error_message?: string;
  }> {
    return fetchJson('/products/search', {
      method: 'POST',
      body: JSON.stringify({ query, budget_limit: budgetLimit }),
    });
  },

  async getActiveSearch(): Promise<ActiveSearchSnapshot> {
    return fetchJson<ActiveSearchSnapshot>('/products/active-search');
  },

  async showMoreProducts(): Promise<any> {
    return fetchJson('/products/show-more', {
      method: 'POST',
    });
  },

  async setProductMode(provider: 'channel3' | 'mock' | 'auto'): Promise<any> {
    return fetchJson('/products/mode', {
      method: 'POST',
      body: JSON.stringify({ provider }),
    });
  },

  async compareProducts(productIds: string[]): Promise<any> {
    return fetchJson('/products/compare', {
      method: 'POST',
      body: JSON.stringify({ product_ids: productIds }),
    });
  },

  // Cart
  async getCart(): Promise<Cart> {
    return fetchJson<Cart>('/cart');
  },

  async addToCart(productId: string, quantity = 1, variant?: Record<string, string>): Promise<Cart> {
    return fetchJson<Cart>('/cart/items', {
      method: 'POST',
      body: JSON.stringify({ product_id: productId, quantity, selected_variant: variant }),
    });
  },

  async updateCartItem(productId: string, quantity: number): Promise<Cart> {
    return fetchJson<Cart>(`/cart/items/${productId}`, {
      method: 'PUT',
      body: JSON.stringify({ quantity }),
    });
  },

  async removeFromCart(productIdOrTitle: string): Promise<Cart> {
    return fetchJson<Cart>(`/cart/items/${encodeURIComponent(productIdOrTitle)}`, {
      method: 'DELETE',
    });
  },

  async clearCart(): Promise<Cart> {
    return fetchJson<Cart>('/cart', {
      method: 'DELETE',
    });
  },

  // Purchase & Confirmation State Machine
  async preparePurchaseReview(): Promise<PurchaseReview> {
    return fetchJson<PurchaseReview>('/purchase/review', {
      method: 'POST',
    });
  },

  async confirmPurchase(params: {
    reviewToken: string;
    spokenPhrase?: string;
    confirmationMethod?: string;
    subscriptionAcknowledged?: boolean;
    trialAcknowledged?: boolean;
    highValueStep?: number;
    authorizeOnly?: boolean;
  }): Promise<PurchaseResponse> {
    return fetchJson<PurchaseResponse>('/purchase/confirm', {
      method: 'POST',
      body: JSON.stringify({
        review_token: params.reviewToken,
        spoken_phrase: params.spokenPhrase,
        confirmation_method: params.confirmationMethod || 'VOICE',
        subscription_acknowledged: params.subscriptionAcknowledged,
        trial_acknowledged: params.trialAcknowledged,
        high_value_step: params.highValueStep,
        authorize_only: params.authorizeOnly ?? false,
      }),
    });
  },

  async acknowledgeSubscription(acknowledged = true): Promise<{ status: string; subscription_acknowledged: boolean }> {
    return fetchJson('/purchase/acknowledge-subscription', {
      method: 'POST',
      body: JSON.stringify({ acknowledged }),
    });
  },

  // PayPal Sandbox Integration (Phase 4)
  async getPayPalConfig(): Promise<{
    paypal_client_id: string;
    environment: string;
    provider: string;
    is_configured: boolean;
    sandbox_label: string;
    agent_ready_note: string;
  }> {
    return fetchJson('/payments/config');
  },

  async createPayPalOrder(
    reviewToken?: string,
    urls?: { returnUrl?: string; cancelUrl?: string }
  ): Promise<PayPalOrderCreationResponse> {
    return fetchJson<PayPalOrderCreationResponse>('/payments/paypal/create-order', {
      method: 'POST',
      body: JSON.stringify({
        review_token: reviewToken,
        return_url: urls?.returnUrl,
        cancel_url: urls?.cancelUrl,
      }),
    });
  },

  async getPayPalOrderStatus(orderId: string): Promise<{
    success: boolean;
    paypal_order_id: string;
    status: string;
    paypal_capture_id?: string | null;
    amount?: number | null;
    currency?: string;
    provider?: string;
    environment?: string;
  }> {
    return fetchJson(`/payments/paypal/order/${encodeURIComponent(orderId)}`);
  },

  async capturePayPalOrder(
    orderId: string,
    params?: { reviewToken?: string; interactionMode?: string; confirmationMethod?: string }
  ): Promise<PayPalCaptureResponse> {
    return fetchJson<PayPalCaptureResponse>(`/payments/paypal/capture-order/${encodeURIComponent(orderId)}`, {
      method: 'POST',
      body: JSON.stringify({
        review_token: params?.reviewToken,
        interaction_mode: params?.interactionMode,
        confirmation_method: params?.confirmationMethod,
      }),
    });
  },

  async cancelPurchase(): Promise<PurchaseResponse> {
    return fetchJson<PurchaseResponse>('/purchase/cancel', {
      method: 'POST',
    });
  },

  async simulatePriceChange(newPrice = 62.99): Promise<PurchaseReview> {
    return fetchJson<PurchaseReview>('/purchase/simulate-price-change', {
      method: 'POST',
      body: JSON.stringify({ new_price: newPrice }),
    });
  },

  // AI Agentic Commerce
  async sendAiIntent(message: string, context?: AiIntentContext): Promise<any> {
    return fetchJson('/ai/intent', {
      method: 'POST',
      body: JSON.stringify({
        message,
        input_mode: context?.inputMode || 'text',
        active_search_id: context?.activeSearchId ?? null,
        search_generation: context?.searchGeneration ?? null,
        visible_product_ids: context?.visibleProductIds ?? null,
        raw_transcript: context?.rawTranscript ?? null,
        current_view: context?.currentView ?? null,
        visible_saved_item_ids: context?.visibleSavedItemIds ?? null,
        visible_saved_search_ids: context?.visibleSavedSearchIds ?? null,
        visible_order_ids: context?.visibleOrderIds ?? null,
        selected_order_id: context?.selectedOrderId ?? null,
        selected_saved_item_id: context?.selectedSavedItemId ?? null,
        visible_cart_product_ids: context?.visibleCartProductIds ?? null,
      }),
    });
  },

  async getSuggestedCommands(): Promise<{ commands: string[] }> {
    return fetchJson('/ai/commands');
  },

  async getAiStatus(): Promise<{ is_llm_configured: boolean; active_provider: string; fallback_available: boolean; session_turns: number }> {
    return fetchJson('/ai/status');
  },

  // Accessibility
  async getPreferences(): Promise<AccessibilityPreferences> {
    return fetchJson<AccessibilityPreferences>('/accessibility/preferences');
  },

  async updatePreferences(updates: Partial<AccessibilityPreferences>): Promise<AccessibilityPreferences> {
    return fetchJson<AccessibilityPreferences>('/accessibility/preferences', {
      method: 'PUT',
      body: JSON.stringify(updates),
    });
  },

  async switchMode(mode: AccessibilityMode): Promise<AccessibilityPreferences> {
    return fetchJson<AccessibilityPreferences>('/accessibility/mode', {
      method: 'POST',
      body: JSON.stringify({ mode }),
    });
  },

  async resetPreferences(): Promise<AccessibilityPreferences> {
    return fetchJson<AccessibilityPreferences>('/accessibility/reset', {
      method: 'POST',
    });
  },

  // Timeline (Bryntum)
  async getTimeline(): Promise<TimelineEvent[]> {
    return fetchJson<TimelineEvent[]>('/timeline');
  },

  async queryTimeline(query: string): Promise<{ query: string; message: string; highlighted_count: number; events: TimelineEvent[] }> {
    return fetchJson('/timeline/query', {
      method: 'POST',
      body: JSON.stringify({ query }),
    });
  },

  // Analytics & AG Grid
  async getActivitySummary(): Promise<AccessibilityActivitySummary> {
    return fetchJson<AccessibilityActivitySummary>('/analytics/summary');
  },

  async getOrders(): Promise<OrderRecord[]> {
    return fetchJson<OrderRecord[]>('/orders');
  },

  async getOrderById(orderId: string): Promise<OrderRecord> {
    return fetchJson<OrderRecord>(`/orders/${encodeURIComponent(orderId)}`);
  },

  async reorderOrder(orderId: string): Promise<{
    success: boolean;
    order_id: string;
    cart: Cart;
    review: PurchaseReview;
    price_changes: Array<Record<string, any>>;
    unavailable_items: string[];
    message: string;
  }> {
    return fetchJson(`/orders/${encodeURIComponent(orderId)}/reorder`, {
      method: 'POST',
    });
  },

  async reorderLastOrder(): Promise<{
    success: boolean;
    order_id: string;
    cart: Cart;
    review: PurchaseReview;
    price_changes: Array<Record<string, any>>;
    unavailable_items: string[];
    message: string;
  }> {
    return fetchJson('/orders/reorder-last', {
      method: 'POST',
    });
  },

  // Saved Items, Saved Searches & Search History
  async getSavedItems(): Promise<SavedItem[]> {
    return fetchJson<SavedItem[]>('/saved/items');
  },

  async saveItem(productId: string, productSnapshot?: Product): Promise<SavedItem> {
    return fetchJson<SavedItem>('/saved/items', {
      method: 'POST',
      body: JSON.stringify({ product_id: productId, product_snapshot: productSnapshot }),
    });
  },

  async removeSavedItem(savedItemId: string): Promise<{ success: boolean; removed_id: string }> {
    return fetchJson(`/saved/items/${encodeURIComponent(savedItemId)}`, {
      method: 'DELETE',
    });
  },

  async addSavedItemToCart(savedItemId: string): Promise<{
    success: boolean;
    cart: Cart;
    product: Product;
    saved_item_id: string;
    price_changed: boolean;
    price_at_save: number;
    current_price: number;
    message: string;
  }> {
    return fetchJson(`/saved/items/${encodeURIComponent(savedItemId)}/add-to-cart`, {
      method: 'POST',
    });
  },

  async getSavedSearches(): Promise<SavedSearch[]> {
    return fetchJson<SavedSearch[]>('/saved/searches');
  },

  async saveCurrentSearch(payload?: {
    original_query?: string;
    display_query?: string;
    filters?: Record<string, any>;
    sort?: string | null;
    reference_product_ids?: string[];
  }): Promise<SavedSearch> {
    return fetchJson<SavedSearch>('/saved/searches', {
      method: 'POST',
      body: JSON.stringify(payload || {}),
    });
  },

  async deleteSavedSearch(savedSearchId: string): Promise<{ success: boolean; removed_id: string }> {
    return fetchJson(`/saved/searches/${encodeURIComponent(savedSearchId)}`, {
      method: 'DELETE',
    });
  },

  async runSavedSearch(savedSearchId: string): Promise<any> {
    return fetchJson(`/saved/searches/${encodeURIComponent(savedSearchId)}/run`, {
      method: 'POST',
    });
  },

  async getSearchHistory(limit = 20): Promise<SearchHistoryEntry[]> {
    return fetchJson<SearchHistoryEntry[]>(`/saved/history?limit=${limit}`);
  },

  async runSearchHistory(historyId: string): Promise<any> {
    return fetchJson(`/saved/history/${encodeURIComponent(historyId)}/run`, {
      method: 'POST',
    });
  },

  async saveRecentSearch(historyId: string): Promise<SavedSearch> {
    return fetchJson<SavedSearch>(`/saved/history/${encodeURIComponent(historyId)}/save`, {
      method: 'POST',
    });
  },

  async clearSearchHistory(): Promise<{ success: boolean }> {
    return fetchJson('/saved/history', {
      method: 'DELETE',
    });
  },

  async queryGrid(query: string): Promise<{ query: string; explanation: string; count: number; rows: OrderRecord[] }> {
    return fetchJson('/analytics/grid-query', {
      method: 'POST',
      body: JSON.stringify({ query }),
    });
  },

  async trackOrder(query?: string): Promise<any> {
    return fetchJson(`/orders/track${query ? `?query=${encodeURIComponent(query)}` : ''}`);
  },

  async returnAssistant(productName = 'headphones'): Promise<any> {
    return fetchJson('/orders/return', {
      method: 'POST',
      body: JSON.stringify({ product_name: productName }),
    });
  },

  // Demo Scenarios & Reset
  async listDemoScenarios(): Promise<{ scenarios: DemoScenario[] }> {
    return fetchJson('/demo/scenarios');
  },

  async loadDemoScenario(scenarioId: number): Promise<any> {
    return fetchJson(`/demo/scenario/${scenarioId}`, {
      method: 'POST',
    });
  },

  async resetDemo(): Promise<{ status: string; message: string }> {
    return fetchJson('/demo/reset', {
      method: 'POST',
    });
  },

  // Developer Platform
  async getDeveloperOverview(): Promise<any> {
    return fetchJson('/developer/overview');
  },

  // Subscriptions (Isolated Demo Catalog + PayPal Sandbox Subscriptions API v1)
  async getSubscriptionProducts(query?: string): Promise<import('../types').SubscriptionOffer[]> {
    const qs = query ? `?q=${encodeURIComponent(query)}` : '';
    return fetchJson(`/subscriptions/products${qs}`);
  },

  async askSubscriptionQuestion(offerId: string, question: string): Promise<{ offer_id: string; answer: string }> {
    return fetchJson('/subscriptions/qa', {
      method: 'POST',
      body: JSON.stringify({ offer_id: offerId, question }),
    });
  },

  async prepareSubscriptionReview(offerId: string): Promise<import('../types').SubscriptionReview> {
    return fetchJson('/subscriptions/review', {
      method: 'POST',
      body: JSON.stringify({ offer_id: offerId }),
    });
  },

  async confirmSubscription(params: {
    reviewToken: string;
    spokenPhrase: string;
    method?: string;
  }): Promise<import('../types').SubscriptionConfirmResponse> {
    return fetchJson('/subscriptions/confirm', {
      method: 'POST',
      body: JSON.stringify({
        review_token: params.reviewToken,
        spoken_phrase: params.spokenPhrase,
        method: params.method || 'VOICE',
      }),
    });
  },

  async createPayPalSubscription(params: {
    reviewToken: string;
    returnUrl?: string;
    cancelUrl?: string;
  }): Promise<import('../types').SubscriptionRecord> {
    return fetchJson('/subscriptions/paypal/create', {
      method: 'POST',
      body: JSON.stringify({
        review_token: params.reviewToken,
        return_url: params.returnUrl,
        cancel_url: params.cancelUrl,
      }),
    });
  },

  async getPayPalSubscriptionStatus(subscriptionId: string): Promise<import('../types').SubscriptionRecord> {
    return fetchJson(`/subscriptions/paypal/status/${encodeURIComponent(subscriptionId)}`);
  },

  async listSubscriptions(): Promise<import('../types').SubscriptionRecord[]> {
    return fetchJson('/subscriptions/records/list');
  },

  async cancelSubscription(
    subscriptionId: string,
    confirmationPhrase: string,
    reason?: string
  ): Promise<import('../types').SubscriptionRecord> {
    return fetchJson(`/subscriptions/${encodeURIComponent(subscriptionId)}/cancel`, {
      method: 'POST',
      body: JSON.stringify({ confirmation_phrase: confirmationPhrase, reason }),
    });
  },

  // Health
  async getHealth(): Promise<{ status: string; [key: string]: any }> {
    return fetchJson('/health');
  }
};
