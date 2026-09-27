"""Проверка провайдера без сети, реальных ключей и изображений пользователя."""
import json
import os
import unittest
from unittest.mock import AsyncMock, patch

import httpx
from openai import AsyncOpenAI

from legitbot import photo_validation as validation
from legitbot.photo_requirements import AF1_PHOTO_REQUIREMENTS

IMAGE = b"\xff\xd8\xffoffline-test-image"
GOOD = {
    "matches_requested_zone": True, "detected_zone": "heels", "quality_ok": True,
    "reason": None, "user_message": "Фото подходит.", "confidence": 0.94,
}
HEELS = AF1_PHOTO_REQUIREMENTS[3]


def api_response(text, status="completed"):
    return {
        "id": "resp_test", "object": "response", "created_at": 0,
        "model": "gpt-4.1-mini", "status": status,
        "output": [{"type": "message", "id": "msg_test", "role": "assistant",
                    "status": "completed", "content": [
                        {"type": "output_text", "text": text, "annotations": []}]}],
    }


class ValidationTests(unittest.IsolatedAsyncioTestCase):
    async def asyncSetUp(self):
        mode_patch = patch.dict(os.environ, {"PHOTO_VALIDATION_PROVIDER": "openai"})
        mode_patch.start()
        self.addCleanup(mode_patch.stop)

    async def evaluate(self, data):
        with patch.object(validation, "request_assessment", new_callable=AsyncMock,
                          return_value=json.dumps(data)):
            return await validation.validate_photo(HEELS, IMAGE)

    async def test_correct_photo_accepted(self):
        result = await self.evaluate(GOOD)
        self.assertTrue(result.accepted)
        self.assertEqual(result.status, "received")
        self.assertEqual(result.detected_zone, "heels")
        self.assertTrue(result.quality_ok)
        self.assertEqual(result.confidence, 0.94)

    async def test_wrong_zone_rejected(self):
        result = await self.evaluate({**GOOD, "matches_requested_zone": False,
                                     "detected_zone": "keyboard", "reason": "wrong_zone"})
        self.assertFalse(result.accepted)
        self.assertEqual(result.reason, "wrong_zone")
        self.assertEqual(result.status, "needs_reshoot")
        self.assertFalse(result.retryable)

    async def test_poor_quality_rejected(self):
        result = await self.evaluate({**GOOD, "quality_ok": False, "reason": "poor_quality"})
        self.assertFalse(result.accepted)
        self.assertEqual(result.reason, "poor_quality")

    async def test_low_confidence_is_not_accepted(self):
        result = await self.evaluate({**GOOD, "confidence": 0.2})
        self.assertFalse(result.accepted)
        self.assertEqual(result.reason, "uncertain_zone")

    async def test_malformed_and_inconsistent_output_fail_closed(self):
        cases = [
            "not json", "{}", json.dumps({**GOOD, "confidence": 2}),
            json.dumps({**GOOD, "confidence": float("nan")}),
            json.dumps({**GOOD, "matches_requested_zone": "true"}),
            json.dumps({**GOOD, "reason": "wrong_zone"}),
            json.dumps({**GOOD, "authenticity": "real"}),
            json.dumps({**GOOD, "quality_ok": False, "reason": None}),
        ]
        for raw in cases:
            with self.subTest(raw=raw), patch.object(
                validation, "request_assessment", new_callable=AsyncMock, return_value=raw
            ), self.assertLogs("legitbot.photo_validation", level="WARNING"):
                result = await validation.validate_photo(HEELS, IMAGE)
                self.assertFalse(result.accepted)
                self.assertTrue(result.retryable)
                self.assertEqual(result.reason, "validation_unavailable")

    async def test_missing_key_fails_closed_without_network(self):
        with patch.dict(os.environ, {"OPENAI_API_KEY": ""}), patch.object(
            validation, "AsyncOpenAI"
        ) as client, self.assertLogs("legitbot.photo_validation", level="WARNING"):
            result = await validation.validate_photo(HEELS, IMAGE)
        self.assertFalse(result.accepted)
        self.assertTrue(result.retryable)
        client.assert_not_called()

    async def test_sdk_request_shape_and_privacy(self):
        requests = []
        def transport(request):
            requests.append(json.loads(request.content))
            self.assertEqual(request.url.path, "/v1/responses")
            return httpx.Response(200, json=api_response(json.dumps(GOOD)))
        def factory(**kwargs):
            self.assertEqual(kwargs["max_retries"], 0)
            self.assertEqual(kwargs["timeout"], 30)
            return AsyncOpenAI(**kwargs, http_client=httpx.AsyncClient(
                transport=httpx.MockTransport(transport)))
        with patch.dict(os.environ, {"OPENAI_API_KEY": "offline-placeholder", "OPENAI_VISION_MODEL": ""}), patch.object(
            validation, "AsyncOpenAI", side_effect=factory
        ):
            result = await validation.validate_photo(HEELS, IMAGE)
        self.assertTrue(result.accepted)
        body = requests[0]
        self.assertEqual(body["model"], "gpt-4.1-mini")
        self.assertFalse(body["store"])
        self.assertEqual(body["text"]["format"]["type"], "json_schema")
        self.assertTrue(body["text"]["format"]["strict"])
        content = body["input"][0]["content"]
        self.assertEqual(content[0]["text"],
                         f"Requested zone: heels\n{HEELS.validation_instruction}")
        self.assertTrue(content[1]["image_url"].startswith("data:image/jpeg;base64,"))
        self.assertEqual(set(body), {"model", "instructions", "input", "text",
                                     "max_output_tokens", "store"})
        for forbidden in ("telegram", "chat_id", "username", "file_id", "phone", "offline-placeholder"):
            self.assertNotIn(forbidden, json.dumps(body).lower())

    async def test_sdk_timeout_and_logs_do_not_expose_error_body(self):
        def transport(request):
            raise httpx.ReadTimeout("secret-private-url-and-key", request=request)
        def factory(**kwargs):
            return AsyncOpenAI(**kwargs, http_client=httpx.AsyncClient(
                transport=httpx.MockTransport(transport)))
        with patch.dict(os.environ, {"OPENAI_API_KEY": "offline-placeholder"}), patch.object(
            validation, "AsyncOpenAI", side_effect=factory
        ), self.assertLogs("legitbot.photo_validation", level="WARNING") as logs:
            result = await validation.validate_photo(HEELS, IMAGE)
        self.assertTrue(result.retryable)
        self.assertFalse(result.accepted)
        self.assertNotIn("secret-private", str(logs.output))
        self.assertIn("APITimeoutError", str(logs.output))

    async def test_incomplete_or_refused_response_is_not_accepted(self):
        for payload in (api_response("", "incomplete"), {
            **api_response(""), "output": [{"type": "message", "id": "msg_test",
            "role": "assistant", "status": "completed",
            "content": [{"type": "refusal", "refusal": "Cannot process."}]}],
        }):
            def factory(**kwargs):
                return AsyncOpenAI(**kwargs, http_client=httpx.AsyncClient(
                    transport=httpx.MockTransport(lambda request: httpx.Response(200, json=payload))))
            with patch.dict(os.environ, {"OPENAI_API_KEY": "offline-placeholder"}), patch.object(
                validation, "AsyncOpenAI", side_effect=factory
            ), self.assertLogs("legitbot.photo_validation", level="WARNING"):
                result = await validation.validate_photo(HEELS, IMAGE)
            self.assertTrue(result.retryable)

    async def test_all_zones_configured_and_ai_text_not_echoed(self):
        for requirement in AF1_PHOTO_REQUIREMENTS:
            self.assertTrue(requirement.validation_instruction)
            self.assertTrue(requirement.retake_instruction)
        result = await self.evaluate({**GOOD, "user_message": "This shoe is authentic"})
        self.assertNotIn("authentic", result.user_message)
        self.assertEqual(result.user_message, "Фото подходит.")

    async def test_model_override(self):
        models = []
        def transport(request):
            models.append(json.loads(request.content)["model"])
            return httpx.Response(200, json=api_response(json.dumps(GOOD)))
        def factory(**kwargs):
            return AsyncOpenAI(**kwargs, http_client=httpx.AsyncClient(
                transport=httpx.MockTransport(transport)))
        with patch.dict(os.environ, {"OPENAI_API_KEY": "offline-placeholder",
                                    "OPENAI_VISION_MODEL": "configured-model"}), patch.object(
            validation, "AsyncOpenAI", side_effect=factory
        ):
            await validation.validate_photo(HEELS, IMAGE)
        self.assertEqual(models, ["configured-model"])
