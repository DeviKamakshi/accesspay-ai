import React from 'react';
import { Repeat, ShieldAlert, ArrowRight, CheckCircle2 } from 'lucide-react';
import { SubscriptionOffer } from '../../types';

interface SubscriptionCardProps {
  offer: SubscriptionOffer;
  index?: number;
  isSelected?: boolean;
  onSelect: (offer: SubscriptionOffer) => void;
  onReview: (offer: SubscriptionOffer) => void;
}

export const SubscriptionCard: React.FC<SubscriptionCardProps> = ({
  offer,
  index,
  isSelected = false,
  onSelect,
  onReview,
}) => {
  const unitLabel = offer.billing_frequency === 'yearly' ? 'YEAR' : 'MONTH';

  return (
    <article
      className={`rounded-2xl border p-5 transition-all bg-slate-900/80 ${
        isSelected
          ? 'border-amber-400/70 ring-2 ring-amber-400/20'
          : 'border-slate-700/80 hover:border-amber-400/50'
      }`}
      data-testid={`subscription-card-${offer.id}`}
    >
      <div className="flex flex-wrap items-center justify-between gap-2 mb-3">
        <div className="flex flex-wrap items-center gap-2">
          {typeof index === 'number' && (
            <span className="text-xs font-semibold px-2 py-0.5 rounded-md bg-slate-800 text-slate-300 border border-slate-700">
              #{index + 1}
            </span>
          )}
          <span className="inline-flex items-center gap-1.5 text-xs font-bold uppercase tracking-wider px-2.5 py-1 rounded-full bg-amber-500/15 text-amber-300 border border-amber-400/40">
            <Repeat className="w-3.5 h-3.5" aria-hidden="true" />
            SUBSCRIPTION • DEMO CATALOG
          </span>
        </div>

        <span className="text-xs font-semibold px-2.5 py-1 rounded-full bg-slate-800 text-slate-300 border border-slate-700">
          {offer.provider}
        </span>
      </div>

      <h3 className="text-lg font-bold text-slate-100 leading-snug">{offer.name}</h3>
      <p className="text-sm text-slate-400 mt-1.5 leading-relaxed">{offer.description}</p>

      <div className="mt-4 rounded-xl bg-amber-950/35 border border-amber-500/35 p-3.5">
        <div className="flex flex-wrap items-baseline justify-between gap-2">
          <div>
            <p className="text-[11px] font-bold uppercase tracking-wider text-amber-300 flex items-center gap-1.5">
              <ShieldAlert className="w-3.5 h-3.5" aria-hidden="true" />
              RECURRING SUBSCRIPTION
            </p>
            <p className="text-2xl font-extrabold text-white mt-0.5">
              ${offer.recurring_amount.toFixed(2)}{' '}
              <span className="text-sm font-bold text-amber-300">/ {unitLabel}</span>
            </p>
          </div>
          <div className="text-right">
            <p className="text-xs text-slate-400">Due Today</p>
            <p className="text-base font-bold text-slate-100">${offer.amount_due_today.toFixed(2)}</p>
          </div>
        </div>

        <dl className="mt-3 pt-3 border-t border-amber-500/20 grid grid-cols-1 sm:grid-cols-2 gap-2 text-xs">
          <div>
            <dt className="text-slate-400">Billing Frequency</dt>
            <dd className="font-semibold text-slate-100 capitalize">{offer.billing_frequency}</dd>
          </div>
          <div>
            <dt className="text-slate-400">Free Trial</dt>
            <dd className="font-semibold text-slate-100">{offer.trial_period || 'None'}</dd>
          </div>
        </dl>
      </div>

      <p className="text-xs text-slate-400 mt-3 leading-relaxed">
        <span className="text-slate-300 font-medium">Renewal:</span> {offer.renewal_behavior}
      </p>

      <div className="mt-4 flex flex-wrap items-center gap-2.5">
        <button
          type="button"
          onClick={() => onSelect(offer)}
          className={`inline-flex items-center gap-1.5 px-3.5 py-2 rounded-xl text-xs font-semibold border transition-colors ${
            isSelected
              ? 'bg-amber-500/20 border-amber-400 text-amber-200'
              : 'bg-slate-800 border-slate-700 text-slate-200 hover:border-slate-500'
          }`}
        >
          {isSelected && <CheckCircle2 className="w-3.5 h-3.5" aria-hidden="true" />}
          {isSelected ? 'Selected' : 'Select Plan'}
        </button>

        <button
          type="button"
          onClick={() => onReview(offer)}
          className="flex-1 inline-flex items-center justify-center gap-1.5 px-4 py-2 rounded-xl text-xs font-bold bg-amber-400 hover:bg-amber-300 text-slate-950 transition-colors"
        >
          Review Subscription
          <ArrowRight className="w-3.5 h-3.5" aria-hidden="true" />
        </button>
      </div>
    </article>
  );
};

