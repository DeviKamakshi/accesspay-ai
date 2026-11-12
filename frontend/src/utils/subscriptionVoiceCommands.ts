import { AppViewName } from '../types';

export type SubscriptionVoiceIntent =
  | { kind: 'search_subscriptions'; query: string }
  | { kind: 'open_subscriptions' }
  | { kind: 'open_purchases' }
  | { kind: 'select_subscription'; index: number }
  | { kind: 'review_subscription'; index?: number }
  | { kind: 'subscription_qa'; question: string; index?: number }
  | { kind: 'subscription_confirm_attempt'; phrase: string }
  | { kind: 'subscription_record_qa'; question: string }
  | { kind: 'cancel_subscription_start' }
  | { kind: 'cancel_subscription_confirm'; phrase: string }
  | { kind: 'cancel_subscription_flow' };

const SUBSCRIPTION_VIEWS = new Set<AppViewName>([
  'SUBSCRIPTION_RESULTS',
  'SUBSCRIPTION_REVIEW',
  'SUBSCRIPTION_CONFIRMATION',
  'SUBSCRIPTION_PAYPAL',
  'SUBSCRIPTION_OUTCOME',
]);

function extractOrdinalIndex(clean: string): number | undefined {
  if (/\b(first|1st|one|#1|option 1|plan 1)\b/.test(clean)) return 0;
  if (/\b(second|2nd|two|#2|option 2|plan 2)\b/.test(clean)) return 1;
  if (/\b(third|3rd|three|#3|option 3|plan 3)\b/.test(clean)) return 2;
  return undefined;
}

export function parseSubscriptionVoiceIntent(
  raw: string,
  currentView: AppViewName
): SubscriptionVoiceIntent | null {
  const trimmed = (raw || '').trim();
  const clean = trimmed.toLowerCase().replace(/[?.!,]+$/g, '').trim();
  if (!clean) return null;

  // 1. Post-subscription navigation & queries (work from anywhere)
  if (
    /^(show|open|view|list|what)\s+(my\s+)?subscriptions?(\s+do i have)?$/.test(clean) ||
    clean === 'open my subscription' ||
    clean === 'what subscriptions do i have'
  ) {
    return { kind: 'open_subscriptions' };
  }

  if (clean === 'go back to purchases' || clean === 'show my purchases') {
    return { kind: 'open_purchases' };
  }

  if (
    /^confirm cancellation of\b/.test(clean) ||
    (clean.includes('confirm') && clean.includes('cancel'))
  ) {
    return { kind: 'cancel_subscription_confirm', phrase: trimmed };
  }

  if (
    clean === 'cancel this subscription' ||
    clean === 'cancel my subscription' ||
    clean === 'cancel subscription'
  ) {
    return { kind: 'cancel_subscription_start' };
  }

  // 2. Subscription Discovery (works from Shop or anywhere)
  if (
    /\b(show|find|search|list|get)\b.*\bsubscriptions?\b/.test(clean) ||
    /\bsubscription\s+(plans|services|options|catalog)\b/.test(clean) ||
    /^(monthly|annual|yearly)\s+subscriptions?$/.test(clean)
  ) {
    return { kind: 'search_subscriptions', query: trimmed };
  }

  // 3. Post-subscription account questions (when in SUBSCRIPTIONS or SUBSCRIPTION_OUTCOME)
  if (currentView === 'SUBSCRIPTIONS' || currentView === 'SUBSCRIPTION_OUTCOME') {
    if (
      clean.includes('how much is my subscription') ||
      clean.includes('how often am i charged') ||
      clean.includes('my subscription')
    ) {
      return { kind: 'subscription_record_qa', question: trimmed };
    }
  }

  // 4. Inside active subscription shopping/review views
  if (!SUBSCRIPTION_VIEWS.has(currentView)) {
    return null;
  }

  if (
    clean === 'go back' ||
    clean === 'never mind' ||
    clean === 'cancel' ||
    clean === 'cancel review' ||
    clean === 'back to shop'
  ) {
    return { kind: 'cancel_subscription_flow' };
  }

  // In Review or Confirmation view: route confirmation phrases (exact OR casual/wrong) to server gate!
  if (currentView === 'SUBSCRIPTION_REVIEW' || currentView === 'SUBSCRIPTION_CONFIRMATION') {
    if (
      clean.startsWith('confirm') ||
      /^(yes|yeah|yep|okay|ok|sure|go ahead|subscribe|buy it|continue|sounds good|click confirm|do it|looks good)$/.test(
        clean
      )
    ) {
      return { kind: 'subscription_confirm_attempt', phrase: trimmed };
    }
  }

  // In Results view: "Subscribe" / "Review this subscription" opens SUBSCRIPTION REVIEW (NEVER subscribes!)
  if (
    clean === 'subscribe' ||
    clean.includes('review this subscription') ||
    clean.includes('review subscription') ||
    clean.includes('open subscription review')
  ) {
    return { kind: 'review_subscription', index: extractOrdinalIndex(clean) };
  }

  // Selection in Results view
  if (/\b(select|choose|pick)\b/.test(clean)) {
    const idx = extractOrdinalIndex(clean);
    return { kind: 'select_subscription', index: idx ?? 0 };
  }

  // Subscription Q&A
  if (
    clean.includes('is this a subscription') ||
    clean.includes('how much') ||
    clean.includes('how often') ||
    clean.includes('trial') ||
    clean.includes('renew') ||
    clean.includes('cancel') ||
    clean.includes('agreeing to') ||
    clean.includes('tell me about') ||
    clean.includes('due today') ||
    clean.includes('every month') ||
    clean.includes('billing')
  ) {
    return {
      kind: 'subscription_qa',
      question: trimmed,
      index: extractOrdinalIndex(clean),
    };
  }

  return null;
}

