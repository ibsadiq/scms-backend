"""
Tenant API URLs - ViewSet Routing
"""
from django.urls import path, include
from rest_framework.routers import DefaultRouter
from tenants import views

# Separate routers for public and admin
public_router = DefaultRouter()
admin_router = DefaultRouter()
inspector_router = DefaultRouter()


# Register ViewSets
public_router.register(r'', views.PublicTenantViewSet, basename='public-tenant')
admin_router.register(r'', views.AdminTenantViewSet, basename='admin-tenant')
inspector_router.register(r'', views.InspectorViewSet,   basename='inspector')


urlpatterns = [
    # Public endpoints: /api/tenants/
    path('', include(public_router.urls)),

    path('admin/inspectors/', include(inspector_router.urls)),

    
    # Admin endpoints: /api/tenants/admin/
    path('admin/', include(admin_router.urls)),
    path('branding/', views.TenantBrandingView.as_view(), name='tenant-branding'),
    path('search/', views.SchoolSearchView.as_view(), name='school-search'),

    # Public — consumed by the /reset-password frontend page
    path('password-reset/confirm/', views.PasswordResetConfirmView.as_view(), name='tenant-password-reset-confirm'),

    # School admin — manage their own school settings (called from school subdomain)
    path('school/settings/', views.SchoolSettingsView.as_view(), name='school-settings'),
]