#!/usr/bin/env python3

from collections import defaultdict
import functools
import json
import os
import pickle
import sys

import bs4
import click
import requests

sys.path.append(os.path.dirname(__file__))
from util import get_graph, write_graph, write_users


TWITTER_URL = 'https://twitter.com/'


class Config(object):
    ''' Keeps track of configuration. '''

    def __init__(self):
        self.debug = False
        self.password = None
        self.session = None
        self.twitter_url = TWITTER_URL.rstrip('/')
        self.user = None


pass_config = click.make_pass_decorator(Config, ensure=True)


@click.group()
@click.option('--user',
              envvar='TWITTER_USER',
              help='Twitter user to log in as (required, or export ' \
                   'TWITTER_USER)')
@click.option('--password',
              envvar='TWITTER_PASSWORD',
              help='Twitter password to log in with (required, or export ' \
                   'TWITTER_PASSWORD)')
@click.option('--url', help='URL for Twitter (default: {})'.format(TWITTER_URL))
@click.option('--session',
              type=click.File('rb+', lazy=False),
              help='Path to save/load session file to/from (if not specified, ' \
                   'the session will not be loaded/saved)')
@pass_config
def cli(config, user, password, url, session):
    config.user = user
    config.password = password
    config.session = session

    if url is not None:
        config.url = url.rstrip('/')


@cli.command()
@click.option('--depth',
              type=float,
              default=1,
              help='Maximum number of hops from the seed user.')
@click.option('--max-follow',
              default=100,
              help='Maximum number of followers or followees to traverse per ' \
                   'user. (May exceed this size a bit because it breaks on ' \
                   'page boundaries.)')
@click.argument('username')
@click.argument('username_file', type=click.File('w', lazy=False))
@click.argument('graph_file', type=click.File('w', lazy=False))
@pass_config
def graph(config, depth, max_follow, username, username_file, graph_file):
    ''' Get a twitter user's friends/follower graph. '''

    session = _login_twitter(config)

    # Get user ID.
    home_url = '{}/{}'.format(config.twitter_url, username)
    response = session.get(home_url)

    if response.status_code != 200:
        raise click.ClickException('Not able to get home page for {}. ({})'
                                   .format(username, response.status_code))

    html = bs4.BeautifulSoup(response.text, 'html.parser')
    profile_el = html.select('.ProfileNav-item--userActions .user-actions')[0]
    user_id = profile_el['data-user-id']

    # Get graph.
    node_fn = functools.partial(_get_graph, session, config, max_follow)
    users, graph = get_graph(node_fn, {user_id: username}, depth)

    write_users(users, username_file)
    write_graph(graph, graph_file)

    click.secho('Finished: {} nodes'.format(len(users)))


@cli.command('id')
@click.argument('username')
@pass_config
def id_(config, username):
    ''' Get a twitter user ID for USERNAME. '''

    session = _login_twitter(config)

    home_url = '{}/{}'.format(config.twitter_url, username)
    response = session.get(home_url)

    if response.status_code != 200:
        raise click.ClickException('Not able to get home page for {}. ({})'
                                   .format(username, response.status_code))

    html = bs4.BeautifulSoup(response.text, 'html.parser')
    profile_el = html.select('.ProfileNav-item--userActions .user-actions')[0]
    user_id = profile_el['data-user-id']

    click.secho('{} has ID {}'.format(username, user_id))


def _get_graph(session, config, max_follow, user_id, username):
    '''
    Fetch friends (a.k.a. "following") and followers.

    Returns a tuple:

        0. dictionary mapping ID to username
        1. dictionary mapping each ID to its `set` of followers
    '''

    users = dict()
    graph = defaultdict(set)

    # Fetch first page.
    following_url = '{}/{}/following'.format(config.twitter_url, username)
    click.echo('Getting {}'.format(following_url))
    response = session.get(following_url)

    if response.status_code != 200:
        click.secho('Not able to fetch friends: ()'.format(response.status_code))

    html = bs4.BeautifulSoup(response.text, 'html.parser')

    user_el = html.select('.ProfileNav-item--userActions')[0]
    user_id = user_el.select('.user-actions')[0]['data-user-id']

    click.secho('User "{}" has ID {}.'.format(username, user_id), fg='green')

    try:
        position_el = html.select('.GridTimeline-items')[0]
    except IndexError:
        click.secho('Not able to get friends for {}'.format(username))
        return users, graph

    min_position = position_el['data-min-position']

    click.secho('First page min position: {}'.format(min_position))

    profile_els = html.select('.ProfileCard-content')
    friends = 0

    for profile_el in profile_els:
        profile = profile_el.select('.user-actions')[0]
        following_id = profile['data-user-id']
        following_name = profile['data-screen-name']

        users[following_id] = following_name
        graph[user_id].add(following_id)
        friends += 1

    # Fetch remaining pages.
    following_page_url = '{}/{}/following/users'.format(config.twitter_url, username)

    params = {
        'include_available_features': '1',
        'include_entities': '1',
        'max_position': min_position,
    }

    while True:
        click.echo('Getting {} with max position {}'
                   .format(following_page_url, params['max_position']))
        response = session.get(following_page_url, params=params)
        body = response.json()
        html = bs4.BeautifulSoup(body['items_html'], 'html.parser')

        for profile_el in html.select('.user-actions'):
            following_id = profile_el['data-user-id']
            following_name = profile_el['data-screen-name']

            users[following_id] = following_name
            graph[user_id].add(following_id)
            friends += 1

        if friends >= max_follow:
            break

        if body['has_more_items']:
            params['max_position'] = body['min_position']
        else:
            break

    # Fetch first page.
    following_url = '{}/{}/followers'.format(config.twitter_url, username)
    click.echo('Getting {}'.format(following_url))
    response = session.get(following_url)

    if response.status_code != 200:
        click.secho('Not able to fetch friends: ()'.format(response.status_code))

    html = bs4.BeautifulSoup(response.text, 'html.parser')

    try:
        position_el = html.select('.GridTimeline-items')[0]
    except IndexError:
        click.secho('Not able to get followers for {}'.format(username))
        return users, graph

    min_position = position_el['data-min-position']

    click.secho('First page min position: {}'.format(min_position))

    profile_els = html.select('.ProfileCard-content')
    followers = 0

    for profile_el in profile_els:
        profile = profile_el.select('.user-actions')[0]
        follower_id = profile['data-user-id']
        follower_name = profile['data-screen-name']

        users[follower_id] = follower_name
        graph[follower_id].add(user_id)
        followers += 1

    # Fetch remaining pages.
    following_page_url = '{}/{}/followers/users'.format(config.twitter_url, username)

    params = {
        'include_available_features': '1',
        'include_entities': '1',
        'max_position': min_position,
    }

    while True:
        click.echo('Getting {} with max position {}'
                   .format(following_page_url, params['max_position']))
        response = session.get(following_page_url, params=params)
        body = response.json()
        html = bs4.BeautifulSoup(body['items_html'], 'html.parser')

        for profile_el in html.select('.user-actions'):
            follower_id = profile_el['data-user-id']
            follower_name = profile_el['data-screen-name']

            users[follower_id] = follower_name
            graph[follower_id].add(user_id)
            followers += 1

        if followers >= max_follow:
            break

        if body['has_more_items']:
            params['max_position'] = body['min_position']
        else:
            break

    return users, graph


def _login_twitter(config):
    '''
    Log into a Twitter account and return a session.

    If a session file exists in `config`, then that session will be deserialized
    and returned instead of creating a new session.
    '''

    if config.session is not None:
        try:
            click.echo('Loading session from: {}'.format(config.session.name))
            session = pickle.load(config.session)
            return session
        except:
            click.secho('No session found! Falling back to login.', fg='red')

    click.echo('Logging in to Twitter...')
    session = requests.Session()
    home_url = '{}/login'.format(config.twitter_url)
    home_response = session.get(home_url)

    if home_response.status_code != 200:
        raise click.ClickException(
            'Not able to fetch Twitter home page: {}'
            .format(home_response.status_code)
        )

    page = bs4.BeautifulSoup(home_response.text, 'html.parser')
    csrf_selector = 'input[name=authenticity_token]'
    csrf_elements = page.select(csrf_selector)

    if len(csrf_elements) == 0:
        raise click.ClickException(
            'Expected >=1 elements matching selector "{}", found 0 instead.'
            .format(csrf_selector)
        )

    # There may be more than one CSRF element but they should all have the same
    # value, so we arbitrarily take the first one.
    csrf_token = csrf_elements[0]['value']
    click.echo('Got CSRF token: {}'.format(csrf_token))

    login_url = '{}/sessions'.format(config.twitter_url)

    payload = {
        'authenticity_token': csrf_token,
        'session[username_or_email]': config.user,
        'session[password]': config.password,
        'remember_me': '1',
        'return_to_ssl': 'true',
    }

    login_response = session.post(login_url,
                                  data=payload,
                                  allow_redirects=False)

    if login_response.status_code != 302:
        raise click.ClickException(
            'Not able to log in to Twitter: {}'
            .format(login_response.status_code)
        )
    elif login_response.headers['Location'].startswith(home_url):
        # This indicates that we're being redirected to the login form, e.g.
        # an unsuccessful login attemp.
        raise click.ClickException(
            'Not able to log in to Twitter: probably a bad username or password'
            .format(login_response.status_code)
        )

    click.secho('Logged in successfully!', fg='green')

    if config.session is not None:
        click.echo('Writing session to file: {}'.format(config.session.name))
        pickle.dump(session, config.session)

    return session


if __name__ == '__main__':
    cli()
