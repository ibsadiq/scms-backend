from django.contrib import admin

from .models import *

admin.site.register(Article)
admin.site.register(CarouselImage)
admin.site.register(School)
admin.site.register(Day)
admin.site.register(AcademicYear)
admin.site.register(Term)

@admin.register(SchoolEvent)
class SchoolEventAdmin(admin.ModelAdmin):
    list_display = ('name', 'event_type', 'term', 'start_date', 'end_date')
    list_filter = ('event_type', 'term__academic_year')
    search_fields = ('name', 'description')
