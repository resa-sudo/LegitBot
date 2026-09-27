"""Статусы материалов; ни один статус не является оценкой подлинности."""
from collections import Counter
from enum import StrEnum
from typing import TypedDict

from .photo_requirements import PhotoRequirement


class PhotoStatus(StrEnum):
    RECEIVED = "received"
    UNAVAILABLE = "unavailable"
    MISSING = "missing"
    NEEDS_RESHOOT = "needs_reshoot"


class PhotoRecord(TypedDict):
    step_id: str
    analysis_zone: str
    step_number: int
    file_id: str | None
    status: str
    reason: str | None


def make_record(requirement: PhotoRequirement, number: int, *,
                status: PhotoStatus, file_id: str | None = None,
                reason: str | None = None) -> PhotoRecord:
    if status == PhotoStatus.RECEIVED and not file_id:
        raise ValueError("Received photo must have a file_id")
    if status in (PhotoStatus.UNAVAILABLE, PhotoStatus.MISSING):
        file_id = None
    return PhotoRecord(step_id=requirement.id, analysis_zone=requirement.analysis_zone,
                       step_number=number, file_id=file_id, status=status.value, reason=reason)


def summary_counts(requirements: tuple[PhotoRequirement, ...], photos: dict) -> dict[str, int]:
    counts = Counter({status.value: 0 for status in PhotoStatus})
    for requirement in requirements:
        record = photos.get(requirement.id, {})
        status = record.get("status", PhotoStatus.MISSING)
        if status == PhotoStatus.RECEIVED and not record.get("file_id"):
            status = PhotoStatus.MISSING
        counts[status if status in PhotoStatus else PhotoStatus.MISSING] += 1
    return dict(counts)
