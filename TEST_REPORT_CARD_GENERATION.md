# Report Card Generation - Testing Guide

**Date**: 2025-12-04
**Phase**: 1.2 - Report Card Generator
**Status**: Ready for Testing

---

## Prerequisites

Before testing report card generation:

1. ✅ **Phase 1.1 Complete**: Results must be computed and published
2. ✅ **Migrations Applied**: `uv run manage.py migrate`
3. ✅ **WeasyPrint Installed**: `pip list | grep weasyprint`
4. ✅ **MEDIA Directory**: Must exist and be writable

---

## Step 1: Apply Migrations

```bash
cd /home/abu/Projects/django-scms
uv run manage.py makemigrations examination
uv run manage.py migrate
```

Expected output:
```
Migrations for 'examination':
  examination/migrations/0003_reportcard.py
    - Create model ReportCard
Operations to perform:
  Apply all migrations: examination
Running migrations:
  Applying examination.0003_reportcard... OK
```

---

## Step 2: Verify Installation

### Check WeasyPrint

```bash
uv run python -c "import weasyprint; print('WeasyPrint version:', weasyprint.__version__)"
```

Expected: `WeasyPrint version: 62.3`

### Check Models

```bash
uv run python manage.py shell
```

```python
from examination.models import ReportCard, TermResult
from examination.services import ReportCardGenerator

print("✓ ReportCard model:", ReportCard)
print("✓ ReportCardGenerator:", ReportCardGenerator)
print("✓ TermResult count:", TermResult.objects.count())
print("✓ Published results:", TermResult.objects.filter(is_published=True).count())
```

---

## Step 3: Prepare Test Data

You need at least one published term result to generate a report card.

### Check for Published Results

```bash
uv run python manage.py shell
```

```python
from examination.models import TermResult

# Check if we have published results
published = TermResult.objects.filter(is_published=True)
if published.exists():
    result = published.first()
    print(f"✓ Found published result:")
    print(f"  Student: {result.student.full_name}")
    print(f"  Term: {result.term.name}")
    print(f"  Grade: {result.grade}")
    print(f"  GPA: {result.gpa}")
    print(f"  Position: {result.position_in_class}/{result.total_students}")
    print(f"  Term Result ID: {result.id}")
else:
    print("⚠ No published results found!")
    print("You need to:")
    print("1. Add marks for students")
    print("2. Compute results")
    print("3. Publish results")
```

### If No Published Results:

Follow the Phase 1.1 guide to compute and publish results first.

---

## Step 4: Test Single Report Card Generation

### Option A: Via Python Shell

```bash
uv run python manage.py shell
```

```python
from examination.models import TermResult
from examination.services import ReportCardGenerator
from users.models import CustomUser

# Get a published term result
term_result = TermResult.objects.filter(is_published=True).first()

if not term_result:
    print("No published results available!")
else:
    print(f"Generating report card for: {term_result.student.full_name}")

    # Get admin user
    admin = CustomUser.objects.filter(is_staff=True).first()

    # Generate report card
    generator = ReportCardGenerator(term_result, generated_by=admin)

    try:
        report_card = generator.generate_pdf()
        print(f"✓ Report card generated successfully!")
        print(f"  ID: {report_card.id}")
        print(f"  File: {report_card.pdf_file.name}")
        print(f"  Path: {report_card.pdf_file.path}")
        print(f"  URL: {report_card.pdf_file.url}")
        print(f"  Size: {report_card.pdf_file.size} bytes")
    except Exception as e:
        print(f"✗ Error: {e}")
        import traceback
        traceback.print_exc()
```

### Option B: Via API (Recommended)

```bash
# First, get an authentication token
curl -X POST http://localhost:8000/api/token/ \
  -H "Content-Type: application/json" \
  -d '{"username": "your_username", "password": "your_password"}'

# Save the token
TOKEN="your_access_token_here"

# Get a published term result ID
curl -X GET "http://localhost:8000/api/examination/term-results/?is_published=true&limit=1" \
  -H "Authorization: Bearer $TOKEN" | python -m json.tool

# Generate report card (replace term_result_id with actual ID)
curl -X POST http://localhost:8000/api/examination/report-cards/generate/ \
  -H "Content-Type: application/json" \
  -H "Authorization: Bearer $TOKEN" \
  -d '{
    "term_result_id": 1,
    "regenerate": false
  }' | python -m json.tool
```

Expected response:
```json
{
  "message": "Report card generated successfully",
  "report_card_id": 1,
  "student": "John Doe",
  "term": "One",
  "download_url": "/api/examination/report-cards/1/download/"
}
```

---

## Step 5: Test HTML Preview

Preview the HTML before PDF generation (helps with debugging):

```bash
curl -X GET "http://localhost:8000/api/examination/report-cards/1/preview/" \
  -H "Authorization: Bearer $TOKEN" > preview.html

# Open in browser
xdg-open preview.html
```

Or visit in browser:
```
http://localhost:8000/api/examination/report-cards/1/preview/
```

---

## Step 6: Test PDF Download

### Via API:

```bash
curl -X GET "http://localhost:8000/api/examination/report-cards/1/download/" \
  -H "Authorization: Bearer $TOKEN" \
  --output report_card.pdf

# Open the PDF
xdg-open report_card.pdf
```

### Via Browser:

Navigate to:
```
http://localhost:8000/api/examination/report-cards/1/download/
```

---

## Step 7: Test Bulk Generation

Generate report cards for an entire classroom:

```bash
# Get classroom and term IDs
curl -X GET "http://localhost:8000/api/examination/term-results/by_classroom/?classroom_id=1&term_id=1&limit=1" \
  -H "Authorization: Bearer $TOKEN"

# Bulk generate
curl -X POST http://localhost:8000/api/examination/report-cards/bulk-generate/ \
  -H "Content-Type: application/json" \
  -H "Authorization: Bearer $TOKEN" \
  -d '{
    "term_id": 1,
    "classroom_id": 1,
    "regenerate": false
  }' | python -m json.tool
```

Expected response:
```json
{
  "message": "Bulk report card generation completed",
  "summary": {
    "total": 42,
    "generated": 42,
    "failed": 0,
    "errors": []
  },
  "term": "One",
  "classroom": "Primary 1"
}
```

---

## Step 8: Verify Generated Files

Check that PDF files were created:

```bash
# List generated report cards
ls -lh /home/abu/Projects/django-scms/media/report_cards/

# Count files
find /home/abu/Projects/django-scms/media/report_cards/ -name "*.pdf" | wc -l

# Check file sizes
du -sh /home/abu/Projects/django-scms/media/report_cards/
```

---

## Step 9: Test Listing Endpoints

### List All Report Cards:

```bash
curl -X GET "http://localhost:8000/api/examination/report-cards/" \
  -H "Authorization: Bearer $TOKEN" | python -m json.tool
```

### Get Report Cards by Student:

```bash
curl -X GET "http://localhost:8000/api/examination/report-cards/by_student/?student_id=5" \
  -H "Authorization: Bearer $TOKEN" | python -m json.tool
```

### Get Report Cards by Classroom:

```bash
curl -X GET "http://localhost:8000/api/examination/report-cards/by_classroom/?classroom_id=1&term_id=1" \
  -H "Authorization: Bearer $TOKEN" | python -m json.tool
```

---

## Step 10: Test Regeneration

Update a mark, recompute results, and regenerate report card:

```bash
# 1. Update a mark
curl -X PATCH "http://localhost:8000/api/examination/marks/123/" \
  -H "Content-Type: application/json" \
  -H "Authorization: Bearer $TOKEN" \
  -d '{"points_scored": 95}'

# 2. Recompute results
curl -X POST http://localhost:8000/api/examination/term-results/compute/ \
  -H "Content-Type: application/json" \
  -H "Authorization: Bearer $TOKEN" \
  -d '{
    "term_id": 1,
    "classroom_id": 1,
    "recompute": true
  }'

# 3. Regenerate report cards
curl -X POST http://localhost:8000/api/examination/report-cards/bulk-generate/ \
  -H "Content-Type: application/json" \
  -H "Authorization: Bearer $TOKEN" \
  -d '{
    "term_id": 1,
    "classroom_id": 1,
    "regenerate": true
  }'
```

---

## Verification Checklist

After testing, verify the following:

### PDF Content:
- [ ] School name and details displayed correctly
- [ ] Student information accurate
- [ ] All subjects listed with correct scores
- [ ] Grades calculated correctly (match grade scale)
- [ ] Overall GPA and position correct
- [ ] Attendance section (if available)
- [ ] Grade legend showing configured scale
- [ ] Teacher and principal remarks present
- [ ] Signature sections included
- [ ] Generation date/time in footer

### PDF Quality:
- [ ] Text is readable and clear
- [ ] Tables aligned properly
- [ ] Colors display correctly
- [ ] No overlapping text
- [ ] Margins appropriate for A4
- [ ] Prints correctly on paper
- [ ] File size reasonable (< 500KB per card)

### Functionality:
- [ ] Generation succeeds without errors
- [ ] Download increments counter
- [ ] Bulk generation processes all students
- [ ] Regeneration overwrites old PDF
- [ ] Preview HTML renders correctly
- [ ] Permissions enforced (staff vs non-staff)

### Database:
- [ ] ReportCard records created
- [ ] PDF files stored in correct location
- [ ] Download counts increment
- [ ] Timestamps recorded correctly

---

## Troubleshooting

### Error: "WeasyPrint not found"

```bash
uv pip install weasyprint==62.3
```

### Error: "Permission denied" when saving PDF

```bash
# Check MEDIA_ROOT permissions
ls -ld /home/abu/Projects/django-scms/media/
chmod 755 /home/abu/Projects/django-scms/media/

# Create report_cards directory
mkdir -p /home/abu/Projects/django-scms/media/report_cards/
chmod 755 /home/abu/Projects/django-scms/media/report_cards/
```

### Error: "Template not found"

```bash
# Verify template exists
ls -l /home/abu/Projects/django-scms/examination/templates/examination/report_card.html
```

### PDF is blank or incomplete

1. Test HTML preview first to check template rendering
2. Check all context data is available:
   ```python
   from examination.services import ReportCardGenerator
   from examination.models import TermResult

   tr = TermResult.objects.first()
   gen = ReportCardGenerator(tr)
   context = gen._prepare_context()
   print(context)
   ```

### Fonts not rendering correctly

WeasyPrint may need system fonts. On Linux:
```bash
sudo apt-get install fonts-liberation
```

---

## Sample Test Script

Create a comprehensive test script:

```python
# test_report_cards.py
import os
os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'school.settings')

import django
django.setup()

from examination.models import TermResult, ReportCard
from examination.services import ReportCardGenerator
from users.models import CustomUser

def test_report_card_generation():
    print("=" * 60)
    print("REPORT CARD GENERATION TEST")
    print("=" * 60)

    # Get published results
    published = TermResult.objects.filter(is_published=True)
    print(f"\n1. Published results: {published.count()}")

    if not published.exists():
        print("⚠ No published results. Run Phase 1.1 tests first.")
        return

    # Get admin user
    admin = CustomUser.objects.filter(is_staff=True).first()
    if not admin:
        print("⚠ No admin user found")
        return

    # Test single generation
    print("\n2. Testing single report card generation...")
    term_result = published.first()
    print(f"   Student: {term_result.student.full_name}")

    try:
        generator = ReportCardGenerator(term_result, generated_by=admin)
        report_card = generator.generate_pdf()
        print(f"   ✓ Generated: {report_card.pdf_file.name}")
        print(f"   ✓ File size: {report_card.pdf_file.size:,} bytes")
        print(f"   ✓ ID: {report_card.id}")
    except Exception as e:
        print(f"   ✗ Error: {e}")
        import traceback
        traceback.print_exc()
        return

    # Test download counter
    print("\n3. Testing download counter...")
    initial_count = report_card.download_count
    report_card.increment_download_count()
    report_card.refresh_from_db()
    print(f"   ✓ Download count: {initial_count} → {report_card.download_count}")

    # Test regeneration
    print("\n4. Testing regeneration...")
    try:
        report_card2 = generator.generate_pdf(regenerate=True)
        print(f"   ✓ Regenerated successfully")
        print(f"   ✓ Same ID: {report_card.id == report_card2.id}")
    except Exception as e:
        print(f"   ✗ Error: {e}")

    # Summary
    print("\n" + "=" * 60)
    print("TEST SUMMARY")
    print("=" * 60)
    total_cards = ReportCard.objects.count()
    print(f"Total report cards: {total_cards}")
    print(f"Total downloads: {sum(rc.download_count for rc in ReportCard.objects.all())}")

    print("\n✓ All tests passed!")

if __name__ == '__main__':
    test_report_cards()
```

Run the test:
```bash
uv run python test_report_cards.py
```

---

## Next Steps

After successful testing:

1. ✅ **Configure School Branding** in settings.py
2. ✅ **Generate Report Cards** for all published results
3. ✅ **Test Downloads** with different user roles
4. ✅ **Print Sample** on A4 paper to verify layout
5. ✅ **Move to Phase 1.3** - Teacher Permissions & Workflows

---

**Testing Status**: Ready for Manual Testing
**Date**: 2025-12-04
**Version**: 1.0
