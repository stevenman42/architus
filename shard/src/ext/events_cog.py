import pytz
import dateutil.parser
import re
from unidecode import unidecode
from contextlib import suppress
from discord.ext.commands import Cog
from discord.ext import commands

class ReminderEvent:
    def __init__(self, msg, title, time_str):
        self.msg = msg
        self.title_str = title
        self.parsed_time = time_str
        self.in_channel = False
        self.member_mentions = set()
        self.role_mentions = []
    

class ScheduleEvent(object):
    def __init__(self, msg, title, time_str):
        self.msg = msg
        self.title_str = title
        self.parsed_time = time_str
        self.yes = set()
        self.no = set()
        self.maybe = set()


class PollEvent(object):
    def __init__(self, msg, title, options, votes):
        self.msg = msg
        self.title = title
        self.options = options
        self.votes = votes


class EventCog(Cog, name="Events"):
    '''
    Special messages that track the number of participants
    '''

    YES_EMOJI = '✅'
    NO_EMOJI = '❌'
    MAYBE_EMOJI = '🤷'
    OPT_IN_EMOJI = '⏲️'

    ANSWERS = [
        '\N{DIGIT ZERO}\N{COMBINING ENCLOSING KEYCAP}',
        '\N{DIGIT ONE}\N{COMBINING ENCLOSING KEYCAP}',
        '\N{DIGIT TWO}\N{COMBINING ENCLOSING KEYCAP}',
        '\N{DIGIT THREE}\N{COMBINING ENCLOSING KEYCAP}',
        '\N{DIGIT FOUR}\N{COMBINING ENCLOSING KEYCAP}',
        '\N{DIGIT FIVE}\N{COMBINING ENCLOSING KEYCAP}',
        '\N{DIGIT SIX}\N{COMBINING ENCLOSING KEYCAP}',
        '\N{DIGIT SEVEN}\N{COMBINING ENCLOSING KEYCAP}',
        '\N{DIGIT EIGHT}\N{COMBINING ENCLOSING KEYCAP}',
        '\N{DIGIT NINE}\N{COMBINING ENCLOSING KEYCAP}'
    ]

    def __init__(self, bot):
        self.bot = bot
        self.schedule_messages = {}
        self.poll_messages = {}
        self.reminder_messages = {}

    @commands.Cog.listener()
    async def on_reaction_add(self, react, user):
        if not user.bot and react.message.id in self.schedule_messages:
            event = self.schedule_messages[react.message.id]
            with suppress(KeyError):
                event.yes.remove(user)
            with suppress(KeyError):
                event.no.remove(user)
            with suppress(KeyError):
                event.maybe.remove(user)
            for r in react.message.reactions:
                if r != react:
                    await r.remove(user)

            if self.YES_EMOJI in str(react.emoji):
                event.yes.add(user)
            elif self.NO_EMOJI in str(react.emoji):
                event.no.add(user)
            elif self.MAYBE_EMOJI in str(react.emoji):
                event.maybe.add(user)
            await react.message.edit(
                content=self.render_schedule_text(event.title_str, event.parsed_time, event.yes, event.no, event.maybe))

        elif not user.bot and react.message.id in self.poll_messages:
            event = self.poll_messages[react.message.id]
            for r in react.message.reactions:
                try:
                    i = self.ANSWERS.index(str(r.emoji))
                    event.votes[i] = [u for u in await r.users().flatten() if u != self.bot.user]
                except ValueError:
                    continue
            await react.message.edit(
                content=self.render_poll_text(event.title, event.options, event.votes))

        elif not user.bot and react.message.id in self.reminder_messages:
            reminder = self.reminder_messages[react.message.id]
            if react.emoji == self.OPT_IN_EMOJI:
            # alarm_reaction = next(r for r in message.reactions if r.emoji == self.OPT_IN_EMOJI)
                reminder.member_mentions.update(await react.users().flatten())


            

    @commands.Cog.listener()
    async def on_reaction_remove(self, react, user):

        if not user.bot and react.message.id in self.schedule_messages and False:
            event = self.schedule_messages[react.message.id]
            with suppress(KeyError):
                if self.YES_EMOJI in str(react.emoji):
                    event.yes.remove(user)
                elif self.NO_EMOJI in str(react.emoji):
                    event.no.remove(user)
                elif self.MAYBE_EMOJI in str(react.emoji):
                    event.maybe.remove(user)
            await react.message.edit(
                content=self.render_schedule_text(event.title_str, event.parsed_time, event.yes, event.no, event.maybe))

        elif not user.bot and react.message.id in self.poll_messages:
            await self.on_reaction_add(react, user)

        elif not user.bot and react.message.id in self.reminder_messages:
            reminder = self.reminder_messages[react.message.id]
            if react.emoji == OPT_IN_EMOJI:
                reminder.member_mentions.remove(user)

    async def prompt_date(self, ctx, author):
        await ctx.channel.send("What time?")
        time_msg = await self.bot.wait_for('message', timeout=30, check=lambda m: m.author == author)
        try:
            return dateutil.parser.parse(time_msg.clean_content)
        except Exception:
            await ctx.channel.send("Not sure what that means.")
            return None

    async def prompt_title(self, ctx, author):
        await ctx.channel.send("What event?")
        title_msg = await self.bot.wait_for('message', timeout=30, check=lambda m: m.author == author)
        return title_msg.clean_content or None

    @commands.command()
    async def schedule(self, ctx, *args):
        '''
        Start an event poll.
        Timezone is based on your servers voice zone.
        '''
        # event bot's id
        if ctx.guild.get_member(476042677440479252):
            print("Not scheduling cause event bot exists.")
            return

        title, parsed_time = await self.parse_time(ctx, args)

        if len(title) == 0:
            title_str = await self.prompt_title(ctx, ctx.author)
            if not title_str:
                return
        else:
            title_str = ' '.join(title)

        msg = await ctx.channel.send(self.render_schedule_text(title_str, parsed_time, [], [], []))
        await msg.add_reaction(self.YES_EMOJI)
        await msg.add_reaction(self.NO_EMOJI)
        await msg.add_reaction(self.MAYBE_EMOJI)
        self.schedule_messages[msg.id] = ScheduleEvent(msg, title_str, parsed_time)

    @commands.command()
    async def poll(self, ctx, *args):
        '''
        Starts a poll with some pretty formatting.
        Supports up to 10 options.
        '''
        pattern = re.compile(r'.poll (?P<title>(?:\S*[^\s,] )+)(?P<options>.*$)')
        match = pattern.search(unidecode(ctx.message.content))
        if not match:
            return

        votes = [[] for x in range(10)]
        options = [o.lstrip() for o in match.group('options').split(",")[:10]]
        title = match.group('title').replace('"', '')
        text = self.render_poll_text(title, options, votes)

        msg = await ctx.channel.send(text)
        for i in range(len(options)):
            await msg.add_reaction(self.ANSWERS[i])

        self.poll_messages[msg.id] = PollEvent(msg, title, options, votes)

    @commands.command()
    async def reminder(self, ctx, *args):
        '''
        Sets up a scheduled reminder that other users can opt into.
        Can be set to send the reminder in a public channel or in private messages.
        '''

        clean_args = [arg for arg in args if arg not in (m.mention for m in ctx.message.mentions) and arg not in (r.mention for r in ctx.message.role_mentions)]
        title, parsed_time = await self.parse_time(ctx, clean_args)
        

        if ctx.author.id in self.bot.settings[ctx.guild].admin_ids:
            member_list = set(ctx.message.mentions)
            mention_list = ctx.message.mentions + ctx.message.role_mentions
        else:
            pass
        
        em = discord.Embed(title="8)", description="hi", colour=0x111111)
        message = await ctx.send(embed=em)
        reminder = ReminderEvent(message, title, parsed_time)
        self.reminder_messages[message.id] = reminder

    def get_timezone(self, region):
        region = str(region)
        if region == 'us-south' or region == 'us-east':
            return 'America/New_York'
        elif region == 'us-central':
            return 'America/Chicago'
        elif region == 'us-west':
            return 'America/Los_Angeles'
        else:
            return 'Etc/UTC'

    def render_schedule_text(self, title_str, parsed_time, yes, no, maybe):
        return "**__%s__**\n**Time:** %s\n:white_check_mark: Yes (%d): %s\n:x: No (%d): %s\n:shrug: Maybe (%d): %s" % (
            title_str.strip(),
            parsed_time.strftime("%b %d %I:%M%p %Z"),
            len(yes), ' '.join([u.mention for u in yes]),
            len(no), ' '.join([u.mention for u in no]),
            len(maybe), ' '.join([u.mention for u in maybe])
        )

    def render_poll_text(self, title, options, votes):
        text = f"**__{title.strip()}__**\n"
        i = 0
        for option in options:
            text += "%s **%s (%d)**: %s\n" % (
                    self.ANSWERS[i],
                    option,
                    len(votes[i]), ' '.join([u.mention for u in votes[i]])
            )
            i += 1
        return text

    async def parse_time(self, ctx, args):
        tz = pytz.timezone(self.get_timezone(ctx.guild.region))
        # ct = datetime.datetime.now(tz=tz)
        title = []
        parsed_time = None
        args = list(args)
        for _ in args:
            with suppress(ValueError):
                # print(" ".join(args))
                parsed_time = dateutil.parser.parse(' '.join(args))
                # parsed_time = tz.localize(parsed_time)
                break
            with suppress(ValueError):
                # print(" ".join(args))
                parsed_time = dateutil.parser.parse(' '.join(args[:-1]))
                # parsed_time = tz.localize(parsed_time)
                # print("deleted something from the end")
                break
            title.append(args[0])
            del args[0]
        else:
            parsed_time = await self.prompt_date(ctx, ctx.author)
            if not parsed_time:
                return
            parsed_time = tz.localize(parsed_time)
        return title, parsed_time
    

def setup(bot):
    bot.add_cog(EventCog(bot))
