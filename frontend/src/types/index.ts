export type AccessibilityMode = 'VOICE' | 'LARGE_CONTROLS' | 'KEYBOARD' | 'SWITCH';

export interface AccessibilityPreferences {
  user_name: string;
  current_mode: AccessibilityMode;
  read_important_aloud: boolean;
  read_total_aloud: boolean;
  simplified_interface: boolean;
  one_action_per_screen: boolean;
  reduced_motion: boolean;
  extra_response_time: boolean;
  warn_subscriptions: boolean;
  always_show_total_cost: boolean;
  suggest_cheaper_alternatives: boolean;
  cheaper_alternative_threshold: number;
  exact_price_confirmation: boolean;
  double_confirmation_threshold: number;
  warn_quantity_greater_one: boolean;
  warn_shipping_exceeds: number;
  switch_scan_speed_ms: number;
}

export interface Product {
  id: string;
  title: string;
  name?: string | null;
  description: string;
  price: number;
  original_price?: number | null;
  shipping: number;
  estimated_tax: number;
  category: string;
  merchant: string;
  image_url: string;
  image_alt?: string | null;
  product_url?: string | null;
  rating?: number | null;
  review_count?: number | null;
  is_available: boolean;
  availability?: string | null;
  attributes?: Record<string, any>;
  source?: string;
  is_subscription: boolean;
  subscription_period?: string | null;
  is_trial: boolean;
  trial_days: number;
  trial_post_price: number;
  documented_accessibility_features: string[];
  ai_inferred_accessibility: string[];
  ranking_badge?: string | null;
  ranking_reason?: string | null;
  cheaper_alternative_id?: string | null;
  savings_amount?: number | null;
  variants?: Record<string, string[]> | null;
}

export interface CartItem {
  id: string;
  product_id: string;
  product: Product;
  quantity: number;
  selected_variant?: Record<string, string>;
  item_total: number;
}

export interface Cart {
  items: CartItem[];
  item_count: number;
  subtotal: number;
  shipping_total: number;
  tax_total: number;
  discount_total: number;
  total_today: number;
  future_payments: string;
  has_subscriptions: boolean;
  has_trials: boolean;
  warnings: string[];
}

export type PurchaseState =
  | 'BROWSING'
  | 'PRODUCT_SELECTED'
  | 'CART'
  | 'PAYMENT_REVIEW'
  | 'CONFIRMATION_REQUIRED'
  | 'PAYMENT_PROCESSING'
  | 'PAYMENT_COMPLETE'
  | 'CANCELLED'
  | 'PAYMENT_FAILED';

export interface PurchaseReview {
  state: PurchaseState;
  cart: Cart;
  item_subtotal: number;
  shipping: number;
  tax: number;
  discount: number;
  total_today: number;
  future_payments: string;
  is_high_value: boolean;
  high_value_step: number;
  high_value_total_steps: number;
  requires_exact_phrase: boolean;
  expected_phrase: string;
  is_subscription: boolean;
  subscription_terms?: string | null;
  subscription_acknowledged: boolean;
  is_free_trial: boolean;
  trial_terms?: string | null;
  trial_acknowledged: boolean;
  quantity_warning?: string | null;
  shipping_warning?: string | null;
  snapshot_total: number;
  snapshot_shipping: number;
  snapshot_item_subtotal: number;
  review_token: string;
  is_invalidated: boolean;
  invalidation_reason?: string | null;
}

export interface OrderLineItem {
  product_id: string;
  product_title: string;
  merchant: string;
  category: string;
  unit_price: number;
  quantity: number;
  line_total: number;
  variant?: string | null;
}

export interface PurchaseResponse {
  success: boolean;
  state: PurchaseState;
  message: string;
  order_id?: string | null;
  paypal_order_id?: string | null;
  paypal_capture_id?: string | null;
  product_title?: string | null;
  merchant?: string | null;
  is_subscription?: boolean | null;
  amount_charged?: number | null;
  item_subtotal?: number | null;
  shipping?: number | null;
  tax?: number | null;
  items?: OrderLineItem[];
  requires_step?: number | null;
  is_ambiguous: boolean;
}

export interface PayPalOrderCreationResponse {
  success: boolean;
  paypal_order_id?: string;
  status?: string;
  amount?: number;
  item_subtotal?: number;
  shipping?: number;
  tax?: number;
  discount?: number;
  currency?: string;
  product_title?: string;
  merchant?: string;
  item_count?: number;
  items?: OrderLineItem[];
  is_subscription?: boolean;
  subscription_terms?: string | null;
  subscription_note?: string | null;
  provider?: string;
  environment?: string;
  approval_url?: string | null;
  price_changed?: boolean;
  duplicate?: boolean;
  state?: PurchaseState;
  message?: string;
}

export interface PayPalCaptureResponse {
  success: boolean;
  state: PurchaseState;
  message: string;
  order_id?: string;
  paypal_order_id?: string;
  paypal_capture_id?: string | null;
  product_title?: string;
  merchant?: string;
  amount_charged?: number;
  item_subtotal?: number;
  shipping?: number;
  tax?: number;
  items?: OrderLineItem[];
  is_subscription?: boolean;
  environment?: string;
  price_changed?: boolean;
  duplicate?: boolean;
}

export interface TimelineEvent {
  id: string;
  date: string;
  display_date: string;
  title: string;
  category: 'purchase' | 'delivery' | 'subscription' | 'trial_expiration';
  amount?: number | null;
  merchant?: string | null;
  description: string;
  status: string;
  is_recurring: boolean;
  recurring_interval?: string | null;
  highlight?: boolean;
}

export interface OrderRecord {
  order_id: string;
  date: string;
  product_title: string;
  merchant: string;
  category: string;
  item_price: number;
  item_subtotal?: number | null;
  shipping: number;
  tax: number;
  total: number;
  quantity: number;
  variant: string;
  items?: OrderLineItem[];
  is_recurring: boolean;
  interaction_mode: string;
  confirmation_method: string;
  payment_status: string;
  paypal_order_id?: string | null;
  paypal_capture_id?: string | null;
  tracking_status: string;
  tracking_number?: string | null;
  return_eligible: boolean;
  return_window_days: number;
}

export interface AccessibilityActivitySummary {
  purchases_completed: number;
  voice_interactions: number;
  keyboard_interactions: number;
  large_control_interactions: number;
  switch_compatible_interactions: number;
  subscription_warnings_shown: number;
  cheaper_alternatives_accepted: number;
  purchases_cancelled_before_payment: number;
}

export interface DemoScenario {
  id: number;
  title: string;
  description: string;
  initial_command?: string;
  recommended_next_commands?: string[];
  expected_behavior?: string;
  target_mode?: AccessibilityMode;
}

export interface SavedItem {
  saved_item_id: string;
  product_id: string;
  product_title: string;
  merchant: string;
  price_at_save: number;
  image_url?: string | null;
  product_url?: string | null;
  important_attributes?: string[];
  product_snapshot: Product;
  saved_at: string;
}

export interface SavedSearch {
  saved_search_id: string;
  original_query: string;
  display_query: string;
  structured_intent?: Record<string, any>;
  filters?: Record<string, any>;
  sort?: string | null;
  reference_product_ids?: string[];
  saved_at: string;
}

export interface SearchHistoryEntry {
  history_id: string;
  search_id: string;
  query: string;
  display_query: string;
  result_count: number;
  structured_intent?: Record<string, any>;
  filters?: Record<string, any>;
  sort?: string | null;
  searched_at: string;
}

export interface ActiveSearchSnapshot {
  search_id?: string | null;
  search_generation: number;
  original_query: string;
  display_query: string;
  displayed_products: Product[];
  displayed_product_ids: string[];
  count: number;
  has_more: boolean;
  total_available: number;
  filters?: Record<string, any>;
  sort?: string | null;
}

export type AppViewName =
  | 'SHOP'
  | 'SAVED_ITEMS'
  | 'SAVED_SEARCHES'
  | 'ORDERS'
  | 'ORDER_DETAILS'
  | 'SUBSCRIPTIONS'
  | 'CART'
  | 'PURCHASE_REVIEW'
  | 'CONFIRMATION_REQUIRED'
  | 'PAYPAL_CHECKOUT'
  | 'PAYMENT_SUCCESS'
  | 'PAYMENT_FAILURE'
  | 'SUBSCRIPTION_RESULTS'
  | 'SUBSCRIPTION_REVIEW'
  | 'SUBSCRIPTION_CONFIRMATION'
  | 'SUBSCRIPTION_PAYPAL'
  | 'SUBSCRIPTION_OUTCOME';

export interface SubscriptionOffer {
  id: string;
  provider: string;
  name: string;
  description: string;
  image_url?: string | null;
  currency: string;
  amount_due_today: number;
  recurring_amount: number;
  billing_frequency: string;
  billing_interval: string;
  interval_count: number;
  trial_period?: string | null;
  setup_fee?: number | null;
  renewal_behavior: string;
  cancellation_information: string;
  paypal_product_id?: string | null;
  paypal_plan_id?: string | null;
  source: string;
  is_demo: boolean;
}

export interface SubscriptionReview {
  review_token: string;
  offer: SubscriptionOffer;
  due_today: number;
  recurring_amount: number;
  billing_frequency: string;
  expected_phrase: string;
  is_invalidated: boolean;
  invalidation_reason?: string | null;
  confirmation_granted: boolean;
}

export interface SubscriptionConfirmResponse {
  success: boolean;
  is_ambiguous: boolean;
  wrong_amount: boolean;
  wrong_frequency: boolean;
  message: string;
  review_token: string;
  expected_phrase: string;
}

export interface SubscriptionRecord {
  subscription_id: string;
  offer_id: string;
  plan_name: string;
  provider: string;
  currency: string;
  amount_due_today: number;
  recurring_amount: number;
  billing_frequency: string;
  paypal_product_id?: string | null;
  paypal_plan_id?: string | null;
  paypal_subscription_id: string;
  status: string;
  approval_url?: string | null;
  created_at: string;
  updated_at: string;
  cancelled_at?: string | null;
  is_demo_catalog: boolean;
  paypal_environment: string;
}
