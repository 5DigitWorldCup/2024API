# Generated by Django 4.2.6 on 2024-01-22 18:20

from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ('userauth', '0013_alter_tournamentplayer_discord_avatar_and_more'),
    ]

    operations = [
        migrations.AddIndex(
            model_name='tournamentplayerbadge',
            index=models.Index(fields=['user'], name='userauth_to_user_id_e2d512_idx'),
        ),
    ]
