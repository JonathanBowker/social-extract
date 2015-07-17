from collections import defaultdict
import math

import click


def get_graph(node_fn, seeds, max_depth):
    '''
    Recursively extract a subgraph starting at the specified seeds and going up
    to `max_depth` hops .

    `node_fn` is a function that takes two arguments (a node ID and its name)
    and returns a `users` dict that maps IDs to usernames and a `graph` dict
    that contains the induced subgraph of the specified node.

    `max_depth` is a multiple of 0.5. If `max_depth` is a whole number (e.g. 1),
    then the graph will be extracted to that many hops, but edges between nodes
    in the final hop will not be included. If `max_depth` is not a whole number
    (e.g. 1.5), then edges between nodes in the final hop will be included.

    `seeds` is a dictionary (or iterable of 2-tuples) mapping seed node IDs to
    names.
    '''

    users = dict(seeds)
    graph = defaultdict(set)
    next_hop = dict(seeds)
    max_depth_int = math.ceil(max_depth)
    include_last_hop_nodes = max_depth_int == max_depth
    half_depth = max_depth_int != max_depth

    try:
        for depth in range(1, max_depth_int + 1):
            print('Getting graph at depth={}'.format(depth))
            hop_users = dict()
            hop_graph = defaultdict(set)

            # Get induced graphs for each node in the next hop and combine them.
            for node_id, node_name in next_hop.items():
                try:
                    node_users, node_graph = node_fn(node_id, node_name)
                except:
                    print('Failed fetching graph node id={}, name={}'
                          .format(node_id, node_name))
                    continue
                hop_users.update(node_users)
                merge_graphs(node_graph, hop_graph)

            if depth < max_depth_int:
                # This is not the last hop: add all edges.
                merge_graphs(hop_graph, graph)
            else:
                if half_depth:
                    # This is the last hop and we should include edges only
                    # between nodes already in the graph or current hop.
                    known_nodes = set(users.keys()) | set(next_hop.keys())

                    for follower, follows in hop_graph.items():
                        if follower in known_nodes:
                            graph[follower] |= (follows & known_nodes)
                else:
                    # This is the last hop and we should include edges that
                    # start or end at a node already in the graph (but not in
                    # the current hop).
                    known_nodes = set(users.keys())

                    for follower, follows in hop_graph.items():
                        if follower in known_nodes:
                            graph[follower] |= follows
                        else:
                            graph[follower] |= (follows & known_nodes)

            next_hop = {k:hop_users[k] for k in hop_users if k not in users}

            # Add users from this hop unless its the last hop in a "half" depth.
            if depth < max_depth_int or include_last_hop_nodes:
                users.update(hop_users)

    except KeyboardInterrupt:
        print('Received signal... cleaning up')

    return users, graph


def merge_graphs(source, dest):
    ''' Merge graph `source` into `dest`. '''

    for follower, follows in source.items():
        dest[follower] |= follows


def write_graph(graph, file_):
    ''' Write graph data to open file handle. '''

    for user, follows in graph.items():
        for follow in follows:
            file_.write('{}\t{}\n'.format(user, follow))


def write_users(users, file_):
    ''' Write user ID and username to open file handle. '''

    for user_id, username in users.items():
        file_.write('{}\t{}\n'.format(user_id, username))
