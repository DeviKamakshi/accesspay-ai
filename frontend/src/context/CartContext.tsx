import React, { createContext, useContext, useState, useEffect } from 'react';
import { Cart, PurchaseReview, PurchaseResponse } from '../types';
import { api } from '../services/api';
import { useAccessibility } from './AccessibilityContext';

interface CartContextType {
  cart: Cart | null;
  isLoading: boolean;
  activeReview: PurchaseReview | null;
  lastPurchaseResult: PurchaseResponse | null;
  refreshCart: () => Promise<void>;
  addToCart: (productId: string, quantity?: number, variant?: Record<string, string>) => Promise<void>;
  updateQuantity: (productId: string, quantity: number) => Promise<void>;
  removeFromCart: (productIdOrTitle: string) => Promise<void>;
  clearCart: () => Promise<void>;
  prepareReview: () => Promise<PurchaseReview | null>;
  confirmPurchase: (
    spokenPhrase?: string,
    method?: string,
    subAck?: boolean,
    trialAck?: boolean,
    highValueStep?: number,
    authorizeOnly?: boolean
  ) => Promise<PurchaseResponse>;
  cancelPurchase: () => Promise<PurchaseResponse>;
  simulatePriceChange: (newPrice?: number) => Promise<PurchaseReview>;
  closeReviewModal: () => void;
  closeResultModal: () => void;
}

const CartContext = createContext<CartContextType | undefined>(undefined);

export const CartProvider: React.FC<{ children: React.ReactNode }> = ({ children }) => {
  const [cart, setCart] = useState<Cart | null>(null);
  const [isLoading, setIsLoading] = useState<boolean>(false);
  const [activeReview, setActiveReview] = useState<PurchaseReview | null>(null);
  const [lastPurchaseResult, setLastPurchaseResult] = useState<PurchaseResponse | null>(null);
  const { announce } = useAccessibility();

  const refreshCart = async () => {
    setIsLoading(true);
    try {
      const data = await api.getCart();
      setCart(data);
    } catch (err) {
      console.error('Failed to load cart:', err);
    } finally {
      setIsLoading(false);
    }
  };

  useEffect(() => {
    refreshCart();
  }, []);

  const addToCart = async (productId: string, quantity = 1, variant?: Record<string, string>) => {
    setIsLoading(true);
    try {
      const updated = await api.addToCart(productId, quantity, variant);
      setCart(updated);
      setActiveReview(null);
      announce(`Added product to cart. Total today is $${updated.total_today.toFixed(2)}.`);
    } catch (err: any) {
      announce(`Could not add item to cart: ${err.message}`);
    } finally {
      setIsLoading(false);
    }
  };

  const updateQuantity = async (productId: string, quantity: number) => {
    try {
      const updated = await api.updateCartItem(productId, quantity);
      setCart(updated);
      setActiveReview(null);
      announce(`Updated quantity to ${quantity}. New total is $${updated.total_today.toFixed(2)}.`);
    } catch (err: any) {
      announce(`Could not update quantity: ${err.message}`);
    }
  };

  const removeFromCart = async (productIdOrTitle: string) => {
    try {
      const updated = await api.removeFromCart(productIdOrTitle);
      setCart(updated);
      setActiveReview(null);
      announce(`Item removed from cart. New total is $${updated.total_today.toFixed(2)}.`);
    } catch (err: any) {
      announce(`Could not remove item: ${err.message}`);
    }
  };

  const clearCart = async () => {
    try {
      const updated = await api.clearCart();
      setCart(updated);
      setActiveReview(null);
      announce('Cart cleared.');
    } catch (err: any) {
      announce(`Could not clear cart: ${err.message}`);
    }
  };

  const prepareReview = async (): Promise<PurchaseReview | null> => {
    try {
      const review = await api.preparePurchaseReview();
      setActiveReview(review);
      announce(
        `Payment review ready. Total is $${review.total_today.toFixed(2)}. Say: '${review.expected_phrase}' to authorize payment.`
      );
      return review;
    } catch (err: any) {
      announce(`Cannot prepare checkout: ${err.message}`);
      return null;
    }
  };

  const confirmPurchase = async (
    spokenPhrase?: string,
    method = 'VOICE',
    subAck?: boolean,
    trialAck?: boolean,
    highValueStep?: number,
    authorizeOnly = false
  ): Promise<PurchaseResponse> => {
    if (!activeReview) {
      throw new Error('No active payment review');
    }

    try {
      const response = await api.confirmPurchase({
        reviewToken: activeReview.review_token,
        spokenPhrase,
        confirmationMethod: method,
        subscriptionAcknowledged: subAck,
        trialAcknowledged: trialAck,
        highValueStep,
        authorizeOnly,
      });

      setLastPurchaseResult(response);

      if (response.success && response.state === 'PAYMENT_COMPLETE') {
        announce(`Payment successful. Order ${response.order_id || 'confirmed'}.`);
        setActiveReview(null);
        refreshCart();
      } else if (response.success && response.state === 'PAYMENT_PROCESSING') {
        announce('Confirmation verified. Proceeding to PayPal Sandbox checkout.');
      } else if (response.is_ambiguous) {
        announce(response.message);
      } else if (response.requires_step === 2) {
        announce(response.message);
        setActiveReview((prev) => prev ? { ...prev, high_value_step: 2 } : null);
      } else if (!response.success) {
        announce(response.message);
      }

      return response;
    } catch (err: any) {
      const failureResp: PurchaseResponse = {
        success: false,
        state: 'PAYMENT_FAILED',
        message: "Your payment could not be completed.\n\nNothing was charged.",
        is_ambiguous: false,
      };
      setLastPurchaseResult(failureResp);
      announce(failureResp.message);
      return failureResp;
    }
  };

  const cancelPurchase = async (): Promise<PurchaseResponse> => {
    try {
      const res = await api.cancelPurchase();
      setActiveReview(null);
      setLastPurchaseResult(res);
      announce('Purchase cancelled. No payment was made.');
      return res;
    } catch (err: any) {
      announce('Could not cancel purchase.');
      throw err;
    }
  };

  const simulatePriceChange = async (newPrice = 62.99): Promise<PurchaseReview> => {
    const updated = await api.simulatePriceChange(newPrice);
    setActiveReview(updated);
    announce(updated.invalidation_reason || 'Price changed. Confirmation invalidated.');
    return updated;
  };

  const closeReviewModal = () => setActiveReview(null);
  const closeResultModal = () => setLastPurchaseResult(null);

  return (
    <CartContext.Provider
      value={{
        cart,
        isLoading,
        activeReview,
        lastPurchaseResult,
        refreshCart,
        addToCart,
        updateQuantity,
        removeFromCart,
        clearCart,
        prepareReview,
        confirmPurchase,
        cancelPurchase,
        simulatePriceChange,
        closeReviewModal,
        closeResultModal,
      }}
    >
      {children}
    </CartContext.Provider>
  );
};

export const useCart = () => {
  const context = useContext(CartContext);
  if (!context) throw new Error('useCart must be used within CartProvider');
  return context;
};
