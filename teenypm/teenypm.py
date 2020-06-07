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

__version__ = '0.1.7'

DEFAULT_EDITOR = 'vi +<line>'

class Entry:
    def __init__(self, id, state, msg, points, tags, history, deadline):
        self.id = id
        self.state = state
        self.open = state != 'done'
        self.msg = msg
        self.points = points
        self.tags = tags
        self.history = history
        self.deadline = deadline

        for e in history:
            if e.event == 'create':
                self.created = e.date
            elif e.event == 'done':
                self.done = e.date

class Event:
    def __init__(self, entry, event, date):
        self.entry = entry
        self.event = event
        self.date = date

def init_db():
    filename = 'pm.db'
    if not os.path.isfile(filename):
        print('No teenypm database found - creating new one: ' + filename)

    db = sqlite3.connect(filename, detect_types=sqlite3.PARSE_DECLTYPES|sqlite3.PARSE_COLNAMES)
    db.row_factory = sqlite3.Row

    c = db.cursor()
    c.execute('CREATE TABLE IF NOT EXISTS entry (msg TEXT, points INT, state TEXT)')
    c.execute('CREATE TABLE IF NOT EXISTS tag (tag TEXT, entry INT)')
    c.execute('CREATE TABLE IF NOT EXISTS history (entry INT, event TEXT, date INT)')
    c.execute('CREATE TABLE IF NOT EXISTS feature (tag TEXT)')
    c.execute('CREATE TABLE IF NOT EXISTS deadline (entry INT, date INT)')

    db.commit()
    return db

def summary(msg):
    parts = list(filter(lambda line: line != '', msg.split('\n')))

    if len(parts) > 1:
        return '{} {}'.format(parts[0], bluebg('[+]'))
    elif len(parts) > 0:
        return parts[0]
    else:
        return '<empty description>' + Style.RESET_ALL

def fetch_history(db, entry):
    c = db.cursor()
    history = []
    for row in c.execute('SELECT event, date as "date [timestamp]" FROM history WHERE entry = ?', (entry,)):
        history.append(Event(
            entry, row['event'], row['date']
        ))

    return history

def fetch_features(db):
    c = db.cursor()
    features = []
    for row in c.execute('SELECT tag FROM feature'):
        features.append(row['tag'])
    return features

def fetch_entries(db, tags, id):
    c = db.cursor()
    result = []
    deadlines = {}

    for row in c.execute('SELECT entry, date as "date [timestamp]" FROM deadline'):
        deadlines[row['entry']] = row['date']

    sql = 'SELECT e.rowid AS id, state, msg, points, GROUP_CONCAT(tag) AS tags FROM tag t INNER JOIN entry e ON e.rowid = t.entry'
    if id:
        c.execute(sql + ' WHERE e.rowid = ? GROUP BY e.rowid', (id,))
    else:
        c.execute(sql + ' GROUP BY e.rowid')

    for row in c:
        etags = row['tags'].split(',')

        match = False
        if len(tags) > 0:
            for t in tags.split(','):
                if t in etags:
                    match = True
                    break
        else:
            match = True

        if match:
            result.append(Entry(
                row['id'], row['state'],
                row['msg'], row['points'],
                etags,
                fetch_history(db, row['id']),
                deadlines.get(row['id'], None)
            ))

    state_order = ['doing', 'backlog', 'done']
    return sorted(result, key=lambda e: (state_order.index(e.state), -e.id))

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

def displayid(id):
    return yellow(str(id).zfill(4))

def show_entries_internal(db, tags, all, full_dates):
    if tags and (tags.startswith('PM') and tags[2:].isdigit()):
        show_full_entry(db, map_id(tags))
        return

    total = 0
    open = 0

    entries = fetch_entries(db, tags, None)
    features = fetch_features(db)

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

            msg = summary(e.msg)
            if e.points > 1:
                points = cyan(points)
            else:
                points = ''

            print(state_style(background('  +- {}  {}  {} {} {}'.format(displayid(e.id), display_tags, white(msg), dates, points))))

def show_full_entry(db, id):
    entries = fetch_entries(db, (), id)
    e = entries[0]

    tags = [cyan(t) if t != 'bug' else red('bug') for t in sorted(e.tags)]
    display_tags = ','.join(tags)
    dates = e.created.strftime('%Y-%m-%d %H:%M')

    if not e.open:
        dates += ' -> ' + e.done.strftime('%Y-%m-%d %H:%M')

    print(('{} | {} | {} | {}').format(displayid(e.id), display_tags, dim(dates), cyan(e.points)))
    print(white(e.msg))

def show_tags(db, args):
    c = db.cursor()
    for row in c.execute('SELECT tag, COUNT(*) as count FROM tag GROUP BY tag ORDER BY tag'):
        print('{} - {}'.format(cyan(row['tag']), white(row['count'])))

def add_history(c, id, event):
    c.execute('INSERT INTO history (entry, date, event) VALUES (?, CURRENT_TIMESTAMP, ?)', (id, event))

def add_entry(db, args):
    add_entry_internal(db, args.tags.split(','), args.desc, args.points, args.edit)

def add_entry_internal(db, tags, msg, points, edit):
    if edit:
        content = from_editor(msg, 0)
        if content != None:
            msg = ''.join(content)

    c = db.cursor()
    c.execute("INSERT INTO entry (msg, points, state) VALUES (?, ?, 'backlog')", (msg, points))

    id = c.lastrowid
    add_history(c, id, 'create')

    for tag in tags:
        c.execute('INSERT INTO tag VALUES (?, ?)', (tag, id))

    db.commit()

    print('Added {}: {}'.format(displayid(id), white(summary(msg))))

def change_state(db, id, state):
    c = db.cursor()
    c.execute('UPDATE entry SET state = ? where rowid = ?', (state, id))
    if c.rowcount == 0:
        return False

    add_history(c, id, state)
    db.commit()
    return True

def edit_entry(db, args):
    id = args.id
    entries = fetch_entries(db, (), id)

    if len(entries) < 1:
        print('{} doesn\'t exist'.format(displayid(id)))
        return

    e = entries[0]

    content = from_editor(e.msg, 0)
    if content != None:
        msg = ''.join(content)

    c = db.cursor()
    c.execute('UPDATE entry SET msg = ? WHERE rowid = ?', (msg, id))
    db.commit()

    print('Modified {}: {}'.format(displayid(e.id), white(summary(msg))))

def feature_tag(db, args):
    if args.remove:
        unfeature_tag(db, args)
        return

    tag = args.tag
    c = db.cursor()
    count = c.execute('SELECT count(*) AS count FROM feature where tag = ?', (tag,)).fetchone()['count']
    if count == 0:
        c.execute('INSERT INTO feature VALUES (?)', (tag,))
    db.commit()

    print('Tag {} is now a feature'.format(cyan(tag)))

def unfeature_tag(db, args):
    tag = args.tag
    c = db.cursor()
    c.execute('DELETE FROM feature WHERE tag = ?', (tag,))
    db.commit()

    print('Tag {} is no longer a feature'.format(cyan(tag)))

def set_deadline(db, id, date):
    c = db.cursor()
    c.execute('DELETE FROM deadline WHERE entry = ?', (id, ))
    c.execute('INSERT INTO deadline (entry, date) VALUES (?, ?)', (id, date))
    db.commit()

def clear_deadline(db, id):
    c = db.cursor()
    c.execute('DELETE FROM deadline WHERE entry = ?', (id, ))
    db.commit()

def start_entry(db, args):
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

    if change_state(db, id, 'doing'):
        print('Started {}'.format(displayid(id)))
        if tf:
            set_deadline(db, id, tf)
            print('Your deadline is midnight {}'.format(red(tf.strftime('%Y-%m-%d'))))
    else:
        print('{} doesn\'t exist'.format(displayid(id)))

def backlog_entry(db, args):
    id = args.id
    if change_state(db, id, 'backlog'):
        clear_deadline(db, id)
        print('Moved {} to backlog'.format(displayid(id)))
    else:
        print('{} doesn\'t exist'.format(display(id)))

def end_entry(db, args):
    id = args.id
    if change_state(db, id, 'done'):
        clear_deadline(db, id)
        print('Ended {}{:0>4}{}'.format(Fore.YELLOW, id, Style.RESET_ALL))
        return True
    else:
        print('{}{:0>4}{} doesn\'t exist'.format(Fore.YELLOW, id, Style.RESET_ALL))
        return False

def end_entry_and_commit(db, args):
    if end_entry(db, args):
        e = fetch_entries(db, (), args.id)[0]
        os.system('git commit -a -m "{}"'.format('PM{:04} - {}'.format(e.id, e.msg)))

def tag_entry(db, args):
    if args.remove:
        untag_entry(db, args)
        return

    tag = args.tag
    id = args.id
    c = db.cursor()

    count = c.execute('SELECT count(*) as count from tag where entry = ? and tag = ?', (id, tag)).fetchone()['count']
    if count == 0:
        c.execute('INSERT INTO tag VALUES (?, ?)', (tag, id))
        db.commit()
        print('Tagged {} with {}'.format(displayid(id), cyan(tag)))
    else:
        print('{} already tagged with {}'.format(displayid(id), cyan(tag)))

def untag_entry(db, args):
    tag = args.tag
    id = args.id
    c = db.cursor()

    c.execute('DELETE FROM tag where tag = ? and entry = ?', (tag, id))
    db.commit()

    if c.rowcount > 0:
        print('Untagged {} with {}'.format(displayid(id), cyan(tag)))
    else:
        print('{} wasn\'t tagged with {}'.format(displayid(id), cyan(tag)))

def remove_entry(db, args):
    id = args.id
    c = db.cursor()

    c.execute('DELETE FROM tag where entry = ?', (id,))
    c.execute('DELETE FROM entry where rowid = ?', (id,))
    db.commit()

    if c.rowcount > 0:
        print('Deleted {}'.format(displayid(id)))
    else:
        print('{} doesn\'t exist'.format(displayid(id)))
    
def burndown(db, args):
    tags = args.tags.split(',') if args.tags else []

    first_date = None
    created = {}
    done = {}

    for e in fetch_entries(db, tags, None):
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

def make_a_plan(db, args):
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

            add_entry_internal(db, tags, task['msg'], points, False)

def map_id(id):
    if id.startswith('PM'):
        return id[2:]
    return id

def main():
    db = init_db()

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

    args = parser.parse_args()

    col_init(strip = args.nocolour)

    if hasattr(args, 'id'):
        args.id = map_id(args.id)

    if not hasattr(args, 'func'):
        show_entries_internal(db, [], args.all, args.dates)
    else:
        args.func(db, args)

    db.close()

if __name__ == '__main__':
    main()
