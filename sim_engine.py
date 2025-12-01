from __future__ import annotations
import heapq
from typing import Any, Callable, List, Dict, Optional

from utils.protocol import config, Event, SimulationConfig
from utils.node import VisualNode
from utils.network import VisualNetwork, VisualSwitch


class AlgorithmLoader:
    """Auto-discover and validate algorithms from algorithms/ folder"""

    @staticmethod
    def discover_algorithms():
        """Scan algorithms folder and return dict of {name: instance or error}"""
        import os
        import importlib.util
        import inspect

        algorithms = {}
        algo_dir = os.path.join(os.path.dirname(__file__), 'algorithms')

        if not os.path.exists(algo_dir):
            return algorithms

        for filename in os.listdir(algo_dir):
            if filename.endswith('.py') and not filename.startswith('__'):
                algo_name = filename[:-3]
                filepath = os.path.join(algo_dir, filename)

                try:
                    spec = importlib.util.spec_from_file_location(
                        algo_name, filepath)
                    if spec is None or spec.loader is None:
                        algorithms[algo_name] = {
                            "error": f"Failed to load module spec"}
                        continue
                    module = importlib.util.module_from_spec(spec)
                    spec.loader.exec_module(module)

                    algo_class = None
                    for name, obj in inspect.getmembers(module):
                        if inspect.isclass(obj) and obj.__module__ == module.__name__:
                            algo_class = obj
                            break

                    if algo_class is None:
                        algorithms[algo_name] = {
                            "error": f"No class found in {filename}"}
                        continue

                    if not hasattr(algo_class, 'run'):
                        algorithms[algo_name] = {
                            "error": f"Missing required run(nodes, step_count) method"}
                        continue

                    if not callable(getattr(algo_class, 'run')):
                        algorithms[algo_name] = {
                            "error": f"run must be a callable method"}
                        continue

                    algorithms[algo_name] = {
                        "instance": algo_class(), "error": None}

                except Exception as e:
                    algorithms[algo_name] = {
                        "error": f"Failed to load: {str(e)}"}

        return algorithms


class AlgorithmController:
    def __init__(self, simulator=None):
        self.algorithms = {}
        self.validation_errors = {}
        self.active_algorithm_name = None
        self.is_paused = False
        self.simulator = simulator

    def register_algorithm(self, name, algorithm_instance):
        self.algorithms[name] = algorithm_instance

    def set_active(self, name):
        if name in self.algorithms:
            self.active_algorithm_name = name
            self.is_paused = False
        elif name in self.validation_errors:
            self.is_paused = True
            if config.reset_on_error and self.simulator:
                self.simulator.reset()

    def execute(self, nodes, step_count):
        if self.is_paused or not self.active_algorithm_name:
            return
        if self.active_algorithm_name in self.algorithms:
            self.algorithms[self.active_algorithm_name].run(nodes, step_count)


class VisualSimulator:
    def __init__(self):
        self.time = 0.0
        self.events = []
        self.nodes = {}
        self.network = None
        self.running = False
        self.algorithm_controller = AlgorithmController(self)

        self.message_history = []
        self.logs = []

        self.initial_nodes_config = []
        
        # Metrics collection
        from utils.metrics import MetricsCollector
        self.metrics = MetricsCollector()
        self.metrics.start_time = 0.0
        
        # Clock drift modeling
        from utils.protocol import ClockDrift
        self.clock_drift = ClockDrift(max_drift=config.max_clock_drift)

    def register_node(self, node):
        self.nodes[node.node_id] = node
        node.attach_simulator(self)

    def remove_node(self, node_id: str):
        """Remove a node from the simulation"""
        if node_id in self.nodes:
            del self.nodes[node_id]
            self.log(node_id, "Server removed")
            return True
        return False

    def toggle_node_power(self, node_id: str):
        """Toggle power state of a node"""
        node = self.nodes.get(node_id)
        if node:
            if node.is_shutdown:
                node.is_shutdown = False
                node.state = "IDLE"
                self.log(node_id, "Server restarted")
            else:
                node.is_shutdown = True
                node.state = "SHUTDOWN"
                self.log(node_id, "Server shutdown")

    def register_network(self, network):
        self.network = network
        network.attach_simulator(self)

    def schedule(self, delay: float, callback: Callable, *args, **kwargs):
        event_time = self.time + delay
        event = Event(timestamp=event_time, priority=1,
                      callback=callback, args=args, kwargs=kwargs)
        heapq.heappush(self.events, event)

    def step(self, delta_time: float):
        """Run the simulation for `delta_time` seconds."""
        target_time = self.time + delta_time

        while self.events and self.events[0].timestamp <= target_time:
            event = heapq.heappop(self.events)
            self.time = event.timestamp
            event.callback(*event.args, **event.kwargs)

        self.time = target_time

    def log(self, node_id: str, message: str):
        self.logs.append((self.time, node_id, message))
        if len(self.logs) > 100:
            self.logs.pop(0)

    def save_initial_state(self, nodes_config):
        """Save initial node configuration for reset. 
        nodes_config: list of dicts with keys: node_id, ip_address, rack_id, cores, ram_gb"""
        self.initial_nodes_config = nodes_config

    def reset(self):
        """Reset simulation to initial state"""
        self.nodes.clear()
        self.time = 0.0
        self.events.clear()
        self.message_history.clear()
        self.logs.clear()
        
        # Reset metrics and clock drift
        self.metrics.reset()
        self.clock_drift.reset()

        if self.network:
            net = VisualNetwork(latency=self.network.latency)
            self.register_network(net)

        recreated_nodes = []
        for node_config in self.initial_nodes_config:
            node = VisualNode(**node_config)
            self.register_node(node)
            recreated_nodes.append(node)

        return recreated_nodes
