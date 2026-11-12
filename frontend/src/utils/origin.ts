export const CANONICAL_LOCAL_ORIGIN = 'http://127.0.0.1:5173';

/**
 * Ensures local development always uses ONE canonical origin (127.0.0.1:5173)
 * rather than mixing localhost:5173 and 127.0.0.1:5173, because browser
 * microphone permissions are strictly origin-scoped.
 */
export function ensureCanonicalLocalOrigin(): boolean {
  if (typeof window === 'undefined') return false;
  if (window.location.hostname === 'localhost' && window.location.port === '5173') {
    const target = `${CANONICAL_LOCAL_ORIGIN}${window.location.pathname}${window.location.search}${window.location.hash}`;
    window.location.replace(target);
    return true;
  }
  return false;
}

export function getCanonicalFrontendOrigin(): string {
  if (typeof window === 'undefined') return '';
  if (
    (window.location.hostname === 'localhost' || window.location.hostname === '127.0.0.1') &&
    window.location.port === '5173'
  ) {
    return CANONICAL_LOCAL_ORIGIN;
  }
  return window.location.origin;
}

