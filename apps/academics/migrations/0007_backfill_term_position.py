from django.db import migrations


def backfill_positions(apps, schema_editor):
    Term = apps.get_model('academics', 'Term')
    for term in Term.objects.all():
        name = (term.name or '').upper()
        if name == 'FIRST':
            term.position = 1
        elif name == 'SECOND':
            term.position = 2
        elif name == 'THIRD':
            term.position = 3
        else:
            # leave as is (None) if unknown; admin can set manually
            continue
        term.save(update_fields=['position'])


def noop(apps, schema_editor):
    pass


class Migration(migrations.Migration):

    dependencies = [
        ('academics', '0006_term_position_alter_term_name'),
    ]

    operations = [
        migrations.RunPython(backfill_positions, reverse_code=noop),
    ]
