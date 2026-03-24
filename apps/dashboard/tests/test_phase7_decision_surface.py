"""Phase 7 — decision-engine surface partial renders with contract markers."""

from django.template import engines
from django.test import SimpleTestCase


class Phase7DecisionSurfaceTests(SimpleTestCase):
    def test_decision_engine_surface_renders_zones(self):
        eng = engines["django"]
        tpl = eng.get_template("components/decision_engine_surface.html")
        html = tpl.render(
            {
                "de_eyebrow": "Test",
                "de_headline_label": "State",
                "de_headline_value": "42",
                "de_headline_meta": "meta",
                "de_metrics": [
                    {"label": "A", "value": 1, "meta": "m", "status": "ok"}
                ],
                "de_urgent_queue": [{"title": "Do", "url": "/x/", "hint": "h"}],
                "de_next_actions": [{"label": "Go", "url": "/y/"}],
                "de_activity": [{"title": "Act", "meta": "recent"}],
            }
        )
        self.assertIn('data-decision-engine="surface"', html)
        self.assertIn('data-decision-zone="headline"', html)
        self.assertIn('data-decision-zone="supporting-metrics"', html)
        self.assertIn('data-decision-zone="urgent-queue"', html)
        self.assertIn('data-decision-zone="next-best-actions"', html)
        self.assertIn('data-decision-zone="activity-trend"', html)
