def write_graph(graph, file_):
    ''' Write graph data to open file handle. '''

    for user, follows in graph.items():
        for follow in follows:
            file_.write('{}\t{}\n'.format(user, follow))


def write_users(users, file_):
    ''' Write user ID and username to open file handle. '''

    for user_id, username in users.items():
        file_.write('{}\t{}\n'.format(user_id, username))
