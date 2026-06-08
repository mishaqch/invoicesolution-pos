"""Project-wide DRF pagination.

PageNumberPagination that lets the client pick a page size via `?page_size=N`
(capped), so list UIs — e.g. the admin-web Products table, which now spans
thousands of rows — can offer a "rows per page" control without each viewset
re-declaring it. Default + cap are conservative to protect the DB on the slow
single-VPS deploy.
"""

from __future__ import annotations

from rest_framework.pagination import PageNumberPagination


class StandardPagination(PageNumberPagination):
    page_size = 50
    page_size_query_param = "page_size"
    max_page_size = 200
