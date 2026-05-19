/**
 * Lighthouse CI config – run against local or deployed URL.
 * Usage: npx lhci autorun (or npm run lighthouse after starting server)
 */
module.exports = {
  ci: {
    collect: {
      url: [
        process.env.LHCI_URL || 'http://localhost:8000/accounts/login/',
        process.env.LHCI_URL_PORTAL || 'http://localhost:8000/portal/parent/',
        process.env.LHCI_URL_MARKETING_HOME || 'http://runmycampus.com:8000/',
        process.env.LHCI_URL_MARKETING_PRICING || 'http://runmycampus.com:8000/pricing/',
      ],
      numberOfRuns: 1,
      startServerCommand: process.env.LHCI_START_SERVER ? 'python manage.py runserver' : undefined,
    },
    assert: {
      assertions: {
        'categories:performance': ['warn', { minScore: 0.5 }],
        'categories:accessibility': ['error', { minScore: 0.85 }],
        'categories:best-practices': ['warn', { minScore: 0.8 }],
        'first-contentful-paint': ['warn', { maxNumericValue: 3000 }],
        'largest-contentful-paint': ['warn', { maxNumericValue: 2500 }],
        'cumulative-layout-shift': ['warn', { maxNumericValue: 0.1 }],
      },
    },
    upload: {
      target: 'temporary-public-storage',
    },
  },
};
