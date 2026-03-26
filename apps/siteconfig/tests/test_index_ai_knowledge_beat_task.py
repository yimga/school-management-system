from unittest.mock import patch

from django.test import TestCase

from apps.siteconfig.tasks import index_ai_knowledge_beat


class IndexAiKnowledgeBeatTaskTests(TestCase):
    @patch("django.core.management.call_command")
    def test_task_runs_index_ai_knowledge_command(self, mock_cmd):
        index_ai_knowledge_beat()
        mock_cmd.assert_called_once()
        args, kwargs = mock_cmd.call_args
        self.assertEqual(args[0], "index_ai_knowledge")
        self.assertIn("stdout", kwargs)
        self.assertIn("stderr", kwargs)
