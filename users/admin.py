from django.contrib import admin
from django.contrib.auth.admin import UserAdmin

from .forms import CustomUserCreationForm, CustomUserChangeForm
from .models import CustomUser, Accountant, UserInvitation


class UserTypeFilter(admin.SimpleListFilter):
    """Custom filter to filter users by their type/role"""
    title = 'user type'
    parameter_name = 'user_type'

    def lookups(self, request, model_admin):
        return (
            ('teacher', 'Teachers'),
            ('parent', 'Parents'),
            ('accountant', 'Accountants'),
            ('staff', 'Staff/Admin'),
            ('student', 'Students (no role)'),
        )

    def queryset(self, request, queryset):
        if self.value() == 'teacher':
            return queryset.filter(is_teacher=True)
        elif self.value() == 'parent':
            return queryset.filter(is_parent=True)
        elif self.value() == 'accountant':
            return queryset.filter(is_accountant=True)
        elif self.value() == 'staff':
            return queryset.filter(is_staff=True)
        elif self.value() == 'student':
            # Users with no specific role (not teacher, parent, accountant, or staff)
            return queryset.filter(
                is_teacher=False,
                is_parent=False,
                is_accountant=False,
                is_staff=False
            )
        return queryset


class CustomUserAdmin(UserAdmin):
    add_form = CustomUserCreationForm
    form = CustomUserChangeForm
    model = CustomUser
    list_display = ('email', 'get_full_name', 'phone_number', 'get_user_type', 'is_active', 'date_joined')
    list_filter = (UserTypeFilter, 'is_staff', 'is_active', 'is_accountant', 'is_teacher', 'is_parent')
    fieldsets = (
        ('Personal Information', {'fields': ('first_name', 'middle_name', 'last_name', 'email', 'phone_number', 'password')}),
        ('User Types', {'fields': ('is_accountant', 'is_teacher', 'is_parent')}),
        ('Permissions', {'fields': ('is_staff', 'is_active', 'is_superuser', 'groups', 'user_permissions')}),
        ('Important Dates', {'fields': ('last_login', 'date_joined')}),
    )
    add_fieldsets = (
        (None, {
            'classes': ('wide',),
            'fields': ('first_name', 'middle_name', 'last_name', 'email', 'phone_number', 'password1', 'password2', 'is_staff', 'is_active', 'is_accountant', 'is_teacher', 'is_parent')}
        ),
    )
    search_fields = ('email', 'first_name', 'last_name', 'phone_number')
    ordering = ('email',)
    readonly_fields = ('date_joined', 'last_login')

    def get_full_name(self, obj):
        """Display full name of the user"""
        if obj.first_name or obj.last_name:
            return f"{obj.first_name} {obj.last_name}".strip()
        return "-"
    get_full_name.short_description = 'Full Name'

    def get_user_type(self, obj):
        """Display user type/role"""
        types = []
        if obj.is_superuser:
            types.append('Superuser')
        if obj.is_staff:
            types.append('Staff')
        if obj.is_teacher:
            types.append('Teacher')
        if obj.is_parent:
            types.append('Parent')
        if obj.is_accountant:
            types.append('Accountant')

        return ', '.join(types) if types else 'No Role'
    get_user_type.short_description = 'User Type'


@admin.register(UserInvitation)
class UserInvitationAdmin(admin.ModelAdmin):
    list_display = ('email', 'first_name', 'last_name', 'role', 'status', 'created_at', 'expires_at', 'invited_by')
    list_filter = ('role', 'status', 'created_at')
    search_fields = ('email', 'first_name', 'last_name', 'token')
    readonly_fields = ('token', 'created_at', 'accepted_at')
    ordering = ('-created_at',)


admin.site.register(CustomUser, CustomUserAdmin)
admin.site.register(Accountant)