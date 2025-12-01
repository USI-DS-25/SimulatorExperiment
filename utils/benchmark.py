from __future__ import annotations
from typing import Dict, List, Any, Optional, Callable
from dataclasses import dataclass, field
import json
import os
from datetime import datetime
import statistics


@dataclass
class BenchmarkScenario:
    """Configuration for a benchmark scenario"""
    name: str
    description: str
    duration: float  # Simulation duration in seconds
    
    # Network configuration
    latency: float = 0.5
    packet_loss_rate: float = 0.0
    jitter_range: float = 0.0
    reorder_probability: float = 0.0
    bandwidth_mbps: float = 1000.0
    
    # Synchronization model
    sync_model: str = "asynchronous"
    max_clock_drift: float = 0.01
    sync_violation_prob: float = 0.0
    
    # Fault injection
    hw_fault_prob: float = 0.0
    power_failure_prob: float = 0.0
    partition_schedule: List[Dict[str, Any]] = field(default_factory=list)  # [{time, group1, group2, duration}]
    
    # Node configuration
    num_nodes: int = 9
    nodes_per_rack: List[int] = field(default_factory=lambda: [5, 4])
    
    # Algorithm
    algorithm_name: Optional[str] = None
    
    @classmethod
    def from_json(cls, filepath: str) -> 'BenchmarkScenario':
        """Load scenario from JSON file"""
        with open(filepath, 'r') as f:
            data = json.load(f)
        return cls(**data)
    
    def to_json(self, filepath: str):
        """Save scenario to JSON file"""
        with open(filepath, 'w') as f:
            json.dump(self.__dict__, f, indent=2)


@dataclass
class BenchmarkResults:
    """Results from a benchmark run"""
    scenario_name: str
    timestamp: str
    simulation_time: float
    metrics: Dict[str, Any]
    node_metrics: Dict[str, Dict[str, Any]] = field(default_factory=dict)
    
    def to_dict(self) -> Dict[str, Any]:
        return {
            'scenario_name': self.scenario_name,
            'timestamp': self.timestamp,
            'simulation_time': self.simulation_time,
            'metrics': self.metrics,
            'node_metrics': self.node_metrics
        }
    
    def save(self, filepath: str):
        """Save results to JSON file"""
        with open(filepath, 'w') as f:
            json.dump(self.to_dict(), f, indent=2)
    
    @classmethod
    def load(cls, filepath: str) -> 'BenchmarkResults':
        """Load results from JSON file"""
        with open(filepath, 'r') as f:
            data = json.load(f)
        return cls(**data)


class BenchmarkRunner:
    """Run and manage benchmark scenarios"""
    
    def __init__(self, output_dir: str = "benchmark_results"):
        self.output_dir = output_dir
        os.makedirs(output_dir, exist_ok=True)
        self.results: List[BenchmarkResults] = []
    
    def run_scenario(self, scenario: BenchmarkScenario, simulator_factory: Callable, 
                     num_trials: int = 1) -> List[BenchmarkResults]:
        """
        Run a benchmark scenario multiple times
        
        Args:
            scenario: The scenario configuration
            simulator_factory: Function that creates and returns a configured simulator
            num_trials: Number of times to run the scenario
        
        Returns:
            List of BenchmarkResults for each trial
        """
        trial_results = []
        
        for trial in range(num_trials):
            print(f"\n=== Running {scenario.name} - Trial {trial + 1}/{num_trials} ===")
            
            # Create fresh simulator
            sim = simulator_factory()
            
            # Apply scenario configuration
            self._configure_simulator(sim, scenario)
            
            # Run simulation
            self._run_simulation(sim, scenario)
            
            # Collect results
            results = self._collect_results(sim, scenario, trial)
            trial_results.append(results)
            self.results.append(results)
            
            # Save individual trial results
            filename = f"{scenario.name}_trial{trial + 1}_{datetime.now().strftime('%Y%m%d_%H%M%S')}.json"
            results.save(os.path.join(self.output_dir, filename))
        
        return trial_results
    
    def _configure_simulator(self, sim: Any, scenario: BenchmarkScenario):
        """Apply scenario configuration to simulator"""
        from utils.protocol import config
        
        # Network parameters
        config.packet_loss_rate = scenario.packet_loss_rate
        config.jitter_range = scenario.jitter_range
        config.reorder_probability = scenario.reorder_probability
        config.bandwidth_mbps = scenario.bandwidth_mbps
        
        # Synchronization
        config.sync_model = scenario.sync_model
        config.max_clock_drift = scenario.max_clock_drift
        config.sync_violation_prob = scenario.sync_violation_prob
        
        # Faults
        config.hw_fault_prob = scenario.hw_fault_prob
        config.power_failure_prob = scenario.power_failure_prob
        
        # Set network latency
        if sim.network:
            sim.network.latency = scenario.latency
        
        # Set algorithm
        if scenario.algorithm_name and hasattr(sim, 'algorithm_controller'):
            sim.algorithm_controller.set_active(scenario.algorithm_name)
        
        # Schedule partition events
        for partition_event in scenario.partition_schedule:
            self._schedule_partition(sim, partition_event)
    
    def _schedule_partition(self, sim: Any, event: Dict[str, Any]):
        """Schedule a network partition event"""
        partition_time = event.get('time', 0)
        group1 = set(event.get('group1', []))
        group2 = set(event.get('group2', []))
        duration = event.get('duration', 10.0)
        
        # Schedule partition creation
        sim.schedule(partition_time, self._create_partition, sim, group1, group2)
        
        # Schedule partition healing
        sim.schedule(partition_time + duration, self._heal_partition, sim)
    
    def _create_partition(self, sim: Any, group1: set, group2: set):
        """Create a network partition"""
        if sim.network:
            sim.network.create_partition(group1, group2)
            if hasattr(sim, 'metrics'):
                sim.metrics.record_partition_event()
    
    def _heal_partition(self, sim: Any):
        """Heal a network partition"""
        if sim.network:
            sim.network.heal_partition()
    
    def _run_simulation(self, sim: Any, scenario: BenchmarkScenario):
        """Run the simulation for the specified duration"""
        steps = int(scenario.duration)
        
        for step in range(steps):
            sim.step(1.0)
            
            # Update algorithm
            if hasattr(sim, 'algorithm_controller'):
                nodes = list(sim.nodes.values())
                sim.algorithm_controller.execute(nodes, step)
            
            # Update node metrics
            for node in sim.nodes.values():
                if hasattr(node, 'update_metrics'):
                    node.update_metrics()
            
            # Update switch metrics
            if sim.network:
                for switch in sim.network.switches.values():
                    if hasattr(switch, 'update_metrics'):
                        switch.update_metrics()
    
    def _collect_results(self, sim: Any, scenario: BenchmarkScenario, trial: int) -> BenchmarkResults:
        """Collect metrics from the simulation"""
        metrics = {}
        node_metrics = {}
        
        if hasattr(sim, 'metrics'):
            metrics = sim.metrics.get_global_stats(sim.time)
            
            # Collect per-node metrics
            for node_id in sim.nodes.keys():
                node_metrics[node_id] = sim.metrics.get_node_stats(node_id, sim.time)
        
        return BenchmarkResults(
            scenario_name=f"{scenario.name}_trial{trial + 1}",
            timestamp=datetime.now().isoformat(),
            simulation_time=sim.time,
            metrics=metrics,
            node_metrics=node_metrics
        )
    
    def compare_results(self, result_names: List[str]) -> Dict[str, Any]:
        """Compare results from multiple scenarios"""
        comparison = {
            'scenarios': result_names,
            'metrics': {}
        }
        
        # Find matching results
        matching_results = [r for r in self.results if r.scenario_name in result_names]
        
        if not matching_results:
            return comparison
        
        # Compare key metrics
        metric_keys = ['latency', 'throughput', 'delivery_rate', 'sync_violations', 'sync_timeouts']
        
        for key in metric_keys:
            values = []
            for result in matching_results:
                if key in result.metrics:
                    metric_value = result.metrics[key]
                    if isinstance(metric_value, dict):
                        # For nested metrics like latency, use avg
                        values.append(metric_value.get('avg', 0))
                    else:
                        values.append(metric_value)
            
            if values:
                comparison['metrics'][key] = {
                    'min': min(values),
                    'max': max(values),
                    'avg': statistics.mean(values),
                    'values': values
                }
        
        return comparison
    
    def generate_report(self, filepath: str):
        """Generate a comparison report for all results"""
        report = {
            'generated_at': datetime.now().isoformat(),
            'total_scenarios': len(self.results),
            'results': [r.to_dict() for r in self.results]
        }
        
        with open(filepath, 'w') as f:
            json.dump(report, f, indent=2)
        
        print(f"\nReport saved to: {filepath}")
