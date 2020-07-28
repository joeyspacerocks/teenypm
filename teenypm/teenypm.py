# -*- coding: utf-8 -*- 
from sys import argv
import os
import os.path
import sqlite3
import time
from datetime import datetime, timedelta
from pprint import pprint
import math
import re
import humanize
import argparse
import importlib.util
from collections.abc import MutableMapping
import uuid

from rich import box
from rich.console import Console
from rich.table import Table, Column
from rich.style import Style
from rich.theme import Theme

__version__ = '0.1.8'

DEFAULT_EDITOR = 'vi +<line>'

active_plugins = []

class Entry:
    def __init__(self, id, state, msg, points, remote_id, tags, history, deadline):
        self.id = id
        self.state = state
        self.open = state != 'done'
        self.msg = msg
        self.points = points
        self.remote_id = remote_id
        self.tags = tags
        self.history = history
        self.deadline = deadline

        for e in history:
            if e.event == 'create':
                self.created = e.date
            elif e.event == 'done':
                self.done = e.date

    def summary(self):
        parts = list(filter(lambda line: line != '', self.msg.split('\n')))

        if len(parts) > 1:
            return '{} [bold white on blue][[+]]'.format(parts[0])
        elif len(parts) > 0:
            return parts[0]
        else:
            return '<empty description>' + Style.RESET_ALL

    def displayid(self):
        if self.remote_id:
            return '[id.local]{:>4}[/] [id.remote]..{:0>2}[/]'.format(str(self.id), self.remote_id)
        else:
            return '[id.local]{:>4}[/]'.format(str(self.id))

class Event:
    def __init__(self, entry, event, date):
        self.entry = entry
        self.event = event
        self.date = date

class Config(MutableMapping):
    def __init__(self, db):
        self.storage = dict()
        self.db = db
        c = db.cursor()
        for row in c.execute('SELECT key, value FROM config'):
            self[row['key']] = row['value']

    def __getitem__(self, key):
        return self.storage[key]

    def __setitem__(self, key, item):
        self.storage[key] = item
        c = self.db.cursor()
        c.execute('INSERT INTO config(key, value) VALUES(?, ? ) ON CONFLICT(key) DO UPDATE SET value=?', (key, item, item))
        self.db.commit()
    
    def __delitem__(self, key):
        del self.storage[key]
        c = self.db.cursor()
        c.execute('DELETE FROM config WHERE key = ?', (key,))
        self.db.commit()

    def __iter__(self):
        return iter(self.storage)

    def __len__(self):
        return len(self.storage)

class TeenyPM():
    def __init__(self, config):
        self.config = config

    def fetch_entries(self, tags, id):
        return active_plugins[0].fetch_issues(self.config, tags, id)

    def add_entry(self, tags, msg, points):
        e = Entry(None, 'backlog', msg, points, None, tags, [], None)

        for p in reversed(active_plugins):
            p.add_entry(self.config, e)

        return e

    def edit_entry(self, issue, msg):
        for p in reversed(active_plugins):
            id = p.update_entry(self.config, issue, msg)

    def feature_tag(self, tag):
        for p in reversed(active_plugins):
            id = p.add_feature(self.config, tag)

    def unfeature_tag(self, tag):
        for p in reversed(active_plugins):
            id = p.remove_feature(self.config, tag)

    def start_entry(self, issue, deadline = None):
        for p in reversed(active_plugins):
            p.start_entry(self.config, issue, deadline)

    def end_entry(self, issue):
        for p in reversed(active_plugins):
            p.end_entry(self.config, issue)

    def backlog_entry(self, issue):
        for p in reversed(active_plugins):
            p.backlog_entry(self.config, issue)

    def tag_entry(self, issue, tag):
        for p in reversed(active_plugins):
            p.tag_entry(self.config, issue, tag)

    def untag_entry(self, issue, tag):
        for p in reversed(active_plugins):
            p.untag_entry(self.config, issue, tag)

    def remove_entry(self, issue):
        for p in reversed(active_plugins):
            p.remove_entry(self.config, issue)

def init_db():
    filename = 'pm.db'
    if not os.path.isfile(filename):
        print('No teenypm database found - creating new one: ' + filename)

    db = sqlite3.connect(filename, detect_types=sqlite3.PARSE_DECLTYPES|sqlite3.PARSE_COLNAMES)
    db.row_factory = sqlite3.Row

    c = db.cursor()
    schema_version = c.execute('PRAGMA user_version').fetchone()[0]

    if schema_version == 0:
        c.execute('CREATE TABLE IF NOT EXISTS entry (msg TEXT, points INT, state TEXT)')
        c.execute('CREATE TABLE IF NOT EXISTS tag (tag TEXT, entry INT)')
        c.execute('CREATE TABLE IF NOT EXISTS history (entry INT, event TEXT, date INT)')
        c.execute('CREATE TABLE IF NOT EXISTS feature (tag TEXT)')
        c.execute('CREATE TABLE IF NOT EXISTS deadline (entry INT, date INT)')
        c.execute('CREATE TABLE IF NOT EXISTS config (key TEXT PRIMARY KEY, value TEXT)')
        c.execute('PRAGMA user_version = 1')
        schema_version += 1
    
    if schema_version == 1:
        c.execute('ALTER TABLE entry ADD COLUMN remote_id TEXT')
        c.execute('PRAGMA user_version = 2')
        schema_version += 1

    if schema_version == 2:
        c.execute('INSERT INTO config (key, value) VALUES(?, ?)', ('project.id', str(uuid.uuid4())))
        c.execute('PRAGMA user_version = 3')
        schema_version += 1

    db.commit()
    return db

def display_date(date, full_date):
    if full_date:
        return date.strftime('%Y-%m-%d %H:%M')
    else:
        now = datetime.now()
        return humanize.naturaltime(now - date)

def show_entries(tpm, console, args):
    tags = args.tags or []
    if tags and ((tags.startswith('PM') and tags[2:].isdigit()) or tags.isdigit()):
        show_full_entry(console, tpm.fetch_entries((), tags)[0])
    else:
        show_entries_internal(tpm, console, tags, args.all, args.dates)

def doing_entries(tpm, console, args):
    show_entries_internal(tpm, console, [], False, args.dates, True)

def show_entries_internal(tpm, console, tags, all, full_dates, started = False):
    total = 0
    open = 0

    entries = tpm.fetch_entries(tags, None)
    features = active_plugins[0].fetch_features(tpm.config)

    buckets = {}

    for e in entries:
        total += 1

        if not all and not e.open:
            continue

        if started and not e.state == 'doing':
            continue

        if e.open:
            open += 1

        bt = 'misc'
        for t in list(e.tags):
            if t in features:
                e.tags.remove(t)
                bt = t
                break

        if bt in buckets:
            buckets[bt].append(e)
        else:
            buckets[bt] = [e]

    now = datetime.now().strftime('%Y-%m-%d %H:%M')

    console.print('[white][bold]{}[/bold]/{}[/white] issues [dim]| {} | teenypm v{}'.format(open, total, now, __version__), highlight=False)

    table = Table(
        "id",
        "tags",
        Column("msg", style = "msg"),
        Column("dates", justify = 'right'),
        "points",
        show_header = False,
        show_edge = False,
        box = box.SIMPLE,
        padding = [0, 0, 0, 1]
    )

    for b in buckets:
        bstyle = 'bucket.done'
        for e in buckets[b]:
            if e.open:
                bstyle = 'bucket.open'
                break

        table.add_row('{} ({})'.format(b, len(buckets[b])), None, None, None, None, style = bstyle)

        for e in buckets[b]:
            row_style = None

            if all and not e.open:
                row_style = Style(dim = True)
                dates = 'closed {}'.format(display_date(e.done, full_dates))

            elif e.state == 'doing':
                row_style = 'state.doing'
                now = datetime.now()
                if e.deadline:
                    if now > e.deadline:
                        dates = '[date.overdue]due {}'.format(display_date(e.deadline, full_dates))
                    else:
                        dates = '[date.soon]{}'.format(display_date(e.deadline, full_dates))
                else:
                    dates = '[date.created]{}'.format('{}'.format(display_date(e.created, full_dates)))

            else:
                dates = '[date.created]{}'.format('{}'.format(display_date(e.created, full_dates)))

            tags = ['[tag.default]{}[/]'.format(t) if t != 'bug' or e.deadline else '[tag.bug]bug[/]' for t in sorted(e.tags)]
            display_tags = ','.join(tags)

            msg = e.summary()
            if e.points > 1:
                points = '[points]{}[/]'.format(str(points))
            else:
                points = ''

            table.add_row(e.displayid(), display_tags, e.summary(), dates, points, style = row_style)

    console.print(table)

def show_full_entry(console, e):
    tags = ['[tag.default]{}[/]'.format(t) if t != 'bug' or e.deadline else '[tag.bug]bug[/ ]' for t in sorted(e.tags)]
    display_tags = ','.join(tags)
    dates = e.created.strftime('%Y-%m-%d %H:%M')

    if not e.open:
        dates += ' -> ' + e.done.strftime('%Y-%m-%d %H:%M')

    console.print(('{} | {} | [date.created]{}[/] | [points]{}').format(e.displayid(), display_tags, dates, e.points))
    console.print('[msg]' + e.msg)

def show_tags(tpm, console, args):
    c = tpm.db.cursor()
    for row in c.execute('SELECT tag, COUNT(*) as count FROM tag GROUP BY tag ORDER BY tag'):
        console.print('[tag.default]{}[/] - [msg]{}[/]'.format(row['tag'], row['count']))

def add_entry(tpm, console, args):
    msg = args.desc
    if args.edit:
        content = from_editor(msg, 0)
        if content != None:
            msg = ''.join(content)

    tags = args.tag.split(',') if args.tag else []

    e = tpm.add_entry(tags, msg, args.points)
    console.print('Added {}: [msg]{}'.format(e.displayid(), e.summary()))

def edit_entry(tpm, console, args):
    content = from_editor(args.issue.msg, 0)
    if content != None:
        msg = ''.join(content)

    tpm.edit_entry(args.issue, msg)
    console.print('Modified {}: [msg]{}'.format(args.issue.displayid(), args.issue.summary()))

def feature_tag(tpm, console, args):
    tag = args.tag

    if args.remove:
        tpm.unfeature_tag(tag)
        console.print('Tag [tag]{}[/] is no longer a feature'.format(tag))
    else:
        tpm.feature_tag(tag)
        console.print('Tag [tag]{}[/] is now a feature'.format(tag))

def start_entry(tpm, console, args):
    id = args.id
    tf = None

    if args.timeframe:
        import dateparser   # bad style, but dateparser very slow to import
        now = datetime.now()
        tf_str = args.timeframe
        tf = dateparser.parse(tf_str, settings={'RELATIVE_BASE': now}).replace(hour=23, minute=59, second=0)
        if tf < now:
            console.print("[error]ERROR: time flows inexorably forwards.\nPromising to complete an issue in the past will bring you nothing but despair.")
            quit()

    tpm.start_entry(args.issue, tf)
    console.print('Started {}'.format(args.issue.displayid()))
    if tf:
        console.print('Your deadline is midnight [date.soon]{}'.format(tf.strftime('%Y-%m-%d')))

def backlog_entry(tpm, console, args):
    tpm.backlog_entry(args.issue)
    console.print('Moved {} to backlog'.format(args.issue.displayid()))

def end_entry(tpm, console, args):
    tpm.end_entry(args.issue)
    console.print('Ended {}'.format(args.issue.displayid()))

def end_entry_and_commit(tpm, console, args):
    end_entry(tpm, console, args)
    os.system('git commit -a -m "{}"'.format('PM{:04} - {}'.format(args.issue.id, args.issue.msg)))
    os.system('git lg -n 1')

def tag_entry(tpm, console, args):
    tag = args.tag
    id = args.id
    issue = args.issue

    if args.remove:
        if tag in issue.tags:
            tpm.untag_entry(issue, tag)
            console.print('Untagged {} with [tag.default]{}'.format(issue.displayid(), tag))
        else:
            console.print('{} wasn\'t tagged with [tag.default]{}'.format(issue.displayid(), tag))
    else:
        if tag not in issue.tags:
            tpm.tag_entry(issue, tag)
            console.print('Tagged {} with [tag.default]{}'.format(issue.displayid(), tag))
        else:
            console.print('{} already tagged with [tag.default]{}'.format(issue.displayid(), tag))

def remove_entry(tpm, console, args):
    tpm.remove_entry(args.issue)
    console.print('Deleted {}'.format(args.issue.displayid()))

def from_editor(start_text, start_line):
    tmp_file = '_pm_.txt'

    if start_text:
        f = open(tmp_file, "w")
        f.write(start_text)
        f.close()

    ed_cmd = os.getenv('EDITOR', DEFAULT_EDITOR).replace('<line>', str(start_line))

    if '<file>' in ed_cmd:
        ed_cmd = ed_cmd.replace('<file>', tmp_file)
    else:
        ed_cmd += ' ' + tmp_file

    os.system(ed_cmd)

    if not os.path.isfile(tmp_file):
        return []

    with open(tmp_file) as f:
        content = [line for line in list(f) if not line.startswith('#')]

    if len(content)>0:
        content[-1] = content[-1].rstrip('\n')

    os.remove(tmp_file)

    return content

def make_a_plan(tpm, console, args):
    tag = args.tag
    help_text = '# One line for each issue, with optional tags and points.\n#  <desc> [[<tag>,...]] [points]\n# For example:\n#  Sort out the thing there [bug] 2\n\n'
    content = from_editor(help_text, help_text.count('\n') + 1)

    for line in content:
        line = line.strip()

        m = re.match(r"^(?P<msg>.+?)\s*(\[(?P<tags>[^\]]+)\])?\s*(?P<points>\d+)?$", line)
        if m:
            task = m.groupdict()

            if task['tags']:
                tags = task['tags'].split(',')
            else:
                tags = []

            tags.append('task')
            if tag:
                tags.append(tag)

            if task['points']:
                points = task['points']
            else:
                points = 1

            e = tpm.add_entry(tags, task['msg'], points)
            console.print('Added {}: [msg]{}'.format(e.displayid(), msg))

def sync(config, force):
    now = int(time.time())

    if not force:
        last_sync = int(config.get('last.sync', 0))

        if now - last_sync < 60 * 60:
            return

    config['last.sync'] = now

    if len(active_plugins) == 1:
        return

    p1 = active_plugins[0]
    p2 = active_plugins[1]

    local_lookup = {}
    local_issues = p1.fetch_issues(config)
    remote_issues = p2.fetch_issues(config)

    for issue in local_issues:
        if issue.remote_id:
            local_lookup[issue.remote_id] = issue
        elif issue.msg != '':
            p2.add_entry(config, issue)
            print('Local issue pushed: {} - {}'.format(issue.displayid(), issue.summary()))

    for issue in remote_issues:
        if issue.remote_id not in local_lookup:
            p1.add_entry(config, issue)
            print('GitHub issue pulled: GH #{} - {}'.format(issue.remote_id, issue.summary()))

def map_id(id):
    if id.startswith('PM'):
        return id[2:]
    return id

def remote_plugin(tpm, console, args):
    plugin = import_plugin(args.plugin)

    if not plugin:
        console.print('[error]ERROR: plugin [white bold]{}[/] not found - available plugins are:'.format(args.plugin))
        for ap in available_plugins():
            console.print('  - [white]' + ap)
        exit(0)

    config = tpm.config

    plugin_cp = 'plugin.' + args.plugin
    plugin_enabled = plugin_cp in config

    if args.remove:
        if not plugin_enabled:
            console.print('Remote [remote]{}[/] has not been setup'.format(args.plugin))
        else:
            plugin.remove(config)
            del config[plugin_cp]
            activate_plugins.remove(args.plugin)
            console.print('Removed [remote]{}[/] remote'.format(args.plugin))
    else:
        if plugin_enabled:
            console.print('Remote [remote]{}[/] is already configured'.format(args.plugin))
        else:
            if plugin.setup(config):
                config[plugin_cp] = 'true'
                activate_plugins.append(args.plugin)
                console.print('Remote [remote]{}[/] has been set up .. syncing issues ..'.format(args.plugin))
                sync(config, True)

def available_plugins():
    plugins_dir = os.path.join(os.path.dirname(__file__), 'plugins')

    plugins = {}
    for f in [f for f in os.listdir(plugins_dir) if f.endswith('.py')]:
        plugins[f.split('.')[0]] = os.path.join(plugins_dir, f)
    
    return plugins

def import_plugin(p):
    plugins = available_plugins()

    if p not in plugins:
        return None

    spec = importlib.util.spec_from_file_location("plugins." + p, plugins[p])
    plugin = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(plugin)
    return plugin

def activate_plugins(config):
    active_plugins.append(import_plugin('local'))
    for key in config.keys():
        if key.startswith('plugin.'):
            active_plugins.append(import_plugin(key.split('.')[1]))

def main():
    db = init_db()
    config = Config(db)

    tpm = TeenyPM(config)

    activate_plugins(tpm.config)

    parser = argparse.ArgumentParser(description="teenypm - a teeny, tiny CLI project manager | v" + __version__)
    parser.add_argument('-a', '--all', help='Show all issues, even closed', action="store_true")
    parser.add_argument('-d', '--dates', help='Show full dates', action="store_true")
    parser.add_argument('-s', '--force-sync', help='Force a sync with remote store', action="store_true")

    subparsers = parser.add_subparsers(title='subcommands', metavar="<command>", help='sub-command help')

    p_show = subparsers.add_parser('show', help='show issues')
    p_show.add_argument('tags', nargs="?", type=str, help='Filter by comma-seperated tags')
    p_show.add_argument('-a', '--all', help='Show all issues, even closed', action="store_true")
    p_show.add_argument('-d', '--dates', help='Show full dates', action="store_true")
    p_show.set_defaults(func=show_entries)

    p_show = subparsers.add_parser('doing', help='show issues in progress')
    p_show.add_argument('-d', '--dates', help='Show full dates', action="store_true")
    p_show.set_defaults(func=doing_entries)

    p_add = subparsers.add_parser('add', help='add an issue')
    p_add.add_argument('desc', type=str, help='issue description')
    p_add.add_argument('points', type=int, nargs='?', default=1, help='effort points (defaults to 1)')
    p_add.add_argument('-t', '--tag', type=str, help='comma-seperated tags')
    p_add.add_argument('-e', '--edit', help='Effort points (defaults to 1)', action="store_true")
    p_add.set_defaults(func=add_entry)

    p_edit = subparsers.add_parser('edit', help='edit an issue description')
    p_edit.add_argument('id', type=str, help='issue id')
    p_edit.set_defaults(func=edit_entry)

    p_remove = subparsers.add_parser('rm', help='remove an issue')
    p_remove.add_argument('id', type=str, help='issue id')
    p_remove.set_defaults(func=remove_entry)

    p_plan = subparsers.add_parser('plan', help='make a plan')
    p_plan.add_argument('tag', type=str, nargs='?', help='tag to add to all issues')
    p_plan.set_defaults(func=make_a_plan)

    p_start = subparsers.add_parser('start', help='mark an issue as started')
    p_start.add_argument('id', type=str, help='issue id')
    p_start.add_argument('timeframe', type=str, nargs='?', help='promised timeframe')
    p_start.set_defaults(func=start_entry)

    p_backlog = subparsers.add_parser('backlog', help='return an issue to the backlog')
    p_backlog.add_argument('id', type=str, help='issue id')
    p_backlog.set_defaults(func=backlog_entry)

    p_end = subparsers.add_parser('end', help='mark an issue as ended')
    p_end.add_argument('id', type=str, help='issue id')
    p_end.set_defaults(func=end_entry)

    # tag management

    p_tags = subparsers.add_parser('tags', help='list tags')
    p_tags.set_defaults(func=show_tags)

    p_tag = subparsers.add_parser('tag', help='tag an issue')
    p_tag.add_argument('tag', type=str, help='tag')
    p_tag.add_argument('id', type=str, help='issue id')
    p_tag.add_argument('-r', '--remove', help='remove tag from issue', action='store_true')
    p_tag.set_defaults(func=tag_entry)

    p_feature = subparsers.add_parser('feature', help='flag a tag as a feature')
    p_feature.add_argument('tag', type=str, help='tag to feature')
    p_feature.add_argument('-r', '--remove', help='remove feature flag from tag', action='store_true')
    p_feature.set_defaults(func=feature_tag)

    p_commit = subparsers.add_parser('commit', help='mark an issue as ended and git commit changes')
    p_commit.add_argument('id', type=str, help='issue id')
    p_commit.set_defaults(func=end_entry_and_commit)

    p_remote = subparsers.add_parser('remote', help='integrate a remote API')
    p_remote.add_argument('plugin', type=str, help='"supported: github"')
    p_remote.add_argument('-r', '--remove', help='remove remote', action='store_true')
    p_remote.set_defaults(func=remote_plugin)

    args = parser.parse_args()

    console = Console(theme = Theme({
        "id.local": "yellow",
        "id.remote": "dim white",
        "tag.default": "cyan",
        "tag.bug": "bold red",
        "date.overdue": "bold white on red",
        "date.soon": "bold yellow",
        "date.created": "dim",
        "state.doing": "bold",
        "bucket.done": "dim white",
        "bucket.open": "bold white",
        "points": "cyan",
        "msg" : "white",
        "error": "red",
        "remote": "bold white"
    }))

    if hasattr(args, 'id'):
        args.id = map_id(args.id)

        entries = tpm.fetch_entries([], args.id)
        if len(entries) == 0:
            console.print('[id.local]{:>4}[/] doesn\'t exist'.format(args.id))
            exit(0)
        args.issue = entries[0]

    sync(config, args.force_sync)

    if not hasattr(args, 'func'):
        show_entries_internal(tpm, console, [], args.all, args.dates)
    else:
        args.func(tpm, console, args)

    db.close()

if __name__ == '__main__':
    main()
