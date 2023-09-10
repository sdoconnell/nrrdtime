#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""nrrdtime
Version:  0.0.2
Author:   Sean O'Connell <sean@sdoconnell.net>
License:  MIT
Homepage: https://github.com/sdoconnell/nrrdtime
About:
A terminal-based time tracking tool with local file-based storage.

usage: nrrdtime [-h] [-c <file>] for more help: nrrdtime <command> -h ...

Terminal-based time tracking for nerds.

commands:
  (for more help: nrrdtime <command> -h)
    config              edit configuration file
    delete (rm)         delete an entry file
    edit                edit a time entry file (uses $EDITOR)
    info                show info about a time entry
    list (ls)           list running and/or paused entries
    modify (mod)        modify a time entry
    notes               add/update notes on a time entry (uses $EDITOR)
    pause               pause the clock on an entry
    query               search time entries with structured text output
    report              print a time report
    resume              resume the clock on an entry
    shell               interactive shell
    start               create a new time entry
    stop                stop the clock on an entry
    unset               clear a field from a specified time entry
    version             show version info

optional arguments:
  -h, --help            show this help message and exit
  -c <file>, --config <file>
                        config file


Copyright © 2021 Sean O'Connell

Permission is hereby granted, free of charge, to any person obtaining a copy
of this software and associated documentation files (the "Software"), to deal
in the Software without restriction, including without limitation the rights
to use, copy, modify, merge, publish, distribute, sublicense, and/or sell
copies of the Software, and to permit persons to whom the Software is
furnished to do so, subject to the following conditions:

The above copyright notice and this permission notice shall be included in all
copies or substantial portions of the Software.

THE SOFTWARE IS PROVIDED "AS IS", WITHOUT WARRANTY OF ANY KIND, EXPRESS OR
IMPLIED, INCLUDING BUT NOT LIMITED TO THE WARRANTIES OF MERCHANTABILITY,
FITNESS FOR A PARTICULAR PURPOSE AND NONINFRINGEMENT. IN NO EVENT SHALL THE
AUTHORS OR COPYRIGHT HOLDERS BE LIABLE FOR ANY CLAIM, DAMAGES OR OTHER
LIABILITY, WHETHER IN AN ACTION OF CONTRACT, TORT OR OTHERWISE, ARISING FROM,
OUT OF OR IN CONNECTION WITH THE SOFTWARE OR THE USE OR OTHER DEALINGS IN THE
SOFTWARE.

"""
import argparse
import calendar as modcalendar  # name too commonly used
import configparser
import json
import os
import random
import string
import subprocess
import sys
import tempfile
import uuid
from cmd import Cmd
from datetime import datetime, timedelta, date, timezone
from datetime import time as dttime

import tzlocal
import yaml
from dateutil import parser as dtparser
from rich import box
from rich.color import ColorParseError
from rich.console import Console
from rich.table import Table
from rich.text import Text
from rich.style import Style
from watchdog.events import FileSystemEventHandler
from watchdog.observers import Observer

APP_NAME = "nrrdtime"
APP_VERS = "0.0.2"
APP_COPYRIGHT = "Copyright © 2021 Sean O'Connell."
APP_LICENSE = "Released under MIT license."
DEFAULT_FIRST_WEEKDAY = 6
DEFAULT_DATA_DIR = f"$HOME/.local/share/{APP_NAME}"
DEFAULT_CONFIG_FILE = f"$HOME/.config/{APP_NAME}/config"
DEFAULT_ROUNDING_METHOD = None
DEFAULT_ROUNDING_INTERVAL = 1
DEFAULT_CONFIG = (
    "[main]\n"
    f"data_dir = {DEFAULT_DATA_DIR}\n"
    "# first day of week (0 = Mon, 6 = Sun)\n"
    f"first_weekday = {DEFAULT_FIRST_WEEKDAY}\n"
    "# rounding method can be either:\n"
    "# 1 - round time up\n"
    "# 2 - round time down\n"
    "# or empty for no rounding of time (default)\n"
    "#rounding_method =\n"
    "# the rounding interval can be one of:\n"
    "# 1 - 15m\n"
    "# 2 - 30m\n"
    "# 3 - 1h\n"
    "# use sensible rounding policies. Ex. rounding down\n"
    "# with a 1h interval will cause any entry of less than\n"
    "# an hour to show as 0m (maybe you want that? probably not).\n"
    "#rounding_interval = 1\n"
    "# show seconds (pointless if you use rounding btw)\n"
    "show_seconds = false\n"
    "\n"
    "[colors]\n"
    "disable_colors = false\n"
    "disable_bold = false\n"
    "# set to 'true' if your terminal pager supports color\n"
    "# output and you would like color output when using\n"
    "# the '--pager' ('-p') option\n"
    "color_pager = false\n"
    "# custom colors\n"
    "#title = blue\n"
    "#header = magenta\n"
    "#description = default\n"
    "#alias = bright_black\n"
    "#tags = cyan\n"
    "#label = white\n"
    "#date = green\n"
    "#time = bright_green\n"
    "#status_stopped = bright_red\n"
    "#status_running = green\n"
    "#status_paused = yellow\n"
    "#border = white\n"
    "\n"
    "[project_colors]\n"
    "#projectx = bright_blue\n"
    "#vegasbuild = bright_green\n"
)


class TimeEntries():
    """Performs time management operations.

    Attributes:
        config_file (str):  application config file.
        data_dir (str):     directory containing time entry files.
        dflt_config (str):  the default config if none is present.

    """
    def __init__(
            self,
            config_file,
            data_dir,
            dflt_config):
        """Initializes a TimeEntries() object."""
        self.config_file = config_file
        self.data_dir = data_dir
        self.config_dir = os.path.dirname(self.config_file)
        self.dflt_config = dflt_config
        self.interactive = False

        # default colors
        self.color_title = "bright_blue"
        self.color_header = "bright_black"
        self.color_description = "default"
        self.color_alias = "default"
        self.color_tags = "cyan"
        self.color_label = "white"
        self.color_date = "green"
        self.color_time = "cyan"
        self.color_status_stopped = "bright_red"
        self.color_status_running = "green"
        self.color_status_paused = "yellow"
        self.color_border = "white"
        self.color_bold = True
        self.color_pager = False
        self.project_colors = None
        self.color_enabled = True

        # default settings
        self.ltz = tzlocal.get_localzone()
        self.first_weekday = DEFAULT_FIRST_WEEKDAY
        self.rounding_method = DEFAULT_ROUNDING_METHOD
        self.rounding_interval = DEFAULT_ROUNDING_INTERVAL
        self.show_seconds = False

        # editor (required for some functions)
        self.editor = os.environ.get("EDITOR")

        # initial style definitions, these are updated after the config
        # file is parsed for custom colors
        self.style_title = None
        self.style_header = None
        self.style_border = None
        self.style_description = None
        self.style_alias = None
        self.style_tags = None
        self.style_label = None
        self.style_date = None
        self.style_time = None
        self.style_status_stopped = None
        self.style_status_paused = None
        self.style_status_running = None
        self.style_status_default = None

        self._default_config()
        self._parse_config()
        self._verify_data_dir()
        self._parse_files()

    def _alias_not_found(self, alias):
        """Report an invalid alias and exit or pass appropriately.

        Args:
            alias (str):    the invalid alias.

        """
        self._handle_error(f"Alias '{alias}' not found")

    def _calc_entry_time(self, stopwatch):
        """Calculate the total time for a time entry.

        Args:
            stopwatch (dict):   the stopwatch of stop and start times

        Returns:
            entry_time (list):  hours, minutes, and seconds

        """
        entry_time = []
        if stopwatch:
            hours = 0
            minutes = 0
            seconds = 0
            for entry in stopwatch:
                start = self._datetime_or_none(entry.get('start'))
                stop = self._datetime_or_none(entry.get('stop'))
                # for running time entries
                if not stop:
                    stop = datetime.now(tz=self.ltz)
                if start and stop:
                    duration = stop - start
                    seconds += duration.seconds
            # sanitize time
            while seconds > 59:
                seconds -= 60
                minutes += 1
            while minutes > 59:
                minutes -= 60
                hours += 1
            entry_time = [hours, minutes, seconds]
        return entry_time

    def _datetime_or_none(self, timestr):
        """Verify a datetime object or a datetime string in ISO format
        and return a datetime object or None.

        Args:
            timestr (str): a datetime formatted string.

        Returns:
            timeobj (datetime): a valid datetime object or None.

        """
        if isinstance(timestr, datetime):
            timeobj = timestr.astimezone(tz=self.ltz)
        else:
            try:
                timeobj = dtparser.parse(timestr).astimezone(tz=self.ltz)
            except (TypeError, ValueError, dtparser.ParserError):
                timeobj = None
        return timeobj

    def _default_config(self):
        """Create a default configuration directory and file if they
        do not already exist.
        """
        if not os.path.exists(self.config_file):
            try:
                os.makedirs(self.config_dir, exist_ok=True)
                with open(self.config_file, "w",
                          encoding="utf-8") as config_file:
                    config_file.write(self.dflt_config)
            except IOError:
                self._error_exit(
                    "Config file doesn't exist "
                    "and can't be created.")

    @staticmethod
    def _error_exit(errormsg):
        """Print an error message and exit with a status of 1

        Args:
            errormsg (str): the error message to display.

        """
        print(f'ERROR: {errormsg}.')
        sys.exit(1)

    @staticmethod
    def _error_pass(errormsg):
        """Print an error message but don't exit.

        Args:
            errormsg (str): the error message to display.

        """
        print(f'ERROR: {errormsg}.')

    def _format_timestr(self, hours, minutes, seconds):
        """Calculate hours, minutes, and seconds and return a formatted
        string (XhYmZs or XhYm).

        Args:
            hours (int):    time hours
            minutes (int):  time minutes
            seconds (int):  time seconds

        Returns:
            timestr (str):  the formatted string

        """
        timeobj = dttime(hours, minutes, seconds)
        if self.show_seconds:
            timestr = timeobj.strftime("%H:%M:%S")
        else:
            timestr = timeobj.strftime("%H:%M")
        return timestr

    @staticmethod
    def _format_timestamp(timeobj, pretty=False):
        """Convert a datetime obj to a string.

        Args:
            timeobj (datetime): a datetime object.
            pretty (bool):      return a pretty formatted string.

        Returns:
            timestamp (str): "%Y-%m-%d %H:%M:%S" or "%Y-%m-%d[ %H:%M]".

        """
        if pretty:
            if timeobj.strftime("%H:%M") == "00:00":
                timestamp = timeobj.strftime("%Y-%m-%d")
            else:
                timestamp = timeobj.strftime("%Y-%m-%d %H:%M")
        else:
            timestamp = timeobj.strftime("%Y-%m-%d %H:%M:%S")
        return timestamp

    def _gen_alias(self):
        """Generates a new alias and check for collisions.

        Returns:
            alias (str):    a randomly-generated alias.

        """
        aliases = self._get_aliases()
        chars = string.ascii_lowercase + string.digits
        while True:
            alias = ''.join(random.choice(chars) for x in range(4))
            if alias not in aliases:
                break
        return alias

    def _get_aliases(self):
        """Generates a list of all time entry aliases.

        Returns:
            aliases (list): the list of all time entry aliases.

        """
        aliases = []
        for entry in self.time_entries:
            alias = self.time_entries[entry].get('alias')
            if alias:
                aliases.append(alias.lower())
        return aliases

    def _handle_error(self, msg):
        """Reports an error message and conditionally handles error exit
        or notification.

        Args:
            msg (str):  the error message.

        """
        if self.interactive:
            self._error_pass(msg)
        else:
            self._error_exit(msg)

    def _is_paused(self, uid):
        """Determine if a time entry is currently paused.

        Args:
            uid (str):    the time entry uid.

        Returns:
            paused (bool):  the time entry is paused.

        """
        time_entry = self._parse_time_entry(uid)
        status = time_entry['status']
        stopwatch = time_entry['stopwatch']
        # check both the status and the stopwatch entries
        paused = True
        if status != 'paused':
            paused = False
        for entry in stopwatch:
            start = entry.get('start')
            stop = entry.get('stop')
            if not (start and stop):
                paused = False
        return paused

    def _is_running(self, uid):
        """Determine if a time entry is currently running.

        Args:
            uid (str):    the time entry uid.

        Returns:
            running (bool):  the time entry is running.

        """
        time_entry = self._parse_time_entry(uid)
        status = time_entry['status']
        stopwatch = time_entry['stopwatch']
        # check both the status and the stopwatch entries
        running = True
        if status != 'running':
            running = False
        for entry in stopwatch:
            start = entry.get('start')
            stop = entry.get('stop')
            if entry == stopwatch[-1] and start and stop is not None:
                running = False
        return running

    def _make_project_style(self, project):
        """Create a style for a project label based on values in
        self.project_colors.

        Args:
            project (str): the project name to stylize.\

        Returns:
            this_style (obj): Rich Style() object.

        """
        color = self.project_colors.get(project)
        if color and self.color_enabled:
            try:
                this_style = Style(color=color)
            except ColorParseError:
                this_style = Style(color="default")
        else:
            this_style = Style(color="default")

        return this_style

    def _make_status_style(self, status):
        """Return a style based on the entry status.

        Args:
            status (str):   the entry status.

        Returns:
            style (obj):   the Style() object.

        """
        status = status.lower()

        if status == "running":
            style = self.style_status_running
        elif status == "paused":
            style = self.style_status_paused
        elif status == "stopped":
            style = self.style_status_stopped
        else:
            style = self.style_status_default
        return style

    def _parse_config(self):
        """Read and parse the configuration file."""
        config = configparser.ConfigParser()
        if os.path.isfile(self.config_file):
            try:
                config.read(self.config_file)
            except configparser.Error:
                self._error_exit("Error reading config file")

            if "main" in config:
                if config["main"].get("data_dir"):
                    self.data_dir = os.path.expandvars(
                        os.path.expanduser(
                            config["main"].get("data_dir")))
                # default first day of the week
                if config["main"].get("first_weekday"):
                    try:
                        self.first_weekday = int(
                                config["main"].get("first_weekday"))
                    except ValueError:
                        self.first_weekday = DEFAULT_FIRST_WEEKDAY
                # rounding method: 1 (up), 2 (down) or None
                if config["main"].get("rounding_method"):
                    try:
                        self.rounding_method = int(
                                config["main"].get("rounding_method"))
                    except ValueError:
                        self.rounding_method = DEFAULT_ROUNDING_METHOD
                    else:
                        if self.rounding_method not in range(1, 3):
                            self.rounding_method = DEFAULT_ROUNDING_METHOD
                # rounding interval: 1 (15m), 2 (30m) or 3 (1h)
                if config["main"].get("rounding_interval"):
                    try:
                        self.rounding_interval = int(
                                config["main"].get("rounding_interval"))
                    except ValueError:
                        self.rounding_interval = DEFAULT_ROUNDING_INTERVAL
                    else:
                        if self.rounding_interval not in range(1, 4):
                            self.rounding_interval = DEFAULT_ROUNDING_INTERVAL
                # show seconds in list() and report() (disabled by default)
                self.show_seconds = config["main"].getboolean(
                    "show_seconds", "False")

            def _apply_colors():
                """Try to apply custom colors and catch exceptions for
                invalid color names.
                """
                try:
                    self.style_title = Style(
                        color=self.color_title,
                        bold=self.color_bold)
                except ColorParseError:
                    pass
                try:
                    self.style_header = Style(
                        color=self.color_header,
                        bold=self.color_bold)
                except ColorParseError:
                    pass
                try:
                    self.style_border = Style(
                        color=self.color_border)
                except ColorParseError:
                    pass
                try:
                    self.style_description = Style(
                        color=self.color_description)
                except ColorParseError:
                    pass
                try:
                    self.style_alias = Style(
                        color=self.color_alias)
                except ColorParseError:
                    pass
                try:
                    self.style_tags = Style(
                        color=self.color_tags)
                except ColorParseError:
                    pass
                try:
                    self.style_label = Style(
                        color=self.color_label)
                except ColorParseError:
                    pass
                try:
                    self.style_date = Style(
                        color=self.color_date)
                except ColorParseError:
                    pass
                try:
                    self.style_time = Style(
                        color=self.color_time)
                except ColorParseError:
                    pass
                try:
                    self.style_status_stopped = Style(
                        color=self.color_status_stopped,
                        bold=self.color_bold)
                except ColorParseError:
                    pass
                try:
                    self.style_status_running = Style(
                        color=self.color_status_running,
                        bold=self.color_bold)
                except ColorParseError:
                    pass
                try:
                    self.style_status_paused = Style(
                        color=self.color_status_paused,
                        bold=self.color_bold)
                except ColorParseError:
                    pass
                try:
                    self.style_status_default = Style(
                        color="default")
                except ColorParseError:
                    pass

            # apply default colors
            _apply_colors()

            if "colors" in config:
                # custom colors
                self.color_title = (
                    config["colors"].get(
                        "title", "bright_blue"))
                self.color_header = (
                    config["colors"].get(
                        "header", "bright_black"))
                self.color_description = (
                    config["colors"].get(
                        "description", "default"))
                self.color_alias = (
                    config["colors"].get(
                        "alias", "default"))
                self.color_tags = (
                    config["colors"].get(
                        "tags", "cyan"))
                self.color_label = (
                    config["colors"].get(
                        "label", "white"))
                self.color_date = (
                    config["colors"].get(
                        "date", "green"))
                self.color_time = (
                    config["colors"].get(
                        "time", "cyan"))
                self.color_status_stopped = (
                    config["colors"].get(
                        "status_stopped", "bright_red"))
                self.color_status_running = (
                    config["colors"].get(
                        "status_running", "green"))
                self.color_status_paused = (
                    config["colors"].get(
                        "status_paused", "yellow"))
                self.color_border = (
                    config["colors"].get(
                        "border", "white"))

                # color paging (disabled by default)
                self.color_pager = config["colors"].getboolean(
                    "color_pager", "False")

                # disable colors
                if bool(config["colors"].getboolean("disable_colors")):
                    self.color_enabled = False
                    self.color_title = "default"
                    self.color_header = "default"
                    self.color_description = "default"
                    self.color_alias = "default"
                    self.color_tags = "default"
                    self.color_label = "default"
                    self.color_date = "default"
                    self.color_time = "default"
                    self.color_status_stopped = "default"
                    self.color_status_running = "default"
                    self.color_status_paused = "default"
                    self.color_border = "default"

                # disable bold
                if bool(config["colors"].getboolean("disable_bold")):
                    self.color_bold = False

                # try to apply requested custom colors
                _apply_colors()

            if "project_colors" in config:
                project_colors = config["project_colors"]
                self.project_colors = {}
                for proj in project_colors:
                    self.project_colors[proj] = project_colors.get(proj)
        else:
            self._error_exit("Config file not found")

    def _parse_files(self):
        """ Read time entry files from `data_dir` and parse time entry
        data into `time_entries`.

        Returns:
            time_entries (dict):    parsed data from each time entry file

        """
        this_entry_files = {}
        this_entries = {}
        aliases = {}

        with os.scandir(self.data_dir) as entries:
            for entry in entries:
                if entry.name.endswith('.yml') and entry.is_file():
                    fullpath = entry.path
                    data = None
                    try:
                        with open(fullpath, "r",
                                  encoding="utf-8") as entry_file:
                            data = yaml.safe_load(entry_file)
                    except (OSError, IOError, yaml.YAMLError):
                        self._error_pass(
                            f"failure reading or parsing {fullpath} "
                            "- SKIPPING")
                    if data:
                        uid = None
                        time_entry = data.get("entry")
                        if time_entry:
                            uid = time_entry.get("uid")
                            alias = time_entry.get("alias")
                            add_entry = True
                            if uid:
                                # duplicate UID detection
                                dupid = this_entry_files.get(uid)
                                if dupid:
                                    self._error_pass(
                                        "duplicate UID detected:\n"
                                        f"  {uid}\n"
                                        f"  {dupid}\n"
                                        f"  {fullpath}\n"
                                        f"SKIPPING {fullpath}")
                                    add_entry = False
                            if alias:
                                # duplicate alias detection
                                dupalias = aliases.get(alias)
                                if dupalias:
                                    self._error_pass(
                                        "duplicate alias detected:\n"
                                        f"  {alias}\n"
                                        f"  {dupalias}\n"
                                        f"  {fullpath}\n"
                                        f"SKIPPING {fullpath}")
                                    add_entry = False
                            if add_entry:
                                if alias and uid:
                                    this_entries[uid] = time_entry
                                    this_entry_files[uid] = fullpath
                                    aliases[alias] = fullpath
                                else:
                                    self._error_pass(
                                        "no uid and/or alias param "
                                        f"in {fullpath} - SKIPPING")
                        else:
                            self._error_pass(
                                f"no data in {fullpath} - SKIPPING")
        self.time_entries = this_entries.copy()
        self.time_entry_files = this_entry_files.copy()

    def _parse_time_entry(self, uid):
        """Parse a time entry and return values for entry parameters.

        Args:
            uid (str): the UUID of the time entry to parse.

        Returns:
            time_entry (dict):    the time entry parameters.

        """
        time_entry = {}
        time_entry['uid'] = self.time_entries[uid].get('uid')

        time_entry['created'] = self.time_entries[uid].get('created')
        if time_entry['created']:
            time_entry['created'] = self._datetime_or_none(
                    time_entry['created'])

        time_entry['updated'] = self.time_entries[uid].get('updated')
        if time_entry['updated']:
            time_entry['updated'] = self._datetime_or_none(
                    time_entry['updated'])

        time_entry['started'] = self.time_entries[uid].get('started')
        if time_entry['started']:
            time_entry['started'] = self._datetime_or_none(
                    time_entry['started'])

        time_entry['completed'] = self.time_entries[uid].get('completed')
        if time_entry['completed']:
            time_entry['completed'] = self._datetime_or_none(
                    time_entry['completed'])

        time_entry['alias'] = self.time_entries[uid].get('alias')
        if time_entry['alias']:
            time_entry['alias'] = time_entry['alias'].lower()

        time_entry['description'] = self.time_entries[uid].get('description')
        time_entry['location'] = self.time_entries[uid].get('location')

        time_entry['project'] = self.time_entries[uid].get('project')
        if time_entry['project']:
            time_entry['project'] = time_entry['project'].lower()

        time_entry['tags'] = self.time_entries[uid].get('tags')

        time_entry['status'] = self.time_entries[uid].get('status')
        if time_entry['status']:
            time_entry['status'] = time_entry['status'].lower()

        time_entry['stopwatch'] = self.time_entries[uid].get('stopwatch')

        time_entry['notes'] = self.time_entries[uid].get('notes')

        return time_entry

    def _perform_search(self, term):
        """Parses a search term and returns a list of matching time entries.
        A 'term' can consist of two parts: 'search' and 'exclude'. The
        operator '%' separates the two parts. The 'exclude' part is
        optional.
        The 'search' and 'exclude' terms use the same syntax but differ
        in one noteable way:
          - 'search' is parsed as AND. All parameters must match to
        return a time entry record. Note that within a parameter the '+'
        operator is still an OR.
          - 'exclude' is parsed as OR. Any parameters that match will
        exclude a time entry record.

        Args:
            term (str):     the search term to parse.

        Returns:
            this_time_entries (list): the time entries matching the
        search criteria.

        """
        # helper lambda functions for parsing search and exclude strings
        def _parse_dt_range(timestr):
            """Parses a datetime range expression and returns start and
            end datetime objects.

            Args:
                timestr (str):  the datetime range string provided.

            Returns:
                begin (obj):    a valid datetime object.
                end (obj):      a valid datetime object.

            """
            now = datetime.now(tz=self.ltz)
            origin = datetime(1969, 1, 1, 0, 0, 0, tzinfo=timezone.utc)
            if timestr.startswith("~"):
                begin = origin
                end = self._datetime_or_none(
                          timestr.replace("~", ""))
            elif timestr.endswith("~"):
                begin = self._datetime_or_none(
                            timestr.replace("~", ""))
                end = now
            elif "~" in timestr:
                times = timestr.split("~")
                begin = self._datetime_or_none(
                            times[0].strip())
                end = self._datetime_or_none(
                            times[1].strip())
            else:
                begin = self._datetime_or_none(timestr)
                end = self._datetime_or_none(timestr)
            # return a valid range, regardless
            # if the input values were bad, we'll just ignore them and
            # match all timestamps 1969-01-01 to present.
            if not begin:
                begin = origin
            if not end:
                end = now
            # in the case that an end date was provided without a time,
            # set the time to the last second of the date to match any
            # time in that day.
            elif end.hour == 0 and end.minute == 0:
                end = end.replace(hour=23, minute=59, second=59)
            return begin, end

        # if the exclusion operator is in the provided search term then
        # split the term into two components: search and exclude
        # otherwise, treat it as just a search term alone.
        if "%" in term:
            term = term.split("%")
            searchterm = str(term[0]).lower()
            excludeterm = str(term[1]).lower()
        else:
            searchterm = str(term).lower()
            excludeterm = None

        valid_criteria = [
            "uid=",
            "description=",
            "project=",
            "alias=",
            "tags=",
            "status=",
            "started=",
            "completed=",
            "notes="
        ]
        # parse the search term into a dict
        if searchterm:
            if searchterm == 'any':
                search = None
            elif not any(x in searchterm for x in valid_criteria):
                # treat this as a simple description search
                search = {}
                search['description'] = searchterm.strip()
            else:
                try:
                    search = dict((k.strip(), v.strip())
                                  for k, v in (item.split('=')
                                  for item in searchterm.split(',')))
                except ValueError:
                    msg = "invalid search expression"
                    if not self.interactive:
                        self._error_exit(msg)
                    else:
                        self._error_pass(msg)
                        return
        else:
            search = None

        # parse the exclude term into a dict
        if excludeterm:
            if not any(x in excludeterm for x in valid_criteria):
                # treat this as a simple description search
                exclude = {}
                exclude['description'] = excludeterm.strip()
            else:
                try:
                    exclude = dict((k.strip(), v.strip())
                                   for k, v in (item.split('=')
                                   for item in excludeterm.split(',')))
                except ValueError:
                    msg = "invalid exclude expression"
                    if not self.interactive:
                        self._error_exit(msg)
                    else:
                        self._error_pass(msg)
                        return
        else:
            exclude = None

        this_time_entries = []
        for uid in self.time_entries:
            this_time_entries.append(uid)
        exclude_list = []

        if exclude:
            x_uid = exclude.get('uid')
            x_alias = exclude.get('alias')
            x_description = exclude.get('description')
            x_project = exclude.get('project')
            x_tags = exclude.get('tags')
            if x_tags:
                x_tags = x_tags.split('+')
            x_status = exclude.get('status')
            if x_status:
                x_status = x_status.split('+')
            x_status = exclude.get('status')
            x_started = exclude.get('started')
            x_completed = exclude.get('completed')
            x_notes = exclude.get('notes')

            for uid in this_time_entries:
                time_entry = self._parse_time_entry(uid)
                remove = False
                if x_uid:
                    if x_uid == uid:
                        remove = True
                if x_alias:
                    if time_entry['alias']:
                        if x_alias == time_entry['alias']:
                            remove = True
                if x_description:
                    if time_entry['description']:
                        if x_description in time_entry['description']:
                            remove = True
                if x_project:
                    if time_entry['project']:
                        if x_project in time_entry['project']:
                            remove = True
                if x_tags:
                    if time_entry['tags']:
                        for tag in x_tags:
                            if tag in time_entry['tags']:
                                remove = True
                if x_status:
                    if time_entry['status']:
                        for this_status in x_status:
                            if this_status == time_entry['status']:
                                remove = True
                if x_started:
                    if time_entry['started']:
                        begin, end = _parse_dt_range(x_started)
                        if begin <= time_entry['started'] <= end:
                            remove = True
                if x_completed:
                    if time_entry['completed']:
                        begin, end = _parse_dt_range(x_completed)
                        if begin <= time_entry['completed'] <= end:
                            remove = True
                if x_notes:
                    if time_entry['notes']:
                        if x_notes in time_entry['notes']:
                            remove = True

                if remove:
                    exclude_list.append(uid)

        # remove excluded time_entrys
        for uid in exclude_list:
            this_time_entries.remove(uid)

        not_match = []

        if search:
            s_uid = search.get('uid')
            s_alias = search.get('alias')
            s_description = search.get('description')
            s_project = search.get('project')
            s_tags = search.get('tags')
            if s_tags:
                s_tags = s_tags.split('+')
            s_status = search.get('status')
            if s_status:
                s_status = s_status.split('+')
            s_started = search.get('started')
            s_completed = search.get('completed')
            s_notes = search.get('notes')
            if s_notes:
                s_notes = s_notes.lower()

            for uid in this_time_entries:
                time_entry = self._parse_time_entry(uid)
                remove = False
                if s_uid:
                    if not s_uid == uid:
                        remove = True
                if s_alias:
                    if time_entry['alias']:
                        if not s_alias == time_entry['alias']:
                            remove = True
                    else:
                        remove = True
                if s_description:
                    if time_entry['description']:
                        if (s_description not in
                                time_entry['description'].lower()):
                            remove = True
                    else:
                        remove = True
                if s_project:
                    if time_entry['project']:
                        if (s_project not in
                                time_entry['project'].lower()):
                            remove = True
                    else:
                        remove = True
                if s_tags:
                    keep = False
                    if time_entry['tags']:
                        # searching for tags allows use of the '+' OR
                        # operator, so if we match any tag in the list
                        # then keep the entry
                        for tag in s_tags:
                            if tag in time_entry['tags']:
                                keep = True
                    if not keep:
                        remove = True
                if s_status:
                    keep = False
                    if time_entry['status']:
                        # searching for status allows use of the '+' OR
                        # operator, so if we match any status in the
                        # list then keep the entry
                        for this_status in s_status:
                            if this_status == time_entry['status']:
                                keep = True
                    if not keep:
                        remove = True
                if s_started:
                    if time_entry['started']:
                        begin, end = _parse_dt_range(s_started)
                        if not begin <= time_entry['started'] <= end:
                            remove = True
                    else:
                        remove = True
                if s_completed:
                    if time_entry['completed']:
                        begin, end = _parse_dt_range(s_completed)
                        if not begin <= time_entry['completed'] <= end:
                            remove = True
                    else:
                        remove = True
                if s_notes:
                    if time_entry['notes']:
                        if s_notes not in time_entry['notes'].lower():
                            remove = True
                    else:
                        remove = True
                if remove:
                    not_match.append(uid)

        # remove the time_entrys that didn't match search criteria
        for uid in not_match:
            this_time_entries.remove(uid)

        return this_time_entries

    def _round_time(self, entry_time):
        """Using the defined rounding policy, round entry time and
        return a rounded entry time.

        Rounding method:
            1 - round time up
            2 - round time down
        Rounding interval:
            1 - 15m
            2 - 30m
            3 - 1h

        Args:
            entry_time (list):  hours, minutes, seconds.

        Returns:
            rounded_time (list): rounded hours, minutes, seconds.

        """
        hours = entry_time[0]
        minutes = entry_time[1]
        seconds = entry_time[2]
        if self.rounding_method:
            if self.rounding_method == 1:
                if seconds > 0:
                    minutes += 1
                    seconds = 0
                # in case 59 minutes and 59 seconds got rounded up
                while minutes > 59:
                    minutes -= 60
                    hours += 1
                if self.rounding_interval == 1:
                    # round up to the next 15 minute increment
                    if minutes > 45:
                        hours += 1
                        minutes = 0
                    elif 45 > minutes > 30:
                        minutes = 45
                    elif 30 > minutes > 15:
                        minutes = 30
                    elif 15 > minutes > 0:
                        minutes = 15
                elif self.rounding_interval == 2:
                    # round up to the next 30 minute increment
                    if minutes > 30:
                        hours += 1
                        minutes = 0
                    elif 30 > minutes > 0:
                        minutes = 30
                elif self.rounding_interval == 3:
                    # round up to the next hour
                    if minutes > 0:
                        hours += 1
                        minutes = 0
            elif self.rounding_method == 2:
                seconds = 0
                if self.rounding_interval == 1:
                    # round down to the last 15 minute increment
                    if minutes > 45:
                        minutes = 45
                    elif 45 > minutes > 30:
                        minutes = 30
                    elif 30 > minutes > 15:
                        minutes = 15
                    elif 15 > minutes > 0:
                        minutes = 0
                elif self.rounding_interval == 2:
                    # round down to the last 30 minute increment
                    if minutes > 30:
                        minutes = 30
                    elif 30 > minutes > 0:
                        minutes = 0
                elif self.rounding_interval == 3:
                    # round down to the last hour
                    minutes = 0
            rounded_time = [hours, minutes, seconds]
        else:
            rounded_time = entry_time.copy()
        return rounded_time

    def _sort_entries(self, entries, reverse=False):
        """Sort a list of time entries by completed date and return a
        sorted dict.

        Args:
            entries (list):   the entries to sort.
            reverse (bool): sort in reverse (optional).

        Returns:
            uids (list):    a sorted dict of entries.

        """
        fifouids = {}
        for uid in entries:
            sort = self.time_entries[uid].get('completed')
            fifouids[uid] = sort
        sortlist = sorted(
            fifouids.items(), key=lambda x: x[1], reverse=reverse
        )
        sortdict = dict(sortlist)
        uids = sortdict.keys()
        return uids

    def _uid_from_alias(self, alias):
        """Get the uid for a valid alias.

        Args:
            alias (str):    The alias of the time entry for which to find uid.

        Returns:
            uid (str or None): The uid that matches the submitted alias.

        """
        alias = alias.lower()
        uid = None
        for entry in self.time_entries:
            this_alias = self.time_entries[entry].get("alias")
            if this_alias:
                if this_alias == alias:
                    uid = entry
        return uid

    def _verify_data_dir(self):
        """Create the time entries data directory if it doesn't exist."""
        if not os.path.exists(self.data_dir):
            try:
                os.makedirs(self.data_dir)
            except IOError:
                self._error_exit(
                    f"{self.data_dir} doesn't exist "
                    "and can't be created")
        elif not os.path.isdir(self.data_dir):
            self._error_exit(f"{self.data_dir} is not a directory")
        elif not os.access(self.data_dir,
                           os.R_OK | os.W_OK | os.X_OK):
            self._error_exit(
                "You don't have read/write/execute permissions to "
                f"{self.data_dir}")

    @staticmethod
    def _write_yaml_file(data, filename):
        """Write YAML data to a file.

        Args:
            data (dict):    the structured data to write.
            filename (str): the location to write the data.

        """
        with open(filename, "w",
                  encoding="utf-8") as out_file:
            yaml.dump(
                data,
                out_file,
                default_flow_style=False,
                sort_keys=False)

    def delete(self, alias, force=False):
        """Delete a time entry identified by alias.

        Args:
            alias (str):    The alias of the entry to be deleted.

        """
        alias = alias.lower()
        uid = self._uid_from_alias(alias)
        if not uid:
            self._alias_not_found(alias)
        else:
            filename = self.time_entry_files.get(uid)
            if filename:
                if force:
                    confirm = "yes"
                else:
                    confirm = input(f"Delete '{alias}'? [yes/no]: ").lower()
                if confirm in ['yes', 'y']:
                    try:
                        os.remove(filename)
                    except OSError:
                        self._handle_error(f"failure deleting {filename}")
                    else:
                        print(f"Deleted event: {alias}")
                else:
                    print("Cancelled")
            else:
                self._handle_error(f"failed to find file for {alias}")

    def edit(self, alias):
        """Edit a time entry identified by alias (using $EDITOR).

        Args:
            alias (str):    The alias of the time entry to be edited.

        """
        if self.editor:
            alias = alias.lower()
            uid = self._uid_from_alias(alias)
            if not uid:
                self._alias_not_found(alias)
            else:
                filename = self.time_entry_files.get(uid)
                if filename:
                    try:
                        subprocess.run([self.editor, filename], check=True)
                    except subprocess.SubprocessError:
                        self._handle_error(
                            f"failure editing file {filename}")
                else:
                    self._handle_error(f"failed to find file for {uid}")
        else:
            self._handle_error("$EDITOR is required and not set")

    def edit_config(self):
        """Edit the config file (using $EDITOR) and then reload config."""
        if self.editor:
            try:
                subprocess.run(
                    [self.editor, self.config_file], check=True)
            except subprocess.SubprocessError:
                self._handle_error("failure editing config file")
            else:
                if self.interactive:
                    self._parse_config()
                    self.refresh()
        else:
            self._handle_error("$EDITOR is required and not set")

    def info(self, alias, pager=False):
        """Show information about a time entry.

        Args:
            alias (str):    the time entry to show.

        """
        if self.show_seconds:
            pretty = False
        else:
            pretty = True
        alias = alias.lower()
        uid = self._uid_from_alias(alias)
        if not uid:
            self._alias_not_found(alias)
        else:
            time_entry = self._parse_time_entry(uid)

            title = f"Entry info - {time_entry['alias']}"
            console = Console()
            summary_table = Table(
                title=title,
                title_style=self.style_title,
                title_justify="left",
                box=box.SIMPLE,
                show_header=False,
                show_lines=False,
                pad_edge=False,
                min_width=len(title),
                collapse_padding=False,
                padding=(0, 0, 0, 0))
            summary_table.add_column("field", style=self.style_label)
            summary_table.add_column("data")
            stopwatch = time_entry['stopwatch']
            uidtxt = Text(uid)
            summary_table.add_row("uid:", uidtxt)
            aliastxt = Text(time_entry['alias'])
            aliastxt.stylize(self.style_alias)
            summary_table.add_row("alias:", aliastxt)
            statustxt = Text(time_entry['status'])
            statustxt.stylize(self._make_status_style(time_entry['status']))
            summary_table.add_row("status:", statustxt)
            descriptiontxt = Text(time_entry['description'])
            descriptiontxt.stylize(self.style_description)
            summary_table.add_row("description:", descriptiontxt)
            if time_entry['project']:
                projecttxt = Text(time_entry['project'])
                projecttxt.stylize(
                    self._make_project_style(time_entry['project']))
                summary_table.add_row("project:", projecttxt)
            if time_entry['tags']:
                tags = time_entry['tags']
                if isinstance(tags, list):
                    tags.sort()
                    tags = ','.join(tags)
                tagstxt = Text(tags)
                tagstxt.stylize(self.style_tags)
                summary_table.add_row("tags:", tagstxt)

            if stopwatch:
                entry_time = self._calc_entry_time(stopwatch)
                if entry_time:
                    hours = entry_time[0]
                    minutes = entry_time[1]
                    seconds = entry_time[2]
                    timetxt = Text(
                            self._format_timestr(hours, minutes, seconds))
                    if self.rounding_method:
                        rounded_time = self._round_time(entry_time)
                        r_hrs = rounded_time[0]
                        r_min = rounded_time[1]
                        r_sec = rounded_time[2]
                        roundtxt = Text(
                            f"({self._format_timestr(r_hrs, r_min, r_sec)})")
                    else:
                        roundtxt = Text("")
                    timetxt.stylize(self.style_time)
                    roundtxt.stylize(self.style_time)
                    timeline = Text.assemble(timetxt, " ", roundtxt)
                    summary_table.add_row("time:", timeline)

            console = Console()
            history_table = Table(
                title='History',
                title_style=self.style_title,
                title_justify="left",
                box=box.SIMPLE,
                show_header=False,
                show_lines=False,
                pad_edge=False,
                collapse_padding=False,
                padding=(0, 0, 0, 0))
            history_table.add_column("field", style=self.style_label)
            history_table.add_column("data")
            # created
            if time_entry['created']:
                createdtxt = Text(self._format_timestamp(
                                    time_entry['created'], pretty=pretty))
                createdtxt.stylize(self.style_date)
                history_table.add_row("created:", createdtxt)
            # updated
            if time_entry['updated']:
                updatedtxt = Text(self._format_timestamp(
                                    time_entry['updated'], pretty=pretty))
                updatedtxt.stylize(self.style_date)
                history_table.add_row("updated:", updatedtxt)
            # started
            if time_entry['started']:
                startedtxt = Text(self._format_timestamp(
                                    time_entry['started'], pretty=pretty))
                startedtxt.stylize(self.style_date)
                history_table.add_row("started:", startedtxt)
            # completed
            if time_entry['completed']:
                completedtxt = Text(self._format_timestamp(
                                        time_entry['completed'],
                                        pretty=pretty))
                completedtxt.stylize(self.style_date)
                history_table.add_row("completed:", completedtxt)

            # clock
            if stopwatch:
                clock_table = Table(
                    title="Clock",
                    title_style=self.style_title,
                    title_justify="left",
                    box=box.SIMPLE,
                    show_header=False,
                    show_lines=False,
                    pad_edge=False,
                    collapse_padding=False,
                    padding=(0, 0, 0, 0))
                clock_table.add_column("index")
                clock_table.add_column("timestamps")
                for index, entry in enumerate(stopwatch):
                    index += 1
                    start = self._datetime_or_none(entry.get('start'))
                    if start:
                        start = self._format_timestamp(start, pretty=pretty)
                    stop = self._datetime_or_none(entry.get('stop'))
                    if stop:
                        stop = self._format_timestamp(stop, pretty=pretty)
                    else:
                        stop = ""
                    if start:
                        startlabel = Text("start: ")
                        stoplabel = Text("stop: ")
                        starttxt = Text(start)
                        stoptxt = Text(stop)
                        entry_table = Table(
                            title=None,
                            box=None,
                            show_header=False,
                            show_lines=False,
                            pad_edge=False,
                            collapse_padding=True,
                            padding=(0, 0, 0, 0))
                        entry_table.add_column(
                                "field", style=self.style_label)
                        entry_table.add_column(
                                "date", style=self.style_date)
                        entry_table.add_row(startlabel, starttxt)
                        entry_table.add_row(stoplabel, stoptxt)
                        clock_table.add_row(Text(f"[{index}]"), entry_table)
                        if entry != stopwatch[-1]:
                            clock_table.add_row("", "")

            # note
            if time_entry['notes']:
                notes_table = Table(
                    title="Notes",
                    title_style=self.style_title,
                    title_justify="left",
                    box=box.SIMPLE,
                    show_header=False,
                    show_lines=False,
                    pad_edge=False,
                    collapse_padding=False,
                    padding=(0, 0, 0, 0))
                notes_table.add_column("data")
                notestxt = Text(time_entry['notes'])
                notes_table.add_row(notestxt)

            layout = Table.grid()
            layout.add_column("single")
            layout.add_row("")
            layout.add_row(summary_table)
            layout.add_row(history_table)
            layout.add_row(clock_table)
            if 'notes_table' in locals():
                layout.add_row(notes_table)

            # render the output with a pager if --pager or -p
            if pager:
                if self.color_pager:
                    with console.pager(styles=True):
                        console.print(layout)
                else:
                    with console.pager():
                        console.print(layout)
            else:
                console.print(layout)

    def list(self, view, pager=False):
        """List running and/or paused time entries.

        Args:
            view (str): 'running', 'paused', or 'all'.
            pager (bool):   paginate output.

        """
        view = view.lower()
        if view == 'running':
            this_entries = self._perform_search('status=running')
        elif view == 'paused':
            this_entries = self._perform_search('status=paused')
        elif view == 'all':
            this_entries = self._perform_search('status=running+paused')
        else:
            self._handle_error(
                "invalid view. use: 'running', 'paused' or 'all'")
            if self.interactive:
                return
        console = Console()
        title = f"Time entries - {view}"
        # table
        entry_table = Table(
            title=title,
            title_style=self.style_title,
            title_justify="left",
            header_style=self.style_header,
            border_style=self.style_border,
            box=box.SIMPLE,
            show_header=True,
            show_lines=False,
            pad_edge=False,
            min_width=len(title),
            collapse_padding=False,
            padding=(0, 1, 0, 1))
        entry_table.add_column("alias", style=self.style_alias)
        entry_table.add_column("status")
        entry_table.add_column("time", style=self.style_time)
        entry_table.add_column("description", style=self.style_description)
        entry_table.add_column("project")
        entry_table.add_column("tags", style=self.style_tags)
        for entry in this_entries:
            time_entry = self._parse_time_entry(entry)
            alias = time_entry['alias']
            description = time_entry['description']
            project = time_entry['project']
            if project:
                projecttxt = Text(project)
                projecttxt.stylize(self._make_project_style(project))
            else:
                projecttxt = ""
            tags = time_entry['tags']
            status = time_entry['status']
            statustxt = Text(status)
            statustxt.stylize(self._make_status_style(status))
            if tags:
                tags = ','.join(tags)
            else:
                tags = ""
            stopwatch = time_entry['stopwatch']
            if stopwatch:
                entry_time = self._calc_entry_time(stopwatch)
                if entry_time:
                    hours = entry_time[0]
                    minutes = entry_time[1]
                    seconds = entry_time[2]
                    timestr = self._format_timestr(hours, minutes, seconds)
                else:
                    timestr = "--:--"
                entry_table.add_row(
                    alias,
                    statustxt,
                    timestr,
                    description,
                    projecttxt,
                    tags)
        if not this_entries:
            entry_table.show_header = False
            entry_table.add_row("None")
        layout = Table.grid()
        layout.add_column("single")
        layout.add_row("")
        layout.add_row(entry_table)

        # render the output with a pager if -p
        if pager:
            if self.color_pager:
                with console.pager(styles=True):
                    console.print(layout)
            else:
                with console.pager():
                    console.print(layout)
        else:
            console.print(layout)

    def modify(
            self,
            alias,
            new_completed=None,
            new_description=None,
            new_notes=None,
            new_project=None,
            new_started=None,
            new_status=None,
            new_tags=None,
            del_time=None,
            new_stopwatch=None):
        """Modify a time entry.

        Args:
            alias (str):           the time entry to modify.
            new_completed (str):   completed datetime.
            new_description (str): time entry description.
            new_notes (str):       notes on the time entry.
            new_project (str):     the associated project for the entry.
            new_started (str):     the started datetime.
            new_status (str):      'running', 'paused', or 'stopped'.
            new_tags (str):        tags for the time entry.
            del_time (list):       a list of one or more indexes to delete
        from the stopwatch.
            new_stopwatch (list):  a list of dicts of start/stop times. (for
        internal use only)

        """
        alias = alias.lower()
        uid = self._uid_from_alias(alias)

        def _remove_items(deletions, source):
            """Removes items (identified by index) from a list.
            Args:
                deletions (list):   the indexes to be deleted.
                source (list):    the list from which to remove.
            Returns:
                source (list):    the modified list.
            """
            rem_items = []
            for entry in deletions:
                try:
                    entry = int(entry)
                except ValueError:
                    pass
                else:
                    if 1 <= entry <= len(source):
                        entry -= 1
                        rem_items.append(source[entry])
            if rem_items:
                for item in rem_items:
                    source.remove(item)
            return source

        def _new_or_current(new, current):
            """Return a datetime obj for the new date (if existant and
            valid) or the current date (if existant) or None.

            Args:
                new (str):  the new timestring.
                current (obj): the current datetime object or None.

            Returns:
                updated (obj):  datetime or None.

            """
            if new:
                new = self._datetime_or_none(new)
                if new:
                    updated = new
                elif current:
                    updated = current
                else:
                    updated = None
            elif current:
                updated = current
            else:
                updated = None
            return updated

        if not uid:
            self._alias_not_found(alias)
        else:
            filename = self.time_entry_files.get(uid)
            time_entry = self._parse_time_entry(uid)

            if filename:
                created = time_entry['created']
                u_updated = datetime.now(tz=self.ltz)
                # started
                if new_started:
                    u_started = _new_or_current(
                            new_started, time_entry['started'])
                else:
                    u_started = time_entry['started']
                # completed
                if new_completed:
                    u_completed = _new_or_current(
                            new_completed, time_entry['completed'])
                else:
                    u_completed = time_entry['completed']
                # description
                u_description = new_description or time_entry['description']
                # project
                u_project = new_project or time_entry['project']
                # stopwatch
                u_stopwatch = new_stopwatch or time_entry['stopwatch']
                if del_time and u_stopwatch:
                    u_stopwatch = _remove_items(del_time, u_stopwatch)
                # tags
                if new_tags:
                    new_tags = new_tags.lower()
                    if new_tags.startswith('+'):
                        new_tags = new_tags[1:]
                        new_tags = new_tags.split(',')
                        if not time_entry['tags']:
                            tags = []
                        else:
                            tags = time_entry['tags'].copy()
                        for new_tag in new_tags:
                            if new_tag not in tags:
                                tags.append(new_tag)
                        if tags:
                            tags.sort()
                            u_tags = tags
                        else:
                            u_tags = None
                    elif new_tags.startswith('~'):
                        new_tags = new_tags[1:]
                        new_tags = new_tags.split(',')
                        if time_entry['tags']:
                            tags = time_entry['tags'].copy()
                            for new_tag in new_tags:
                                if new_tag in tags:
                                    tags.remove(new_tag)
                            if tags:
                                tags.sort()
                                u_tags = tags
                            else:
                                u_tags = None
                        else:
                            u_tags = None
                    else:
                        u_tags = new_tags.split(',')
                        u_tags.sort()
                else:
                    u_tags = time_entry['tags']
                # status
                if new_status:
                    u_status = new_status.lower()
                else:
                    u_status = time_entry['status']
                # notes
                if new_notes:
                    # the new note is functionally empty or is using a
                    # placeholder from notes() to clear the notes
                    if new_notes in [' ', ' \n', '\n']:
                        u_notes = None
                    else:
                        u_notes = new_notes
                else:
                    u_notes = time_entry['notes']

                data = {
                    "entry": {
                        "uid": uid,
                        "created": created,
                        "updated": u_updated,
                        "started": u_started,
                        "completed": u_completed,
                        "alias": alias,
                        "status": u_status,
                        "description": u_description,
                        "project": u_project,
                        "tags": u_tags,
                        "stopwatch": u_stopwatch,
                        "notes": u_notes
                    }
                }
                # write the updated file
                self._write_yaml_file(data, filename)

    def notes(self, alias):
        """Add or update notes on a time entry.

        Args:
            alias (str):        the time entry alias being updated.

        """
        if self.editor:
            alias = alias.lower()
            uid = self._uid_from_alias(alias)
            if not uid:
                self._alias_not_found(alias)
            else:
                time_entry = self._parse_time_entry(uid)
                if not time_entry['notes']:
                    fnotes = ""
                else:
                    fnotes = time_entry['notes']
                handle, abs_path = tempfile.mkstemp()
                with os.fdopen(handle, 'w') as temp_file:
                    temp_file.write(fnotes)

                # open the tempfile in $EDITOR and then update the time
                # entry with the new note
                try:
                    subprocess.run([self.editor, abs_path], check=True)
                    with open(abs_path, "r",
                              encoding="utf-8") as temp_file:
                        new_note = temp_file.read()
                except subprocess.SubprocessError:
                    msg = "failure editing note"
                    if not self.interactive:
                        self._error_exit(msg)
                    else:
                        self._error_pass(msg)
                        return
                else:
                    # notes were deleted entirely but if we set this to
                    # None then the note won't be updated. Set it to " "
                    # and then use special handling in modify()
                    if time_entry['notes'] and not new_note:
                        new_note = " "
                    self.modify(
                        alias=alias,
                        new_notes=new_note)
                    os.remove(abs_path)
        else:
            self._handle_error("$EDITOR is required and not set")

    def pause(self, alias):
        """Pause a currently running time entry.

        Args:
            alias (str):    the time entry to pause.

        """
        alias = alias.lower()
        uid = self._uid_from_alias(alias)
        if not uid:
            self._alias_not_found(alias)
        else:
            if self._is_running(uid):
                time_entry = self._parse_time_entry(uid)
                stopwatch = time_entry['stopwatch']
                now = datetime.now(tz=self.ltz)
                last_entry = stopwatch[-1]
                start = last_entry['start']
                stopwatch.pop(-1)
                new_entry = {}
                new_entry['start'] = start
                new_entry['stop'] = now
                stopwatch.append(new_entry)
                self.modify(
                    alias,
                    new_status='paused',
                    new_stopwatch=stopwatch)
                print(f"{alias} paused.")
            else:
                self._handle_error(f"{alias} is not running")

    def query(self, term, limit=None, json_output=False):
        """Perform a search for time entries that match a given criteria
        and print the results in plain, tab-delimited text or JSON.

        Args:
            term (str):     the criteria for which to search.
            limit (str):    filter output to specific fields.
            json_output (bool): output in JSON format.

        """
        result_entries = self._perform_search(term)
        if limit:
            limit = limit.split(',')
        entries_out = {}
        entries_out['entries'] = []
        text_out = ""
        if len(result_entries) > 0:
            for uid in result_entries:
                this_entry = {}
                time_entry = self._parse_time_entry(uid)
                created = time_entry["created"]
                updated = time_entry["updated"]
                description = time_entry["description"] or ""
                alias = time_entry["alias"] or ""
                tags = time_entry["tags"] or []
                status = time_entry["status"] or ""
                project = time_entry["project"] or ""
                stopwatch = time_entry["stopwatch"]
                computed_time = self._calc_entry_time(stopwatch)
                if created:
                    created = self._format_timestamp(created)
                if updated:
                    updated = self._format_timestamp(updated)
                if time_entry["started"]:
                    started = self._format_timestamp(
                        time_entry["started"], True)
                    j_started = self._format_timestamp(
                        time_entry["started"])
                else:
                    started = ""
                    j_started = None
                if time_entry["completed"]:
                    completed = self._format_timestamp(
                        time_entry["completed"], True)
                    j_completed = self._format_timestamp(
                        time_entry["completed"])
                else:
                    completed = ""
                    j_completed = None

                if limit:
                    output = ""
                    if "uid" in limit:
                        output += f"{uid}\t"
                    if "alias" in limit:
                        output += f"{alias}\t"
                    if "status" in limit:
                        output += f"{status}\t"
                    if "started" in limit:
                        output += f"{started}\t"
                    if "completed" in limit:
                        output += f"{completed}\t"
                    if "time" in limit:
                        output += f"{computed_time}\t"
                    if "description" in limit:
                        output += f"{description}\t"
                    if "project" in limit:
                        output += f"{project}\t"
                    if "tags" in limit:
                        output += f"{tags}\t"
                    if output.endswith('\t'):
                        output = output.rstrip(output[-1])
                    output = f"{output}\n"
                else:
                    output = (
                        f"{uid}\t"
                        f"{alias}\t"
                        f"{status}\t"
                        f"{started}\t"
                        f"{completed}\t"
                        f"{computed_time}\t"
                        f"{description}\t"
                        f"{project}\t"
                        f"{tags}\n"
                    )
                this_entry['uid'] = uid
                this_entry['created'] = created
                this_entry['updated'] = updated
                this_entry['started'] = j_started
                this_entry['completed'] = j_completed
                this_entry['time'] = computed_time
                this_entry['alias'] = time_entry['alias']
                this_entry['status'] = time_entry['status']
                this_entry['description'] = time_entry['description']
                this_entry['project'] = time_entry['project']
                this_entry['tags'] = time_entry['tags']
                this_entry['stopwatch'] = time_entry['stopwatch']
                this_entry['notes'] = time_entry['notes']
                entries_out['entries'].append(this_entry)
                text_out += f"{output}"
        if json_output:
            json_out = json.dumps(entries_out, indent=4)
            print(json_out)
        else:
            if text_out != "":
                print(text_out, end="")
            else:
                print("No results.")

    def refresh(self):
        """Public method to refresh data."""
        self._parse_files()

    def report(self, term, pager=False):
        """Produce a time report.

        Args:
            term (str): one of: today, yesterday, thisweek, lastweek,
        thismonth, lastmonth, thisyear, lastyear or a custom search.
            pager (bool): paginate output.

        """
        term = term.lower()
        cal = modcalendar.Calendar(firstweekday=self.first_weekday)
        today = date.today()
        today_wd = today.weekday()
        yesterday = today - timedelta(days=1)
        this_year = today.year
        last_year = this_year - 1
        this_month = today.month
        this_month_ld = modcalendar.monthrange(this_year, this_month)[1]
        last_month = this_month - 1
        if last_month == 0:
            last_month = 12
            lm_year = this_year - 1
        else:
            lm_year = this_year
        last_month_ld = modcalendar.monthrange(lm_year, last_month)[1]
        this_week_start = today - timedelta(
                days=list(cal.iterweekdays()).index(today_wd))
        this_week_end = this_week_start + timedelta(days=6)
        last_week_start = this_week_start - timedelta(days=7)
        last_week_end = last_week_start + timedelta(days=6)
        pretty_views = {
                'today': "today",
                'yesterday': "yesterday",
                'thisweek': "this week",
                'lastweek': "last week",
                'thismonth': "this month",
                'lastmonth': "last month",
                'thisyear': "this year",
                'lastyear': "last year"
        }
        if term == "today":
            todaystr = today.strftime("%Y-%m-%d")
            selected_entries = self._perform_search(
                    f"completed={todaystr}")
        elif term == "yesterday":
            yesterdaystr = yesterday.strftime("%Y-%m-%d")
            selected_entries = self._perform_search(
                    f"completed={yesterdaystr}")
        elif term == "thisweek":
            start = this_week_start.strftime("%Y-%m-%d")
            end = this_week_end.strftime("%Y-%m-%d")
            selected_entries = self._perform_search(
                    f"completed={start}~{end}")
        elif term == "lastweek":
            start = last_week_start.strftime("%Y-%m-%d")
            end = last_week_end.strftime("%Y-%m-%d")
            selected_entries = self._perform_search(
                    f"completed={start}~{end}")
        elif term == "thismonth":
            start = f"{this_year}-{this_month}-01"
            end = f"{this_year}-{this_month}-{this_month_ld}"
            selected_entries = self._perform_search(
                    f"completed={start}~{end}")
        elif term == "lastmonth":
            start = f"{lm_year}-{last_month}-01"
            end = f"{lm_year}-{last_month}-{last_month_ld}"
            selected_entries = self._perform_search(
                    f"completed={start}~{end}")
        elif term == "thisyear":
            start = f"{this_year}-01-01"
            end = f"{this_year}-12-31"
            selected_entries = self._perform_search(
                    f"completed={start}~{end}")
        elif term == "lastyear":
            start = f"{last_year}-01-01"
            end = f"{last_year}-12-31"
            selected_entries = self._perform_search(
                    f"completed={start}~{end}")
        else:
            selected_entries = self._perform_search(term)

        console = Console()
        viewstr = pretty_views.get(term, term)
        title = f"Time report - {viewstr}"
        # table
        report_table = Table(
            title=title,
            title_style=self.style_title,
            title_justify="left",
            header_style=self.style_header,
            border_style=self.style_border,
            box=box.SIMPLE,
            show_header=True,
            show_lines=False,
            pad_edge=False,
            min_width=len(title),
            collapse_padding=False,
            padding=(0, 1, 0, 1))
        report_table.add_column("alias", style=self.style_alias)
        report_table.add_column("completed", style=self.style_date)
        report_table.add_column("time", style=self.style_time)
        report_table.add_column("description", style=self.style_description)
        report_table.add_column("project")
        report_table.add_column("tags", style=self.style_tags)

        total_hours = 0
        total_minutes = 0
        total_seconds = 0
        if selected_entries:
            selected_entries = self._sort_entries(selected_entries)
            for entry in selected_entries:
                time_entry = self._parse_time_entry(entry)
                alias = time_entry['alias']
                if time_entry['completed']:
                    if self.show_seconds:
                        completed = self._format_timestamp(
                                time_entry['completed'], pretty=False)
                    else:
                        completed = self._format_timestamp(
                                time_entry['completed'], pretty=True)
                else:
                    completed = ""
                stopwatch = time_entry['stopwatch']
                if stopwatch:
                    entry_time = self._calc_entry_time(stopwatch)
                    if entry_time:
                        if self.rounding_method:
                            hours, minutes, seconds = self._round_time(
                                    entry_time)
                        else:
                            hours = entry_time[0]
                            minutes = entry_time[1]
                            seconds = entry_time[2]
                        timestr = self._format_timestr(
                                hours, minutes, seconds)
                        total_hours += hours
                        total_minutes += minutes
                        total_seconds += seconds
                    else:
                        if self.show_seconds:
                            timestr = "--:--:--"
                        else:
                            timestr = "--:--"
                else:
                    if self.show_seconds:
                        timestr = "--:--:--"
                    else:
                        timestr = "--:--"
                description = time_entry['description']
                project = time_entry['project']
                if project:
                    projecttxt = Text(project)
                    projecttxt.stylize(self._make_project_style(project))
                else:
                    projecttxt = ""
                tags = time_entry['tags']
                if tags:
                    if isinstance(tags, list):
                        tags.sort()
                        tags = ','.join(tags)
                else:
                    tags = ""
                report_table.add_row(
                    alias,
                    completed,
                    timestr,
                    description,
                    projecttxt,
                    tags)
            # sanitize total time
            while total_seconds > 59:
                total_seconds -= 60
                total_minutes += 1
            while total_minutes > 59:
                total_minutes -= 60
                total_hours += 1

            total_table = Table(
                title=None,
                box=box.SIMPLE,
                show_header=False,
                show_lines=False,
                pad_edge=False,
                collapse_padding=False,
                padding=(0, 1, 0, 1))
            total_table.add_column("total")

            total_time = self._format_timestr(
                    total_hours, total_minutes, total_seconds)
            total_label_txt = Text("total:")
            total_label_txt.stylize(self.style_label)
            total_time_txt = Text(total_time)
            total_time_txt.stylize(self.style_time)
            total_line = Text.assemble(
                    total_label_txt, " ", total_time_txt)
            total_table.add_row(total_line)
        else:
            report_table.show_header = False
            report_table.add_row("None")

        layout = Table.grid()
        layout.add_column("single")
        layout.add_row("")
        layout.add_row(report_table)
        if 'total_table' in locals():
            layout.add_row(total_table)

        # render the output with a pager if -p
        if pager:
            if self.color_pager:
                with console.pager(styles=True):
                    console.print(layout)
            else:
                with console.pager():
                    console.print(layout)
        else:
            console.print(layout)

    def resume(self, alias):
        """Resume a currently paused time entry.

        Args:
            alias (str):    the time entry to resume.

        """
        alias = alias.lower()
        uid = self._uid_from_alias(alias)
        if not uid:
            self._alias_not_found(alias)
        else:
            if self._is_paused(uid):
                time_entry = self._parse_time_entry(uid)
                stopwatch = time_entry['stopwatch']
                now = datetime.now(tz=self.ltz)
                new_entry = {}
                new_entry['start'] = now
                stopwatch.append(new_entry)
                self.modify(
                    alias,
                    new_status='running',
                    new_stopwatch=stopwatch)
                print(f"{alias} resumed.")
            else:
                self._handle_error(f"{alias} is not paused")

    def start(
            self,
            description,
            project=None,
            tags=None):
        """Start a new time entry.

        Args:
            description (str):  the time entry description.
            project (str):      the associated project for the entry.
            tags (str):         tags on the time entry.

        """
        uid = str(uuid.uuid4())
        now = datetime.now(tz=self.ltz)
        created = now
        updated = now
        started = now
        completed = None
        status = 'running'
        alias = self._gen_alias()
        description = description or (
                f"Time entry {now.strftime('%Y-%m-%d %H:%M:%S')}")
        if tags:
            tags = tags.lower()
            tags = tags.split(',')
            tags.sort()
        stopwatch = []
        new_entry = {}
        new_entry['start'] = now
        stopwatch.append(new_entry)
        notes = None

        filename = os.path.join(self.data_dir, f'{uid}.yml')

        data = {
            "entry": {
                "uid": uid,
                "created": created,
                "updated": updated,
                "started": started,
                "completed": completed,
                "alias": alias,
                "status": status,
                "description": description,
                "project": project,
                "tags": tags,
                "stopwatch": stopwatch,
                "notes": notes
            }
        }
        # write the new file
        self._write_yaml_file(data, filename)
        print(f"Started: {alias}")

    def start_wizard(self, description):
        """Prompt the user for time entry parameters and then call
        start().

        Args:
            description (str): the time entry description.

        """
        project = input("Project [none]: ") or None
        tags = input("Tags [none]: ") or None

        self.start(
            description=description,
            project=project,
            tags=tags)

    def stop(self, alias):
        """Stop a currently running time entry.

        Args:
            alias (str):    the time entry to pause.

        """
        alias = alias.lower()
        uid = self._uid_from_alias(alias)
        if not uid:
            self._alias_not_found(alias)
        else:
            if self._is_running(uid):
                time_entry = self._parse_time_entry(uid)
                stopwatch = time_entry['stopwatch']
                now = datetime.now(tz=self.ltz)
                last_entry = stopwatch[-1]
                start = last_entry['start']
                stopwatch.pop(-1)
                new_entry = {}
                new_entry['start'] = start
                new_entry['stop'] = now
                stopwatch.append(new_entry)
                self.modify(
                    alias,
                    new_status='stopped',
                    new_completed=now.strftime("%Y-%m-%d %H:%M:%S"),
                    new_stopwatch=stopwatch)
                print(f"{alias} stopped.")
            else:
                self._handle_error(f"{alias} is not running")

    def unset(self, alias, field):
        """Clear a specified field for a given alias.

        Args:
            alias (str):    the time entry alias.
            field (str):    the field to clear.

        """
        alias = alias.lower()
        field = field.lower()
        uid = self._uid_from_alias(alias)
        if not uid:
            self._alias_not_found(alias)
        else:
            allowed_fields = [
                'tags',
                'project'
            ]
            if field in allowed_fields:
                if self.time_entries[uid][field]:
                    self.time_entries[uid][field] = None
                    time_entry = self._parse_time_entry(uid)
                    filename = self.time_entry_files.get(uid)
                    if time_entry and filename:
                        data = {
                            "entry": {
                                "uid": time_entry['uid'],
                                "created": time_entry['created'],
                                "updated": time_entry['updated'],
                                "started": time_entry['started'],
                                "completed": time_entry['completed'],
                                "alias": time_entry['alias'],
                                "status": time_entry['status'],
                                "description": time_entry['description'],
                                "project": time_entry['project'],
                                "tags": time_entry['tags'],
                                "stopwatch": time_entry['stopwatch'],
                                "notes": time_entry['notes']
                            }
                        }
                        # write the updated file
                        self._write_yaml_file(data, filename)
            else:
                self._handle_error(f"cannot clear field '{field}'")

class FSHandler(FileSystemEventHandler):
    """Handler to watch for file changes and refresh data from files.

    Attributes:
        shell (obj):    the calling shell object.

    """
    def __init__(self, shell):
        """Initializes an FSHandler() object."""
        self.shell = shell

    def on_any_event(self, event):
        """Refresh data in memory on data file changes.

        Args:
            event (obj):    file system event.

        """
        if event.event_type in [
                'created', 'modified', 'deleted', 'moved']:
            self.shell.do_refresh("silent")


class EntriesShell(Cmd):
    """Provides methods for interactive shell use.

    Attributes:
        time_entries (obj):     an instance of TimeEntries().

    """
    def __init__(
            self,
            time_entries,
            completekey='tab',
            stdin=None,
            stdout=None):
        """Initializes a TimeEntriesShell() object."""
        super().__init__()
        self.time_entries = time_entries

        # start watchdog for data_dir changes
        # and perform refresh() on changes
        observer = Observer()
        handler = FSHandler(self)
        observer.schedule(
                handler,
                self.time_entries.data_dir,
                recursive=True)
        observer.start()

        # class overrides for Cmd
        if stdin is not None:
            self.stdin = stdin
        else:
            self.stdin = sys.stdin
        if stdout is not None:
            self.stdout = stdout
        else:
            self.stdout = sys.stdout
        self.cmdqueue = []
        self.completekey = completekey
        self.doc_header = (
            "Commands (for more info type: help):"
        )
        self.ruler = "―"

        self._set_prompt()

        self.nohelp = (
            "\nNo help for %s\n"
        )
        self.do_clear(None)

        print(
            f"{APP_NAME} {APP_VERS}\n\n"
            f"Enter command (or 'help')\n"
        )

    # class method overrides
    def default(self, args):
        """Handle command aliases and unknown commands.

        Args:
            args (str): the command arguments.

        """
        if args == "quit":
            self.do_exit("")
        elif args.startswith("lsa"):
            newargs = args.split()
            newargs[0] = "all"
            self.do_list(' '.join(newargs))
        elif args.startswith("lsp"):
            newargs = args.split()
            newargs[0] = "paused"
            self.do_list(' '.join(newargs))
        elif args.startswith("lsr"):
            newargs = args.split()
            newargs[0] = "running"
            self.do_list(' '.join(newargs))
        elif args.startswith("ls"):
            newargs = args.split()
            if len(newargs) > 1:
                self.do_list(' '.join(newargs[1:]))
            else:
                self.do_list("")
        elif args.startswith("rptd"):
            newargs = args.split()
            newargs[0] = "today"
            self.do_report(' '.join(newargs))
        elif args.startswith("rppd"):
            newargs = args.split()
            newargs[0] = "yesterday"
            self.do_report(' '.join(newargs))
        elif args.startswith("rptw"):
            newargs = args.split()
            newargs[0] = "thisweek"
            self.do_report(' '.join(newargs))
        elif args.startswith("rppw"):
            newargs = args.split()
            newargs[0] = "lastweek"
            self.do_report(' '.join(newargs))
        elif args.startswith("rptm"):
            newargs = args.split()
            newargs[0] = "thismonth"
            self.do_report(' '.join(newargs))
        elif args.startswith("rppm"):
            newargs = args.split()
            newargs[0] = "lastmonth"
            self.do_report(' '.join(newargs))
        elif args.startswith("rpty"):
            newargs = args.split()
            newargs[0] = "thisyear"
            self.do_report(' '.join(newargs))
        elif args.startswith("rppy"):
            newargs = args.split()
            newargs[0] = "lastyear"
            self.do_report(' '.join(newargs))
        elif args.startswith("rp"):
            newargs = args.split()
            if len(newargs) > 1:
                self.do_report(' '.join(newargs[1:]))
            else:
                self.do_report("")
        elif args.startswith("rm"):
            newargs = args.split()
            if len(newargs) > 1:
                self.do_delete(' '.join(newargs[1:]))
            else:
                self.do_delete("")
        elif args.startswith("mod"):
            newargs = args.split()
            if len(newargs) > 1:
                self.do_modify(' '.join(newargs[1:]))
            else:
                self.do_modify("")
        else:
            print("\nNo such command. See 'help'.\n")

    def emptyline(self):
        """Ignore empty line entry."""

    def _set_prompt(self):
        """Set the prompt string."""
        if self.time_entries.color_bold:
            self.prompt = "\033[1mtime\033[0m> "
        else:
            self.prompt = "time> "

    def _uid_from_alias(self, alias):
        """Get the uid for a valid alias.

        Args:
            alias (str):    The alias of the time entry for which to find uid.

        Returns:
            uid (str or None): The uid that matches the submitted alias.

        """
        alias = alias.lower()
        uid = None
        for time_entry in self.time_entries.time_entries:
            this_alias = (self.time_entries.time_entries[time_entry]
                          .get("alias"))
            if this_alias:
                if this_alias == alias:
                    uid = time_entry
        return uid

    @staticmethod
    def do_clear(args):
        """Clear the terminal.

        Args:
            args (str): the command arguments, ignored.

        """
        os.system("cls" if os.name == "nt" else "clear")

    def do_config(self, args):
        """Edit the config file and reload the configuration.

        Args:
            args (str): the command arguments, ignored.

        """
        self.time_entries.edit_config()

    def do_delete(self, args):
        """Delete a time entry.

        Args:
            args (str):     the command arguments.

        """
        if len(args) > 0:
            commands = args.split()
            self.time_entries.delete(str(commands[0]).lower())
        else:
            self.help_delete()

    def do_edit(self, args):
        """Edit a time entry via $EDITOR.

        Args:
            args (str):     the command arguments.

        """
        if len(args) > 0:
            commands = args.split()
            self.time_entries.edit(str(commands[0]).lower())
        else:
            self.help_edit()

    @staticmethod
    def do_exit(args):
        """Exit the time entries shell.

        Args:
            args (str): the command arguments, ignored.

        """
        sys.exit(0)

    def do_info(self, args):
        """Output info about a time entry.

        Args:
            args (str): the command arguments.

        """
        if len(args) > 0:
            commands = args.split()
            alias = str(commands[0]).lower()
            page = False
            if len(commands) > 1:
                if str(commands[1]) == "|":
                    page = True
            self.time_entries.info(alias, page)
        else:
            self.help_info()

    def do_list(self, args):
        """Output a list of running and/or paused time entries.

        Args:
            args (str): the command arguments.

        """
        if len(args) > 0:
            args = args.strip()
            pager = False
            if args.endswith('|'):
                pager = True
                args = args[:-1].strip()
            commands = args.split()
            view = str(commands[0]).lower()
            self.time_entries.list(view, pager=pager)
        else:
            self.help_list()

    def do_modify(self, args):
        """Modify a time entry.

        Args:
            args (str): the command arguments.

        """
        if len(args) > 0:
            commands = args.split()
            alias = str(commands[0]).lower()
            uid = self._uid_from_alias(alias)
            if not uid:
                print(f"Alias '{alias}' not found")
            else:
                subshell = ModShell(self.time_entries, uid, alias)
                subshell.cmdloop()
        else:
            self.help_modify()

    def do_notes(self, args):
        """Edit time entry notes via $EDITOR.

        Args:
            args (str):     the command arguments.

        """
        if len(args) > 0:
            commands = args.split()
            self.time_entries.notes(str(commands[0]).lower())
        else:
            self.help_notes()

    def do_pause(self, args):
        """Pause a time entry.

        Args:
            args (str):     the command arguments.

        """
        if len(args) > 0:
            commands = args.split()
            self.time_entries.pause(str(commands[0]).lower())
        else:
            self.help_pause()

    def do_refresh(self, args):
        """Refresh time entry information if files changed on disk.

        Args:
            args (str): the command arguments, ignored.

        """
        self.time_entries.refresh()
        if args != 'silent':
            print("Data refreshed.")

    def do_report(self, args):
        """Create a time report that meets certain criteria.

        Args:
            args (str): the command arguments.

        """
        if len(args) > 0:
            term = str(args).strip()
            if term.endswith('|'):
                term = term[:-1].strip()
                page = True
            else:
                page = False
            self.time_entries.report(term, pager=page)
        else:
            self.help_report()

    def do_resume(self, args):
        """Resume a time entry.

        Args:
            args (str):     the command arguments.

        """
        if len(args) > 0:
            commands = args.split()
            self.time_entries.resume(str(commands[0]).lower())
        else:
            self.help_resume()

    def do_start(self, args):
        """Evoke the start time entry wizard.

        Args:
            args (str): the command arguments, ignored.

        """
        try:
            self.time_entries.start_wizard(args)
        except KeyboardInterrupt:
            print("\nCancelled.")

    def do_stop(self, args):
        """Stop and complete a time entry.

        Args:
            args (str):     the command arguments.

        """
        if len(args) > 0:
            commands = args.split()
            self.time_entries.stop(str(commands[0]).lower())
        else:
            self.help_stop()

    @staticmethod
    def help_clear():
        """Output help for 'clear' command."""
        print(
            '\nclear:\n'
            '    Clear the terminal window.\n'
        )

    @staticmethod
    def help_config():
        """Output help for 'config' command."""
        print(
            '\nconfig:\n'
            '    Edit the config file with $EDITOR and then reload '
            'the configuration and refresh data files.\n'
        )

    @staticmethod
    def help_delete():
        """Output help for 'delete' command."""
        print(
            '\ndelete (rm) <alias>:\n'
            '    Delete a time entry file.\n'
        )

    @staticmethod
    def help_edit():
        """Output help for 'edit' command."""
        print(
            '\nedit <alias>:\n'
            '    Edit a time entry file with $EDITOR.\n'
        )

    @staticmethod
    def help_exit():
        """Output help for 'exit' command."""
        print(
            '\nexit:\n'
            '    Exit the time entry shell.\n'
        )

    @staticmethod
    def help_info():
        """Output help for 'info' command."""
        print(
            '\ninfo <alias>:\n'
            '    Show info about a time entry.\n'
        )

    @staticmethod
    def help_list():
        """Output help for 'list' command."""
        print(
            '\nlist (ls) <view> [|]:\n'
            '    List time entries using one of the views \'all\', '
            '\'running\', or \'paused\'.'
            'Add \'|\' as an additional argument to page the output.\n\n'
            '    The following command shortcuts are available:\n\n'
            '      lsa : list all\n'
            '      lsp : list paused\n'
            '      lsr : list running\n'
        )

    @staticmethod
    def help_modify():
        """Output help for 'modify' command."""
        print(
            '\nmodify <alias>:\n'
            '    Modify a time entry.\n'
        )

    @staticmethod
    def help_notes():
        """Output help for 'notes' command."""
        print(
            '\nnotes <alias>:\n'
            '    Edit the notes on a time entry with $EDITOR. This is '
            'safer than editing the time entry file directly with '
            '\'edit\', as it will ensure proper indentation for '
            'multi-line notes.\n'
        )

    @staticmethod
    def help_pause():
        """Output help for 'pause' command."""
        print(
            '\npause <alias>:\n'
            '    Pause a running time entry.\n'
        )

    @staticmethod
    def help_refresh():
        """Output help for 'refresh' command."""
        print(
            '\nrefresh:\n'
            '    Refresh the time entry information from files on disk. '
            'This is useful if changes were made to files outside of '
            'the program shell (e.g. sync\'d from another computer).\n'
        )

    @staticmethod
    def help_report():
        """Output help for 'report' command."""
        print(
            '\nreport (rp) <term>:\n'
            '    Create a time entry report that meets some specified '
            'criteria.\n'
            'Add \'|\' as an additional argument to page the output.\n\n'
            '    The following command shortcuts are available:\n\n'
            '      rptd : report today\n'
            '      rppd : report yesterday\n'
            '      rptw : report thisweek\n'
            '      rppw : report lastweek\n'
            '      rptm : report thismonth\n'
            '      rppm : report lastmonth\n'
            '      rpty : report thisyear\n'
            '      rppy : report lastyear\n'
        )

    @staticmethod
    def help_resume():
        """Output help for 'resume' command."""
        print(
            '\nresume <alias>:\n'
            '    Resume a paused time entry.\n'
        )

    @staticmethod
    def help_start():
        """Output help for 'start' command."""
        print(
            '\nstart <description>:\n'
            '    Create new time entry interactively.\n'
        )

    @staticmethod
    def help_stop():
        """Output help for 'stop' command."""
        print(
            '\nstop <alias>:\n'
            '    Stop (and complete) a running time entry.\n'
        )


class ModShell(Cmd):
    """Subshell for modifying a time entry.

    Attributes:
        time_entries (obj):    an instance of TimeEntries().
        uid (str):      the uid of the time entry being modified.
        alias (str):    the alias of the time entry being modified.

    """
    def __init__(
            self,
            time_entries,
            uid,
            alias,
            completekey='tab',
            stdin=None,
            stdout=None):
        """Initializes a ModShell() object."""
        super().__init__()
        self.time_entries = time_entries
        self.uid = uid
        self.alias = alias

        # class overrides for Cmd
        if stdin is not None:
            self.stdin = stdin
        else:
            self.stdin = sys.stdin
        if stdout is not None:
            self.stdout = stdout
        else:
            self.stdout = sys.stdout
        self.cmdqueue = []
        self.completekey = completekey
        self.doc_header = (
            "Commands (for more info type: help):"
        )
        self.ruler = "―"

        self._set_prompt()

        self.nohelp = (
            "\nNo help for %s\n"
        )

    # class method overrides
    def default(self, args):
        """Handle command aliases and unknown commands.

        Args:
            args (str): the command arguments.

        """
        if args.startswith("del") or args.startswith("rm"):
            newargs = args.split()
            if len(newargs) > 1:
                newargs.pop(0)
                newargs = ' '.join(newargs)
                self.do_delete(newargs)
            else:
                self.do_delete("")
        elif args.startswith("quit") or args.startswith("exit"):
            return True
        else:
            print("\nNo such command. See 'help'.\n")

    @staticmethod
    def emptyline():
        """Ignore empty line entry."""

    def _set_prompt(self):
        """Set the prompt string."""
        if self.time_entries.color_bold:
            self.prompt = f"\033[1mmodify ({self.alias})\033[0m> "
        else:
            self.prompt = f"modify ({self.alias})> "

    @staticmethod
    def do_clear(args):
        """Clear the terminal.

        Args:
            args (str): the command arguments, ignored.

        """
        os.system("cls" if os.name == "nt" else "clear")

    def do_completed(self, args):
        """Modify the 'completed' date on a time entry.

        Args:
            args (str):     the command arguments.

        """
        if len(args) > 0:
            completed = str(args)
            self.time_entries.modify(
                alias=self.alias,
                new_completed=completed)
        else:
            self.help_completed()

    def do_delete(self, args):
        """Delete a clock line from a time entry.

        Args:
            args (str): the command arguments.

        """
        commands = args.split()
        if len(commands) < 2:
            self.help_delete()
        else:
            attr = str(commands[0]).lower()
            index = commands[1]
            if attr == 'time':
                clock_line = [index]
                self.time_entries.modify(
                    alias=self.alias,
                    del_time=clock_line)
            else:
                self.help_delete()

    def do_description(self, args):
        """Modify the description on a time entry.

        Args:
            args (str):     the command arguments.

        """
        if len(args) > 0:
            description = str(args)
            self.time_entries.modify(
                alias=self.alias,
                new_description=description)
        else:
            self.help_description()

    @staticmethod
    def do_done(args):
        """Exit the modify subshell.

        Args:
            args (str): the command arguments, ignored.

        """
        return True

    def do_info(self, args):
        """Display full details for the selected time entry.

        Args:
            args (str):     the command arguments.

        """
        if len(args) > 0:
            commands = args.split()
            if str(commands[0]) == "|":
                self.time_entries.info(self.alias, True)
            else:
                self.time_entries.info(self.alias)
        else:
            self.time_entries.info(self.alias)

    def do_notes(self, args):
        """Edit time entry notes via $EDITOR.

        Args:
            args (str):     the command arguments.

        """
        self.time_entries.notes(self.alias)

    def do_project(self, args):
        """Modify the project on a time entry.

        Args:
            args (str):     the command arguments.

        """
        if len(args) > 0:
            project = str(args)
            self.time_entries.modify(
                alias=self.alias,
                new_project=project)
        else:
            self.help_project()

    def do_started(self, args):
        """Modify the 'started' date on a time entry.

        Args:
            args (str):     the command arguments.

        """
        if len(args) > 0:
            started = str(args)
            self.time_entries.modify(
                alias=self.alias,
                new_started=started)
        else:
            self.help_started()

    def do_status(self, args):
        """Modify the status of a time entry.

        Args:
            args (str):     the command arguments.

        """
        if len(args) > 0:
            commands = args.split()
            status = str(commands[0]).lower()
            self.time_entries.modify(
                alias=self.alias,
                new_status=status)
        else:
            self.help_status()

    def do_tags(self, args):
        """Modify the tags on a time entry.

        Args:
            args (str):     the command arguments.

        """
        if len(args) > 0:
            commands = args.split()
            tags = str(commands[0])
            self.time_entries.modify(
                alias=self.alias,
                new_tags=tags)
        else:
            self.help_tags()

    def do_unset(self, args):
        """Clear a field on the time_entry.

        Args:
            args (str):     the command arguments.

        """
        if len(args) > 0:
            commands = args.split()
            if len(commands) > 2:
                self.help_unset()
            else:
                field = str(commands[0]).lower()
                allowed_fields = [
                        'tags',
                        'project'
                ]
                if field in allowed_fields:
                    self.time_entries.unset(self.alias, field)
                else:
                    self.help_unset()
        else:
            self.help_unset()

    @staticmethod
    def help_clear():
        """Output help for 'clear' command."""
        print(
            '\nclear:\n'
            '    Clear the terminal window.\n'
        )

    @staticmethod
    def help_completed():
        """Output help for 'completed' command."""
        print(
            '\ncompleted: <%Y-%m-%d[ %H:%M]>\n'
            '    Modify the \'completed\' date on the time entry.\n'
        )

    @staticmethod
    def help_delete():
        """Output help for 'delete' command."""
        print(
            '\ndelete (del, rm) time <number>:\n'
            '    Delete a clock line from a time entry, identified by '
            'the index number for the clock line.\n'
        )

    @staticmethod
    def help_description():
        """Output help for 'description' command."""
        print(
            '\ndescription <description>:\n'
            '    Modify the description of the time entry.\n'
        )

    @staticmethod
    def help_done():
        """Output help for 'done' command."""
        print(
            '\ndone:\n'
            '    Finish modifying the time entry.\n'
        )

    @staticmethod
    def help_info():
        """Output help for 'info' command."""
        print(
            '\ninfo [|]:\n'
            '    Display details for a time entry. Add "|" as an'
            'argument to page the output.\n'
        )

    @staticmethod
    def help_notes():
        """Output help for 'notes' command."""
        print(
            '\nnotes:\n'
            '    Edit the notes on this time entry with $EDITOR.\n'
        )

    @staticmethod
    def help_project():
        """Output help for 'project' command."""
        print(
            '\nproject <project>:\n'
            '    Modify the project of this time entry.\n'
        )

    @staticmethod
    def help_started():
        """Output help for 'started' command."""
        print(
            '\nstarted <%Y-%m-%d[ %H:%M]>:\n'
            '    Modify the \'started\' date on the time entry.\n'
        )

    @staticmethod
    def help_status():
        """Output help for 'status' command."""
        print(
            '\nstatus <status>:\n'
            '    Modify the status of the time entry.\n'
        )

    @staticmethod
    def help_tags():
        """Output help for 'tags' command."""
        print(
            '\ntags <tag>[,tag]:\n'
            '    Modify the tags on the time entry. A comma-delimted '
            'list or you may use the + and ~ notations to add or delete '
            'a tag from the existing tags.\n'
        )

    @staticmethod
    def help_unset():
        """Output help for 'unset' command."""
        print(
            '\nunset <alias> <field>:\n'
            '    Clear a specified field of the time entry. The field '
            'may be one of the following: tags or project.\n'
        )


def parse_args():
    """Parse command line arguments.

    Returns:
        args (dict):    the command line arguments provided.

    """
    parser = argparse.ArgumentParser(
        prog=APP_NAME,
        description='Terminal-based time tracking for nerds.')
    parser._positionals.title = 'commands'
    parser.set_defaults(command=None)
    subparsers = parser.add_subparsers(
        metavar=f'(for more help: {APP_NAME} <command> -h)')
    pager = subparsers.add_parser('pager', add_help=False)
    pager.add_argument(
        '-p',
        '--page',
        dest='page',
        action='store_true',
        help="page output")
    config = subparsers.add_parser(
        'config',
        help='edit configuration file')
    config.set_defaults(command='config')
    delete = subparsers.add_parser(
        'delete',
        aliases=['rm'],
        help='delete an entry file')
    delete.add_argument(
        'alias',
        help='time entry alias')
    delete.add_argument(
        '-f',
        '--force',
        dest='force',
        action='store_true',
        help="delete without confirmation")
    delete.set_defaults(command='delete')
    edit = subparsers.add_parser(
        'edit',
        help='edit a time entry file (uses $EDITOR)')
    edit.add_argument(
        'alias',
        help='time entry alias')
    edit.set_defaults(command='edit')
    info = subparsers.add_parser(
        'info',
        parents=[pager],
        help='show info about a time entry')
    info.add_argument(
        'alias',
        help='the time entry to view')
    info.set_defaults(command='info')
    listcmd = subparsers.add_parser(
        'list',
        aliases=['ls'],
        parents=[pager],
        help='list running and/or paused entries')
    listcmd.add_argument(
        'view',
        help='running, paused, or all')
    listcmd.set_defaults(command='list')
    # list shortcuts
    lsa = subparsers.add_parser('lsa', parents=[pager])
    lsa.set_defaults(command='lsa')
    lsr = subparsers.add_parser('lsr', parents=[pager])
    lsr.set_defaults(command='lsr')
    lsp = subparsers.add_parser('lsp', parents=[pager])
    lsp.set_defaults(command='lsp')
    modify = subparsers.add_parser(
        'modify',
        aliases=['mod'],
        help='modify a time entry')
    modify.add_argument(
        'alias',
        help='the time entry to modify')
    modify.add_argument(
        '--completed',
        metavar='<datetime>',
        help='completed datetime: YYYY-mm-dd[ HH:MM]')
    modify.add_argument(
        '--description',
        metavar='<description>',
        help='time entry description')
    modify.add_argument(
        '--notes',
        metavar='<text>',
        help='notes about the entry')
    modify.add_argument(
        '--project',
        metavar='<project>',
        help='time entry project')
    modify.add_argument(
        '--started',
        metavar='<datetime>',
        help='started datetime: YYYY-mm-dd[ HH:MM]')
    modify.add_argument(
        '--status',
        metavar='<status>',
        help='entry status [stopped, running, paused]')
    modify.add_argument(
        '--tags',
        metavar='<tag>[,tag]',
        help='time entry tag(s)')
    modify.add_argument(
        '--del-time',
        metavar='<index>',
        dest='del_time',
        action='append',
        help='delete time entry line from stopwatch')
    modify.set_defaults(command='modify')
    notes = subparsers.add_parser(
        'notes',
        help='add/update notes on a time entry (uses $EDITOR)')
    notes.add_argument(
        'alias',
        help='time entry alias')
    notes.set_defaults(command='notes')
    pause = subparsers.add_parser(
        'pause',
        help='pause the clock on an entry')
    pause.add_argument(
        'alias',
        help='time entry alias')
    pause.set_defaults(command='pause')
    query = subparsers.add_parser(
        'query',
        help='search time entries with structured text output')
    query.add_argument(
        'term',
        metavar='<expression>',
        help='search expression')
    query.add_argument(
        '-l',
        '--limit',
        dest='limit',
        help='limit output to specific field(s)')
    query.add_argument(
        '-j',
        '--json',
        dest='json',
        action='store_true',
        help='output as JSON rather than TSV')
    query.set_defaults(command='query')
    report = subparsers.add_parser(
        'report',
        aliases=['rp'],
        parents=[pager],
        help='print a time report')
    report.add_argument(
        'term',
        metavar='<expression>',
        help='the report name or expression')
    report.set_defaults(command='report')
    # report shortcuts
    rptd = subparsers.add_parser('rptd', parents=[pager])
    rptd.set_defaults(command='rptd')
    rppd = subparsers.add_parser('rppd', parents=[pager])
    rppd.set_defaults(command='rppd')
    rptw = subparsers.add_parser('rptw', parents=[pager])
    rptw.set_defaults(command='rptw')
    rppw = subparsers.add_parser('rppw', parents=[pager])
    rppw.set_defaults(command='rppw')
    rptm = subparsers.add_parser('rptm', parents=[pager])
    rptm.set_defaults(command='rptm')
    rppm = subparsers.add_parser('rppm', parents=[pager])
    rppm.set_defaults(command='rppm')
    rpty = subparsers.add_parser('rpty', parents=[pager])
    rpty.set_defaults(command='rpty')
    rppy = subparsers.add_parser('rppy', parents=[pager])
    rppy.set_defaults(command='rppy')
    resume = subparsers.add_parser(
        'resume',
        help='resume the clock on an entry')
    resume.add_argument(
        'alias',
        help='time entry alias')
    resume.set_defaults(command='resume')
    shell = subparsers.add_parser(
        'shell',
        help='interactive shell')
    shell.set_defaults(command='shell')
    start = subparsers.add_parser(
        'start',
        help='create a new time entry')
    start.add_argument(
        'description',
        help='time entry description')
    start.add_argument(
        '--project',
        metavar='<project>',
        help='time entry project')
    start.add_argument(
        '--tags',
        metavar='<tag>[,tag]',
        help='time entry tag(s)')
    start.set_defaults(command='start')
    stop = subparsers.add_parser(
        'stop',
        help='stop the clock on an entry')
    stop.add_argument(
        'alias',
        help='time entry alias')
    stop.set_defaults(command='stop')
    unset = subparsers.add_parser(
        'unset',
        help='clear a field from a specified time entry')
    unset.add_argument(
        'alias',
        help='time entry alias')
    unset.add_argument(
        'field',
        help='field to clear')
    unset.set_defaults(command='unset')
    version = subparsers.add_parser(
        'version',
        help='show version info')
    version.set_defaults(command='version')
    parser.add_argument(
        '-c',
        '--config',
        dest='config',
        metavar='<file>',
        help='config file')
    args = parser.parse_args()
    return parser, args


def main():
    """Entry point. Parses arguments, creates TimeEntries() object, calls
    requested method and parameters.

    """
    if os.environ.get("XDG_CONFIG_HOME"):
        config_file = os.path.join(
            os.path.expandvars(os.path.expanduser(
                os.environ["XDG_CONFIG_HOME"])), APP_NAME, "config")
    else:
        config_file = os.path.expandvars(
            os.path.expanduser(DEFAULT_CONFIG_FILE))

    if os.environ.get("XDG_DATA_HOME"):
        data_dir = os.path.join(
            os.path.expandvars(os.path.expanduser(
                os.environ["XDG_DATA_HOME"])), APP_NAME)
    else:
        data_dir = os.path.expandvars(
            os.path.expanduser(DEFAULT_DATA_DIR))

    parser, args = parse_args()

    if args.config:
        config_file = os.path.expandvars(
            os.path.expanduser(args.config))

    time_entries = TimeEntries(
        config_file,
        data_dir,
        DEFAULT_CONFIG)

    if not args.command:
        parser.print_help(sys.stderr)
        sys.exit(1)
    elif args.command == "config":
        time_entries.edit_config()
    elif args.command == "modify":
        time_entries.modify(
            alias=args.alias,
            new_description=args.description,
            new_tags=args.tags,
            new_started=args.started,
            new_completed=args.completed,
            new_status=args.status,
            new_project=args.project,
            del_time=args.del_time,
            new_notes=args.notes)
    elif args.command == "start":
        time_entries.start(
            description=args.description,
            tags=args.tags,
            project=args.project)
    elif args.command == "info":
        time_entries.info(args.alias, args.page)
    elif args.command == "list":
        time_entries.list(args.view, pager=args.page)
    elif args.command == "lsa":
        time_entries.list('all', pager=args.page)
    elif args.command == "lsr":
        time_entries.list('running', pager=args.page)
    elif args.command == "lsp":
        time_entries.list('paused', pager=args.page)
    elif args.command == "delete":
        time_entries.delete(args.alias, args.force)
    elif args.command == "edit":
        time_entries.edit(args.alias)
    elif args.command == "notes":
        time_entries.notes(args.alias)
    elif args.command == "pause":
        time_entries.pause(args.alias)
    elif args.command == "resume":
        time_entries.resume(args.alias)
    elif args.command == "stop":
        time_entries.stop(args.alias)
    elif args.command == "report":
        time_entries.report(args.term, args.page)
    elif args.command == "query":
        time_entries.query(args.term, limit=args.limit, json_output=args.json)
    elif args.command == "unset":
        time_entries.unset(args.alias, args.field)
    elif args.command == "shell":
        time_entries.interactive = True
        shell = EntriesShell(time_entries)
        shell.cmdloop()
    elif args.command == "version":
        print(f"{APP_NAME} {APP_VERS}")
        print(APP_COPYRIGHT)
        print(APP_LICENSE)
    else:
        sys.exit(1)


# entry point
if __name__ == "__main__":
    try:
        main()
    except KeyboardInterrupt:
        print("\nInterrupted.")
        sys.exit(1)
