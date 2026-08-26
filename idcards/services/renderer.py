import base64
import html
import mimetypes
from decimal import Decimal

from django.core.files.base import File
from weasyprint import HTML

from idcards.models import IDCardDesignAsset
from idcards.services.fields import DynamicFieldRegistry
from idcards.services.icons import IconRegistry
from idcards.services.layout import TemplateService


class IDCardRenderService:
    """Authoritative backend render & export service for single ID cards."""

    @classmethod
    def get_card_version(cls, card):
        """Card's immutable template_version takes precedence."""
        return card.template_version or card.template.current_published_version

    @classmethod
    def get_preview_data(cls, card):
        version = cls.get_card_version(card)
        front_layout = version.front_layout if version else card.template.front_layout
        back_layout = version.back_layout if version else card.template.back_layout
        width_mm = version.width_mm if version else card.template.width_mm
        height_mm = version.height_mm if version else card.template.height_mm
        orientation = getattr(
            version, "orientation",
            "LANDSCAPE" if Decimal(str(width_mm)) >= Decimal(str(height_mm)) else "PORTRAIT",
        )

        keys = TemplateService.dynamic_keys(version or card.template)
        values = DynamicFieldRegistry.resolve(keys, card)

        holder_name = card.student.full_name if card.student_id else card.staff.full_name
        holder_id = card.student.admission_number if card.student_id else card.staff.staff_id
        holder_context = (
            str(card.student.classroom) if card.student_id and card.student.classroom_id
            else (card.staff.designation or card.staff.get_role_display()) if card.staff_id
            else ""
        )
        photo_url = (
            card.student.image.url if card.student_id and card.student.image
            else card.staff.image.url if card.staff_id and card.staff.image
            else ""
        )

        signatures_map = {}
        for layout_dict in (front_layout, back_layout):
            if isinstance(layout_dict, dict):
                for el in layout_dict.get("elements", []):
                    if isinstance(el, dict) and el.get("type") == "signature":
                        sv_id = el.get("signature_version_id")
                        if sv_id and sv_id not in signatures_map:
                            sig_data = cls._get_signature_version_data(sv_id)
                            if sig_data:
                                signatures_map[sv_id] = sig_data

        return {
            "card": {
                "id": card.id,
                "card_number": card.card_number,
                "status": card.status,
                "effective_status": card.effective_status,
                "holder_type": card.holder_type,
                "issued_at": card.issued_at.isoformat() if card.issued_at else None,
                "expires_at": card.expires_at.isoformat() if card.expires_at else None,
            },
            "holder": {
                "id": card.student_id or card.staff_id,
                "type": card.holder_type,
                "name": holder_name,
                "identifier": holder_id,
                "context": holder_context,
                "photo_url": photo_url,
            },
            "template": {
                "id": card.template_id,
                "name": card.template.name,
            },
            "template_version": {
                "id": version.id if version else None,
                "version_number": version.version_number if version else None,
                "status": version.status if version else None,
                "width_mm": str(width_mm),
                "height_mm": str(height_mm),
                "orientation": orientation,
            },
            "front_layout": front_layout,
            "back_layout": back_layout,
            "values": values,
            "signatures": signatures_map,
        }

    @classmethod
    def _to_data_uri_or_url(cls, value):
        """Convert a File or URL to a usable HTML image src without filesystem path assumptions."""
        if not value:
            return ""
        if isinstance(value, File):
            try:
                value.seek(0)
                content = value.read()
                mime, _ = mimetypes.guess_type(getattr(value, "name", "image.jpg"))
                mime = mime or "image/jpeg"
                b64 = base64.b64encode(content).decode("utf-8")
                return f"data:{mime};base64,{b64}"
            except Exception:
                return getattr(value, "url", "")
        return str(value)

    @classmethod
    def _get_asset_data_uri(cls, asset_id):
        if not asset_id:
            return ""
        try:
            asset = IDCardDesignAsset.objects.filter(pk=asset_id, is_active=True).first()
            if asset and asset.file:
                return cls._to_data_uri_or_url(asset.file)
        except Exception:
            pass
        return ""

    @classmethod
    def _get_signature_version_data(cls, version_id):
        if not version_id:
            return None
        try:
            from idcards.models import AuthorizedSignatureVersion
            version = AuthorizedSignatureVersion.objects.select_related("signature").filter(pk=version_id).first()
            if version:
                return {
                    "id": version.id,
                    "version_number": version.version_number,
                    "src": cls._to_data_uri_or_url(version.image) if version.image else "",
                    "signatory_name": version.signature.signatory_name,
                    "signatory_title": version.signature.signatory_title,
                    "signature_name": version.signature.name,
                    "is_active": version.signature.is_active,
                }
        except Exception:
            pass
        return None

    @classmethod
    def render_element_html(cls, element, values, schema_version, canvas_w=10000, canvas_h=6306):
        el_type = element.get("type", "text")
        visible = element.get("visible", True)
        if not visible:
            return ""

        # Position & Sizing
        if schema_version == 2:
            x_pct = (element.get("x", 0) / canvas_w) * 100
            y_pct = (element.get("y", 0) / canvas_h) * 100
            w_pct = (element.get("width", 100) / canvas_w) * 100
            h_pct = (element.get("height", 100) / canvas_h) * 100
            rotation = element.get("rotation", 0)
            z_index = element.get("z_index", 0)
            style_dict = element.get("style", {})
            font_size = style_dict.get("font_size", 14)
            color = style_dict.get("color", "#111827")
            bg = style_dict.get("fill") if el_type == "shape" else style_dict.get("background", "transparent")
            border_color = style_dict.get("border_color", "transparent")
            border_width = style_dict.get("border_width", 0)
            border_radius = style_dict.get("radius", 0)
            opacity = style_dict.get("opacity", 1)
            font_weight = style_dict.get("font_weight", "normal")
            text_align = style_dict.get("text_align", "left")
            font_family = style_dict.get("font_family")
            font_style = style_dict.get("font_style", "normal")
            text_decoration = style_dict.get("text_decoration", "none")
            text_transform = style_dict.get("text_transform", "none")
            letter_spacing = style_dict.get("letter_spacing", 0)
            line_height = style_dict.get("line_height", 1.2)
            fit = style_dict.get("fit", "contain")
            binding = element.get("binding") or {}
            field_key = binding.get("field", "")
            hide_when_empty = binding.get("hide_when_empty", False)
        else:
            # Schema v1
            x_pct = element.get("x", 0)
            y_pct = element.get("y", 0)
            w_pct = element.get("width", 100)
            h_pct = element.get("height", 100)
            rotation = 0
            z_index = 0
            font_size = element.get("font_size", 14)
            color = element.get("color", "#111827")
            bg = element.get("background", "transparent")
            border_color = "transparent"
            border_width = 0
            border_radius = 0
            opacity = 1
            font_weight = "normal"
            text_align = "left"
            font_family = None
            font_style = "normal"
            text_decoration = "none"
            text_transform = "none"
            letter_spacing = 0
            line_height = 1.2
            fit = "contain"
            field_key = element.get("field", "")
            hide_when_empty = False

        # Hide When Empty check for dynamic elements
        if el_type == "dynamic_text":
            resolved = values.get(field_key, "")
            if hide_when_empty and (resolved is None or str(resolved).strip() == ""):
                return ""
            inner_content = html.escape(str(resolved))
        elif el_type == "text":
            text_val = element.get("text", "")
            inner_content = html.escape(str(text_val))
        elif el_type == "icon":
            icon_key = element.get("icon") or (element.get("style", {}) or {}).get("icon_key", "lucide:star")
            inner_content = IconRegistry.render_svg(icon_key, size=24, color=color, opacity=opacity)
        elif el_type in ("photo", "school_logo", "image"):
            if el_type == "photo":
                img_url = values.get("student.photo") or values.get("staff.photo") or ""
                src = cls._to_data_uri_or_url(img_url)
            elif el_type == "school_logo":
                img_url = values.get("school.logo") or ""
                src = cls._to_data_uri_or_url(img_url)
            else:
                asset_id = element.get("asset_id") or (element.get("style", {}) or {}).get("asset_id")
                src = cls._get_asset_data_uri(asset_id) or cls._to_data_uri_or_url(values.get(field_key, ""))

            if src:
                inner_content = f'<img src="{src}" style="width:100%;height:100%;object-fit:{fit};display:block;" alt="" />'
            else:
                inner_content = f'<div style="width:100%;height:100%;background:#e5e7eb;display:flex;align-items:center;justify-content:center;color:#9ca3af;font-size:10px;">{el_type.replace("_", " ").title()}</div>'
        elif el_type == "qr":
            qr_val = values.get(field_key or "card.card_number", "")
            inner_content = f'<div style="width:100%;height:100%;border:1px solid #d1d5db;background:#f9fafb;display:flex;flex-direction:column;align-items:center;justify-content:center;font-size:8px;color:#4b5563;text-align:center;padding:2px;"><span>QR Code</span><span style="font-size:6px;word-break:break-all;opacity:0.7;">{html.escape(str(qr_val)[:12])}</span></div>'
        elif el_type == "barcode":
            barcode_val = values.get(field_key or "card.card_number", "")
            inner_content = f'<div style="width:100%;height:100%;border:1px dashed #9ca3af;background:#f3f4f6;display:flex;flex-direction:column;align-items:center;justify-content:center;font-size:8px;font-family:monospace;color:#1f2937;"><span>||| | |||| | ||</span><span>{html.escape(str(barcode_val))}</span></div>'
        elif el_type == "signature":
            sig_ver_id = element.get("signature_version_id")
            sig_data = cls._get_signature_version_data(sig_ver_id)
            if sig_data and sig_data["src"]:
                show_line = element.get("show_signature_line", True)
                show_name = element.get("show_signatory_name", True)
                show_title = element.get("show_signatory_title", True)
                grayscale_style = "filter: grayscale(100%);" if style_dict.get("grayscale") else ""

                parts = [
                    f'<img src="{sig_data["src"]}" style="max-height:60%;max-width:100%;object-fit:{fit};display:block;margin:0 auto;{grayscale_style}" alt="{html.escape(sig_data["signatory_name"])}" />'
                ]
                if show_line:
                    parts.append('<div style="width:80%;border-top:1px solid #1f2937;margin:2px auto 3px auto;"></div>')
                if show_name and sig_data["signatory_name"]:
                    parts.append(f'<div style="font-size:{font_size * 0.7}pt;font-weight:700;line-height:1.1;color:#111827;">{html.escape(sig_data["signatory_name"])}</div>')
                if show_title and sig_data["signatory_title"]:
                    parts.append(f'<div style="font-size:{font_size * 0.55}pt;font-weight:400;line-height:1.1;color:#4b5563;">{html.escape(sig_data["signatory_title"])}</div>')

                inner_content = f'<div style="width:100%;height:100%;display:flex;flex-direction:column;align-items:center;justify-content:flex-end;text-align:center;box-sizing:border-box;padding:2px;">{"".join(parts)}</div>'
            else:
                inner_content = '<div style="width:100%;height:100%;border:1px dashed #d1d5db;display:flex;align-items:center;justify-content:center;font-size:9px;color:#9ca3af;">Authorized Signature</div>'
        elif el_type == "shape":
            inner_content = ""
        else:
            inner_content = ""

        # Style string
        styles = [
            f"position: absolute;",
            f"left: {x_pct}%;",
            f"top: {y_pct}%;",
            f"width: {w_pct}%;",
            f"height: {h_pct}%;",
            f"z-index: {z_index};",
            f"color: {color};",
            f"background-color: {bg};",
            f"font-size: {font_size * 0.75}pt;",
            f"font-weight: {font_weight};",
            f"font-style: {font_style};",
            f"text-decoration: {text_decoration};",
            f"text-transform: {text_transform};",
            f"text-align: {text_align};",
            f"line-height: {line_height};",
            f"opacity: {opacity};",
            f"display: flex;",
            f"align-items: center;",
            f"box-sizing: border-box;",
            f"overflow: hidden;",
        ]
        if font_family:
            styles.append(f'font-family: "{font_family}", sans-serif;')
        if letter_spacing:
            styles.append(f"letter-spacing: {letter_spacing}px;")

        if text_align == "center":
            styles.append("justify-content: center;")
        elif text_align == "right":
            styles.append("justify-content: flex-end;")
        else:
            styles.append("justify-content: flex-start;")

        if border_width > 0:
            styles.append(f"border: {border_width}px solid {border_color};")
        if border_radius > 0:
            styles.append(f"border-radius: {border_radius}px;")
        if rotation != 0:
            styles.append(f"transform: rotate({rotation}deg);")

        style_attr = " ".join(styles)
        return f'<div class="element" style="{style_attr}">{inner_content}</div>'

    @classmethod
    def render_side_html(cls, layout, values, width_mm, height_mm):
        schema_version = layout.get("schema_version", 1)
        coords = layout.get("coordinate_system", {})
        canvas_w = coords.get("width", 10000)
        canvas_h = coords.get("height", 6306)
        bg_config = layout.get("background", {})

        bg_styles = []
        if isinstance(bg_config, dict):
            bg_type = bg_config.get("type", "color")
            if bg_type == "image":
                asset_id = bg_config.get("asset_id")
                img_src = cls._get_asset_data_uri(asset_id)
                fit = bg_config.get("fit", "cover")
                if img_src:
                    bg_styles.append(f"background-image: url('{img_src}');")
                    bg_styles.append(f"background-size: {fit};")
                    bg_styles.append("background-position: center;")
                    bg_styles.append("background-repeat: no-repeat;")
            else:
                bg_color = bg_config.get("color", "#ffffff")
                bg_styles.append(f"background-color: {bg_color};")
        else:
            bg_styles.append("background-color: #ffffff;")

        bg_style_str = " ".join(bg_styles)

        elements_html = []
        for element in layout.get("elements", []):
            el_html = cls.render_element_html(element, values, schema_version, canvas_w, canvas_h)
            if el_html:
                elements_html.append(el_html)

        elements_str = "\n".join(elements_html)
        return f"""
        <div class="card-page" style="width: {width_mm}mm; height: {height_mm}mm; {bg_style_str}">
            {elements_str}
        </div>
        """

    @classmethod
    def render_html(cls, card):
        data = cls.get_preview_data(card)
        width_mm = data["template_version"]["width_mm"]
        height_mm = data["template_version"]["height_mm"]
        front_layout = data["front_layout"]
        back_layout = data["back_layout"]
        values = data["values"]

        front_html = cls.render_side_html(front_layout, values, width_mm, height_mm)
        back_html = cls.render_side_html(back_layout, values, width_mm, height_mm)

        return f"""<!DOCTYPE html>
<html>
<head>
<meta charset="utf-8">
<title>ID Card - {html.escape(card.card_number)}</title>
<style>
@page {{
    size: {width_mm}mm {height_mm}mm;
    margin: 0;
}}
* {{
    box-sizing: border-box;
    margin: 0;
    padding: 0;
}}
html, body {{
    margin: 0;
    padding: 0;
    font-family: -apple-system, BlinkMacSystemFont, "Segoe UI", Roboto, Helvetica, Arial, sans-serif;
    -webkit-print-color-adjust: exact;
    print-color-adjust: exact;
}}
.card-page {{
    position: relative;
    overflow: hidden;
    page-break-inside: avoid;
}}
.card-page:first-child {{
    page-break-after: always;
}}
.element {{
    position: absolute;
    box-sizing: border-box;
    overflow: hidden;
    line-height: 1.2;
}}
</style>
</head>
<body>
{front_html}
{back_html}
</body>
</html>"""

    @classmethod
    def generate_pdf(cls, card):
        html_content = cls.render_html(card)
        return HTML(string=html_content).write_pdf()
