"""Phase 8: WebSocket AI path must use services.ai_gateway.invoke (no direct provider calls)."""

from __future__ import annotations

import json
from unittest.mock import AsyncMock, patch

from django.contrib.auth import get_user_model
from django.test import TransactionTestCase

User = get_user_model()


class AIChatConsumerGatewayTests(TransactionTestCase):
    def setUp(self):
        suffix = __import__("uuid").uuid4().hex[:8]
        self.user = User.objects.create_user(
            username=f"ws-ai-{suffix}",
            email=f"ws-{suffix}@t.test",
            password="test-pass-123",
        )

    async def test_receive_uses_gateway_invoke(self):
        from apps.api import consumers

        if not getattr(consumers, "CHANNELS_AVAILABLE", False):
            self.skipTest("channels not available")

        consumer = consumers.AIChatConsumer()
        consumer.scope = {"user": self.user, "request": None}
        consumer.user = self.user
        consumer.send = AsyncMock()

        with patch("services.ai_gateway.invoke") as mock_invoke:
            mock_invoke.return_value = ("assistant reply", {"provider": "rules", "tier": "rules"})
            await consumer.receive(json.dumps({"message": "hello tenant"}))

        mock_invoke.assert_called_once()
        call_args = mock_invoke.call_args
        self.assertEqual(call_args[0][0], "general_chat")
        self.assertIn("hello tenant", call_args[0][1])
        consumer.send.assert_awaited()
        call_kw = consumer.send.await_args.kwargs
        raw = call_kw.get("text_data") or (consumer.send.await_args.args[0] if consumer.send.await_args.args else "")
        payload = json.loads(raw)
        self.assertEqual(payload.get("reply"), "assistant reply")
