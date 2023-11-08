from django.contrib.auth.models import User
from django.http import HttpResponseRedirect
from django.shortcuts import render, redirect
from rest_framework import viewsets, status
import requests
import urllib.parse
from django.conf import settings
from rest_framework.response import Response
from rest_framework.decorators import action
from django.contrib.auth import authenticate, login, logout
import django.dispatch

login_signal = django.dispatch.Signal()


def parse_return_page(request):
    return_page: str | None = request.query_params.get("state", None)
    return_page = urllib.parse.unquote(return_page)
    if not return_page.startswith("/"):
        return_page = None
    return return_page


class SessionDetails(viewsets.ViewSet):
    @staticmethod
    def list(request):
        return Response({
            "logged_in_user": request.user.username,
            "discord": request.session.get("discord_user_data"),
            "osu": request.session.get("osu_user_data")})

    @action(methods=['get', 'post'], detail=False)
    def logout(self, request):
        if request.session.get("discord_user_data") is not None:
            del request.session["discord_user_data"]
        if request.session.get("osu_user_data") is not None:
            del request.session["osu_user_data"]
        logout(request)
        return Response({"ok": "logged out"}, status=status.HTTP_204_NO_CONTENT)

    @action(methods=['get', 'post'], detail=False)
    def login(self, request):
        user: User = authenticate(request,
                                  discord_user_data=request.session.get("discord_user_data"),
                                  osu_user_data=request.session.get("osu_user_data"))
        if user is not None:
            login(request, user)
            return Response({"ok": "logged in", "user": user.username})
        return Response({"error": "failed to authenticate"}, status=status.HTTP_401_UNAUTHORIZED)

    @action(methods=['delete'], detail=False)
    def delete_account(self, request):
        # todo: using authentication classes would make this a lot easier no?
        if not request.user.is_authenticated:
            return Response({"error": "not logged in"}, status=status.HTTP_401_UNAUTHORIZED)
        user = request.user
        logout(request)
        user.delete()
        return Response({"ok": "account deleted"}, status=status.HTTP_204_NO_CONTENT)


class OsuAuth(viewsets.ViewSet):
    @action(methods=['get'], detail=False)
    def prompt_login(self, request):
        return_page = request.query_params.get("return_page", None)
        uri = (f"{settings.OSU_OAUTH_ENDPOINT}/authorize"
               f"?response_type=code"
               f"&client_id={settings.OSU_CLIENT_ID}"
               f"&scope=identify"
               f"&redirect_uri={urllib.parse.quote(settings.OSU_REDIRECT_URI)}"
               f"&prompt=consent")
        if return_page is not None:
            uri += f"&state={return_page}"
        return HttpResponseRedirect(redirect_to=uri)

    @action(methods=['get'], detail=False)
    def code(self, request):
        code = request.query_params.get("code", None)
        return_page = parse_return_page(request)
        if code is None:
            return Response({"error": "missing `code` query param"}, status=status.HTTP_400_BAD_REQUEST)

        r = requests.post(f'{settings.OSU_OAUTH_ENDPOINT}/token',
                          data={'grant_type': 'authorization_code',
                                'code': code,
                                'redirect_uri': settings.OSU_REDIRECT_URI},
                          headers={'Content-Type': 'application/x-www-form-urlencoded'},
                          auth=(settings.OSU_CLIENT_ID, settings.OSU_CLIENT_SECRET))
        if r.status_code != 200:
            return Response(r.json(), status=r.status_code)

        auth_data = r.json()
        # fetch user information
        r = requests.get(f"{settings.OSU_API_ENDPOINT}/me",
                         headers={"Authorization": f"Bearer {auth_data.get('access_token')}"})
        if r.status_code != 200:
            return Response(r.json(), status=r.status_code)
        user_data = r.json()
        request.session["osu_user_data"] = user_data
        if return_page is not None:
            return redirect(return_page)
        return Response(user_data, status=r.status_code)

    @staticmethod
    def list(request):
        return Response({})


class DiscordAuth(viewsets.ViewSet):
    @action(methods=['get'], detail=False)
    def prompt_login(self, request):
        return_page = request.query_params.get("return_page", None)
        uri = (f"https://discord.com/oauth2/authorize"
               f"?response_type=code"
               f"&client_id={settings.DISCORD_CLIENT_ID}"
               f"&scope=identify"
               f"&redirect_uri={urllib.parse.quote(settings.DISCORD_REDIRECT_URI)}"
               f"&prompt=consent")
        if return_page is not None:
            uri += f"&state={return_page}"
        return HttpResponseRedirect(redirect_to=uri)

    @action(methods=['get'], detail=False)
    def discord_code(self, request):
        code = request.query_params.get("code", None)
        return_page = parse_return_page(request)
        if code is None:
            return Response({"error": "missing `code` query param"}, status=status.HTTP_400_BAD_REQUEST)

        # access token exchange
        data = {
            'grant_type': 'authorization_code',
            'code': code,
            'redirect_uri': settings.DISCORD_REDIRECT_URI
        }
        headers = {'Content-Type': 'application/x-www-form-urlencoded'}
        r = requests.post(f'{settings.DISCORD_API_ENDPOINT}/oauth2/token',
                          data=data,
                          headers=headers,
                          auth=(settings.DISCORD_CLIENT_ID, settings.DISCORD_CLIENT_SECRET))
        if r.status_code != 200:
            return Response(r.json(), status=r.status_code)
        auth_data = r.json()

        # fetch user information
        r = requests.get(f"{settings.DISCORD_API_ENDPOINT}/oauth2/@me",
                         headers={"Authorization": f"Bearer {auth_data.get('access_token')}"})
        if r.status_code != 200:
            return Response(r.json(), status=r.status_code)
        user_data = r.json().get("user")
        request.session["discord_user_data"] = user_data
        if return_page is not None:
            return redirect(return_page)
        return Response(user_data, status=r.status_code)

        # check if user exists
        # if TournamentPlayer.objects.filter(discord_user_id)

    @action(methods=['get'], detail=False)
    def token(self, request):
        print(request.query_params.get("access_token"))
        return Response(request.query_params)

    @staticmethod
    def list(request):
        return Response({})


def login_frontend(request):
    return render(request, "login.html", {})
