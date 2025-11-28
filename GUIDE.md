# Datacenter Simulator Developer Guide

## 1. How to Run
Open your terminal and run:
```bash
python3 app.py
```
Then open your web browser to **http://127.0.0.1:8050/**.

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
- **`node.send(message, target=node_id)`**: Sends a message. `message` can be a string or object.

---

## 4. Configuration (Probabilities & Thresholds)
The simulation parameters are defined in **`sim_engine.py`**.

Look for the `SimulationConfig` class at the top of the file:
```python
@dataclass
class SimulationConfig:
    idle_spike_prob: float = 0.1      # Chance of random CPU load
    hw_fault_prob: float = 0.005      # Chance of hardware failure
    critical_threshold: float = 90.0  # % usage to turn node RED
    # ...
```
You can change the default values here directly.

---

## 5. How to Add New Sliders & Controls
To add a new slider to the UI (e.g., to control a new variable):

1.  **Add the UI Element**:
    Open `app.py` and find the `app.layout` section (specifically the `# Sidebar` div). Add a new slider:
    ```python
    create_slider("My New Param", 'slider-my-param', min=0, max=100, default=50)
    ```

2.  **Connect the Logic**:
    Find the `@app.callback` function named `update_config` in `app.py`.
    - Add `Input('slider-my-param', 'value')` to the list of inputs.
    - Add a new argument to the `update_config` function definition.
    - Update the config variable inside the function:
      ```python
      sim_engine.config.my_new_param = new_slider_value
      ```
