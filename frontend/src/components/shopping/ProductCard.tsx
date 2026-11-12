import React, { useState } from 'react';
import { Product } from '../../types';
import { Check, Layers, Package, Bookmark } from 'lucide-react';

interface ProductCardProps {
  product: Product;
  onCompare: (product: Product) => void;
  onSelect: (product: Product) => void;
  onSave?: (product: Product) => void;
  isCompared?: boolean;
  isSelected?: boolean;
  isSaved?: boolean;
}

export const ProductCard: React.FC<ProductCardProps> = ({
  product,
  onCompare,
  onSelect,
  onSave,
  isCompared = false,
  isSelected = false,
  isSaved = false,
}) => {
  const [imageError, setImageError] = useState(false);

  // Show only 2–3 useful features from actual product data
  const features = (product.documented_accessibility_features || []).slice(0, 3);
  const hasImage = Boolean(product.image_url && product.image_url.trim()) && !imageError;
  const altText = product.image_alt || `${product.title} from ${product.merchant}`;

  return (
    <article
      className="app-card"
      style={{
        display: 'flex',
        flexDirection: 'column',
        justifyContent: 'space-between',
        borderRadius: '18px',
        backgroundColor: '#182235',
        border: isSelected
          ? '3px solid #10b981'
          : isCompared
          ? '3px solid #38bdf8'
          : '1px solid #24324d',
        overflow: 'hidden',
        padding: '0',
      }}
      aria-label={`${product.title}, $${product.price.toFixed(2)}, From ${product.merchant}`}
    >
      {/* 1. Product Image or Accessible Placeholder */}
      <div
        style={{
          height: '190px',
          width: '100%',
          overflow: 'hidden',
          backgroundColor: '#0a0f1d',
          position: 'relative',
          display: 'flex',
          alignItems: 'center',
          justifyContent: 'center',
        }}
      >
        {hasImage ? (
          <img
            src={product.image_url}
            alt={altText}
            onError={() => setImageError(true)}
            style={{ width: '100%', height: '100%', objectFit: 'cover' }}
            loading="lazy"
          />
        ) : (
          <div
            role="img"
            aria-label={altText}
            style={{
              display: 'flex',
              flexDirection: 'column',
              alignItems: 'center',
              justifyContent: 'center',
              color: '#64748b',
              padding: '16px',
              textAlign: 'center',
            }}
          >
            <Package size={40} color="#38bdf8" style={{ marginBottom: '8px', opacity: 0.7 }} />
            <span style={{ fontSize: '0.88rem', color: '#94a3b8', fontWeight: 600 }}>
              {product.title}
            </span>
          </div>
        )}

        {product.ranking_badge && (
          <span
            style={{
              position: 'absolute',
              top: '12px',
              left: '12px',
              backgroundColor: '#0a0f1d',
              border: '1px solid #38bdf8',
              color: '#38bdf8',
              fontSize: '0.75rem',
              fontWeight: 800,
              padding: '4px 10px',
              borderRadius: '999px',
              letterSpacing: '0.04em',
            }}
          >
            {product.ranking_badge}
          </span>
        )}
      </div>

      <div style={{ padding: '22px', display: 'flex', flexDirection: 'column', flex: 1, justifyContent: 'space-between' }}>
        <div>
          {/* 2. Product Name */}
          <h3 style={{ fontSize: '1.2rem', fontWeight: 800, color: '#f8fafc', marginBottom: '6px', lineHeight: 1.3 }}>
            {product.title}
          </h3>

          {/* 3. Merchant */}
          <p style={{ fontSize: '0.92rem', color: '#94a3b8', marginBottom: '12px', fontWeight: 600 }}>
            From: <span style={{ color: '#cbd5e1' }}>{product.merchant}</span>
          </p>

          {/* 4. Price */}
          <div style={{ fontSize: '1.65rem', fontWeight: 900, color: '#38bdf8', marginBottom: '16px' }}>
            ${product.price.toFixed(2)}
            {product.subscription_period && (
              <span style={{ fontSize: '0.95rem', color: '#94a3b8', fontWeight: 600, marginLeft: '4px' }}>
                / {product.subscription_period}
              </span>
            )}
          </div>

          {/* 5. 2–3 Useful Features */}
          {features.length > 0 && (
            <ul style={{ listStyle: 'disc', paddingLeft: '20px', color: '#cbd5e1', fontSize: '0.95rem', lineHeight: 1.55, marginBottom: '22px' }}>
              {features.map((feat, idx) => (
                <li key={idx} style={{ marginBottom: '6px' }}>
                  {feat}
                </li>
              ))}
            </ul>
          )}
        </div>

        {/* 6. Actions: Compare & Select */}
        <div style={{ display: 'flex', gap: '10px', paddingTop: '14px', borderTop: '1px solid #24324d' }}>
          <button
            type="button"
            onClick={() => onCompare(product)}
            style={{
              flex: 1,
              backgroundColor: isCompared ? '#1e293b' : 'transparent',
              border: isCompared ? '2px solid #38bdf8' : '1px solid #3b5075',
              color: isCompared ? '#38bdf8' : '#cbd5e1',
              fontWeight: 700,
              padding: '12px 14px',
              borderRadius: '12px',
              display: 'inline-flex',
              alignItems: 'center',
              justifyContent: 'center',
              gap: '6px',
            }}
            aria-label={`Compare ${product.title}`}
          >
            <Layers size={18} />
            <span>{isCompared ? 'Comparing' : 'Compare'}</span>
          </button>

          <button
            type="button"
            onClick={() => onSelect(product)}
            style={{
              flex: 1.4,
              backgroundColor: isSelected ? '#10b981' : '#0284c7',
              color: '#ffffff',
              fontWeight: 700,
              padding: '12px 18px',
              borderRadius: '12px',
              border: 'none',
              display: 'inline-flex',
              alignItems: 'center',
              justifyContent: 'center',
              gap: '6px',
            }}
            aria-label={`Select ${product.title} for $${product.price.toFixed(2)}`}
          >
            <Check size={18} />
            <span>{isSelected ? 'Selected' : 'Select'}</span>
          </button>
          {onSave && (
            <button
              type="button"
              onClick={() => onSave(product)}
              aria-pressed={Boolean(isSaved)}
              aria-label={isSaved ? `${product.title} saved` : `Save ${product.title}`}
              style={{
                backgroundColor: isSaved ? '#064e3b' : '#1e293b',
                color: isSaved ? '#6ee7b7' : '#e2e8f0',
                fontWeight: 700,
                padding: '12px 14px',
                borderRadius: '12px',
                border: isSaved ? '2px solid #10b981' : '1px solid #475569',
                display: 'inline-flex',
                alignItems: 'center',
                justifyContent: 'center',
                gap: '6px',
              }}
            >
              <Bookmark size={16} />
              <span>{isSaved ? 'Saved' : 'Save'}</span>
            </button>
          )}
        </div>
      </div>
    </article>
  );
};
