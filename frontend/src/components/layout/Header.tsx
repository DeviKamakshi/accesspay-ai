import React, { useMemo } from 'react';
import { Mic, Loader2, ShieldCheck, ShoppingCart } from 'lucide-react';
import { useVoiceCommand, useRegisterVoiceControls } from '../../context/VoiceCommandContext';
import { VoiceControlDescriptor } from '../../utils/voiceControlMatcher';

export type PrimaryTab = 'shop' | 'saved' | 'orders' | 'cart';

interface HeaderProps {
  activeTab?: PrimaryTab;
  onSelectTab?: (tab: PrimaryTab) => void;
  savedCount?: number;
  cartCount?: number;
}

export const Header: React.FC<HeaderProps> = ({
  activeTab = 'shop',
  onSelectTab,
  savedCount = 0,
  cartCount = 0,
}) => {
  const { voiceStatus, toggleListening } = useVoiceCommand();

  const navTabs = useMemo(
    () =>
      [
        { id: 'shop' as const, name: 'Shop', label: 'Shop', aliases: ['shop', 'shopping', 'home', 'go back to shop', 'back to shop'] },
        {
          id: 'saved' as const,
          name: 'Saved',
          label: savedCount > 0 ? `Saved (${savedCount})` : 'Saved',
          aliases: ['saved', 'saved items', 'show saved'],
        },
        { id: 'orders' as const, name: 'Orders', label: 'Orders', aliases: ['orders', 'order history', 'go to my orders', 'my orders'] },
        {
          id: 'cart' as const,
          name: 'Cart',
          label: cartCount > 0 ? `Cart (${cartCount})` : 'Cart',
          aliases: ['cart', 'shopping cart', 'my cart', 'show my cart', 'bag'],
          icon: ShoppingCart,
        },
      ],
    [savedCount, cartCount]
  );

  const navControls = useMemo<VoiceControlDescriptor[]>(() => {
    if (!onSelectTab) return [];
    return navTabs.map((tab, idx) => ({
      id: `nav-tab-${tab.id}`,
      type: 'tab',
      accessibleName: tab.name,
      aliases: tab.aliases,
      entityIndex: idx,
      currentView: 'GLOBAL',
      enabled: true,
      feedbackText: `Opening ${tab.name}.`,
      action: () => onSelectTab(tab.id),
    }));
  }, [navTabs, onSelectTab]);

  useRegisterVoiceControls('header-nav', navControls, [navControls]);

  const isListening = voiceStatus === 'listening';
  const isProcessing = voiceStatus === 'processing';

  const speakLabel = isListening
    ? 'Listening...'
    : isProcessing
    ? 'Processing...'
    : 'Speak';

  return (
    <header
      style={{
        backgroundColor: '#0a0f1d',
        borderBottom: '1px solid #1e293b',
        padding: '16px 24px',
        position: 'sticky',
        top: 0,
        zIndex: 40,
      }}
      aria-label="AccessPay AI Voice-First Header"
    >
      <div
        style={{
          display: 'flex',
          flexWrap: 'wrap',
          alignItems: 'center',
          justifyContent: 'space-between',
          maxWidth: '1120px',
          margin: '0 auto',
          gap: '14px',
        }}
      >
        {/* Brand Identity */}
        <div style={{ display: 'flex', alignItems: 'center', gap: '12px' }}>
          <div
            style={{
              width: '44px',
              height: '44px',
              borderRadius: '12px',
              backgroundColor: '#0284c7',
              display: 'flex',
              alignItems: 'center',
              justifyContent: 'center',
              boxShadow: '0 0 20px rgba(2, 132, 199, 0.4)',
            }}
          >
            <ShieldCheck size={24} color="#ffffff" />
          </div>
          <div>
            <h1 style={{ fontSize: '1.35rem', fontWeight: 900, letterSpacing: '-0.02em', color: '#f8fafc', margin: 0 }}>
              AccessPay <span style={{ color: '#38bdf8' }}>AI</span>
            </h1>
            <p style={{ fontSize: '0.84rem', color: '#94a3b8', margin: '2px 0 0', fontWeight: 500 }}>
              Voice-First Shopping &bull; <strong style={{ color: '#f8fafc' }}>You make the decisions.</strong>
            </p>
          </div>
        </div>

        {/* Clean Primary View Navigation: Shop | Saved | Orders | Cart */}
        {onSelectTab && (
          <nav
            role="navigation"
            aria-label="Primary Views"
            style={{
              display: 'flex',
              flexWrap: 'wrap',
              gap: '6px',
              backgroundColor: '#111827',
              padding: '6px',
              borderRadius: '14px',
              border: '1px solid #1e293b',
            }}
          >
            {navTabs.map((tab) => {
              const isActive = activeTab === tab.id;
              return (
                <button
                  key={tab.id}
                  type="button"
                  onClick={() => onSelectTab(tab.id)}
                  aria-current={isActive ? 'page' : undefined}
                  style={{
                    backgroundColor: isActive ? '#0284c7' : 'transparent',
                    color: isActive ? '#ffffff' : '#cbd5e1',
                    border: 'none',
                    borderRadius: '10px',
                    padding: '10px 16px',
                    fontSize: '0.94rem',
                    fontWeight: isActive ? 800 : 600,
                    minHeight: '44px',
                    display: 'inline-flex',
                    alignItems: 'center',
                    gap: '6px',
                  }}
                >
                  {tab.icon && <tab.icon size={16} />}
                  <span>{tab.label}</span>
                </button>
              );
            })}
          </nav>
        )}

        {/* Persistent Global Voice Command Button */}
        <button
          type="button"
          onClick={toggleListening}
          disabled={isProcessing}
          data-testid="global-speak-button"
          aria-pressed={isListening}
          aria-label={
            isListening
              ? 'Stop voice listening'
              : isProcessing
              ? 'Processing voice command'
              : 'Speak a voice command'
          }
          style={{
            backgroundColor: isListening ? '#dc2626' : isProcessing ? '#1e293b' : '#0284c7',
            color: '#ffffff',
            border: isListening ? '2px solid #fca5a5' : '2px solid #38bdf8',
            borderRadius: '14px',
            padding: '12px 22px',
            fontSize: '1rem',
            fontWeight: 800,
            minHeight: '48px',
            minWidth: '144px',
            display: 'inline-flex',
            alignItems: 'center',
            justifyContent: 'center',
            gap: '8px',
            boxShadow: isListening
              ? '0 0 0 6px rgba(220, 38, 38, 0.35)'
              : '0 4px 16px rgba(2, 132, 199, 0.38)',
          }}
        >
          {isProcessing ? <Loader2 size={18} /> : <Mic size={18} />}
          <span>{speakLabel}</span>
        </button>
      </div>
    </header>
  );
};
