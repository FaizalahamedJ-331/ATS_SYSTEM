from django.db import migrations


def backfill_profiles(apps, schema_editor):
    """Give every existing user a profile. Accounts that predate email
    verification are trusted, so they are marked verified."""
    User = apps.get_model("auth", "User")
    UserProfile = apps.get_model("core", "UserProfile")
    for user in User.objects.all():
        UserProfile.objects.get_or_create(
            user_id=user.pk,
            defaults={"email_verified": True},
        )


class Migration(migrations.Migration):

    dependencies = [
        ("core", "0001_initial"),
    ]

    operations = [
        migrations.RunPython(backfill_profiles, migrations.RunPython.noop),
    ]
