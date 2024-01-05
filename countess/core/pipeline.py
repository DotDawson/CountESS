from typing import Any, Optional
from threading import Thread
from queue import Queue
import time

from countess.core.logger import Logger
from countess.core.plugins import BasePlugin, get_plugin_classes

PRERUN_ROW_LIMIT = 100000

# Indicates that a node is "finished" and will not send any further
# data
# XXX probably better ways to be a sentinel
class FINISHED_SENTINEL:
    pass

class PipelineNode:
    name: str
    plugin: Optional[BasePlugin] = None
    position: Optional[tuple[float, float]] = None
    notes: Optional[str] = None
    parent_nodes: set["PipelineNode"]
    child_nodes: set["PipelineNode"]
    config: Optional[list[tuple[str, str, str]]] = None
    result: Any = None
    is_dirty: bool = True

    queue: Optional[Queue] = None
    counter: int = 0

    # XXX config is a cache for config loaded from the file
    # at config load time, if it is present it is loaded the
    # first time the plugin is prerun.

    def __init__(self, name, plugin=None, config=None, position=None, notes=None):
        self.name = name
        self.plugin = plugin
        self.config = config or []
        self.position = position
        self.notes = notes
        self.parent_nodes = set()
        self.child_nodes = set()
        self.output_queues = set()

    def __hash__(self):
        return id(self)

    def is_ancestor_of(self, node):
        return (self in node.parent_nodes) or any((self.is_ancestor_of(n) for n in node.parent_nodes))

    def is_descendant_of(self, node):
        return (self in node.child_nodes) or any((self.is_descendant_of(n) for n in node.child_nodes))

    def plugin_process(self, x):
        self.plugin.process(*x)

    def queue_to_child_nodes(self, data_iterable):
        for data in data_iterable:
            # XXX can we do this out-of-order if any queues are full?
            for child_node in self.child_nodes:
                child_node.queue.put((self.name, data))

    def run_thread(self, logger, row_limit: Optional[int] = None):
        # XXX using node.name for sources isn't great
        # XXX this is not a good sentinel value either

        self.queue = Queue(maxsize=3)
        self.counter = 0

        sources = { pn.name for pn in self.parent_nodes }
        if not sources:
            for data_out in self.plugin.execute(self.name, {}, logger, row_limit):
                self.counter += 1
                self.queue_to_child_nodes([data_out])
        else:
            self.plugin.prepare(list(sources), row_limit)
            while sources:
                source, data_in = self.queue.get()
                self.counter += 1
                assert source in sources
                if data_in is FINISHED_SENTINEL:
                    self.queue_to_child_nodes(self.plugin.finished(source, logger))
                    sources.remove(source)
                else:
                    self.queue_to_child_nodes(self.plugin.process(data_in, source, logger))
            self.queue_to_child_nodes(self.plugin.finalize(logger))

        self.queue_to_child_nodes([FINISHED_SENTINEL])
        self.queue = None

    def execute(self, logger: Logger, row_limit: Optional[int] = None):
        assert row_limit is None or isinstance(row_limit, int)

        if self.plugin is None:
            self.result = []
            return

        elif row_limit is not None and self.result and not self.is_dirty:
            return

        sources = {pn.name: pn.result for pn in self.parent_nodes}
        self.result = self.plugin.execute(self.name, sources, logger, row_limit)

        # XXX at the moment, we freeze the results into an array
        # if we have multiple children, as *both children* will be
        # drawing items from the array.  This isn't the most efficient
        # strategy.

        if row_limit is not None or len(self.child_nodes) != 1:
            self.result = list(self.result)

        self.is_dirty = False

    def load_config(self, logger: Logger):
        assert isinstance(self.plugin, BasePlugin)
        if self.config:
            for key, val, base_dir in self.config:
                try:
                    self.plugin.set_parameter(key, val, base_dir)
                except (KeyError, ValueError):
                    logger.warning(f"Parameter {key}={val} Not Found")
            self.config = None

    def prerun(self, logger: Logger, row_limit=PRERUN_ROW_LIMIT):
        assert isinstance(logger, Logger)

        if self.is_dirty and self.plugin:
            for parent_node in self.parent_nodes:
                parent_node.prerun(logger, row_limit)
            self.load_config(logger)
            self.execute(logger, row_limit)
            self.is_dirty = False

    def mark_dirty(self):
        self.is_dirty = True
        for child_node in self.child_nodes:
            if not child_node.is_dirty:
                child_node.mark_dirty()

    def add_parent(self, parent):
        self.parent_nodes.add(parent)
        parent.child_nodes.add(self)
        self.mark_dirty()

    def del_parent(self, parent):
        self.parent_nodes.discard(parent)
        parent.child_nodes.discard(self)
        self.mark_dirty()

    def has_sibling(self):
        return any(len(pn.child_nodes) > 1 for pn in self.parent_nodes)

    def configure_plugin(self, key, value, base_dir="."):
        self.plugin.set_parameter(key, value, base_dir)
        self.mark_dirty()

    def final_descendants(self):
        if self.child_nodes:
            return set(n2 for n1 in self.child_nodes for n2 in n1.final_descendants())
        else:
            return set(self)

    def detatch(self):
        for parent_node in self.parent_nodes:
            parent_node.child_nodes.discard(self)
        for child_node in self.child_nodes:
            child_node.parent_nodes.discard(self)

    @classmethod
    def get_ancestor_list(cls, nodes):
        """Given a bunch of nodes, find the list of all the ancestors in a
        sensible order"""
        parents = set((p for n in nodes for p in n.parent_nodes))
        if not parents:
            return list(nodes)
        return cls.get_ancestor_list(parents) + list(nodes)


class PipelineGraph:
    # XXX doesn't actually do much except hold a bag of nodes

    # XXX should be an actual sentinel

    def __init__(self):
        self.plugin_classes = get_plugin_classes()
        self.nodes = []

    def add_node(self, node):
        self.nodes.append(node)

    def del_node(self, node):
        node.detatch()
        self.nodes.remove(node)

    def traverse_nodes(self):
        found_nodes = set(node for node in self.nodes if not node.parent_nodes)
        yield from found_nodes

        while len(found_nodes) < len(self.nodes):
            for node in self.nodes:
                if node not in found_nodes and node.parent_nodes.issubset(found_nodes):
                    yield node
                    found_nodes.add(node)

    def traverse_nodes_backwards(self):
        found_nodes = set(node for node in self.nodes if not node.child_nodes)
        yield from found_nodes

        while len(found_nodes) < len(self.nodes):
            for node in self.nodes:
                if node not in found_nodes and node.child_nodes.issubset(found_nodes):
                    yield node
                    found_nodes.add(node)


    def run(self, logger):
        # XXX this is the last thing PipelineGraph actually does!
        # might be easier to just keep a set of nodes and sort through
        # them for output nodes, or something.

        threads = []
        for node in self.traverse_nodes_backwards():
            node.load_config(logger)
            threads.append(Thread(target=node.run_thread, args=(logger,)))

        for thread in threads:
            thread.start()

        while True:
            print("------------------")
            for node in self.traverse_nodes():
                print("%-40s %d %d" % (node.name, node.counter, node.queue.qsize() if node.queue else -1))
            if not any(t.is_alive() for t in threads):
                break
            time.sleep(1)

    def reset(self):
        for node in self.nodes:
            node.result = None
            node.is_dirty = True

    def tidy(self):
        """Tidies the graph (sets all the node positions)"""

        # XXX This is very arbitrary and not particularly efficient.
        # Some kind of FDP-like algorithm might be nice.
        # Especially if it could include node/line collisions.
        # See #24

        nodes = list(self.traverse_nodes())

        # first calculate a stratum for each node.

        stratum = {}
        for node in nodes:
            if not node.parent_nodes:
                stratum[node] = 0
            else:
                stratum[node] = max(stratum[n] for n in node.parent_nodes) + 1

        # shufffle nodes back down to avoid really long connections.

        for node in nodes[::-1]:
            if node.child_nodes:
                if len(node.parent_nodes) == 0:
                    stratum[node] = min(stratum[n] for n in node.child_nodes) - 1
                else:
                    stratum[node] = (
                        min(stratum[n] for n in node.child_nodes) + max(stratum[n] for n in node.parent_nodes)
                    ) // 2

        max_stratum = max(stratum.values())

        position = {}
        for s in range(0, max_stratum + 1):
            # now sort all the nodes by the average position of their parents,
            # to try and stop them forming a big tangle.  The current position
            # is included as a "tie breaker" and to keep some memory of the user's
            # preference for position (eg: ordering of branches)

            def avg_pos_parents(node):
                return sum(position[p] for p in node.parent_nodes) / len(node.parent_nodes)

            snodes = [
                (
                    avg_pos_parents(node) if node.parent_nodes else 0.5,
                    node.position[1],
                    n,
                )
                for n, node in enumerate(nodes)
                if stratum[node] == s
            ]
            snodes.sort()

            # Assign node positions with the stratums placed
            # evenly and the nodes spaced evenly per stratum.

            y = (s + 0.5) / (max_stratum + 1)
            for p, (_, _, n) in enumerate(snodes):
                x = (p + 0.5) / len(snodes)
                nodes[n].position = (y, x)
                position[nodes[n]] = x
