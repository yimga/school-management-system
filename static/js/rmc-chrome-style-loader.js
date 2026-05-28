(() => {
  "use strict";

  const SELECTOR = "link[data-rmc-deferred-style][rel='preload'][as='style']";

  const promoteDeferredStyles = () => {
    const deferredLinks = document.querySelectorAll(SELECTOR);
    deferredLinks.forEach((preloadLink) => {
      const href = preloadLink.getAttribute("href");
      if (!href) return;
      if (document.querySelector(`link[rel="stylesheet"][href="${href}"]`)) return;
      const stylesheet = document.createElement("link");
      stylesheet.rel = "stylesheet";
      stylesheet.href = href;
      preloadLink.insertAdjacentElement("afterend", stylesheet);
    });
  };

  promoteDeferredStyles();
  if (document.readyState === "loading") {
    document.addEventListener("DOMContentLoaded", promoteDeferredStyles, { once: true });
  }
})();
