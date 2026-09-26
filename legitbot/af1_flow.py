"""Сбор и пересъёмка AF1: один обработчик для всех настроенных зон."""
from aiogram import F, Router
from aiogram.fsm.context import FSMContext
from aiogram.fsm.state import State, StatesGroup
from aiogram.types import Message

from .flow import keyboard, Check, BEGIN_BUTTON, show_lines
from .photo_requirements import MODEL, FULL_MODEL, PHOTO_REQUIREMENTS

BACK = "Назад"
NO_BOX = "У меня нет коробки"
ANALYZE = "Начать анализ"
RETAKE = "Переснять фото"
OTHER_MODEL = "Другая Air Force 1"
UNSUPPORTED = ("Эта модель пока находится в разработке.\n"
               "Сейчас полноценная проверка доступна для Nike Air Force 1.")
PLACEHOLDER = ("Все материалы подготовлены для анализа.\n\n"
               "Автоматическая проверка будет подключена на следующем этапе разработки.")


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
        await message.answer(
            f"Бренд: Nike\nЛинейка: Air Force 1\nМодель: {MODEL}\n\n"
            "Сейчас мы только собираем фотографии. Решение о подлинности не принимается.",
            reply_markup=keyboard(BEGIN_BUTTON, BACK, cancel=True))
    else:
        if message.text == OTHER_MODEL:
            await message.answer(UNSUPPORTED)
        await show_models(message, state)


async def begin(message: Message, state: FSMContext) -> None:
    data = await state.get_data()
    # Повторный вход с первого шага сохраняет уже загруженные ракурсы.
    if not isinstance(data.get("photos"), dict):
        await state.update_data(photos={})
    await state.update_data(photo_index=0, retaking=False)
    await state.set_state(AF1.photos)
    await prompt(message, 0)


async def prompt(message: Message, index: int) -> None:
    requirement = PHOTO_REQUIREMENTS[index]
    buttons = [BACK]
    if not requirement.required:
        buttons.insert(0, NO_BOX)
    await message.answer(
        f"Фото {index + 1} из {len(PHOTO_REQUIREMENTS)}\n\n"
        f"Фото {index + 1}/13 — {requirement.title[0].lower() + requirement.title[1:]}\n\n{requirement.instruction}\n\n"
        "Отправьте одно фото, не файл и не альбом.",
        reply_markup=keyboard(*buttons, cancel=True))


def complete(photos: dict) -> bool:
    return all(
        photos.get(r.id, {}).get("file_id") or
        (not r.required and photos.get(r.id, {}).get("missing") is True)
        for r in PHOTO_REQUIREMENTS
    )


async def review(message: Message, state: FSMContext) -> None:
    data = await state.get_data()
    photos = data.get("photos", {})
    if not complete(photos):
        index = next(i for i, r in enumerate(PHOTO_REQUIREMENTS)
                     if not photos.get(r.id, {}).get("file_id")
                     and not (not r.required and photos.get(r.id, {}).get("missing")))
        await state.update_data(photo_index=index, retaking=False)
        await state.set_state(AF1.photos)
        await prompt(message, index)
        return
    await state.update_data(retaking=False)
    await state.set_state(AF1.review)
    count = sum(bool(p.get("file_id")) for p in photos.values())
    missing = "\n\nНаклейка коробки — отсутствует" if photos["BOX_LABEL"]["missing"] else ""
    await message.answer(
        f"Фотографии получены 👟\n\nМодель:\n{FULL_MODEL}\n\n"
        f"Получено фотографий: {count}/13\n\n"
        "Перед анализом проверьте, что фотографии чёткие и все детали хорошо видны."
        + missing, reply_markup=keyboard(ANALYZE, RETAKE, cancel=True))


async def save_photo(message: Message, state: FSMContext, missing: bool = False) -> None:
    data = await state.get_data()
    index = data["photo_index"]
    requirement = PHOTO_REQUIREMENTS[index]
    photos = dict(data.get("photos", {}))
    photos[requirement.id] = {
        "step_id": requirement.id,
        "file_id": None if missing else message.photo[-1].file_id,
        "analysis_zone": requirement.analysis_zone,
        "step_number": index + 1,
        "missing": missing,
    }
    await state.update_data(photos=photos)
    if data.get("retaking") or index == len(PHOTO_REQUIREMENTS) - 1:
        await review(message, state)
    else:
        await state.update_data(photo_index=index + 1)
        await prompt(message, index + 1)


async def photo_input(message: Message, state: FSMContext) -> None:
    data = await state.get_data()
    index = data["photo_index"]
    if message.text == BACK:
        if data.get("retaking"):
            await retake_menu(message, state)
        elif index == 0:
            await state.set_state(Check.confirmation)
            await message.answer(
                f"Модель: {FULL_MODEL}",
                reply_markup=keyboard(BEGIN_BUTTON, BACK, cancel=True))
        else:
            await state.update_data(photo_index=index - 1)
            await prompt(message, index - 1)
    elif message.text == NO_BOX and not PHOTO_REQUIREMENTS[index].required:
        await save_photo(message, state, missing=True)
    elif message.photo and not message.media_group_id:
        await save_photo(message, state)
    else:
        await message.answer("На этом этапе нужна фотография.")
        await prompt(message, index)


def zone_label(requirement, photos: dict) -> str:
    suffix = " — отсутствует" if photos.get(requirement.id, {}).get("missing") else ""
    return requirement.title + suffix


async def retake_menu(message: Message, state: FSMContext) -> None:
    data = await state.get_data()
    await state.set_state(AF1.retake)
    await message.answer(
        "Выберите фото, которое хотите переснять:",
        reply_markup=keyboard(
            *(zone_label(r, data["photos"]) for r in PHOTO_REQUIREMENTS),
            BACK, cancel=True))


async def select_retake(message: Message, state: FSMContext) -> None:
    if message.text == BACK:
        await review(message, state)
        return
    data = await state.get_data()
    for index, requirement in enumerate(PHOTO_REQUIREMENTS):
        if message.text == zone_label(requirement, data["photos"]):
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
            await review(message, state)
    else:
        await review(message, state)


def register(router: Router) -> None:
    router.message.register(select_model, AF1.model)
    router.message.register(photo_input, AF1.photos)
    router.message.register(select_retake, AF1.retake)
    router.message.register(review_input, AF1.review)
