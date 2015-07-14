#!/usr/bin/env python3

from collections import defaultdict
from hashlib import sha256
import hmac
import json
import time

import click
import requests


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
@click.option('--depth', default=1, help='Maximum number of hops from the seed user.')
@click.option('--max-follow', default=100, help='Maximum number of followers or followees to traverse per user.')
@click.argument('user_id')
@click.argument('username_file', type=click.File('w'))
@click.argument('graph_file', type=click.File('w'))
@pass_config
def graph(config, user_id, depth, max_follow, username_file, graph_file):
    '''
    Get follower/following graph.

    Starting with the seed user identified by USER_ID, construct a directed
    follower/following graph by traversing up to --depth hops (default: 1).
    For each user, fetch only --max-follow followers and followees.
    '''

    graph = defaultdict(set)
    user_map = dict()

    try:
        _get_graph(config, graph, user_map, [user_id], depth, max_follow)
    except KeyboardInterrupt:
        click.secho('Received signal: quitting', fg=red)
        _write_users(users, username_file)
        _write_graph(graph, graph_file)
        raise

    _write_users(user_map, username_file)
    _write_graph(graph, graph_file)


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


def _get_graph(config, graph, user_map, user_ids, depth, max_follow):
    ''' Helper function for getting social graph. '''

    next_hop = set()

    for user_id in user_ids:
        endpoint = '/users/{}/follows'.format(user_id)
        response = _get_instagram(config, endpoint, {'count': max_follow})

        if response.status_code != 200:
            warn = 'Warning: unable to fetch follows: {} {}'.format(
                response.status_code,
                response.payload['meta']['error_message']
            )
            click.secho(warn, fg='yellow')
            continue

        for user in response.payload['data']:
            following_id = user['id']
            following_name = user['username']

            user_map[following_id] = following_name
            graph[user_id].add(following_id)

            if following_id not in graph:
                next_hop.add(following_id)

        endpoint = '/users/{}/followed-by'.format(user_id)
        response = _get_instagram(config, endpoint, {'count': max_follow})

        if response.status_code != 200:
            warn = 'Warning: unable to fetch followed-by: {} {}'.format(
                response.status_code,
                response.payload['meta']['error_message']
            )
            click.secho(warn, fg='yellow')

        for user in response.payload['data']:
            followed_id = user['id']
            followed_name = user['username']

            user_map[followed_id] = followed_name
            graph[followed_id].add(user_id)

            if followed_id not in graph:
                next_hop.add(followed_id)

    if depth > 1:
        msg = 'Finished depth={}, moving on to depth={}'.format(depth, depth-1)
        click.secho(msg, fg='green')
        _get_graph(config, graph, user_map, list(next_hop), depth-1, max_follow)


def _write_graph(graph, file_):
    ''' Write graph data to specified file. '''

    for user, follows in graph.items():
        for follow in follows:
            file_.write('{}\t{}\n'.format(user, follow))


def _write_users(users, file_):
    ''' Write user ID and username to specified file. '''

    for user_id, username in users.items():
        file_.write('{}\t{}\n'.format(user_id, username))


if __name__ == '__main__':
    cli()
