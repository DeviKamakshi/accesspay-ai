import React, { useEffect, useState, useCallback, useMemo } from 'react';
import { SavedItem, SavedSearch, SearchHistoryEntry, Product } from '../../types';
import { api } from '../../services/api';
import { useAccessibility } from '../../context/AccessibilityContext';
import { useCart } from '../../context/CartContext';
import { useRegisterVoiceControls } from '../../context/VoiceCommandContext';
import { VoiceControlDescriptor } from '../../utils/voiceControlMatcher';
import { ContextualVoiceTips } from '../common/ContextualVoiceTips';
import {
  Bookmark,
  Search,
  ShoppingCart,
  Trash2,
  Play,
  ExternalLink,
  History,
  AlertTriangle,
} from 'lucide-react';

interface SavedViewProps {
  initialSubTab?: 'items' | 'searches';
  onReopenSearch: (searchResult: any) => void;
  onSavedChanged?: (savedProductIds: Set<string>) => void;
  selectedSavedItemId?: string | null;
  onSelectSavedItem?: (savedItemId: string | null) => void;
  onSubTabChange?: (subTab: 'items' | 'searches') => void;
  reloadNonce?: number;
}

export const SavedView: React.FC<SavedViewProps> = ({
  initialSubTab = 'items',
  onReopenSearch,
  onSavedChanged,
  selectedSavedItemId = null,
  onSelectSavedItem,
  onSubTabChange,
  reloadNonce = 0,
}) => {
  const { announce } = useAccessibility();
  const { refreshCart } = useCart();

  const [subTab, setSubTab] = useState<'items' | 'searches'>(initialSubTab);
  const [savedItems, setSavedItems] = useState<SavedItem[]>([]);
  const [savedSearches, setSavedSearches] = useState<SavedSearch[]>([]);
  const [searchHistory, setSearchHistory] = useState<SearchHistoryEntry[]>([]);
  const [loading, setLoading] = useState<boolean>(true);
  const [statusBanner, setStatusBanner] = useState<string | null>(null);
  const [priceNotice, setPriceNotice] = useState<string | null>(null);
  const [busyId, setBusyId] = useState<string | null>(null);
  const [confirmClearHistory, setConfirmClearHistory] = useState<boolean>(false);

  useEffect(() => {
    setSubTab(initialSubTab);
  }, [initialSubTab]);

  const loadAll = useCallback(async () => {
    setLoading(true);
    try {
      const [items, searches, history] = await Promise.all([
        api.getSavedItems(),
        api.getSavedSearches(),
        api.getSearchHistory(20),
      ]);
      setSavedItems(items);
      setSavedSearches(searches);
      setSearchHistory(history);
      onSavedChanged?.(new Set(items.map((it) => it.product_id)));
    } catch (err: any) {
      setStatusBanner(err?.message || 'Unable to load saved items right now.');
    } finally {
      setLoading(false);
    }
  }, [onSavedChanged]);

  useEffect(() => {
    loadAll();
  }, [loadAll, reloadNonce]);

  const handleAddSavedToCart = async (item: SavedItem) => {
    setBusyId(item.saved_item_id);
    setPriceNotice(null);
    setStatusBanner(null);
    try {
      const res = await api.addSavedItemToCart(item.saved_item_id);
      await refreshCart();
      if (res.price_changed) {
        const notice = `Price updated since saving: was $${res.price_at_save.toFixed(2)}, current price is $${res.current_price.toFixed(2)}. Added to your cart for review.`;
        setPriceNotice(notice);
        announce(notice, true);
      } else {
        const msg = res.message || `Added ${item.product_title} ($${res.current_price.toFixed(2)}) to your cart.`;
        setStatusBanner(msg);
        announce(msg);
      }
    } catch (err: any) {
      const errMsg = err?.message || 'Could not add saved item to cart.';
      setStatusBanner(errMsg);
      announce(errMsg, true);
    } finally {
      setBusyId(null);
    }
  };

  const handleAddAllToCart = async () => {
    if (savedItems.length === 0) return;
    setBusyId('add-all');
    setPriceNotice(null);
    setStatusBanner(null);
    try {
      let addedCount = 0;
      for (const item of savedItems) {
        await api.addSavedItemToCart(item.saved_item_id);
        addedCount += 1;
      }
      await refreshCart();
      const msg = `Added ${addedCount} saved item${addedCount === 1 ? '' : 's'} to your cart.`;
      setStatusBanner(msg);
      announce(msg);
    } catch (err: any) {
      const errMsg = err?.message || 'Could not add all saved items to cart.';
      setStatusBanner(errMsg);
      announce(errMsg, true);
    } finally {
      setBusyId(null);
    }
  };

  const handleRemoveSavedItem = async (item: SavedItem) => {
    setBusyId(item.saved_item_id);
    try {
      await api.removeSavedItem(item.saved_item_id);
      const next = savedItems.filter((x) => x.saved_item_id !== item.saved_item_id);
      setSavedItems(next);
      onSavedChanged?.(new Set(next.map((it) => it.product_id)));
      setStatusBanner(`Removed ${item.product_snapshot.title} from saved items.`);
      announce('Product removed from saved items.');
    } catch (err: any) {
      setStatusBanner(err?.message || 'Could not remove saved item.');
    } finally {
      setBusyId(null);
    }
  };

  const handleViewProductInShop = async (product: Product) => {
    setBusyId(product.id);
    try {
      const res = await api.searchProducts(product.title);
      onReopenSearch({
        ...res,
        action: 'SEARCH_RESULTS',
        display_query: product.title,
        message: `Showing saved product "${product.title}" in Shop.`,
      });
    } catch {
      onReopenSearch({
        action: 'SEARCH_RESULTS',
        products: [product],
        count: 1,
        has_more: false,
        total_candidates: 1,
        display_query: product.title,
        message: `Showing saved product "${product.title}".`,
      });
    } finally {
      setBusyId(null);
    }
  };

  const handleRunSavedSearch = async (saved: SavedSearch) => {
    setBusyId(saved.saved_search_id);
    setStatusBanner(null);
    try {
      const res = await api.runSavedSearch(saved.saved_search_id);
      announce('Search reopened.');
      onReopenSearch(res);
    } catch (err: any) {
      const msg = err?.message || 'Could not reopen saved search right now.';
      setStatusBanner(msg);
      announce(msg, true);
    } finally {
      setBusyId(null);
    }
  };

  const handleDeleteSavedSearch = async (saved: SavedSearch) => {
    setBusyId(saved.saved_search_id);
    try {
      await api.deleteSavedSearch(saved.saved_search_id);
      setSavedSearches((prev) => prev.filter((s) => s.saved_search_id !== saved.saved_search_id));
      setStatusBanner(`Deleted saved search "${saved.display_query}".`);
      announce('Saved search deleted.');
    } catch (err: any) {
      setStatusBanner(err?.message || 'Could not delete saved search.');
    } finally {
      setBusyId(null);
    }
  };

  const handleRunHistoryEntry = async (entry: SearchHistoryEntry) => {
    setBusyId(entry.history_id);
    try {
      const res = await api.runSearchHistory(entry.history_id);
      announce('Search reopened.');
      onReopenSearch(res);
    } catch (err: any) {
      setStatusBanner(err?.message || 'Could not rerun search.');
    } finally {
      setBusyId(null);
    }
  };

  const handleClearHistory = async () => {
    try {
      await api.clearSearchHistory();
      setSearchHistory([]);
      setConfirmClearHistory(false);
      announce('Recent searches cleared.');
    } catch {
      setStatusBanner('Could not clear recent searches.');
    }
  };

  const activeSavedView = subTab === 'searches' ? 'SAVED_SEARCHES' : 'SAVED_ITEMS';

  const savedControls = useMemo<VoiceControlDescriptor[]>(() => {
    const controls: VoiceControlDescriptor[] = [
      {
        id: 'saved-tab-items',
        type: 'tab',
        accessibleName: 'Items',
        aliases: ['items', 'saved items', 'open items', 'select items', 'show saved items'],
        currentView: activeSavedView,
        enabled: true,
        action: () => {
          setSubTab('items');
          onSubTabChange?.('items');
        },
      },
      {
        id: 'saved-tab-searches',
        type: 'tab',
        accessibleName: 'Searches',
        aliases: ['searches', 'saved searches', 'open searches', 'open saved searches', 'select searches', 'show saved searches'],
        currentView: activeSavedView,
        enabled: true,
        action: () => {
          setSubTab('searches');
          onSubTabChange?.('searches');
        },
      },
    ];

    if (subTab === 'items') {
      controls.push({
        id: 'saved-add-all-to-cart',
        type: 'button',
        accessibleName: 'Add All to Cart',
        aliases: ['add all to cart', 'add all', 'add all items to cart'],
        currentView: 'SAVED_ITEMS',
        enabled: savedItems.length > 0 && busyId !== 'add-all',
        disabledReason: 'No saved items to add to cart.',
        action: () => handleAddAllToCart(),
      });
      savedItems.forEach((item, idx) => {
        controls.push(
          {
            id: `saved-item-view-${item.saved_item_id}`,
            type: 'saved-item-action',
            accessibleName: 'View',
            aliases: ['view', 'view in shop', 'open', 'inspect'],
            currentView: 'SAVED_ITEMS',
            enabled: true,
            entityId: item.saved_item_id,
            entityTitle: item.product_title,
            entityIndex: idx,
            action: () => handleViewProductInShop(item.product_snapshot),
          },
          {
            id: `saved-item-add-${item.saved_item_id}`,
            type: 'saved-item-action',
            accessibleName: 'Add to Cart',
            aliases: ['add to cart', 'add item'],
            currentView: 'SAVED_ITEMS',
            enabled: busyId !== item.saved_item_id,
            disabledReason: 'Still updating that saved item.',
            entityId: item.saved_item_id,
            entityTitle: item.product_title,
            entityIndex: idx,
            action: () => handleAddSavedToCart(item),
          },
          {
            id: `saved-item-remove-${item.saved_item_id}`,
            type: 'saved-item-action',
            accessibleName: 'Remove',
            aliases: ['remove', 'delete', 'unsave', 'remove saved item', 'remove item'],
            currentView: 'SAVED_ITEMS',
            enabled: busyId !== item.saved_item_id,
            disabledReason: 'Still updating that saved item.',
            entityId: item.saved_item_id,
            entityTitle: item.product_title,
            entityIndex: idx,
            action: () => handleRemoveSavedItem(item),
          },
        );
      });
    } else {
      savedSearches.forEach((saved, idx) => {
        controls.push(
          {
            id: `saved-search-run-${saved.saved_search_id}`,
            type: 'saved-item-action',
            accessibleName: 'Run Again',
            aliases: ['run again', 'run', 'run search', 'open', 'reopen', 'search again'],
            currentView: 'SAVED_SEARCHES',
            enabled: busyId !== saved.saved_search_id,
            disabledReason: 'Still running that saved search.',
            entityId: saved.saved_search_id,
            entityTitle: saved.display_query,
            entityIndex: idx,
            action: () => handleRunSavedSearch(saved),
          },
          {
            id: `saved-search-delete-${saved.saved_search_id}`,
            type: 'saved-item-action',
            accessibleName: 'Delete',
            aliases: ['delete', 'remove', 'delete saved search', 'remove search'],
            currentView: 'SAVED_SEARCHES',
            enabled: busyId !== saved.saved_search_id,
            disabledReason: 'Still updating that saved search.',
            entityId: saved.saved_search_id,
            entityTitle: saved.display_query,
            entityIndex: idx,
            action: () => handleDeleteSavedSearch(saved),
          },
        );
      });

      controls.push({
        id: 'saved-clear-history',
        type: 'button',
        accessibleName: 'Clear History',
        aliases: ['clear history', 'clear search history'],
        currentView: 'SAVED_SEARCHES',
        enabled: searchHistory.length > 0,
        disabledReason: 'Search history is already empty.',
        action: () => handleClearHistory(),
      });
    }

    return controls;
  }, [activeSavedView, subTab, savedItems, savedSearches, searchHistory.length, busyId]);

  useRegisterVoiceControls('saved-view', savedControls, [savedControls]);

  return (
    <section
      aria-label="Saved Items and Saved Searches"
      style={{ maxWidth: '1120px', margin: '0 auto', padding: '8px 4px 48px' }}
    >
      <div
        style={{
          display: 'flex',
          flexWrap: 'wrap',
          justifyContent: 'space-between',
          alignItems: 'center',
          gap: '16px',
          marginBottom: '24px',
        }}
      >
        <div>
          <div style={{ display: 'flex', alignItems: 'center', gap: '10px' }}>
            <Bookmark size={24} color="#38bdf8" aria-hidden="true" />
            <h2 style={{ fontSize: '1.75rem', fontWeight: 800, color: '#f8fafc', margin: 0 }}>
              Saved
            </h2>
          </div>
          <p style={{ color: '#94a3b8', marginTop: '4px', fontSize: '0.98rem', marginBottom: 0 }}>
            Products and searches you want to revisit.
          </p>
        </div>

        <div
          role="tablist"
          aria-label="Saved view sections"
          style={{
            display: 'flex',
            gap: '8px',
            backgroundColor: '#111827',
            padding: '6px',
            borderRadius: '14px',
            border: '2px solid #334155',
          }}
        >
          <button
            type="button"
            role="tab"
            aria-selected={subTab === 'items'}
            onClick={() => {
              setSubTab('items');
              onSubTabChange?.('items');
            }}
            style={{
              padding: '10px 18px',
              borderRadius: '10px',
              border: 'none',
              fontWeight: 700,
              backgroundColor: subTab === 'items' ? '#0284c7' : 'transparent',
              color: subTab === 'items' ? '#ffffff' : '#cbd5e1',
              display: 'inline-flex',
              alignItems: 'center',
              gap: '8px',
            }}
          >
            <Bookmark size={16} />
            <span>Items ({savedItems.length})</span>
          </button>
          <button
            type="button"
            role="tab"
            aria-selected={subTab === 'searches'}
            onClick={() => {
              setSubTab('searches');
              onSubTabChange?.('searches');
            }}
            style={{
              padding: '10px 18px',
              borderRadius: '10px',
              border: 'none',
              fontWeight: 700,
              backgroundColor: subTab === 'searches' ? '#0284c7' : 'transparent',
              color: subTab === 'searches' ? '#ffffff' : '#cbd5e1',
              display: 'inline-flex',
              alignItems: 'center',
              gap: '8px',
            }}
          >
            <Search size={16} />
            <span>Searches ({savedSearches.length})</span>
          </button>
          {subTab === 'items' && savedItems.length > 0 && (
            <button
              type="button"
              disabled={busyId === 'add-all'}
              onClick={handleAddAllToCart}
              style={{
                backgroundColor: '#0284c7',
                color: '#ffffff',
                border: 'none',
                borderRadius: '10px',
                padding: '8px 14px',
                fontWeight: 700,
                fontSize: '0.9rem',
                display: 'inline-flex',
                alignItems: 'center',
                gap: '6px',
                cursor: busyId === 'add-all' ? 'not-allowed' : 'pointer',
              }}
            >
              <ShoppingCart size={15} aria-hidden="true" />
              <span>Add All to Cart</span>
            </button>
          )}
        </div>
      </div>

      {subTab === 'items' && savedItems.length > 0 && (
        <div style={{ marginBottom: '16px' }}>
          <ContextualVoiceTips
            commands={[
              'Open the second item',
              'Add the first item to cart',
              'Add all to cart',
              'Show saved searches',
            ]}
          />
        </div>
      )}

      {subTab === 'searches' && (
        <div style={{ marginBottom: '16px' }}>
          <ContextualVoiceTips
            subtitle="Re-run saved searches with current products and prices."
            commands={[
              'Run the first search',
              'Delete the second search',
              'Show saved items',
            ]}
          />
        </div>
      )}

      {priceNotice && (
        <div
          role="alert"
          aria-live="assertive"
          style={{
            backgroundColor: '#451a03',
            border: '2px solid #f59e0b',
            color: '#fef3c7',
            borderRadius: '14px',
            padding: '14px 18px',
            marginBottom: '18px',
            display: 'flex',
            alignItems: 'center',
            gap: '10px',
            fontWeight: 600,
          }}
        >
          <AlertTriangle size={20} color="#fbbf24" />
          <span>{priceNotice}</span>
        </div>
      )}

      {statusBanner && (
        <div
          role="status"
          aria-live="polite"
          style={{
            backgroundColor: '#111827',
            border: '2px solid #38bdf8',
            color: '#e0f2fe',
            borderRadius: '14px',
            padding: '12px 18px',
            marginBottom: '18px',
            fontWeight: 600,
          }}
        >
          {statusBanner}
        </div>
      )}

      {loading ? (
        <div
          style={{
            backgroundColor: '#111827',
            borderRadius: '16px',
            padding: '32px',
            textAlign: 'center',
            color: '#94a3b8',
            border: '2px solid #1e293b',
          }}
        >
          Loading saved items...
        </div>
      ) : subTab === 'items' ? (
        savedItems.length === 0 ? (
          <div
            style={{
              backgroundColor: '#111827',
              borderRadius: '16px',
              padding: '28px 24px',
              textAlign: 'center',
              border: '1px solid #1e293b',
              color: '#cbd5e1',
            }}
          >
            <p style={{ fontSize: '1.05rem', fontWeight: 700, color: '#f8fafc', margin: '0 0 6px' }}>
              Nothing saved yet.
            </p>
            <p style={{ color: '#94a3b8', margin: 0, fontSize: '0.92rem' }}>
              Try saying: &ldquo;Save the first one&rdquo; while shopping.
            </p>
          </div>
        ) : (
          <div
            style={{
              display: 'grid',
              gridTemplateColumns: 'repeat(auto-fill, minmax(300px, 1fr))',
              gap: '20px',
            }}
          >
            {savedItems.map((item) => {
              const p = item.product_snapshot;
              const isBusy = busyId === item.saved_item_id || busyId === p.id;
              const isFocused = selectedSavedItemId === item.saved_item_id;
              return (
                <article
                  key={item.saved_item_id}
                  data-saved-item-id={item.saved_item_id}
                  onClick={() => onSelectSavedItem?.(item.saved_item_id)}
                  style={{
                    backgroundColor: '#111827',
                    border: isFocused ? '2px solid #38bdf8' : '2px solid #334155',
                    borderRadius: '18px',
                    padding: '18px',
                    display: 'flex',
                    flexDirection: 'column',
                    gap: '12px',
                    boxShadow: isFocused ? '0 0 0 4px rgba(56, 189, 248, 0.2)' : 'none',
                  }}
                >
                  <div style={{ display: 'flex', gap: '14px', alignItems: 'center' }}>
                    {item.image_url || p.image_url ? (
                      <img
                        src={item.image_url || p.image_url}
                        alt={p.image_alt || p.title}
                        style={{
                          width: '72px',
                          height: '72px',
                          objectFit: 'contain',
                          borderRadius: '10px',
                          backgroundColor: '#ffffff',
                          padding: '4px',
                          flexShrink: 0,
                        }}
                      />
                    ) : null}
                    <div style={{ flex: 1, minWidth: 0 }}>
                      <h3
                        style={{
                          fontSize: '1.05rem',
                          fontWeight: 700,
                          color: '#f8fafc',
                          margin: '0 0 4px',
                        }}
                      >
                        {p.title}
                      </h3>
                      <div style={{ color: '#94a3b8', fontSize: '0.9rem' }}>
                        {item.merchant}
                      </div>
                      <div
                        style={{
                          color: '#38bdf8',
                          fontWeight: 800,
                          fontSize: '1.2rem',
                          marginTop: '4px',
                        }}
                      >
                        ${item.price_at_save.toFixed(2)}
                      </div>
                    </div>
                  </div>

                  {isFocused && (
                    <div
                      data-testid="saved-item-details"
                      style={{
                        backgroundColor: '#0f172a',
                        border: '1px solid #334155',
                        borderRadius: '12px',
                        padding: '10px 12px',
                        color: '#cbd5e1',
                        fontSize: '0.88rem',
                      }}
                    >
                      <div>{p.description || 'Saved product ready to inspect or add to cart.'}</div>
                      {item.important_attributes && item.important_attributes.length > 0 && (
                        <ul style={{ margin: '6px 0 0', paddingLeft: '18px' }}>
                          {item.important_attributes.slice(0, 3).map((attr, i) => (
                            <li key={i}>{attr}</li>
                          ))}
                        </ul>
                      )}
                    </div>
                  )}

                  <div style={{ display: 'flex', flexWrap: 'wrap', gap: '8px', marginTop: 'auto' }}>
                    <button
                      type="button"
                      disabled={isBusy}
                      onClick={() => handleViewProductInShop(p)}
                      aria-label={`View ${p.title} in Shop`}
                      style={{
                        flex: 1,
                        backgroundColor: '#1e293b',
                        color: '#f8fafc',
                        border: '1px solid #475569',
                        borderRadius: '10px',
                        padding: '10px 12px',
                        fontWeight: 700,
                        display: 'inline-flex',
                        alignItems: 'center',
                        justifyContent: 'center',
                        gap: '6px',
                      }}
                    >
                      <ExternalLink size={15} />
                      <span>View</span>
                    </button>
                    <button
                      type="button"
                      disabled={isBusy}
                      onClick={() => handleAddSavedToCart(item)}
                      aria-label={`Add ${p.title} to cart`}
                      style={{
                        flex: 1.4,
                        backgroundColor: '#0284c7',
                        color: '#ffffff',
                        border: 'none',
                        borderRadius: '10px',
                        padding: '10px 12px',
                        fontWeight: 700,
                        display: 'inline-flex',
                        alignItems: 'center',
                        justifyContent: 'center',
                        gap: '6px',
                      }}
                    >
                      <ShoppingCart size={15} />
                      <span>Add to Cart</span>
                    </button>
                    <button
                      type="button"
                      disabled={isBusy}
                      onClick={() => handleRemoveSavedItem(item)}
                      aria-label={`Remove ${p.title} from saved items`}
                      style={{
                        backgroundColor: '#1f2937',
                        color: '#fda4af',
                        border: '1px solid #475569',
                        borderRadius: '10px',
                        padding: '10px 12px',
                        fontWeight: 700,
                        display: 'inline-flex',
                        alignItems: 'center',
                        justifyContent: 'center',
                      }}
                    >
                      <Trash2 size={16} />
                    </button>
                  </div>
                </article>
              );
            })}
          </div>
        )
      ) : (
        <div style={{ display: 'flex', flexDirection: 'column', gap: '28px' }}>
          <div>
            <div style={{ display: 'inline-flex', alignItems: 'center', gap: '8px', color: '#38bdf8', fontWeight: 800, fontSize: '0.95rem', marginBottom: '12px' }}>
              <Bookmark size={16} aria-hidden="true" />
              <span>Saved Searches</span>
            </div>
            {savedSearches.length === 0 ? (
              <div
                style={{
                  backgroundColor: '#111827',
                  borderRadius: '16px',
                  padding: '28px',
                  textAlign: 'center',
                  border: '1px solid #1e293b',
                  color: '#cbd5e1',
                }}
              >
                <p style={{ fontSize: '1.05rem', fontWeight: 700, marginBottom: '6px' }}>
                  No saved searches yet
                </p>
                <p style={{ color: '#94a3b8', margin: 0, fontSize: '0.92rem' }}>
                  Click Save Search on any search results or say &ldquo;save this search&rdquo;.
                </p>
              </div>
            ) : (
            <div style={{ display: 'flex', flexDirection: 'column', gap: '12px' }}>
              {savedSearches.map((saved) => {
                const isBusy = busyId === saved.saved_search_id;
                const filterEntries = Object.entries(saved.filters || {}).filter(([, v]) => v !== null && v !== undefined && v !== '');
                return (
                  <article
                    key={saved.saved_search_id}
                    data-saved-search-id={saved.saved_search_id}
                    style={{
                      backgroundColor: '#111827',
                      border: '2px solid #334155',
                      borderRadius: '16px',
                      padding: '16px 20px',
                      display: 'flex',
                      flexWrap: 'wrap',
                      alignItems: 'center',
                      justifyContent: 'space-between',
                      gap: '14px',
                    }}
                  >
                    <div>
                      <h3 style={{ fontSize: '1.08rem', fontWeight: 800, color: '#f8fafc', margin: '0 0 4px' }}>
                        {saved.display_query}
                      </h3>
                      <div style={{ color: '#94a3b8', fontSize: '0.88rem' }}>
                        {filterEntries.length > 0
                          ? `Filters: ${filterEntries.map(([k, v]) => `${k}: ${Array.isArray(v) ? v.join(', ') : v}`).join(' | ')}`
                          : `Query: ${saved.original_query}`}
                        {saved.sort ? ` | Sort: ${saved.sort}` : ''}
                      </div>
                    </div>
                    <div style={{ display: 'flex', gap: '10px' }}>
                      <button
                        type="button"
                        disabled={isBusy}
                        onClick={() => handleRunSavedSearch(saved)}
                        aria-label={`Run saved search ${saved.display_query} again`}
                        style={{
                          backgroundColor: '#0284c7',
                          color: '#ffffff',
                          border: 'none',
                          borderRadius: '10px',
                          padding: '10px 16px',
                          fontWeight: 700,
                          display: 'inline-flex',
                          alignItems: 'center',
                          gap: '6px',
                        }}
                      >
                        <Play size={15} />
                        <span>{isBusy ? 'Running...' : 'Run Again'}</span>
                      </button>
                      <button
                        type="button"
                        disabled={isBusy}
                        onClick={() => handleDeleteSavedSearch(saved)}
                        aria-label={`Delete saved search ${saved.display_query}`}
                        style={{
                          backgroundColor: '#1f2937',
                          color: '#fda4af',
                          border: '1px solid #475569',
                          borderRadius: '10px',
                          padding: '10px 14px',
                          fontWeight: 700,
                          display: 'inline-flex',
                          alignItems: 'center',
                          gap: '6px',
                        }}
                      >
                        <Trash2 size={15} />
                        <span>Delete</span>
                      </button>
                    </div>
                  </article>
                );
              })}
            </div>
          )}
          </div>

          {/* Full Recent Search History (distinct from Saved Searches) */}
          {searchHistory.length > 0 && (
            <div
              style={{
                backgroundColor: '#0f172a',
                border: '1px solid #334155',
                borderRadius: '16px',
                padding: '16px 20px',
              }}
            >
              <div
                style={{
                  display: 'flex',
                  justifyContent: 'space-between',
                  alignItems: 'center',
                  flexWrap: 'wrap',
                  gap: '10px',
                  marginBottom: '12px',
                }}
              >
                <div style={{ display: 'inline-flex', alignItems: 'center', gap: '8px', color: '#cbd5e1', fontWeight: 700 }}>
                  <History size={16} color="#94a3b8" aria-hidden="true" />
                  <span>Recent Searches</span>
                </div>
                {confirmClearHistory ? (
                  <div style={{ display: 'inline-flex', alignItems: 'center', gap: '8px' }}>
                    <span style={{ fontSize: '0.84rem', color: '#fca5a5', fontWeight: 700 }}>
                      Clear all recent searches?
                    </span>
                    <button
                      type="button"
                      onClick={handleClearHistory}
                      style={{
                        backgroundColor: '#7f1d1d',
                        color: '#fecaca',
                        border: '1px solid #ef4444',
                        borderRadius: '8px',
                        padding: '5px 10px',
                        fontSize: '0.82rem',
                        fontWeight: 700,
                      }}
                    >
                      Confirm Clear
                    </button>
                    <button
                      type="button"
                      onClick={() => setConfirmClearHistory(false)}
                      style={{
                        backgroundColor: 'transparent',
                        color: '#94a3b8',
                        border: '1px solid #334155',
                        borderRadius: '8px',
                        padding: '5px 10px',
                        fontSize: '0.82rem',
                        fontWeight: 600,
                      }}
                    >
                      Cancel
                    </button>
                  </div>
                ) : (
                  <button
                    type="button"
                    onClick={() => setConfirmClearHistory(true)}
                    style={{
                      backgroundColor: 'transparent',
                      color: '#94a3b8',
                      border: '1px solid #334155',
                      borderRadius: '8px',
                      padding: '6px 10px',
                      fontSize: '0.85rem',
                      fontWeight: 600,
                    }}
                  >
                    Clear Recent Searches
                  </button>
                )}
              </div>
              <div style={{ display: 'flex', flexWrap: 'wrap', gap: '8px' }}>
                {searchHistory.map((entry) => (
                  <button
                    key={entry.history_id}
                    type="button"
                    onClick={() => handleRunHistoryEntry(entry)}
                    disabled={busyId === entry.history_id}
                    style={{
                      backgroundColor: '#1e293b',
                      color: '#e2e8f0',
                      border: '1px solid #475569',
                      borderRadius: '8px',
                      padding: '7px 12px',
                      fontSize: '0.88rem',
                      fontWeight: 600,
                      display: 'inline-flex',
                      alignItems: 'center',
                      gap: '6px',
                    }}
                  >
                    <History size={13} color="#94a3b8" aria-hidden="true" />
                    <span>{entry.display_query} ({entry.result_count})</span>
                  </button>
                ))}
              </div>
            </div>
          )}
        </div>
      )}
    </section>
  );
};
