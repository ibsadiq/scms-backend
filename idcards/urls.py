from django.urls import include, path
from rest_framework.routers import DefaultRouter

from idcards.views import IDCardTemplateVersionViewSet, IDCardTemplateViewSet, IDCardViewSet, RFIDCredentialViewSet, template_fields

router = DefaultRouter()
router.register("templates", IDCardTemplateViewSet, basename="idcard-template")
router.register("template-versions", IDCardTemplateVersionViewSet, basename="idcard-template-version")
router.register("cards", IDCardViewSet, basename="idcard")
router.register("rfid-credentials", RFIDCredentialViewSet, basename="rfid-credential")

urlpatterns = [path("template-fields/", template_fields, name="idcard-template-fields"), path("", include(router.urls))]
