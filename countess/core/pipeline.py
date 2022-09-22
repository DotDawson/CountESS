import logging
from importlib.metadata import entry_points
from typing import Type

from countess.core.plugins import BasePlugin


class Pipeline:
    """Represents a series of plugins linked up to each other.  Plugins can be added
    and removed from the pipeline if they are able to deal with each other's input"""

    def __init__(self):
        self.plugins: list[BasePlugin] = []
        self.plugin_classes: list[Type[BasePlugin]] = []

        for ep in entry_points(group="countess_plugins"):
            plugin_class = ep.load()
            if issubclass(plugin_class, BasePlugin):
                self.plugin_classes.append(plugin_class)
            else:
                logging.warning(f"{plugin_class} is not a valid CountESS plugin")

    def add_plugin(self, plugin: BasePlugin, position: int = None):
        """Adds a plugin at `position`, if that's possible.
        It might not be possible if the plugin chain would not be compatible,
        in which case we throw an assertion error"""
        # XXX would it be easier to pass an "after: Plugin" instead of position?

        if position is None:
            position = len(self.plugins)
        assert 0 <= position <= len(self.plugins)
        if position > 0:
            previous_plugin = self.plugins[position - 1]
            assert plugin.can_follow(previous_plugin)
        else:
            previous_plugin = None

        if position < len(self.plugins):
            next_plugin = self.plugins[position]
            assert next_plugin.can_follow(plugin)
        else:
            next_plugin = None

        self.plugins.insert(position, plugin)

        if previous_plugin:
            plugin.set_previous_plugin(previous_plugin)
            plugin.update()
        if next_plugin:
            next_plugin.set_previous_plugin(plugin)

    def del_plugin(self, position: int):
        """Deletes the plugin at `position` if that's possible.
        It might not be possible if the plugins before and after the deletion aren't compatible,
        in which case we throw an assertion error"""
        # XXX would it be easier to pass "plugin: Plugin" instead of position?

        assert 0 <= position < len(self.plugins)

        previous_plugin = self.plugins[position - 1] if position > 0 else None

        if position < len(self.plugins) - 1:
            next_plugin = self.plugins[position + 1]
            assert next_plugin.can_follow(previous_plugin)
        else:
            next_plugin = None

        self.plugins.pop(position)

        if next_plugin:
            next_plugin.set_previous_plugin(previous_plugin)
            next_plugin.update()

    def move_plugin(self, position: int, new_position: int):
        assert 0 <= position < len(self.plugins)
        assert 0 <= new_position < len(self.plugins)

        # XXX TODO
        raise NotImplementedError("surprisingly involved")

    def update_plugin(self, position: int):
        """Updates the plugin at `position` and then all the subsequent plugins,
        to allow changes to carry through the pipeline"""
        assert 0 <= position < len(self.plugins)
        for plugin in self.plugins[position:]:
            plugin.update()

    def choose_plugin_classes(self, position: int):
        if position is None:
            position = len(self.plugins)

        previous_plugin_class = (
            self.plugins[position - 1].__class__ if position > 0 else None
        )
        next_plugin_class = (
            self.plugins[position].__class__ if position < len(self.plugins) else None
        )

        for plugin_class in self.plugin_classes:
            if plugin_class.can_follow(previous_plugin_class):
                if next_plugin_class is None or next_plugin_class.can_follow(
                    plugin_class
                ):
                    yield plugin_class