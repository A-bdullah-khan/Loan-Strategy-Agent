# Hand-written: this app takes over the Bank/LoanPolicy models previously
# defined in the `core` app. It was originally written with empty
# database_operations under the assumption that the underlying tables
# (core_bank / core_loanpolicy) already existed from the old `core` app's own
# migrations — which is true on this project's existing dev/prod database,
# where this migration has long since been applied. But the `core` app and
# its migrations no longer exist anywhere in this repo, so replaying history
# on a brand-new database (as `manage.py test` does for the test database)
# could never actually create these tables, even though every later banks/
# migration assumes they're there. `database_operations` below now mirrors
# `state_operations` so a fresh database gets real tables too.
#
# This is safe for the existing dev/prod database: Django never re-runs a
# migration already recorded as applied (`manage.py showmigrations banks`
# confirms 0001_initial is applied there), so this change only takes effect
# the first time this migration runs against a database that doesn't have it
# yet — i.e. only on freshly created databases such as the test database.

import django.db.models.deletion
from django.db import migrations, models


class Migration(migrations.Migration):

    initial = True

    dependencies = [
    ]

    operations = [
        migrations.SeparateDatabaseAndState(
            database_operations=[
                migrations.CreateModel(
                    name='Bank',
                    fields=[
                        ('id', models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name='ID')),
                        ('name', models.CharField(max_length=255)),
                        ('is_islamic', models.BooleanField(default=False)),
                        ('website_url', models.URLField()),
                    ],
                    options={
                        'db_table': 'core_bank',
                    },
                ),
                migrations.CreateModel(
                    name='LoanPolicy',
                    fields=[
                        ('id', models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name='ID')),
                        ('loan_type', models.CharField(choices=[('Personal', 'Personal'), ('Vehicle', 'Vehicle'), ('Home', 'Home')], max_length=20)),
                        ('min_income', models.DecimalField(decimal_places=2, max_digits=12)),
                        ('min_credit_score', models.IntegerField()),
                        ('min_age', models.IntegerField(default=21)),
                        ('max_age', models.IntegerField(default=60)),
                        ('max_loan_amount', models.DecimalField(decimal_places=2, max_digits=14)),
                        ('interest_or_profit_rate', models.DecimalField(decimal_places=2, max_digits=5)),
                        ('min_downpayment_percentage', models.DecimalField(decimal_places=2, default=0.0, max_digits=5)),
                        ('max_tenure_years', models.IntegerField()),
                        ('policy_details', models.JSONField(blank=True, help_text='Granular policy terms: full terms & conditions, required documents, and interest/profit calculation formulas.', null=True)),
                        ('raw_scraped_data', models.JSONField(blank=True, null=True)),
                        ('updated_at', models.DateTimeField(auto_now=True)),
                        ('bank', models.ForeignKey(on_delete=django.db.models.deletion.CASCADE, related_name='loan_policies', to='banks.bank')),
                    ],
                    options={
                        'db_table': 'core_loanpolicy',
                    },
                ),
            ],
            state_operations=[
                migrations.CreateModel(
                    name='Bank',
                    fields=[
                        ('id', models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name='ID')),
                        ('name', models.CharField(max_length=255)),
                        ('is_islamic', models.BooleanField(default=False)),
                        ('website_url', models.URLField()),
                    ],
                    options={
                        'db_table': 'core_bank',
                    },
                ),
                migrations.CreateModel(
                    name='LoanPolicy',
                    fields=[
                        ('id', models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name='ID')),
                        ('loan_type', models.CharField(choices=[('Personal', 'Personal'), ('Vehicle', 'Vehicle'), ('Home', 'Home')], max_length=20)),
                        ('min_income', models.DecimalField(decimal_places=2, max_digits=12)),
                        ('min_credit_score', models.IntegerField()),
                        ('min_age', models.IntegerField(default=21)),
                        ('max_age', models.IntegerField(default=60)),
                        ('max_loan_amount', models.DecimalField(decimal_places=2, max_digits=14)),
                        ('interest_or_profit_rate', models.DecimalField(decimal_places=2, max_digits=5)),
                        ('min_downpayment_percentage', models.DecimalField(decimal_places=2, default=0.0, max_digits=5)),
                        ('max_tenure_years', models.IntegerField()),
                        ('policy_details', models.JSONField(blank=True, help_text='Granular policy terms: full terms & conditions, required documents, and interest/profit calculation formulas.', null=True)),
                        ('raw_scraped_data', models.JSONField(blank=True, null=True)),
                        ('updated_at', models.DateTimeField(auto_now=True)),
                        ('bank', models.ForeignKey(on_delete=django.db.models.deletion.CASCADE, related_name='loan_policies', to='banks.bank')),
                    ],
                    options={
                        'db_table': 'core_loanpolicy',
                    },
                ),
            ],
        ),
    ]
