from __future__ import annotations
import heapq
import random
from dataclasses import dataclass, field
from typing import Any, Callable, List, Dict, Optional


@dataclass
class SimulationConfig:
    idle_spike_prob: float = 0.1
    log_rotation_prob: float = 0.05
    hw_fault_prob: float = 0.005
    fault_clear_prob: float = 0.05
    power_failure_prob: float = 0.5

    critical_threshold: float = 90.0
    disk_growth_rate: float = 0.05

    reset_on_error: bool = True

config = SimulationConfig()

@dataclass(order=True)
class Event:
    timestamp: float
    priority: int
    callback: Callable = field(compare=False)
    args: tuple = field(default=(), compare=False)
    kwargs: dict = field(default_factory=dict, compare=False)


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

        if self.network:
            net = VisualNetwork(latency=self.network.latency)
            self.register_network(net)

        recreated_nodes = []
        for node_config in self.initial_nodes_config:
            node = VisualNode(**node_config)
            self.register_node(node)
            recreated_nodes.append(node)

        return recreated_nodes


class VisualNetwork:
    def __init__(self, latency=0.5):
        self.simulator: Optional['VisualSimulator'] = None
        self.latency = latency
        self.switches: Dict[str, 'VisualSwitch'] = {}

    def attach_simulator(self, simulator: 'VisualSimulator'):
        self.simulator = simulator

    def register_switch(self, switch: 'VisualSwitch'):
        """Register a switch with the network"""
        self.switches[switch.switch_id] = switch
        if self.simulator:
            switch.attach_simulator(self.simulator)

    def send(self, src_id: str, dst_id: str, message: Any):
        if self.simulator is None:
            return
        self.simulator.message_history.append({
            "time": self.simulator.time,
            "src": src_id,
            "dst": dst_id,
            "msg": str(message)
        })

        total_latency = self._calculate_routing_latency(src_id, dst_id)

        self.simulator.schedule(total_latency, self._deliver, dst_id, message)

    def _calculate_routing_latency(self, src_id: str, dst_id: str) -> float:
        """Calculate latency based on realistic routing through switches"""
        base_latency = self.latency

        if not self.switches:
            return base_latency

        src_node = self.simulator.nodes.get(src_id) if self.simulator else None
        dst_node = self.simulator.nodes.get(dst_id) if self.simulator else None

        if not src_node or not dst_node:
            return base_latency

        if src_node.rack_id == dst_node.rack_id:
            leaf_switch_id = None
            for sw_id, sw in self.switches.items():
                if sw.switch_type == "Leaf" and sw.rack_id == src_node.rack_id:
                    leaf_switch_id = sw_id
                    break

            if not leaf_switch_id:
                leaf_switch_id = f"Leaf-{src_node.rack_id}"

            leaf_switch = self.switches.get(leaf_switch_id)
            if leaf_switch:
                switch_delay = leaf_switch.forward_packet(src_id, dst_id, None)
                return base_latency + switch_delay * 2

        else:
            src_leaf_id = None
            for sw_id, sw in self.switches.items():
                if sw.switch_type == "Leaf" and sw.rack_id == src_node.rack_id:
                    src_leaf_id = sw_id
                    break
            if not src_leaf_id:
                src_leaf_id = f"Leaf-{src_node.rack_id}"

            dst_leaf_id = None
            for sw_id, sw in self.switches.items():
                if sw.switch_type == "Leaf" and sw.rack_id == dst_node.rack_id:
                    dst_leaf_id = sw_id
                    break
            if not dst_leaf_id:
                dst_leaf_id = f"Leaf-{dst_node.rack_id}"

            spine_id = None
            for sw_id, sw in self.switches.items():
                if sw.switch_type == "Spine":
                    spine_id = sw_id
                    break

            if not spine_id:
                spine_id = "Spine-Switch"

            total_switch_delay = 0.0

            if src_leaf_id in self.switches:
                total_switch_delay += self.switches[src_leaf_id].forward_packet(
                    src_id, dst_id, None)

            if spine_id in self.switches:
                total_switch_delay += self.switches[spine_id].forward_packet(
                    src_id, dst_id, None)

            if dst_leaf_id in self.switches:
                total_switch_delay += self.switches[dst_leaf_id].forward_packet(
                    src_id, dst_id, None)

            return base_latency + total_switch_delay + 0.1

        return base_latency

    def _deliver(self, dst_id: str, message: Any):
        if self.simulator is None:
            return
        node = self.simulator.nodes.get(dst_id)
        if node:
            node.receive_message(message)


class VisualSwitch:
    """Represents a network switch (Leaf or Spine)"""

    def __init__(self, switch_id: str, switch_type: str = "Leaf", rack_id: Optional[str] = None,
                 ports: int = 48, bandwidth_gbps: int = 10):
        self.switch_id = switch_id
        self.switch_type = switch_type
        self.rack_id = rack_id
        self.ports = ports
        self.bandwidth_gbps = bandwidth_gbps
        self.simulator: Optional['VisualSimulator'] = None

        self.active_connections = 0
        self.packets_forwarded = 0
        self.port_utilization = 0.0
        self.is_congested = False

        self.switching_latency = 0.001 if switch_type == "Leaf" else 0.002

    def attach_simulator(self, simulator: 'VisualSimulator'):
        self.simulator = simulator

    def forward_packet(self, src_id: str, dst_id: str, message: Any):
        """Forward a packet through this switch"""
        self.packets_forwarded += 1

        self.port_utilization = min(
            100, (self.active_connections / self.ports) * 100)

        if self.port_utilization > 80:
            self.is_congested = True
            return self.switching_latency * 2
        else:
            self.is_congested = False
            return self.switching_latency

    def update_metrics(self):
        """Update switch metrics - called periodically"""
        self.port_utilization = max(0, self.port_utilization - 5)

        if self.port_utilization < 60:
            self.is_congested = False


class VisualNode:
    def __init__(self, node_id: str, ip_address: Optional[str] = None, rack_id: str = "Rack1", cores: int = 8, ram_gb: int = 32):
        self.node_id = node_id
        self.ip_address = ip_address or f"192.168.1.{node_id[1:]}"
        self.rack_id = rack_id
        self.cores = cores
        self.ram_gb = ram_gb
        self.simulator: Optional['VisualSimulator'] = None
        self.state = "IDLE"
        self.messages_received = 0
        self.is_shutdown = False
        self.inbox = []
        self.processing_tasks = 0

        self.store = {}

        self.cpu_usage = random.randint(5, 25)
        self.memory_usage = random.randint(30, 50)
        self.disk_usage = random.randint(40, 60)

        self.power_watts = cores * 15 + ram_gb * 2
        self.is_critical = False
        self.faults = []

    def attach_simulator(self, simulator):
        self.simulator = simulator

    def update_metrics(self):
        """Simulate resource usage changes"""
        if self.is_shutdown:
            self.cpu_usage = 0
            self.memory_usage = 0
            self.faults = []
            return

        if self.state == "PROCESSING":
            self.cpu_usage = min(100, self.cpu_usage + random.randint(20, 50))
        else:
            if random.random() < config.idle_spike_prob:
                self.cpu_usage = min(90, self.cpu_usage +
                                     random.randint(5, 20))
            else:
                self.cpu_usage = max(10, self.cpu_usage -
                                     random.randint(5, 15))

        self.memory_usage = max(
            30, min(85, self.memory_usage + random.randint(-5, 5)))

        self.disk_usage = min(98, self.disk_usage +
                              random.uniform(0, config.disk_growth_rate))

        if self.disk_usage > 70 and random.random() < config.log_rotation_prob:
            self.disk_usage = max(20, self.disk_usage - random.randint(10, 30))

        base_power = self.cores * 15 + self.ram_gb * 2
        self.power_watts = base_power * (0.3 + 0.7 * (self.cpu_usage / 100))

        self.is_critical = False

        if self.cpu_usage > config.critical_threshold:
            self.is_critical = True
            if "High CPU Load" not in self.faults:
                self.faults.append("High CPU Load")
                print(
                    f"[CRITICAL] {self.node_id}: CPU {self.cpu_usage:.1f}% > {config.critical_threshold}%")
        elif "High CPU Load" in self.faults:
            self.faults.remove("High CPU Load")

        if self.memory_usage > config.critical_threshold:
            self.is_critical = True
            if "Memory Exhaustion" not in self.faults:
                self.faults.append("Memory Exhaustion")
                print(
                    f"[CRITICAL] {self.node_id}: Memory {self.memory_usage:.1f}% > {config.critical_threshold}%")
        elif "Memory Exhaustion" in self.faults:
            self.faults.remove("Memory Exhaustion")

        if self.disk_usage > config.critical_threshold:
            self.is_critical = True
            if "Disk Space Low" not in self.faults:
                self.faults.append("Disk Space Low")
                print(
                    f"[CRITICAL] {self.node_id}: Disk {self.disk_usage:.1f}% > {config.critical_threshold}%")
        elif "Disk Space Low" in self.faults:
            self.faults.remove("Disk Space Low")

        if random.random() < config.hw_fault_prob and len(self.faults) < 3:
            hw_faults = ["Power Supply Warning", "Network Packet Loss"]
            new_fault = random.choice(hw_faults)
            if new_fault not in self.faults:
                self.faults.append(new_fault)
                self.is_critical = True
                print(f"[FAULT] {self.node_id}: Generated {new_fault}")

        for f in ["Power Supply Warning", "Network Packet Loss"]:
            if f in self.faults and random.random() < config.fault_clear_prob:
                self.faults.remove(f)
                print(f"[FAULT] {self.node_id}: Cleared {f}")

        if self.faults:
            self.is_critical = True

        if "Power Supply Warning" in self.faults:
            if random.random() < config.power_failure_prob:
                self.is_shutdown = True
                self.state = "SHUTDOWN"
                if self.simulator:
                    self.simulator.log(
                        self.node_id, "CRITICAL FAILURE: Power Supply Died!")
                print(
                    f"[SHUTDOWN] {self.node_id}: Power Supply DIED! (prob={config.power_failure_prob})")
                self.faults = []
                self.cpu_usage = 0
                self.memory_usage = 0

    def receive_message(self, message: Any):
        if self.is_shutdown or self.simulator is None:
            return

        self.messages_received += 1
        self.state = "PROCESSING"
        self.simulator.log(self.node_id, f"Received {message}")

        self.inbox.append(message)

        self.processing_tasks += 1
        self.simulator.schedule(0.1, self._finish_processing)

    def _finish_processing(self):
        self.processing_tasks -= 1
        if self.processing_tasks <= 0:
            self.processing_tasks = 0
            self.state = "IDLE"

    def send(self, message: Any, target: Optional[str] = None):
        if self.is_shutdown or self.simulator is None:
            return

        if target:
            self.simulator.log(self.node_id, f"Sending {message} to {target}")
            if self.simulator.network:
                self.simulator.network.send(self.node_id, target, message)
        else:
            pass
