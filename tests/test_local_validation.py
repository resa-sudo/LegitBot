"""Полностью локальные изображения и FSM; никаких сетевых запросов."""
import os
import unittest
from datetime import datetime, timezone
from io import BytesIO
from unittest.mock import AsyncMock, patch

from PIL import Image, ImageDraw, ImageFilter
from aiogram import Bot
from aiogram.types import Message, Chat, User, PhotoSize, Update

from legitbot.photo_validation import validate_photo
from legitbot.photo_requirements import AF1_PHOTO_REQUIREMENTS, MODEL
from legitbot.af1_flow import AF1, FIXED_INSOLES, NO_BOX, RETAKE
from legitbot.flow import CHECK_BUTTON, BEGIN_BUTTON
from legitbot.__main__ import create_dispatcher


def sample(kind="good", size=640):
    image = Image.new("RGB", (size, size), (128, 128, 128))
    if kind in ("good", "blur"):
        draw = ImageDraw.Draw(image)
        for y in range(0, size, 32):
            for x in range(0, size, 32):
                draw.rectangle((x, y, x + 31, y + 31),
                               fill=(60, 60, 60) if (x // 32 + y // 32) % 2 else (210, 210, 210))
        if kind == "blur":
            image = image.filter(ImageFilter.GaussianBlur(12))
    elif kind == "dark":
        image.paste((5, 5, 5), (0, 0, size, size))
    elif kind == "bright":
        image.paste((253, 253, 253), (0, 0, size, size))
    output = BytesIO()
    image.save(output, format="JPEG", quality=95)
    image.close()
    return output.getvalue()


class LocalTests(unittest.IsolatedAsyncioTestCase):
    async def asyncSetUp(self):
        environment = patch.dict(os.environ, {"PHOTO_VALIDATION_PROVIDER": "local", "OPENAI_API_KEY": ""})
        environment.start()
        self.addCleanup(environment.stop)
        network = patch("legitbot.photo_validation.AsyncOpenAI")
        self.client = network.start()
        self.addCleanup(network.stop)

    async def asyncTearDown(self):
        self.client.assert_not_called()

    async def test_good_image_without_key_and_without_semantic_claim(self):
        result = await validate_photo(AF1_PHOTO_REQUIREMENTS[3], sample())
        self.assertTrue(result.accepted)
        self.assertTrue(result.quality_ok)
        self.assertIsNone(result.detected_zone)
        self.assertIsNone(result.confidence)
        self.assertNotIn("пят", result.user_message)

    async def test_default_provider_is_local(self):
        with patch.dict(os.environ):
            os.environ.pop("PHOTO_VALIDATION_PROVIDER", None)
            result = await validate_photo(AF1_PHOTO_REQUIREMENTS[0], sample())
        self.assertTrue(result.accepted)

    async def test_low_resolution(self):
        result = await validate_photo(AF1_PHOTO_REQUIREMENTS[0], sample(size=200))
        self.assertEqual(result.reason, "resolution_too_low")

    async def test_extreme_darkness(self):
        result = await validate_photo(AF1_PHOTO_REQUIREMENTS[0], sample("dark"))
        self.assertEqual(result.reason, "too_dark")

    async def test_extreme_brightness(self):
        result = await validate_photo(AF1_PHOTO_REQUIREMENTS[0], sample("bright"))
        self.assertEqual(result.reason, "too_bright")

    async def test_severe_blur(self):
        result = await validate_photo(AF1_PHOTO_REQUIREMENTS[0], sample("blur"))
        self.assertFalse(result.accepted)
        self.assertEqual(result.reason, "too_blurry")

    async def test_uniform_lack_of_detail(self):
        result = await validate_photo(AF1_PHOTO_REQUIREMENTS[0], sample("flat"))
        self.assertEqual(result.reason, "too_blurry")

    async def test_decode_failure(self):
        for content in (b"not an image", b"\xff\xd8\xffbroken", sample()[:100]):
            result = await validate_photo(AF1_PHOTO_REQUIREMENTS[0], content)
            self.assertFalse(result.accepted)
            self.assertEqual(result.reason, "invalid_image")

    async def test_unknown_provider_does_not_fallback_to_openai(self):
        with patch.dict(os.environ, {"PHOTO_VALIDATION_PROVIDER": "typo"}), self.assertLogs(
            "legitbot.photo_validation", level="WARNING"
        ):
            result = await validate_photo(AF1_PHOTO_REQUIREMENTS[0], sample())
        self.assertFalse(result.accepted)
        self.assertTrue(result.retryable)


class LocalFlowTests(unittest.IsolatedAsyncioTestCase):
    async def asyncSetUp(self):
        environment = patch.dict(os.environ, {"PHOTO_VALIDATION_PROVIDER": "local", "OPENAI_API_KEY": ""})
        environment.start()
        self.addCleanup(environment.stop)
        network = patch("legitbot.photo_validation.AsyncOpenAI")
        self.client = network.start()
        self.addCleanup(network.stop)
        self.bot = Bot("123456:offline-placeholder")
        self.dp = create_dispatcher()
        self.ctx = self.dp.fsm.get_context(bot=self.bot, chat_id=1, user_id=1)
        self.sequence = 0
        self.image = sample()
        async def download(photo, *, destination, timeout):
            destination.write(self.image)
        for name, side_effect in (("download", download),):
            target = patch.object(Bot, name, new_callable=AsyncMock)
            target.start().side_effect = side_effect
            self.addCleanup(target.stop)
        answer = patch.object(Message, "answer", new_callable=AsyncMock)
        self.answer = answer.start()
        self.addCleanup(answer.stop)

    async def asyncTearDown(self):
        self.client.assert_not_called()
        await self.dp.storage.close()
        await self.dp.fsm.events_isolation.close()
        await self.bot.session.close()

    async def send(self, text=None, photo=False):
        self.sequence += 1
        message = Message(message_id=self.sequence, date=datetime.now(timezone.utc),
                          chat=Chat(id=1, type="private"),
                          from_user=User(id=1, first_name="Test", is_bot=False), text=text,
                          photo=[PhotoSize(file_id=str(self.sequence), file_unique_id=str(self.sequence),
                                           width=640, height=640)] if photo else None)
        await self.dp.feed_update(self.bot, Update(update_id=self.sequence, message=message))

    async def prepare(self):
        for text in (CHECK_BUTTON, "Nike", "Air Force 1", MODEL, BEGIN_BUTTON):
            await self.send(text)

    async def test_bad_image_stays_then_good_advances(self):
        await self.prepare()
        for kind in ("blur", "dark", "bright"):
            self.image = sample(kind)
            await self.send(photo=True)
            data = await self.ctx.get_data()
            self.assertEqual(data["photo_index"], 0)
            self.assertEqual(data["photos"]["TOP_VIEW"]["status"], "needs_reshoot")
        self.image = sample(size=200)
        await self.send(photo=True)
        self.assertEqual((await self.ctx.get_data())["photo_index"], 0)
        self.image = sample()
        await self.send(photo=True)
        self.assertEqual((await self.ctx.get_data())["photo_index"], 1)

    async def test_local_insoles_box_review_and_reshoot(self):
        await self.prepare()
        for _ in range(7):
            await self.send(photo=True)
        await self.send(FIXED_INSOLES)
        await self.send(photo=True)
        self.assertEqual((await self.ctx.get_data())["photo_index"], 10)
        await self.send(photo=True)
        await self.send(photo=True)
        await self.send(NO_BOX)
        self.assertEqual(await self.ctx.get_state(), AF1.review.state)
        self.assertIn("Получено: 10", self.answer.call_args.args[0])
        self.assertIn("Недоступно: 3", self.answer.call_args.args[0])
        before = (await self.ctx.get_data())["photos"]
        await self.send(RETAKE)
        await self.send("Вид сверху")
        await self.send(photo=True)
        after = (await self.ctx.get_data())["photos"]
        self.assertNotEqual(before["TOP_VIEW"]["file_id"], after["TOP_VIEW"]["file_id"])
        self.assertEqual(before["BOX_LABEL"], after["BOX_LABEL"])
        self.assertEqual(before["UNDER_INSOLE"], after["UNDER_INSOLE"])
