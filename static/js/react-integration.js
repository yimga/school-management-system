/**
 * React Integration for Frontend Dashboard
 * Uses CDN for React, ReactDOM, and TanStack Query
 * Can be replaced with build process later
 */

// React and ReactDOM are loaded via CDN in template
// TanStack Query will be loaded via CDN

// Create React Query Client
window.ReactQueryClient = null;
window.ReactQueryProvider = null;

// Initialize when React is available
function initReactQuery() {
  if (typeof React === 'undefined' || typeof ReactDOM === 'undefined') {
    console.warn('React not loaded yet');
    return;
  }
  
  if (typeof ReactQuery === 'undefined') {
    console.warn('TanStack Query not loaded yet');
    return;
  }

  const { QueryClient, QueryClientProvider } = ReactQuery;
  
  // Create query client with default options
  window.ReactQueryClient = new QueryClient({
    defaultOptions: {
      queries: {
        refetchOnWindowFocus: false,
        retry: 1,
        staleTime: 5 * 60 * 1000, // 5 minutes
      },
    },
  });
}

// Auto-initialize when DOM is ready
if (document.readyState === 'loading') {
  document.addEventListener('DOMContentLoaded', initReactQuery);
} else {
  initReactQuery();
}

// Export helper functions for React components
window.ReactHelpers = {
  getQueryClient: () => window.ReactQueryClient,
  
  // CSRF token helper
  getCsrfToken: () => {
    const cookies = document.cookie ? document.cookie.split(";") : [];
    for (const raw of cookies) {
      const cookie = raw.trim();
      if (cookie.startsWith("csrftoken=")) {
        return decodeURIComponent(cookie.substring("csrftoken".length + 1));
      }
    }
    return "";
  },
  
  // Fetch helper with CSRF
  fetchWithAuth: async (url, options = {}) => {
    const headers = {
      'Content-Type': 'application/json',
      'X-CSRFToken': window.ReactHelpers.getCsrfToken(),
      ...(options.headers || {}),
    };
    
    const response = await fetch(url, {
      ...options,
      headers,
    });
    
    if (!response.ok) {
      const error = await response.json().catch(() => ({ error: response.statusText }));
      throw new Error(error.error || response.statusText);
    }
    
    return response.json();
  },
};
