"""Требования к снимкам AF1: только сбор материалов, без решений о подлинности."""
from dataclasses import dataclass


@dataclass(frozen=True)
class PhotoRequirement:
    id: str
    title: str
    required: bool
    analysis_zone: str
    instruction: str


MODEL = "Air Force 1 Low '07 White"
FULL_MODEL = "Nike " + MODEL
PHOTO_REQUIREMENTS = (
    PhotoRequirement("TOP_VIEW", "Вид сверху", True, "top_view",
        "Поставьте оба кроссовка рядом и сфотографируйте их строго сверху.\n\n"
        "В кадре должны полностью помещаться оба кроссовка."),
    PhotoRequirement("LEFT_OUTER_SIDE", "Внешний бок левого кроссовка", True, "left_outer_side",
        "Сфотографируйте левый кроссовок строго сбоку.\n"
        "Логотип Swoosh и вся боковая часть должны быть хорошо видны."),
    PhotoRequirement("RIGHT_OUTER_SIDE", "Внешний бок правого кроссовка", True, "right_outer_side",
        "Сфотографируйте правый кроссовок строго сбоку.\n"
        "Логотип Swoosh и вся боковая часть должны быть хорошо видны."),
    PhotoRequirement("HEELS", "Задники", True, "heels",
        "Поставьте оба кроссовка рядом задней частью к камере.\n\n"
        "Надписи NIKE AIR, вышивка и форма задника должны быть хорошо видны."),
    PhotoRequirement("TOE_BOX", "Носовая часть", True, "toe_box",
        "Сделайте крупное фото toe box сверху.\n\n"
        "Перфорация и швы должны быть резкими и хорошо различимыми."),
    PhotoRequirement("TONGUE", "Язычок", True, "tongue",
        "Сделайте крупное фото язычка и логотипа Nike Air Force 1."),
    PhotoRequirement("SIZE_TAG", "Внутренняя бирка", True, "size_tag",
        "Сделайте максимально крупное и резкое фото бирки с размером.\n\n"
        "Все буквы, цифры, SKU и QR-код должны читаться."),
    PhotoRequirement("INSOLES_TOP", "Стельки сверху", True, "insoles_top",
        "Достаньте обе стельки и сфотографируйте их сверху."),
    PhotoRequirement("INSOLES_BOTTOM", "Обратная сторона стелек", True, "insoles_bottom",
        "Переверните обе стельки и сфотографируйте обратную сторону."),
    PhotoRequirement("UNDER_INSOLE", "Под стелькой", True, "under_insole",
        "Снимите стельку и сфотографируйте внутреннюю прошивку и материал внутри кроссовка.\n\n"
        "Это важная часть проверки."),
    PhotoRequirement("OUTSOLE", "Подошва", True, "outsole",
        "Сделайте чёткое фото всей подошвы одного кроссовка."),
    PhotoRequirement("DUBRAE", "Металлическая вставка AF1", True, "dubrae",
        "Сделайте крупное фото металлической детали AF1 на шнурках."),
    PhotoRequirement("BOX_LABEL", "Наклейка коробки", False, "box_label",
        "Сделайте крупное фото наклейки на коробке.\n\n"
        "Артикул, размер и штрихкод должны читаться."),
)
