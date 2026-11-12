import { AppViewName } from '../types';

export type VoiceControlType =
  | 'tab'
  | 'navigation'
  | 'button'
  | 'product-action'
  | 'saved-item-action'
  | 'saved-search-action'
  | 'order-action'
  | 'cart-action'
  | 'checkout-action'
  | 'dialog-action';

export interface VoiceControlDescriptor {
  id: string;
  type: VoiceControlType;
  accessibleName: string;
  aliases?: string[];
  entityId?: string;
  entityTitle?: string;
  entityIndex?: number;
  currentView: AppViewName | 'GLOBAL';
  enabled: boolean;
  disabledReason?: string;
  sensitivePaymentAuth?: boolean;
  feedbackText?: string;
  action: () => void | Promise<void>;
}

export type VoiceControlMatchResult =
  | { status: 'matched'; control: VoiceControlDescriptor }
  | { status: 'disabled'; control: VoiceControlDescriptor; message: string }
  | { status: 'ambiguous'; candidates: VoiceControlDescriptor[]; message: string }
  | { status: 'no_match' };

const ORDINAL_WORDS: Record<string, number> = {
  first: 0,
  '1st': 0,
  one: 0,
  '1': 0,
  second: 1,
  '2nd': 1,
  two: 1,
  '2': 1,
  third: 2,
  '3rd': 2,
  three: 2,
  '3': 2,
  fourth: 3,
  '4th': 3,
  four: 3,
  '4': 3,
  fifth: 4,
  '5th': 4,
  five: 4,
  '5': 4,
  sixth: 5,
  '6th': 5,
  six: 5,
  '6': 5,
  seventh: 6,
  '7th': 6,
  seven: 6,
  '7': 6,
  eighth: 7,
  '8th': 7,
  eight: 7,
  '8': 7,
  ninth: 8,
  '9th': 8,
  nine: 8,
  '9': 8,
  tenth: 9,
  '10th': 9,
  ten: 9,
  '10': 9,
};

export function parseVoiceOrdinal(text: string): { index: number | null; isChronologicalLatest: boolean } {
  const t = (text || '').toLowerCase();
  if (/\b(?:last|latest|recent|previous)\b/.test(t)) {
    return {
      index: -1,
      isChronologicalLatest: /\b(?:latest|recent|previous|last\s+order)\b/.test(t),
    };
  }
  const match = t.match(
    /\b(?:the\s+)?(first|1st|second|2nd|third|3rd|fourth|4th|fifth|5th|sixth|6th|seventh|7th|eighth|8th|ninth|9th|tenth|10th)\b|\b(?:option|item|product|order|search|number|#)\s*(10|[1-9]|one|two|three|four|five|six|seven|eight|nine|ten)\b/
  );
  if (match) {
    const token = (match[1] || match[2] || '').toLowerCase();
    if (token in ORDINAL_WORDS) {
      return { index: ORDINAL_WORDS[token], isChronologicalLatest: false };
    }
  }
  const bare = t.trim().replace(/^the\s+/, '').replace(/\s+one$/, '').trim();
  if (bare in ORDINAL_WORDS) {
    return { index: ORDINAL_WORDS[bare], isChronologicalLatest: false };
  }
  return { index: null, isChronologicalLatest: false };
}

function normalizePhrase(raw: string): string {
  return (raw || '')
    .toLowerCase()
    .replace(/\([^)]*\)/g, ' ') // Strip count badges like "Saved (2)" -> "saved"
    .replace(/\$[0-9]+(?:\.[0-9]+)?/g, ' ')
    .replace(/[.,!?;:'"()]+/g, ' ')
    .replace(/\s+/g, ' ')
    .trim();
}

function stripInvocationPrefix(normalized: string): string {
  return normalized
    .replace(
      /^(?:please\s+)?(?:click|press|tap|select|choose|activate|hit|push|open|go\s+to|switch\s+to|show\s+me|show|view)\s+(?:the\s+|my\s+)?/i,
      ''
    )
    .replace(/\s+(?:tab|button|control|link)$/i, '')
    .trim();
}

function shouldDeferToSemanticIntentRouter(raw: string, currentView: AppViewName): boolean {
  const t = (raw || '').toLowerCase().trim();
  if (!t) return true;

  // Sensitive confirmation utterances MUST ALWAYS go to backend ConfirmationService
  if (/\bconfirm\b.*(?:\$|\d)/.test(t)) return true;
  if (
    currentView === 'CONFIRMATION_REQUIRED' &&
    /^(?:yes|yeah|yep|ok|okay|sure|buy\s+it|go\s+ahead|do\s+it|continue|proceed|click\s+confirm|press\s+confirm|confirm|confirm\s+purchase)$/i.test(
      t
    )
  ) {
    return true;
  }
  if (/^(?:click\s+confirm|press\s+confirm|yes|yeah|yep|ok|okay|sure|buy\s+it|go\s+ahead|do\s+it|confirm\s+purchase)$/i.test(t)) {
    return true;
  }

  // Search queries, multi-item comparisons, filters, and conversational Q&A go to backend AI router
  if (/\b(?:find|search\s+for|look\s+for|under\s+\$|below\s+\$|cheaper\s+alternative|something\s+cheaper|show\s+something|compare)\b/.test(t)) {
    return true;
  }
  if (/\b(?:what\s+did\s+i\s+buy|how\s+much\s+was|what\s+was\s+the\s+total|what'?s\s+my\s+total|read\s+my\s+order|read\s+receipt|read\s+order)\b/.test(t)) {
    return true;
  }
  // Explicit quantity value mutations ("set second item quantity to 3", "change quantity to 2")
  if (/\b(?:quantity|qty)\s+to\s+\d+|\b(?:set|change|update)\b.*\bquantity\b.*\b(?:to\s+)?(?:one|two|three|four|five|six|seven|eight|nine|ten|\d+)\b/.test(t)) {
    return true;
  }
  return false;
}

export function isDiscoveryQuestion(raw: string): boolean {
  const t = normalizePhrase(raw);
  return /^(?:what\s+can\s+i\s+say|what\s+can\s+i\s+do|what\s+can\s+i\s+do\s+here|help|available\s+commands|commands)$/.test(
    t
  );
}

export function buildDiscoveryHelp(currentView: AppViewName, controls: VoiceControlDescriptor[]): string {
  const viewNames: Record<AppViewName, string> = {
    SHOP: 'Shop',
    SAVED_ITEMS: 'Saved Items',
    SAVED_SEARCHES: 'Saved Searches',
    ORDERS: 'Orders',
    ORDER_DETAILS: 'Order Details',
    SUBSCRIPTIONS: 'Subscriptions',
    CART: 'Cart',
    PURCHASE_REVIEW: 'Purchase Review',
    CONFIRMATION_REQUIRED: 'Payment Confirmation',
    PAYPAL_CHECKOUT: 'PayPal Checkout',
    PAYMENT_SUCCESS: 'Payment Receipt',
    PAYMENT_FAILURE: 'Payment Failed',
    SUBSCRIPTION_RESULTS: 'Subscription Plans',
    SUBSCRIPTION_REVIEW: 'Subscription Review',
    SUBSCRIPTION_CONFIRMATION: 'Subscription Confirmation',
    SUBSCRIPTION_PAYPAL: 'PayPal Subscription Checkout',
    SUBSCRIPTION_OUTCOME: 'Subscription Receipt',
  };

  if (currentView === 'CART') {
    return 'On Cart, you can ask me to increase or decrease a quantity, remove an item, clear your cart, read your total, or checkout.';
  }
  if (currentView === 'SAVED_ITEMS') {
    return 'On Saved Items, you can say open or view an item, add it to cart, remove an item, switch to Searches, or go to Shop or Cart.';
  }
  if (currentView === 'SAVED_SEARCHES') {
    return 'On Saved Searches, you can say run the first search again, delete a saved search, clear search history, or switch to Items.';
  }
  if (currentView === 'ORDERS' || currentView === 'ORDER_DETAILS') {
    return 'On Orders, you can open or collapse an order, view details, buy an order again, ask about totals or shipping, or go to Cart.';
  }
  if (currentView === 'PURCHASE_REVIEW') {
    return 'On Purchase Review, you can say read my order, continue, cancel, or go back.';
  }
  if (currentView === 'CONFIRMATION_REQUIRED') {
    return 'Say the exact displayed confirmation phrase to authorize, or say cancel or go back.';
  }
  if (currentView === 'PAYPAL_CHECKOUT') {
    return 'On PayPal Checkout, you can say continue to PayPal, cancel, or go back.';
  }

  const activeLabels = Array.from(
    new Set(
      controls
        .filter((c) => c.enabled && !c.sensitivePaymentAuth && c.currentView === currentView)
        .map((c) => normalizePhrase(c.accessibleName))
        .filter(Boolean)
    )
  ).slice(0, 5);

  const labelPhrase = activeLabels.length > 0 ? activeLabels.join(', ') : 'search for a product, compare options, or open Saved, Orders, or Cart';
  if (currentView === 'SHOP') {
    return `On Shop, you can ${labelPhrase}. You can also say 'run my previous search' or 'show my recent searches.'`;
  }
  return `On ${viewNames[currentView] || 'Shop'}, you can ${labelPhrase}.`;
}

export function resolveAmbiguousOrdinal(
  rawTranscript: string,
  candidates: VoiceControlDescriptor[]
): VoiceControlMatchResult {
  const norm = normalizePhrase(rawTranscript);
  // If user switched to a new explicit action ("increase the first item quantity", "open cart", "checkout"),
  // don't hijack it as an answer to the old clarification.
  if (
    norm.split(' ').length > 4 ||
    /\b(?:increase|decrease|reduce|quantity|remove|delete|checkout|clear|compare|find|search|buy|run|go\s+to|back|cancel|cart|orders|saved|shop)\b/.test(
      norm
    )
  ) {
    return { status: 'no_match' };
  }
  const { index, isChronologicalLatest } = parseVoiceOrdinal(rawTranscript);
  if (index === null || candidates.length === 0) {
    return { status: 'no_match' };
  }
  const target =
    index === -1
      ? isChronologicalLatest
        ? candidates[0]
        : candidates[candidates.length - 1]
      : candidates[index];
  if (!target) {
    return { status: 'no_match' };
  }
  if (!target.enabled) {
    return {
      status: 'disabled',
      control: target,
      message: target.disabledReason || `${target.accessibleName} isn't available right now.`,
    };
  }
  return { status: 'matched', control: target };
}

export function matchVisibleVoiceControl(
  rawTranscript: string,
  currentView: AppViewName,
  allControls: VoiceControlDescriptor[]
): VoiceControlMatchResult {
  if (shouldDeferToSemanticIntentRouter(rawTranscript, currentView)) {
    return { status: 'no_match' };
  }

  const normFull = normalizePhrase(rawTranscript);
  const stripped = stripInvocationPrefix(normFull);
  if (!normFull) return { status: 'no_match' };

  const { index: ordinalIdx, isChronologicalLatest } = parseVoiceOrdinal(normFull);

  // Extract leading verb before stripping so both pronoun phrases ("open it") and ordinal phrases ("select the first product") retain the verb
  const leadVerbMatch = normFull.match(
    /^(?:please\s+)?(click|press|tap|select|choose|activate|open|view|save|remove|delete|add|run|re-?run)\b/i
  );
  const leadVerb = leadVerbMatch ? leadVerbMatch[1].toLowerCase().replace('-', '') : '';
  const isPronounObj = /^(?:please\s+)?(click|press|tap|select|choose|activate|open|view|save|remove|delete|add)\s+(?:it|this|that)(?:\s+one)?$/i.test(
    normFull
  );
  const effectiveNorm = isPronounObj ? leadVerb : normFull;
  const effectiveStripped = isPronounObj ? leadVerb : stripped;

  // Strip ordinal/item filler words so "save the second product" matches control accessibleName "save"
  let actionCore = effectiveStripped
    .replace(
      /\b(?:the\s+)?(?:first|1st|second|2nd|third|3rd|fourth|4th|fifth|5th|sixth|6th|seventh|7th|eighth|8th|ninth|9th|tenth|10th|last|latest|recent|previous|this|that)\b/g,
      ' '
    )
    .replace(/\b(?:one|item|product|option|saved\s+item|saved\s+search|order|search)\b/g, ' ')
    .replace(/\b(?:for|from|of|to|in|my|me|it)\b/g, ' ')
    .replace(/\s+/g, ' ')
    .trim();
  if (!actionCore && leadVerb && !['click', 'press', 'tap', 'activate'].includes(leadVerb)) {
    actionCore = leadVerb;
  }

  const visiblePool = allControls.filter(
    (c) => !c.sensitivePaymentAuth && (c.currentView === currentView || c.currentView === 'GLOBAL')
  );

  type ScoredControl = { ctrl: VoiceControlDescriptor; score: number };
  const scored: ScoredControl[] = [];

  for (const ctrl of visiblePool) {
    const names = [ctrl.accessibleName, ...(ctrl.aliases || [])].map(normalizePhrase).filter(Boolean);
    let best = 0;

    for (const candidateName of names) {
      if (effectiveNorm === candidateName || effectiveStripped === candidateName) {
        best = Math.max(best, 100);
      } else if (actionCore && actionCore === candidateName) {
        best = Math.max(best, 92);
      } else if (
        effectiveStripped.length >= 3 &&
        (candidateName === effectiveStripped ||
          (candidateName.split(' ').length >= 2 && effectiveStripped.includes(candidateName)))
      ) {
        best = Math.max(best, 84);
      } else if (
        actionCore.length >= 3 &&
        (candidateName === actionCore ||
          (candidateName.split(' ').length >= 1 &&
            actionCore.split(' ').every((tok) => candidateName.split(' ').includes(tok))))
      ) {
        best = Math.max(best, 76);
      }
    }

    // Special natural action phrase check: "add ... to cart" -> matches "Add to Cart"
    if (
      best === 0 &&
      /\badd\b.*\b(?:to\s+)?cart\b/.test(normFull) &&
      names.some((n) => n === 'add to cart' || n === 'select')
    ) {
      best = names.includes('add to cart') ? 88 : 80;
    }
    // "run ... search" / "run the second search again" -> matches "Run Again"
    if (
      best === 0 &&
      /\b(?:run|re-?run)\b/.test(normFull) &&
      names.includes('run again')
    ) {
      best = 86;
    }
    // "buy ... again" -> matches "Buy Again"
    if (
      best === 0 &&
      /\bbuy\b.*\bagain\b/.test(normFull) &&
      names.includes('buy again')
    ) {
      best = 88;
    }
    // "collapse ..." -> matches "Hide Details"
    if (
      best === 0 &&
      /\b(?:collapse|close|hide)\b/.test(normFull) &&
      names.some((n) => n === 'hide details' || n === 'collapse')
    ) {
      best = 88;
    }
    // "view details ..." -> matches "View Details"
    if (
      best === 0 &&
      /\b(?:view\s+details|details|expand)\b/.test(normFull) &&
      names.some((n) => n === 'view details' || n === 'details')
    ) {
      best = 86;
    }
    // "increase ... quantity" / "decrease ... quantity"
    if (
      best === 0 &&
      /\b(?:increase|more|plus|increment)\b/.test(normFull) &&
      /\bquantity\b/.test(normFull) &&
      names.includes('increase quantity')
    ) {
      best = 90;
    }
    if (
      best === 0 &&
      /\b(?:decrease|reduce|less|minus|decrement)\b/.test(normFull) &&
      /\bquantity\b/.test(normFull) &&
      names.includes('decrease quantity')
    ) {
      best = 90;
    }

    // Boost score if entityTitle appears in the spoken utterance
    if (best > 0 && ctrl.entityTitle) {
      const titleTokens = normalizePhrase(ctrl.entityTitle)
        .split(' ')
        .filter((w) => w.length >= 3);
      if (titleTokens.some((tok) => normFull.includes(tok))) {
        best += 15;
      }
    }

    if (best >= 76) {
      scored.push({ ctrl, score: best });
    }
  }

  if (scored.length === 0) {
    return { status: 'no_match' };
  }

  scored.sort((a, b) => b.score - a.score);
  const topScore = scored[0].score;
  const topControls = scored.filter((s) => s.score === topScore).map((s) => s.ctrl);

  if (topControls.length === 1) {
    const target = topControls[0];
    if (!target.enabled) {
      return {
        status: 'disabled',
        control: target,
        message: target.disabledReason || `${target.accessibleName} isn't available right now.`,
      };
    }
    return { status: 'matched', control: target };
  }

  // Multiple matching controls (e.g., Save / View / Add to Cart across multiple cards)
  if (ordinalIdx !== null) {
    const ordered = [...topControls].sort(
      (a, b) => (a.entityIndex ?? 0) - (b.entityIndex ?? 0)
    );
    const chosen =
      ordinalIdx === -1
        ? isChronologicalLatest
          ? ordered[0]
          : ordered[ordered.length - 1]
        : ordered.find((c) => c.entityIndex === ordinalIdx) || ordered[ordinalIdx];
    if (chosen) {
      if (!chosen.enabled) {
        return {
          status: 'disabled',
          control: chosen,
          message: chosen.disabledReason || `${chosen.accessibleName} isn't available right now.`,
        };
      }
      return { status: 'matched', control: chosen };
    }
  }

  // Ambiguous match without ordinal or entity title -> ask clarifying question!
  const verbLabel = normalizePhrase(topControls[0].accessibleName);
  return {
    status: 'ambiguous',
    candidates: topControls,
    message: `Which item would you like to ${verbLabel}? Say the first one or the second one.`,
  };
}
