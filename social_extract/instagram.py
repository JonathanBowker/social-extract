#!/usr/bin/env python3

from collections import defaultdict
import functools
from hashlib import sha256
import hmac
import json
import os
import sys
import time

import click
import requests

sys.path.append(os.path.dirname(__file__))
from util import get_graph, write_graph, write_users


API_URL = 'https://api.instagram.com/v1'


class Config(object):
    ''' Keeps track of configuration. '''

    def __init__(self):
        self.api_url = API_URL
        self.client_id = None
        self.client_secret = None
        self.debug = False


pass_config = click.make_pass_decorator(Config, ensure=True)


@click.group()
@click.option('--client-id',
              envvar='INSTAGRAM_CLIENT_ID',
              help='Your client ID (required, or export INSTAGRAM_CLIENT_ID)')
@click.option('--client-secret',
              envvar='INSTAGRAM_CLIENT_SECRET',
              help='Your client secret (required, or export INSTAGRAM_CLIENT_SECRET)')
@pass_config
def cli(config, client_id, client_secret):
    if client_id is None:
        raise click.ClickException('Client ID is required.')
    config.client_id = client_id
    config.client_secret = client_secret


@cli.command('id')
@click.argument('username')
@pass_config
def id_(config, username):
    ''' Get an instagram user's ID. '''

    endpoint = '/users/search'
    response = _get_instagram(config, endpoint, {'q': username})

    if response.status_code != 200:
        raise click.ClickException(
            'Unable to perform search: {} {}'
            .format(response.status_code, response.payload['meta']['error_message'])
        )

    for user in response.payload['data']:
        click.echo('{:>20} {}'.format(user['username'], user['id']))


@cli.command()
@click.argument('user_id')
@pass_config
def info(config, user_id):
    '''
    Get biographical data for a user.

    Get data for the user identified by USER_ID.
    '''

    endpoint = '/users/{}'.format(user_id)
    response = _get_instagram(config, endpoint)

    if response.status_code == 200:
        click.echo(response.text)
    else:
        raise click.ClickException(
            'Unable to fetch user information: {} {}'
            .format(response.status_code, response.payload['meta']['error_message'])
        )


@cli.command()
@click.option('--depth',
              type=float,
              default=1,
              help='Maximum number of hops from the seed user.')
@click.option('--max-follow',
              default=100,
              help='Maximum number of followers or followees to traverse per user.')
@click.argument('user_id')
@click.argument('username_file', type=click.File('w', lazy=False))
@click.argument('graph_file', type=click.File('w', lazy=False))
@pass_config
def graph(config, user_id, depth, max_follow, username_file, graph_file):
    '''
    Get follower/following graph.

    Starting with the seed user identified by USER_ID, construct a directed
    follower/following graph by traversing up to --depth hops (default: 1).
    For each user, fetch only --max-follow followers and followees.
    '''

    # Get username for this user_id.
    endpoint = '/users/{}'.format(user_id)
    response = _get_instagram(config, endpoint)

    if response.status_code != 200:
        raise click.ClickException(
            'Unable to fetch user information: {} {}'
            .format(response.status_code, response.payload['meta']['error_message'])
        )

    user_info = json.loads(response.text)
    username = user_info['data']['username']

    # Get graph.
    node_fn = functools.partial(_get_graph, config, max_follow)
    users, graph = get_graph(node_fn, {user_id: username}, depth)

    write_users(users, username_file)
    write_graph(graph, graph_file)

    click.secho('Finished: {} nodes'.format(len(users)))


def _get_instagram(config, endpoint, params={}):
    ''' Get a resource from instagram. '''

    signature = hmac.new(
        key=config.client_secret.encode('utf8'),
        msg=endpoint.encode('utf8'),
        digestmod=sha256
    )

    params['client_id'] = config.client_id

    for key in sorted(params.keys()):
        signature.update('|{}={}'.format(key, params[key]).encode('utf8'))

    params['sig'] = signature.hexdigest()
    url = '{}/{}'.format(config.api_url, endpoint.lstrip('/'))
    click.echo('Requesting: {}'.format(url))
    response = requests.get(url, params=params)

    while response.status_code == 429:
        err = 'Error: over the rate limit! (Will try again in 5 minutes.)'
        click.secho(err, fg='red')
        time.sleep(300)
        click.echo('Requesting (again): {}'.format(url))
        response = requests.get(url, params=params)

    response.payload = response.json()
    response.rate_limit = int(response.headers['X-Ratelimit-Remaining'])

    if response.rate_limit <= 5:
        warn = 'Warning: rate limit is low ({})!'.format(response.rate_limit)
        click.secho(warn, fg='yellow')

    return response


def _get_graph(config, max_follow, user_id, user_name):
    ''' Helper function for getting social graph. '''

    users = dict()
    graph = defaultdict(set)

    # Get follows.
    endpoint = '/users/{}/follows'.format(user_id)
    response = _get_instagram(config, endpoint, {'count': max_follow})

    if response.status_code == 200:
        for user in response.payload['data']:
            following_id = user['id']
            following_name = user['username']

            users[following_id] = following_name
            graph[user_id].add(following_id)
    else:
        warn = 'Warning: unable to fetch follows: {} {}'.format(
            response.status_code,
            response.payload['meta']['error_message']
        )
        click.secho(warn, fg='yellow')

    # Get followers.
    endpoint = '/users/{}/followed-by'.format(user_id)
    response = _get_instagram(config, endpoint, {'count': max_follow})

    if response.status_code == 200:
        for user in response.payload['data']:
            followed_id = user['id']
            followed_name = user['username']

            users[followed_id] = followed_name
            graph[followed_id].add(user_id)
    else:
        warn = 'Warning: unable to fetch followed-by: {} {}'.format(
            response.status_code,
            response.payload['meta']['error_message']
        )
        click.secho(warn, fg='yellow')

    return users, graph


if __name__ == '__main__':
    cli()
