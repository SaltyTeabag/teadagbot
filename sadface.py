__author__ = "Benjamin Keith (ben@benlk.com)"

import sys, os, random, re, time, ConfigParser, string
from twisted.words.protocols import irc
from twisted.internet import protocol
from twisted.internet import reactor
from time import localtime, strftime
from commands.calendarcountdown import CalendarCountdown
from markovbrain import MarkovBrain
from calendar import Calendar

#
# Setting some settings
#

config_file = sys.argv[1]

requiredconfig = [('Connection', 'host'), ('Connection', 'port'), ('Bot', 'nickname'), ('Bot', 'erroneousNickFallback'), ('Bot', 'realname'), ('Bot', 'username'), ('Bot', 'userinfo'), ('Brain', 'reply'), ('Brain', 'brain_file'), ('Brain', 'ignore_file'), ('Brain', 'chain_length'), ('Brain', 'max_words')];
config = ConfigParser.ConfigParser()
config.read(config_file)
for setting in requiredconfig:
    if not config.has_option(setting[0], setting[1]):
        sys.exit('Error: Option "' + setting[1] + '" in section "' + setting[0] + '" is required! Take a look at your config.ini')

requiredsections = ['Channels']
for section in requiredsections:
    if not config.has_section(section) or len(config.items(section)) == 0:
        sys.exit('Error: Section "' + section + '" is required & must be non empty! Take a look at your config.ini')

host = config.get('Connection', 'host')
port = int(config.get('Connection', 'port'))
password = config.get('Connection', 'password')

nickname = config.get('Bot', 'nickname')
erroneousNickFallback = config.get('Bot', 'erroneousNickFallback')
realname = config.get('Bot', 'realname')
username = config.get('Bot', 'username')
userinfo = config.get('Bot', 'userinfo')
versionName = config.get('Bot', 'versionName')

reply = config.get('Brain', 'reply')
brain_file = config.get('Brain', 'brain_file')
if not os.path.exists(brain_file):
    sys.exit('Error: Hoi! I need me some brains! Whaddya think I am, the Tin Man?')

# Chain_length is the length of the message that sadface compares
chain_length = int(config.get('Brain', 'chain_length'))
max_words = int(config.get('Brain', 'max_words'))

ignore_nicks = []
if config.has_option('Brain', 'ignore_file'):
    with open(config.get('Brain', 'ignore_file'), 'r') as f:
        for line in f:
            ignore_nicks.append(line.strip())

channels = {}
for chan,chattiness in config.items("Channels"):
    channels['#' + chan.lower()] = float(chattiness)

listen_only_channels = []
if config.has_option('Bot', 'listenOnlyChannels'):
    for chan in config.get('Bot', 'listenOnlyChannels').split(','):
        listen_only_channels.append('#' + chan.strip().lower())

static_commands = []
if config.has_option('Brain', 'static_commands_file'):
    with open(config.get('Brain', 'static_commands_file'), 'r') as f:
        for line in f:
            split = line.split(':', 1);
            static_commands.append((split[0].strip().lower(), split[1].strip()))

# Calendar from http://www.f1fanatic.co.uk/contact/f1-fanatic-calendar/
formula1_calendar = Calendar('https://www.google.com/calendar/ical/hendnaic1pa2r3oj8b87m08afg%40group.calendar.google.com/public/basic.ics')

dynamic_commands = [CalendarCountdown(formula1_calendar,
                                      ['@next', '@countdown'],
                                      ['r', 'q'],
                                      {'': '', 'r': 'grand prix', 'q': 'grand prix qualifying'}),
                                      # Calendar from http://icalshare.com/calendars/7111
                    CalendarCountdown(Calendar('https://calendar.google.com/calendar/ical/hq7d8mnvjfodf60rno2rbr6leg%40group.calendar.google.com/public/basic.ics'),
                                      ['@nextwec', '@countdownwec'],
                                      ['r', 'q'],
                                      {'': '', 'r': 'race', 'q': 'qualifying'}),
                    CalendarCountdown(Calendar('https://www.google.com/calendar/ical/smcvrb4c50unt7gs59tli4kq9o%40group.calendar.google.com/public/basic.ics'),
                                      ['@nextgp2', '@countdowngp2'],
                                      ['r', 'q'],
                                      {'': '', 'r': 'race', 'q': 'qualifying'}),
                    CalendarCountdown(Calendar('https://www.google.com/calendar/ical/dc71ef6p5csp8i8gu4vai0h5mg%40group.calendar.google.com/public/basic.ics'),
                                      ['@nextgp3', '@countdowngp3'],
                                      ['r', 'q'],
                                      {'': '', 'r': 'race', 'q': 'qualifying'})]

if config.has_option('Brain', 'dynamic_command_aliases_file'):
    with open(config.get('Brain', 'dynamic_command_aliases_file'), 'r') as f:
        for line in f:
            command,aliases = line.split(':', 1)
            command = command.strip().lower()
            aliases = [a.strip() for a in aliases.split(',')]
            for c in dynamic_commands:
                if command in c.keywords:
                    c.keywords.extend([a for a in aliases if a not in c.keywords])

markov = MarkovBrain(brain_file, chain_length, max_words)

#
# Begin actual code
#

def ignore(user):
    if user in ignore_nicks:
        return True
    return False

def pick_modifier(modifiers, str):
    for modifier in modifiers:
        if str.startswith(modifier):
            return modifier
    return ''

class sadfaceBot(irc.IRCClient):
    realname = realname
    username = username
    userinfo = userinfo
    versionName = versionName
    erroneousNickFallback = erroneousNickFallback
    password = password

    def _get_nickname(self):
        return self.factory.nickname
    nickname = property(_get_nickname)

    def joinChannel(self, channel):
        self.join(channel)

    def signedOn(self):
        if self.password != '':
            self.msg('nickserv', 'identify ' + self.password)

        for chan in self.factory.channels:
            self.joinChannel(chan)

        for chan in self.factory.listen_only_channels:
            self.joinChannel(chan)

    def joined(self, channel):
        print "Joined %s as %s." % (channel,self.nickname)

    def listen_only(self, channel):
        return channel.lower() in self.factory.listen_only_channels

    def receiver(self, user_nick, channel):
        return user_nick if channel.lower() == self.factory.nickname.lower() else channel

    def send(self, user_nick, channel, msg):
        self.msg(self.receiver(user_nick, channel), msg)

    def handle_dynamic(self, user_nick, channel, msg, keyword, modifiers, response, check_only):
        prefix = user_nick + ': '
        if msg.startswith(keyword):
            if not check_only:
                self.send(user_nick, channel, prefix + response(pick_modifier(modifiers, msg[len(keyword):])))
            return True
        return False

    def handle_command(self, user_nick, channel, msg, check_only = False):
        prefix = user_nick + ': '
        # Check if this is a simple static command
        for command,response in self.factory.static_commands:
            if msg.startswith(command):
                if not check_only:
                    self.send(user_nick, channel, prefix + response)
                return True

        for command_index,keyword_index in self.factory.dynamic_command_keyword_order:
            command = self.factory.dynamic_commands[command_index]
            if self.handle_dynamic(user_nick, channel, msg, command.keywords[keyword_index], command.modifiers, command.response, check_only):
                return True

        return False

    def privmsg(self, user, channel, msg):
# TODO
# make the privmsg class run:
#    check for user
#    check for reply
#        check for self.

        user_nick = user.split('!', 1)[0]
        # Prints the message to stdout
        print channel + " <" + user_nick + "> " + msg
        if not user:
            print "NON-USER:" + msg
            return

        # Ignores the message if the person is in the ignore list
        if ignore(user_nick):
            print "\t" + "Ignored message from <" + user_nick + "> at: " + strftime("%a, %d %b %Y %H:%M:%S %Z", localtime()) # Time method from http://stackoverflow.com/a/415527
            return

        if reply == '0' or self.listen_only(channel):
            print msg
            if not self.handle_command(user_nick, channel, msg.lower(), True):
                self.factory.markov.add_to_brain(re.compile(self.nickname + "[:,]* ?", re.I).sub('', msg))
            return

        if self.handle_command(user_nick, channel, msg.lower()):
            return

        if self.factory.quiet_hours_calendar.in_event():
            print "No response during quiet hours. Message: " + msg
            self.factory.markov.add_to_brain(re.compile(self.nickname + "[:,]* ?", re.I).sub('', msg))
            return

        # Replies to messages containing the bot's name
        if reply == '1':
            if self.nickname in msg:
                time.sleep(0.2) #to prevent flooding
                msg = re.compile(self.nickname + "[:,]* ?", re.I).sub('', msg)
                prefix = "%s: " % (user_nick, )
            else:
                prefix = ''

            self.factory.markov.add_to_brain(msg)
            print "\t" + msg #prints to stdout what sadface added to brain
            if prefix or (channel == self.nickname or random.random() <= self.factory.channels[channel]):
                sentence = self.factory.markov.generate_sentence(msg)
                if sentence:
                    self.msg(self.receiver(user_nick, channel), prefix + sentence)
                    print ">" + "\t" + sentence #prints to stdout what sadface said
            return

        # Replies to messages starting with the bot's name.
        if reply == '2':
            if msg.startswith(self.nickname): #matches nickname, mecause of Noxz
                time.sleep(0.2) #to prevent flooding
                msg = re.compile(self.nickname + "[:,]* ?", re.I).sub('', msg)
                prefix = "%s: " % (user_nick, )
            else:
                msg = re.compile(self.nickname + "[:,]* ?", re.I).sub('', msg)
                prefix = ''

            self.factory.markov.add_to_brain(msg)
            print "\t" + msg #prints to stdout what sadface added to brain
            if prefix or (channel == self.nickname or random.random() <= self.factory.channels[channel]):
                sentence = self.factory.markov.generate_sentence(msg)
                if sentence:
                    self.msg(self.receiver(user_nick, channel), prefix + sentence)
                    print ">" + "\t" + sentence #prints to stdout what sadface said
            return

#
# Idea for later implementation
# To limit who gets to talk to the bot, the talker's nickname is self.nickname
# if user in allowed_people:
#    Check that user is okayed with nickserv
#    pass
# else:
#    fail
#

class sadfaceBotFactory(protocol.ClientFactory):
    protocol = sadfaceBot

    def __init__(self, markov, channels, listen_only_channels, nickname, static_commands, dynamic_commands, quiet_hours_calendar):
        self.markov = markov
        self.channels = channels
        self.listen_only_channels = listen_only_channels
        self.nickname = nickname
        self.static_commands = static_commands
        self.dynamic_commands = dynamic_commands
        self.quiet_hours_calendar = quiet_hours_calendar

        # Holds the order of matching for keywords from longest in length to shortest. This prevents collisions of substring keywords.
        # Each array element is (index into dynamic_command, index into that specific command's keywords)
        self.dynamic_command_keyword_order = []
        for command_index, command_object in enumerate(self.dynamic_commands):
            for keyword_index, keyword in enumerate(command_object.keywords):
                self.dynamic_command_keyword_order.append((command_index, keyword_index))
        self.dynamic_command_keyword_order.sort(key=lambda x: len(self.dynamic_commands[x[0]].keywords[x[1]]), reverse=True)

    def clientConnectionLost(self, connector, reason):
        print "Lost connection (%s), reconnecting." % (reason,)
        connector.connect()

    def clientConnectionFailed(self, connector, reason):
        print "Could not connect: %s" % (reason,)
        quit()
#
#    We begin!
#

if __name__ == "__main__":
    config_file = sys.argv[1]
    if config_file == False:
        print "Please specify a valid config file in the arguments."
        print "Example:"
        print "python sadface.py default.ini"

    reactor.connectTCP(host, port, sadfaceBotFactory(markov, channels, listen_only_channels, nickname, static_commands, dynamic_commands, formula1_calendar))
    reactor.run()

    markov.dump_new_brain_lines()