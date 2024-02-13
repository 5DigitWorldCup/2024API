import datetime

from django.conf import settings
from django.contrib.auth.models import AnonymousUser, User
from django.core.cache import cache
from django.http import Http404
from django.utils.translation import gettext_lazy as _
from rest_framework import exceptions, permissions, serializers, status, viewsets
from rest_framework.authentication import TokenAuthentication
from rest_framework.decorators import action
from rest_framework.exceptions import ValidationError
from rest_framework.generics import get_object_or_404
from rest_framework.permissions import BasePermission
from rest_framework.response import Response

from discord import tasks
from userauth.authentication import filter_badges, IsSuperUser
from userauth.models import TournamentPlayer, TournamentPlayerBadge


class ReadOnly(BasePermission):
    def has_permission(self, request, view):
        return request.method in permissions.SAFE_METHODS


class PreSharedKeyAuthentication(TokenAuthentication, BasePermission):
    def has_permission(self, request, view):
        auth = self.authenticate(request)
        return auth is not None

    def authenticate_credentials(self, key):
        if settings.DISCORD_PSK != key:
            raise exceptions.AuthenticationFailed(_('Invalid token.'))

        return None, key


class TeamOrganizer(BasePermission):
    def has_object_permission(self, request, view, obj):
        if isinstance(request.user, AnonymousUser):
            return False
        try:
            tourney_player = request.user.tournamentplayer
        except TournamentPlayer.DoesNotExist:
            return False
        if not tourney_player.is_organizer or tourney_player.team != obj:
            return False

        return True


class TournamentPlayerSerializer(serializers.HyperlinkedModelSerializer):
    url = serializers.HyperlinkedIdentityField(view_name='tournamentplayer-detail')
    team_id = serializers.ReadOnlyField()
    user_id = serializers.PrimaryKeyRelatedField(queryset=User.objects.all())
    rank_standard = serializers.ReadOnlyField(source='osu_rank_std')
    rank_standard_bws = serializers.ReadOnlyField(source='osu_rank_std_bws')

    def to_representation(self, instance):
        representation = super(TournamentPlayerSerializer, self).to_representation(instance=instance)

        request = self._context['request']
        # kinda don't like that I have to put these conditions here, but it is what it is
        has_admin_perms = (IsSuperUser | PreSharedKeyAuthentication)().has_permission(request, None)
        has_team_perms = TeamOrganizer().has_object_permission(request, None, instance.team)
        if not has_admin_perms and not has_team_perms:
            del representation['is_captain']
            del representation['in_roster']
            del representation['in_backup_roster']

        return representation

    class Meta:
        model = TournamentPlayer
        fields = ['url',
                  'user_id',
                  'discord_user_id',
                  'discord_username',
                  'osu_user_id',
                  'osu_username',
                  'osu_flag',
                  'osu_stats_updated',
                  'rank_standard',
                  'rank_standard_bws',
                  'is_organizer',
                  'is_captain',
                  'in_roster',
                  'in_backup_roster',
                  'team_id',
                  'team']


class BadgeSerializer(serializers.HyperlinkedModelSerializer):
    # awarded_at = serializers.DateTimeField(source='award_date', format='%Y-%m-%dT%H:%M:%S%:z')  # %:z does not work
    awarded_at = serializers.SerializerMethodField()

    @staticmethod
    def get_awarded_at(badge):
        return datetime.datetime.isoformat(badge.award_date)

    class Meta:
        model = TournamentPlayerBadge
        fields = ['description',
                  'awarded_at',
                  'url',
                  'image_url',
                  'image_url_2x']


class TournamentPlayerSerializerWithBadges(TournamentPlayerSerializer):
    # tournamentplayerbadge_set is the default `related_name` for badge -> tourney player relationship
    badges = serializers.SerializerMethodField()

    # use this to add `filtered_badge_count`
    def to_representation(self, instance):
        representation = super().to_representation(instance)
        representation['filtered_badges_count'] = len(representation['badges'])
        return representation

    def get_badges(self, tournament_player: TournamentPlayer):
        serializer = BadgeSerializer(instance=TournamentPlayerBadge.objects.filter(user=tournament_player),
                                     many=True,
                                     read_only=True,
                                     source='tournamentplayerbadge_set')
        unfiltered_badges = serializer.data
        cutoff_date = self.context['request'].query_params.get('badge_cutoff_date', None)
        if cutoff_date is not None:
            try:
                cutoff_date = datetime.datetime.fromtimestamp(int(cutoff_date), tz=datetime.timezone.utc)
            except ValueError:
                raise ValueError("Invalid badge_cutoff_date provided, please provide a unix timestamp")
            return filter_badges(unfiltered_badges, [], cutoff_date=cutoff_date)
        return filter_badges(unfiltered_badges, [])  # use default cutoff

    class Meta(TournamentPlayerSerializer.Meta):
        fields = TournamentPlayerSerializer.Meta.fields + ['badges', ]


class TournamentPlayerViewSet(viewsets.ModelViewSet):
    queryset = TournamentPlayer.objects.filter(is_staff=False)
    queryset_include_staff = TournamentPlayer.objects.all()
    permission_classes = [PreSharedKeyAuthentication | ReadOnly]

    def handle_exception(self, exc):
        if isinstance(exc, Http404) and str(exc):
            return Response({'detail': str(exc)},
                            status=status.HTTP_404_NOT_FOUND)

        return super(TournamentPlayerViewSet, self).handle_exception(exc)

    def get_serializer_class(self):
        # noinspection PyTestUnpassedFixture
        if self.action == "retrieve":
            return TournamentPlayerSerializerWithBadges
        return TournamentPlayerSerializer

    @action(detail=False, permission_classes=[PreSharedKeyAuthentication | IsSuperUser], methods=["POST"])
    def update_all_users(self, request):
        queue_len = cache.get("osu_queue_length", 0)
        if queue_len > 0:
            return Response({"message": f"update tasks queue is not empty, {queue_len} tasks remaining"},
                            status=status.HTTP_429_TOO_MANY_REQUESTS)
        tasks.update_users.delay()
        return Response({"message": "Scheduled all users to be updated"})

    @action(detail=True, permission_classes=[PreSharedKeyAuthentication | IsSuperUser], methods=["POST"])
    def update_user(self, request, **kwargs):
        queue_len = cache.get("osu_queue_length", 0)

        tournament_player = self.get_object()
        tasks.update_user.delay(tournament_player.osu_user_id)
        return Response({"message": f"Scheduled {tournament_player.osu_username} ({tournament_player.osu_user_id}) "
                                    f"for update. {queue_len + 1} tasks in queue"})

    # todo: this should really go...
    def retrieve(self, request, *args, **kwargs):
        try:
            return super().retrieve(request, *args, **kwargs)
        except ValueError as e:
            return Response({"error": str(e)}, status=status.HTTP_400_BAD_REQUEST)

    def get_queryset(self, include_staff=False):
        if not include_staff:
            return super().get_queryset()

        # Ensure queryset is re-evaluated on each request.
        queryset = self.queryset_include_staff.all()
        return queryset

    def get_object(self, include_staff=False):
        queryset = self.filter_queryset(self.get_queryset(include_staff))
        # Lookup with pk
        lookup_type = self.request.query_params.get("key", None)
        lookup_url_kwarg = self.lookup_url_kwarg or self.lookup_field

        try:
            if lookup_type is None or lookup_type in ('id', 'pk'):
                filter_kwargs = {self.lookup_field: self.kwargs[lookup_url_kwarg]}
                obj = get_object_or_404(queryset, **filter_kwargs)

                # May raise a permission denied
                self.check_object_permissions(self.request, obj)

                return obj
        except Http404 as pk404:
            if lookup_url_kwarg not in self.kwargs:  # I'm no longer sure what purpose this really serves...
                raise pk404

        error_404 = Http404("No %s matches the given query." % queryset.model.__name__)

        if lookup_type in ("pk", "id") or lookup_type is None:
            raise error_404

        match [lookup_type]:
            case ["discord" | "osu"]:
                try:
                    obj = queryset.get(**{f"{lookup_type}_user_id": self.kwargs[lookup_url_kwarg]})
                except queryset.model.DoesNotExist:
                    raise error_404
            case _:
                raise ValueError(f"optional query parameter key not valid: '{lookup_type}'. "
                                 f'Must be one of {("pk", "id", "discord", "osu")}')

        self.check_object_permissions(self.request, obj)
        return obj

    def update(self, request, **kwargs):
        return self.partial_update(request, **kwargs)

    def set_staff_status(self, request, new_staff_status):
        if type(new_staff_status) is not bool:
            raise ValidationError(f"type of `is_staff` is {type(new_staff_status)}, expected bool")
        tournament_player = self.get_object(include_staff=True)
        tournament_player.is_staff = new_staff_status
        tournament_player.save()
        return Response({"msg": f"{tournament_player} is staff: {new_staff_status}"})

    def partial_update(self, request, pk=None, **kwargs):
        if (new_staff_status := request.data.get('is_staff', None)) is not None:
            return self.set_staff_status(request, new_staff_status)
        tournament_player = self.get_object()

        new_is_organizer = request.data.get("is_organizer")
        if new_is_organizer is None:
            return Response({"error": "required field `is_organizer` missing"}, status=status.HTTP_400_BAD_REQUEST)

        if type(new_is_organizer) is not bool:
            return Response({"error": "field `is_organizer` must be boolean"}, status=status.HTTP_400_BAD_REQUEST)

        if tournament_player.is_organizer != new_is_organizer:
            tournament_player.is_organizer = new_is_organizer
            tournament_player.save()
        serializer = self.get_serializer(tournament_player, many=False)
        return Response(serializer.data)
