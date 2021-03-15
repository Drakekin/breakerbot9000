import asyncio
import re
from datetime import datetime, timedelta
from os import environ

import discord
from discord.errors import Forbidden
import pytz

from data import BotConfig, Event, Game

UPDATE_POST_IMAGE_URL = "https://media.discordapp.net/attachments/698288353493254154/778364076468076544/Plytest_Submissions-09.png?width=800&height=292"

client = discord.Client()

config = BotConfig()


@client.event
async def on_ready():
    print(f"Signed in as {client.user}")

    for channel in client.get_all_channels():
        if not isinstance(channel, discord.TextChannel):
            continue

        try:
            print(f"Testing {channel.name}")
            async for message in channel.history(limit=1, oldest_first=True):
                if "configuration" in message.content and client.user.id in message.raw_mentions:
                    config.config_channel = channel
                    print("Found config channel")
                    break
        except Forbidden:
            print("Missing permissions")

        if config.config_channel is not None:
            break

    await parse_config(suppress_message=True)

    if config.task is not None:
        config.task.cancel()

    config.task = asyncio.create_task(main_task())


async def parse_event(event):
    event_time = event.get_next_event_time()
    games = []

    async for message in event.channel.history(after=(event_time-timedelta(days=7)+timedelta(hours=4)).replace(tzinfo=None)):
        try:
            game = Game.from_string(message.content, message.author)
            if "name of game" in game.name.lower() or game.name.strip() == "":
                continue
            game.approved = config.approve in [reaction.emoji for reaction in message.reactions]
            game.on_deck = config.on_deck in [reaction.emoji for reaction in message.reactions]
            games.append(game)
        except ValueError:
            pass

    return games


def create_update_post(event):
    event_time = event.get_next_event_time(offset=timedelta(minutes=10))
    local_time = event_time.astimezone(event.tz)
    et_time = event_time.astimezone(pytz.timezone("US/Eastern"))
    et_end = et_time + timedelta(hours=3)
    uk_time = event_time.astimezone(pytz.timezone("Europe/London"))
    uk_end = uk_time + timedelta(hours=3)

    return f"""*Now accepting submissions for {local_time.strftime('%B %-d')}* <:x_Breaker_Playtest:763231646291460146> 
**{et_time.strftime('%-I:%M')} - {et_end.strftime('%-I:%M')}  ｜  {uk_time.strftime('%-I:%M %Z')} - {uk_end.strftime('%-I:%M %Z')}**

Be sure to check <#768608578751561728> before signing up or participating. Remember:
<:BMG_TinyBullet:764153337971998770> **Playtesters** don't need to sign up, just join the Weekly Voice chat when the session starts!
<:BMG_TinyBullet:764153337971998770> Please type/write your pronouns in-game next to your display name when possible.
<:BMG_TinyBullet:764153337971998770> Respect the rules of the <@&699328458454728756> {event.host.mention}.
<:BMG_TinyBullet:764153337971998770> Keep general discussion for the event in <#781549464149164103>.

**Designers** please copy, paste, and fill out the following list into this Discord channel to submit your game:

<:Bullet_1:763213967006105611>   **Name of Game**:
<:Bullet_2:763213967153168385>   **Number of Players**:
<:Bullet_3:763213967166275624>   **Total Time**:
<:Bullet_4:763213967149105212>   **Description of Game**:
<:Bullet_5:763213967035203616>   **Playtesting Platform**:
<:Bullet_6:763213967245967360>   **Any Additional Info**: *this is optional!*

We generally accept **six games** per session, and aim to make sure designers who have not playtested with us before or recently have an opportunity to share their games first."""


async def ending_event(event):
    games = await parse_event(event)

    game_channel = []
    for game in games:
        if not game.approved:
            continue

        game_channel.append(f"{game.name} ({game.platform})")

    for channel in client.get_all_channels():
        if not isinstance(channel, discord.VoiceChannel):
            continue

        if channel.name in game_channel:
            await channel.delete()
            game_channel.remove(channel.name)

    if game_channel:
        await config.response_channel.send(f"Could not clean up all voice channels for {event.name}")
    else:
        await config.response_channel.send(f"Cleaned up voice channels for {event.name}")

    await event.channel.send(create_update_post(event), embed=discord.Embed().set_image(url=UPDATE_POST_IMAGE_URL))


async def current_event(event):
    pass  # do nothing for now


async def next_event(event):
    games = await parse_event(event)
    response = f"Channels created for {event.name}, {event.host.mention}. The following games are up tonight:\n"
    game_lists = []
    for game in games:
        if not game.approved:
            continue

        channel = await config.voice_template.clone(name=f"{game.name} ({game.platform})")
        await channel.edit(sync_permissions=True)
        game_lists.append(f"{game.name} ({game.platform} by {game.user.mention}){' (on deck)' if game.on_deck else ''}")

    await config.response_channel.send(response + "\n".join(game_lists))
    await event.channel.send(f"{event.name} has started! Please join {config.voice_template.mention}")


async def main_task():
    print("running")
    while True:
        print("ping")
        current_time = datetime.now(tz=pytz.utc)
        for event in config.events:
            delta = event.get_next_event_time() - current_time
            if delta <= timedelta(hours=-3, minutes=-55):
                print(f"ending {event.name}")
                await ending_event(event)
                break
            elif delta <= timedelta(seconds=0):
                print(f"{event.name} ongoing")
                await current_event(event)
                break
            elif delta <= timedelta(minutes=5):
                print(f"starting {event.name}")
                await next_event(event)
                break

        await asyncio.sleep(300)


async def parse_config(suppress_message=False):
    async for message in config.config_channel.history(limit=None):
        try:
            if message.content.startswith("On deck emoji"):
                config.on_deck = message.content.split(" ")[-1]
            elif message.content.startswith("Approve emoji"):
                config.approve = message.content.split(" ")[-1]
            elif message.content.startswith("Event"):
                _, day, name, tz, start, *_ = message.content.split(",")
                channel = message.channel_mentions[0]
                host = message.mentions[0]
                event = Event(day.strip(), name.strip(), tz.strip(), start.strip(), channel, host)
                config.events.append(event)
            elif message.content.startswith("Respond in"):
                config.response_channel = message.channel_mentions[0]
            elif message.content.startswith("Voice template"):
                config.voice_template = message.channel_mentions[0]
        except:
            pass

    if not suppress_message:
        await config.response_channel.send("Ingested new configuration")


@client.event
async def on_message(message):
    if message.author == client.user:
        return

    if message.channel == config.config_channel:
        await parse_config()

    if client.user.id in message.raw_mentions and message.channel == config.response_channel:
        test = re.search("test post for ([^<>]+)", message.content)
        if test is not None:
            event_name = test.group(1).lower()
            for event in config.events:
                if event.name.lower() == event_name:
                    await config.response_channel.send(create_update_post(event), embed=discord.Embed().set_image(url=UPDATE_POST_IMAGE_URL))
                    break
            else:
                await config.response_channel.send(f"I can't find an event called {event_name}")
                return

        report = re.search("report for ([^<>]+)", message.content)
        if report is not None:
            event_name = report.group(1).lower()
            for event in config.events:
                if event.name.lower() == event_name:
                    games = await parse_event(event)
                    break
            else:
                await config.response_channel.send(f"I can't find an event called {event_name}")
                return

            await config.response_channel.send(
                f"There {'is' if len(games) == 1 else 'are'} currently {len(games)} game{'s' if len(games) != 1 else ''} for {event_name}\n" +
                "\n".join([
                              f"{game.name} ({game.platform}) by {game.user.mention} ({'on deck' if game.on_deck else 'approved' if game.approved else 'pending'})"
                              for game in games])
            )

        demo = re.search("create channels for ([^<>]+)", message.content)
        if demo is not None:
            event_name = demo.group(1).lower()
            for event in config.events:
                if event.name.lower() == event_name:
                    await next_event(event)
                    break
            else:
                await config.response_channel.send(f"I can't find an event called {event_name}")
                return

        undemo = re.search("delete channels for ([^<>]+)", message.content)
        if undemo is not None:
            event_name = undemo.group(1).lower()
            for event in config.events:
                if event.name.lower() == event_name:
                    await ending_event(event)
                    break
            else:
                await config.response_channel.send(f"I can't find an event called {event_name}")
                return

        help = re.search("help", message.content)
        if help is not None:
            await config.response_channel.send(
                "I respond to the following commands when tagged:\n"
                "help\n"
                "report for [event name]\n"
                "list events\n"
            )

        list_events = re.search("list events", message.content)
        if list_events is not None:
            events = sorted(config.events, key=lambda e: e.get_next_event_time())
            response = ",\n".join([f"{event.name} - next running at {event.get_next_event_time().astimezone(event.tz).strftime('%B %-d %H:%M %Z')}" for event in events])
            await config.response_channel.send(f"I know about the following events:\n{response}")


@client.event
async def on_raw_message_edit(payload):
    if payload.channel_id == config.config_channel.id:
        await parse_config()


@client.event
async def on_raw_message_delete(payload):
    if payload.channel_id == config.config_channel.id:
        await parse_config()


if __name__ == "__main__":
    client.run(environ["DISCORD_SECRET"])
