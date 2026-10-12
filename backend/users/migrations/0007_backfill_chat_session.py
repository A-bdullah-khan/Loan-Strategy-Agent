"""Data migration: carries every existing `LoanRequest.session_id` value
over to a real `ChatSession` row + FK, before 0008 drops the old field.

One `ChatSession` per distinct session_id, owned by whichever user (if any)
that session's rows were created under — guest sessions (user_id null) stay
guest sessions.
"""
from django.db import migrations


def backfill_chat_sessions(apps, schema_editor):
    LoanRequest = apps.get_model('users', 'LoanRequest')
    ChatSession = apps.get_model('users', 'ChatSession')

    rows_with_session = LoanRequest.objects.exclude(session_id__isnull=True).exclude(session_id='')
    seen_session_ids = set()

    for loan_request in rows_with_session.iterator():
        session_id = loan_request.session_id
        if session_id not in seen_session_ids:
            ChatSession.objects.get_or_create(id=session_id, defaults={'user_id': loan_request.user_id})
            seen_session_ids.add(session_id)
        loan_request.chat_session_id = session_id
        loan_request.save(update_fields=['chat_session'])


def noop_reverse(apps, schema_editor):
    # Nothing to reverse into — 0006's AddField reversal already drops the
    # chat_session column, and the old session_id column/values are gone by
    # the time this migration is unapplied (0008 already ran forward).
    pass


class Migration(migrations.Migration):

    dependencies = [
        ('users', '0006_chatsession_and_fk'),
    ]

    operations = [
        migrations.RunPython(backfill_chat_sessions, noop_reverse),
    ]
