from django.contrib import admin
from .models import (
    TeacherAvatarSetting,
    TutorSession,
    TutorMessage,
    TutorSessionInsight,
)


@admin.register(TeacherAvatarSetting)
class TeacherAvatarSettingAdmin(admin.ModelAdmin):
    list_display = ["teacher", "avatar_style", "teaching_tone", "is_ai_tutor_enabled", "allow_direct_answers"]
    list_filter = ["avatar_style", "teaching_tone", "is_ai_tutor_enabled", "allow_direct_answers"]
    search_fields = ["teacher__user__first_name", "teacher__user__last_name", "teacher__user__email"]


class TutorMessageInline(admin.TabularInline):
    model = TutorMessage
    extra = 0
    readonly_fields = ["role", "content", "tokens_used", "learning_objective", "created_at"]
    can_delete = False


class TutorSessionInsightInline(admin.StackedInline):
    model = TutorSessionInsight
    extra = 0
    readonly_fields = ["summary", "misconceptions", "concepts_struggled_with", "concepts_mastered", "follow_up_recommended", "teacher_attention_required", "updated_at"]
    can_delete = False


@admin.register(TutorSession)
class TutorSessionAdmin(admin.ModelAdmin):
    list_display = ["id", "student", "teacher", "subject", "lesson_plan", "curriculum_topic", "updated_at"]
    list_filter = ["subject", "created_at"]
    search_fields = [
        "student__first_name",
        "student__last_name",
        "teacher__user__first_name",
        "teacher__user__last_name",
        "subject__name",
    ]
    inlines = [TutorSessionInsightInline, TutorMessageInline]


@admin.register(TutorMessage)
class TutorMessageAdmin(admin.ModelAdmin):
    list_display = ["id", "session", "role", "learning_objective", "created_at"]
    list_filter = ["role", "created_at"]
    search_fields = ["content", "session__student__first_name", "session__student__last_name"]


@admin.register(TutorSessionInsight)
class TutorSessionInsightAdmin(admin.ModelAdmin):
    list_display = ["session", "follow_up_recommended", "teacher_attention_required", "updated_at"]
    list_filter = ["follow_up_recommended", "teacher_attention_required"]
