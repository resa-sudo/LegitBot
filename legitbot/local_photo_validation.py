"""Локальные эвристики качества: не распознают предмет, ракурс или подлинность."""
from dataclasses import dataclass
from io import BytesIO
import warnings

from PIL import Image, ImageChops, ImageFilter, ImageStat, UnidentifiedImageError

from .photo_records import PhotoStatus


@dataclass(frozen=True)
class QualityThresholds:
    min_side: int = 480
    max_pixels: int = 25_000_000
    max_bytes: int = 12 * 1024 * 1024
    analysis_side: int = 768
    dark_mean: float = 25.0
    dark_pixel: int = 20
    bright_mean: float = 245.0
    bright_pixel: int = 250
    extreme_fraction: float = 0.95
    min_contrast: float = 8.0
    blur_radius: float = 1.0
    min_detail: float = 1.0


THRESHOLDS = QualityThresholds()


def validate_local(image: bytes, thresholds: QualityThresholds = THRESHOLDS):
    from .photo_validation import PhotoValidationResult

    def reject(reason, message):
        return PhotoValidationResult(False, PhotoStatus.NEEDS_RESHOOT,
                                     reason, message, quality_ok=False)

    if not image or len(image) > thresholds.max_bytes:
        return reject("invalid_image", "Не удалось прочитать фото. Отправьте его заново как фотографию.")
    try:
        with warnings.catch_warnings():
            warnings.simplefilter("error", Image.DecompressionBombWarning)
            with Image.open(BytesIO(image)) as source:
                width, height = source.size
                if width * height > thresholds.max_pixels:
                    return reject("image_too_large", "Фото слишком большое. Отправьте обычное фото через Telegram.")
                source.load()  # Полное декодирование, не только чтение заголовка.
                if min(width, height) < thresholds.min_side:
                    return reject("resolution_too_low",
                                  f"Фото слишком маленькое. Нужен снимок не менее {thresholds.min_side} пикселей по каждой стороне.")
                gray = source.convert("L")
        try:
            gray.thumbnail((thresholds.analysis_side, thresholds.analysis_side), Image.Resampling.LANCZOS)
            stats = ImageStat.Stat(gray)
            mean = stats.mean[0]
            histogram = gray.histogram()
            pixels = gray.width * gray.height
            dark_fraction = sum(histogram[:thresholds.dark_pixel + 1]) / pixels
            bright_fraction = sum(histogram[thresholds.bright_pixel:]) / pixels
            if mean < thresholds.dark_mean or dark_fraction >= thresholds.extreme_fraction:
                return reject("too_dark", "Фото слишком тёмное. Сделайте снимок при хорошем освещении.")
            if mean > thresholds.bright_mean or bright_fraction >= thresholds.extreme_fraction:
                return reject("too_bright", "Фото сильно пересвечено. Уберите блики и уменьшите яркость освещения.")
            with gray.filter(ImageFilter.GaussianBlur(thresholds.blur_radius)) as smooth:
                with ImageChops.difference(gray, smooth) as difference:
                    detail = ImageStat.Stat(difference).mean[0]
            if stats.stddev[0] < thresholds.min_contrast or detail < thresholds.min_detail:
                return reject("too_blurry",
                              "Фото слишком размыто. Сделайте снимок ещё раз и держите камеру неподвижно.")
        finally:
            gray.close()
    except (UnidentifiedImageError, OSError, ValueError, SyntaxError,
            Image.DecompressionBombError, Image.DecompressionBombWarning):
        return reject("invalid_image", "Не удалось прочитать фото. Отправьте его заново как фотографию.")
    return PhotoValidationResult(
        True, PhotoStatus.RECEIVED, user_message="Техническое качество фото подходит.",
        quality_ok=True, detected_zone=None, confidence=None)
