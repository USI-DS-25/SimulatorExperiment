from __future__ import annotations
from typing import Dict, List, Optional, Any
from dataclasses import dataclass, field
import statistics
import json
import csv
from datetime import datetime


@dataclass
class LatencyStats:
    """Statistical summary of latencies"""
    count: int = 0
    min: float = float('inf')
    max: float = 0.0
    avg: float = 0.0
    median: float = 0.0
    p50: float = 0.0
    p95: float = 0.0
    p99: float = 0.0
    
    def to_dict(self) -> Dict:
        return {
            'count': self.count,
            'min': self.min,
            'max': self.max,
            'avg': self.avg,
            'median': self.median,
            'p50': self.p50,
            'p95': self.p95,
            'p99': self.p99
        }


@dataclass
class ThroughputStats:
    """Throughput statistics"""
    total_messages: int = 0
    messages_per_second: float = 0.0
    bytes_per_second: float = 0.0
    time_window: float = 1.0
    
    def to_dict(self) -> Dict:
        return {
            'total_messages': self.total_messages,
            'messages_per_second': self.messages_per_second,
            'bytes_per_second': self.bytes_per_second,
            'time_window': self.time_window
        }


class LatencyTracker:
    """Track and analyze message latencies"""
    
    def __init__(self):
        self.latencies: List[float] = []
        self.send_times: Dict[str, float] = {}  # msg_id -> send_time
    
    def record_send(self, msg_id: str, send_time: float):
        """Record when a message was sent"""
        self.send_times[msg_id] = send_time
    
    def record_receive(self, msg_id: str, receive_time: float):
        """Record when a message was received and calculate latency"""
        if msg_id in self.send_times:
            latency = receive_time - self.send_times[msg_id]
            self.latencies.append(latency)
            del self.send_times[msg_id]
    
    def get_stats(self) -> LatencyStats:
        """Calculate latency statistics"""
        if not self.latencies:
            return LatencyStats(count=0)
        
        sorted_latencies = sorted(self.latencies)
        count = len(sorted_latencies)
        
        return LatencyStats(
            count=count,
            min=sorted_latencies[0],
            max=sorted_latencies[-1],
            avg=statistics.mean(sorted_latencies),
            median=statistics.median(sorted_latencies),
            p50=sorted_latencies[int(count * 0.50)] if count > 0 else 0.0,
            p95=sorted_latencies[int(count * 0.95)] if count > 1 else sorted_latencies[-1],
            p99=sorted_latencies[int(count * 0.99)] if count > 1 else sorted_latencies[-1]
        )
    
    def reset(self):
        """Reset all tracked latencies"""
        self.latencies.clear()
        self.send_times.clear()


class ThroughputTracker:
    """Track message throughput over time"""
    
    def __init__(self, window_size: float = 1.0):
        self.window_size = window_size
        self.message_times: List[float] = []
        self.message_sizes: List[int] = []
    
    def record_message(self, timestamp: float, size_bytes: int = 0):
        """Record a message at the given timestamp"""
        self.message_times.append(timestamp)
        self.message_sizes.append(size_bytes)
    
    def get_stats(self, current_time: float) -> ThroughputStats:
        """Calculate throughput for the current time window"""
        # Filter messages within the window
        cutoff_time = current_time - self.window_size
        recent_messages = [t for t in self.message_times if t >= cutoff_time]
        recent_sizes = [s for t, s in zip(self.message_times, self.message_sizes) if t >= cutoff_time]
        
        count = len(recent_messages)
        total_bytes = sum(recent_sizes)
        
        return ThroughputStats(
            total_messages=count,
            messages_per_second=count / self.window_size if self.window_size > 0 else 0.0,
            bytes_per_second=total_bytes / self.window_size if self.window_size > 0 else 0.0,
            time_window=self.window_size
        )
    
    def reset(self):
        """Reset all tracked messages"""
        self.message_times.clear()
        self.message_sizes.clear()


class MetricsCollector:
    """Collect and analyze simulation metrics"""
    
    def __init__(self):
        # Global metrics
        self.latency_tracker = LatencyTracker()
        self.throughput_tracker = ThroughputTracker()
        
        # Per-node metrics
        self.node_latencies: Dict[str, LatencyTracker] = {}
        self.node_throughput: Dict[str, ThroughputTracker] = {}
        
        # Network metrics
        self.packets_sent = 0
        self.packets_received = 0
        self.packets_dropped = 0
        self.sync_violations = 0
        self.sync_timeouts = 0
        
        # Fault metrics
        self.node_failures = 0
        self.partition_events = 0
        
        self.start_time = 0.0
    
    def reset(self):
        """Reset all metrics"""
        self.latency_tracker.reset()
        self.throughput_tracker.reset()
        self.node_latencies.clear()
        self.node_throughput.clear()
        self.packets_sent = 0
        self.packets_received = 0
        self.packets_dropped = 0
        self.sync_violations = 0
        self.sync_timeouts = 0
        self.node_failures = 0
        self.partition_events = 0
    
    def record_send(self, src_id: str, dst_id: str, msg_id: str, timestamp: float, size_bytes: int = 100):
        """Record a message send event"""
        self.packets_sent += 1
        self.latency_tracker.record_send(msg_id, timestamp)
        self.throughput_tracker.record_message(timestamp, size_bytes)
        
        # Per-node tracking
        if src_id not in self.node_latencies:
            self.node_latencies[src_id] = LatencyTracker()
            self.node_throughput[src_id] = ThroughputTracker()
        
        self.node_latencies[src_id].record_send(msg_id, timestamp)
        self.node_throughput[src_id].record_message(timestamp, size_bytes)
    
    def record_receive(self, dst_id: str, msg_id: str, timestamp: float):
        """Record a message receive event"""
        self.packets_received += 1
        self.latency_tracker.record_receive(msg_id, timestamp)
        
        if dst_id in self.node_latencies:
            self.node_latencies[dst_id].record_receive(msg_id, timestamp)
    
    def record_packet_drop(self):
        """Record a packet drop event"""
        self.packets_dropped += 1
        self.packets_sent += 1  # Count as a send attempt
    
    def record_sync_violation(self):
        """Record a synchronization violation"""
        self.sync_violations += 1
    
    def record_sync_timeout(self):
        """Record a synchronous send timeout"""
        self.sync_timeouts += 1
    
    def record_node_failure(self):
        """Record a node failure"""
        self.node_failures += 1
    
    def record_partition_event(self):
        """Record a network partition event"""
        self.partition_events += 1
    
    def get_global_stats(self, current_time: float) -> Dict[str, Any]:
        """Get global statistics"""
        return {
            'latency': self.latency_tracker.get_stats().to_dict(),
            'throughput': self.throughput_tracker.get_stats(current_time).to_dict(),
            'packets_sent': self.packets_sent,
            'packets_received': self.packets_received,
            'packets_dropped': self.packets_dropped,
            'delivery_rate': self.packets_received / self.packets_sent if self.packets_sent > 0 else 0.0,
            'sync_violations': self.sync_violations,
            'sync_timeouts': self.sync_timeouts,
            'node_failures': self.node_failures,
            'partition_events': self.partition_events
        }
    
    def get_node_stats(self, node_id: str, current_time: float) -> Dict[str, Any]:
        """Get statistics for a specific node"""
        if node_id not in self.node_latencies:
            return {}
        
        return {
            'latency': self.node_latencies[node_id].get_stats().to_dict(),
            'throughput': self.node_throughput[node_id].get_stats(current_time).to_dict()
        }
    
    def export_to_json(self, filepath: str, current_time: float):
        """Export metrics to JSON file"""
        data = {
            'timestamp': datetime.now().isoformat(),
            'simulation_time': current_time,
            'global_stats': self.get_global_stats(current_time),
            'node_stats': {
                node_id: self.get_node_stats(node_id, current_time)
                for node_id in self.node_latencies.keys()
            }
        }
        
        with open(filepath, 'w') as f:
            json.dump(data, f, indent=2)
    
    def export_to_csv(self, filepath: str, current_time: float):
        """Export metrics to CSV file"""
        global_stats = self.get_global_stats(current_time)
        
        with open(filepath, 'w', newline='') as f:
            writer = csv.writer(f)
            writer.writerow(['Metric', 'Value'])
            
            # Flatten the stats
            for key, value in global_stats.items():
                if isinstance(value, dict):
                    for subkey, subvalue in value.items():
                        writer.writerow([f"{key}_{subkey}", subvalue])
                else:
                    writer.writerow([key, value])
