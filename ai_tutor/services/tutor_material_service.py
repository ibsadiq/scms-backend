import logging
from typing import List, Optional
from academic.models import LessonPlan, LessonPlanMaterial

logger = logging.getLogger(__name__)


class TutorMaterialService:
    """
    Service responsible for extracting, filtering, and bounding lesson material
    from LessonPlanMaterial records for grounding the AI Tutor.
    """

    MAX_MATERIAL_CHARS = 10000  # Safe context bound per session

    @staticmethod
    def extract_text_from_file(file_obj) -> str:
        """
        Safely extracts text content from an uploaded document file (PDF / text).
        """
        if not file_obj:
            return ""

        filename = getattr(file_obj, "name", "").lower()
        if filename.endswith(".pdf"):
            try:
                import pypdf
                reader = pypdf.PdfReader(file_obj)
                extracted_pages = []
                for page in reader.pages[:20]:  # Bound to first 20 pages
                    page_text = page.extract_text()
                    if page_text:
                        extracted_pages.append(page_text.strip())
                return "\n".join(extracted_pages)
            except Exception as e:
                logger.warning("Failed to extract PDF text from %s: %s", filename, e)
                return ""
        elif filename.endswith((".txt", ".md", ".csv")):
            try:
                file_obj.seek(0)
                content = file_obj.read()
                if isinstance(content, bytes):
                    return content.decode("utf-8", errors="ignore")
                return str(content)
            except Exception as e:
                logger.warning("Failed to read text file %s: %s", filename, e)
                return ""

        return ""

    @classmethod
    def get_grounding_materials_text(
        cls,
        *,
        lesson_plan: Optional[LessonPlan] = None,
        max_chars: int = MAX_MATERIAL_CHARS,
    ) -> str:
        """
        Collects and formats materials from the authoritative LessonPlan.
        """
        if not lesson_plan:
            return ""

        materials = lesson_plan.materials.all()
        chunks: List[str] = []
        total_len = 0

        for mat in materials:
            header = f"--- Material: {mat.title} ---"
            body = mat.description or ""

            if mat.file:
                file_text = cls.extract_text_from_file(mat.file)
                if file_text:
                    body = f"{body}\n{file_text}".strip()

            if mat.external_url:
                body = f"{body}\nReference Link: {mat.external_url}".strip()

            if not body:
                continue

            chunk = f"{header}\n{body}\n"
            if total_len + len(chunk) > max_chars:
                remaining = max_chars - total_len
                if remaining > 100:
                    chunks.append(chunk[:remaining] + "\n[... truncated for length ...]")
                break

            chunks.append(chunk)
            total_len += len(chunk)

        return "\n".join(chunks)
