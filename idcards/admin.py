from django.contrib import admin

from idcards.models import IDCard, IDCardTemplate, IDCardTemplateVersion, RFIDCredential


@admin.register(IDCardTemplate)
class IDCardTemplateAdmin(admin.ModelAdmin):
    list_display = ("name", "holder_type", "current_draft_version", "current_published_version", "is_active", "is_archived", "updated_at")
    list_filter = ("holder_type", "is_active", "is_archived")
    search_fields = ("name",)
    readonly_fields = ("public_id", "current_draft_version", "current_published_version", "created_at", "updated_at")


@admin.register(IDCardTemplateVersion)
class IDCardTemplateVersionAdmin(admin.ModelAdmin):
    list_display = ("template", "version_number", "status", "orientation", "published_at", "updated_at")
    list_filter = ("status", "orientation", "template__holder_type")
    search_fields = ("template__name",)
    readonly_fields = (
        "template", "version_number", "status", "width_mm", "height_mm", "orientation",
        "front_layout", "back_layout", "created_from_version", "created_by", "published_by",
        "published_at", "created_at", "updated_at",
    )


@admin.register(IDCard)
class IDCardAdmin(admin.ModelAdmin):
    list_display = ("card_number", "holder_type", "template", "status", "issued_at", "expires_at")
    list_filter = ("status", "template__holder_type")
    search_fields = ("card_number", "student__student_id", "staff__staff_id")
    readonly_fields = ("card_number", "verification_token", "template_version", "issued_at", "created_at", "updated_at")


@admin.register(RFIDCredential)
class RFIDCredentialAdmin(admin.ModelAdmin):
    list_display = ("masked_uid", "id_card", "status", "assigned_at", "revoked_at")
    list_filter = ("status",)
    search_fields = ("id_card__card_number", "uid_last_four")
    readonly_fields = ("uid_hash", "uid_last_four", "assigned_at", "created_at", "updated_at")
