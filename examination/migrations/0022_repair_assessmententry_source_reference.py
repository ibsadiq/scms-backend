from django.db import migrations


def repair_source_reference(apps, schema_editor):
    table_name = "examination_assessmententry"
    connection = schema_editor.connection

    with connection.cursor() as cursor:
        tables = connection.introspection.table_names(cursor)
        if table_name not in tables:
            return

        columns = {
            column.name
            for column in connection.introspection.get_table_description(
                cursor, table_name
            )
        }
        if "source_reference" not in columns:
            cursor.execute(
                'ALTER TABLE "examination_assessmententry" '
                'ADD COLUMN "source_reference" varchar(100) NULL'
            )

        cursor.execute(
            "CREATE UNIQUE INDEX IF NOT EXISTS "
            '"examination_assessmententry_source_reference_repair_uniq" '
            'ON "examination_assessmententry" ("source_reference")'
        )


class Migration(migrations.Migration):
    dependencies = [
        ("examination", "0021_stage10_source_reference_unique"),
    ]

    operations = [
        migrations.RunPython(repair_source_reference, migrations.RunPython.noop),
    ]
