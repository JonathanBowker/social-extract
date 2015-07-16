from collections import defaultdict
import functools
import os
import sys
import unittest

sys.path.append(os.path.dirname(__file__))
import util


class TestSqlToJl(unittest.TestCase):
    ''' Tests for social extract functionality. '''

    def _count_edges(self, graph):
        ''' Return the number of edges in a directed graph. '''

        count = 0

        for follows in graph.values():
            count += len(follows)

        return count

    def _generate_node(self, user_id, user_name):
        '''
        Generate a directed graph around a node (identified by `id`) according
        to the following rules:

        1. A node follows nodes that begin with the same prefix and end in 0 or 1.
        2. A node is followed by nodes that begin with the same prefix and end in 2 or 3.
        3. Any node ending in 0 follows a node with the same prefix that ends in 1.

        These rules generate a simple but useful graph for testing purposes.
        '''

        users = {}
        graph = defaultdict(set)

        # Rule 1
        for i in range (0, 2):
            friend_id = '{}{}'.format(user_id, i)
            users[friend_id] = 'user{}'.format(friend_id)
            graph[user_id].add(friend_id)

        # Rule 2
        for i in range (2, 4):
            friend_id = '{}{}'.format(user_id, i)
            users[friend_id] = 'user{}'.format(friend_id)
            graph[friend_id].add(user_id)

        # Rule 3
        graph['{}0'.format(user_id)].add('{}1'.format(user_id))

        return users, graph

    def test_get_graph_depth_1(self):
        ''' Test graph generation at depth 1. '''

        node_fn = functools.partial(self._generate_node)
        users, graph = util.get_graph(node_fn, seeds={'1': 'user1'}, max_depth=1)

        # 1 seed node plus 4 adjacent nodes
        self.assertEqual(5, len(users))

        # One edge between the seed and each of its 4 neighbors.
        self.assertEqual(4, self._count_edges(graph))

        # Node 1 has 2 friends.
        self.assertEqual({'10', '11'}, graph['1'])

        # Node 1 has 2 followers.
        self.assertIn('1', graph['12'])
        self.assertIn('1', graph['13'])

        # Even though node 10 follows node 11, that edge should not be part
        # of a depth 1 graph. (It is included in depth 1.5: see below.)
        self.assertNotIn('11', graph['10'])

    def test_get_graph_depth_1_5(self):
        ''' Test graph generation at depth 1.5. '''

        node_fn = functools.partial(self._generate_node)
        users, graph = util.get_graph(node_fn, seeds={'1': 'user1'}, max_depth=1.5)

        # 1 seed node plus 4 adjacent nodes
        self.assertEqual(5, len(users))

        # All edges from test_get_graph_depth_1() are also present here, plus
        # one additional edge from 10 to 12.
        self.assertEqual(5, self._count_edges(graph))

        # Node 1 has 2 friends.
        self.assertEqual({'10', '11'}, graph['1'])

        # Node 1 has 2 followers.
        self.assertIn('1', graph['12'])
        self.assertIn('1', graph['13'])

        # Node 10 is in the user list, but node 100 is not (because we don't
        # include nodes from 2 hops).
        self.assertIn('10', users)
        self.assertNotIn('100', users)

        # Node 10 follows node 11 -- this is the key difference between this
        # test and test_get_graph_depth_1().
        self.assertIn('11', graph['10'])

    def test_get_graph_depth_2(self):
        ''' Test graph generation at depth 2. '''

        node_fn = functools.partial(self._generate_node)
        users, graph = util.get_graph(node_fn, seeds={'1': 'user1'}, max_depth=2)

        # 21 nodes: 1 seed node, 4 nodes within one hop, 16 nodes within two
        # hops.
        self.assertEqual(21, len(users))

        # 5 edges in the first hop + 4 edges * 4 nodes in the second hop.
        self.assertEqual(21, self._count_edges(graph))

        # Node 10 has 3 friends.
        self.assertEqual({'11', '100', '101'}, graph['10'])

        # Node 10 has 3 followers.
        self.assertIn('10', graph['1'])
        self.assertIn('10', graph['102'])
        self.assertIn('10', graph['103'])

        # Node 100 follows 101, but that edge should not appear in this graph.
        # It should appear in the depth=2.5 graph (see below).
        self.assertNotIn('101', graph['100'])

    def test_get_graph_depth_2_5(self):
        ''' Test graph generation at depth 2.5. '''

        node_fn = functools.partial(self._generate_node)
        users, graph = util.get_graph(node_fn, seeds={'1': 'user1'}, max_depth=2.5)

        # 21 nodes: 1 seed node, 4 nodes within one hop, 16 nodes within two
        # hops.
        self.assertEqual(21, len(users))

        # Same edges as test_get_graph_depth_2() plus 4 extra edges (100->101,
        # 110->111, 120->121, 130->131).
        self.assertEqual(25, self._count_edges(graph))

        # Node 10 has 3 friends.
        self.assertEqual({'11', '100', '101'}, graph['10'])

        # Node 10 has 3 followers.
        self.assertIn('10', graph['1'])
        self.assertIn('10', graph['102'])
        self.assertIn('10', graph['103'])

        # Node 100 follows 101. This is the main difference between this test
        # and test_get_graph_depth_2().
        self.assertIn('101', graph['100'])


if __name__ == '__main__':
    unittest.main(buffer=True)
