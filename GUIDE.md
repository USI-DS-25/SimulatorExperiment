# Datacenter Simulator Developer Guide

## 1. How to Run
Open your terminal and run:
```bash
python3 app.py
```
Then open your web browser to **http://127.0.0.1:8050/**.

To run benchmarks:
```bash
python3 run_benchmark.py
```

---

## 2. How to Add a New Algorithm
The simulator automatically loads algorithms from the `algorithms/` folder.

1.  **Create a file**: Create a new `.py` file in `algorithms/` (e.g., `leader_election.py`).
2.  **Define a class**: Create a class with a `run` method.
3.  **Implement logic**: Use the `nodes` list to read messages and send replies.

**Template:**
```python
class MyAlgorithm:
    def run(self, nodes, step_count):
        # 1. Process received messages
        for node in nodes:
            while node.inbox:
                msg = node.inbox.pop(0)
                # Your logic here...
                if "VOTE" in str(msg):
                    node.store['voted'] = True
        
        # 2. Take actions (e.g., send heartbeats)
        if step_count % 10 == 0:
            nodes[0].send("HEARTBEAT", target="R1-S2")
```

---

## 3. Algorithm API & Variables
Your algorithm interacts with `VisualNode` objects. Here are the key variables you can use:

### Node State (Read/Write)
- **`node.inbox`** *(List)*: Queue of received messages. **You must pop messages from here to process them.**
- **`node.store`** *(Dict)*: **Persistent storage** for your algorithm.
    - Use this to store things like `current_term`, `voted_for`, `log`, etc.
    - **Special Key**: `node.store['role']` (e.g., "Leader", "Follower") will be **displayed visually** on the server box in the UI.
- **`node.state`** *(String)*: "IDLE", "PROCESSING", or "SHUTDOWN".

### Node Info (Read Only)
- **`node.node_id`** *(String)*: Unique ID (e.g., "R1-S1").
- **`node.rack_id`** *(String)*: Location (e.g., "Rack1").
- **`node.is_shutdown`** *(Bool)*: True if the node is powered off.

### Actions
- **`node.send(message, target=node_id)`**: Asynchronous send (fire and forget).
- **`node.sync_send(message, target=node_id, timeout=2.0)`**: Synchronous send with acknowledgment. Returns `True` if successful.
- **`node.set_timer(timer_id, delay, callback)`**: Schedule a callback.

---

## 4. Configuration (Probabilities & Thresholds)
The simulation parameters are defined in **`sim_engine.py`** and `utils/protocol.py`.

### Synchronization
- `sync_model`: "synchronous" | "asynchronous" | "partial_synchronous"
- `max_clock_drift`: Maximum clock drift (default: 0.01s)
- `sync_timeout`: Timeout for sync operations (default: 5.0s)

### Network
- `packet_loss_rate`: 0.0 - 1.0 (default: 0.0)
- `bandwidth_mbps`: Network bandwidth (default: 1000.0)
- `jitter_range`: Latency variance in seconds (default: 0.0)
- `reorder_probability`: 0.0 - 1.0 (default: 0.0)

### Faults
- `hw_fault_prob`: Hardware fault rate (default: 0.005)
- `power_failure_prob`: Power failure rate (default: 0.5)

---

## 5. Benchmarking

### Create Scenario
Create a JSON file in `benchmarks/`:
```json
{
  "name": "my_scenario",
  "description": "Test scenario",
  "duration": 60.0,
  "latency": 1.0,
  "packet_loss_rate": 0.05,
  "sync_model": "asynchronous",
  "algorithm_name": "random_traffic"
}
```

### Run Benchmark
```python
from utils.benchmark import BenchmarkRunner, BenchmarkScenario

scenario = BenchmarkScenario.from_json("benchmarks/my_scenario.json")
runner = BenchmarkRunner()
results = runner.run_scenario(scenario, create_simulator, num_trials=3)
```

---

## 6. Performance Metrics

### Latency Statistics
- Min, Max, Average
- Median (P50)
- P95, P99 percentiles

### Throughput
- Messages per second
- Bytes per second

### Network Stats
- Packets sent/received/dropped
- Delivery rate
- Sync violations/timeouts

### Export Metrics
```python
# JSON export
sim.metrics.export_to_json("metrics.json", sim.time)
```

---

## 7. Best Practices

1. **Use sync_send for consensus protocols** - Ensures message delivery
2. **Set appropriate timeouts** - Based on expected network conditions
3. **Handle partitions gracefully** - Design for split-brain scenarios
4. **Monitor metrics** - Track latency and throughput
5. **Run multiple trials** - Get statistical significance
