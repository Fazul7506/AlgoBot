"""Merge independent profile onboarding migrations.

The terms-acceptance and demographics migrations add separate fields to
UserProfile. This no-op merge records both branches as dependencies without
changing database schema or rewriting either migration.
"""
from django.db import migrations


class Migration(migrations.Migration):
    dependencies = [
        ("core", "0011_userprofile_terms_acceptance"),
        ("core", "0013_profile_onboarding_demographics"),
    ]

    operations = []
