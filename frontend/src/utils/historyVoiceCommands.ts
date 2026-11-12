import { SearchHistoryEntry } from '../types';

export type HistoryVoiceIntent =
  | { kind: 'show_history' }
  | { kind: 'run_last' }
  | { kind: 'run_previous' }
  | { kind: 'run_ordinal'; index: number }
  | { kind: 'run_query_again'; queryFragment: string }
  | { kind: 'save_last' }
  | { kind: 'save_ordinal'; index: number }
  | { kind: 'clear_history' };

const ORDINAL_MAP: Record<string, number> = {
  first: 0,
  '1st': 0,
  one: 0,
  second: 1,
  '2nd': 1,
  two: 1,
  third: 2,
  '3rd': 2,
  three: 2,
  fourth: 3,
  '4th': 3,
  four: 3,
  fifth: 4,
  '5th': 4,
  five: 4,
};

function parseOrdinal(text: string): number | null {
  for (const [word, idx] of Object.entries(ORDINAL_MAP)) {
    if (new RegExp(`\\b${word}\\b`, 'i').test(text)) {
      return idx;
    }
  }
  return null;
}

/**
 * Parses voice commands targeting Search History (Recent Searches) without interfering
 * with Saved Searches or Order History.
 */
export function parseHistoryVoiceIntent(rawTranscript: string): HistoryVoiceIntent | null {
  const lower = rawTranscript.toLowerCase().trim().replace(/[?.!]+$/g, '');
  if (!lower) return null;

  // Guard: never intercept order commands as search history
  if (/\border(s)?\b/.test(lower)) {
    return null;
  }

  // Clear recent searches (destructive -> caller confirms before executing)
  if (
    /\bclear\b.*\brecent search(es)?\b/.test(lower) ||
    /\bclear\b.*\bsearch history\b/.test(lower) ||
    /\bdelete\b.*\brecent search(es)?\b/.test(lower)
  ) {
    return { kind: 'clear_history' };
  }

  // Show / list recent searches
  if (
    /\b(show|open|view|list|what)\b.*\brecent search(es)?\b/.test(lower) ||
    /\b(show|open|view|list)\b.*\bsearch history\b/.test(lower) ||
    /\bwhat did i search( for)?\b/.test(lower) ||
    /\bmy search history\b/.test(lower)
  ) {
    return { kind: 'show_history' };
  }

  // Save a recent search into Saved Searches
  if (/\bsave\b/.test(lower) && /\b(last|previous|recent)\s+search\b/.test(lower)) {
    const ord = parseOrdinal(lower);
    if (ord !== null && /\brecent\s+search\b/.test(lower)) {
      return { kind: 'save_ordinal', index: ord };
    }
    if (/\b(last|most recent)\s+search\b/.test(lower)) {
      return { kind: 'save_last' };
    }
  }

  // Run an ordinal recent search: "run the second recent search"
  if (/\brecent\s+search\b/.test(lower)) {
    const ord = parseOrdinal(lower);
    if (ord !== null && /\b(run|open|rerun|re-run|use|repeat|select)\b/.test(lower)) {
      return { kind: 'run_ordinal', index: ord };
    }
  }

  // Previous search: "run my previous search", "go back to my previous search"
  if (
    /\bprevious\s+search\b/.test(lower) &&
    !/\bsaved\s+search\b/.test(lower)
  ) {
    return { kind: 'run_previous' };
  }

  // Last search: "run my last search", "repeat my last search" (not saved search)
  if (
    /\blast\s+search\b/.test(lower) &&
    !/\bsaved\s+search\b/.test(lower) &&
    /\b(run|rerun|re-run|repeat|go back|open)\b/.test(lower)
  ) {
    return { kind: 'run_last' };
  }

  // "Search for <query> again" -> match in recent searches
  const againMatch = lower.match(/^(?:search(?:\s+for)?|find)\s+(.+?)\s+again$/i);
  if (againMatch && againMatch[1]) {
    return { kind: 'run_query_again', queryFragment: againMatch[1].trim() };
  }

  return null;
}

/**
 * Resolves "previous search" (the search immediately before the currently active search)
 * vs "last search" (most recent search when no active search is open).
 */
export function resolvePreviousSearchEntry(
  history: SearchHistoryEntry[],
  activeSearchId: string | null | undefined,
  activeQuery?: string | null
): SearchHistoryEntry | null {
  if (history.length === 0) return null;

  if (activeSearchId) {
    const activeIdx = history.findIndex((h) => h.search_id === activeSearchId);
    if (activeIdx >= 0) {
      return history[activeIdx + 1] ?? null;
    }
  }

  if (activeQuery && activeQuery.trim()) {
    const normActive = activeQuery.trim().toLowerCase();
    const activeIdx = history.findIndex(
      (h) =>
        h.query.trim().toLowerCase() === normActive ||
        h.display_query.trim().toLowerCase() === normActive
    );
    if (activeIdx >= 0) {
      return history[activeIdx + 1] ?? null;
    }
  }

  // If an active search is running (even if not in history), "previous search" is history[0];
  // if no active search, it's also history[0].
  return history[0];
}

export function findMatchingHistoryEntry(
  history: SearchHistoryEntry[],
  fragment: string
): SearchHistoryEntry | null {
  const tokens = fragment
    .toLowerCase()
    .split(/\s+/)
    .filter((t) => t.length >= 2);
  if (tokens.length === 0) return history[0] ?? null;

  let best: SearchHistoryEntry | null = null;
  let bestScore = 0;
  for (const entry of history) {
    const hay = `${entry.display_query} ${entry.query}`.toLowerCase();
    const score = tokens.reduce((acc, tok) => (hay.includes(tok) ? acc + 1 : acc), 0);
    if (score > bestScore) {
      bestScore = score;
      best = entry;
    }
  }
  return bestScore > 0 ? best : null;
}

