#!/usr/bin/env python3
"""
Example benchmark script demonstrating how to use the benchmarking framework
"""

from sim_engine import VisualSimulator, VisualNetwork, VisualNode, VisualSwitch
from utils.benchmark import BenchmarkRunner, BenchmarkScenario
from utils.protocol import config
import os


def create_simulator():
    """Factory function to create a fresh simulator instance"""
    sim = VisualSimulator()
    
    # Create network
    net = VisualNetwork(latency=1.0)
    sim.register_network(net)
    
    # Create switches
    leaf_rack1 = VisualSwitch("Leaf-Rack1", switch_type="Leaf", rack_id="Rack1", ports=48, bandwidth_gbps=10)
    leaf_rack2 = VisualSwitch("Leaf-Rack2", switch_type="Leaf", rack_id="Rack2", ports=48, bandwidth_gbps=10)
    spine_switch = VisualSwitch("Spine-Switch", switch_type="Spine", ports=96, bandwidth_gbps=100)
    
    net.register_switch(leaf_rack1)
    net.register_switch(leaf_rack2)
    net.register_switch(spine_switch)
    
    # Create nodes
    for i in range(5):
        node = VisualNode(f"R1-S{i+1}", ip_address=f"192.168.1.{10+i}", rack_id="Rack1", cores=8, ram_gb=32)
        sim.register_node(node)
    
    for i in range(4):
        node = VisualNode(f"R2-S{i+1}", ip_address=f"192.168.2.{10+i}", rack_id="Rack2", cores=16, ram_gb=128)
        sim.register_node(node)
    
    # Save initial state
    initial_config = [
        {"node_id": f"R1-S{i+1}", "ip_address": f"192.168.1.{10+i}", "rack_id": "Rack1", "cores": 8, "ram_gb": 32}
        for i in range(5)
    ] + [
        {"node_id": f"R2-S{i+1}", "ip_address": f"192.168.2.{10+i}", "rack_id": "Rack2", "cores": 16, "ram_gb": 128}
        for i in range(4)
    ]
    sim.save_initial_state(initial_config)
    
    # Load and register algorithms
    from sim_engine import AlgorithmLoader
    discovered = AlgorithmLoader.discover_algorithms()
    
    for algo_name, algo_data in discovered.items():
        if algo_data["error"]:
            sim.algorithm_controller.validation_errors[algo_name] = algo_data["error"]
        else:
            sim.algorithm_controller.register_algorithm(algo_name, algo_data["instance"])
    
    return sim


def main():
    print("=== Datacenter Simulator Benchmark Runner ===\n")
    
    # Create benchmark runner
    runner = BenchmarkRunner(output_dir="benchmark_results")
    
    # Load scenarios
    scenarios = []
    benchmark_dir = "benchmarks"
    
    if os.path.exists(benchmark_dir):
        for filename in os.listdir(benchmark_dir):
            if filename.endswith('.json'):
                filepath = os.path.join(benchmark_dir, filename)
                try:
                    scenario = BenchmarkScenario.from_json(filepath)
                    scenarios.append(scenario)
                    print(f"Loaded scenario: {scenario.name}")
                except Exception as e:
                    print(f"Failed to load {filename}: {e}")
    
    if not scenarios:
        print("No scenarios found. Creating a default scenario...")
        scenario = BenchmarkScenario(
            name="default",
            description="Default benchmark scenario",
            duration=30.0,
            algorithm_name="random_traffic"
        )
        scenarios.append(scenario)
    
    print(f"\nRunning {len(scenarios)} scenario(s)...\n")
    
    # Run each scenario
    all_results = []
    for scenario in scenarios:
        print(f"\n{'='*60}")
        print(f"Scenario: {scenario.name}")
        print(f"Description: {scenario.description}")
        print(f"{'='*60}")
        
        results = runner.run_scenario(scenario, create_simulator, num_trials=1)
        all_results.extend(results)
        
        # Print summary
        if results:
            metrics = results[0].metrics
            print(f"\n--- Results Summary ---")
            print(f"Packets sent: {metrics.get('packets_sent', 0)}")
            print(f"Packets received: {metrics.get('packets_received', 0)}")
            print(f"Packets dropped: {metrics.get('packets_dropped', 0)}")
            print(f"Delivery rate: {metrics.get('delivery_rate', 0):.2%}")
            
            if 'latency' in metrics:
                lat = metrics['latency']
                print(f"\nLatency Statistics:")
                print(f"  Count: {lat.get('count', 0)}")
                print(f"  Min: {lat.get('min', 0):.4f}s")
                print(f"  Avg: {lat.get('avg', 0):.4f}s")
                print(f"  Max: {lat.get('max', 0):.4f}s")
                print(f"  P95: {lat.get('p95', 0):.4f}s")
                print(f"  P99: {lat.get('p99', 0):.4f}s")
            
            if 'throughput' in metrics:
                tput = metrics['throughput']
                print(f"\nThroughput:")
                print(f"  Messages/sec: {tput.get('messages_per_second', 0):.2f}")
    
    # Generate comparison report
    print(f"\n{'='*60}")
    print("Generating comparison report...")
    report_path = os.path.join(runner.output_dir, "benchmark_report.json")
    runner.generate_report(report_path)
    
    # Export metrics for the last result
    if all_results:
        last_result = all_results[-1]
        metrics_path = os.path.join(runner.output_dir, "latest_metrics.json")
        last_result.save(metrics_path)
        print(f"Latest metrics saved to: {metrics_path}")
    
    print(f"\n{'='*60}")
    print("Benchmark complete!")
    print(f"Results saved to: {runner.output_dir}/")
    print(f"{'='*60}\n")


if __name__ == "__main__":
    main()
