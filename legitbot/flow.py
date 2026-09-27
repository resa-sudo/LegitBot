"""Пошаговая проверка кроссовок без AI и внешнего хранилища."""

from aiogram import F, Router
from aiogram.filters import Command, CommandStart
from aiogram.fsm.context import FSMContext
from aiogram.fsm.state import State, StatesGroup
from aiogram.types import KeyboardButton, Message, ReplyKeyboardMarkup

CHECK_BUTTON = "👟 Проверить кроссовки"
CANCEL_BUTTON = "Отменить проверку"
BEGIN_BUTTON = "Начать проверку"
ANALYZE_BUTTON = "🔍 Начать анализ"
SKIP_BOX_BUTTON = "Нет коробки"
BRANDS = ("Nike", "Adidas", "New Balance", "Другой бренд")
NIKE_LINES = ("Air Force 1", "Dunk", "Air Jordan", "Air Max", "Other Nike")
PHOTO_STEPS = (
    "Общий вид пары сверху. Поставьте оба кроссовка рядом и снимите сверху целиком.",
    "Внешний вид сбоку. Снимите внешнюю боковую сторону кроссовка целиком.",
    "Вид сзади. Поставьте оба кроссовка пятками к камере и снимите заднюю часть.",
    "Подошва. Переверните кроссовки и снимите подошвы целиком, чтобы был виден рисунок.",
    "Внутренняя бирка левого кроссовка крупным планом. Текст и номера должны быть читаемыми.",
    "Внутренняя бирка правого кроссовка. Снимите крупно, без бликов и размытия.",
    "Стелька сверху. Достаньте стельку и снимите её верхнюю сторону целиком.",
    "Обратная сторона стельки. Переверните стельку и снимите её нижнюю сторону целиком.",
    "Коробка и наклейка на коробке. Снимите коробку так, чтобы наклейка и её текст "
    "были видны. Если коробки нет, нажмите «Нет коробки».",
)


class Check(StatesGroup):
    brand = State()
    line = State()
    model = State()
    confirmation = State()
    photos = State()
    ready = State()


def keyboard(*buttons: str, cancel: bool = False) -> ReplyKeyboardMarkup:
    rows = [[KeyboardButton(text=text)] for text in buttons]
    if cancel:
        rows.append([KeyboardButton(text=CANCEL_BUTTON)])
    return ReplyKeyboardMarkup(keyboard=rows, resize_keyboard=True)


async def start(message: Message, state: FSMContext) -> None:
    await state.clear()
    await message.answer(
        "Привет! Я LegitBot 👟\n\n"
        "Помогу подготовить фотографии кроссовок для проверки. "
        "Для Air Force 1 проверяю техническое качество фото. Подлинность пока не определяю.\n\nНажмите кнопку ниже.",
        reply_markup=keyboard(CHECK_BUTTON),
    )


async def cancel(message: Message, state: FSMContext) -> None:
    await state.clear()
    await message.answer(
        "Проверка отменена. Можно начать заново.",
        reply_markup=keyboard(CHECK_BUTTON),
    )


async def choose_brand(message: Message, state: FSMContext) -> None:
    await state.clear()
    await state.set_state(Check.brand)
    await message.answer(
        "Выберите бренд кроссовок", reply_markup=keyboard(*BRANDS, cancel=True)
    )


async def save_brand(message: Message, state: FSMContext) -> None:
    await state.update_data(brand=message.text, line=None)
    if message.text == "Nike":
        await show_lines(message, state)
    else:
        await ask_model(message, state)


async def ask_model(message: Message, state: FSMContext) -> None:
    data = await state.get_data()
    text = "Напишите точную модель."
    if data.get("line") == "Air Jordan":
        text += "\nПример: Air Jordan 4 Military Black"
    await state.set_state(Check.model)
    await message.answer(text, reply_markup=keyboard(cancel=True))


async def show_lines(message: Message, state: FSMContext) -> None:
    await state.set_state(Check.line)
    await message.answer(
        "Выберите линейку Nike",
        reply_markup=keyboard(*NIKE_LINES, "Назад", cancel=True),
    )


async def save_line(message: Message, state: FSMContext) -> None:
    from .af1_flow import show_models, UNSUPPORTED
    if message.text == "Air Force 1":
        await state.update_data(line="Air Force 1")
        await show_models(message, state)
    else:
        await message.answer(UNSUPPORTED)
        await show_lines(message, state)


async def invalid_line(message: Message, state: FSMContext) -> None:
    if message.text in ("Назад", "Back"):
        await choose_brand(message, state)
    else:
        await show_lines(message, state)


async def back_confirmation(message: Message, state: FSMContext) -> None:
    data = await state.get_data()
    if data.get("brand") == "Nike" and data.get("line") == "Air Force 1":
        from .af1_flow import show_models
        await show_models(message, state)
    else:
        await ask_model(message, state)


async def invalid_brand(message: Message) -> None:
    await message.answer(
        "Выберите бренд кнопкой ниже.", reply_markup=keyboard(*BRANDS, cancel=True)
    )


async def save_model(message: Message, state: FSMContext) -> None:
    model = (message.text or "").strip()
    if not model or len(model) > 150 or model.startswith("/") or model in (
        BEGIN_BUTTON, ANALYZE_BUTTON, SKIP_BOX_BUTTON
    ):
        await message.answer("Напишите модель текстом: от 1 до 150 символов.")
        return
    data = await state.update_data(model=model)
    await state.set_state(Check.confirmation)
    summary = f"Бренд: {data['brand']}"
    if data.get("line"):
        summary += f"\nЛинейка: {data['line']}"
    summary += f"\nМодель: {model}"
    await message.answer(
        summary,
        reply_markup=keyboard(BEGIN_BUTTON, cancel=True),
    )


async def request_photo(message: Message, index: int) -> None:
    buttons = (SKIP_BOX_BUTTON,) if index == len(PHOTO_STEPS) - 1 else ()
    await message.answer(
        f"Фото {index + 1} из {len(PHOTO_STEPS)}\n\n{PHOTO_STEPS[index]}\n\n"
        "Отправьте одну фотографию как фото, не как файл и не альбомом.",
        reply_markup=keyboard(*buttons, cancel=True),
    )


async def begin_photos(message: Message, state: FSMContext) -> None:
    data = await state.get_data()
    if data.get("brand") == "Nike":
        from .af1_flow import begin, show_models
        from .photo_requirements import MODEL
        if data.get("line") == "Air Force 1" and data.get("model") == MODEL:
            await begin(message, state)
        else:
            await show_models(message, state)
        return
    await state.update_data(photos=[], photo_index=0, box_skipped=False)
    await state.set_state(Check.photos)
    await request_photo(message, 0)


async def invalid_confirmation(message: Message) -> None:
    await message.answer(
        "Нажмите «Начать проверку», чтобы перейти к фотографиям.",
        reply_markup=keyboard(BEGIN_BUTTON, cancel=True),
    )


async def finish_photos(message: Message, state: FSMContext) -> None:
    await state.set_state(Check.ready)
    await message.answer(
        "✅ Все фотографии получены.\nПроверка готова к анализу.",
        reply_markup=keyboard(ANALYZE_BUTTON, cancel=True),
    )


async def receive_photo(message: Message, state: FSMContext) -> None:
    # Альбом целиком отклоняется: его снимки нельзя надёжно сопоставить ракурсам.
    if message.media_group_id:
        await message.answer(
            "Отправляйте фотографии по одной, не альбомом. Этот альбом не принят."
        )
        return
    data = await state.get_data()
    index = data["photo_index"]
    photos = list(data["photos"])
    photos.append({"step": index + 1, "file_id": message.photo[-1].file_id})
    await state.update_data(photos=photos, photo_index=index + 1)
    if index + 1 == len(PHOTO_STEPS):
        await finish_photos(message, state)
    else:
        await request_photo(message, index + 1)


async def skip_box(message: Message, state: FSMContext) -> None:
    data = await state.get_data()
    if data["photo_index"] != len(PHOTO_STEPS) - 1:
        await message.answer("Пропустить можно только фотографию коробки на шаге 9.")
        return
    await state.update_data(box_skipped=True, photo_index=len(PHOTO_STEPS))
    await finish_photos(message, state)


async def invalid_photo(message: Message, state: FSMContext) -> None:
    data = await state.get_data()
    await message.answer("На этом шаге нужна фотография. Текст, видео и файлы не принимаются.")
    await request_photo(message, data["photo_index"])


async def analyze(message: Message) -> None:
    await message.answer("AI-анализ подключим на следующем этапе.")


async def invalid_ready(message: Message) -> None:
    await message.answer(
        "Фотографии уже собраны. Нажмите «🔍 Начать анализ».",
        reply_markup=keyboard(ANALYZE_BUTTON, cancel=True),
    )


async def fallback(message: Message) -> None:
    await message.answer(
        "Чтобы начать, нажмите «👟 Проверить кроссовки».",
        reply_markup=keyboard(CHECK_BUTTON),
    )


def create_router() -> Router:
    router = Router()
    # Общие команды регистрируются первыми и работают на любом шаге.
    router.message.register(start, CommandStart())
    router.message.register(cancel, Command("cancel"))
    router.message.register(cancel, F.text == CANCEL_BUTTON)
    router.message.register(choose_brand, F.text == CHECK_BUTTON)
    from .af1_flow import register
    register(router)
    router.message.register(back_confirmation, Check.confirmation, F.text == "Назад")
    router.message.register(save_brand, Check.brand, F.text.in_(BRANDS))
    router.message.register(invalid_brand, Check.brand)
    router.message.register(save_line, Check.line, F.text.in_(NIKE_LINES))
    router.message.register(invalid_line, Check.line)
    router.message.register(save_model, Check.model)
    router.message.register(begin_photos, Check.confirmation, F.text == BEGIN_BUTTON)
    router.message.register(invalid_confirmation, Check.confirmation)
    router.message.register(skip_box, Check.photos, F.text == SKIP_BOX_BUTTON)
    router.message.register(receive_photo, Check.photos, F.photo)
    router.message.register(invalid_photo, Check.photos)
    router.message.register(analyze, Check.ready, F.text == ANALYZE_BUTTON)
    router.message.register(invalid_ready, Check.ready)
    router.message.register(fallback)
    return router
