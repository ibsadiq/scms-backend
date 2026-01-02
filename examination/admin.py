from django.contrib import admin
from .models import *


# ============================================================================
# GRADE SCALE ADMIN
# ============================================================================

class GradeScaleRuleInline(admin.TabularInline):
    model = GradeScaleRule
    extra = 1
    fields = ['min_grade', 'max_grade', 'letter_grade', 'numeric_scale']


@admin.register(GradeScale)
class GradeScaleAdmin(admin.ModelAdmin):
    list_display = ['name']
    search_fields = ['name']
    inlines = [GradeScaleRuleInline]


@admin.register(GradeScaleRule)
class GradeScaleRuleAdmin(admin.ModelAdmin):
    list_display = ['grade_scale', 'min_grade', 'max_grade', 'letter_grade', 'numeric_scale']
    list_filter = ['grade_scale', 'letter_grade']
    search_fields = ['grade_scale__name']


# ============================================================================
# EXAMINATION ADMIN
# ============================================================================

@admin.register(ExaminationListHandler)
class ExaminationAdmin(admin.ModelAdmin):
    list_display = ['name', 'start_date', 'ends_date', 'out_of', 'status', 'created_by']
    list_filter = ['start_date', 'ends_date']
    search_fields = ['name', 'comments']
    filter_horizontal = ['classrooms']
    readonly_fields = ['created_on']


@admin.register(MarksManagement)
class MarksAdmin(admin.ModelAdmin):
    list_display = ['exam_name', 'student', 'subject', 'points_scored', 'created_by', 'date_time']
    list_filter = ['exam_name', 'subject', 'created_by']
    search_fields = ['student__student__first_name', 'student__student__last_name', 'subject__name']
    readonly_fields = ['date_time']


@admin.register(Result)
class ResultAdmin(admin.ModelAdmin):
    list_display = ['student', 'gpa', 'cat_gpa', 'academic_year', 'term']
    list_filter = ['academic_year', 'term']
    search_fields = ['student__first_name', 'student__last_name']


# ============================================================================
# RESULT COMPUTATION ADMIN (Phase 1.1)
# ============================================================================

class SubjectResultInline(admin.TabularInline):
    model = SubjectResult
    extra = 0
    fields = [
        'subject', 'ca_score', 'exam_score', 'total_score',
        'percentage', 'grade', 'grade_point', 'position_in_subject'
    ]
    readonly_fields = ['total_score', 'percentage']
    can_delete = False


@admin.register(TermResult)
class TermResultAdmin(admin.ModelAdmin):
    list_display = [
        'student', 'term', 'classroom', 'average_percentage',
        'grade', 'gpa', 'position_in_class', 'is_published'
    ]
    list_filter = [
        'term', 'academic_year', 'classroom', 'grade',
        'is_published', 'computed_date'
    ]
    search_fields = [
        'student__first_name', 'student__last_name',
        'student__admission_number'
    ]
    readonly_fields = [
        'total_marks', 'total_possible', 'average_percentage',
        'grade', 'gpa', 'position_in_class', 'total_students',
        'computed_date', 'computed_by', 'published_date'
    ]
    fieldsets = (
        ('Student Information', {
            'fields': ('student', 'term', 'academic_year', 'classroom')
        }),
        ('Computed Results', {
            'fields': (
                'total_marks', 'total_possible', 'average_percentage',
                'grade', 'gpa', 'position_in_class', 'total_students'
            )
        }),
        ('Remarks', {
            'fields': ('class_teacher_remarks', 'principal_remarks')
        }),
        ('Publishing', {
            'fields': ('is_published', 'published_date')
        }),
        ('Metadata', {
            'fields': ('computed_date', 'computed_by'),
            'classes': ('collapse',)
        }),
    )
    inlines = [SubjectResultInline]

    actions = ['publish_results', 'unpublish_results']

    def publish_results(self, request, queryset):
        """Bulk publish results"""
        from django.utils import timezone
        count = queryset.update(is_published=True, published_date=timezone.now())
        self.message_user(request, f'{count} result(s) published successfully.')
    publish_results.short_description = 'Publish selected results'

    def unpublish_results(self, request, queryset):
        """Bulk unpublish results"""
        count = queryset.update(is_published=False, published_date=None)
        self.message_user(request, f'{count} result(s) unpublished successfully.')
    unpublish_results.short_description = 'Unpublish selected results'


@admin.register(SubjectResult)
class SubjectResultAdmin(admin.ModelAdmin):
    list_display = [
        'term_result', 'subject', 'teacher', 'total_score',
        'percentage', 'grade', 'grade_point', 'position_in_subject'
    ]
    list_filter = [
        'term_result__term', 'subject', 'grade', 'teacher'
    ]
    search_fields = [
        'term_result__student__first_name',
        'term_result__student__last_name',
        'subject__name'
    ]
    readonly_fields = [
        'total_score', 'percentage', 'position_in_subject',
        'total_students', 'highest_score', 'lowest_score', 'class_average'
    ]
    fieldsets = (
        ('Basic Information', {
            'fields': ('term_result', 'subject', 'teacher')
        }),
        ('Scores', {
            'fields': (
                ('ca_score', 'ca_max'),
                ('exam_score', 'exam_max'),
                ('total_score', 'total_possible'),
                'percentage'
            )
        }),
        ('Grading', {
            'fields': ('grade', 'grade_point')
        }),
        ('Class Statistics', {
            'fields': (
                'position_in_subject', 'total_students',
                'highest_score', 'lowest_score', 'class_average'
            ),
            'classes': ('collapse',)
        }),
        ('Remarks', {
            'fields': ('teacher_remarks',)
        }),
    )


# ============================================================================
# REPORT CARD ADMIN (Phase 1.2)
# ============================================================================

@admin.register(ReportCard)
class ReportCardAdmin(admin.ModelAdmin):
    list_display = [
        'get_student_name', 'get_term', 'get_classroom',
        'generated_date', 'download_count', 'has_pdf'
    ]
    list_filter = [
        'generated_date',
        'term_result__term',
        'term_result__academic_year',
        'term_result__classroom'
    ]
    search_fields = [
        'term_result__student__first_name',
        'term_result__student__last_name',
        'term_result__student__admission_number'
    ]
    readonly_fields = [
        'term_result', 'generated_date', 'generated_by',
        'download_count', 'last_downloaded', 'pdf_file'
    ]
    fieldsets = (
        ('Report Card Information', {
            'fields': ('term_result', 'pdf_file')
        }),
        ('Generation Details', {
            'fields': ('generated_date', 'generated_by')
        }),
        ('Download Statistics', {
            'fields': ('download_count', 'last_downloaded')
        }),
    )

    def get_student_name(self, obj):
        return obj.term_result.student.full_name
    get_student_name.short_description = 'Student'
    get_student_name.admin_order_field = 'term_result__student__first_name'

    def get_term(self, obj):
        return obj.term_result.term.name
    get_term.short_description = 'Term'
    get_term.admin_order_field = 'term_result__term'

    def get_classroom(self, obj):
        return str(obj.term_result.classroom) if obj.term_result.classroom else 'N/A'
    get_classroom.short_description = 'Class'
    get_classroom.admin_order_field = 'term_result__classroom'

    def has_pdf(self, obj):
        return bool(obj.pdf_file)
    has_pdf.boolean = True
    has_pdf.short_description = 'PDF Generated'


# ============================================================================
# MARKED SCRIPT ADMIN
# ============================================================================

@admin.register(MarkedScript)
class MarkedScriptAdmin(admin.ModelAdmin):
    list_display = [
        'get_student_name', 'exam', 'subject', 'uploaded_by',
        'uploaded_at', 'file_size_display', 'visible_to_student', 'visible_to_parent'
    ]
    list_filter = [
        'exam', 'subject', 'uploaded_by', 'uploaded_at',
        'visible_to_student', 'visible_to_parent'
    ]
    search_fields = [
        'student__first_name', 'student__last_name',
        'student__admission_number', 'exam__name',
        'subject__name', 'file_name'
    ]
    readonly_fields = [
        'file_name', 'file_size', 'uploaded_at'
    ]
    fieldsets = (
        ('Assignment Information', {
            'fields': ('exam', 'student', 'subject', 'marks_entry')
        }),
        ('File Information', {
            'fields': ('script_file', 'file_name', 'file_size', 'notes')
        }),
        ('Upload Details', {
            'fields': ('uploaded_by', 'uploaded_at')
        }),
        ('Visibility Settings', {
            'fields': ('visible_to_student', 'visible_to_parent')
        }),
    )

    actions = ['make_visible_to_students', 'make_visible_to_parents', 'hide_from_students', 'hide_from_parents']

    def get_student_name(self, obj):
        return obj.student.full_name
    get_student_name.short_description = 'Student'
    get_student_name.admin_order_field = 'student__first_name'

    def file_size_display(self, obj):
        """Display file size in human-readable format"""
        if obj.file_size:
            if obj.file_size < 1024:
                return f"{obj.file_size} B"
            elif obj.file_size < 1024 * 1024:
                return f"{obj.file_size / 1024:.2f} KB"
            else:
                return f"{obj.file_size / (1024 * 1024):.2f} MB"
        return "N/A"
    file_size_display.short_description = 'File Size'

    def make_visible_to_students(self, request, queryset):
        """Bulk action to make scripts visible to students"""
        count = queryset.update(visible_to_student=True)
        self.message_user(request, f'{count} script(s) made visible to students.')
    make_visible_to_students.short_description = 'Make visible to students'

    def make_visible_to_parents(self, request, queryset):
        """Bulk action to make scripts visible to parents"""
        count = queryset.update(visible_to_parent=True)
        self.message_user(request, f'{count} script(s) made visible to parents.')
    make_visible_to_parents.short_description = 'Make visible to parents'

    def hide_from_students(self, request, queryset):
        """Bulk action to hide scripts from students"""
        count = queryset.update(visible_to_student=False)
        self.message_user(request, f'{count} script(s) hidden from students.')
    hide_from_students.short_description = 'Hide from students'

    def hide_from_parents(self, request, queryset):
        """Bulk action to hide scripts from parents"""
        count = queryset.update(visible_to_parent=False)
        self.message_user(request, f'{count} script(s) hidden from parents.')
    hide_from_parents.short_description = 'Hide from parents'
