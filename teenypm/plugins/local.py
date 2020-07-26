# Core plugin providing local storage

import configparser
import pprint
import os
import sys
import requests
from datetime import datetime, timezone
from teenypm import Entry, Event

def setup(config):
    return True

def remove(config):
    pass

def fetch_history(db, entry):
    c = db.cursor()
    history = []
    for row in c.execute('SELECT event, date as "date [timestamp]" FROM history WHERE entry = ?', (entry,)):
        history.append(Event(
            entry, row['event'], 
            row['date'].replace(tzinfo=timezone.utc).astimezone(tz=None).replace(tzinfo=None)
        ))

    return history

def fetch_issues(config, tags = [], id = None):
    c = config.db.cursor()
    result = []
    deadlines = {}
    entry_tags = {}

    for row in c.execute('SELECT entry, GROUP_CONCAT(tag) as tags FROM tag GROUP BY entry'):
        entry_tags[row['entry']] = row['tags'].split(',')

    for row in c.execute('SELECT entry, date as "date [timestamp]" FROM deadline'):
        deadlines[row['entry']] = row['date']

    sql = 'SELECT rowid AS id, state, msg, points, remote_id FROM entry'
    if id:
        c.execute(sql + ' WHERE id = ?', (id,))
    else:
        c.execute(sql)

    for row in c:
        etags = entry_tags.get(row['id'], [])

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
                row['remote_id'], etags,
                fetch_history(config.db, row['id']),
                deadlines.get(row['id'], None)
            ))

    state_order = ['doing', 'backlog', 'done']
    return sorted(result, key=lambda e: (state_order.index(e.state), -e.id))

def add_entry(config, e):
    c = config.db.cursor()
    c.execute("INSERT INTO entry (msg, points, state, remote_id) VALUES (?, ?, ?, ?)", (e.msg, e.points, e.state, e.remote_id))

    e.id = c.lastrowid
    add_history(c, e.id, 'create')

    for tag in e.tags:
        c.execute('INSERT INTO tag VALUES (?, ?)', (tag, e.id))

    config.db.commit()

def update_entry(config, issue, msg):
    c = config.db.cursor()
    c.execute('UPDATE entry SET msg = ? WHERE rowid = ?', (msg, issue.id))
    config.db.commit()
    issue.msg = msg

def remove_entry(config, e):
    c = config.db.cursor()
    c.execute('DELETE FROM tag where entry = ?', (e.id,))
    c.execute('DELETE FROM entry where rowid = ?', (e.id,))
    config.db.commit()

def tag_entry(config, e, tag):
    c = config.db.cursor()
    count = c.execute('SELECT count(*) as count from tag where entry = ? and tag = ?', (e.id, tag)).fetchone()['count']
    if count == 0:
        c.execute('INSERT INTO tag VALUES (?, ?)', (tag, e.id))
        config.db.commit()

def untag_entry(config, e, tag):
    c = config.db.cursor()
    c.execute('DELETE FROM tag where tag = ? and entry = ?', (tag, e.id))
    config.db.commit()
    return c.rowcount > 0

def fetch_features(config):
    c = config.db.cursor()
    features = []
    for row in c.execute('SELECT tag FROM feature'):
        features.append(row['tag'])
    return features

def add_feature(config, tag):
    c = config.db.cursor()
    count = c.execute('SELECT count(*) AS count FROM feature where tag = ?', (tag,)).fetchone()['count']
    if count == 0:
        c.execute('INSERT INTO feature VALUES (?)', (tag,))
    config.db.commit()

def remove_feature(config, tag):
    c = config.db.cursor()
    c.execute('DELETE FROM feature WHERE tag = ?', (tag,))
    config.db.commit()

def start_entry(config, e, deadline = None):
    change_state(config, e, 'doing')
    if deadline:
        c = config.db.cursor()
        c.execute('DELETE FROM deadline WHERE entry = ?', (e.id, ))
        c.execute('INSERT INTO deadline (entry, date) VALUES (?, ?)', (e.id, deadline))
        config.db.commit()

def end_entry(config, e):
    change_state(config, e, 'done')
    clear_deadline(config, e.id)

def backlog_entry(config, e):
    change_state(config, e, 'backlog')
    clear_deadline(config, e.id)

# internal

def add_history(c, id, event):
    c.execute('INSERT INTO history (entry, date, event) VALUES (?, CURRENT_TIMESTAMP, ?)', (id, event))

def change_state(config, e, state):
    c = config.db.cursor()
    c.execute('UPDATE entry SET state = ? where rowid = ?', (state, e.id))
    add_history(c, e.id, state)
    config.db.commit()

def clear_deadline(config, id):
    c = config.db.cursor()
    c.execute('DELETE FROM deadline WHERE entry = ?', (id, ))
    config.db.commit()
