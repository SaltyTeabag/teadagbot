import string
from collections import OrderedDict

from utilities.calendar import Calendar
from commands.commandhandler import CommandHandler

class CalendarCountdown(object):
    def __init__(self, calendar, filters):
        self.calendar = calendar if type(calendar) is Calendar else Calendar(calendar)
        self.filters = OrderedDict(sorted(filters.iteritems(), reverse=True, key=lambda t: len(t[0])))

    def get_filter(self, str):
        for f in self.filters:
            if str.startswith(f):
                return self.filters[f]
        return ''

    def get_response(self, param_str):
        event = self.calendar.closest_event(self.get_filter(param_str))
        if not event:
            return 'No future event found'

        delta = event[1]
        hours, remainder = divmod(delta.seconds, 3600)
        minutes, seconds = divmod(remainder, 60)
        response = '%s starting in %d %s %02d:%02d:%02d' % (event[0].summary, delta.days, 'days' if delta.days != 1 else 'day', hours, minutes, seconds)
        return response.encode('utf-8')

class CalendarCountdownPool(CommandHandler):
    def __init__(self, json_config):
        self.calendars = {}
        self.default_id = None
        for config in json_config:
            calendar = CalendarCountdown(config['calendar_url'], {k.lower(): v.lower() for k,v in config['filters'].iteritems()})
            for id in config['identifiers']:
                self.calendars[id.lower()] = calendar

            if 'default_id' in config and config['default_id']:
                self.default_id = config['identifiers'][0].lower()

        self.calendars = OrderedDict(sorted(self.calendars.iteritems(), reverse=True, key=lambda t: len(t[0])))

    def choose_calendar_id(self, param_str, chan):
        for id in self.calendars:
            if param_str.startswith(id):
                return (id, param_str[len(id):])

        if chan[1:] in self.calendars:
            return (chan[1:], param_str)

        return (self.default_id, param_str)

    def get_help(self):
        return ''

    # param_str should be lowercase
    def get_response(self, param_str, _, chan):
        id,filter = self.choose_calendar_id(param_str, chan)
        if not id:
            return 'Bad calendar countdown config. Check your JSON.'.encode('utf-8')

        return self.calendars[id].get_response(filter)

command_handler_properties = (CalendarCountdownPool, ['@next'], False)