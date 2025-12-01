from __future__ import annotations
import heapq
from dataclasses import dataclass, field
from typing import Any, Callable, List, Dict, Optional, Protocol, TYPE_CHECKING

if TYPE_CHECKING:
    from .node import VisualNode
    from .network import VisualNetwork

@dataclass
class SimulationConfig:
    # Fault injection 
    idle_spike_prob: float = 0.1
    log_rotation_prob: float = 0.05
    hw_fault_prob: float = 0.005
    fault_clear_prob: float = 0.05
    power_failure_prob: float = 0.5

    critical_threshold: float = 90.0
    disk_growth_rate: float = 0.05

    reset_on_error: bool = True
    
    # Synchronization model parameters
    sync_model: str = "asynchronous"  # "synchronous" | "asynchronous" | "partial_synchronous"
    max_clock_drift: float = 0.01  # Maximum clock drift in seconds
    sync_timeout: float = 5.0  # Timeout for synchronous operations
    sync_violation_prob: float = 0.0  # Probability of synchronization violations
    
    # Network parameters
    packet_loss_rate: float = 0.0  # Probability of packet loss (0.0 - 1.0)
    bandwidth_mbps: float = 1000.0  # Network bandwidth in Mbps
    jitter_range: float = 0.0  # Random jitter variance in seconds
    reorder_probability: float = 0.0  # Probability of out-of-order
    partition_enabled: bool = False  # Whether network partitions are enabled


class ClockDrift:
    """Models clock drift between nodes"""
    def __init__(self, max_drift: float = 0.01):
        self.max_drift = max_drift
        self.node_drifts: Dict[str, float] = {}
    
    def get_drift(self, node_id: str) -> float:
        """Get the clock drift for a specific node"""
        if node_id not in self.node_drifts:
            import random
            # Random drift between -max_drift and +max_drift
            self.node_drifts[node_id] = random.uniform(-self.max_drift, self.max_drift)
        return self.node_drifts[node_id]
    
    def get_local_time(self, node_id: str, global_time: float) -> float:
        """Get the local time for a node given global time"""
        drift = self.get_drift(node_id)
        return global_time + (global_time * drift)
    
    def reset(self):
        """Reset all clock drifts"""
        self.node_drifts.clear()

config = SimulationConfig()

@dataclass(order=True)
class Event:
    timestamp: float
    priority: int
    callback: Callable = field(compare=False)
    args: tuple = field(default=(), compare=False)
    kwargs: dict = field(default_factory=dict, compare=False)

class SimulatorProtocol(Protocol):
    time: float
    nodes: Dict[str, 'VisualNode']
    network: Optional['VisualNetwork']
    message_history: List[Dict]

    def log(self, node_id: str, message: str) -> None: ...
    def schedule(self, delay: float, callback: Callable, *args, **kwargs) -> None: ...
