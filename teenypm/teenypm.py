# -*- coding: utf-8 -*- 
from sys import argv
import os
import os.path
import sqlite3
from colorama import Fore, Back, Style
import datetime
from pprint import pprint
import math
import re

DEFAULT_EDITOR = 'vi'

class Entry:
    def __init__(self, id, open, created, done, msg, points, tags):
        self.id = id
        self.open = open
        self.created = created
        self.done = done
        self.msg = msg
        self.points = points
        self.tags = tags

def init_db():
    filename = 'pm.db'
    existed = os.path.isfile(filename)

    db = sqlite3.connect(filename, detect_types=sqlite3.PARSE_DECLTYPES|sqlite3.PARSE_COLNAMES)
    db.row_factory = sqlite3.Row

    if not existed:
        c = db.cursor()
        c.execute('CREATE TABLE entry (created INT, done INT, msg TEXT, points INT, state TEXT)')
        c.execute('CREATE TABLE tag (tag TEXT, entry INT)')
        db.commit()
        print('No pm database found ... created ' + filename)

    return db

def summary(msg):
    parts = msg.split('\n')

    if len(parts) > 1:
        return '{} ...'.format(parts[0])
    else:
        return msg

def fetch_entries(db, tags, id):
    c = db.cursor()
    result = []

    sql = 'SELECT e.rowid AS id, state, created as "created [timestamp]", done as "done [timestamp]", msg, points, GROUP_CONCAT(tag) AS tags FROM tag t INNER JOIN entry e ON e.rowid = t.entry'
    if id:
        cursor = c.execute(sql + ' WHERE e.rowid = ? GROUP BY e.rowid ORDER BY state DESC,e.rowid DESC', (id,))
    else:
        cursor = c.execute(sql + ' GROUP BY e.rowid ORDER BY state DESC,e.rowid DESC')

    for row in cursor:
        match = False
        if len(tags) > 0:
            for t in tags:
                if t in row['tags']:
                    match = True
                    break
        else:
            match = True

        if match:
            result.append(Entry(
                row['id'], row['state'] == 'open',
                row['created'], row['done'],
                row['msg'], row['points'],
                row['tags'].split(',')
            ))

    return result

def show_entries(db, tags, all):
    total = 0
    open = 0

    entries = fetch_entries(db, tags, None)

    maxtag = 0
    for e in entries:
        t = ','.join(e.tags)
        if len(t) > maxtag:
            maxtag = len(t)

    for e in entries:
        total += 1

        if not all and not e.open:
            continue

        if e.open:
            open += 1

        display_tags = ','.join(sorted(e.tags))
        dates = e.created.strftime('%Y-%m-%d %H:%M')
        state_style = ''

        if all and not e.open:
            state_style = Style.DIM
            dates += ' -> ' + e.done.strftime('%Y-%m-%d %H:%M')

        msg = summary(e.msg)
        print(('{}{}{:0>4}{}  {}{:' + str(maxtag) + '}{}  {}{}{} {}({}){} {}{}{}').format(state_style,Fore.YELLOW, e.id, Fore.RESET, Fore.CYAN, display_tags, Fore.RESET, Fore.WHITE, msg, Fore.RESET, Style.DIM, dates, Style.RESET_ALL, Fore.CYAN, e.points, Fore.RESET))

    print('{}{}{} open / {}{}{} total'.format(Fore.WHITE, open, Fore.RESET, Fore.WHITE, total, Fore.RESET))

def show_full_entry(db, id):
    entries = fetch_entries(db, (), id)
    e = entries[0]

    display_tags = ','.join(sorted(e.tags))
    dates = e.created.strftime('%Y-%m-%d %H:%M')

    if not e.open:
        dates += ' -> ' + e.done.strftime('%Y-%m-%d %H:%M')

    print(('{}{:0>4}{} | {}{}{} | {}{}{} | {}{}{}').format(Fore.YELLOW, e.id, Fore.RESET, Fore.CYAN, display_tags, Fore.RESET, Style.DIM, dates, Style.RESET_ALL, Fore.CYAN, e.points, Fore.RESET))
    print('----------------------------------------------')
    print(Fore.WHITE + e.msg + Fore.RESET)

def show_tags(db):
    c = db.cursor()
    for row in c.execute('SELECT tag, COUNT(*) as count FROM tag GROUP BY tag ORDER BY tag'):
        print('{}{}{} - {}'.format(Fore.CYAN, row['tag'], Fore.RESET, row['count']))

def add_entry(db, tags, msg, points, edit):
    if edit:
        content = from_editor(msg)
        if content != None:
            msg = ''.join(content)

    c = db.cursor()
    c.execute('INSERT INTO entry VALUES (CURRENT_TIMESTAMP, NULL, ?, ?, ?)', (msg, points, 'open'))
    id = c.lastrowid
    for tag in tags:
        c.execute('INSERT INTO tag VALUES (?, ?)', (tag, id))

    db.commit()

    print('Added {}{:0>4}{}: {}{}{}'.format(Fore.YELLOW, id, Style.RESET_ALL, Fore.WHITE, summary(msg), Fore.RESET))

def edit_entry(db, id):
    entries = fetch_entries(db, (), id)

    if len(entries) < 1:
        print('{}{:0>4}{} doesn\'t exist'.format(Fore.YELLOW, id, Style.RESET_ALL))
        return

    e = entries[0]

    content = from_editor(e.msg)
    if content != None:
        msg = ''.join(content)

    c = db.cursor()
    c.execute('UPDATE entry SET msg = ? WHERE rowid = ?', (msg, id))
    db.commit()

    print('Modified {}{:0>4}{}: {}{}{}'.format(Fore.YELLOW, id, Style.RESET_ALL, Fore.WHITE, summary(msg), Fore.RESET))

def end_entry(db, id):
    c = db.cursor()
    c.execute('UPDATE entry SET state = ?, done = CURRENT_TIMESTAMP WHERE rowid = ?', ('done', id))
    db.commit()

    if c.rowcount > 0:
        print('Ended {}{:0>4}{}'.format(Fore.YELLOW, id, Style.RESET_ALL))
    else:
        print('{}{:0>4}{} doesn\'t exist'.format(Fore.YELLOW, id, Style.RESET_ALL))

def tag_entry(db, tag, id):
    c = db.cursor()

    count = c.execute('SELECT count(*) as count from tag where entry = ? and tag = ?', (id, tag)).fetchone()['count']
    if count == 0:
        c.execute('INSERT INTO tag VALUES (?, ?)', (tag, id))
        db.commit()
        print('Tagged {}{:0>4}{} with {}{}{}'.format(Fore.YELLOW, id, Style.RESET_ALL, Fore.CYAN, tag, Style.RESET_ALL))
    else:
        print('{}{:0>4}{} already tagged with {}{}{}'.format(Fore.YELLOW, id, Style.RESET_ALL, Fore.CYAN, tag, Style.RESET_ALL))

def untag_entry(db, tag, id):
    c = db.cursor()

    c.execute('DELETE FROM tag where tag = ? and entry = ?', (tag, id))
    db.commit()

    if c.rowcount > 0:
        print('Untagged {}{:0>4}{} with {}{}{}'.format(Fore.YELLOW, id, Style.RESET_ALL, Fore.CYAN, tag, Style.RESET_ALL))
    else:
        print('{}{:0>4}{} wasn\'t tagged with {}{}{}'.format(Fore.YELLOW, id, Style.RESET_ALL, Fore.CYAN, tag, Style.RESET_ALL))

def remove_entry(db, id):
    c = db.cursor()

    c.execute('DELETE FROM tag where entry = ?', (id,))
    c.execute('DELETE FROM entry where rowid = ?', (id,))
    db.commit()

    if c.rowcount > 0:
        print('Deleted {}{:0>4}{}'.format(Fore.YELLOW, id, Style.RESET_ALL))
    else:
        print('{}{:0>4}{} doesn\'t exist'.format(Fore.YELLOW, id, Style.RESET_ALL))
    
def burndown(db, tags):
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
        days = int((datetime.datetime.today() - first_date).days) + 1

    screen = [[0 for x in range(days)] for y in range(h)]
    maxy = 0
    first = 0
    last = 0

    for n in range(days):
        date = first_date + datetime.timedelta(days=n)
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
                    line += Fore.CYAN + '⭑ ' + Fore.RESET
                else:
                    line += Fore.WHITE + '★ ' + Fore.RESET
            elif y_end[x] and y < y_end[x]:
                if x == days - 1:
                    line += Fore.WHITE + '. ' + Style.RESET_ALL
                else:
                    line += Style.DIM + '. ' + Style.RESET_ALL
            else:
                line += empty

        for x in range(predicted):
            if y == math.floor((predicted - x) * velocity):
                if x == predicted - 1:
                    line += '🏁'
                else:
                    line += Fore.CYAN + Style.DIM + '● ' + Style.RESET_ALL
            else:
                line += empty
        
        print(line)

    end_date = datetime.date.today() + datetime.timedelta(days=predicted)

    print('Finish in {}{}{} days on {}{}{} {}(velocity {:.1f}){}'.format(Fore.WHITE + Style.BRIGHT, predicted, Style.RESET_ALL, Fore.WHITE + Style.BRIGHT, end_date.strftime('%A %d %b %Y'), Style.RESET_ALL, Style.DIM, velocity, Style.RESET_ALL))

def from_editor(start_text):
    tmp_file = '_pm_.txt'

    if start_text:
        f = open(tmp_file, "w")
        f.write(start_text)
        f.close()

    os.system(os.getenv('EDITOR', DEFAULT_EDITOR) + ' ' + tmp_file)

    if not os.path.isfile(tmp_file):
        return []

    with open(tmp_file) as f:
        content = f.readlines()

    os.remove(tmp_file)

    return content

def make_a_plan(db, plan):
    content = from_editor(None)

    for line in content:
        line = line.strip()

        if line.startswith('#'): continue

        m = re.match(r"^(?P<msg>.+?)\s*(\[(?P<tags>[^\]]+)\])?\s*(?P<points>\d+)?$", line)
        if m:
            task = m.groupdict()

            if task['tags']:
                tags = task['tags'].split(',')
            else:
                tags = []

            tags.append('task')
            if plan:
                tags.append(plan)

            if task['points']:
                points = task['points']
            else:
                points = 1

            add_entry(db, tags, task['msg'], points)

def main():
    db = init_db()

    script = argv.pop(0)

    if len(argv) == 0:
        cmd = 'show'
    elif argv[0] == 'all':
        cmd = 'show'
    else:
        cmd = argv.pop(0)

    if cmd == 'show':
        tags = []

        if len(argv) == 0:
            show_all = False
        else:
            if argv[0] == 'all':
                argv.pop(0)
                show_all = True
            else:
                show_all = False

            if len(argv) > 0:
                tags = argv[0].split(',')

        if len(tags) == 1 and tags[0].isdigit():
            show_full_entry(db, tags[0])
        else:
            show_entries(db, tags, show_all)
    
    elif cmd == 'add' or cmd == 'addx':
        if len(argv) < 2:
            print("Usage: {0} add <tags> <msg> [points]".format(script))
        else:
            if len(argv) > 2:
                points=int(argv[2])
            else:
                points=1
            add_entry(db, argv[0].split(','), argv[1], points, cmd == 'addx')

    elif cmd == 'edit':
        if len(argv) < 1:
            print("Usage: {0} edit <id>".format(script))
        else:
            edit_entry(db, argv[0])

    elif cmd == 'end':
        if len(argv) < 1:
            print("Usage: {0} end <id>".format(script))
        else:
            end_entry(db, argv[0])

    elif cmd == 'rm':
        if len(argv) < 1:
            print("Usage: {0} rm <id>".format(script))
        else:
            remove_entry(db, int(argv[0]))

    elif cmd == 'tag':
        if len(argv) < 2:
            print("Usage: {0} tag <tag> <id>".format(script))
        else:
            tag_entry(db, argv[0], argv[1])

    elif cmd == 'untag':
        if len(argv) < 2:
            print("Usage: {0} untag <tag> <id>".format(script))
        else:
            untag_entry(db, argv[0], argv[1])

    elif cmd == 'tags':
        show_tags(db)

    elif cmd == 'burn':
        if len(argv) > 0:
            tags = argv[0].split(',')
        else:
            tags = []

        burndown(db, tags)

    elif cmd == 'plan':
        if len(argv) > 0:
            plan = argv[0]
        else:
            plan = None

        make_a_plan(db, plan)

    else:
        print('{}Error: {} is not a recognized command{}'.format(Fore.RED, cmd, Style.RESET_ALL))

    db.close()

if __name__ == '__main__':
    main()
