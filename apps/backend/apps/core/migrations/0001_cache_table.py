"""Create the PostgreSQL table behind the shared DatabaseCache (throttles, lockout).

Django creates cache tables with a management command, not a model; running it from a
migration keeps `migrate` the single deployment step. The command is idempotent.
"""

from django.core.management import call_command
from django.db import migrations


def create_cache_table(apps, schema_editor):
    call_command("createcachetable", database=schema_editor.connection.alias, verbosity=0)


class Migration(migrations.Migration):
    initial = True
    dependencies = []
    operations = [migrations.RunPython(create_cache_table, migrations.RunPython.noop)]
