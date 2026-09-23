"""Shared pagination/filter/sort contract for SaaS list endpoints."""
from __future__ import annotations

from dataclasses import asdict, is_dataclass
from math import ceil
from typing import Any, Sequence
from uuid import UUID

from fastapi import HTTPException

DEFAULT_PAGE_SIZE = 20
MAX_PAGE_SIZE = 100


def validate_filter_tenant_id(value: UUID | None, tenant_id: UUID) -> None:
    if value is not None and value != tenant_id:
        raise HTTPException(status_code=400, detail="INVALID_FILTER")


def paginate(
    items: Sequence[Any],
    *,
    page: int,
    page_size: int,
    sort_by: str,
    sort_order: str,
) -> dict[str, object]:
    if page < 1 or page_size < 1 or page_size > MAX_PAGE_SIZE:
        raise HTTPException(status_code=400, detail="INVALID_PAGINATION")
    if sort_order not in {"asc", "desc"}:
        raise HTTPException(status_code=400, detail="INVALID_SORT")
    try:
        ordered = sorted(items, key=lambda item: getattr(item, sort_by))
    except AttributeError as exc:
        raise HTTPException(status_code=400, detail="INVALID_SORT") from exc
    if sort_order == "desc":
        ordered.reverse()
    total = len(ordered)
    total_pages = ceil(total / page_size) if total else 0
    start = (page - 1) * page_size
    data = ordered[start : start + page_size]
    return {
        "data": [asdict(item) if is_dataclass(item) else item for item in data],
        "pagination": {
            "page": page,
            "page_size": page_size,
            "total": total,
            "total_pages": total_pages,
        },
    }


__all__ = ["DEFAULT_PAGE_SIZE", "MAX_PAGE_SIZE", "paginate", "validate_filter_tenant_id"]
