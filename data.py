import re
from datetime import timedelta, datetime, date, time

import pytz


class BotConfig:
    config_channel = None
    response_channel = None
    raw_config = []
    approve = None
    on_deck = None
    events = []
    task = None
    voice_template = None


class Event:
    def __init__(self, day, name, tz, start, channel, host):
        self.day = ["monday", "tuesday", "wednesday", "thursday", "friday", "saturday", "sunday"].index(day.lower())
        self.name = name
        self.tz = pytz.timezone(tz)
        self.start = start
        self.channel = channel
        self.host = host

    def get_next_event_time(self, offset=timedelta(seconds=0)):
        current_time = datetime.now(tz=pytz.utc) + offset
        weekday = current_time.weekday()
        if weekday < self.day:
            day_delta = self.day - weekday + 7
        else:
            day_delta = self.day - weekday

        tz_unaware_time = datetime.combine(
            date.today() + timedelta(days=day_delta),
            time(int(self.start[0:2]), int(self.start[2:4]))
        )
        possible = self.tz.localize(tz_unaware_time).astimezone(pytz.utc)

        if possible - current_time < timedelta(hours=-4):
            return self.tz.localize(tz_unaware_time + timedelta(days=7)).astimezone(pytz.utc)

        return possible


class Game:
    def __init__(self, name, user, players, length, description, platform, info=None):
        self.user = user
        self.info = info.strip() if info is not None else None
        self.platform = platform.strip().replace("\n", "")
        self.description = description.strip()
        self.length = length.strip()
        self.players = players.strip()
        self.name = name.strip().replace("\n", "")
        self.approved = False
        self.on_deck = False

    @classmethod
    def from_string(cls, game_string, user):
        print(game_string)
        maybe_game = re.search(
            r"\s*<:Bullet_1:\d+>\s+((\s*\*\*\s*)?name of game(\s*\*\*\s*)?:(\s*\*\*\s*)?\s*)?(?P<name>[^<]+)"
            r"\s*<:Bullet_2:\d+>\s+((\s*\*\*\s*)?number of players(\s*\*\*\s*)?:(\s*\*\*\s*)?\s*)?(?P<players>[^<]+)"
            r"\s*<:Bullet_3:\d+>\s+((\s*\*\*\s*)?total time(\s*\*\*\s*)?:(\s*\*\*\s*)?\s*)?(?P<length>[^<]+)"
            r"\s*<:Bullet_4:\d+>\s+((\s*\*\*\s*)?description of game(\s*\*\*\s*)?:(\s*\*\*\s*)?\s*)?(?P<description>[^<]+)"
            r"\s*<:Bullet_5:\d+>\s+((\s*\*\*\s*)?playtesting platform(\s*\*\*\s*)?:(\s*\*\*\s*)?\s*)?(?P<platform>[^<]+)"
            r"(\s*<:Bullet_6:\d+>\s+((\s*\*\*\s*)?any additional info(\s*\*\*\s*)?:(\s*\*\*\s*)?\s*)?(?P<info>[^<]+))?",
            game_string, re.I
        )
        if maybe_game is None:
            raise ValueError("not a game")
        return Game(user=user, **maybe_game.groupdict())