import React, { createContext, useContext, useState, useEffect, useCallback } from 'react';
import { AccessibilityPreferences, AccessibilityMode } from '../types';
import { api } from '../services/api';

interface AccessibilityContextType {
  preferences: AccessibilityPreferences;
  currentMode: AccessibilityMode;
  setMode: (mode: AccessibilityMode) => Promise<void>;
  updatePreferences: (updates: Partial<AccessibilityPreferences>) => Promise<void>;
  speak: (text: string) => void;
  announce: (text: string, assertive?: boolean) => void;
  announcement: { text: string; assertive: boolean };
}

const defaultPreferences: AccessibilityPreferences = {
  user_name: 'Alex',
  current_mode: 'VOICE',
  read_important_aloud: true,
  read_total_aloud: true,
  simplified_interface: false,
  one_action_per_screen: false,
  reduced_motion: false,
  extra_response_time: false,
  warn_subscriptions: true,
  always_show_total_cost: true,
  suggest_cheaper_alternatives: true,
  cheaper_alternative_threshold: 50.0,
  exact_price_confirmation: true,
  double_confirmation_threshold: 500.0,
  warn_quantity_greater_one: true,
  warn_shipping_exceeds: 15.0,
  switch_scan_speed_ms: 1800,
};

const AccessibilityContext = createContext<AccessibilityContextType | undefined>(undefined);

export const AccessibilityProvider: React.FC<{ children: React.ReactNode }> = ({ children }) => {
  const [preferences, setPreferences] = useState<AccessibilityPreferences>(defaultPreferences);
  const [announcement, setAnnouncement] = useState<{ text: string; assertive: boolean }>({ text: '', assertive: false });

  useEffect(() => {
    api.getPreferences()
      .then((loaded) => setPreferences({ ...loaded, current_mode: 'VOICE' }))
      .catch((err) => console.warn('Could not load preferences from backend:', err));
  }, []);

  const speak = useCallback((text: string) => {
    if (typeof window !== 'undefined' && 'speechSynthesis' in window) {
      window.speechSynthesis.cancel();
      const clean = text.replace(/\$/g, ' dollars ').replace(/\//g, ' per ');
      const utterance = new SpeechSynthesisUtterance(clean);
      utterance.rate = 1.0;
      utterance.pitch = 1.0;
      window.speechSynthesis.speak(utterance);
    }
  }, []);

  const announce = useCallback(
    (text: string, assertive = false) => {
      setAnnouncement({ text, assertive });
      if (preferences.read_important_aloud) {
        speak(text);
      }
    },
    [preferences.read_important_aloud, speak]
  );

  const setMode = useCallback(async (_mode: AccessibilityMode) => {
    setPreferences((prev) => ({ ...prev, current_mode: 'VOICE' }));
  }, []);

  const updatePreferences = async (updates: Partial<AccessibilityPreferences>) => {
    try {
      const updated = await api.updatePreferences({ ...updates, current_mode: 'VOICE' });
      setPreferences(updated);
    } catch (err) {
      console.error(err);
      setPreferences((prev) => ({ ...prev, ...updates, current_mode: 'VOICE' }));
    }
  };

  return (
    <AccessibilityContext.Provider
      value={{
        preferences,
        currentMode: 'VOICE',
        setMode,
        updatePreferences,
        speak,
        announce,
        announcement,
      }}
    >
      <div className={preferences.reduced_motion ? 'reduced-motion-active' : ''}>
        {children}
      </div>
    </AccessibilityContext.Provider>
  );
};

export const useAccessibility = () => {
  const context = useContext(AccessibilityContext);
  if (!context) throw new Error('useAccessibility must be used within AccessibilityProvider');
  return context;
};
