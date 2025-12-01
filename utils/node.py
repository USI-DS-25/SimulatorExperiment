from __future__ import annotations
import random
from typing import Any, Optional, List, TYPE_CHECKING
from .protocol import config, SimulatorProtocol

if TYPE_CHECKING:
    from .network import VisualNetwork

class VisualNode:
    def __init__(self, node_id: str, ip_address: Optional[str] = None, rack_id: str = "Rack1", cores: int = 8, ram_gb: int = 32):
        self.node_id = node_id
        self.ip_address = ip_address or f"192.168.1.{node_id[1:]}"
        self.rack_id = rack_id
        self.cores = cores
        self.ram_gb = ram_gb
        self.simulator: Optional[SimulatorProtocol] = None
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
        
        # Clock and synchronization
        self.local_clock = 0.0
        self.timers = {}  # timer_id -> (callback, args, kwargs)
        self.pending_sync_sends = {}  # message_id -> (timestamp, callback)

    def attach_simulator(self, simulator: SimulatorProtocol):
        self.simulator = simulator

    def get_local_time(self) -> float:
        """Get the local time for this node (with clock drift)"""
        if self.simulator and hasattr(self.simulator, 'clock_drift'):
            return self.simulator.clock_drift.get_local_time(self.node_id, self.simulator.time)
        return self.simulator.time if self.simulator else 0.0

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
        """Asynchronous send - fire and forget"""
        if self.is_shutdown or self.simulator is None:
            return

        if target:
            self.simulator.log(self.node_id, f"Sending {message} to {target}")
            if self.simulator.network:
                self.simulator.network.send(self.node_id, target, message)
        else:
            pass

    def sync_send(self, message: Any, target: str, timeout: Optional[float] = None) -> bool:
        """
        Synchronous send - blocks until acknowledgment or timeout.
        Returns True if acknowledged, False if timeout.
        """
        if self.is_shutdown or self.simulator is None:
            return False
        
        if not target:
            return False
        
        timeout = timeout or config.sync_timeout
        
        # Check if synchronization violation occurs
        if config.sync_model == "asynchronous" or (
            config.sync_violation_prob > 0 and random.random() < config.sync_violation_prob
        ):
            # Violation: convert to async send
            self.simulator.log(self.node_id, f"[SYNC_VIOLATION] sync_send degraded to async")
            if hasattr(self.simulator, 'metrics'):
                self.simulator.metrics.record_sync_violation()
            self.send(message, target)
            return False
        
        # Generate unique message ID
        msg_id = f"{self.node_id}_{target}_{self.simulator.time}_{random.randint(0, 999999)}"
        
        # Send the message
        self.simulator.log(self.node_id, f"Sync sending {message} to {target}")
        if self.simulator.network:
            # Track this as a sync send
            send_time = self.simulator.time
            self.pending_sync_sends[msg_id] = (send_time, None)
            
            # Schedule timeout
            self.simulator.schedule(timeout, self._sync_send_timeout, msg_id)
            
            # Send the message (network will handle ack)
            self.simulator.network.send(self.node_id, target, message, sync=True, msg_id=msg_id)
            
            return True
        
        return False
    
    def _sync_send_timeout(self, msg_id: str):
        """Handle sync_send timeout"""
        if msg_id in self.pending_sync_sends:
            self.simulator.log(self.node_id, f"[TIMEOUT] sync_send timed out: {msg_id}")
            if hasattr(self.simulator, 'metrics'):
                self.simulator.metrics.record_sync_timeout()
            del self.pending_sync_sends[msg_id]
    
    def _sync_send_ack(self, msg_id: str):
        """Handle sync_send acknowledgment"""
        if msg_id in self.pending_sync_sends:
            self.simulator.log(self.node_id, f"[ACK] sync_send acknowledged: {msg_id}")
            del self.pending_sync_sends[msg_id]

    def set_timer(self, timer_id: str, delay: float, callback: Any, *args, **kwargs):
        """Set a timer that will fire after delay seconds"""
        if self.is_shutdown or self.simulator is None:
            return
        
        self.timers[timer_id] = (callback, args, kwargs)
        self.simulator.schedule(delay, self._fire_timer, timer_id)
        self.simulator.log(self.node_id, f"Set timer {timer_id} for {delay}s")
    
    def cancel_timer(self, timer_id: str):
        """Cancel a pending timer"""
        if timer_id in self.timers:
            del self.timers[timer_id]
            self.simulator.log(self.node_id, f"Cancelled timer {timer_id}")
    
    def _fire_timer(self, timer_id: str):
        """Fire a timer callback"""
        if timer_id in self.timers:
            callback, args, kwargs = self.timers[timer_id]
            del self.timers[timer_id]
            self.simulator.log(self.node_id, f"Timer {timer_id} fired")
            callback(*args, **kwargs)
