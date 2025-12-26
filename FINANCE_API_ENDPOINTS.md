# Finance API Endpoints - Student Fees

## Overview

Finance endpoints for managing student fees, payments, and receipts.

**Base URL**: `/api/finance/`

---

## 1. Fee Balance

### Get Student Fee Balance

**GET** `/api/finance/fee-balance/?student={student_id}`

Returns the fee balance summary for a student.

#### Query Parameters:
- `student` (**required**) - Student ID
- `term` (optional) - Term ID (defaults to current term)

#### Response Structure:
```json
{
  "id": 505,
  "student": 505,
  "student_name": "Jane Mary Doe",
  "student_admission_number": "TEST/2024/001",
  "term": 1,
  "term_name": "First Term",
  "academic_year": "2024/2025",
  "total_fee": "50000.00",
  "amount_paid": "30000.00",
  "balance": "20000.00",
  "status": "partial",
  "last_payment_date": "2025-12-01",
  "fee_breakdown": [
    {
      "id": 1,
      "fee_name": "Tuition Fee - Term 1",
      "fee_type": "Tuition",
      "amount_owed": "45000.00",
      "amount_paid": "25000.00",
      "balance": "20000.00",
      "status": "Partial",
      "is_waived": false
    },
    {
      "id": 2,
      "fee_name": "Transport Fee",
      "fee_type": "Transport",
      "amount_owed": "5000.00",
      "amount_paid": "5000.00",
      "balance": "0.00",
      "status": "Paid",
      "is_waived": false
    }
  ]
}
```

#### Status Values:
- `paid` - Fully paid
- `partial` - Partially paid
- `unpaid` - Not paid at all

#### Examples:
```bash
# Get balance for current term
GET /api/finance/fee-balance/?student=505

# Get balance for specific term
GET /api/finance/fee-balance/?student=505&term=1
```

---

## 2. Payment History (Receipts)

### Get Student Receipts

**GET** `/api/finance/receipts/?student={student_id}`

Returns all payment receipts for a student.

#### Query Parameters:
- `student` (optional) - Filter by student ID
- `term` (optional) - Filter by term ID
- `status` (optional) - Filter by status
- `date__gte` (optional) - From date (YYYY-MM-DD)
- `date__lte` (optional) - To date (YYYY-MM-DD)

#### Response Structure:
```json
[
  {
    "id": 1,
    "receipt_number": "RCP-2025-001",
    "student": 505,
    "student_name": "Jane Mary Doe",
    "amount": "25000.00",
    "payer": "John Doe",
    "paid_through": "Cash",
    "payment_date": "2025-12-01",
    "date": "2025-12-01T10:30:00Z",
    "term": 1,
    "term_name": "First Term",
    "academic_year": "2024/2025",
    "reference_number": null,
    "status": "Completed",
    "received_by": "Admin User",
    "notes": "Payment for tuition",
    "fee_allocations": [
      {
        "fee_assignment": 1,
        "fee_name": "Tuition Fee - Term 1",
        "amount": "25000.00"
      }
    ]
  }
]
```

#### Payment Methods (paid_through):
- `Cash`
- `Bank Transfer`
- `Cheque`
- `POS`
- `Mobile Money`
- `Online`

#### Examples:
```bash
# Get all receipts for a student
GET /api/finance/receipts/?student=505

# Get receipts for specific term
GET /api/finance/receipts/?student=505&term=1

# Get receipts for date range
GET /api/finance/receipts/?student=505&date__gte=2025-01-01&date__lte=2025-12-31
```

---

## 3. Fee Assignments

### Get Student Fee Assignments

**GET** `/api/finance/student-fee-assignments/?student={student_id}`

Returns all fee assignments for a student.

#### Query Parameters:
- `student` (optional) - Filter by student ID
- `term` (optional) - Filter by term ID
- `is_waived` (optional) - Filter waived fees (true/false)

#### Response Structure:
```json
[
  {
    "id": 1,
    "student": 505,
    "student_name": "Jane Mary Doe",
    "fee_structure": 1,
    "fee_name": "Tuition Fee - Term 1",
    "fee_type": "Tuition",
    "term": 1,
    "term_name": "First Term",
    "amount_owed": "45000.00",
    "amount_paid": "25000.00",
    "balance": "20000.00",
    "discount": "0.00",
    "payment_status": "Partial",
    "is_waived": false,
    "waived_reason": null,
    "assigned_date": "2025-09-01",
    "due_date": "2025-12-31"
  }
]
```

---

## Frontend Integration

### TypeScript Interfaces

```typescript
// Fee Balance
interface FeeBalance {
  id: number
  student: number
  student_name: string
  student_admission_number: string
  term: number
  term_name: string
  academic_year: string
  total_fee: number
  amount_paid: number
  balance: number
  status: 'paid' | 'partial' | 'unpaid'
  last_payment_date?: string | null
  fee_breakdown: FeeBreakdownItem[]
}

interface FeeBreakdownItem {
  id: number
  fee_name: string
  fee_type: string
  amount_owed: number
  amount_paid: number
  balance: number
  status: string
  is_waived: boolean
}

// Receipt (Payment)
interface Receipt {
  id: number
  receipt_number: string
  student: number
  student_name: string
  amount: number
  payer: string
  paid_through: string
  payment_date: string
  date: string
  term: number
  term_name: string
  academic_year: string
  reference_number?: string | null
  status: string
  received_by: string
  notes: string
  fee_allocations: FeeAllocation[]
}

interface FeeAllocation {
  fee_assignment: number
  fee_name: string
  amount: number
}

// Fee Assignment
interface FeeAssignment {
  id: number
  student: number
  student_name: string
  fee_structure: number
  fee_name: string
  fee_type: string
  term: number
  term_name: string
  amount_owed: number
  amount_paid: number
  balance: number
  discount: number
  payment_status: string
  is_waived: boolean
  waived_reason?: string | null
  assigned_date: string
  due_date: string
}
```

### Example API Calls

```typescript
// Get fee balance
const getFeeBalance = async (studentId: number, termId?: number) => {
  let url = `http://localhost:8000/api/finance/fee-balance/?student=${studentId}`
  
  if (termId) {
    url += `&term=${termId}`
  }
  
  const response = await fetch(url, {
    headers: {
      'Authorization': `Bearer ${accessToken}`
    }
  })
  
  return await response.json() as FeeBalance
}

// Get payment history
const getPaymentHistory = async (studentId: number) => {
  const response = await fetch(
    `http://localhost:8000/api/finance/receipts/?student=${studentId}`,
    {
      headers: {
        'Authorization': `Bearer ${accessToken}`
      }
    }
  )
  
  return await response.json() as Receipt[]
}

// Get fee assignments
const getFeeAssignments = async (studentId: number, termId?: number) => {
  let url = `http://localhost:8000/api/finance/student-fee-assignments/?student=${studentId}`
  
  if (termId) {
    url += `&term=${termId}`
  }
  
  const response = await fetch(url, {
    headers: {
      'Authorization': `Bearer ${accessToken}`
    }
  })
  
  return await response.json() as FeeAssignment[]
}
```

---

## Important Notes

1. **Authentication Required**: All endpoints require Bearer token authentication
2. **Empty Data**: Returns empty arrays or zero balances if no data found
3. **Status Values**: Fee status is lowercase (`paid`, `partial`, `unpaid`)
4. **Receipts vs Payments**: 
   - **Receipts** = Money received from students (what you want)
   - **Payments** = Money paid out by school (expenses/salaries)
5. **Default Term**: If no term specified, uses current active term

---

## Alternative Endpoint Paths

For backward compatibility, the following paths also work:

```bash
# Student balance (alternative path)
GET /api/finance/student-balance/{student_id}/?term_id=1

# Same as:
GET /api/finance/fee-balance/?student={student_id}&term=1
```

---

**Date**: December 6, 2025  
**Status**: ✅ Endpoints ready and tested
