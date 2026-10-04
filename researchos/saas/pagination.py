"""Shared public-list pagination, filtering, and sorting contract."""
from __future__ import annotations

from collections.abc import Mapping, Sequence
from dataclasses import asdict, dataclass, is_dataclass
from math import ceil
from typing import Any
from uuid import UUID

from fastapi import HTTPException

DEFAULT_PAGE = 1
DEFAULT_PAGE_SIZE = 20
MAX_PAGE_SIZE = 100
SORT_ORDERS = frozenset({"asc", "desc"})


class PaginationParameterError(ValueError):
    def __init__(self, message: str, *, code: str = "INVALID_PAGINATION") -> None:
        super().__init__(message)
        self.code = code


@dataclass(frozen=True)
class ListQuery:
    page: int = DEFAULT_PAGE
    page_size: int = DEFAULT_PAGE_SIZE
    sort_by: str = "created_at"
    sort_order: str = "desc"
    status: str | None = None
    tenant_id: str | None = None

    @property
    def offset(self) -> int:
        return (self.page - 1) * self.page_size


def parse_list_query(
    *,
    page: str = "1",
    page_size: str = "20",
    sort_by: str = "created_at",
    sort_order: str = "desc",
    status: str | None = None,
    tenant_id: str | None = None,
    allowed_sort_fields: frozenset[str],
) -> ListQuery:
    try:
        parsed_page = int(page)
        parsed_page_size = int(page_size)
    except (TypeError, ValueError) as exc:
        raise PaginationParameterError("page and page_size must be integers") from exc
    if parsed_page < 1:
        raise PaginationParameterError("page must be >= 1")
    if parsed_page_size < 1 or parsed_page_size > MAX_PAGE_SIZE:
        raise PaginationParameterError(f"page_size must be between 1 and {MAX_PAGE_SIZE}")
    normalized_sort = sort_by.strip()
    if normalized_sort not in allowed_sort_fields:
        raise PaginationParameterError(f"invalid sort field: {normalized_sort}", code="INVALID_SORT")
    normalized_order = sort_order.strip().lower()
    if normalized_order not in SORT_ORDERS:
        raise PaginationParameterError("sort_order must be 'asc' or 'desc'", code="INVALID_SORT_ORDER")
    normalized_status = status.strip() if status is not None else None
    normalized_tenant_id = tenant_id.strip() if tenant_id is not None else None
    if normalized_tenant_id is not None and len(normalized_tenant_id) > 128:
        raise PaginationParameterError("tenant_id filter is too long", code="INVALID_FILTER")
    return ListQuery(parsed_page, parsed_page_size, normalized_sort, normalized_order, normalized_status or None, normalized_tenant_id or None)


def validate_filter_keys(filters: Mapping[str, object], *, allowed: frozenset[str]) -> None:
    for key in filters:
        if key not in allowed:
            raise PaginationParameterError(f"invalid filter: {key}", code="INVALID_FILTER")


def pagination_envelope(
    *,
    data: list[object],
    page: int,
    page_size: int,
    total: int,
    request_id: str | None = None,
) -> dict[str, object]:
    if page < 1 or page_size < 1 or page_size > MAX_PAGE_SIZE:
        raise PaginationParameterError("invalid pagination")
    if total < 0:
        raise PaginationParameterError("total must be non-negative")
    return {
        "data": data,
        "pagination": {"page": page, "page_size": page_size, "total": total, "total_pages": ceil(total / page_size) if total else 0},
        "request_id": request_id,
    }


def paginate(
    items: Sequence[Any],
    *,
    page: int,
    page_size: int,
    sort_by: str,
    sort_order: str,
    request_id: str | None = None,
) -> dict[str, object]:
    if page < 1 or page_size < 1 or page_size > MAX_PAGE_SIZE:
        raise HTTPException(status_code=400, detail="INVALID_PAGINATION")
    if sort_order not in SORT_ORDERS:
        raise HTTPException(status_code=400, detail="INVALID_SORT")
    try:
        ordered = sorted(items, key=lambda item: getattr(item, sort_by))
    except AttributeError as exc:
        raise HTTPException(status_code=400, detail="INVALID_SORT") from exc
    if sort_order == "desc":
        ordered.reverse()
    total = len(ordered)
    data = ordered[(page - 1) * page_size : page * page_size]
    return pagination_envelope(
        data=[asdict(item) if is_dataclass(item) else item for item in data],
        page=page,
        page_size=page_size,
        total=total,
        request_id=request_id,
    )


def validate_filter_tenant_id(value: UUID | None, tenant_id: UUID) -> None:
    if value is not None and value != tenant_id:
        raise HTTPException(status_code=400, detail="INVALID_FILTER")


__all__ = ["DEFAULT_PAGE", "DEFAULT_PAGE_SIZE", "MAX_PAGE_SIZE", "SORT_ORDERS", "ListQuery", "PaginationParameterError", "pagination_envelope", "parse_list_query", "paginate", "validate_filter_keys", "validate_filter_tenant_id"]
