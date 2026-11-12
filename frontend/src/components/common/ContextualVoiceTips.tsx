import React from 'react';
import { Mic, HelpCircle } from 'lucide-react';
import { useVoiceCommand } from '../../context/VoiceCommandContext';

interface ContextualVoiceTipsProps {
  title?: string;
  subtitle?: string;
  commands: string[];
  disabled?: boolean;
  showVoiceTipsButton?: boolean;
  onRunCommand?: (command: string) => void;
}

export const ContextualVoiceTips: React.FC<ContextualVoiceTipsProps> = ({
  title,
  subtitle,
  commands,
  disabled = false,
  showVoiceTipsButton = false,
  onRunCommand,
}) => {
  const { processVoiceTranscript, voiceStatus } = useVoiceCommand();
  const isBusy = disabled || voiceStatus === 'processing';

  const handleSelect = (cmd: string) => {
    if (isBusy) return;
    if (onRunCommand) {
      onRunCommand(cmd);
      return;
    }
    void processVoiceTranscript(cmd, 'COMMAND_CHIP');
  };

  return (
    <div
      style={{
        display: 'flex',
        flexDirection: 'column',
        gap: '8px',
        padding: '10px 14px',
        backgroundColor: 'rgba(15, 23, 42, 0.72)',
        border: '1px solid #1e293b',
        borderRadius: '14px',
      }}
      aria-label={title ? `${title} voice commands` : 'Suggested voice commands'}
    >
      {(title || subtitle) && (
        <div style={{ display: 'flex', alignItems: 'baseline', gap: '8px', flexWrap: 'wrap' }}>
          {title && (
            <span style={{ fontSize: '0.88rem', fontWeight: 700, color: '#e2e8f0' }}>
              {title}
            </span>
          )}
          {subtitle && (
            <span style={{ fontSize: '0.84rem', color: '#94a3b8' }}>
              {subtitle}
            </span>
          )}
        </div>
      )}

      <div
        style={{
          display: 'flex',
          alignItems: 'center',
          gap: '8px',
          flexWrap: 'wrap',
        }}
      >
        <span
          style={{
            display: 'inline-flex',
            alignItems: 'center',
            gap: '5px',
            fontSize: '0.8rem',
            fontWeight: 700,
            color: '#94a3b8',
            whiteSpace: 'nowrap',
          }}
        >
          <Mic size={13} color="#38bdf8" aria-hidden="true" />
          <span>Try saying:</span>
        </span>

        {commands.slice(0, 4).map((cmd) => (
          <button
            key={cmd}
            type="button"
            disabled={isBusy}
            onClick={() => handleSelect(cmd)}
            style={{
              backgroundColor: '#182235',
              border: '1px solid #24324d',
              color: '#cbd5e1',
              padding: '5px 11px',
              borderRadius: '999px',
              fontSize: '0.8rem',
              fontWeight: 500,
              minHeight: '32px',
              minWidth: 'auto',
              whiteSpace: 'nowrap',
            }}
          >
            {cmd}
          </button>
        ))}

        {showVoiceTipsButton && (
          <button
            type="button"
            disabled={isBusy}
            onClick={() => handleSelect('What can I say?')}
            aria-label="Voice Tips"
            style={{
              backgroundColor: 'transparent',
              border: '1px solid #334155',
              color: '#94a3b8',
              padding: '5px 10px',
              borderRadius: '999px',
              fontSize: '0.78rem',
              fontWeight: 600,
              minHeight: '32px',
              minWidth: 'auto',
              whiteSpace: 'nowrap',
            }}
          >
            <HelpCircle size={13} aria-hidden="true" />
            <span>Voice Tips</span>
          </button>
        )}
      </div>
    </div>
  );
};

