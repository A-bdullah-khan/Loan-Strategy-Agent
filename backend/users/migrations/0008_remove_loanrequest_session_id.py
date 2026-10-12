from django.db import migrations


class Migration(migrations.Migration):

    dependencies = [
        ('users', '0007_backfill_chat_session'),
    ]

    operations = [
        migrations.RemoveField(
            model_name='loanrequest',
            name='session_id',
        ),
    ]
