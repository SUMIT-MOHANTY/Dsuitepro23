"""
Core Pagination Classes for Enterprise LMS
Provides standardized pagination for DRF API responses.
"""

from rest_framework.pagination import LimitOffsetPagination, PageNumberPagination
from rest_framework.response import Response


class StandardResultsSetPagination(LimitOffsetPagination):
    """
    Standard pagination class using limit/offset.
    Default: 20 items, Max: 100 items
    """
    default_limit = 20
    max_limit = 100
    limit_query_param = 'limit'
    offset_query_param = 'offset'

    def get_paginated_response(self, data):
        return Response({
            'count': self.count,
            'next': self.get_next_link(),
            'previous': self.get_previous_link(),
            'results': data,
        })


class StandardPageNumberPagination(PageNumberPagination):
    """
    Alternative pagination using page numbers.
    Default: 20 items per page, Max: 100 items
    """
    page_size = 20
    page_size_query_param = 'page_size'
    max_page_size = 100
    page_query_param = 'page'

    def get_paginated_response(self, data):
        return Response({
            'count': self.page.paginator.count,
            'next': self.get_next_link(),
            'previous': self.get_previous_link(),
            'results': data,
            'page': self.page.number,
            'pages': self.page.paginator.num_pages,
        })


class LargeResultsSetPagination(LimitOffsetPagination):
    """
    Pagination class for large result sets (e.g., exports, bulk operations).
    Default: 100 items, Max: 1000 items
    """
    default_limit = 100
    max_limit = 1000
    limit_query_param = 'limit'
    offset_query_param = 'offset'

    def get_paginated_response(self, data):
        return Response({
            'count': self.count,
            'next': self.get_next_link(),
            'previous': self.get_previous_link(),
            'results': data,
        })


class SmallResultsSetPagination(LimitOffsetPagination):
    """
    Pagination class for small result sets (e.g., dropdowns, quick selects).
    Default: 10 items, Max: 50 items
    """
    default_limit = 10
    max_limit = 50
    limit_query_param = 'limit'
    offset_query_param = 'offset'

    def get_paginated_response(self, data):
        return Response({
            'count': self.count,
            'next': self.get_next_link(),
            'previous': self.get_previous_link(),
            'results': data,
        })
