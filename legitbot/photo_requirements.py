"""Требования к снимкам AF1: только сбор материалов, без решений о подлинности."""
from dataclasses import dataclass, replace


@dataclass(frozen=True)
class PhotoRequirement:
    id: str
    title: str
    required: bool
    analysis_zone: str
    instruction: str
    validation_instruction: str = ""
    retake_instruction: str = ""


MODEL = "Air Force 1 Low '07 White"
FULL_MODEL = "Nike " + MODEL
AF1_PHOTO_REQUIREMENTS = (
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
        "Если обе стельки легко вынимаются, достаньте их и сфотографируйте сверху.\n\n"
        "Если стельки приклеены или не вынимаются, не тяните их силой. "
        "Нажмите «Стельки не снимаются» и сфотографируйте их сверху внутри обуви."),
    PhotoRequirement("INSOLES_BOTTOM", "Обратная сторона стелек", True, "insoles_bottom",
        "Если стельки легко снимаются, переверните обе и сфотографируйте обратную сторону.\n\n"
        "Не отклеивайте и не вытягивайте их силой. Если они не снимаются, "
        "нажмите «Назад» и выберите «Стельки не снимаются» на шаге 8."),
    PhotoRequirement("UNDER_INSOLE", "Под стелькой", True, "under_insole",
        "Только если стелька легко снимается, сфотографируйте внутреннюю прошивку "
        "и материал внутри кроссовка. Не отклеивайте и не вытягивайте стельку силой.\n\n"
        "Если она не снимается, вернитесь кнопкой «Назад» на шаг 8 "
        "и выберите «Стельки не снимаются».\n\n"
        "Это важная часть проверки."),
    PhotoRequirement("OUTSOLE", "Подошва", True, "outsole",
        "Сделайте чёткое фото всей подошвы одного кроссовка."),
    PhotoRequirement("DUBRAE", "Металлическая вставка AF1", True, "dubrae",
        "Сделайте крупное фото металлической детали AF1 на шнурках."),
    PhotoRequirement("BOX_LABEL", "Наклейка коробки", False, "box_label",
        "Сделайте крупное фото наклейки на коробке.\n\n"
        "Артикул, размер и штрихкод должны читаться."),
)

# Исключения относятся только к текущему набору требований AF1.
AF1_INSOLE_REMOVAL_ZONES = frozenset({"INSOLES_BOTTOM", "UNDER_INSOLE"})

AF1_VALIDATION_RULES = {'TOP_VIEW': ['Both whole sneakers together viewed from above; shoes fully in frame, shape and '
              'upper details clear.',
              'Сфотографируйте оба кроссовка целиком строго сверху.'],
 'LEFT_OUTER_SIDE': ['Outer lateral side of the left sneaker, full side silhouette and Swoosh area '
                     'visible in a side-on view. Do not reject solely on uncertain left/right '
                     'orientation.',
                     'Сфотографируйте внешний бок левого кроссовка целиком.'],
 'RIGHT_OUTER_SIDE': ['Outer lateral side of the right sneaker, full side silhouette and Swoosh '
                      'area visible in a side-on view. Do not reject solely on uncertain '
                      'left/right orientation.',
                      'Сфотографируйте внешний бок правого кроссовка целиком.'],
 'HEELS': ['Rear view of both sneakers. Rear heel panels and Nike Air embroidery area must be '
           'clearly visible. A side view, keyboard or distant full shoe is not sufficient. Judge '
           'visibility, not logo authenticity.',
           'Сфотографируйте оба задника сзади, чтобы были видны вышивка и форма пяток.'],
 'TOE_BOX': ['Close top view of toe box; perforations, stitching and toe shape clearly '
             'distinguishable. Reject a distant whole shoe if toe detail cannot be inspected.',
             'Сделайте крупное фото носовой части сверху, чтобы были видны отверстия и швы.'],
 'TONGUE': ['Close-up of sneaker tongue and Nike Air Force 1 logo area, sufficiently sharp to '
            'inspect the visible print or stitching.',
            'Сфотографируйте язычок и область логотипа крупным планом.'],
 'SIZE_TAG': ['Internal size label shown close-up and in focus; letters, numbers, SKU and QR area '
              'inspectable. Reject unreadable blurred or too-distant text. Do not check SKU '
              'validity or authenticity.',
              'Сделайте крупное резкое фото внутренней бирки с читаемыми буквами и цифрами.'],
 'INSOLES_TOP': ['Upper surface of both insoles visibly inspectable. Either removed insoles OR '
                 'insoles still inside shoes are equally acceptable; do not require removal.',
                 'Сфотографируйте верх стелек; несъёмные стельки снимайте внутри обуви.'],
 'INSOLES_BOTTOM': ['Underside surfaces of both removed insoles, material and texture visible. '
                    'Upper printed faces are the wrong zone.',
                    'Сфотографируйте обратную сторону уже вынутых стелек. Не вытягивайте стельки '
                    'силой.'],
 'UNDER_INSOLE': ['Interior footbed beneath an already removed insole; internal stitching and base '
                  'material clearly visible. A photo with insole covering the footbed does not '
                  'match.',
                  'Сфотографируйте материал и прошивку под уже вынутой стелькой. Не применяйте '
                  'силу.'],
 'OUTSOLE': ['Entire bottom outsole of one sneaker, tread pattern and sole perimeter clearly '
             'visible. A side view of the midsole does not match.',
             'Сфотографируйте всю подошву снизу, чтобы был виден рисунок протектора.'],
 'DUBRAE': ['Close-up of the metal AF1 lace dubrae on laces, detail and lettering area visible. '
            'Whole shoe from a distance is insufficient. Do not assess whether metal piece is '
            'authentic.',
            'Сделайте крупное фото металлической вставки AF1 на шнурках.'],
 'BOX_LABEL': ['Close-up of shoe box product label: SKU/article number, size and barcode areas '
               'visible and text readable. Plain box without label or unreadable label is '
               'insufficient.',
               'Сфотографируйте наклейку коробки крупно, чтобы читались артикул, размер и '
               'штрихкод.']}

AF1_PHOTO_REQUIREMENTS = tuple(
    replace(requirement, validation_instruction=AF1_VALIDATION_RULES[requirement.id][0],
            retake_instruction=AF1_VALIDATION_RULES[requirement.id][1])
    for requirement in AF1_PHOTO_REQUIREMENTS
)
