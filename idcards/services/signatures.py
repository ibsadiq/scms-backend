"""Authorized signature service: secure upload, immutable versioning, and template reference protection."""

import hashlib
from io import BytesIO
from PIL import Image

from django.core.exceptions import ValidationError
from django.core.files.uploadedfile import UploadedFile
from django.db import transaction
from django.db.models import Max

from idcards.models import AuthorizedSignature, AuthorizedSignatureVersion, IDCardTemplateVersion


class AuthorizedSignatureService:
    """Service for managing versioned authorized school signatories and signature images."""

    MAX_FILE_SIZE = 2 * 1024 * 1024  # 2 MB
    MAX_DIMENSION = 2000  # 2000 px
    MAX_PIXELS = 10_000_000  # 10 MP decompression limit check
    ALLOWED_FORMATS = {"PNG", "JPEG"}
    ALLOWED_MIMES = {"image/png", "image/jpeg"}

    @classmethod
    def validate_and_process_upload(cls, file_obj: UploadedFile) -> dict:
        """Validate uploaded signature image for MIME, raster format, dimensions, and compute hash."""
        if file_obj.size > cls.MAX_FILE_SIZE:
            raise ValidationError(f"Signature file size exceeds maximum limit of {cls.MAX_FILE_SIZE // (1024 * 1024)}MB.")

        content = file_obj.read()
        file_obj.seek(0)
        content_hash = hashlib.sha256(content).hexdigest()

        try:
            with Image.open(BytesIO(content)) as img:
                img_format = img.format
                width, height = img.size

                if img_format not in cls.ALLOWED_FORMATS:
                    raise ValidationError(f"Unsupported image format '{img_format}'. Only PNG and JPEG are allowed for signatures.")

                if width * height > cls.MAX_PIXELS:
                    raise ValidationError("Signature image resolution is too high (potential decompression bomb).")

                if width > cls.MAX_DIMENSION or height > cls.MAX_DIMENSION:
                    raise ValidationError(f"Signature dimensions exceed maximum allowed limit of {cls.MAX_DIMENSION}px.")

                mime_type = f"image/{img_format.lower()}"
                if mime_type == "image/jpg":
                    mime_type = "image/jpeg"

                return {
                    "mime_type": mime_type,
                    "width": width,
                    "height": height,
                    "file_size": file_obj.size,
                    "content_hash": content_hash,
                }
        except ValidationError:
            raise
        except Exception as exc:
            raise ValidationError("Invalid or corrupted signature image file.") from exc

    @classmethod
    @transaction.atomic
    def create_signature(
        cls,
        *,
        name: str,
        signatory_name: str,
        signatory_title: str,
        description: str = "",
        file: UploadedFile,
        user=None,
    ) -> AuthorizedSignature:
        """Create a new AuthorizedSignature and its initial AuthorizedSignatureVersion 1."""
        meta = cls.validate_and_process_upload(file)

        signature = AuthorizedSignature.objects.create(
            name=name.strip(),
            signatory_name=signatory_name.strip(),
            signatory_title=signatory_title.strip(),
            description=description.strip(),
            is_active=True,
            created_by=user,
        )

        version = AuthorizedSignatureVersion.objects.create(
            signature=signature,
            version_number=1,
            image=file,
            mime_type=meta["mime_type"],
            width=meta["width"],
            height=meta["height"],
            file_size=meta["file_size"],
            content_hash=meta["content_hash"],
            uploaded_by=user,
        )

        signature.current_version = version
        signature.save(update_fields=("current_version", "updated_at"))
        return signature

    @classmethod
    @transaction.atomic
    def replace_signature_image(
        cls,
        signature: AuthorizedSignature,
        *,
        file: UploadedFile,
        user=None,
    ) -> AuthorizedSignatureVersion:
        """Upload a replacement signature image, creating an immutable version N+1 and making it current."""
        meta = cls.validate_and_process_upload(file)

        max_ver = signature.versions.aggregate(m=Max("version_number"))["m"] or 0
        next_ver = max_ver + 1

        new_version = AuthorizedSignatureVersion.objects.create(
            signature=signature,
            version_number=next_ver,
            image=file,
            mime_type=meta["mime_type"],
            width=meta["width"],
            height=meta["height"],
            file_size=meta["file_size"],
            content_hash=meta["content_hash"],
            uploaded_by=user,
        )

        signature.current_version = new_version
        signature.save(update_fields=("current_version", "updated_at"))
        return new_version

    @classmethod
    def activate_signature(cls, signature: AuthorizedSignature) -> AuthorizedSignature:
        signature.is_active = True
        signature.save(update_fields=("is_active", "updated_at"))
        return signature

    @classmethod
    def deactivate_signature(cls, signature: AuthorizedSignature) -> AuthorizedSignature:
        signature.is_active = False
        signature.save(update_fields=("is_active", "updated_at"))
        return signature

    @classmethod
    def find_referenced_signature_version_ids(cls, layout: dict) -> set[int]:
        """Extract all signature_version_ids referenced in a layout dictionary."""
        version_ids = set()
        if not isinstance(layout, dict):
            return version_ids

        for element in layout.get("elements", []):
            if isinstance(element, dict) and element.get("type") == "signature":
                ver_id = element.get("signature_version_id")
                if ver_id:
                    try:
                        version_ids.add(int(ver_id))
                    except (ValueError, TypeError):
                        pass
        return version_ids

    @classmethod
    def is_version_referenced(cls, version: AuthorizedSignatureVersion) -> bool:
        """Check if an exact signature version is referenced in any template version layout."""
        version_id = version.id
        for tmpl_ver in IDCardTemplateVersion.objects.all():
            for layout in (tmpl_ver.front_layout, tmpl_ver.back_layout):
                if version_id in cls.find_referenced_signature_version_ids(layout):
                    return True
        return False

    @classmethod
    def is_signature_referenced(cls, signature: AuthorizedSignature) -> bool:
        """Check if any version of this signature is referenced in any template version layout."""
        version_ids = set(signature.versions.values_list("id", flat=True))
        if not version_ids:
            return False

        for tmpl_ver in IDCardTemplateVersion.objects.all():
            for layout in (tmpl_ver.front_layout, tmpl_ver.back_layout):
                referenced = cls.find_referenced_signature_version_ids(layout)
                if referenced.intersection(version_ids):
                    return True
        return False

    @classmethod
    def delete_signature(cls, signature: AuthorizedSignature) -> None:
        """Protect referenced signatures from hard-deletion."""
        if cls.is_signature_referenced(signature):
            raise ValidationError(
                "Cannot delete an authorized signature referenced by existing ID card templates. Deactivate it instead."
            )
        signature.delete()
