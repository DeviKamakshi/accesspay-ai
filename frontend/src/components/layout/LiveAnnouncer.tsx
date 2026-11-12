import React from 'react';
import { useAccessibility } from '../../context/AccessibilityContext';

export const LiveAnnouncer: React.FC = () => {
  const { announcement } = useAccessibility();

  return (
    <div className="sr-only" aria-hidden="false">
      {/* Polite region for standard status changes */}
      <div
        role="status"
        aria-live="polite"
        aria-atomic="true"
        id="accessible-polite-announcer"
      >
        {!announcement.assertive ? announcement.text : ''}
      </div>

      {/* Assertive region for warnings, errors, and invalidations */}
      <div
        role="alert"
        aria-live="assertive"
        aria-atomic="true"
        id="accessible-alert-announcer"
      >
        {announcement.assertive ? announcement.text : ''}
      </div>
    </div>
  );
};
