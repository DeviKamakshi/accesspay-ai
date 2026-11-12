import React, {
  createContext,
  useCallback,
  useContext,
  useEffect,
  useRef,
  useState,
} from 'react';
import { api } from '../services/api';
import { AppViewName } from '../types';
import { useAccessibility } from './AccessibilityContext';
import {
  VoiceControlDescriptor,
  buildDiscoveryHelp,
  isDiscoveryQuestion,
  matchVisibleVoiceControl,
  resolveAmbiguousOrdinal,
} from '../utils/voiceControlMatcher';
import {
  findMatchingHistoryEntry,
  parseHistoryVoiceIntent,
  resolvePreviousSearchEntry,
} from '../utils/historyVoiceCommands';
import { parseSubscriptionVoiceIntent } from '../utils/subscriptionVoiceCommands';

export type VoiceStatus = 'idle' | 'listening' | 'processing';
export type VoiceInputSource = 'REAL_MIC' | 'SIMULATED_VOICE' | 'COMMAND_CHIP';

export interface VoiceViewSnapshot {
  currentView: AppViewName;
  activeSearchId?: string | null;
  searchGeneration?: number;
  visibleProductIds?: string[];
  visibleSavedItemIds?: string[];
  visibleSavedSearchIds?: string[];
  visibleOrderIds?: string[];
  selectedOrderId?: string | null;
  selectedSavedItemId?: string | null;
  visibleCartProductIds?: string[];
}

export interface VoiceHandlerRegistration {
  getContext: () => VoiceViewSnapshot;
  onIntentResult: (
    response: any,
    rawTranscript: string,
    source: VoiceInputSource
  ) => Promise<AppViewName | void> | AppViewName | void;
}

interface VoiceCommandContextValue {
  voiceStatus: VoiceStatus;
  voiceError: string | null;
  lastTranscript: string;
  voiceFeedback: string | null;
  clearVoiceFeedback: () => void;
  startListening: () => void;
  stopListening: () => void;
  toggleListening: () => void;
  processVoiceTranscript: (rawTranscript: string, source?: VoiceInputSource) => Promise<any>;
  registerVoiceHandler: (handler: VoiceHandlerRegistration) => () => void;
  registerVoiceControls: (ownerKey: string, controls: VoiceControlDescriptor[]) => () => void;
  getRegisteredControls: (view?: AppViewName) => VoiceControlDescriptor[];
}

const VoiceCommandContext = createContext<VoiceCommandContextValue | undefined>(undefined);

const SILENCE_FINALIZE_MS = 1800;
const INITIAL_NO_SPEECH_MS = 9000;

export const VoiceCommandProvider: React.FC<{ children: React.ReactNode }> = ({ children }) => {
  const { announce } = useAccessibility();

  const [voiceStatus, setVoiceStatus] = useState<VoiceStatus>('idle');
  const [voiceError, setVoiceError] = useState<string | null>(null);
  const [lastTranscript, setLastTranscript] = useState<string>('');
  const [voiceFeedback, setVoiceFeedback] = useState<string | null>(null);

  const voiceStatusRef = useRef<VoiceStatus>('idle');
  voiceStatusRef.current = voiceStatus;

  const recognitionRef = useRef<any>(null);
  const isStartingRef = useRef<boolean>(false);
  const hasDispatchedTurnRef = useRef<boolean>(false);
  const accumulatedFinalsRef = useRef<string[]>([]);
  const latestInterimRef = useRef<string>('');
  const silenceTimerRef = useRef<ReturnType<typeof setTimeout> | null>(null);
  const noSpeechTimerRef = useRef<ReturnType<typeof setTimeout> | null>(null);

  const turnCounterRef = useRef<number>(0);
  const handlerRef = useRef<VoiceHandlerRegistration | null>(null);
  const controlsRegistryRef = useRef<Map<string, VoiceControlDescriptor[]>>(new Map());
  const pendingClarificationRef = useRef<{
    candidates: VoiceControlDescriptor[];
    message: string;
  } | null>(null);
  const pendingClearHistoryConfirmRef = useRef<boolean>(false);

  const clearRecognitionTimers = useCallback(() => {
    if (silenceTimerRef.current) {
      clearTimeout(silenceTimerRef.current);
      silenceTimerRef.current = null;
    }
    if (noSpeechTimerRef.current) {
      clearTimeout(noSpeechTimerRef.current);
      noSpeechTimerRef.current = null;
    }
  }, []);

  const registerVoiceHandler = useCallback((handler: VoiceHandlerRegistration) => {
    handlerRef.current = handler;
    return () => {
      if (handlerRef.current === handler) {
        handlerRef.current = null;
      }
    };
  }, []);

  const registerVoiceControls = useCallback(
    (ownerKey: string, controls: VoiceControlDescriptor[]) => {
      controlsRegistryRef.current.set(ownerKey, controls);
      return () => {
        controlsRegistryRef.current.delete(ownerKey);
      };
    },
    []
  );

  const getRegisteredControls = useCallback((view?: AppViewName): VoiceControlDescriptor[] => {
    const all: VoiceControlDescriptor[] = [];
    controlsRegistryRef.current.forEach((list) => {
      for (const c of list) {
        if (!view || c.currentView === view || c.currentView === 'GLOBAL') {
          all.push(c);
        }
      }
    });
    return all;
  }, []);

  const clearVoiceFeedback = useCallback(() => {
    setVoiceFeedback(null);
    setVoiceError(null);
  }, []);

  const logTrace = useCallback((payload: Record<string, any>) => {
    if ((import.meta as any).env?.DEV) {
      console.debug('[AccessPay RealMic Trace]', payload);
    }
  }, []);

  const processVoiceTranscript = useCallback(
    async (rawTranscript: string, source: VoiceInputSource = 'REAL_MIC') => {
      const trimmed = (rawTranscript || '').trim();
      if (!trimmed) {
        setVoiceStatus('idle');
        setVoiceError('Did not hear a command. Tap Speak and try again.');
        return null;
      }

      const turnNum = ++turnCounterRef.current;
      const voiceTurnId = `vt_${Date.now()}_${turnNum}`;
      setLastTranscript(trimmed);
      setVoiceError(null);
      setVoiceStatus('processing');

      const snapshot: VoiceViewSnapshot = handlerRef.current?.getContext() ?? {
        currentView: 'SHOP',
      };
      const registeredControls = getRegisteredControls();

      try {
        // 0. Resolve pending destructive Clear Recent Searches confirmation
        if (pendingClearHistoryConfirmRef.current) {
          pendingClearHistoryConfirmRef.current = false;
          if (/^(?:yes|yeah|yep|confirm|clear|clear all|clear all recent searches|okay|ok|do it)$/i.test(trimmed)) {
            await api.clearSearchHistory();
            const clearedMsg = 'All recent searches cleared.';
            await handlerRef.current?.onIntentResult(
              { action: 'RECENT_SEARCH_CLEARED', speech_response: clearedMsg },
              trimmed,
              source
            );
            setVoiceFeedback(clearedMsg);
            announce(clearedMsg);
            return { action: 'RECENT_SEARCH_CLEARED', message: clearedMsg, channel3_called: false };
          }
          const cancelHistoryMsg = 'Cancelled clearing recent searches.';
          setVoiceFeedback(cancelHistoryMsg);
          announce(cancelHistoryMsg);
          return { action: 'CLEAR_HISTORY_CANCELLED', message: cancelHistoryMsg, channel3_called: false };
        }

        // 1. Resolve pending ambiguous-control clarification if user answered with an ordinal
        if (pendingClarificationRef.current) {
          const pending = pendingClarificationRef.current;
          if (/^(?:cancel|never mind|stop)$/i.test(trimmed)) {
            pendingClarificationRef.current = null;
            const cancelNote = 'Cancelled.';
            setVoiceFeedback(cancelNote);
            announce(cancelNote);
            return { action: 'CLARIFICATION_CANCELLED', message: cancelNote };
          }
          const clarified = resolveAmbiguousOrdinal(trimmed, pending.candidates);
          if (clarified.status === 'matched') {
            pendingClarificationRef.current = null;
            await clarified.control.action();
            const ack =
              clarified.control.feedbackText || `Activated ${clarified.control.accessibleName}.`;
            setVoiceFeedback(ack);
            announce(ack);
            logTrace({
              source,
              voice_turn_id: voiceTurnId,
              raw_transcript: trimmed,
              current_view: snapshot.currentView,
              detected_action: 'CONTROL_ACTIVATED',
              control_id: clarified.control.id,
              control_type: clarified.control.type,
              accessible_name: clarified.control.accessibleName,
              resolved_entity_ids: clarified.control.entityId ? [clarified.control.entityId] : [],
              channel3_called: false,
            });
            return {
              action: 'CONTROL_ACTIVATED',
              control_id: clarified.control.id,
              control_type: clarified.control.type,
              accessible_name: clarified.control.accessibleName,
              entity_id: clarified.control.entityId,
              message: ack,
              channel3_called: false,
            };
          }
          if (clarified.status === 'disabled') {
            pendingClarificationRef.current = null;
            setVoiceFeedback(clarified.message);
            announce(clarified.message, true);
            return {
              action: 'CONTROL_DISABLED',
              control_id: clarified.control.id,
              message: clarified.message,
              channel3_called: false,
            };
          }
          // Otherwise clear stale pending clarification and evaluate fresh command
          pendingClarificationRef.current = null;
        }

        // 2. Context-sensitive discovery: "What can I say?" / "Help"
        if (isDiscoveryQuestion(trimmed)) {
          const helpMsg = buildDiscoveryHelp(snapshot.currentView, registeredControls);
          setVoiceFeedback(helpMsg);
          announce(helpMsg);
          logTrace({
            source,
            voice_turn_id: voiceTurnId,
            raw_transcript: trimmed,
            current_view: snapshot.currentView,
            detected_action: 'CONTROL_DISCOVERY',
            channel3_called: false,
          });
          return { action: 'CONTROL_DISCOVERY', message: helpMsg, channel3_called: false };
        }

        // 2a. Subscription Commerce voice routing (isolated from Channel3 one-time shopping)
        const subIntent = parseSubscriptionVoiceIntent(trimmed, snapshot.currentView);
        if (subIntent) {
          const subView = await handlerRef.current?.onIntentResult(
            { action: 'SUBSCRIPTION_VOICE_INTENT', subscriptionIntent: subIntent },
            trimmed,
            source
          );
          return { action: 'SUBSCRIPTION_VOICE_INTENT', view: subView, channel3_called: false };
        }

        // 2b. Search History voice commands (show, previous/last, ordinal, search again, save recent, clear)
        const historyIntent = parseHistoryVoiceIntent(trimmed);
        if (historyIntent) {
          if (historyIntent.kind === 'clear_history') {
            pendingClearHistoryConfirmRef.current = true;
            const confirmPrompt = 'Clear all recent searches?';
            setVoiceFeedback(confirmPrompt);
            announce(confirmPrompt, true);
            return {
              action: 'CLEAR_HISTORY_CONFIRMATION_REQUIRED',
              message: confirmPrompt,
              channel3_called: false,
            };
          }

          const history = await api.getSearchHistory(20);
          if (historyIntent.kind === 'show_history') {
            const top = history.slice(0, 5).map((h) => h.display_query);
            const msg =
              top.length > 0
                ? `Your recent searches: ${top.join(', ')}.`
                : 'No recent searches yet.';
            await handlerRef.current?.onIntentResult(
              { action: 'SHOW_RECENT_SEARCHES', history, speech_response: msg },
              trimmed,
              source
            );
            setVoiceFeedback(msg);
            announce(msg);
            return { action: 'SHOW_RECENT_SEARCHES', history, message: msg, channel3_called: false };
          }

          if (historyIntent.kind === 'save_last' || historyIntent.kind === 'save_ordinal') {
            const targetIdx = historyIntent.kind === 'save_last' ? 0 : historyIntent.index;
            const entry = history[targetIdx];
            if (!entry) {
              const noneMsg = 'No matching recent search to save.';
              setVoiceFeedback(noneMsg);
              announce(noneMsg, true);
              return { action: 'RECENT_SEARCH_NOT_FOUND', message: noneMsg, channel3_called: false };
            }
            const saved = await api.saveRecentSearch(entry.history_id);
            const savedMsg = `Saved "${entry.display_query}" to Saved Searches.`;
            await handlerRef.current?.onIntentResult(
              { action: 'RECENT_SEARCH_SAVED', saved_search: saved, speech_response: savedMsg },
              trimmed,
              source
            );
            setVoiceFeedback(savedMsg);
            announce(savedMsg);
            return { action: 'RECENT_SEARCH_SAVED', saved_search: saved, message: savedMsg, channel3_called: false };
          }

          let entryToRun = null;
          if (historyIntent.kind === 'run_last') {
            entryToRun = history[0] ?? null;
          } else if (historyIntent.kind === 'run_previous') {
            entryToRun = resolvePreviousSearchEntry(history, snapshot.activeSearchId);
          } else if (historyIntent.kind === 'run_ordinal') {
            entryToRun = history[historyIntent.index] ?? null;
          } else if (historyIntent.kind === 'run_query_again') {
            entryToRun = findMatchingHistoryEntry(history, historyIntent.queryFragment);
          }

          if (entryToRun) {
            const rerunRes = await api.runSearchHistory(entryToRun.history_id);
            await handlerRef.current?.onIntentResult(rerunRes, trimmed, source);
            const rerunMsg = rerunRes?.speech_response || `Showing results for ${entryToRun.display_query}.`;
            setVoiceFeedback(rerunMsg);
            logTrace({
              source,
              voice_turn_id: voiceTurnId,
              raw_transcript: trimmed,
              current_view: snapshot.currentView,
              active_search_id: rerunRes?.search_id ?? null,
              search_generation: rerunRes?.search_generation ?? null,
              detected_action: rerunRes?.action ?? 'SEARCH_RESULTS',
              channel3_called: Boolean(rerunRes?.channel3_called ?? true),
            });
            return rerunRes;
          } else if (historyIntent.kind !== 'run_query_again') {
            const missingMsg =
              historyIntent.kind === 'run_previous'
                ? 'There is no previous search before the current one.'
                : 'No matching recent search found.';
            setVoiceFeedback(missingMsg);
            announce(missingMsg, true);
            return { action: 'RECENT_SEARCH_NOT_FOUND', message: missingMsg, channel3_called: false };
          }
          // If run_query_again had no history match, fall through to fresh AI search
        }

        // 3. Generic Visible-Control Registry match (never includes sensitivePaymentAuth)
        const ctrlMatch = matchVisibleVoiceControl(
          trimmed,
          snapshot.currentView,
          registeredControls
        );
        if (ctrlMatch.status === 'ambiguous') {
          pendingClarificationRef.current = {
            candidates: ctrlMatch.candidates,
            message: ctrlMatch.message,
          };
          setVoiceFeedback(ctrlMatch.message);
          announce(ctrlMatch.message, true);
          logTrace({
            source,
            voice_turn_id: voiceTurnId,
            raw_transcript: trimmed,
            current_view: snapshot.currentView,
            detected_action: 'CLARIFICATION_NEEDED',
            candidate_ids: ctrlMatch.candidates.map((c) => c.id),
            channel3_called: false,
          });
          return {
            action: 'CLARIFICATION_NEEDED',
            needs_clarification: true,
            message: ctrlMatch.message,
            candidate_ids: ctrlMatch.candidates.map((c) => c.id),
            channel3_called: false,
          };
        }

        if (ctrlMatch.status === 'disabled') {
          setVoiceFeedback(ctrlMatch.message);
          announce(ctrlMatch.message, true);
          logTrace({
            source,
            voice_turn_id: voiceTurnId,
            raw_transcript: trimmed,
            current_view: snapshot.currentView,
            detected_action: 'CONTROL_DISABLED',
            control_id: ctrlMatch.control.id,
            channel3_called: false,
          });
          return {
            action: 'CONTROL_DISABLED',
            control_id: ctrlMatch.control.id,
            message: ctrlMatch.message,
            channel3_called: false,
          };
        }

        if (ctrlMatch.status === 'matched') {
          await ctrlMatch.control.action();
          const feedback =
            ctrlMatch.control.feedbackText || `${ctrlMatch.control.accessibleName}.`;
          setVoiceFeedback(feedback);
          announce(feedback);
          logTrace({
            source,
            voice_turn_id: voiceTurnId,
            raw_transcript: trimmed,
            current_view: snapshot.currentView,
            detected_action: 'CONTROL_ACTIVATED',
            control_id: ctrlMatch.control.id,
            control_type: ctrlMatch.control.type,
            accessible_name: ctrlMatch.control.accessibleName,
            resolved_entity_ids: ctrlMatch.control.entityId ? [ctrlMatch.control.entityId] : [],
            channel3_called: false,
          });
          return {
            action: 'CONTROL_ACTIVATED',
            control_id: ctrlMatch.control.id,
            control_type: ctrlMatch.control.type,
            accessible_name: ctrlMatch.control.accessibleName,
            entity_id: ctrlMatch.control.entityId,
            message: feedback,
            channel3_called: false,
          };
        }

        // 4. Semantic / AI / Backend Intent Router (search, filters, compare, quantity-to-N, order Q&A, strict confirmation)
        const res = await api.sendAiIntent(trimmed, {
          inputMode: 'voice',
          rawTranscript: trimmed,
          currentView: snapshot.currentView,
          activeSearchId: snapshot.activeSearchId ?? null,
          searchGeneration: snapshot.searchGeneration,
          visibleProductIds: snapshot.visibleProductIds,
          visibleSavedItemIds: snapshot.visibleSavedItemIds,
          visibleSavedSearchIds: snapshot.visibleSavedSearchIds,
          visibleOrderIds: snapshot.visibleOrderIds,
          selectedOrderId: snapshot.selectedOrderId ?? null,
          selectedSavedItemId: snapshot.selectedSavedItemId ?? null,
          visibleCartProductIds: snapshot.visibleCartProductIds,
        });

        let navigationDestination: string | null = null;
        if (handlerRef.current) {
          const dest = await handlerRef.current.onIntentResult(res, trimmed, source);
          if (dest) navigationDestination = dest;
        }

        const feedbackMsg = res?.speech_response || res?.message || '';
        if (feedbackMsg) {
          setVoiceFeedback(feedbackMsg);
        }

        const resolvedIds: string[] = [];
        if (Array.isArray(res?.referenced_product_ids)) {
          resolvedIds.push(...res.referenced_product_ids);
        }
        if (res?.saved_item_id) resolvedIds.push(res.saved_item_id);
        if (res?.order_id) resolvedIds.push(res.order_id);

        logTrace({
          source,
          voice_turn_id: voiceTurnId,
          raw_transcript: trimmed,
          normalized_transcript: res?.normalized_transcript ?? trimmed,
          current_view: snapshot.currentView,
          active_search_id: snapshot.activeSearchId ?? null,
          search_generation: res?.search_generation ?? snapshot.searchGeneration ?? null,
          visible_product_ids: snapshot.visibleProductIds ?? [],
          detected_action: res?.action ?? 'UNKNOWN',
          navigation_destination: navigationDestination,
          resolved_entity_ids: resolvedIds,
          channel3_called: Boolean(res?.channel3_called),
        });

        return res;
      } catch (err: any) {
        const errMsg = err?.message || 'Unable to process that voice command right now. Please try again.';
        setVoiceError(errMsg);
        announce(errMsg, true);
        logTrace({
          source,
          voice_turn_id: voiceTurnId,
          raw_transcript: trimmed,
          current_view: snapshot.currentView,
          error: errMsg,
        });
        return null;
      } finally {
        setVoiceStatus('idle');
      }
    },
    [announce, getRegisteredControls, logTrace]
  );

  const finalizeAccumulatedUtterance = useCallback(() => {
    clearRecognitionTimers();
    if (hasDispatchedTurnRef.current) return;
    hasDispatchedTurnRef.current = true;

    const parts = [...accumulatedFinalsRef.current];
    if (latestInterimRef.current.trim()) {
      parts.push(latestInterimRef.current.trim());
    }
    const combined = parts.join(' ').replace(/\s+/g, ' ').trim();
    accumulatedFinalsRef.current = [];
    latestInterimRef.current = '';

    try {
      recognitionRef.current?.stop();
    } catch {
      // Ignore if already stopped
    }

    if (!combined) {
      setVoiceStatus('idle');
      return;
    }

    void processVoiceTranscript(combined, 'REAL_MIC');
  }, [clearRecognitionTimers, processVoiceTranscript]);

  const stopListening = useCallback(() => {
    isStartingRef.current = false;
    finalizeAccumulatedUtterance();
  }, [finalizeAccumulatedUtterance]);

  const startListening = useCallback(async () => {
    if (voiceStatusRef.current === 'processing' || isStartingRef.current) {
      return;
    }

    if (typeof window !== 'undefined' && 'speechSynthesis' in window) {
      window.speechSynthesis.cancel();
    }

    const SpeechRecognitionCtor =
      typeof window !== 'undefined'
        ? (window as any).SpeechRecognition || (window as any).webkitSpeechRecognition
        : null;

    if (!SpeechRecognitionCtor) {
      const msg = 'Voice microphone is not supported in this browser. Type your search or tap a suggestion.';
      setVoiceError(msg);
      announce(msg, true);
      return;
    }

    // Check existing browser microphone permission before calling SpeechRecognition.start()
    // so denied permissions never loop native prompts, and never store fake permission state.
    if (typeof navigator !== 'undefined' && navigator.permissions?.query) {
      try {
        const permStatus = await navigator.permissions.query({
          name: 'microphone' as PermissionName,
        });
        if (permStatus.state === 'denied') {
          const deniedMsg =
            "Microphone access is blocked. Enable it in your browser's site settings to use voice.";
          setVoiceStatus('idle');
          setVoiceError(deniedMsg);
          announce(deniedMsg, true);
          return;
        }
      } catch {
        // Permissions API for 'microphone' is unsupported in some browsers; continue on user click.
      }
    }

    isStartingRef.current = true;
    hasDispatchedTurnRef.current = false;
    accumulatedFinalsRef.current = [];
    latestInterimRef.current = '';
    clearRecognitionTimers();
    setVoiceError(null);

    try {
      if (recognitionRef.current) {
        try {
          recognitionRef.current.onstart = null;
          recognitionRef.current.onresult = null;
          recognitionRef.current.onerror = null;
          recognitionRef.current.onend = null;
          recognitionRef.current.abort();
        } catch {
          // Ignore stale cleanup errors
        }
      }

      const recognition = new SpeechRecognitionCtor();
      recognition.lang = 'en-US';
      // Longer listening window: tolerate natural pauses and accumulate the complete utterance
      recognition.continuous = true;
      recognition.interimResults = true;
      recognition.maxAlternatives = 3;

      recognition.onstart = () => {
        isStartingRef.current = false;
        hasDispatchedTurnRef.current = false;
        setVoiceStatus('listening');
        noSpeechTimerRef.current = setTimeout(() => {
          if (
            accumulatedFinalsRef.current.length === 0 &&
            !latestInterimRef.current.trim() &&
            voiceStatusRef.current === 'listening'
          ) {
            try {
              recognition.stop();
            } catch {
              // ignore
            }
            setVoiceError('No speech detected. Tap Speak when ready and speak clearly.');
            setVoiceStatus('idle');
          }
        }, INITIAL_NO_SPEECH_MS);
      };

      recognition.onresult = (event: any) => {
        if (hasDispatchedTurnRef.current) return;
        const results = event?.results;
        if (!results || results.length === 0) return;

        if (noSpeechTimerRef.current) {
          clearTimeout(noSpeechTimerRef.current);
          noSpeechTimerRef.current = null;
        }

        const finals: string[] = [];
        let interim = '';
        for (let i = 0; i < results.length; i += 1) {
          const res = results[i];
          const text = String(res?.[0]?.transcript || '').trim();
          if (!text) continue;
          const isFinal = typeof res?.isFinal === 'boolean' ? res.isFinal : true;
          if (isFinal) {
            finals.push(text);
          } else {
            interim = interim ? `${interim} ${text}` : text;
          }
        }
        accumulatedFinalsRef.current = finals;
        latestInterimRef.current = interim;

        if (silenceTimerRef.current) {
          clearTimeout(silenceTimerRef.current);
        }
        silenceTimerRef.current = setTimeout(() => {
          finalizeAccumulatedUtterance();
        }, SILENCE_FINALIZE_MS);
      };

      recognition.onerror = (event: any) => {
        isStartingRef.current = false;
        clearRecognitionTimers();
        const code = event?.error || '';
        let msg = 'Voice input had an issue. Tap Speak to try again, or type your request.';
        if (code === 'not-allowed' || code === 'service-not-allowed') {
          msg = "Microphone access is blocked. Enable it in your browser's site settings to use voice.";
        } else if (code === 'no-speech') {
          msg = 'No speech detected. Tap Speak when ready and speak clearly.';
        } else if (code === 'audio-capture') {
          msg = 'No microphone device found. Connect a microphone or type your search.';
        } else if (code === 'aborted') {
          msg = '';
        }

        if (msg) {
          setVoiceError(msg);
          announce(msg, true);
        }
        if (voiceStatusRef.current !== 'processing') {
          setVoiceStatus('idle');
        }
      };

      recognition.onend = () => {
        isStartingRef.current = false;
        clearRecognitionTimers();
        if (!hasDispatchedTurnRef.current) {
          const hasText =
            accumulatedFinalsRef.current.length > 0 || Boolean(latestInterimRef.current.trim());
          if (hasText) {
            finalizeAccumulatedUtterance();
          } else if (voiceStatusRef.current === 'listening') {
            setVoiceStatus('idle');
          }
        }
      };

      recognitionRef.current = recognition;
      recognition.start();
    } catch {
      isStartingRef.current = false;
      clearRecognitionTimers();
      setVoiceStatus('idle');
      setVoiceError('Could not start the microphone. Please check permissions or try again.');
    }
  }, [announce, clearRecognitionTimers, finalizeAccumulatedUtterance]);

  const toggleListening = useCallback(() => {
    if (voiceStatusRef.current === 'listening') {
      stopListening();
    } else if (voiceStatusRef.current === 'idle') {
      void startListening();
    }
  }, [startListening, stopListening]);

  // DEV helpers for automated verification & control-coverage inspection
  useEffect(() => {
    if ((import.meta as any).env?.DEV && typeof window !== 'undefined') {
      (window as any).__accesspaySimulateVoiceTranscript = (text: string) =>
        processVoiceTranscript(text, 'SIMULATED_VOICE');
      (window as any).__accesspayGetVoiceControls = (view?: AppViewName) =>
        getRegisteredControls(view).map(({ action, ...meta }) => ({
          ...meta,
          hasAction: typeof action === 'function',
        }));
      return () => {
        delete (window as any).__accesspaySimulateVoiceTranscript;
        delete (window as any).__accesspayGetVoiceControls;
      };
    }
    return undefined;
  }, [getRegisteredControls, processVoiceTranscript]);

  return (
    <VoiceCommandContext.Provider
      value={{
        voiceStatus,
        voiceError,
        lastTranscript,
        voiceFeedback,
        clearVoiceFeedback,
        startListening,
        stopListening,
        toggleListening,
        processVoiceTranscript,
        registerVoiceHandler,
        registerVoiceControls,
        getRegisteredControls,
      }}
    >
      {children}
    </VoiceCommandContext.Provider>
  );
};

export const useVoiceCommand = () => {
  const ctx = useContext(VoiceCommandContext);
  if (!ctx) throw new Error('useVoiceCommand must be used within VoiceCommandProvider');
  return ctx;
};

export function useRegisterVoiceControls(
  ownerKey: string,
  controls: VoiceControlDescriptor[],
  deps: React.DependencyList
) {
  const { registerVoiceControls } = useVoiceCommand();
  useEffect(() => {
    return registerVoiceControls(ownerKey, controls);
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [ownerKey, registerVoiceControls, ...deps]);
}
