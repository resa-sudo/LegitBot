"""Локальная заглушка проверки снимка. Содержимое фото пока не анализируется."""
from dataclasses import dataclass

from aiogram.types import PhotoSize

from .photo_records import PhotoStatus
from .photo_requirements import PhotoRequirement


@dataclass(frozen=True)
class PhotoValidationResult:
    accepted: bool
    status: PhotoStatus
    reason: str | None = None
    user_message: str | None = None


async def validate_photo(requirement: PhotoRequirement, photo: PhotoSize) -> PhotoValidationResult:
    """Принимает Telegram-фото без скачивания и внешних API.

    Будущая реализация сможет вернуть accepted=False, needs_reshoot,
    машинную причину и понятную пользователю подсказку.
    """
    return PhotoValidationResult(accepted=True, status=PhotoStatus.RECEIVED)
