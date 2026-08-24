import copy

from django.core.exceptions import ValidationError
from django.db import transaction
from django.db.models import Max
from django.utils import timezone

from idcards.models import IDCardTemplate, IDCardTemplateVersion
from .layout import LayoutService


class IDCardTemplateLifecycleService:
    """The sole write boundary for template versions and lifecycle transitions."""

    @classmethod
    @transaction.atomic
    def create_template(cls, *, name, holder_type, actor=None, description="", width_mm="85.60",
                        height_mm="53.98", orientation=None, front_layout=None, back_layout=None):
        orientation = orientation or ("LANDSCAPE" if float(width_mm) >= float(height_mm) else "PORTRAIT")
        front_layout = copy.deepcopy(front_layout) if front_layout is not None else LayoutService.empty_v2(width_mm, height_mm, orientation)
        back_layout = copy.deepcopy(back_layout) if back_layout is not None else LayoutService.empty_v2(width_mm, height_mm, orientation)
        template = IDCardTemplate(
            name=name, holder_type=holder_type, description=description, created_by=actor,
            width_mm=width_mm, height_mm=height_mm, front_layout=front_layout,
            back_layout=back_layout, is_active=False, is_archived=False,
        )
        template.full_clean(exclude=("current_draft_version", "current_published_version"))
        template.save()
        draft = cls._create_version(
            template=template, actor=actor, width_mm=width_mm, height_mm=height_mm,
            orientation=orientation, front_layout=front_layout, back_layout=back_layout,
        )
        template.current_draft_version = draft
        template.save(update_fields=("current_draft_version", "updated_at"))
        return template

    @classmethod
    def _next_number(cls, template):
        current = template.versions.aggregate(value=Max("version_number"))["value"] or 0
        return current + 1

    @classmethod
    def _create_version(cls, *, template, actor=None, source=None, width_mm=None, height_mm=None,
                        orientation=None, front_layout=None, back_layout=None):
        version = IDCardTemplateVersion(
            template=template,
            version_number=cls._next_number(template),
            status=IDCardTemplateVersion.Status.DRAFT,
            width_mm=width_mm if width_mm is not None else source.width_mm,
            height_mm=height_mm if height_mm is not None else source.height_mm,
            orientation=orientation or source.orientation,
            front_layout=copy.deepcopy(front_layout if front_layout is not None else source.front_layout),
            back_layout=copy.deepcopy(back_layout if back_layout is not None else source.back_layout),
            created_from_version=source,
            created_by=actor,
        )
        version.full_clean()
        version.save()
        return version

    @classmethod
    @transaction.atomic
    def create_draft(cls, template, *, actor=None, source=None):
        template = IDCardTemplate.objects.select_for_update().get(pk=template.pk)
        if template.is_archived:
            raise ValidationError("Archived templates cannot be edited.")
        existing = template.versions.filter(status=IDCardTemplateVersion.Status.DRAFT).first()
        if existing:
            if template.current_draft_version_id != existing.pk:
                template.current_draft_version = existing
                template.save(update_fields=("current_draft_version", "updated_at"))
            return existing
        source = source or template.current_published_version
        if not source:
            raise ValidationError("A source version is required to create a draft.")
        if source.template_id != template.pk:
            raise ValidationError("The source version belongs to another template.")
        draft = cls._create_version(template=template, actor=actor, source=source)
        template.current_draft_version = draft
        template.save(update_fields=("current_draft_version", "updated_at"))
        return draft

    @classmethod
    @transaction.atomic
    def update_draft(cls, version, **changes):
        version = IDCardTemplateVersion.objects.select_for_update().select_related("template").get(pk=version.pk)
        if version.status != IDCardTemplateVersion.Status.DRAFT:
            raise ValidationError("Only draft template versions can be edited.")
        allowed = {"width_mm", "height_mm", "orientation", "front_layout", "back_layout"}
        unknown = set(changes) - allowed
        if unknown:
            raise ValidationError(f"Unsupported draft fields: {', '.join(sorted(unknown))}.")
        for field, value in changes.items():
            setattr(version, field, copy.deepcopy(value))
        version.full_clean()
        version.save(update_fields=(*changes.keys(), "updated_at"))
        template = version.template
        template.width_mm = version.width_mm
        template.height_mm = version.height_mm
        template.front_layout = copy.deepcopy(version.front_layout)
        template.back_layout = copy.deepcopy(version.back_layout)
        template.save(update_fields=("width_mm", "height_mm", "front_layout", "back_layout", "updated_at"))
        return version

    @classmethod
    @transaction.atomic
    def publish(cls, version, *, actor=None):
        version = IDCardTemplateVersion.objects.select_for_update().select_related("template").get(pk=version.pk)
        template = IDCardTemplate.objects.select_for_update().get(pk=version.template_id)
        if version.status != IDCardTemplateVersion.Status.DRAFT:
            raise ValidationError("Only a draft version can be published.")
        if template.is_archived:
            raise ValidationError("Archived templates cannot publish versions.")
        version.full_clean()
        previous = template.current_published_version
        if previous and previous.pk != version.pk:
            IDCardTemplateVersion.objects.filter(pk=previous.pk).update(status=IDCardTemplateVersion.Status.ARCHIVED)
        version.status = IDCardTemplateVersion.Status.PUBLISHED
        version.published_by = actor
        version.published_at = timezone.now()
        version.save(update_fields=("status", "published_by", "published_at", "updated_at"))
        template.current_published_version = version
        template.current_draft_version = None
        template.is_active = True
        template.width_mm = version.width_mm
        template.height_mm = version.height_mm
        template.front_layout = copy.deepcopy(version.front_layout)
        template.back_layout = copy.deepcopy(version.back_layout)
        template.save(update_fields=(
            "current_published_version", "current_draft_version", "is_active", "width_mm",
            "height_mm", "front_layout", "back_layout", "updated_at",
        ))
        return version

    @classmethod
    @transaction.atomic
    def archive(cls, template):
        template = IDCardTemplate.objects.select_for_update().get(pk=template.pk)
        template.is_archived = True
        template.is_active = False
        draft = template.current_draft_version
        if draft:
            draft.status = IDCardTemplateVersion.Status.ARCHIVED
            draft.save(update_fields=("status", "updated_at"))
            template.current_draft_version = None
        template.save(update_fields=("is_archived", "is_active", "current_draft_version", "updated_at"))
        return template

    @classmethod
    @transaction.atomic
    def archive_version(cls, version):
        version = IDCardTemplateVersion.objects.select_for_update().select_related("template").get(pk=version.pk)
        template = IDCardTemplate.objects.select_for_update().get(pk=version.template_id)
        if version.status == IDCardTemplateVersion.Status.ARCHIVED:
            return version
        version.status = IDCardTemplateVersion.Status.ARCHIVED
        version.save(update_fields=("status", "updated_at"))
        fields = []
        if template.current_draft_version_id == version.pk:
            template.current_draft_version = None
            fields.append("current_draft_version")
        if template.current_published_version_id == version.pk:
            template.current_published_version = None
            template.is_active = False
            fields.extend(("current_published_version", "is_active"))
        if fields:
            template.save(update_fields=(*fields, "updated_at"))
        return version

    @classmethod
    @transaction.atomic
    def duplicate(cls, template, *, name, actor=None):
        template = IDCardTemplate.objects.select_for_update().get(pk=template.pk)
        source = template.current_draft_version or template.current_published_version or template.versions.first()
        if not source:
            raise ValidationError("The template has no version to duplicate.")
        return cls.create_template(
            name=name, holder_type=template.holder_type, description=template.description,
            actor=actor, width_mm=source.width_mm, height_mm=source.height_mm,
            orientation=source.orientation, front_layout=source.front_layout, back_layout=source.back_layout,
        )

    @classmethod
    @transaction.atomic
    def ensure_legacy_published_version(cls, template, *, actor=None):
        """Compatibility for old direct ORM callers; migrated rows already have versions."""
        template = IDCardTemplate.objects.select_for_update().get(pk=template.pk)
        version = template.current_published_version
        if version:
            return version
        if template.versions.exists():
            raise ValidationError("This template has no published version.")
        orientation = "LANDSCAPE" if template.width_mm >= template.height_mm else "PORTRAIT"
        version = IDCardTemplateVersion(
            template=template, version_number=1, status=IDCardTemplateVersion.Status.PUBLISHED,
            width_mm=template.width_mm, height_mm=template.height_mm, orientation=orientation,
            front_layout=copy.deepcopy(template.front_layout), back_layout=copy.deepcopy(template.back_layout),
            created_by=actor, published_by=actor, published_at=timezone.now(),
        )
        version.full_clean()
        version.save()
        template.current_published_version = version
        template.save(update_fields=("current_published_version", "updated_at"))
        return version
