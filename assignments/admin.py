"""
Assignment Admin - Phase 1.7: Assignment & Homework Management
"""
from django.contrib import admin
from django.utils.html import format_html
from .models import (
    Assignment,
    AssignmentAttachment,
    AssignmentSubmission,
    SubmissionAttachment,
    AssignmentGrade
)


class AssignmentAttachmentInline(admin.TabularInline):
    """Inline for assignment attachments"""
    model = AssignmentAttachment
    extra = 1
    fields = ['file', 'file_name', 'file_size', 'uploaded_at']
    readonly_fields = ['file_name', 'file_size', 'uploaded_at']


@admin.register(Assignment)
class AssignmentAdmin(admin.ModelAdmin):
    """Admin interface for assignments"""
    list_display = [
        'title',
        'assignment_type',
        'teacher',
        'classroom',
        'subject',
        'due_date',
        'status',
        'submission_stats',
        'is_overdue'
    ]
    list_filter = [
        'status',
        'assignment_type',
        'academic_year',
        'term',
        'classroom',
        'subject',
        'is_active'
    ]
    search_fields = [
        'title',
        'description',
        'teacher__user__first_name',
        'teacher__user__last_name',
        'classroom__name',
        'subject__name'
    ]
    readonly_fields = [
        'assigned_date',
        'created_at',
        'updated_at',
        'submission_stats_detail'
    ]
    fieldsets = (
        ('Basic Information', {
            'fields': (
                'title',
                'description',
                'assignment_type',
                'status',
                'is_active'
            )
        }),
        ('Assignment Details', {
            'fields': (
                'teacher',
                'classroom',
                'subject',
                'academic_year',
                'term'
            )
        }),
        ('Dates and Scoring', {
            'fields': (
                'assigned_date',
                'due_date',
                'max_score',
                'allow_late_submission',
                'late_penalty_percent'
            )
        }),
        ('Statistics', {
            'fields': ('submission_stats_detail',),
            'classes': ('collapse',)
        }),
        ('Timestamps', {
            'fields': ('created_at', 'updated_at'),
            'classes': ('collapse',)
        })
    )
    inlines = [AssignmentAttachmentInline]
    date_hierarchy = 'due_date'
    
    def submission_stats(self, obj):
        """Show submission statistics in list view"""
        return format_html(
            '<span style="color: {};">{}/{} ({}%)</span>',
            'green' if obj.submission_rate >= 80 else 'orange' if obj.submission_rate >= 50 else 'red',
            obj.submission_count,
            obj.total_students,
            obj.submission_rate
        )
    submission_stats.short_description = 'Submissions'
    
    def submission_stats_detail(self, obj):
        """Show detailed submission statistics"""
        return format_html(
            '<div style="padding: 10px; background-color: #f9f9f9; border-radius: 5px;">'
            '<p><strong>Total Students:</strong> {}</p>'
            '<p><strong>Submissions:</strong> {} ({}%)</p>'
            '<p><strong>Graded:</strong> {}</p>'
            '<p><strong>Pending Grading:</strong> {}</p>'
            '<p><strong>Overdue:</strong> {}</p>'
            '</div>',
            obj.total_students,
            obj.submission_count,
            obj.submission_rate,
            obj.graded_count,
            obj.submission_count - obj.graded_count,
            'Yes' if obj.is_overdue else 'No'
        )
    submission_stats_detail.short_description = 'Submission Statistics'


class SubmissionAttachmentInline(admin.TabularInline):
    """Inline for submission attachments"""
    model = SubmissionAttachment
    extra = 0
    fields = ['file', 'file_name', 'file_size', 'uploaded_at']
    readonly_fields = ['file_name', 'file_size', 'uploaded_at']


@admin.register(AssignmentSubmission)
class AssignmentSubmissionAdmin(admin.ModelAdmin):
    """Admin interface for submissions"""
    list_display = [
        'assignment',
        'student',
        'submitted_at',
        'is_late',
        'grade_status',
        'grade_display'
    ]
    list_filter = [
        'is_late',
        'submitted_at',
        'assignment__classroom',
        'assignment__subject'
    ]
    search_fields = [
        'student__full_name',
        'student__admission_number',
        'assignment__title',
        'submission_text'
    ]
    readonly_fields = ['submitted_at', 'updated_at', 'is_late']
    fieldsets = (
        ('Submission Details', {
            'fields': (
                'assignment',
                'student',
                'submission_text',
                'is_late'
            )
        }),
        ('Timestamps', {
            'fields': ('submitted_at', 'updated_at')
        })
    )
    inlines = [SubmissionAttachmentInline]
    date_hierarchy = 'submitted_at'
    
    def grade_status(self, obj):
        """Show grading status"""
        if hasattr(obj, 'grade'):
            return format_html('<span style="color: green;">✓ Graded</span>')
        return format_html('<span style="color: orange;">Pending</span>')
    grade_status.short_description = 'Status'
    
    def grade_display(self, obj):
        """Display grade if available"""
        if hasattr(obj, 'grade'):
            grade = obj.grade
            return format_html(
                '{}/{} ({}% - {})',
                grade.final_score,
                obj.assignment.max_score,
                grade.percentage,
                grade.grade_letter
            )
        return '-'
    grade_display.short_description = 'Grade'


@admin.register(AssignmentGrade)
class AssignmentGradeAdmin(admin.ModelAdmin):
    """Admin interface for grades"""
    list_display = [
        'submission',
        'student_name',
        'score',
        'late_penalty_applied',
        'final_score',
        'percentage',
        'grade_letter',
        'graded_by',
        'graded_at'
    ]
    list_filter = [
        'graded_at',
        'submission__assignment__classroom',
        'submission__assignment__subject'
    ]
    search_fields = [
        'submission__student__full_name',
        'submission__assignment__title',
        'feedback'
    ]
    readonly_fields = [
        'graded_at',
        'updated_at',
        'final_score',
        'percentage',
        'grade_letter'
    ]
    fieldsets = (
        ('Grade Details', {
            'fields': (
                'submission',
                'score',
                'late_penalty_applied',
                'final_score',
                'percentage',
                'grade_letter'
            )
        }),
        ('Feedback', {
            'fields': ('feedback',)
        }),
        ('Grading Information', {
            'fields': (
                'graded_by',
                'graded_at',
                'updated_at'
            )
        })
    )
    date_hierarchy = 'graded_at'
    
    def student_name(self, obj):
        """Display student name"""
        return obj.submission.student.full_name
    student_name.short_description = 'Student'
    student_name.admin_order_field = 'submission__student__full_name'


@admin.register(AssignmentAttachment)
class AssignmentAttachmentAdmin(admin.ModelAdmin):
    """Admin interface for assignment attachments"""
    list_display = ['assignment', 'file_name', 'file_size', 'uploaded_at']
    list_filter = ['uploaded_at', 'assignment__classroom']
    search_fields = ['assignment__title', 'file_name']
    readonly_fields = ['file_name', 'file_size', 'uploaded_at']


@admin.register(SubmissionAttachment)
class SubmissionAttachmentAdmin(admin.ModelAdmin):
    """Admin interface for submission attachments"""
    list_display = ['submission', 'student_name', 'file_name', 'file_size', 'uploaded_at']
    list_filter = ['uploaded_at', 'submission__assignment__classroom']
    search_fields = ['submission__student__full_name', 'file_name']
    readonly_fields = ['file_name', 'file_size', 'uploaded_at']
    
    def student_name(self, obj):
        """Display student name"""
        return obj.submission.student.full_name
    student_name.short_description = 'Student'
    student_name.admin_order_field = 'submission__student__full_name'
