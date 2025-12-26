# urls.py
from django.urls import path, include
from rest_framework.routers import DefaultRouter
from finance.views import (
    FeeStructureViewSet,
    StudentFeeAssignmentViewSet,
    ReceiptViewSet,
    PaymentViewSet,
    PaymentCategoryViewSet,
    StudentFeeBalanceViewSet,
)

# Create router and register viewsets
router = DefaultRouter()
router.register(r'fee-structures', FeeStructureViewSet, basename='fee-structure')
router.register(r'student-fee-assignments', StudentFeeAssignmentViewSet, basename='student-fee-assignment')
router.register(r'receipts', ReceiptViewSet, basename='receipt')
router.register(r'payments', PaymentViewSet, basename='payment')
router.register(r'payment-categories', PaymentCategoryViewSet, basename='payment-category')
router.register(r'student-balance', StudentFeeBalanceViewSet, basename='student-balance')
router.register(r'fee-balance', StudentFeeBalanceViewSet, basename='fee-balance')

urlpatterns = [
    path('', include(router.urls)),
]

"""
This will create the following API endpoints:

FEE STRUCTURES:
===============
GET    /api/financial/fee-structures/                           - List all fee structures
POST   /api/financial/fee-structures/                           - Create new fee structure
GET    /api/financial/fee-structures/{id}/                      - Get specific fee structure
PUT    /api/financial/fee-structures/{id}/                      - Update fee structure (full)
PATCH  /api/financial/fee-structures/{id}/                      - Update fee structure (partial)
DELETE /api/financial/fee-structures/{id}/                      - Delete fee structure
POST   /api/financial/fee-structures/{id}/auto_assign/          - Auto-assign fee to students
GET    /api/financial/fee-structures/by_student/               - Get fees for student
       ?student_id=1&term_id=1

Query params for list:
  - academic_year=1
  - term=1
  - grade_level=2
  - class_level=3
  - fee_type=Tuition
  - is_mandatory=true
  - search=Tuition
  - ordering=name,-amount,due_date


STUDENT FEE ASSIGNMENTS:
========================
GET    /api/financial/student-fee-assignments/                  - List all assignments
POST   /api/financial/student-fee-assignments/                  - Create new assignment
GET    /api/financial/student-fee-assignments/{id}/             - Get specific assignment
PUT    /api/financial/student-fee-assignments/{id}/             - Update assignment (full)
PATCH  /api/financial/student-fee-assignments/{id}/             - Update assignment (partial)
DELETE /api/financial/student-fee-assignments/{id}/             - Delete assignment
POST   /api/financial/student-fee-assignments/{id}/waive/       - Waive fee
POST   /api/financial/student-fee-assignments/{id}/adjust_amount/ - Adjust fee amount
GET    /api/financial/student-fee-assignments/by_student/       - Get student's assignments
       ?student_id=1&term_id=1
GET    /api/financial/student-fee-assignments/unpaid/           - Get unpaid assignments
       ?term_id=1

Query params for list:
  - student=5
  - term=1
  - fee_structure=3
  - is_waived=false
  - fee_structure__fee_type=Transport
  - search=John
  - ordering=assigned_date,-amount_owed


RECEIPTS (INCOMING PAYMENTS):
==============================
GET    /api/financial/receipts/                                 - List all receipts
POST   /api/financial/receipts/                                 - Create new receipt
GET    /api/financial/receipts/{id}/                            - Get specific receipt
PUT    /api/financial/receipts/{id}/                            - Update receipt (full)
PATCH  /api/financial/receipts/{id}/                            - Update receipt (partial)
DELETE /api/financial/receipts/{id}/                            - Delete receipt
POST   /api/financial/receipts/{id}/allocate_to_fees/           - Allocate to specific fees
GET    /api/financial/receipts/by_student/                      - Get student's receipts
       ?student_id=1

Query params for list:
  - student=5
  - term=1
  - status=Completed
  - paid_through=Cash
  - received_by=2
  - search=John
  - ordering=date,-receipt_number


PAYMENTS (OUTGOING):
====================
GET    /api/financial/payments/                                 - List all payments
POST   /api/financial/payments/                                 - Create new payment
GET    /api/financial/payments/{id}/                            - Get specific payment
PUT    /api/financial/payments/{id}/                            - Update payment (full)
PATCH  /api/financial/payments/{id}/                            - Update payment (partial)
DELETE /api/financial/payments/{id}/                            - Delete payment

Query params for list:
  - category=1
  - status=Completed
  - paid_through=Bank Transfer
  - paid_by=2
  - search=salary
  - ordering=date,-amount


PAYMENT CATEGORIES:
===================
GET    /api/financial/payment-categories/                       - List all categories
POST   /api/financial/payment-categories/                       - Create new category
GET    /api/financial/payment-categories/{id}/                  - Get specific category
PUT    /api/financial/payment-categories/{id}/                  - Update category
DELETE /api/financial/payment-categories/{id}/                  - Delete category


STUDENT BALANCE:
================
GET    /api/financial/student-balance/{student_id}/             - Get student balance
       ?term_id=1
GET    /api/financial/student-balance/summary/                  - Get all students summary
       ?term_id=1


Example API Usage:
==================

1. Create fee structure (mandatory tuition):
   POST /api/financial/fee-structures/
   {
     "name": "Grade 7 Tuition - Term 1 2025",
     "fee_type": "Tuition",
     "amount": 50000.00,
     "academic_year": 1,
     "term": 1,
     "grade_level": 2,
     "is_mandatory": true,
     "due_date": "2025-03-31"
   }

2. Create optional transport fee:
   POST /api/financial/fee-structures/
   {
     "name": "Bus Service - Term 1 2025",
     "fee_type": "Transport",
     "amount": 5000.00,
     "academic_year": 1,
     "term": 1,
     "is_mandatory": false
   }

3. Assign optional fee to student:
   POST /api/financial/student-fee-assignments/
   {
     "student": 5,
     "fee_structure": 2,
     "term": 1,
     "amount_owed": 5000.00
   }

4. Record payment:
   POST /api/financial/receipts/
   {
     "student": 5,
     "amount": 30000.00,
     "payer": "John's Father",
     "paid_through": "Mobile Money",
     "reference_number": "MM123456",
     "term": 1
   }

5. Allocate payment to fees:
   POST /api/financial/receipts/1/allocate_to_fees/
   {
     "allocations": [
       {"fee_assignment_id": 10, "amount": 25000.00},
       {"fee_assignment_id": 11, "amount": 5000.00}
     ]
   }

6. Get student balance:
   GET /api/financial/student-balance/5/?term_id=1

7. Waive fee:
   POST /api/financial/student-fee-assignments/10/waive/
   {"reason": "Scholarship awarded"}

8. Adjust fee amount:
   POST /api/financial/student-fee-assignments/10/adjust_amount/
   {"new_amount": 45000.00, "reason": "10% discount"}
"""
