import json

from asgiref.sync import async_to_sync
from channels.generic.websocket import WebsocketConsumer
from django.conf import settings


class DiscordRegistrationConsumer(WebsocketConsumer):
    def connect(self):
        async_to_sync(self.channel_layer.group_add)(settings.CHANNELS_DISCORD_WS_GROUP_NAME, self.channel_name)
        self.accept()

    def disconnect(self, close_code):
        async_to_sync(self.channel_layer.group_discard)(settings.CHANNELS_DISCORD_WS_GROUP_NAME, self.channel_name)

    def _forward_event_message(self, event):
        payload = event["message"]

        self.send(text_data=json.dumps({"message": payload}))

    def registration_new(self, event):
        self._forward_event_message(event)

    def registration_delete(self, event):
        self._forward_event_message(event)

    def registration_discord_switch(self, event):
        self._forward_event_message(event)
