from django.db import migrations, models


class Migration(migrations.Migration):
    dependencies = [
        ("finance", "0005_financeauditlog"),
    ]

    operations = [
        migrations.AddConstraint(
            model_name="studentfeeassignment",
            constraint=models.CheckConstraint(
                condition=models.Q(("amount_owed__gte", 0)),
                name="finance_assignment_owed_nonnegative",
            ),
        ),
        migrations.AddConstraint(
            model_name="studentfeeassignment",
            constraint=models.CheckConstraint(
                condition=models.Q(("amount_paid__gte", 0)),
                name="finance_assignment_paid_nonnegative",
            ),
        ),
        migrations.AddConstraint(
            model_name="studentfeeassignment",
            constraint=models.CheckConstraint(
                condition=models.Q(("amount_paid__lte", models.F("amount_owed"))),
                name="finance_assignment_paid_lte_owed",
            ),
        ),
        migrations.AddConstraint(
            model_name="receipt",
            constraint=models.CheckConstraint(
                condition=models.Q(("amount__gt", 0)),
                name="finance_receipt_amount_positive",
            ),
        ),
        migrations.AddConstraint(
            model_name="feepaymentallocation",
            constraint=models.CheckConstraint(
                condition=models.Q(("amount__gt", 0)),
                name="finance_allocation_amount_positive",
            ),
        ),
        migrations.AddConstraint(
            model_name="payment",
            constraint=models.CheckConstraint(
                condition=models.Q(("amount__gt", 0)),
                name="finance_payment_amount_positive",
            ),
        ),
    ]
