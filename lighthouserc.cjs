/** @type {import('lighthouse').Config} */
module.exports = {
  ci: {
    collect: {
      numberOfRuns: 1,
      url: [process.env.LHCI_URL || "http://127.0.0.1:8000/"],
    },
    assert: {
      assertions: {
        "categories:performance": ["warn", { minScore: 0.75 }],
        "largest-contentful-paint": ["warn", { maxNumericValue: 4000 }],
        "cumulative-layout-shift": ["warn", { maxNumericValue: 0.15 }],
      },
    },
    upload: {
      target: "temporary-public-storage",
    },
  },
};
