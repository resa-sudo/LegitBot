"""Сбор и пересъёмка AF1: один обработчик для всех настроенных зон."""
import asyncio
import logging
from io import BytesIO

from aiogram import Router
from aiogram.fsm.context import FSMContext
from aiogram.fsm.state import State, StatesGroup
from aiogram.types import Message

from .flow import keyboard, Check, BEGIN_BUTTON, show_lines
from .photo_requirements import (
    MODEL, FULL_MODEL, AF1_PHOTO_REQUIREMENTS as PHOTO_REQUIREMENTS,
    AF1_INSOLE_REMOVAL_ZONES,
)
from .photo_records import PhotoStatus, make_record, summary_counts
from . import photo_validation

BACK = "Назад"
NO_BOX = "У меня нет коробки"
FIXED_INSOLES = "Стельки не снимаются"
ANALYZE = "Начать анализ"
RETAKE = "Переснять фото"
OTHER_MODEL = "Другая Air Force 1"
UNSUPPORTED = ("Эта модель пока находится в разработке.\n"
               "Сейчас полноценная проверка доступна для Nike Air Force 1.")
PLACEHOLDER = ("Все материалы подготовлены для анализа.\n\n"
               "Автоматическая проверка будет подключена на следующем этапе разработки.")
REASONS = {
    "insole_not_removable": "стельки не снимаются",
    "no_box": "нет коробки",
}
STATUS_LABELS = {
    "received": "получено",
    "unavailable": "недоступно",
    "missing": "пропущено",
    "needs_reshoot": "требует пересъёмки",
}


class AF1(StatesGroup):
    model = State()
    photos = State()
    review = State()
    retake = State()


async def show_models(message: Message, state: FSMContext) -> None:
    await state.set_state(AF1.model)
    await message.answer("Выберите модель:",
                         reply_markup=keyboard(MODEL, OTHER_MODEL, BACK, cancel=True))


async def select_model(message: Message, state: FSMContext) -> None:
    if message.text == BACK:
        await state.update_data(line=None, model=None)
        await show_lines(message, state)
    elif message.text == MODEL:
        await state.update_data(brand="Nike", line="Air Force 1", model=MODEL)
        await state.set_state(Check.confirmation)
        validation_notice = (
            "Фото передаются OpenAI для проверки ракурса и качества."
            if photo_validation.get_provider() == "openai" else
            "Фото проверяются локально только на техническое качество, без распознавания ракурса."
        )
        await message.answer(
            f"Бренд: Nike\nЛинейка: Air Force 1\nМодель: {MODEL}\n\n"
            f"{validation_notice} Решение о подлинности не принимается.",
            reply_markup=keyboard(BEGIN_BUTTON, BACK, cancel=True))
    else:
        if message.text == OTHER_MODEL:
            await message.answer(UNSUPPORTED)
        await show_models(message, state)


async def begin(message: Message, state: FSMContext) -> None:
    data = await state.get_data()
    if not isinstance(data.get("photos"), dict):
        await state.update_data(photos={})
    await state.update_data(photo_index=0, retaking=False)
    await state.set_state(AF1.photos)
    await prompt(message, 0)


async def prompt(message: Message, index: int) -> None:
    requirement = PHOTO_REQUIREMENTS[index]
    buttons = [BACK]
    if requirement.id == "BOX_LABEL":
        buttons.insert(0, NO_BOX)
    if requirement.id == "INSOLES_TOP":
        buttons.insert(0, FIXED_INSOLES)
    await message.answer(
        f"Фото {index + 1} из {len(PHOTO_REQUIREMENTS)}\n\n"
        f"Фото {index + 1}/13 — {requirement.title[0].lower() + requirement.title[1:]}\n\n{requirement.instruction}\n\n"
        "Отправьте одно фото, не файл и не альбом.",
        reply_markup=keyboard(*buttons, cancel=True))


def applicable(index: int, data: dict) -> bool:
    return not (data.get("insole_not_removable") and
                PHOTO_REQUIREMENTS[index].id in AF1_INSOLE_REMOVAL_ZONES)


def complete(photos: dict) -> bool:
    """Завершение сбора, а не полнота доказательств или подлинность."""
    for requirement in PHOTO_REQUIREMENTS:
        record = photos.get(requirement.id, {})
        if record.get("status") == PhotoStatus.RECEIVED and record.get("file_id"):
            continue
        if record.get("status") == PhotoStatus.UNAVAILABLE:
            if requirement.id == "BOX_LABEL" and record.get("reason") == "no_box":
                continue
            if requirement.id in AF1_INSOLE_REMOVAL_ZONES and record.get("reason") == "insole_not_removable":
                continue
        return False
    return True


async def review(message: Message, state: FSMContext) -> None:
    data = await state.get_data()
    photos = data.get("photos", {})
    await state.update_data(retaking=False)
    await state.set_state(AF1.review)
    counts = summary_counts(PHOTO_REQUIREMENTS, photos)
    problems = []
    for requirement in PHOTO_REQUIREMENTS:
        record = photos.get(requirement.id, {})
        status = record.get("status", "missing")
        if status != PhotoStatus.RECEIVED or not record.get("file_id"):
            label = STATUS_LABELS.get(status, "пропущено")
            if status == PhotoStatus.RECEIVED:
                label = "пропущено"
            reason = REASONS.get(record.get("reason"))
            problems.append(f"• {requirement.title} — {label}" + (f" ({reason})" if reason else ""))
    details = "\n\n" + "\n".join(problems) if problems else ""
    await message.answer(
        f"Фотографии собраны 👟\n\nМодель:\n{FULL_MODEL}\n\n"
        f"Получено: {counts['received']}\n"
        f"Недоступно: {counts['unavailable']}\n"
        f"Пропущено: {counts['missing']}\n"
        f"Требует пересъёмки: {counts['needs_reshoot']}"
        + details + "\n\nПеред анализом проверьте, что фотографии чёткие и все детали хорошо видны.",
        reply_markup=keyboard(ANALYZE, RETAKE, cancel=True))


async def advance(message: Message, state: FSMContext) -> None:
    data = await state.get_data()
    if not data.get("retaking"):
        index = next((i for i in range(data["photo_index"] + 1, len(PHOTO_REQUIREMENTS))
                      if applicable(i, data)), None)
        if index is not None:
            await state.update_data(photo_index=index)
            await prompt(message, index)
            return
    await review(message, state)


async def save_photo(message: Message, state: FSMContext) -> None:
    data = await state.get_data()
    index = data["photo_index"]
    requirement = PHOTO_REQUIREMENTS[index]
    # Telegram-фото скачивается только в память, без URL с токеном в OpenAI.
    try:
        photo = message.photo[-1]
        if photo.file_size and photo.file_size > photo_validation.MAX_IMAGE_BYTES:
            raise ValueError("Image too large")
        with BytesIO() as buffer:
            async with asyncio.timeout(20):
                await message.bot.download(photo, destination=buffer, timeout=15)
            image = buffer.getvalue()
        if not image or len(image) > photo_validation.MAX_IMAGE_BYTES:
            raise ValueError("Invalid downloaded image size")
        result = await photo_validation.validate_photo(requirement, image)
        del image
    except Exception as error:
        logging.getLogger(__name__).warning("Photo download/validation failed (%s)", type(error).__name__)
        result = photo_validation.unavailable_result()
    if result.accepted != (result.status == PhotoStatus.RECEIVED):
        result = photo_validation.unavailable_result()
    if result.retryable:
        # Сетевой сбой не портит ранее принятый снимок при пересъёмке.
        await message.answer(result.user_message)
        await prompt(message, index)
        return
    photos = dict(data.get("photos", {}))
    photos[requirement.id] = make_record(
        requirement, index + 1, file_id=message.photo[-1].file_id,
        status=result.status, reason=result.reason)
    photos[requirement.id]["validation"] = {
        "detected_zone": result.detected_zone,
        "quality_ok": result.quality_ok,
        "confidence": result.confidence,
    }
    await state.update_data(photos=photos)
    if result.user_message:
        await message.answer(result.user_message)
    if not result.accepted:
        if not result.user_message:
            await message.answer("Пожалуйста, переснимите эту зону.")
        await prompt(message, index)
        return
    await advance(message, state)


async def mark_no_box(message: Message, state: FSMContext) -> None:
    data = await state.get_data()
    index = data["photo_index"]
    photos = dict(data.get("photos", {}))
    photos["BOX_LABEL"] = make_record(
        PHOTO_REQUIREMENTS[index], index + 1,
        status=PhotoStatus.UNAVAILABLE, reason="no_box")
    await state.update_data(photos=photos)
    await advance(message, state)


async def mark_fixed_insoles(message: Message, state: FSMContext) -> None:
    data = await state.get_data()
    photos = dict(data.get("photos", {}))
    for index, requirement in enumerate(PHOTO_REQUIREMENTS):
        if requirement.id in AF1_INSOLE_REMOVAL_ZONES:
            photos[requirement.id] = make_record(
                requirement, index + 1, status=PhotoStatus.UNAVAILABLE,
                reason="insole_not_removable")
    await state.update_data(photos=photos, insole_not_removable=True)
    await message.answer(
        "Не отклеивайте и не вытягивайте стельки силой. "
        "Сфотографируйте их сверху внутри обуви. "
        "Обратную сторону и пространство под стелькой отметим как недоступные.")
    # Верх стельки остаётся обязательным, два следующих ракурса будут пропущены.
    await prompt(message, data["photo_index"])


async def photo_input(message: Message, state: FSMContext) -> None:
    data = await state.get_data()
    index = data["photo_index"]
    requirement = PHOTO_REQUIREMENTS[index]
    if message.text == BACK:
        if data.get("retaking"):
            await retake_menu(message, state)
        else:
            previous = next((i for i in range(index - 1, -1, -1) if applicable(i, data)), None)
            if previous is None:
                await state.set_state(Check.confirmation)
                await message.answer(
                    f"Модель: {FULL_MODEL}",
                    reply_markup=keyboard(BEGIN_BUTTON, BACK, cancel=True))
            else:
                await state.update_data(photo_index=previous)
                await prompt(message, previous)
    elif message.text == FIXED_INSOLES and requirement.id == "INSOLES_TOP":
        await mark_fixed_insoles(message, state)
    elif message.text == NO_BOX and requirement.id == "BOX_LABEL":
        await mark_no_box(message, state)
    elif message.photo and not message.media_group_id:
        await save_photo(message, state)
    else:
        await message.answer("На этом этапе нужна фотография.")
        await prompt(message, index)


def zone_label(requirement, photos: dict) -> str:
    status = photos.get(requirement.id, {}).get("status", "missing")
    suffix = "" if status == PhotoStatus.RECEIVED else " — " + STATUS_LABELS.get(status, "пропущено")
    return requirement.title + suffix


async def retake_menu(message: Message, state: FSMContext) -> None:
    data = await state.get_data()
    await state.set_state(AF1.retake)
    await message.answer(
        "Выберите фото, которое хотите переснять:",
        reply_markup=keyboard(
            *(zone_label(r, data.get("photos", {})) for r in PHOTO_REQUIREMENTS),
            BACK, cancel=True))


async def select_retake(message: Message, state: FSMContext) -> None:
    if message.text == BACK:
        await review(message, state)
        return
    data = await state.get_data()
    for index, requirement in enumerate(PHOTO_REQUIREMENTS):
        if message.text == zone_label(requirement, data.get("photos", {})):
            if not applicable(index, data):
                await message.answer(
                    "Эта зона недоступна: стельки не снимаются. "
                    "Не отклеивайте их и не применяйте силу.")
                await retake_menu(message, state)
                return
            await state.update_data(photo_index=index, retaking=True)
            await state.set_state(AF1.photos)
            await prompt(message, index)
            return
    await retake_menu(message, state)


async def review_input(message: Message, state: FSMContext) -> None:
    if message.text == RETAKE:
        await retake_menu(message, state)
    elif message.text == ANALYZE:
        data = await state.get_data()
        if complete(data.get("photos", {})):
            await message.answer(PLACEHOLDER)
        else:
            await message.answer("Есть пропущенные фото или снимки, требующие пересъёмки. Выберите «Переснять фото».")
            await review(message, state)
    else:
        await review(message, state)


def register(router: Router) -> None:
    router.message.register(select_model, AF1.model)
    router.message.register(photo_input, AF1.photos)
    router.message.register(select_retake, AF1.retake)
    router.message.register(review_input, AF1.review)
