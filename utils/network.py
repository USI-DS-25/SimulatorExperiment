from __future__ import annotations
import random
from typing import Any, Dict, Optional, TYPE_CHECKING, Set
from .protocol import SimulatorProtocol, config

if TYPE_CHECKING:
    from .node import VisualNode

class VisualSwitch:
    """Represents a network switch (Leaf or Spine)"""

    def __init__(self, switch_id: str, switch_type: str = "Leaf", rack_id: Optional[str] = None,
                 ports: int = 48, bandwidth_gbps: int = 10):
        self.switch_id = switch_id
        self.switch_type = switch_type
        self.rack_id = rack_id
        self.ports = ports
        self.bandwidth_gbps = bandwidth_gbps
        self.simulator: Optional[SimulatorProtocol] = None

        self.active_connections = 0
        self.packets_forwarded = 0
        self.port_utilization = 0.0
        self.is_congested = False

        self.switching_latency = 0.001 if switch_type == "Leaf" else 0.002

    def attach_simulator(self, simulator: SimulatorProtocol):
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


class VisualNetwork:
    def __init__(self, latency=0.5):
        self.simulator: Optional[SimulatorProtocol] = None
        self.latency = latency
        self.switches: Dict[str, VisualSwitch] = {}
        
        # Network partitions
        self.partitions: List[Set[str]] = []  # List of isolated node groups
        self.partition_active = False
        
        # Message reordering queue
        self.reorder_queue: List[tuple] = []  # (delivery_time, dst_id, message)

    def attach_simulator(self, simulator: SimulatorProtocol):
        self.simulator = simulator

    def register_switch(self, switch: VisualSwitch):
        """Register a switch with the network"""
        self.switches[switch.switch_id] = switch
        if self.simulator:
            switch.attach_simulator(self.simulator)

    def create_partition(self, group1: Set[str], group2: Set[str]):
        """Create a network partition between two groups of nodes"""
        self.partitions = [group1, group2]
        self.partition_active = True
        if self.simulator:
            self.simulator.log("NETWORK", f"Partition created: {group1} | {group2}")
    
    def heal_partition(self):
        """Heal all network partitions"""
        self.partitions = []
        self.partition_active = False
        if self.simulator:
            self.simulator.log("NETWORK", "Partition healed")
    
    def are_partitioned(self, src_id: str, dst_id: str) -> bool:
        """Check if two nodes are in different partitions"""
        if not self.partition_active or not self.partitions:
            return False
        
        for partition in self.partitions:
            if src_id in partition and dst_id not in partition:
                return True
            if dst_id in partition and src_id not in partition:
                return True
        
        return False

    def send(self, src_id: str, dst_id: str, message: Any, sync: bool = False, msg_id: Optional[str] = None):
        if self.simulator is None:
            return
        
        # Generate message ID if not provided
        if msg_id is None:
            import random
            msg_id = f"{src_id}_{dst_id}_{self.simulator.time}_{random.randint(0, 999999)}"
        
        # Check for network partition
        if self.are_partitioned(src_id, dst_id):
            self.simulator.log("NETWORK", f"[PARTITION] Message dropped: {src_id} -> {dst_id}")
            if hasattr(self.simulator, 'metrics'):
                self.simulator.metrics.record_packet_drop()
            return
        
        # Check for packet loss
        if config.packet_loss_rate > 0 and random.random() < config.packet_loss_rate:
            self.simulator.log("NETWORK", f"[PACKET_LOSS] Message dropped: {src_id} -> {dst_id}")
            if hasattr(self.simulator, 'metrics'):
                self.simulator.metrics.record_packet_drop()
            return
        
        # Record send in metrics
        if hasattr(self.simulator, 'metrics'):
            self.simulator.metrics.record_send(src_id, dst_id, msg_id, self.simulator.time)
        
        self.simulator.message_history.append({
            "time": self.simulator.time,
            "src": src_id,
            "dst": dst_id,
            "msg": str(message),
            "sync": sync,
            "msg_id": msg_id
        })

        total_latency = self._calculate_routing_latency(src_id, dst_id)
        
        # Add jitter
        if config.jitter_range > 0:
            jitter = random.uniform(-config.jitter_range, config.jitter_range)
            total_latency = max(0.001, total_latency + jitter)
        
        # Check for message reordering
        if config.reorder_probability > 0 and random.random() < config.reorder_probability:
            # Delay this message randomly
            extra_delay = random.uniform(0.1, 0.5)
            total_latency += extra_delay
            self.simulator.log("NETWORK", f"[REORDER] Message delayed: {src_id} -> {dst_id}")
        
        # Schedule delivery
        if sync:
            # For sync messages, also schedule ACK back to sender
            self.simulator.schedule(total_latency, self._deliver, dst_id, message, msg_id)
            self.simulator.schedule(total_latency * 2, self._deliver_sync_ack, src_id, msg_id)
        else:
            self.simulator.schedule(total_latency, self._deliver, dst_id, message, msg_id)

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

    def _deliver(self, dst_id: str, message: Any, msg_id: Optional[str] = None):
        if self.simulator is None:
            return
        node = self.simulator.nodes.get(dst_id)
        if node:
            # Record receive in metrics
            if hasattr(self.simulator, 'metrics') and msg_id:
                self.simulator.metrics.record_receive(dst_id, msg_id, self.simulator.time)
            node.receive_message(message)
    
    def _deliver_sync_ack(self, src_id: str, msg_id: Optional[str]):
        """Deliver synchronous acknowledgment back to sender"""
        if self.simulator is None or msg_id is None:
            return
        node = self.simulator.nodes.get(src_id)
        if node and hasattr(node, '_sync_send_ack'):
            node._sync_send_ack(msg_id)
