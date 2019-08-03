import discord
from discord.ext.commands import Bot
from datetime import datetime
import asyncio
import zmq
import zmq.asyncio
import json
import websockets
import os
import time
from pytz import timezone

from src.user_command import UserCommand
from src.smart_message import smart_message
from src.config import get_session
from src.models import Command

starboarded_messages = []
shard_id = None
num_shards = None
MANAGER_URI = "ws://manager:5300"


class Architus(Bot):

    def __init__(self, **kwargs):
        self.user_commands = {}
        self.session = get_session()
        self.guild_counter = (0, 0)
        self.tracked_messages = {}
        super().__init__(**kwargs)

    def run(self, token):
        self.loop.create_task(self.list_guilds())

        ctx = zmq.asyncio.Context()
        self.loop.create_task(self.api_entry(ctx))
        super().run(token)

    @asyncio.coroutine
    def api_entry(self, ctx):
        api = self.get_cog('Api')
        sub = ctx.socket(zmq.SUB)
        sub.connect(f"tcp://ipc:6200")
        pub = ctx.socket(zmq.PUB)
        pub.connect(f"tcp://ipc:7300")

        print('setting sockopt')
        sub.setsockopt_string(zmq.SUBSCRIBE, str(shard_id))

        while True:
            try:
                task = (yield from sub.recv_string())[len(str(shard_id)) + 1:]
                print(f"shard {shard_id} got task {task}")
            except Exception as e:
                print(f"Malformed ipc request or something: {e}")
                continue
            self.loop.create_task(api.handle_request(pub, json.loads(task)))

    async def on_reaction_add(self, react, user):
        if user == self.user:
            return
        settings = self.guild_settings.get_guild(react.message.guild, session=self.session)
        if settings.starboard_emoji in str(react.emoji):
            if react.count == settings.starboard_threshold:
                await self.starboard_post(react.message, react.message.guild)

        if settings.edit_emoji in str(react.emoji):
            sm = self.tracked_messages.get(react.message.id)
            if sm:
                await sm.add_popup(react.message.channel)

    async def on_reaction_remove(self, react, user):
        settings = self.guild_settings.get_guild(react.message.guild, session=self.session)
        if settings.edit_emoji in str(react.emoji) and react.count == 0:
            sm = self.tracked_messages[react.message.id]
            await sm.delete_popup()

    async def on_message_edit(self, before, after):
        if before.author == self.user:
            return

        sm = self.tracked_messages.get(before.id)
        # have to manually give datetime.now() cause discord.py is broken
        if sm and sm.add_edit(before, after, datetime.now()):
            await sm.edit_popup()
            return
        sm = smart_message(before)
        sm.add_edit(before, after, datetime.now())
        self.tracked_messages[before.id] = sm

    async def on_message(self, msg):
        print('Message from {0.author} in {0.guild.name}: {0.content}'.format(msg))

        if msg.author == self.user:
            return

        # check for real commands
        await self.process_commands(msg)
        # check for user commands
        for command in self.user_commands[msg.guild.id]:
            if (command.triggered(msg.content)):
                await command.execute(msg)
                break

    async def on_ready(self):
        await self.initialize_user_commands()
        print('Logged on as {0}!'.format(self.user))
        await self.change_presence(activity=discord.Activity(name=f"shard id: {shard_id}", type=3))

    async def on_guild_join(self, guild):
        print(" -- JOINED NEW GUILD: {guild.name} -- ")
        self.user_commands.setdefault(guild.id, [])

    async def initialize_user_commands(self):
        command_list = self.session.query(Command).all()
        for guild in self.guilds:
            self.user_commands.setdefault(int(guild.id), [])
        for command in command_list:
            self.user_commands.setdefault(command.server_id, [])
            self.user_commands[command.server_id].append(UserCommand(
                self.session,
                command.trigger.replace(str(command.server_id), '', 1),
                command.response, command.count,
                self.get_guild(command.server_id),
                command.author_id))
        for guild, cmds in self.user_commands.items():
            self.user_commands[guild].sort()

    @property
    def guild_settings(self):
        return self.get_cog('GuildSettings')

    async def list_guilds(self):
        await self.wait_until_ready()
        while not self.is_closed():
            print("Current guilds:")
            guild_counter = 0
            user_counter = 0
            for guild in self.guilds:
                me = guild.get_member(self.user.id)
                if me.display_name == 'archit.us':
                    await me.edit(nick='architus')
                print("{} - {} ({})".format(guild.name, guild.id, guild.member_count))
                guild_counter += 1
                user_counter += guild.member_count
            self.guild_counter = (guild_counter, user_counter)

            await asyncio.sleep(600)

    async def starboard_post(self, message, guild):
        starboard_ch = discord.utils.get(guild.text_channels, name='starboard')
        if message.id in starboarded_messages or not starboard_ch or message.author == self.user:
            return
        print("Starboarding message: " + message.content)
        starboarded_messages.append(message.id)
        utc = message.created_at.replace(tzinfo=timezone('UTC'))
        est = utc.astimezone(timezone('US/Eastern'))
        em = discord.Embed(title=est.strftime("%Y-%m-%d %I:%M %p"), description=message.content, colour=0x42f468)
        em.set_author(name=message.author.display_name, icon_url=message.author.avatar_url)
        if message.embeds:
            em.set_image(url=message.embeds[0].url)
        elif message.attachments:
            em.set_image(url=message.attachments[0].url)
        await starboard_ch.send(embed=em)

async def heartbeat():
    global num_shards
    global shard_id
    print("connecting to manager...")
    async with websockets.connect(MANAGER_URI) as websocket:
        data = json.loads(await websocket.recv())
        print(f"got data: {data}")
        num_shards = data['num_shards']
        shard_id = data['shard_id']
        await websocket.send("ok thanks")
        while False:
            await websocket.recv()
            await websocket.send("everything's fine here, thanks")
#print("starting garbage")
#asyncio.get_event_loop().run_until_complete(heartbeat())
#print("after garbage")


#while shard_id is None:
    #time.sleep(.1)
#print("shard_id is not none")
shard_id = 0

architus = Architus(
    command_prefix=('!', '?'),
    shard_id=shard_id,
    shard_count=num_shards
)

for ext in (e for e in os.listdir("src/ext") if e.endswith(".py")):
    architus.load_extension(f"src.ext.{ext[:-3]}")

architus.load_extension('src.emoji_manager')
architus.load_extension('src.api.api')
architus.load_extension('src.guild_settings')

if __name__ == '__main__':
    from src.config import secret_token
    architus.run(secret_token)
