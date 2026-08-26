import json
from decimal import Decimal
from numbers import Integral, Real

from django.core.exceptions import ValidationError

from idcards.services.fields import DynamicFieldRegistry
from idcards.services.icons import IconRegistry


class LayoutValidator:
    """Version-aware, non-mutating validation for persisted layouts."""

    ELEMENT_TYPES = {
        "text", "dynamic_text", "photo", "school_logo", "image",
        "shape", "qr", "barcode", "icon", "signature",
    }
    MAX_ELEMENTS = 200
    MAX_LAYOUT_BYTES = 256 * 1024
    DESIGN_MAJOR_AXIS = 10000
    MIN_ELEMENT_SIZE = 1

    FONT_ALLOWLIST = {
        "Inter", "Roboto", "Outfit", "Open Sans", "Montserrat",
        "Merriweather", "Playfair Display", "JetBrains Mono", "Fira Code",
        "system-ui", "sans-serif", "serif", "monospace",
    }
    OVERFLOW_MODES = {"AUTO_FIT", "WRAP", "TRUNCATE"}
    IMAGE_FIT_MODES = {"contain", "cover", "fill"}

    @classmethod
    def canvas_dimensions(cls, width_mm, height_mm, orientation):
        width, height = Decimal(str(width_mm)), Decimal(str(height_mm))
        if width <= 0 or height <= 0:
            raise ValidationError("Physical dimensions must be positive.")
        if orientation == "LANDSCAPE":
            if width < height:
                raise ValidationError("Landscape layouts require width to be at least height.")
            return cls.DESIGN_MAJOR_AXIS, round(cls.DESIGN_MAJOR_AXIS * float(height / width))
        if orientation == "PORTRAIT":
            if height < width:
                raise ValidationError("Portrait layouts require height to be at least width.")
            return round(cls.DESIGN_MAJOR_AXIS * float(width / height)), cls.DESIGN_MAJOR_AXIS
        raise ValidationError("Unknown orientation.")

    @classmethod
    def validate(cls, layout, holder_type, *, width_mm=None, height_mm=None, orientation=None):
        if not isinstance(layout, dict):
            raise ValidationError("Layout must be an object.")
        try:
            size = len(json.dumps(layout, separators=(",", ":"), ensure_ascii=False).encode())
        except (TypeError, ValueError):
            raise ValidationError("Layout must contain JSON-compatible values.")
        if size > cls.MAX_LAYOUT_BYTES:
            raise ValidationError(f"Layout exceeds the {cls.MAX_LAYOUT_BYTES}-byte limit.")
        version = layout.get("schema_version")
        if version == 1:
            return cls._validate_v1(layout, holder_type)
        if version == 2:
            return cls._validate_v2(layout, holder_type, width_mm, height_mm, orientation)
        raise ValidationError(f"Unsupported schema_version '{version}'.")

    @classmethod
    def _elements(cls, layout):
        elements = layout.get("elements")
        if not isinstance(elements, list):
            raise ValidationError("elements must be a list.")
        if len(elements) > cls.MAX_ELEMENTS:
            raise ValidationError(f"A layout may contain at most {cls.MAX_ELEMENTS} elements.")
        return elements

    @classmethod
    def _identity(cls, element, index, seen):
        if not isinstance(element, dict):
            raise ValidationError(f"Element {index} must be an object.")
        element_id = element.get("id")
        if not isinstance(element_id, str) or not element_id.strip():
            raise ValidationError(f"Element {index} requires a non-empty string id.")
        if element_id in seen:
            raise ValidationError(f"Duplicate element id '{element_id}'.")
        seen.add(element_id)
        if element.get("type") not in cls.ELEMENT_TYPES:
            raise ValidationError(f"Unknown element type '{element.get('type')}'.")
        return element_id

    @classmethod
    def _validate_v1(cls, layout, holder_type):
        seen = set()
        for index, element in enumerate(cls._elements(layout)):
            element_id = cls._identity(element, index, seen)
            for name in ("x", "y", "width", "height"):
                value = element.get(name)
                if isinstance(value, bool) or not isinstance(value, Real) or value < 0 or value > 10000:
                    raise ValidationError(f"Element '{element_id}' has invalid {name}.")
            field = element.get("field")
            if element["type"] in {"dynamic_text", "photo", "school_logo", "qr", "barcode"}:
                if not field:
                    raise ValidationError(f"Element '{element_id}' requires a field.")
                DynamicFieldRegistry.require(field, holder_type)
        return layout

    @classmethod
    def _validate_v2(cls, layout, holder_type, width_mm, height_mm, orientation):
        if width_mm is None or height_mm is None or orientation is None:
            raise ValidationError("Schema v2 validation requires physical dimensions and orientation.")
        canvas_width, canvas_height = cls.canvas_dimensions(width_mm, height_mm, orientation)
        coordinates = layout.get("coordinate_system")
        if not isinstance(coordinates, dict) or coordinates.get("unit") != "design_unit":
            raise ValidationError("coordinate_system.unit must be 'design_unit'.")
        if coordinates.get("width") != canvas_width or coordinates.get("height") != canvas_height:
            raise ValidationError(f"coordinate_system must be {canvas_width} × {canvas_height}.")

        # Background validation
        bg = layout.get("background")
        if not isinstance(bg, dict):
            raise ValidationError("background must be an object.")
        bg_type = bg.get("type", "color")
        if bg_type not in {"color", "image"}:
            raise ValidationError(f"Unsupported background type '{bg_type}'.")

        # Safe area validation
        safe_area = layout.get("safe_area")
        if not isinstance(safe_area, dict):
            raise ValidationError("safe_area must be an object.")

        seen, seen_z = set(), set()
        for index, element in enumerate(cls._elements(layout)):
            element_id = cls._identity(element, index, seen)
            values = {}
            for name in ("x", "y", "width", "height"):
                value = element.get(name)
                if isinstance(value, bool) or not isinstance(value, Real):
                    raise ValidationError(f"Element '{element_id}' has invalid {name}.")
                values[name] = value
            if values["x"] < 0 or values["y"] < 0:
                raise ValidationError(f"Element '{element_id}' coordinates cannot be negative.")
            if values["width"] < cls.MIN_ELEMENT_SIZE or values["height"] < cls.MIN_ELEMENT_SIZE:
                raise ValidationError(f"Element '{element_id}' dimensions are below the minimum size.")
            if values["x"] + values["width"] > canvas_width or values["y"] + values["height"] > canvas_height:
                raise ValidationError(f"Element '{element_id}' is outside the canvas bounds.")
            rotation = element.get("rotation", 0)
            if isinstance(rotation, bool) or not isinstance(rotation, Real) or not -360 <= rotation <= 360:
                raise ValidationError(f"Element '{element_id}' has invalid rotation.")
            z_index = element.get("z_index")
            if isinstance(z_index, bool) or not isinstance(z_index, Integral) or z_index < 0:
                raise ValidationError(f"Element '{element_id}' requires a non-negative integer z_index.")
            if z_index in seen_z:
                raise ValidationError(f"Duplicate z_index '{z_index}'.")
            seen_z.add(z_index)
            for field in ("visible", "locked"):
                if not isinstance(element.get(field), bool):
                    raise ValidationError(f"Element '{element_id}' requires boolean {field}.")
            for field in ("style", "constraints"):
                if not isinstance(element.get(field), dict):
                    raise ValidationError(f"Element '{element_id}' requires object {field}.")

            style = element.get("style", {})

            # Validate Icon
            if element.get("type") == "icon":
                icon_key = element.get("icon") or style.get("icon_key")
                if not icon_key:
                    raise ValidationError(f"Element '{element_id}' requires an icon key.")
                IconRegistry.require(icon_key)

            # Validate Typography / Text styling
            if element.get("type") in {"text", "dynamic_text"}:
                font_family = style.get("font_family")
                if font_family:
                    if any(bad in str(font_family).lower() for bad in ("url(", "javascript:", "<", ">", ";", "{", "}")):
                        raise ValidationError(f"Element '{element_id}' has invalid font_family.")
                overflow = style.get("overflow")
                if overflow and overflow not in cls.OVERFLOW_MODES:
                    raise ValidationError(f"Element '{element_id}' has invalid overflow mode '{overflow}'.")

            # Validate Image styling
            if element.get("type") in {"photo", "school_logo", "image"}:
                fit = style.get("fit")
                if fit and fit not in cls.IMAGE_FIT_MODES:
                    raise ValidationError(f"Element '{element_id}' has invalid fit mode '{fit}'.")

            # Validate Signature element
            if element.get("type") == "signature":
                sig_ver_id = element.get("signature_version_id")
                if not sig_ver_id:
                    raise ValidationError(f"Element '{element_id}' requires 'signature_version_id'.")
                try:
                    ver_id_int = int(sig_ver_id)
                except (ValueError, TypeError):
                    raise ValidationError(f"Element '{element_id}' has invalid 'signature_version_id'.")

                from idcards.models import AuthorizedSignatureVersion
                if not AuthorizedSignatureVersion.objects.filter(pk=ver_id_int).exists():
                    raise ValidationError(f"Element '{element_id}' references non-existent signature version {ver_id_int}.")

                for bool_flag in ("show_signatory_name", "show_signatory_title", "show_signature_line"):
                    if bool_flag in element and not isinstance(element[bool_flag], bool):
                        raise ValidationError(f"Element '{element_id}' {bool_flag} must be a boolean.")

            cls._validate_v2_binding(element, holder_type, element_id)
        return layout

    @classmethod
    def _validate_v2_binding(cls, element, holder_type, element_id):
        binding = element.get("binding")
        required = element["type"] in {"dynamic_text", "photo", "school_logo", "qr", "barcode"}
        if binding is None:
            if required:
                raise ValidationError(f"Element '{element_id}' requires a binding.")
            return
        if not isinstance(binding, dict):
            raise ValidationError(f"Element '{element_id}' binding must be an object.")
        if set(binding) - {"field", "required", "hide_when_empty"}:
            raise ValidationError(f"Element '{element_id}' binding contains unsupported properties.")
        field = binding.get("field")
        if not isinstance(field, str) or not field:
            raise ValidationError(f"Element '{element_id}' binding requires a field.")
        DynamicFieldRegistry.require(field, holder_type)
        for name in ("required", "hide_when_empty"):
            if name in binding and not isinstance(binding[name], bool):
                raise ValidationError(f"Element '{element_id}' binding.{name} must be boolean.")


class LayoutService:
    @classmethod
    def read(cls, layout, holder_type, **dimension_context):
        LayoutValidator.validate(layout, holder_type, **dimension_context)
        return layout

    @classmethod
    def empty_v2(cls, width_mm, height_mm, orientation):
        width, height = LayoutValidator.canvas_dimensions(width_mm, height_mm, orientation)
        return {
            "schema_version": 2,
            "coordinate_system": {"unit": "design_unit", "width": width, "height": height},
            "background": {"type": "color", "color": "#ffffff"},
            "safe_area": {"top": 250, "right": 250, "bottom": 250, "left": 250},
            "elements": [],
        }


class TemplateService:
    @classmethod
    def validate_template(cls, template):
        template.full_clean()
        version = template.current_draft_version or template.current_published_version
        if version:
            version.full_clean()
        return template

    @classmethod
    def dynamic_keys(cls, template_or_version):
        keys = []
        for layout in (template_or_version.front_layout, template_or_version.back_layout):
            for element in layout.get("elements", []):
                binding = element.get("binding") or {}
                field = element.get("field") or binding.get("field")
                if field and field not in keys:
                    keys.append(field)
        return keys
