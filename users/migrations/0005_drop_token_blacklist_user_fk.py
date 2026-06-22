"""
Drop the FK constraint from token_blacklist_outstandingtoken.user_id.

In a multi-tenant setup, school-admin users live in tenant schemas while
token_blacklist tables live in the public schema.  The FK from
token_blacklist_outstandingtoken → users_customuser therefore references
the wrong schema, causing a constraint-violation on every login attempt.

Dropping the constraint keeps the user_id column (still useful for
debugging / auditing) but removes the cross-schema referential-integrity
check that can never be satisfied for tenant users.
"""
from django.db import migrations


class Migration(migrations.Migration):

    dependencies = [
        ('users', '0004_alter_customuser_is_student'),
        ('token_blacklist', '0012_alter_outstandingtoken_user'),
    ]

    operations = [
        migrations.RunSQL(
            sql="""
                ALTER TABLE token_blacklist_outstandingtoken
                DROP CONSTRAINT IF EXISTS
                    token_blacklist_outs_user_id_83bc629a_fk_users_cus;
            """,
            reverse_sql=migrations.RunSQL.noop,
        ),
    ]
