from rest_framework import viewsets, status
from rest_framework.decorators import action
from rest_framework.response import Response
from rest_framework.permissions import AllowAny
from rest_framework.parsers import MultiPartParser, FormParser, JSONParser
from .models import SchoolSettings
from .serializers import SchoolSettingsSerializer


class SchoolSettingsViewSet(viewsets.ModelViewSet):
    """
    ViewSet for managing school settings.
    Only one settings instance exists (singleton pattern).
    """
    queryset = SchoolSettings.objects.all()
    serializer_class = SchoolSettingsSerializer
    permission_classes = [AllowAny]
    parser_classes = [JSONParser, MultiPartParser, FormParser]

    def get_object(self):
        """
        Always return the singleton settings instance
        """
        return SchoolSettings.get_settings()

    def list(self, request, *args, **kwargs):
        """
        Return the singleton settings instance
        """
        settings = self.get_object()
        serializer = self.get_serializer(settings)
        return Response(serializer.data)

    def create(self, request, *args, **kwargs):
        """
        Create or update settings (since it's a singleton)
        """
        settings = self.get_object()
        serializer = self.get_serializer(settings, data=request.data, partial=True)
        serializer.is_valid(raise_exception=True)
        serializer.save()
        return Response(serializer.data, status=status.HTTP_200_OK)

    def update(self, request, *args, **kwargs):
        """
        Update settings
        """
        settings = self.get_object()
        serializer = self.get_serializer(settings, data=request.data, partial=True)
        serializer.is_valid(raise_exception=True)
        serializer.save()
        return Response(serializer.data)

    def partial_update(self, request, *args, **kwargs):
        """
        Partially update settings
        """
        return self.update(request, *args, **kwargs)

    def destroy(self, request, *args, **kwargs):
        """
        Prevent deletion of settings
        """
        return Response(
            {'error': 'Settings cannot be deleted'},
            status=status.HTTP_400_BAD_REQUEST
        )

    @action(detail=False, methods=['post'], parser_classes=[MultiPartParser, FormParser])
    def upload_logo(self, request):
        """
        Upload school logo
        """
        settings = self.get_object()

        if 'logo' not in request.FILES:
            return Response(
                {'error': 'No logo file provided'},
                status=status.HTTP_400_BAD_REQUEST
            )

        logo_file = request.FILES['logo']

        # Validate file size (2MB)
        if logo_file.size > 2 * 1024 * 1024:
            return Response(
                {'error': 'Logo file must be less than 2MB'},
                status=status.HTTP_400_BAD_REQUEST
            )

        # Validate file type
        if not logo_file.content_type.startswith('image/'):
            return Response(
                {'error': 'File must be an image'},
                status=status.HTTP_400_BAD_REQUEST
            )

        # Save logo
        settings.logo = logo_file
        settings.save()

        serializer = self.get_serializer(settings)
        return Response({
            'message': 'Logo uploaded successfully',
            'logo_url': serializer.data['logo_url']
        })

    @action(detail=False, methods=['post'])
    def remove_logo(self, request):
        """
        Remove school logo
        """
        settings = self.get_object()
        if settings.logo:
            settings.logo.delete()
            settings.save()

        return Response({'message': 'Logo removed successfully'})
