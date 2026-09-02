from rest_framework.pagination import PageNumberPagination


class DefaultPagination(PageNumberPagination):
    page_size = 20
    page_size_query_param = "page_size"
    max_page_size = 1000

    def paginate_queryset(self, queryset, request, view=None):
        if (
            request.query_params.get("all") in ("true", "1")
            or request.query_params.get("paginate") in ("false", "0")
            or request.query_params.get(self.page_size_query_param) in ("all", "0", "-1")
        ):
            return None
        return super().paginate_queryset(queryset, request, view)