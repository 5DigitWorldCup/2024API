from django.conf import settings
from django.db import models
from django.db.models import CheckConstraint, Q

import teammgmt.models


class TournamentPlayer(models.Model):
    user = models.OneToOneField(settings.AUTH_USER_MODEL, on_delete=models.CASCADE, primary_key=True)

    discord_user_id = models.CharField(max_length=20, blank=True)
    discord_username = models.CharField(max_length=64)
    discord_global_name = models.CharField(max_length=64, null=True, blank=True)
    discord_avatar = models.CharField(max_length=64, null=True, blank=True)

    osu_user_id = models.BigIntegerField(blank=True)
    osu_username = models.CharField(max_length=64)
    osu_flag = models.CharField(max_length=4)

    osu_rank_std = models.IntegerField(null=True)
    osu_rank_std_bws = models.IntegerField(null=True)  # global_rank ^ (0.9937 ^ (badge_count ^ 2))
    osu_stats_updated = models.DateTimeField()

    is_organizer = models.BooleanField(default=False)
    is_captain = models.BooleanField(default=False)
    is_staff = models.BooleanField(null=False, blank=False, default=False)
    team = models.ForeignKey(teammgmt.models.TournamentTeam,
                             related_name='players',
                             on_delete=models.PROTECT,
                             default=teammgmt.models.TournamentTeam.get_default_pk)
    in_roster = models.BooleanField(default=False)
    in_backup_roster = models.BooleanField(default=False)

    def __str__(self):
        return (f"{self.osu_username} ({self.osu_flag}|"
                f"{self.discord_global_name if self.discord_global_name is not None else self.discord_username})")

    class Meta:
        ordering = ['pk']
        indexes = [
            models.Index(fields=['discord_user_id', 'osu_user_id']),
            models.Index(fields=['osu_user_id']),
            models.Index(fields=['team']),
            models.Index(fields=['is_staff'])
        ]
        constraints = [
            CheckConstraint(name="not_both_roster_and_backup",
                            check=~Q(in_roster=True, in_backup_roster=True)),
            CheckConstraint(name="captain_only_if_also_in_roster",
                            check=~Q(is_captain=True, in_roster=False))
        ]


class TournamentPlayerBadge(models.Model):
    user = models.ForeignKey(TournamentPlayer, on_delete=models.CASCADE)
    description = models.TextField()
    award_date = models.DateTimeField()
    url = models.TextField(blank=True)
    image_url = models.TextField()
    image_url_2x = models.TextField()

    class Meta:
        indexes = (
            models.Index(fields=('user',)),
        )


class DisqualifiedUser(models.Model):
    osu_user_id = models.IntegerField(primary_key=True, unique=True)

    def __str__(self):
        return f"https://osu.ppy.sh/users/{self.osu_user_id}"
