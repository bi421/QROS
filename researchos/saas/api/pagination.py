"""Shared API pagination/filter/sort contract for tenant-scoped list endpoints."""
from __future__ import annotations

from dataclasses import dataclass
from math import ceil
from typing import Any, Iterable

from fastapi import HTTPException, Request


DEFAULT_PAGE_SIZE = 20
MAX_PAGE_SIZE = 100
ALLOWED_SORT_ORDERS = frozenset({"asc", "desc"})


@dataclass(frozen=True)
class ListQuery:
    page: int
    page_size: int
    sort_by: str
    sort_order: str
    filters: dict[str, str]

    @property
    def offset(self) -> int:
        return (self.page - 1) * self.page_size


@dataclass(frozen=True)
class Pagination:
    page: int
    page_size: int
    total: int

    @property
    def total_pages(self) -> int:
        return ceil(self.total / self.page_size) if self.total else 0


def _bad(code: str, message: str) -> HTTPException:
    exc = HTTPException(status_code=400, detail={"code": code, "message": message})
    return exc


def parse_list_query(
    request: Request,
    *,
    allowed_sort_by: Iterable[str],
    allowed_filters: Iterable[str],
) -> ListQuery:
    """Parse the v1 list contract; never silently accept unknown controls."""
    allowed_sort = set(allowed_sort_by)
    allowed_filter = set(allowed_filters)
    try:
        page = int(request.query_params.get("page", "1"))
        page_size = int(request.query_params.get("page_size", str(DEFAULT_PAGE_SIZE)))
    except ValueError as exc:
        raise _bad("INVALID_FILTER", "page and page_size must be integers") from exc
    if page < 1 or page_size < 1 or page_size > MAX_PAGE_SIZE:
        raise _bad("INVALID_FILTER", "page must be >= 1 and page_size must be between 1 and 100")

    sort_by = request.query_params.get("sort_by", "created_at")
    sort_order = request.query_params.get("sort_order", "desc").lower()
    if sort_by not in allowed_sort:
        raise _bad("INVALID_SORT", f"unsupported sort_by: {sort_by}")
    if sort_order not in ALLOWED_SORT_ORDERS:
        raise _bad("INVALID_SORT", f"unsupported sort_order: {sort_order}")

    filters: dict[str, str] = {}
    for key, value in request.query_params.multi_items():
        if not key.startswith("filter["):
            continue
        if not key.endswith("]") or len(key) <= 8:
            raise _bad("INVALID_FILTER", f"malformed filter: {key}")
        name = key[7:-1]
        if name not in allowed_filter:
            raise _bad("INVALID_FILTER", f"unsupported filter: {name}")
        filters[name] = value

    return ListQuery(page, page_size, sort_by, sort_order, filters)


def envelope(items: list[Any], total: int, query: ListQuery, request_id: str | None) -> dict[str, object]:
    return {
        "data": items,
        "pagination": {
            "page": query.page,
            "page_size": query.page_size,
            "total": total,
            "total_pages": Pagination(query.page, query.page_size, total).total_pages,
        },
        "request_id": request_id,
    }


def sort_items(items: list[Any], *, sort_by: str, sort_order: str) -> list[Any]:
    """Sort a page/result list using a strict attribute/key lookup."""
    def value(item: Any) -> Any:
        if isinstance(item, dict):
            return item.get(sort_by)
        return getattr(item, sort_by, None)
    return sorted(items, key=lambda item: (value(item) is None, value(item)), reverse=sort_order == "desc")
