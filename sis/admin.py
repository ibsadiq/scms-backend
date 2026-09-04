from django.contrib import admin

from academic.models import *
from academic.services.parent_student_service import ParentStudentService


class ParentAdmin(admin.ModelAdmin):
    list_display = ("first_name", "last_name", "phone_number", "email", "user")
    search_fields = ("first_name", "last_name", "phone_number", "email")

    def delete_model(self, request, obj):
        ParentStudentService.delete_parent(obj)

    def delete_queryset(self, request, queryset):
        for obj in queryset:
            ParentStudentService.delete_parent(obj)


admin.site.register(ReasonLeft)
admin.site.register(StudentsPreviousAcademicHistory)
admin.site.register(StudentFile)
admin.site.register(StudentHealthRecord)
admin.site.register(Parent, ParentAdmin)
