# -*- coding: utf-8 -*- 
from sys import argv
import os
import os.path
import sqlite3
from colorama import Fore, Back, Style, init as col_init
from datetime import datetime, timedelta
from pprint import pprint
import math
import re
import humanize
import argparse
import importlib.util
from collections.abc import MutableMapping
import uuid

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
            return '{} {}'.format(parts[0], bluebg('[+]'))
        elif len(parts) > 0:
            return parts[0]
        else:
            return '<empty description>' + Style.RESET_ALL

    def displayid(self):
        if self.remote_id:
            return yellow('{:0>4} '.format(str(self.id))) + white(dim('{}'.format('(gh {:0>2})'.format(self.remote_id))))
        else:
            return yellow(str(self.id).zfill(4))

class Event:
    def __init__(self, entry, event, date):
        self.entry = entry
        self.event = event
        self.date = date

class CustomDictOne(dict):
   def __init__(self,*arg,**kw):
      super(CustomDictOne, self).__init__(*arg, **kw)

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
    def __init__(self, db):
        self.db = db

    def fetch_features(self):
        return active_plugins[0].fetch_features(self.config())

    def fetch_entries(self, tags, id):
        return active_plugins[0].fetch_issues(self.config(), tags, id)

    def add_entry(self, tags, msg, points):
        e = Entry(None, 'backlog', msg, points, None, tags, [], None)

        for p in reversed(active_plugins):
            p.add_entry(self.config(), e)

        return e

    def edit_entry(self, issue, msg):
        for p in reversed(active_plugins):
            id = p.update_entry(self.config(), issue, msg)

    def feature_tag(self, tag):
        for p in reversed(active_plugins):
            id = p.add_feature(self.config(), tag)

    def unfeature_tag(self, tag):
        for p in reversed(active_plugins):
            id = p.remove_feature(self.config(), tag)

    def start_entry(self, issue, deadline = None):
        for p in reversed(active_plugins):
            p.start_entry(self.config(), issue, deadline)

    def end_entry(self, issue):
        for p in reversed(active_plugins):
            p.end_entry(self.config(), issue)

    def backlog_entry(self, issue):
        for p in reversed(active_plugins):
            p.backlog_entry(self.config(), issue)

    def tag_entry(self, issue, tag):
        for p in reversed(active_plugins):
            p.tag_entry(self.config(), issue, tag)

    def untag_entry(self, issue, tag):
        for p in reversed(active_plugins):
            p.untag_entry(self.config(), issue, tag)

    def remove_entry(self, issue):
        for p in reversed(active_plugins):
            p.remove_entry(self.config(), issue)

    def config(self):
        return Config(self.db)

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

def show_entries(db, args):
    tags = args.tags or []
    all = args.all
    dates = args.dates
    show_entries_internal(db, tags, all, dates)

def red(t):
    return '{}{}{}'.format(Fore.RED, t, Fore.RESET)

def black(t):
    return '{}{}{}'.format(Fore.BLACK, t, Fore.RESET)

def white(t):
    return '{}{}{}'.format(Fore.WHITE, t, Fore.RESET)

def cyan(t):
    return '{}{}{}'.format(Fore.CYAN, t, Fore.RESET)

def yellow(t):
    return '{}{}{}'.format(Fore.YELLOW, t, Fore.RESET)

def bright(t):
    return '{}{}{}'.format(Style.BRIGHT, t, Style.NORMAL)

def dim(t):
    return '{}{}{}'.format(Style.DIM, t, Style.NORMAL)

def normal(t):
    return '{}{}'.format(Style.NORMAL, t)

def nobg(t):
    return '{}{}'.format(Back.RESET, t)

def redbg(t):
    return '{}{}{}'.format(Back.RED, t, Back.RESET)

def bluebg(t):
    return '{}{}{}'.format(Back.BLUE, t, Back.RESET)

def yellowbg(t):
    return '{}{}{}'.format(Back.YELLOW, t, Back.RESET)

def show_entries_internal(tpm, tags, all, full_dates):
    if tags and ((tags.startswith('PM') and tags[2:].isdigit()) or tags.isdigit()):
        show_full_entry(tpm, map_id(tags))
        return

    total = 0
    open = 0

    entries = tpm.fetch_entries(tags, None)
    features = tpm.fetch_features()

    maxtag = 0

    buckets = {}

    for e in entries:
        total += 1

        if not all and not e.open:
            continue

        if e.open:
            open += 1

        bt = 'misc'
        for t in list(e.tags):
            if t in features:
                e.tags.remove(t)
                bt = t
                break

        t = ','.join(e.tags)
        if len(t) > maxtag:
            maxtag = len(t)

        if bt in buckets:
            buckets[bt].append(e)
        else:
            buckets[bt] = [e]

    now = datetime.now().strftime('%Y-%m-%d %H:%M')

    print('{}/{} issues {}'.format(white(bright(open)), white(total), dim('| {} | teenypm v{}'.format(now, __version__))))

    for b in buckets:
        bstyle = dim
        for e in buckets[b]:
            if e.open:
                bstyle = bright

        print(bstyle(white('{} ({})'.format(b, len(buckets[b])))))

        for e in buckets[b]:
            state_style = normal
            background = nobg

            if all and not e.open:
                state_style = dim
                dates = ' - finished {}'.format(display_date(e.done, full_dates))

            elif e.state == 'doing':
                now = datetime.now()
                if e.deadline:
                    if now > e.deadline - timedelta(days=2):
                        state_style = normal
                        background = redbg
                    else:
                        background = bluebg

                    if now > e.deadline:
                        dates = bright(yellow('(LATE: was due {})'.format(display_date(e.deadline, full_dates))))
                    else:
                        dates = yellow(redbg('(due {})'.format(display_date(e.deadline, full_dates))))
                else:
                    state_style = normal
                    background = bluebg
                    dates = dim('({})'.format('added {}'.format(display_date(e.created, full_dates))))

            else:
                dates = dim('({})'.format('added {}'.format(display_date(e.created, full_dates))))

            tags = [cyan(t) if t != 'bug' or e.deadline else red('bug') for t in sorted(e.tags)]
            display_tags = ','.join(tags)

            display_tags += ' ' * (maxtag - len(','.join(e.tags)))

            msg = e.summary()
            if e.points > 1:
                points = cyan(points)
            else:
                points = ''

            print(state_style(background('  +- {}  {}  {} {} {}'.format(e.displayid(), display_tags, white(msg), dates, points))))

def show_full_entry(tpm, id):
    entries = tpm.fetch_entries((), id)
    e = entries[0]

    tags = [cyan(t) if t != 'bug' else red('bug') for t in sorted(e.tags)]
    display_tags = ','.join(tags)
    dates = e.created.strftime('%Y-%m-%d %H:%M')

    if not e.open:
        dates += ' -> ' + e.done.strftime('%Y-%m-%d %H:%M')

    print(('{} | {} | {} | {}').format(e.displayid(), display_tags, dim(dates), cyan(e.points)))
    print(white(e.msg))

def show_tags(tpm, args):
    c = tpm.db.cursor()
    for row in c.execute('SELECT tag, COUNT(*) as count FROM tag GROUP BY tag ORDER BY tag'):
        print('{} - {}'.format(cyan(row['tag']), white(row['count'])))

def add_entry(tpm, args):
    msg = args.desc
    if args.edit:
        content = from_editor(msg, 0)
        if content != None:
            msg = ''.join(content)

    e = tpm.add_entry(args.tags.split(','), msg, args.points)
    print('Added {}: {}'.format(e.displayid(), white(e.summary())))

def edit_entry(tpm, args):
    content = from_editor(args.issue.msg, 0)
    if content != None:
        msg = ''.join(content)

    tpm.edit_entry(args.issue, msg)
    print('Modified {}: {}'.format(args.issue.displayid(), white(args.issue.summary())))

def feature_tag(tpm, args):
    tag = args.tag

    if args.remove:
        tpm.unfeature_tag(tag)
        print('Tag {} is no longer a feature'.format(cyan(tag)))
    else:
        tpm.feature_tag(tag)
        print('Tag {} is now a feature'.format(cyan(tag)))

def start_entry(tpm, args):
    id = args.id
    tf = None

    if args.timeframe:
        import dateparser   # bad style, but dateparser very slow to import
        now = datetime.now()
        tf_str = args.timeframe
        tf = dateparser.parse(tf_str, settings={'RELATIVE_BASE': now}).replace(hour=23, minute=59, second=0)
        if tf < now:
            print(red("ERROR: time flows inexorably forwards.\nPromising to complete an issue in the past will bring you nothing but despair."))
            quit()

    tpm.start_entry(args.issue, tf)
    print('Started {}'.format(tpm.displayid(id)))
    if tf:
        print('Your deadline is midnight {}'.format(red(tf.strftime('%Y-%m-%d'))))

def backlog_entry(tpm, args):
    tpm.backlog_entry(args.issue)
    print('Moved {} to backlog'.format(args.issue.displayid()))

def end_entry(tpm, args):
    tpm.end_entry(args.issue)
    print('Ended {}{:0>4}{}'.format(args.issue.displayid()))

def end_entry_and_commit(tpm, args):
    end_entry(tpm, args)
    os.system('git commit -a -m "{}"'.format('PM{:04} - {}'.format(args.issue.id, args.issue.msg)))

def tag_entry(tpm, args):
    tag = args.tag
    id = args.id
    issue = args.issue

    if args.remove:
        if tag in issue.tags:
            tpm.untag_entry(issue, tag)
            print('Untagged {} with {}'.format(issue.displayid(), cyan(tag)))
        else:
            print('{} wasn\'t tagged with {}'.format(issue.displayid(), cyan(tag)))
    else:
        if tag not in issue.tags:
            tpm.tag_entry(issue, tag)
            print('Tagged {} with {}'.format(issue.displayid(), cyan(tag)))
        else:
            print('{} already tagged with {}'.format(issue.displayid(), cyan(tag)))

def remove_entry(tpm, args):
    tpm.remove_entry(args.issue)
    print('Deleted {}'.format(args.issue.displayid()))

def burndown(tpm, args):
    tags = args.tags.split(',') if args.tags else []

    first_date = None
    created = {}
    done = {}

    for e in tpm.fetch_entries(tags, None):
        ckey = e.created.strftime("%Y%j")
        created[ckey] = created.get(ckey, 0) + e.points

        if not first_date or e.created < first_date:
            first_date = e.created

        if not e.open:
            dkey = e.done.strftime("%Y%j")
            done[dkey] = done.get(dkey, 0) + e.points

    total = 0

    h = 20
    if first_date == None:
        days = 0
    else:
        days = int((datetime.today() - first_date).days) + 1

    screen = [[0 for x in range(days)] for y in range(h)]
    maxy = 0
    first = 0
    last = 0

    for n in range(days):
        date = first_date + timedelta(days=n)
        key = date.strftime("%Y%j")

        total = total + created.get(key, 0) - done.get(key, 0)

        if n == 0:
            first = total
        
        if n == days - 1:
            last = total

        screen[total][n] = '+'
        if total > maxy:
            maxy = total

    if first == last:
        velocity = 1
    else:
        velocity = (first - last) / days

    predicted = math.ceil(last / velocity)

    # print screen

    print()
    empty = '  '
    y_end = [None] * days
    for y in range(maxy,-1,-1):
        line = ''
        for x in range(days):
            if screen[y][x]:
                y_end[x] = y
                if x < days - 1:
                    line += cyan('⭑ ')
                else:
                    line += white('★ ')
            elif y_end[x] and y < y_end[x]:
                if x == days - 1:
                    line += white('. ')
                else:
                    line += dim('. ')
            else:
                line += empty

        for x in range(predicted):
            if y == math.floor((predicted - x) * velocity):
                if x == predicted - 1:
                    line += '🏁'
                else:
                    line += dim(cyan('● '))
            else:
                line += empty
        
        print(line)

    end_date = date.today() + timedelta(days=predicted)

    print('Finish in {} days on {} {}'.format(bright(white(predicted)), bright(white(end_date.strftime('%A %d %b %Y'))), dim("(velocity {:.1f})".format(velocity))))

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

def make_a_plan(tpm, args):
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
            print('Added {}: {}'.format(e.displayid(), white(msg)))

def sync(tpm):
    config = tpm.config()

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

def remote_plugin(tpm, args):
    plugin = import_plugin(args.plugin)
    config = tpm.config()

    plugin_cp = 'plugin.' + args.plugin
    plugin_enabled = plugin_cp in config

    if args.remove:
        if not plugin_enabled:
            print('Remote {} has not been setup'.format(args.plugin))
        else:
            plugin.remove(config)
            del config[plugin_cp]
            activate_plugins.remove(args.plugin)
            print('Removed {} remote'.format(args.plugin))
    else:
        if plugin_enabled:
            print('Remote {} is already configured'.format(args.plugin))
        else:
            if plugin.setup(config):
                config[plugin_cp] = 'true'
                activate_plugins.append(args.plugin)
                print('Remote {} has been set up'.format(args.plugin))

    # TEST
    sync(tpm)

def import_plugin(p):
    plugins_dir = os.path.join(os.path.dirname(__file__), 'plugins')

    plugins = {}
    for f in [f for f in os.listdir(plugins_dir) if f.endswith('.py')]:
        plugins[f.split('.')[0]] = os.path.join(plugins_dir, f)

    if p not in plugins:
        print(red('ERROR:') + ' plugin {} not found - available plugins are:'.format(white(bright(p))))
        for ap in plugins:
            print('  - ' + ap)

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
    tpm = TeenyPM(db)

    activate_plugins(tpm.config())
    
    parser = argparse.ArgumentParser(description="teenypm - a teeny, tiny CLI project manager | v" + __version__)
    parser.add_argument('-a', '--all', help='Show all issues, even closed', action="store_true")
    parser.add_argument('-d', '--dates', help='Show full dates', action="store_true")
    parser.add_argument('-nc', '--nocolour', help='Disable colour output', action="store_true")

    subparsers = parser.add_subparsers(title='subcommands', metavar="<command>", help='sub-command help')

    p_show = subparsers.add_parser('show', help='show issues')
    p_show.add_argument('tags', nargs="?", type=str, help='Filter by comma-seperated tags')
    p_show.add_argument('-a', '--all', help='Show all issues, even closed', action="store_true")
    p_show.add_argument('-d', '--dates', help='Show full dates', action="store_true")
    p_show.set_defaults(func=show_entries)

    p_add = subparsers.add_parser('add', help='add an issue')
    p_add.add_argument('tags', type=str, help='comma-seperated tags')
    p_add.add_argument('desc', type=str, help='issue description')
    p_add.add_argument('points', type=int, nargs='?', default=1, help='effort points (defaults to 1)')
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

    p_burn = subparsers.add_parser('burn', help='display a burndown chart')
    p_burn.add_argument('tags', type=str, nargs='?', help='comma-seperated tags')
    p_burn.set_defaults(func=burndown)

    p_remote = subparsers.add_parser('remote', help='integrate a remote API')
    p_remote.add_argument('plugin', type=str, help='"supported: github"')
    p_remote.add_argument('-r', '--remove', help='remove remote', action='store_true')
    p_remote.set_defaults(func=remote_plugin)

    args = parser.parse_args()

    col_init(strip = args.nocolour)

    if hasattr(args, 'id'):
        args.id = map_id(args.id)

        entries = tpm.fetch_entries([], args.id)
        if len(entries) == 0:
            print('{} doesn\'t exist'.format(yellow(str(args.id).zfill(4))))
            exit(0)
        args.issue = entries[0]

    if not hasattr(args, 'func'):
        show_entries_internal(tpm, [], args.all, args.dates)
    else:
        args.func(tpm, args)

    db.close()

if __name__ == '__main__':
    main()
