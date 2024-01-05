from django.conf import settings
from django.contrib.auth.models import AnonymousUser
from django.db import transaction, IntegrityError
from rest_framework import serializers, viewsets, status
from rest_framework.decorators import action
from rest_framework.response import Response

from discord.views import TournamentPlayerSerializer, PreSharedKeyAuthentication, TeamOrganizer, ReadOnly
from teammgmt.models import TournamentTeam
from userauth.models import TournamentPlayer


class TournamentTeamSerializer(serializers.HyperlinkedModelSerializer):
    class Meta:
        model = TournamentTeam
        fields = ['url', 'osu_flag']


class TournamentTeamMembersSerializer(serializers.HyperlinkedModelSerializer):
    candidates = TournamentPlayerSerializer(many=True, read_only=True, source="players")
    roster = serializers.SerializerMethodField()
    backups = serializers.SerializerMethodField()

    class Meta:
        model = TournamentTeam
        fields = ['url', 'osu_flag', 'roster', 'backups', 'candidates']

    def get_roster(self, team):
        players = TournamentPlayer.objects.filter(team=team, in_roster=True)
        serializer = TournamentPlayerSerializer(instance=players, context=self.context, many=True)
        return serializer.data

    def get_backups(self, team):
        players = TournamentPlayer.objects.filter(team=team, in_backup_roster=True)
        serializer = TournamentPlayerSerializer(instance=players, context=self.context, many=True)
        return serializer.data


class TournamentTeamViewSet(viewsets.ModelViewSet):
    serializer_class = TournamentTeamSerializer
    queryset = TournamentTeam.objects.all()
    http_method_names = ["get", "patch"]
    permission_classes = [ReadOnly]

    @action(methods=['get', 'PATCH'], detail=True, permission_classes=[PreSharedKeyAuthentication | TeamOrganizer])
    def members(self, request, **kwargs):
        """
        only organizer of team and admins can see team registrants and roster
        :param request:
        :param kwargs:
        :return:
        """
        team = self.get_object()
        if request.method == "PATCH":
            if not ((required_fields := {'players', 'backups'}) <= (keys_provided := request.data.keys())):
                return Response({"error": f"required field(s) "
                                          f"missing: {(keys_provided & required_fields) ^ required_fields}"},
                                status=status.HTTP_400_BAD_REQUEST)
            players = request.data['players']
            backups = request.data['backups']

            # todo: enforce registration time window cutoff

            # check roster size
            if not all([len(players) >= settings.TEAM_ROSTER_SIZE_MIN,
                        len(players) <= settings.TEAM_ROSTER_SIZE_MAX,
                        len(backups) <= settings.TEAM_ROSTER_BACKUP_SIZE_MAX]):
                return Response({"error": f"roster and backup player count out of bounds; "
                                          f"minimum roster size: {settings.TEAM_ROSTER_SIZE_MIN}"
                                          f"maximum roster size: {settings.TEAM_ROSTER_SIZE_MAX}"
                                          f"maximum backup players: {settings.TEAM_ROSTER_BACKUP_SIZE_MAX}"},
                                status=status.HTTP_400_BAD_REQUEST)

            try:
                req_players_qs = TournamentPlayer.objects.filter(pk__in=players)
            except TypeError:
                return Response({'error': 'players: expected array of player IDs'},
                                status=status.HTTP_400_BAD_REQUEST)
            original_players_qs = team.players.filter(in_roster=True)
            to_remove_from_roster = original_players_qs.exclude(pk__in=req_players_qs)

            try:
                req_backups_qs = TournamentPlayer.objects.filter(pk__in=backups)
            except TypeError:
                return Response({'error': 'backups: expected array of backup player IDs'},
                                status=status.HTTP_400_BAD_REQUEST)
            original_backups_qs = team.players.filter(in_backup_roster=True)
            to_remove_from_backup = original_backups_qs.exclude(pk__in=req_backups_qs)

            try:
                with transaction.atomic():
                    to_remove_from_roster.update(in_roster=False)
                    to_remove_from_backup.update(in_backup_roster=False)
                    req_players_qs.update(in_roster=True)
                    req_backups_qs.update(in_backup_roster=True)
            except IntegrityError as e:
                if str(e) == 'CHECK constraint failed: not_both_roster_and_backup':
                    return Response({"error": "player cannot be both in roster and "
                                              "backup roster at the same time"},
                                    status=status.HTTP_400_BAD_REQUEST)
                return Response({"error": f"got unexpected exception: {repr(e)}"},
                                status=status.HTTP_400_BAD_REQUEST)
        serializer = TournamentTeamMembersSerializer(team, context={'request': request}, partial=True)
        return Response(serializer.data)
