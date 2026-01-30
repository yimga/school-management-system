/**
 * Lighthouse CI – Core Web Vitals and performance assertions.
 * Run: Start dev server (python manage.py runserver), then npm run lighthouse
 * Or in CI: set LHCI_COLLECT_URL or use --collect.url in npm script.
 */
module.exports = {
  ci: {
    collect: {
      url: process.env.LHCI_COLLECT_URL
        ? process.env.LHCI_COLLECT_URL.split(',')
        : ['http://localhost:8000/accounts/login/'],
      numberOfRuns: process.env.CI ? 3 : 1,
    },
    assert: {
      preset: 'lighthouse:no-pwa',
      assertions: {
        'largest-contentful-paint': ['warn', { maxNumericValue: 2500, aggregationMethod: 'optimistic' }],
        'cumulative-layout-shift': ['warn', { maxNumericValue: 0.1, aggregationMethod: 'pessimistic' }],
        'categories:performance': ['warn', { minScore: 0.5 }],
        'categories:accessibility': ['warn', { minScore: 0.8 }],
        'offscreen-images': 'off',
        'uses-webp-images': 'off',
        'color-contrast': 'off',
      },
    },
    upload: {
      target: 'temporary-public-storage',
    },
  },
};
