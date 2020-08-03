# Sync issues with GitHub account

import configparser
import pprint
import os
import sys
import requests
from pathlib import Path
from teenypm import Entry

API_USER_KEY = 'github.api.user'
API_REPO_KEY = 'github.api.repo'

TOKEN_FILE = Path.home() / '.teenypm' / 'github.conf'

def parse_git_config():
    info = {}
    if os.path.isfile('.git/config'):
        git_config = configparser.ConfigParser()
        git_config.read('.git/config')

        if 'remote "origin"' in git_config:
            url = git_config['remote "origin"']['url'].split('/')
            info['user'] = url[-2]
            info['repo'] = url[-1].split('.')[0]

    return info

def quiet_input(msg, default):
    try:
        value = input('{} [{}]: '.format(msg, default))
        if value == '':
            if default == '':
                print('Cancelled GitHub setup')
                sys.exit(0)

            return default
        return value

    except KeyboardInterrupt:
        print('\nExiting remote setup')
        sys.exit(0)

def setup(config):
    defaults = parse_git_config()

    config[API_USER_KEY] = quiet_input('Enter the GitHub user for API access', defaults.get('user', ''))
    api_token = quiet_input('Enter your GitHub access token', '')
    config[API_REPO_KEY] = quiet_input('Enter the GitHub repo', defaults.get('repo', ''))
 
    project_id = config['project.id']
    TOKEN_FILE.parent.mkdir(parents=True, exist_ok=True)
    with TOKEN_FILE.open('a') as fh:
        fh.write('{}={}\n'.format(project_id, api_token))

    return True

def remove(config):
    config.pop(API_USER_KEY, None)
    config.pop(API_REPO_KEY, None)

    project_id = config['project.id']
    lines = []

    with TOKEN_FILE.open() as fh:
        for line in fh:
            if not line.startswith(project_id):
                lines.append(line)

    with TOKEN_FILE.open('w') as fh:
        fh.writelines(lines)

def fetch_issues(config, tags = [], id = None):
    # FIXME: filter by tags / id
    ghi = github_request(config, 'GET', '/repos/{owner}/{repo}/issues')
    if ghi == None:
        return []

    issues = []
    for issue in ghi:
        if 'pull_request' in issue:
            continue

        remote_id = str(issue['number'])
        msg = issue['title']
        if issue['body'] != '':
            msg = '{}\n\n{}'.format(issue['title'], issue['body'])

        tags = [label['name'] for label in issue['labels']]
        if len(tags) == 0:
            tags.append('task')

        if issue['state'] == 'closed':
            state = 'done'
        else:
            state = 'backlog'

        issues.append(Entry(None, state, msg, 1, remote_id, tags, [], None))

    return issues

def add_entry(config, e):
    msg_parts = list(filter(lambda line: line != '', e.msg.split('\n')))
    body = ''
    if len(msg_parts) > 1:
        body = msg_parts[1]

    remote_issue = github_request(config, 'POST', '/repos/{owner}/{repo}/issues', {
        'title': msg_parts[0],
        'body': body,
        'labels': e.tags
    })

    e.remote_id = remote_issue['number']

def update_entry(config, e, msg):
    msg_parts = list(filter(lambda line: line != '', msg.split('\n')))
    body = ''
    if len(msg_parts) > 1:
        body = msg_parts[1]

    github_request(config, 'POST', '/repos/{owner}/{repo}/issues/' + e.remote_id, {
        'title': msg_parts[0],
        'body': body
    })

def remove_entry(config, e):
    change_state(config, e, 'closed')
    print('NOTE: Cannot delete the issue in GitHub - closed it instead')

def tag_entry(config, e, tag):
    github_request(config, 'POST', '/repos/{owner}/{repo}/issues/' + e.remote_id + '/labels', {
        'labels': [ tag ]
    })

def untag_entry(config, e, tag):
    github_request(config, 'DELETE', '/repos/{owner}/{repo}/issues/' + e.remote_id + '/labels/' + tag)

def add_feature(config, tag):
    pass

def remove_feature(config, tag):
    pass

def start_entry(config, e, deadline = None):
    change_state(config, e, 'open')

def end_entry(config, e):
    change_state(config, e, 'closed')

def backlog_entry(config, e):
    change_state(config, e, 'open')

def change_state(config, e, state):
    github_request(config, 'PATCH', '/repos/{owner}/{repo}/issues/' + e.remote_id, {
        'state': state
    })

def github_request(config, method, path, data = None):
    project_id = config['project.id']
 
    with TOKEN_FILE.open() as fh:
        for line in fh:
            if line.startswith(project_id):
                api_token = line.rstrip().split('=')[1]
                break

    if not api_token:
        print('Error - no GitHub token configured')
        return None

    url = 'https://api.github.com' + path.format(owner = config[API_USER_KEY], repo = config[API_REPO_KEY])
    result = requests.request(method, url, auth=(config[API_USER_KEY], api_token), json = data)

    if result.status_code >= 200 and result.status_code < 300:
        return result.json()
    else:
        print('GitHub API error - {}: {}'.format(result.status_code, result.json()['message']))
        return None
