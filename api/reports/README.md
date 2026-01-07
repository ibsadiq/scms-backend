# Reports API

This API provides comprehensive reporting functionality for the School Management System.

## Features

- **Student Reports**: Demographics, attendance, performance, and financial data
- **Financial Reports**: Payment collections, revenue analysis, payment methods breakdown
- **Attendance Reports**: Daily attendance records and summary statistics
- **Export Functionality**: PDF and Excel/CSV export for all reports

## Endpoints

### Student Report
```
GET /api/reports/students/
```

**Query Parameters:**
- `academic_year` - Filter by academic year ID
- `term` - Filter by term ID
- `grade_level` - Filter by grade level ID
- `class_level` - Filter by class level ID
- `status` - Filter by student status (Active, Inactive, Graduated, Withdrawn)
- `date_from` - Start date for attendance/payments
- `date_to` - End date for attendance/payments

**Response:**
```json
{
  "students": [
    {
      "student_id": 1,
      "admission_number": "2025001",
      "full_name": "John Doe",
      "class_name": "JSS 1",
      "grade_level": "Junior Secondary",
      "status": "Active",
      "attendance_rate": 95.5,
      "total_present": 95,
      "total_absent": 5,
      "average_grade": "B+",
      "total_fees": 50000.00,
      "fees_paid": 30000.00,
      "balance": 20000.00
    }
  ],
  "summary": {
    "total_students": 150,
    "active_students": 145,
    "average_attendance": 92.5,
    "average_balance": 15000.00
  }
}
```

### Financial Report
```
GET /api/reports/financial/
```

**Query Parameters:**
- `academic_year` - Filter by academic year ID
- `term` - Filter by term ID
- `date_from` - Start date for payments
- `date_to` - End date for payments
- `payment_method` - Filter by payment method (Cash, Bank Transfer, Mobile Money, Cheque)
- `class_level` - Filter by class level ID

**Response:**
```json
{
  "total_collected": 5000000.00,
  "total_outstanding": 1500000.00,
  "collection_rate": 76.9,
  "payment_by_method": [
    {
      "method": "Bank Transfer",
      "amount": 2500000.00,
      "count": 150
    },
    {
      "method": "Cash",
      "amount": 1500000.00,
      "count": 200
    }
  ],
  "revenue_by_type": [
    {
      "fee_type": "Tuition",
      "amount": 4000000.00
    },
    {
      "fee_type": "Transport",
      "amount": 500000.00
    }
  ],
  "defaulters": [
    {
      "student_id": 45,
      "student_name": "Jane Smith",
      "admission_number": "2025045",
      "class_name": "SSS 2",
      "balance": 35000.00
    }
  ]
}
```

### Attendance Report
```
GET /api/reports/attendance/
```

**Query Parameters:**
- `date_from` - Start date
- `date_to` - End date
- `class_level` - Filter by class level ID

**Response:**
```json
{
  "records": [
    {
      "date": "2025-01-15",
      "class_name": "JSS 1",
      "total_students": 40,
      "present": 38,
      "absent": 2,
      "attendance_rate": 95.0
    }
  ],
  "summary": {
    "total_days": 20,
    "average_attendance": 93.5,
    "total_absences": 52
  }
}
```

### Export Endpoints

#### Student Report PDF
```
POST /api/reports/student/export/pdf/
Content-Type: application/json

{
  "class_level": 3,
  "status": "Active"
}
```

#### Student Report Excel/CSV
```
POST /api/reports/student/export/excel/
Content-Type: application/json

{
  "class_level": 3,
  "status": "Active"
}
```

#### Financial Report PDF
```
POST /api/reports/financial/export/pdf/
Content-Type: application/json

{
  "term": 1,
  "payment_method": "Cash"
}
```

#### Financial Report Excel/CSV
```
POST /api/reports/financial/export/excel/
Content-Type: application/json

{
  "term": 1,
  "payment_method": "Cash"
}
```

## Dependencies

- Django REST Framework
- ReportLab (optional, for PDF generation)

## Installation

The reports API is automatically included when you run the Django application. To enable PDF generation, install ReportLab:

```bash
pip install reportlab
```

## Usage Examples

### Python/Requests
```python
import requests

# Get student report
response = requests.get(
    'http://localhost:8000/api/reports/students/',
    params={'class_level': 3, 'status': 'Active'},
    headers={'Authorization': 'Bearer YOUR_TOKEN'}
)
data = response.json()

# Export to PDF
response = requests.post(
    'http://localhost:8000/api/reports/student/export/pdf/',
    json={'class_level': 3, 'status': 'Active'},
    headers={'Authorization': 'Bearer YOUR_TOKEN'}
)
with open('student_report.pdf', 'wb') as f:
    f.write(response.content)
```

### JavaScript/Fetch
```javascript
// Get financial report
const response = await fetch('/api/reports/financial/?term=1', {
  headers: {
    'Authorization': 'Bearer YOUR_TOKEN'
  }
});
const data = await response.json();

// Export to Excel
const exportResponse = await fetch('/api/reports/financial/export/excel/', {
  method: 'POST',
  headers: {
    'Authorization': 'Bearer YOUR_TOKEN',
    'Content-Type': 'application/json'
  },
  body: JSON.stringify({ term: 1 })
});
const blob = await exportResponse.blob();
const url = window.URL.createObjectURL(blob);
const link = document.createElement('a');
link.href = url;
link.download = 'financial_report.csv';
link.click();
```

## Notes

- All endpoints require authentication
- PDF exports require ReportLab to be installed
- CSV exports are always available
- Date filters should be in ISO format (YYYY-MM-DD)
- Large reports may take time to generate
- PDF reports are limited to 50 records to avoid performance issues
- CSV exports include all records

## Future Enhancements

- Add grade/performance calculation to student reports
- Implement caching for frequently accessed reports
- Add scheduled report generation
- Support for custom report templates
- Email delivery of reports
- More export formats (XLSX, ODS)
