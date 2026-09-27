"""Проверки FSM без токена и запросов к Telegram: python -m unittest discover -s tests -v."""

import asyncio
import unittest
from datetime import datetime, timezone
from unittest.mock import AsyncMock, patch

from aiogram import Bot
from aiogram.types import Chat, Message, PhotoSize, Update, User

from legitbot.af1_flow import AF1, BACK, NO_BOX, ANALYZE, RETAKE, OTHER_MODEL, UNSUPPORTED, PLACEHOLDER
from legitbot.photo_requirements import MODEL, AF1_PHOTO_REQUIREMENTS as PHOTO_REQUIREMENTS
from legitbot.af1_flow import FIXED_INSOLES, review, zone_label
from legitbot.photo_records import PhotoStatus, make_record
from legitbot.photo_validation import PhotoValidationResult
from legitbot.__main__ import create_dispatcher
from legitbot.flow import (
    ANALYZE_BUTTON, BEGIN_BUTTON, BRANDS, CANCEL_BUTTON, CHECK_BUTTON,
    NIKE_LINES, SKIP_BOX_BUTTON, Check,
)


class FlowTests(unittest.IsolatedAsyncioTestCase):
    async def asyncSetUp(self):
        self.bot = Bot(token="123456:offline_test_placeholder")
        self.dp = create_dispatcher()
        self.sequence = 0
        self.answer_patch = patch.object(Message, "answer", new_callable=AsyncMock)
        self.answer = self.answer_patch.start()
        self.addCleanup(self.answer_patch.stop)

    async def asyncTearDown(self):
        await self.dp.storage.close()
        await self.dp.fsm.events_isolation.close()
        await self.bot.session.close()

    def context(self, user=1):
        return self.dp.fsm.get_context(bot=self.bot, chat_id=user, user_id=user)

    async def send(self, text=None, photo=False, user=1, **extra):
        self.sequence += 1
        message = Message(
            message_id=self.sequence, date=datetime.now(timezone.utc),
            chat=Chat(id=user, type="private"),
            from_user=User(id=user, is_bot=False, first_name="Test"),
            text=text,
            photo=[PhotoSize(file_id=f"photo-{self.sequence}", file_unique_id=str(self.sequence),
                             width=100, height=100)] if photo else None,
            **extra,
        )
        await self.dp.feed_update(self.bot, Update(update_id=self.sequence, message=message))

    async def prepare(self, user=1):
        await self.send(CHECK_BUTTON, user=user)
        await self.send("Adidas", user=user)
        await self.send("Air Jordan 4 Military Black", user=user)
        await self.send(BEGIN_BUTTON, user=user)

    async def test_full_flow(self):
        await self.send("/start")
        self.assertIn(CHECK_BUTTON, str(self.answer.call_args.kwargs["reply_markup"]))
        await self.send(CHECK_BUTTON)
        self.assertEqual(self.answer.call_args.args[0], "Выберите бренд кроссовок")
        for brand in BRANDS:
            self.assertIn(brand, str(self.answer.call_args.kwargs["reply_markup"]))
        await self.send("Adidas")
        await self.send("Air Jordan 4 Military Black")
        self.assertIn("Бренд: Adidas", self.answer.call_args.args[0])
        self.assertIn("Модель: Air Jordan 4 Military Black", self.answer.call_args.args[0])
        await self.send(BEGIN_BUTTON)
        for i in range(9):
            self.assertIn(f"Фото {i + 1} из 9", self.answer.call_args.args[0])
            await self.send(photo=True)
        self.assertEqual(await self.context().get_state(), Check.ready.state)
        data = await self.context().get_data()
        self.assertEqual([p["step"] for p in data["photos"]], list(range(1, 10)))
        self.assertFalse(data["box_skipped"])
        self.assertEqual((data["brand"], data["line"], data["model"]),
                         ("Adidas", None, "Air Jordan 4 Military Black"))
        self.assertEqual(self.answer.call_args.args[0],
                         "✅ Все фотографии получены.\nПроверка готова к анализу.")
        await self.send(ANALYZE_BUTTON)
        self.assertEqual(self.answer.call_args.args[0],
                         "AI-анализ подключим на следующем этапе.")

    async def test_validation_and_album(self):
        await self.send(CHECK_BUTTON)
        await self.send("Unknown")
        self.assertEqual(await self.context().get_state(), Check.brand.state)
        await self.send("Другой бренд")
        for value in (" ", "x" * 151, "/other"):
            await self.send(value)
            self.assertEqual(await self.context().get_state(), Check.model.state)
        await self.send(photo=True)
        self.assertEqual(await self.context().get_state(), Check.model.state)
        await self.send("Model")
        await self.send(photo=True)
        self.assertEqual(await self.context().get_state(), Check.confirmation.state)
        await self.send(BEGIN_BUTTON)
        for extra in (
            {"text": "not a photo"},
            {"document": {"file_id": "document", "file_unique_id": "doc", "file_name": "photo.jpg"}},
            {"video": {"file_id": "video", "file_unique_id": "vid", "width": 10, "height": 10, "duration": 1}},
            {"photo": True, "media_group_id": "album"},
            {"text": SKIP_BOX_BUTTON},
        ):
            await self.send(**extra)
            self.assertEqual((await self.context().get_data())["photo_index"], 0)
        await self.send(photo=True)
        self.assertEqual((await self.context().get_data())["photo_index"], 1)

    async def test_optional_box(self):
        await self.prepare()
        for _ in range(8):
            await self.send(photo=True)
        await self.send(SKIP_BOX_BUTTON)
        data = await self.context().get_data()
        self.assertEqual(await self.context().get_state(), Check.ready.state)
        self.assertEqual(len(data["photos"]), 8)
        self.assertTrue(data["box_skipped"])

    async def test_cancel_and_restart_at_every_stage(self):
        for stage in (Check.brand, Check.line, Check.model, Check.confirmation, Check.photos, Check.ready):
            for command in (CANCEL_BUTTON, "/cancel", "/start"):
                await self.context().set_state(stage)
                await self.context().set_data({"brand": "Nike", "line": "Air Jordan", "model": "Old", "photos": [{"file_id": "old"}]})
                await self.send(command)
                self.assertIsNone(await self.context().get_state())
                self.assertEqual(await self.context().get_data(), {})
        await self.prepare()
        await self.send(photo=True)
        await self.send(CHECK_BUTTON)
        self.assertEqual(await self.context().get_state(), Check.brand.state)
        self.assertEqual(await self.context().get_data(), {})

    async def test_users_and_concurrent_photos(self):
        await self.prepare(user=1)
        await self.send(CHECK_BUTTON, user=2)
        await asyncio.gather(self.send(photo=True), self.send(photo=True))
        self.assertEqual((await self.context(1).get_data())["photo_index"], 2)
        self.assertEqual(len((await self.context(1).get_data())["photos"]), 2)
        self.assertEqual(await self.context(2).get_state(), Check.brand.state)
        await self.send(CANCEL_BUTTON, user=2)
        self.assertEqual((await self.context(1).get_data())["photo_index"], 2)

    async def test_stale_buttons_do_not_start_analysis(self):
        await self.send(ANALYZE_BUTTON)
        self.assertIsNone(await self.context().get_state())
        await self.prepare()
        await self.send(ANALYZE_BUTTON)
        self.assertEqual((await self.context().get_data())["photo_index"], 0)




    async def prepare_af1(self):
        for text in (CHECK_BUTTON, "Nike", "Air Force 1", MODEL, BEGIN_BUTTON):
            await self.send(text)

    async def finish_af1(self, missing=False):
        await self.prepare_af1()
        for _ in range(12):
            await self.send(photo=True)
        await self.send(NO_BOX) if missing else await self.send(photo=True)

    async def test_brand_and_line_menus(self):
        await self.send(CHECK_BUTTON)
        buttons = [row[0].text for row in self.answer.call_args.kwargs["reply_markup"].keyboard]
        self.assertEqual(buttons, ["Nike", "Adidas", "New Balance", "Другой бренд", CANCEL_BUTTON])
        await self.send("Nike")
        buttons = [row[0].text for row in self.answer.call_args.kwargs["reply_markup"].keyboard]
        self.assertEqual(buttons, ["Air Force 1", "Dunk", "Air Jordan", "Air Max", "Other Nike", BACK, CANCEL_BUTTON])
        for line in ("Dunk", "Air Jordan", "Air Max", "Other Nike"):
            await self.send(line)
            self.assertEqual(await self.context().get_state(), Check.line.state)
            self.assertEqual(self.answer.call_args_list[-2].args[0], UNSUPPORTED)
        await self.send(BACK)
        self.assertEqual(await self.context().get_state(), Check.brand.state)
        await self.send("Nike")
        await self.send("Air Force 1")
        await self.send(OTHER_MODEL)
        self.assertEqual(await self.context().get_state(), AF1.model.state)
        await self.send("Air Force 1 Black")
        self.assertEqual(await self.context().get_state(), AF1.model.state)
        await self.send(BACK)
        self.assertEqual(await self.context().get_state(), Check.line.state)

    async def test_af1_full_flow_and_metadata(self):
        await self.prepare_af1()
        expected = ["TOP_VIEW", "LEFT_OUTER_SIDE", "RIGHT_OUTER_SIDE", "HEELS",
                    "TOE_BOX", "TONGUE", "SIZE_TAG", "INSOLES_TOP", "INSOLES_BOTTOM",
                    "UNDER_INSOLE", "OUTSOLE", "DUBRAE", "BOX_LABEL"]
        self.assertEqual([r.id for r in PHOTO_REQUIREMENTS], expected)
        for index, requirement in enumerate(PHOTO_REQUIREMENTS):
            self.assertIn(f"Фото {index + 1} из 13", self.answer.call_args.args[0])
            buttons = [row[0].text for row in self.answer.call_args.kwargs["reply_markup"].keyboard]
            self.assertIn(BACK, buttons)
            self.assertIn(CANCEL_BUTTON, buttons)
            self.assertEqual(NO_BOX in buttons, index == 12)
            await self.send(photo=True)
            record = (await self.context().get_data())["photos"][requirement.id]
            self.assertEqual(record["step_id"], requirement.id)
            self.assertEqual(record["step_number"], index + 1)
            self.assertEqual(record["analysis_zone"], requirement.analysis_zone)
            self.assertTrue(record["file_id"])
            self.assertEqual(record["status"], "received")
            self.assertIsNone(record["reason"])
        self.assertEqual(await self.context().get_state(), AF1.review.state)
        self.assertIn("Получено: 13", self.answer.call_args.args[0])
        data = await self.context().get_data()
        self.assertEqual((data["brand"], data["line"], data["model"]), ("Nike", "Air Force 1", MODEL))
        await self.send(ANALYZE)
        self.assertEqual(self.answer.call_args.args[0], PLACEHOLDER)

    async def test_af1_invalid_inputs_and_back(self):
        await self.prepare_af1()
        for extra in ({"text": "skip"}, {"text": NO_BOX},
                      {"photo": True, "media_group_id": "album"},
                      {"document": {"file_id": "doc", "file_unique_id": "doc"}},
                      {"video": {"file_id": "v", "file_unique_id": "v", "width": 1, "height": 1, "duration": 1}}):
            await self.send(**extra)
            self.assertEqual((await self.context().get_data())["photos"], {})
            self.assertEqual(self.answer.call_args_list[-2].args[0], "На этом этапе нужна фотография.")
        await self.send(BACK)
        self.assertEqual(await self.context().get_state(), Check.confirmation.state)
        await self.send(BACK)
        self.assertEqual(await self.context().get_state(), AF1.model.state)
        await self.send(MODEL)
        await self.send(BEGIN_BUTTON)
        await self.send(photo=True)
        old = (await self.context().get_data())["photos"]["TOP_VIEW"]["file_id"]
        await self.send(BACK)
        self.assertEqual((await self.context().get_data())["photo_index"], 0)
        await self.send(photo=True)
        data = await self.context().get_data()
        self.assertNotEqual(data["photos"]["TOP_VIEW"]["file_id"], old)
        self.assertEqual(len(data["photos"]), 1)
        self.assertEqual(data["photo_index"], 1)

    async def test_af1_missing_box_and_retake_every_zone(self):
        await self.finish_af1(missing=True)
        data = await self.context().get_data()
        self.assertEqual(len(data["photos"]), 13)
        self.assertEqual(data["photos"]["BOX_LABEL"]["status"], "unavailable")
        self.assertEqual(data["photos"]["BOX_LABEL"]["reason"], "no_box")
        self.assertIsNone(data["photos"]["BOX_LABEL"]["file_id"])
        self.assertIn("Получено: 12", self.answer.call_args.args[0])
        self.assertIn("Наклейка коробки — недоступно (нет коробки)", self.answer.call_args.args[0])
        for requirement in PHOTO_REQUIREMENTS:
            before = (await self.context().get_data())["photos"]
            await self.send(RETAKE)
            buttons = [row[0].text for row in self.answer.call_args.kwargs["reply_markup"].keyboard]
            self.assertEqual(len(buttons), 15)
            label = zone_label(requirement, before)
            self.assertIn(label, buttons)
            await self.send(label)
            await self.send(photo=True)
            self.assertEqual(await self.context().get_state(), AF1.review.state)
            after = (await self.context().get_data())["photos"]
            for other in PHOTO_REQUIREMENTS:
                if other.id != requirement.id:
                    self.assertEqual(before[other.id], after[other.id])
            self.assertNotEqual(before[requirement.id]["file_id"], after[requirement.id]["file_id"])
        self.assertIn("Получено: 13", self.answer.call_args.args[0])

    async def test_af1_retake_back_and_mark_box_missing(self):
        await self.finish_af1()
        before = (await self.context().get_data())["photos"]
        await self.send(RETAKE)
        await self.send("Вид сверху")
        await self.send(BACK)
        self.assertEqual(await self.context().get_state(), AF1.retake.state)
        await self.send(BACK)
        self.assertEqual(await self.context().get_state(), AF1.review.state)
        self.assertEqual(before, (await self.context().get_data())["photos"])
        await self.send(RETAKE)
        await self.send("Наклейка коробки")
        await self.send(NO_BOX)
        self.assertIn("Получено: 12", self.answer.call_args.args[0])
        await self.send(ANALYZE)
        self.assertEqual(self.answer.call_args.args[0], PLACEHOLDER)

    async def test_af1_users_and_cancel(self):
        await self.prepare_af1()
        await self.send(CHECK_BUTTON, user=2)
        await asyncio.gather(self.send(photo=True), self.send(photo=True))
        self.assertEqual(len((await self.context().get_data())["photos"]), 2)
        self.assertEqual(await self.context(2).get_state(), Check.brand.state)
        for stage in (AF1.model, AF1.photos, AF1.review, AF1.retake):
            for command in (CANCEL_BUTTON, "/cancel", "/start"):
                await self.context().set_state(stage)
                await self.send(command)
                self.assertEqual(await self.context().get_data(), {})
                self.assertIsNone(await self.context().get_state())


    async def test_regression_exact_nike_keyboard_path(self):
        # Нажимаем именно тексты выданной клавиатуры через настоящий Dispatcher.
        await self.send("/start")
        def buttons():
            return [b.text for row in self.answer.call_args.kwargs["reply_markup"].keyboard for b in row]
        self.assertIn(CHECK_BUTTON, buttons())
        await self.send(CHECK_BUTTON)
        self.assertEqual(await self.context().get_state(), Check.brand.state)
        self.assertIn("Nike", buttons())
        previous = self.answer.await_count
        await self.send("Nike")
        self.assertGreater(self.answer.await_count, previous)
        self.assertEqual(await self.context().get_state(), Check.line.state)
        self.assertIn("Air Force 1", buttons())
        await self.send("Air Force 1")
        self.assertEqual(await self.context().get_state(), AF1.model.state)
        self.assertIn(MODEL, buttons())
        await self.send(MODEL)
        self.assertEqual(await self.context().get_state(), Check.confirmation.state)
        self.assertIn(BEGIN_BUTTON, buttons())
        await self.send(BEGIN_BUTTON)
        self.assertEqual(await self.context().get_state(), AF1.photos.state)
        self.assertIn("Фото 1 из 13", self.answer.call_args.args[0])

    async def test_regression_stale_jordan_and_restart(self):
        for stage in (None, Check.brand, Check.line, Check.model, Check.confirmation,
                      Check.photos, Check.ready, AF1.model, AF1.photos, AF1.review, AF1.retake):
            await self.context().set_state(stage)
            await self.context().set_data({"old": True})
            await self.send(CHECK_BUTTON)
            self.assertEqual(await self.context().get_state(), Check.brand.state)
            self.assertEqual(await self.context().get_data(), {})
            previous = self.answer.await_count
            await self.send("Jordan")
            self.assertGreater(self.answer.await_count, previous)
            self.assertEqual(await self.context().get_state(), Check.brand.state)
            await self.send("Nike")
            self.assertEqual(await self.context().get_state(), Check.line.state)
            await self.send(CANCEL_BUTTON)
            self.assertIsNone(await self.context().get_state())
            self.assertEqual(await self.context().get_data(), {})

    async def finish_af1_fixed_insoles(self, no_box=True):
        await self.prepare_af1()
        for _ in range(7):
            await self.send(photo=True)
        await self.send(FIXED_INSOLES)
        await self.send(photo=True)  # Стельки сверху внутри обуви.
        await self.send(photo=True)  # Подошва.
        await self.send(photo=True)  # Вставка AF1.
        await self.send(NO_BOX) if no_box else await self.send(photo=True)

    async def test_fixed_insoles_skip_and_counts(self):
        await self.prepare_af1()
        for _ in range(7):
            await self.send(photo=True)
        self.assertIn(FIXED_INSOLES, str(self.answer.call_args.kwargs["reply_markup"]))
        await self.send(FIXED_INSOLES)
        data = await self.context().get_data()
        self.assertTrue(data["insole_not_removable"])
        self.assertEqual(data["photo_index"], 7)
        self.assertNotIn("INSOLES_TOP", data["photos"])
        for step in ("INSOLES_BOTTOM", "UNDER_INSOLE"):
            self.assertEqual(data["photos"][step]["status"], "unavailable")
            self.assertEqual(data["photos"][step]["reason"], "insole_not_removable")
            self.assertIsNone(data["photos"][step]["file_id"])
        await self.send(FIXED_INSOLES)  # Повторное нажатие не создаёт дубликатов.
        await self.send(photo=True)
        self.assertEqual((await self.context().get_data())["photo_index"], 10)
        self.assertIn("Фото 11 из 13", self.answer.call_args.args[0])
        await self.send(photo=True)
        await self.send(photo=True)
        await self.send(NO_BOX)
        self.assertEqual(await self.context().get_state(), AF1.review.state)
        text = self.answer.call_args.args[0]
        for line in ("Получено: 10", "Недоступно: 3", "Пропущено: 0", "Требует пересъёмки: 0",
                     "Обратная сторона стелек — недоступно (стельки не снимаются)",
                     "Под стелькой — недоступно (стельки не снимаются)",
                     "Наклейка коробки — недоступно (нет коробки)"):
            self.assertIn(line, text)
        await self.send(ANALYZE)
        self.assertEqual(self.answer.call_args.args[0], PLACEHOLDER)

    async def test_fixed_insoles_back_skips_unavailable(self):
        await self.prepare_af1()
        for _ in range(7):
            await self.send(photo=True)
        await self.send(FIXED_INSOLES)
        await self.send(photo=True)
        await self.send(BACK)
        self.assertEqual((await self.context().get_data())["photo_index"], 7)
        await self.send(photo=True)
        self.assertEqual((await self.context().get_data())["photo_index"], 10)

    async def test_fixed_insoles_reshoot_keeps_other_records(self):
        await self.finish_af1_fixed_insoles()
        before = (await self.context().get_data())["photos"]
        await self.send(RETAKE)
        await self.send("Стельки сверху")
        await self.send(photo=True)
        after = (await self.context().get_data())["photos"]
        self.assertNotEqual(before["INSOLES_TOP"]["file_id"], after["INSOLES_TOP"]["file_id"])
        for step in before:
            if step != "INSOLES_TOP":
                self.assertEqual(before[step], after[step])
        await self.send(RETAKE)
        await self.send("Обратная сторона стелек — недоступно")
        self.assertEqual(await self.context().get_state(), AF1.retake.state)
        self.assertIn("Не отклеивайте", self.answer.call_args_list[-2].args[0])
        await self.send(BACK)
        await self.send(RETAKE)
        await self.send("Наклейка коробки — недоступно")
        await self.send(photo=True)
        self.assertIn("Получено: 11", self.answer.call_args.args[0])
        self.assertIn("Недоступно: 2", self.answer.call_args.args[0])
        box = (await self.context().get_data())["photos"]["BOX_LABEL"]
        self.assertEqual(box["status"], "received")
        self.assertIsNone(box["reason"])

    async def test_fixed_insoles_choice_during_reshoot(self):
        await self.finish_af1()
        await self.send(RETAKE)
        await self.send("Стельки сверху")
        await self.send(FIXED_INSOLES)
        await self.send(photo=True)
        self.assertEqual(await self.context().get_state(), AF1.review.state)
        self.assertIn("Получено: 11", self.answer.call_args.args[0])
        self.assertIn("Недоступно: 2", self.answer.call_args.args[0])
        data = await self.context().get_data()
        for step in ("INSOLES_BOTTOM", "UNDER_INSOLE"):
            self.assertEqual(data["photos"][step]["status"], "unavailable")
            self.assertIsNone(data["photos"][step]["file_id"])
        await self.send(CANCEL_BUTTON)
        await self.prepare_af1()
        self.assertNotIn("insole_not_removable", await self.context().get_data())

    async def test_review_calculates_all_statuses(self):
        await self.finish_af1_fixed_insoles()
        photos = dict((await self.context().get_data())["photos"])
        photos["TOP_VIEW"] = make_record(PHOTO_REQUIREMENTS[0], 1, status=PhotoStatus.MISSING)
        photos["HEELS"] = make_record(PHOTO_REQUIREMENTS[3], 4,
                                     status=PhotoStatus.NEEDS_RESHOOT, file_id="bad-photo", reason="wrong_zone")
        await self.context().update_data(photos=photos)
        await self.send("refresh")
        text = self.answer.call_args.args[0]
        for line in ("Получено: 8", "Недоступно: 3", "Пропущено: 1", "Требует пересъёмки: 1",
                     "Вид сверху — пропущено", "Задники — требует пересъёмки"):
            self.assertIn(line, text)
        await self.send(ANALYZE)
        self.assertNotEqual(self.answer.call_args.args[0], PLACEHOLDER)
        await self.send(RETAKE)
        await self.send("Задники — требует пересъёмки")
        await self.send(photo=True)
        self.assertIn("Получено: 9", self.answer.call_args.args[0])
        self.assertIn("Требует пересъёмки: 0", self.answer.call_args.args[0])
        await self.send(RETAKE)
        await self.send("Вид сверху — пропущено")
        await self.send(photo=True)
        self.assertIn("Получено: 10", self.answer.call_args.args[0])

    async def test_validation_precedes_received_and_handles_rejection(self):
        await self.prepare_af1()
        async def reject(requirement, photo):
            self.assertEqual(requirement.id, "TOP_VIEW")
            self.assertTrue(photo.file_id)
            self.assertNotIn("TOP_VIEW", (await self.context().get_data())["photos"])
            return PhotoValidationResult(False, PhotoStatus.NEEDS_RESHOOT,
                                         "wrong_zone", "Переснимите вид сверху.")
        with patch("legitbot.photo_validation.validate_photo", new_callable=AsyncMock) as validator:
            validator.side_effect = reject
            await self.send(photo=True)
            validator.assert_awaited_once()
        data = await self.context().get_data()
        self.assertEqual(data["photos"]["TOP_VIEW"]["status"], "needs_reshoot")
        self.assertEqual(data["photos"]["TOP_VIEW"]["reason"], "wrong_zone")
        self.assertEqual(data["photo_index"], 0)
        self.assertEqual(await self.context().get_state(), AF1.photos.state)
        self.assertEqual(self.answer.call_args_list[-2].args[0], "Переснимите вид сверху.")
        await self.send(photo=True)
        record = (await self.context().get_data())["photos"]["TOP_VIEW"]
        self.assertEqual(record["status"], "received")
        self.assertIsNone(record["reason"])

    async def test_validation_called_on_reshoot_but_not_nonphotos(self):
        from legitbot.photo_validation import validate_photo
        await self.finish_af1()
        await self.send(RETAKE)
        await self.send("Вид сверху")
        with patch("legitbot.photo_validation.validate_photo", wraps=validate_photo) as validator:
            await self.send("not a photo")
            await self.send(photo=True, media_group_id="album")
            validator.assert_not_called()
            await self.send(photo=True)
            validator.assert_awaited_once()
        self.assertEqual(await self.context().get_state(), AF1.review.state)

    async def test_fixed_insoles_button_only_at_top(self):
        await self.prepare_af1()
        await self.send(FIXED_INSOLES)
        data = await self.context().get_data()
        self.assertNotIn("insole_not_removable", data)
        self.assertEqual(data["photo_index"], 0)
        await self.finish_af1()
        self.assertIn("Получено: 13", self.answer.call_args.args[0])
        self.assertIn("Недоступно: 0", self.answer.call_args.args[0])

if __name__ == "__main__":
    unittest.main()
