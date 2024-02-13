import datetime
from unittest.mock import Mock, patch

from django.contrib.auth.models import User
from django.core.cache import cache
from django.test import TestCase
from parameterized import parameterized
from rest_framework.test import APIRequestFactory

from discord import tasks
from discord.views import TeamOrganizer, TournamentPlayerViewSet
from teammgmt.models import TournamentTeam
from userauth.models import TournamentPlayer, TournamentPlayerBadge


class MockResponse:
    def __init__(self, json_data, status_code):
        self.json_data = json_data
        self.status_code = status_code

    def json(self):
        return self.json_data


class TestTournamentOrganizerPermissionClass(TestCase):
    def setUp(self):
        self.user = User.objects.create(is_superuser=False)
        self.team = TournamentTeam.objects.create(osu_flag="US")

    def test_team_organizer_ignores_user_with_no_tourney_player(self):
        request = APIRequestFactory().get(f'/doesnt_matter/')
        request.user = self.user
        has_permission = TeamOrganizer().has_object_permission(request, None, None)
        self.assertFalse(has_permission)

    def test_team_organizer_has_access_to_team(self):
        tourney_player = TournamentPlayer.objects.create(
            user=self.user,
            osu_user_id=1,
            osu_stats_updated=datetime.datetime.fromtimestamp(0, tz=datetime.timezone.utc),
            team=self.team,
            is_organizer=True
        )
        request = APIRequestFactory().get(f'/doesnt_matter/')
        request.user = self.user
        has_permission = TeamOrganizer().has_object_permission(request, None, self.team)
        self.assertTrue(has_permission)

    def test_team_organizer_does_not_have_access_to_other_team(self):
        other_team = TournamentTeam.objects.create(osu_flag="727")
        TournamentPlayer.objects.create(
            user=self.user,
            osu_user_id=1,
            osu_stats_updated=datetime.datetime.fromtimestamp(0, tz=datetime.timezone.utc),
            team=other_team,
            is_organizer=True
        )
        request = APIRequestFactory().get(f'/doesnt_matter/')
        request.user = self.user
        has_permission = TeamOrganizer().has_object_permission(request, None, self.team)
        self.assertFalse(has_permission)


class FetchOsuUserStatsTestCase(TestCase):
    def setUp(self):
        cache.clear()
        self.user = User.objects.create()
        self.tourney_user = TournamentPlayer.objects.create(user=self.user,
                                                            osu_user_id=1,
                                                            osu_stats_updated=datetime.datetime.fromtimestamp(
                                                                0,
                                                                tz=datetime.timezone.utc
                                                            ))

    @patch('discord.tasks.update_users.delay')
    def test_update_all_users_api(self, mocked_tasks_update_users):
        factory = APIRequestFactory()
        request = factory.post(f'/registrants/update_users')
        update_all_users_action = TournamentPlayerViewSet.as_view({'post': 'update_all_users'},
                                                                  permission_classes=[])
        res = update_all_users_action(request)

        self.assertEqual(200, res.status_code)
        self.assertEqual(1, mocked_tasks_update_users.call_count)

    @patch('discord.tasks.update_users.delay')
    def test_update_all_users_api_rate_limited(self, mocked_tasks_update_users):
        cache.set("osu_queue_length", 100, timeout=1)
        factory = APIRequestFactory()
        request = factory.post(f'/registrants/update_users')
        update_all_users_action = TournamentPlayerViewSet.as_view({'post': 'update_all_users'},
                                                                  permission_classes=[])
        res = update_all_users_action(request)

        self.assertEqual(429, res.status_code)
        self.assertEqual(0, mocked_tasks_update_users.call_count)

    @patch('discord.tasks.update_user.delay')
    def test_update_specific_user_api(self, mocked_tasks_update_user):
        factory = APIRequestFactory()
        request = factory.post(f'/registrants/{self.tourney_user}/update_users')
        update_all_users_action = TournamentPlayerViewSet.as_view({'post': 'update_user'},
                                                                  permission_classes=[],
                                                                  detail=True)
        res = update_all_users_action(request, pk=self.tourney_user.pk)

        self.assertEqual(200, res.status_code)
        self.assertEqual(1, mocked_tasks_update_user.call_count)
        mocked_tasks_update_user.assert_called_with(self.tourney_user.osu_user_id)

    def test_get_osu_token_invalid_credentials(self):
        response = MockResponse({}, 401)

        with patch('discord.tasks.requests.post', new=Mock(return_value=response)):
            token = tasks.get_osu_token()
            self.assertIsNone(token)

            # assert that we don't cache invalid credentials
            self.assertIsNone(cache.get("osu_token", None))

    def test_get_osu_token_use_cache(self):
        """
        If an existing token exists in cache, use cached token
        """
        cache.set("osu_token", {
            "token_type": "Bearer",
            "expires_in": 86400,
            "access_token": (token_value := "wQZbHHT8wGnVUn4ABJugD7iID8Gnhvg8jLoCb0ALyj9Mylva9TD")
        }, timeout=30)

        with patch('discord.tasks.requests.post') as p:
            token = tasks.get_osu_token()
            self.assertEqual(token_value, token)
            self.assertEqual(0, p.call_count)

    def test_get_osu_token_success(self):
        token_value = "wQZbHHT8wGnVUn4ABJugD7iID8Gnhvg8jLoCb0ALyj9Mylva9TD"
        response = MockResponse({
            "token_type": "Bearer",
            "expires_in": 86400,
            "access_token": token_value
        },
            200)

        with patch('discord.tasks.requests.post', new=Mock(return_value=response)):
            token = tasks.get_osu_token()
            self.assertEqual(token_value, token)
            self.assertEqual(dict, type(cache.get("osu_token")))
            self.assertEqual(token_value, cache.get("osu_token").get("access_token", None))  # ensure token is cached

    def test_user_not_in_db(self):
        """
        Test that we don't hit the osu! API if the registered user isn't in our own database
        """
        with patch('discord.tasks.requests.get') as p:
            tasks.update_user(self.tourney_user.osu_user_id + 727)
            self.assertEqual(0, p.call_count)

    @patch("discord.tasks.get_osu_token")
    def test_bad_token(self, mocked_get_osu_token):
        """
        Test that we don't hit the osu! API if we fail to fetch a token
        """
        mocked_get_osu_token.return_value = None
        with patch("discord.tasks.requests.get") as p:
            tasks.update_user(self.tourney_user.osu_user_id)
            self.assertEqual(0, p.call_count)

    @patch("discord.tasks.update_user.delay")
    def test_update_all(self, mocked_update_user):
        tasks.update_users()
        self.assertTrue(TournamentPlayer.objects.count() > 0)
        self.assertEqual(TournamentPlayer.objects.count(), mocked_update_user.call_count)

    @patch("discord.tasks.update_user.delay")
    def test_update_list(self, mocked_update_user):
        users_to_update = [1, 2, 3]
        tasks.update_users(users_to_update)
        self.assertEqual(len(users_to_update), mocked_update_user.call_count)

    @patch("discord.tasks.get_osu_token")
    def test_stats_update_no_badge(self, mocked_get_osu_token):
        mocked_get_osu_token.return_value = "TEST_VALID_TOKEN"

        global_rank = 1000
        response = MockResponse({
            "badges": [{'awarded_at': '2023-01-19T02:08:46+00:00',
                        'description': "Mapper's Choice Awards 2021: Top 3 in the user/beatmap "
                                       "category Hitsounding",
                        'image@2x_url': 'https://assets.ppy.sh/profile-badges/mca-2022/'
                                        'mca-standard-2021@2x.png?2023-01-20',
                        'image_url': 'https://assets.ppy.sh/profile-badges/mca-2022/'
                                     'mca-standard-2021.png?2023-01-20',
                        'url': 'https://mca.corsace.io/2021/results'}],
            "statistics": {"global_rank": global_rank},
            "username": self.tourney_user.osu_username
        },
            200)

        year_2000 = datetime.datetime(2000, 1, 1, tzinfo=datetime.timezone.utc)
        self.assertLess(self.tourney_user.osu_stats_updated, year_2000)
        with patch('discord.tasks.requests.get', new=Mock(return_value=response)) as p:
            tasks.update_user(self.tourney_user.osu_user_id)
            self.assertGreater(p.call_count, 0)
            self.tourney_user.refresh_from_db()
            self.assertGreater(self.tourney_user.osu_stats_updated, year_2000)
            self.assertEqual(global_rank, self.tourney_user.osu_rank_std)

    @patch("discord.tasks.get_osu_token")
    def test_stats_update_update_useranme(self, mocked_get_osu_token):
        """
        Test that a registrant's username gets updated along their stats during stats update
        :return:
        """
        mocked_get_osu_token.return_value = "TEST_VALID_TOKEN"

        global_rank = 1000
        response = MockResponse({
            "badges": [{'awarded_at': '2023-01-19T02:08:46+00:00',
                        'description': "Mapper's Choice Awards 2021: Top 3 in the user/beatmap "
                                       "category Hitsounding",
                        'image@2x_url': 'https://assets.ppy.sh/profile-badges/mca-2022/'
                                        'mca-standard-2021@2x.png?2023-01-20',
                        'image_url': 'https://assets.ppy.sh/profile-badges/mca-2022/'
                                     'mca-standard-2021.png?2023-01-20',
                        'url': 'https://mca.corsace.io/2021/results'}],
            "statistics": {"global_rank": global_rank},
            "username": (new_username := "totally_new_username")
        },
            200)

        with patch('discord.tasks.requests.get', new=Mock(return_value=response)) as p:
            tasks.update_user(self.tourney_user.osu_user_id)

            self.assertGreater(p.call_count, 0)
            self.tourney_user.refresh_from_db()
            self.assertEqual(new_username, self.tourney_user.osu_username)

    @patch("discord.tasks.get_osu_token")
    def test_stats_update_queue_decr(self, mocked_get_osu_token):
        """
        Test that we decrement the "osu_queue_length" key in cache
        :return:
        """
        mocked_get_osu_token.return_value = "TEST_VALID_TOKEN"
        response = MockResponse({
            "badges": [],
            "statistics": {"global_rank": 1000},
            "username": self.tourney_user.osu_username
        },
            200)

        with patch('discord.tasks.requests.get', new=Mock(return_value=response)):
            with patch('discord.tasks.cache.decr') as cache_decr:
                with patch('discord.tasks.cache.touch') as cache_touch:
                    tasks.update_user(self.tourney_user.osu_user_id)
                    self.assertEqual(cache_decr.call_count, 1)
                    self.assertEqual(cache_touch.call_count, 1)


class ReturnBadgesOnDetailViewTestCase(TestCase):
    def setUp(self):
        self.maxDiff = None
        self.request_factory = APIRequestFactory()
        self.test_user = User.objects.create()
        self.test_team = TournamentTeam.objects.create(osu_flag="GB")
        self.test_tourney_player = TournamentPlayer.objects.create(
            user_id=self.test_user.pk,
            osu_user_id=self.test_user.pk,
            osu_username=f"user_{self.test_user.pk}",
            discord_user_id=self.test_user.pk,
            osu_stats_updated=datetime.datetime.now(datetime.timezone.utc),
            osu_flag="GB",
            team=self.test_team)

        self.sample_badges = [
            {
                "description": "this user got a badge!",
                "awarded_at": "2023-11-19T21:25:58+00:00",
                "url": "http://testserver/badge",
                "image_url": "http://testserver/image",
                "image_url_2x": "http://testserver/image_2x",
            },
            {
                "description": "this user has _more_ than one badge!!",
                "awarded_at": "2023-11-25T18:51:14+00:00",
                "url": "http://testserver/badge2",
                "image_url": "http://testserver/image2",
                "image_url_2x": "http://testserver/image2_2x",
            },
        ]

    def create_badges_in_db(self, badges):
        for badge in badges:
            TournamentPlayerBadge.objects.create(user=self.test_tourney_player,
                                                 description=badge['description'],
                                                 award_date=datetime.datetime.fromisoformat(badge['awarded_at']),
                                                 url=badge['url'],
                                                 image_url=badge['image_url'],
                                                 image_url_2x=badge['image_url_2x'])

    def test_badges_present_in_details_empty(self):
        request = self.request_factory.get(f'/registrants/{self.test_user.pk}/')
        registrant_detail = TournamentPlayerViewSet.as_view({'get': 'retrieve'})
        response = registrant_detail(request, pk=self.test_user.pk)
        self.assertEqual(response.status_code, 200)
        self.assertCountEqual(response.data['badges'], [])

    def create_badge(self, badge_date):
        badges = self.sample_badges.copy()
        badges += [
            {
                "description": "wow, what an old badge!",
                "awarded_at": badge_date,
                "url": "http://testserver/badge_old",
                "image_url": "http://testserver/image_old",
                "image_url_2x": "http://testserver/image_old_2x",
            },
        ]
        return badges

    def prep_request_with_badge_cutoff(self, badge_award_date_str, cutoff_date):
        badges = self.create_badge(badge_award_date_str)
        self.create_badges_in_db(badges)

        cutoff_date_ts = int(cutoff_date.timestamp())
        request = self.request_factory.get(f'/registrants/{self.test_user.pk}/?badge_cutoff_date={cutoff_date_ts}')
        registrant_detail = TournamentPlayerViewSet.as_view({'get': 'retrieve'})
        response = registrant_detail(request, pk=self.test_user.pk)
        return badges, response

    def test_badges_custom_cutoff_excluded(self):
        award_date = "2019-11-19T21:25:58+00:00"
        cutoff = datetime.datetime.fromisoformat(award_date) + datetime.timedelta(seconds=5)
        badges, response = self.prep_request_with_badge_cutoff(award_date, cutoff)

        self.assertTrue(len(badges) == len(self.sample_badges) + 1)
        self.assertTrue(len(badges) == len(response.data['badges']) + 1)
        self.assertCountEqual(self.sample_badges, response.data['badges'])

    def test_badges_custom_cutoff_included(self):
        award_date = "2019-11-19T21:25:58+00:00"
        cutoff = datetime.datetime.fromisoformat(award_date) + datetime.timedelta(seconds=-5)
        badges, response = self.prep_request_with_badge_cutoff(award_date, cutoff)

        self.assertTrue(len(badges) == len(self.sample_badges) + 1)
        self.assertTrue(len(badges) == len(response.data['badges']))
        self.assertCountEqual(badges, response.data['badges'])

    # noinspection SpellCheckingInspection
    @parameterized.expand([
        ("2020-01-01",),  # not timestamp
        ("gjkhafgkhadfsg",),  # not even a date
        ("1705199901.192",),  # includes fractional part
    ])
    def test_badges_custom_cutoff_invalid_ts(self, invalid_timestamp):
        self.create_badges_in_db(self.sample_badges)

        request = self.request_factory.get(f'/registrants/{self.test_user.pk}/?badge_cutoff_date={invalid_timestamp}')
        registrant_detail = TournamentPlayerViewSet.as_view({'get': 'retrieve'})
        response = registrant_detail(request, pk=self.test_user.pk)

        self.assertEqual(response.status_code, 400)
        self.assertEqual(response.data['error'], "Invalid badge_cutoff_date provided, please provide a unix timestamp")

    def test_badges_default_cutoff(self):
        badges = self.sample_badges.copy()
        badges += [
            {
                "description": "wow, what an old badge!",
                "awarded_at": "2019-11-19T21:25:58+00:00",
                "url": "http://testserver/badge_old",
                "image_url": "http://testserver/image_old",
                "image_url_2x": "http://testserver/image_old_2x",
            },
        ]
        self.create_badges_in_db(badges)

        request = self.request_factory.get(f'/registrants/{self.test_user.pk}/')
        registrant_detail = TournamentPlayerViewSet.as_view({'get': 'retrieve'})
        response = registrant_detail(request, pk=self.test_user.pk)

        self.assertTrue(len(badges) == len(self.sample_badges) + 1)
        self.assertTrue(len(badges) == len(response.data['badges']) + 1)
        self.assertEqual(len(self.sample_badges), len(response.data['badges']))
        self.assertCountEqual(self.sample_badges, response.data['badges'])

    def test_badges_present_in_details(self):
        self.create_badges_in_db(self.sample_badges)

        request = self.request_factory.get(f'/registrants/{self.test_user.pk}/')
        registrant_detail = TournamentPlayerViewSet.as_view({'get': 'retrieve'})
        response = registrant_detail(request, pk=self.test_user.pk)

        self.assertEqual(len(self.sample_badges), len(response.data['badges']))
        self.assertCountEqual(self.sample_badges, response.data['badges'])

    def test_badges_not_present_in_list(self):
        self.create_badges_in_db(self.sample_badges)

        request = self.request_factory.get(f'/registrants/?limit=1')
        registrant_detail = TournamentPlayerViewSet.as_view({'get': 'list'})
        response = registrant_detail(request, pk=self.test_user.pk)
        self.assertTrue("badges" not in response.data)


class RegistrantsListingTestCase(TestCase):
    def test_get_registrant_not_found(self):
        factory = APIRequestFactory()
        pk = 917241725121
        request = factory.get(f'/registrants/{pk}')
        list_method = TournamentPlayerViewSet.as_view({'get': 'retrieve'}, permission_classes=[])

        response = list_method(request, pk=pk)

        self.assertEqual(404, response.status_code)


class UpdateTournamentPlayerRolesTestCase(TestCase):
    def setUp(self):
        self.user = User.objects.create()
        self.tourney_user = TournamentPlayer.objects.create(user=self.user,
                                                            discord_user_id=481212233,
                                                            osu_user_id=1,
                                                            osu_stats_updated=datetime.datetime.fromtimestamp(
                                                                0,
                                                                tz=datetime.timezone.utc
                                                            ))

    @parameterized.expand([
        ("true", True,),
        ("false", False,)
    ])
    def test_set_tourney_player_staff(self, _, new_staff_status):
        factory = APIRequestFactory()
        request = factory.patch(f'/registrants/{self.tourney_user.discord_user_id}/?key=discord',
                                {'is_staff': new_staff_status},
                                format='json')
        set_tourney_user_staff = TournamentPlayerViewSet.as_view({'patch': 'partial_update'},
                                                                 permission_classes=[])

        res = set_tourney_user_staff(request, pk=self.tourney_user.discord_user_id)

        self.assertEqual(200, res.status_code)
        self.tourney_user.refresh_from_db()
        self.assertEqual(new_staff_status, self.tourney_user.is_staff)

    def test_set_tourney_player_staff_bad_type(self):
        factory = APIRequestFactory()
        request = factory.patch(f'/registrants/{self.tourney_user.discord_user_id}/?key=discord',
                                {'is_staff': 'not a boolean'},
                                format='json')
        set_tourney_user_staff = TournamentPlayerViewSet.as_view({'patch': 'partial_update'},
                                                                 permission_classes=[])

        res = set_tourney_user_staff(request, pk=self.tourney_user.discord_user_id)

        self.assertEqual(400, res.status_code)
