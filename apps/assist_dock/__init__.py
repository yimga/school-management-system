"""v4.00.91 — assist dock registry SOT.

The assist dock is the right-edge floating rail that bundles AI copilot,
feedback, help, context, messages, and back-to-top into one chrome.

Prior to v4.00.91 the dock was JS-DOM-scan only: ``rmc-assist-dock.js``
hunted for ``.ai-copilot-wrapper`` / ``.voc-widget`` / ``.cp-context-drawer-toggle``
/ ``[data-rmc-page-help]`` / ``.portal-chathead`` / ``#back-to-top-btn`` and
adopted those source nodes into chips. New chips required a JS edit.

This app introduces the canonical registry (``registry.py``) so any other
app can declare a chip with a one-line ``register_slot(...)`` call. The
context processor renders the registry to a JSON island on every page; the
JS still adopts legacy widgets for ``source="dom-adopt"`` slots (back-compat),
but new chips lifted into the registry render server-side.
"""
