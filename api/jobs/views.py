from rest_framework.generics import RetrieveAPIView
from rest_framework.permissions import IsAuthenticated

from .models import BackgroundJob
from .permissions import CanViewBackgroundJob
from .serializers import BackgroundJobSerializer


class BackgroundJobDetailView(RetrieveAPIView):
    queryset = BackgroundJob.objects.select_related("created_by")
    serializer_class = BackgroundJobSerializer
    permission_classes = (IsAuthenticated, CanViewBackgroundJob)
    lookup_field = "public_id"
    lookup_url_kwarg = "public_id"
