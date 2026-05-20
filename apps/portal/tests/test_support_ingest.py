from django.test import SimpleTestCase

from apps.portal.support_ingest import chunk_text_sliding_window


class SupportIngestChunkTests(SimpleTestCase):
    def test_sliding_window_overlap(self):
        text = "word " * 400
        chunks = chunk_text_sliding_window(text, chunk_tokens=50, overlap_tokens=10)
        self.assertGreater(len(chunks), 1)
        self.assertTrue(all(len(c) > 0 for c in chunks))
