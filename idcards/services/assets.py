"""Design asset validation, security, and centralized reference discovery."""

import hashlib
from io import BytesIO
from PIL import Image

from django.core.exceptions import ValidationError
from django.core.files.uploadedfile import UploadedFile

from idcards.models import IDCardDesignAsset, IDCardTemplateVersion


class IDCardAssetService:
    """Service for securely uploading, archiving, and validating ID card design assets."""

    MAX_FILE_SIZE = 5 * 1024 * 1024  # 5 MB
    MAX_DIMENSION = 4000
    MAX_PIXELS = 25_000_000  # 25 MP local decompression check
    ALLOWED_FORMATS = {"PNG", "JPEG", "WEBP"}
    ALLOWED_MIMES = {"image/png", "image/jpeg", "image/webp"}

    @classmethod
    def validate_and_process_upload(cls, file_obj: UploadedFile) -> dict:
        """Validate uploaded file for MIME, format, dimension limits, and compute metadata."""
        if file_obj.size > cls.MAX_FILE_SIZE:
            raise ValidationError(f"File size exceeds maximum limit of {cls.MAX_FILE_SIZE // (1024 * 1024)}MB.")

        # Read content bytes for hash calculation
        content = file_obj.read()
        file_obj.seek(0)
        content_hash = hashlib.sha256(content).hexdigest()

        try:
            with Image.open(BytesIO(content)) as img:
                img_format = img.format
                width, height = img.size

                if img_format not in cls.ALLOWED_FORMATS:
                    raise ValidationError(f"Unsupported image format '{img_format}'. Allowed: PNG, JPEG, WEBP.")

                if width * height > cls.MAX_PIXELS:
                    raise ValidationError("Image resolution is too high (potential decompression bomb).")

                if width > cls.MAX_DIMENSION or height > cls.MAX_DIMENSION:
                    raise ValidationError(f"Image dimensions exceed maximum allowed limit of {cls.MAX_DIMENSION}px.")

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
            raise ValidationError("Invalid or corrupted image file.") from exc

    @classmethod
    def create_asset(cls, *, file, name: str, asset_type: str = IDCardDesignAsset.AssetType.IMAGE, user=None) -> IDCardDesignAsset:
        meta = cls.validate_and_process_upload(file)
        asset = IDCardDesignAsset.objects.create(
            name=name.strip() or file.name,
            asset_type=asset_type,
            file=file,
            mime_type=meta["mime_type"],
            width=meta["width"],
            height=meta["height"],
            file_size=meta["file_size"],
            content_hash=meta["content_hash"],
            uploaded_by=user,
            is_active=True,
        )
        return asset

    @classmethod
    def find_referenced_asset_ids(cls, layout: dict) -> set[int]:
        """Extract all asset_ids referenced in a layout dictionary (elements or background)."""
        asset_ids = set()
        if not isinstance(layout, dict):
            return asset_ids

        # Check background
        bg = layout.get("background")
        if isinstance(bg, dict) and bg.get("type") == "image" and bg.get("asset_id"):
            try:
                asset_ids.add(int(bg["asset_id"]))
            except (ValueError, TypeError):
                pass

        # Check elements
        for element in layout.get("elements", []):
            if isinstance(element, dict):
                # image element
                if element.get("type") == "image":
                    asset_id = element.get("asset_id") or (element.get("style", {}) or {}).get("asset_id")
                    if asset_id:
                        try:
                            asset_ids.add(int(asset_id))
                        except (ValueError, TypeError):
                            pass
                # style asset_id (e.g. watermark or custom asset)
                style = element.get("style")
                if isinstance(style, dict) and style.get("asset_id"):
                    try:
                        asset_ids.add(int(style["asset_id"]))
                    except (ValueError, TypeError):
                        pass

        return asset_ids

    @classmethod
    def is_asset_referenced(cls, asset: IDCardDesignAsset) -> bool:
        """Central discovery check: is this asset referenced in any template version (draft or published)?"""
        asset_id = asset.id
        for version in IDCardTemplateVersion.objects.all():
            for layout in (version.front_layout, version.back_layout):
                if asset_id in cls.find_referenced_asset_ids(layout):
                    return True
        return False

    @classmethod
    def archive_asset(cls, asset: IDCardDesignAsset) -> IDCardDesignAsset:
        asset.is_active = False
        asset.save(update_fields=("is_active", "updated_at"))
        return asset

    @classmethod
    def delete_asset(cls, asset: IDCardDesignAsset) -> None:
        if cls.is_asset_referenced(asset):
            raise ValidationError(
                "Cannot delete an asset referenced by existing card templates. Archive the asset instead."
            )
        asset.delete()
