from django.db import models, transaction
from django.core.exceptions import ValidationError
from django.utils import timezone
from django.db.models import Sum
from decimal import Decimal
from administration.models import Term, AcademicYear
from academic.models import GradeLevel, ClassLevel
from users.models import Accountant, CustomUser as User
from academic.models import Teacher, Student


class PaymentStatus(models.TextChoices):
    PENDING = "Pending", "Pending"
    COMPLETED = "Completed", "Completed"
    CANCELLED = "Cancelled", "Cancelled"


class PaymentThrough(models.TextChoices):
    CASH = "Cash", "Cash"
    BANK_TRANSFER = "Bank Transfer", "Bank Transfer"
    CHEQUE = "Cheque", "Cheque"
    MOBILE_MONEY = "Mobile Money", "Mobile Money"
    CARD = "Card", "Card"


class FeeType(models.TextChoices):
    TUITION = "Tuition", "Tuition"
    TRANSPORT = "Transport", "Transport"
    MEALS = "Meals", "Meals"
    BOOKS = "Books", "Books"
    UNIFORM = "Uniform", "Uniform"
    OTHER = "Other", "Other"


# ============================================================================
# FEE STRUCTURE MODELS
# ============================================================================

class FeeStructure(models.Model):
    """
    Defines fee templates/structures for the school.
    These are the fee "types" that can be assigned to students.
    """
    name = models.CharField(max_length=255)
    fee_type = models.CharField(
        max_length=50,
        choices=FeeType.choices,
        default=FeeType.TUITION
    )
    amount = models.DecimalField(
        max_digits=10,
        decimal_places=2,
        help_text="Standard amount for this fee"
    )

    # Scope - defines who this fee applies to
    academic_year = models.ForeignKey(
        AcademicYear,
        on_delete=models.CASCADE,
        related_name='fee_structures'
    )
    term = models.ForeignKey(
        Term,
        on_delete=models.CASCADE,
        null=True,
        blank=True,
        related_name='fee_structures',
        help_text="Leave blank to apply to all terms in the academic year"
    )
    grade_levels = models.ManyToManyField(
        GradeLevel,
        blank=True,
        related_name='fee_structures',
        help_text="Leave blank to apply to all grade levels"
    )
    class_levels = models.ManyToManyField(
        ClassLevel,
        blank=True,
        related_name='fee_structures',
        help_text="Leave blank to apply to all class levels"
    )

    # Fee properties
    is_mandatory = models.BooleanField(
        default=True,
        help_text="Mandatory fees are auto-assigned to all applicable students"
    )
    due_date = models.DateField(
        null=True,
        blank=True,
        help_text="Due date for this fee"
    )

    # Metadata
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)
    created_by = models.ForeignKey(
        User,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name='created_fee_structures'
    )

    class Meta:
        ordering = ['-academic_year', 'term', 'fee_type']
        indexes = [
            models.Index(fields=['academic_year', 'term']),
            models.Index(fields=['is_mandatory']),
        ]

    def __str__(self):
        scope = []

        # Get grade levels (need to check if called after initialization)
        try:
            grade_count = self.grade_levels.count()
            if grade_count > 0:
                if grade_count <= 2:
                    scope.append(", ".join(g.name for g in self.grade_levels.all()))
                else:
                    scope.append(f"{grade_count} grades")
        except:
            pass

        # Get class levels
        try:
            class_count = self.class_levels.count()
            if class_count > 0:
                if class_count <= 2:
                    scope.append(", ".join(c.name for c in self.class_levels.all()))
                else:
                    scope.append(f"{class_count} classes")
        except:
            pass

        if self.term:
            scope.append(self.term.name)
        else:
            scope.append("All Terms")

        scope_str = " - ".join(scope) if scope else "All Students"
        return f"{self.name} ({scope_str}) - ₦{self.amount:,.2f}"

    def clean(self):
        if self.amount <= 0:
            raise ValidationError("Amount must be a positive value.")

        # Validate due date is within academic year
        if self.due_date:
            if self.academic_year.start_date and self.due_date < self.academic_year.start_date:
                raise ValidationError("Due date cannot be before academic year start date.")
            if self.academic_year.end_date and self.due_date > self.academic_year.end_date:
                raise ValidationError("Due date cannot be after academic year end date.")

        # Validate due date is within term if term is specified
        if self.term and self.due_date:
            if self.due_date < self.term.start_date or self.due_date > self.term.end_date:
                raise ValidationError("Due date must be within the selected term dates.")

    def applies_to_student(self, student, term=None):
        """Check if this fee structure applies to a given student."""
        # Check grade levels
        grade_levels_list = list(self.grade_levels.all())
        if grade_levels_list and student.class_level:
            if student.class_level.grade_level not in grade_levels_list:
                return False

        # Check class levels
        class_levels_list = list(self.class_levels.all())
        if class_levels_list and student.class_level:
            if student.class_level not in class_levels_list:
                return False

        # Check term
        if self.term and term and self.term != term:
            return False

        return True

    def auto_assign_to_students(self, term=None):
        """
        Auto-assign this fee to all applicable students.
        Only for mandatory fees.
        """
        if not self.is_mandatory:
            return 0

        assigned_count = 0
        students = Student.objects.filter(status='Active')

        # Filter by grade levels if specified
        grade_levels_list = list(self.grade_levels.all())
        if grade_levels_list:
            students = students.filter(classroom__class_level__grade_level__in=grade_levels_list)

        # Filter by class levels if specified
        class_levels_list = list(self.class_levels.all())
        if class_levels_list:
            students = students.filter(classroom__class_level__in=class_levels_list)

        # Determine which term(s) to assign
        terms_to_assign = []
        if self.term:
            terms_to_assign = [self.term]
        elif term:
            terms_to_assign = [term]
        else:
            # Assign to all terms in the academic year
            terms_to_assign = Term.objects.filter(academic_year=self.academic_year)

        for student in students:
            for assignment_term in terms_to_assign:
                if self.applies_to_student(student, assignment_term):
                    _, created = StudentFeeAssignment.objects.get_or_create(
                        student=student,
                        fee_structure=self,
                        term=assignment_term,
                        defaults={
                            'amount_owed': self.amount,
                            'amount_paid': Decimal('0.00'),
                        }
                    )
                    if created:
                        assigned_count += 1

        return assigned_count


class StudentFeeAssignment(models.Model):
    """
    Links students to specific fees they owe.
    Tracks payment progress for each fee.
    This replaces the old DebtRecord model with better granularity.
    """
    student = models.ForeignKey(
        Student,
        on_delete=models.CASCADE,
        related_name='fee_assignments'
    )
    fee_structure = models.ForeignKey(
        FeeStructure,
        on_delete=models.CASCADE,
        related_name='student_assignments'
    )
    term = models.ForeignKey(
        Term,
        on_delete=models.CASCADE,
        related_name='fee_assignments'
    )

    # Financial tracking
    amount_owed = models.DecimalField(
        max_digits=10,
        decimal_places=2,
        help_text="Can be different from fee_structure.amount for discounts/adjustments"
    )
    amount_paid = models.DecimalField(
        max_digits=10,
        decimal_places=2,
        default=Decimal('0.00')
    )

    # Status flags
    is_waived = models.BooleanField(
        default=False,
        help_text="Waived fees (scholarships, etc.) don't need to be paid"
    )
    waived_reason = models.TextField(blank=True, null=True)
    waived_by = models.ForeignKey(
        User,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name='waived_fees'
    )
    waived_date = models.DateTimeField(null=True, blank=True)

    # Metadata
    assigned_date = models.DateTimeField(auto_now_add=True)
    last_payment_date = models.DateTimeField(null=True, blank=True)

    class Meta:
        unique_together = ('student', 'fee_structure', 'term')
        ordering = ['-term', 'fee_structure__fee_type', 'student']
        indexes = [
            models.Index(fields=['student', 'term']),
            models.Index(fields=['is_waived']),
        ]

    def __str__(self):
        return f"{self.student.full_name} - {self.fee_structure.name} ({self.term.name})"

    @property
    def balance(self):
        """Remaining amount to be paid."""
        if self.is_waived:
            return Decimal('0.00')
        return max(Decimal('0.00'), self.amount_owed - self.amount_paid)

    @property
    def is_fully_paid(self):
        """Check if the fee is fully paid."""
        return self.balance == Decimal('0.00')

    @property
    def payment_status(self):
        """Return payment status: Paid, Partial, Unpaid, Waived."""
        if self.is_waived:
            return "Waived"
        if self.is_fully_paid:
            return "Paid"
        if self.amount_paid > 0:
            return "Partial"
        return "Unpaid"

    def clean(self):
        if self.amount_owed < 0:
            raise ValidationError("Amount owed cannot be negative.")
        if self.amount_paid < 0:
            raise ValidationError("Amount paid cannot be negative.")
        if self.amount_paid > self.amount_owed:
            raise ValidationError("Amount paid cannot exceed amount owed.")

    def apply_payment(self, amount):
        """
        Apply a payment to this fee assignment.
        Returns the amount actually applied.
        """
        amount = Decimal(str(amount))

        if amount <= 0:
            raise ValueError("Payment amount must be positive.")

        if self.is_waived:
            raise ValueError("Cannot apply payment to waived fee.")

        # Calculate how much can be applied
        applicable_amount = min(amount, self.balance)

        if applicable_amount > 0:
            self.amount_paid += applicable_amount
            self.last_payment_date = timezone.now()
            self.save()

        return applicable_amount

    def waive_fee(self, reason, waived_by):
        """Waive this fee (scholarship, discount, etc.)."""
        self.is_waived = True
        self.waived_reason = reason
        self.waived_by = waived_by
        self.waived_date = timezone.now()
        self.save()

    def adjust_amount(self, new_amount, reason=None):
        """Adjust the amount owed (for discounts, penalties, etc.)."""
        new_amount = Decimal(str(new_amount))

        if new_amount < 0:
            raise ValueError("New amount cannot be negative.")

        if new_amount < self.amount_paid:
            raise ValueError("New amount cannot be less than amount already paid.")

        old_amount = self.amount_owed
        self.amount_owed = new_amount
        self.save()

        # Log the adjustment
        FeeAdjustment.objects.create(
            fee_assignment=self,
            old_amount=old_amount,
            new_amount=new_amount,
            reason=reason or "Manual adjustment"
        )


class FeeAdjustment(models.Model):
    """Track all fee adjustments for audit purposes."""
    fee_assignment = models.ForeignKey(
        StudentFeeAssignment,
        on_delete=models.CASCADE,
        related_name='adjustments'
    )
    old_amount = models.DecimalField(max_digits=10, decimal_places=2)
    new_amount = models.DecimalField(max_digits=10, decimal_places=2)
    reason = models.TextField()
    adjusted_by = models.ForeignKey(
        User,
        on_delete=models.SET_NULL,
        null=True,
        blank=True
    )
    adjusted_date = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ['-adjusted_date']

    def __str__(self):
        return f"{self.fee_assignment} adjusted from ₦{self.old_amount} to ₦{self.new_amount}"


# ============================================================================
# RECEIPT AND PAYMENT MODELS
# ============================================================================

class Receipt(models.Model):
    """
    Records incoming payments from students/parents.
    Updated to support fee assignment tracking.
    """
    receipt_number = models.IntegerField(unique=True, blank=True, null=True)
    date = models.DateField(auto_now_add=True)
    payer = models.CharField(max_length=255, default="Unknown")
    student = models.ForeignKey(
        Student,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name='receipts'
    )
    amount = models.DecimalField(max_digits=10, decimal_places=2)
    paid_through = models.CharField(
        max_length=20,
        choices=PaymentThrough.choices,
        default=PaymentThrough.CASH
    )
    term = models.ForeignKey(
        Term,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name='receipts'
    )
    payment_date = models.DateField(default=timezone.now)
    reference_number = models.CharField(
        max_length=100,
        blank=True,
        null=True,
        help_text="External reference number (bank ref, mobile money ref, etc.)"
    )
    status = models.CharField(
        max_length=20,
        choices=PaymentStatus.choices,
        default=PaymentStatus.COMPLETED
    )
    received_by = models.ForeignKey(
        Accountant,
        on_delete=models.SET_NULL,
        null=True,
        related_name='received_receipts'
    )
    remarks = models.TextField(blank=True, null=True)

    class Meta:
        ordering = ['-date', '-receipt_number']
        indexes = [
            models.Index(fields=['student', 'term']),
            models.Index(fields=['receipt_number']),
            models.Index(fields=['date']),
        ]

    def __str__(self):
        return f"Receipt #{self.receipt_number} - {self.payer} - ₦{self.amount:,.2f}"

    def clean(self):
        if self.amount <= 0:
            raise ValidationError("Amount must be a positive value.")

    def save(self, *args, **kwargs):
        # Auto-generate receipt number
        if not self.receipt_number:
            with transaction.atomic():
                last_receipt = (
                    Receipt.objects.select_for_update()
                    .order_by("-receipt_number")
                    .first()
                )
                self.receipt_number = (
                    (last_receipt.receipt_number + 1) if last_receipt else 1
                )
        super().save(*args, **kwargs)

    @property
    def allocated_amount(self):
        """Amount allocated to specific fee assignments."""
        return self.fee_allocations.aggregate(
            total=Sum('amount')
        )['total'] or Decimal('0.00')

    @property
    def unallocated_amount(self):
        """Amount not yet allocated to any fee."""
        return self.amount - self.allocated_amount


class FeePaymentAllocation(models.Model):
    """
    Links receipts to specific fee assignments.
    Allows one receipt to pay multiple fees, or multiple receipts to pay one fee.
    This replaces the old PaymentRecord model.
    """
    receipt = models.ForeignKey(
        Receipt,
        on_delete=models.CASCADE,
        related_name='fee_allocations'
    )
    fee_assignment = models.ForeignKey(
        StudentFeeAssignment,
        on_delete=models.CASCADE,
        related_name='payment_allocations'
    )
    amount = models.DecimalField(
        max_digits=10,
        decimal_places=2,
        help_text="Amount of this receipt allocated to this fee"
    )
    allocated_date = models.DateTimeField(auto_now_add=True)
    allocated_by = models.ForeignKey(
        User,
        on_delete=models.SET_NULL,
        null=True,
        blank=True
    )

    class Meta:
        ordering = ['-allocated_date']
        indexes = [
            models.Index(fields=['receipt', 'fee_assignment']),
        ]

    def __str__(self):
        return f"Receipt #{self.receipt.receipt_number} → {self.fee_assignment} (₦{self.amount:,.2f})"

    def clean(self):
        if self.amount <= 0:
            raise ValidationError("Allocation amount must be positive.")

        if self.amount > self.fee_assignment.balance:
            raise ValidationError(
                f"Cannot allocate ₦{self.amount} - fee balance is only ₦{self.fee_assignment.balance}"
            )

        # Check receipt doesn't over-allocate
        current_allocated = self.receipt.fee_allocations.exclude(
            pk=self.pk
        ).aggregate(total=Sum('amount'))['total'] or Decimal('0.00')

        if current_allocated + self.amount > self.receipt.amount:
            raise ValidationError(
                f"Cannot allocate ₦{self.amount} - only ₦{self.receipt.amount - current_allocated} remaining"
            )

    def save(self, *args, **kwargs):
        self.full_clean()
        super().save(*args, **kwargs)

        # Apply payment to fee assignment
        self.fee_assignment.apply_payment(self.amount)


# ============================================================================
# OUTGOING PAYMENT MODEL (for school expenses)
# ============================================================================

class PaymentCategory(models.Model):
    """Categories for outgoing payments/expenses."""
    name = models.CharField(max_length=255)
    abbr = models.CharField(max_length=50, blank=True, null=True)
    description = models.TextField(blank=True, null=True)

    class Meta:
        verbose_name_plural = "Payment Categories"

    def __str__(self):
        return self.name


class Payment(models.Model):
    """Outgoing payments (salaries, utilities, supplies, etc.)."""
    payment_number = models.IntegerField(
        unique=True,
        blank=True,
        null=True,
        db_index=True
    )
    date = models.DateField(auto_now_add=True)
    paid_to = models.CharField(max_length=255)
    user = models.ForeignKey(
        User,
        blank=True,
        null=True,
        on_delete=models.SET_NULL,
        related_name="payments",
        help_text="If payment is to a system user (teacher, accountant, etc.)"
    )
    category = models.ForeignKey(
        PaymentCategory,
        on_delete=models.SET_NULL,
        null=True,
        related_name='payments'
    )
    paid_through = models.CharField(
        max_length=20,
        choices=PaymentThrough.choices,
        default=PaymentThrough.CASH
    )
    amount = models.DecimalField(max_digits=10, decimal_places=2)
    reference_number = models.CharField(
        max_length=100,
        blank=True,
        null=True,
        help_text="Cheque number, transfer reference, etc."
    )
    description = models.TextField(blank=True, null=True)
    status = models.CharField(
        max_length=20,
        choices=PaymentStatus.choices,
        default=PaymentStatus.COMPLETED
    )
    paid_by = models.ForeignKey(
        Accountant,
        on_delete=models.SET_NULL,
        null=True,
        related_name='processed_payments'
    )

    class Meta:
        ordering = ['-date', '-payment_number']
        indexes = [
            models.Index(fields=['date']),
            models.Index(fields=['category']),
        ]

    def __str__(self):
        return f"Payment #{self.payment_number} - {self.paid_to} - ₦{self.amount:,.2f}"

    def clean(self):
        if self.amount <= 0:
            raise ValidationError("Amount must be a positive value.")

    def save(self, *args, **kwargs):
        if not self.payment_number:
            last_payment = Payment.objects.order_by("-payment_number").first()
            self.payment_number = (
                (last_payment.payment_number + 1) if last_payment else 1
            )

        super().save(*args, **kwargs)
