from sim_engine import AlgorithmLoader
import dash
from dash import html, dcc, Input, Output, State
import dash_cytoscape as cyto
from sim_engine import VisualSimulator, VisualNetwork, VisualNode, VisualSwitch, config
import os

# Load GUIDE.md content
guide_path = os.path.join(os.path.dirname(__file__), 'GUIDE.md')
with open(guide_path, 'r') as f:
    guide_content = f.read()

# --- Setup Simulation ---
sim = VisualSimulator()

discovered = AlgorithmLoader.discover_algorithms()

for algo_name, algo_data in discovered.items():
    if algo_data["error"]:
        sim.algorithm_controller.validation_errors[algo_name] = algo_data["error"]
    else:
        sim.algorithm_controller.register_algorithm(
            algo_name, algo_data["instance"])

valid_algos = [name for name in discovered if not discovered[name]["error"]]
if valid_algos:
    sim.algorithm_controller.set_active(valid_algos[0])

net = VisualNetwork(latency=1.0)
sim.register_network(net)

leaf_rack1 = VisualSwitch("Leaf-Rack1", switch_type="Leaf",
                          rack_id="Rack1", ports=48, bandwidth_gbps=10)
leaf_rack2 = VisualSwitch("Leaf-Rack2", switch_type="Leaf",
                          rack_id="Rack2", ports=48, bandwidth_gbps=10)
spine_switch = VisualSwitch(
    "Spine-Switch", switch_type="Spine", ports=96, bandwidth_gbps=100)

net.register_switch(leaf_rack1)
net.register_switch(leaf_rack2)
net.register_switch(spine_switch)

for i in range(5):
    node = VisualNode(
        f"R1-S{i+1}", ip_address=f"192.168.1.{10+i}", rack_id="Rack1", cores=8, ram_gb=32)
    sim.register_node(node)

for i in range(4):
    node = VisualNode(f"R2-S{i+1}", ip_address=f"192.168.2.{10+i}",
                      rack_id="Rack2", cores=16, ram_gb=128)
    sim.register_node(node)

initial_config = [
    {"node_id": f"R1-S{i+1}", "ip_address": f"192.168.1.{10+i}",
     "rack_id": "Rack1", "cores": 8, "ram_gb": 32} for i in range(5)
] + [
    {"node_id": f"R2-S{i+1}", "ip_address": f"192.168.2.{10+i}",
     "rack_id": "Rack2", "cores": 16, "ram_gb": 128} for i in range(4)
]
sim.save_initial_state(initial_config)

app = dash.Dash(__name__)


def create_server_box(node):
    """Create a clickable server box"""
    if node.is_shutdown:
        bg_color = '#CFD8DC'  # Grey (Shutdown)
        border_color = '#90A4AE'
    elif node.is_critical:
        bg_color = '#FFCDD2'  # Red (Critical)
        border_color = '#D32F2F'
    elif node.state == "PROCESSING":
        bg_color = '#FFE082'  # Yellow (Processing)
        border_color = '#FFB74D'
    else:
        bg_color = '#C8E6C9'  # Green (Idle)
        border_color = '#7CB342'

    # power_pct = (node.power_watts / (node.cores * 20 + node.ram_gb * 3)) * 100
    usage_pct = node.cpu_usage

    # Check for algorithm role (e.g. Leader/Follower)
    role_label = html.Div()
    if 'role' in node.store:
        role = node.store['role']
        role_color = '#000'
        if role == 'Leader':
            role_color = '#D32F2F'  # Red text for leader
        elif role == 'Candidate':
            role_color = '#F57C00'

        role_label = html.Div(role, style={
            'fontSize': '9px', 'marginTop': '2px', 'fontWeight': 'bold', 'color': role_color
        })

    return html.Button([
        html.Div(node.node_id, style={
                 'fontWeight': 'bold', 'fontSize': '11px'}),
        html.Div(f"⚙️ {usage_pct:.0f}%", style={
                 'fontSize': '10px', 'marginTop': '3px'}),
        role_label
    ], id={'type': 'server-box', 'index': node.node_id}, n_clicks=0, style={
        'border': f'3px solid {border_color}',
        'borderRadius': '4px',
        'padding': '8px',
        'margin': '4px',
        'backgroundColor': bg_color,
        'width': '85px',
        'cursor': 'pointer',
        'textAlign': 'center'
    })


# --- Initial Elements ---
initial_elements = []
for nid, node in sim.nodes.items():
    initial_elements.append(
        {'data': {'id': nid, 'label': nid, 'type': 'server'}})

for switch_id, switch in net.switches.items():
    if "Leaf" in switch_id:
        label = switch_id.replace("Leaf-", "Leaf ")
    else:
        label = "Spine"
    initial_elements.append(
        {'data': {'id': switch_id, 'label': label, 'type': 'switch'}})

# Edges - Pure hierarchical topology (realistic datacenter)

# Connect servers to their Leaf switches
for nid, node in sim.nodes.items():
    leaf_id = f"Leaf-{node.rack_id}"
    edge_id = f"{nid}_{leaf_id}"
    initial_elements.append(
        {'data': {'id': edge_id, 'source': nid, 'target': leaf_id}})

for rack_id in ["Rack1", "Rack2"]:
    leaf_id = f"Leaf-{rack_id}"
    edge_id = f"{leaf_id}_Spine-Switch"
    initial_elements.append(
        {'data': {'id': edge_id, 'source': leaf_id, 'target': "Spine-Switch"}})

# Rack configuration
RACK_CONFIG = {
    "Rack1": {"name": "Rack 1", "specs": "8C / 32GB", "cores": 8, "ram": 32, "base_ip": "192.168.1."},
    "Rack2": {"name": "Rack 2", "specs": "16C / 128GB", "cores": 16, "ram": 128, "base_ip": "192.168.2."}
}


def create_rack(rack_id):
    """Helper to create a rack container"""
    config = RACK_CONFIG[rack_id]
    return html.Div([
        html.Div(config["name"], style={'textAlign': 'center', 'fontWeight': 'bold',
                 'fontSize': '13px', 'marginBottom': '5px', 'color': 'white'}),
        html.Div(config["specs"], style={
                 'textAlign': 'center', 'fontSize': '10px', 'color': '#aaa', 'marginBottom': '8px'}),
        html.Div(id=f'{rack_id.lower()}-servers', style={'display': 'flex',
                 'flexDirection': 'column', 'alignItems': 'center'}),
        html.Button('+', id={'type': 'add-btn', 'index': rack_id}, n_clicks=0,
                    style={'marginTop': '10px', 'width': '100%', 'backgroundColor': '#4CAF50', 'color': 'white',
                           'border': 'none', 'borderRadius': '4px', 'cursor': 'pointer', 'fontWeight': 'bold'})
    ], style={
        'border': '4px solid #1976D2',
        'backgroundColor': '#263238',
        'borderRadius': '6px',
        'padding': '12px',
        'marginBottom': '15px',
        'width': '130px',
        'marginRight': '15px' if rack_id == "Rack1" else '0'
    })


def create_slider(label, slider_id, min_val, max_val, default_val, step=0.01):
    """Helper to create a labeled slider"""
    marks = {min_val: str(min_val), max_val: str(max_val)}
    if min_val < max_val / 2:
        marks[(min_val + max_val) / 2] = str((min_val + max_val) / 2)

    return html.Div([
        html.Div(label, style={'color': '#aaa',
                 'fontSize': '11px', 'marginTop': '10px'}),
        dcc.Slider(
            id=slider_id,
            min=min_val,
            max=max_val,
            step=step,
            value=default_val,
            marks=marks,
            tooltip={'placement': 'bottom', 'always_visible': True}
        )
    ])


app.layout = html.Div([
    # Sidebar
    html.Div([
        html.H3("Controls", style={'color': 'white', 'textAlign': 'center'}),
        html.Hr(style={'borderColor': '#555'}),

        html.Hr(style={'borderColor': '#555'}),
        create_slider("Sim Speed (ms):", 'slider-speed', 100, 2000, 1000, 100),

        html.Div("Algorithm:", style={
                 'color': '#aaa', 'fontSize': '12px', 'marginTop': '15px', 'marginBottom': '5px'}),
        dcc.Dropdown(
            id='algorithm-dropdown',
            options=[{'label': name, 'value': name} for name in list(
                sim.algorithm_controller.algorithms.keys()) + list(sim.algorithm_controller.validation_errors.keys())],
            value=sim.algorithm_controller.active_algorithm_name,
            style={'marginBottom': '10px'}
        ),
        html.Div(id='algorithm-error', style={'color': '#ff6b6b', 'fontSize': '10px',
                 'marginBottom': '15px', 'padding': '5px', 'backgroundColor': '#2a2a2a', 'borderRadius': '3px'}),

        html.Hr(style={'borderColor': '#555'}),
        html.Div("Simulation Params", style={
                 'color': 'white', 'textAlign': 'center', 'marginBottom': '5px'}),

        create_slider("HW Fault Rate:", 'slider-fault-prob',
                      0, 0.1, 0.005, 0.005),
        create_slider("Power Fail Rate:",
                      'slider-power-fail', 0, 1.0, 0.5, 0.05),
        create_slider("Critical Threshold:",
                      'slider-critical', 50, 100, 90, 5),

        html.Hr(style={'borderColor': '#555', 'marginTop': '20px'}),
        html.Div("Parameter Guide", style={
                 'color': 'white', 'fontSize': '11px', 'fontWeight': 'bold', 'marginBottom': '8px'}),
        html.Div([
            html.Div("• HW Fault: % chance per second a hardware fault appears",
                     style={'color': '#bbb', 'fontSize': '10px', 'marginBottom': '4px'}),
            html.Div("• Power Fail: % chance a fault causes shutdown",
                     style={'color': '#bbb', 'fontSize': '10px', 'marginBottom': '4px'}),
            html.Div("• Critical: CPU/Memory/Disk % threshold to turn red",
                     style={'color': '#bbb', 'fontSize': '10px', 'marginBottom': '4px'}),
        ]),

    ], style={
        'width': '200px',
        'backgroundColor': '#263238',
        'padding': '20px',
        'display': 'flex',
        'flexDirection': 'column',
        'height': '100vh',
        'position': 'fixed',
        'left': 0,
        'top': 0,
        'overflowY': 'auto'
    }),

    # Main Content Area
    html.Div([
        html.H2("Datacenter Simulator", style={
                'textAlign': 'center', 'fontFamily': 'Arial', 'margin': '15px'}),

        # Main Content
        html.Div([
            # Racks Container
            html.Div([
                create_rack("Rack1"),
                create_rack("Rack2")
            ], style={'display': 'flex', 'flexDirection': 'row', 'marginRight': '20px'}),

            # Server Details
            html.Div([
                html.H4("Server Details", style={
                        'textAlign': 'center', 'marginTop': '0', 'marginBottom': '10px', 'padding': '15px'}),
                html.Div(
                    id='server-details', style={'textAlign': 'center', 'padding': '12px', 'fontSize': '12px'})
            ], style={
                'width': '250px',
                'border': '3px solid #333',
                'borderRadius': '6px',
                'backgroundColor': 'white',
                'height': '530px',
                'marginRight': '20px',
                'overflowY': 'auto'
            }),

            # Network Graph
            html.Div([
                html.H4("Network Topology", style={
                        'textAlign': 'center', 'marginTop': '0', 'marginBottom': '10px'}),
                cyto.Cytoscape(
                    id='network-graph',
                    layout={'name': 'cose', 'fit': True, 'padding': 30,
                            'nodeRepulsion': 4000, 'idealEdgeLength': 50},
                    style={'width': '100%', 'height': '450px'},
                    elements=initial_elements,
                    stylesheet=[]  # Will be populated by callback
                )
            ], style={
                'width': '450px',
                'border': '3px solid #333',
                'borderRadius': '6px',
                'padding': '15px',
                'backgroundColor': 'white',
                'height': '500px'
            })
        ], style={'display': 'flex', 'flexDirection': 'row', 'justifyContent': 'center', 'alignItems': 'flex-start', 'margin': '15px auto', 'maxWidth': '1000px'}),

        # System Logs
        html.Div([
            html.H4("System Logs", style={'marginBottom': '8px'}),
            html.Div(id='log-panel', style={
                'height': '100px',
                'overflowY': 'scroll',
                'border': '1px solid #ccc',
                'padding': '8px',
                'fontFamily': 'monospace',
                'fontSize': '10px',
                'backgroundColor': '#f9f9f9'
            })
        ], style={'width': '900px', 'margin': '15px auto'}),

        # Edge Info Panel (for message history)
        html.Div([
            html.H4("Connection Details", style={'marginBottom': '8px'}),
            html.Div(id='edge-details', style={
                'height': '80px',
                'overflowY': 'scroll',
                'border': '1px solid #ccc',
                'padding': '8px',
                'fontFamily': 'monospace',
                'fontSize': '10px',
                'backgroundColor': '#f9f9f9'
            }, children="Click an edge in the graph to view message history")
        ], style={'width': '900px', 'margin': '15px auto'}),

        dcc.Interval(id='interval-component', interval=1000, n_intervals=0),
        dcc.Store(id='selected-server', data=None),
        dcc.Store(id='graph-click-data', data=None),
        # Hidden store for config updates
        dcc.Store(id='config-store', data={})

    ], style={'marginLeft': '220px', 'marginRight': '520px', 'padding': '20px', 'flex': 1}),

    # Right Sidebar Panel
    html.Div([
        html.Hr(style={'borderColor': '#555'}),
        html.Div(id='right-panel-content', style={
            'color': '#ddd',
            'fontSize': '12px',
            'padding': '10px',
            'overflowY': 'auto',
            'height': 'calc(100vh - 100px)'
        }, children=[
            dcc.Markdown(guide_content, style={'color': '#ddd'})
        ])
    ], style={
        'width': '500px',
        'backgroundColor': '#263238',
        'padding': '20px',
        'display': 'flex',
        'flexDirection': 'column',
        'height': '100vh',
        'position': 'fixed',
        'right': 0,
        'top': 0
    })

], style={'fontFamily': 'Arial', 'backgroundColor': '#fafafa', 'minHeight': '100vh', 'display': 'flex'})


@app.callback(
    Output('selected-server', 'data'),
    [Input({'type': 'server-box', 'index': dash.dependencies.ALL}, 'n_clicks'),
     Input({'type': 'power-btn', 'index': dash.dependencies.ALL}, 'n_clicks'),
     Input({'type': 'remove-btn', 'index': dash.dependencies.ALL}, 'n_clicks'),
     Input({'type': 'add-btn', 'index': dash.dependencies.ALL}, 'n_clicks'),
     Input('network-graph', 'tapNodeData')],
    [State('selected-server', 'data')]
)
def handle_interactions(server_clicks, power_clicks, remove_clicks, add_clicks, tap_node, current_selection):
    ctx = dash.callback_context
    if not ctx.triggered:
        return current_selection

    button_id_str = ctx.triggered[0]['prop_id'].split('.')[0]

    # Handle graph node clicks
    if 'tapNodeData' in button_id_str:
        if tap_node and isinstance(tap_node, dict):
            node_id = tap_node.get('id')
            # Only select if it's a server node (not a switch)
            if node_id and node_id in sim.nodes:
                return node_id
        return current_selection

    if not button_id_str:
        return current_selection

    # Check if the value that triggered it is actually a click (truthy)
    trigger_value = ctx.triggered[0]['value']
    if not trigger_value:
        return current_selection

    import json
    try:
        button_id = json.loads(button_id_str)
    except (json.JSONDecodeError, ValueError):
        return current_selection

    action = button_id.get('type')
    node_id = button_id.get('index')

    if not action or not node_id:
        return current_selection

    if action == 'server-box':
        return node_id

    elif action == 'power-btn':
        sim.toggle_node_power(node_id)
        return current_selection

    elif action == 'remove-btn':
        if sim.remove_node(node_id):
            if current_selection == node_id:
                return None
        return current_selection

    elif action == 'add-btn':
        # Add new node to rack
        rack_id = node_id
        rack_config = RACK_CONFIG[rack_id]

        # Generate new ID
        rack_prefix = "R1" if rack_id == "Rack1" else "R2"
        current_nodes = list(sim.nodes.values())
        existing_ids = [
            n.node_id for n in current_nodes if n.rack_id == rack_id]
        count = len(existing_ids) + 1
        while f"{rack_prefix}-S{count}" in [n.node_id for n in current_nodes]:
            count += 1
        new_id = f"{rack_prefix}-S{count}"

        # Generate IP
        ip_suffix = 10 + \
            len([n for n in current_nodes if n.rack_id == rack_id])
        while f"{rack_config['base_ip']}{ip_suffix}" in [n.ip_address for n in current_nodes]:
            ip_suffix += 1
        new_ip = f"{rack_config['base_ip']}{ip_suffix}"

        new_node = VisualNode(new_id, ip_address=new_ip, rack_id=rack_id,
                              cores=rack_config['cores'], ram_gb=rack_config['ram'])
        sim.register_node(new_node)
        sim.log(new_id, "Server added")

        return current_selection
        nodes.append(new_node)
        sim.log(new_id, f"New server added to {rack_id}")

        return current_selection

    return current_selection


@app.callback(
    [Output('rack1-servers', 'children'),
     Output('rack2-servers', 'children'),
     Output('network-graph', 'stylesheet'),
     Output('network-graph', 'elements'),
     Output('server-details', 'children'),
     Output('log-panel', 'children')],
    [Input('interval-component', 'n_intervals'),
     Input('selected-server', 'data')],
    [State('network-graph', 'elements')]
)
def update_datacenter(n, selected_server, current_elements):
    nodes = list(sim.nodes.values())

    # Only run simulation if algorithm controller is not paused
    if not sim.algorithm_controller.is_paused:
        sim.step(1.0)

        sim.algorithm_controller.execute(nodes, n)

        for node in nodes:
            node.update_metrics()

        for switch in net.switches.values():
            switch.update_metrics()

    # Rack servers
    rack1_servers = [create_server_box(node)
                     for node in nodes if node.rack_id == "Rack1"]
    rack2_servers = [create_server_box(node)
                     for node in nodes if node.rack_id == "Rack2"]

    # Network Graph Stylesheet
    stylesheet = [
        {'selector': 'node[type = "server"]', 'style': {
            'content': 'data(label)',
            'background-color': '#7CB342',
            'color': 'white',
            'font-size': '11px',
            'font-weight': 'bold',
            'width': '40px',
            'height': '40px',
            'text-valign': 'center',
            'text-halign': 'center',
            'shape': 'ellipse'
        }},
        {'selector': 'node[type = "switch"]', 'style': {
            'content': 'data(label)',
            'background-color': '#1976D2',
            'color': 'white',
            'font-size': '11px',
            'font-weight': 'bold',
            'width': '60px',
            'height': '60px',
            'text-valign': 'center',
            'text-halign': 'center',
            'shape': 'round-rectangle'
        }},
        {'selector': 'edge', 'style': {
            'line-color': '#ccc',
            'width': 1.5,
            'curve-style': 'bezier'
        }}
    ]

    for nid, node in sim.nodes.items():
        tooltip = f"{nid}\nCPU: {node.cpu_usage:.0f}%\nRAM: {node.memory_usage:.0f}%\nDisk: {node.disk_usage:.0f}%\nPower: {node.power_watts:.0f}W\nState: {node.state}"
        stylesheet.append({
            'selector': f'node[id = "{nid}"]',
            'style': {'label': tooltip if False else f'data(label)'}
        })

        if node.is_shutdown:
            stylesheet.append({
                'selector': f'node[id = "{nid}"]',
                'style': {'background-color': '#CFD8DC'}  # Grey
            })
        elif node.is_critical:
            stylesheet.append({
                'selector': f'node[id = "{nid}"]',
                'style': {'background-color': '#E57373'}  # Red
            })

    # Add active edge styles - highlight routing paths
    for msg in sim.message_history[-5:]:
        src_id = msg['src']
        dst_id = msg['dst']

        src_node = sim.nodes.get(src_id)
        dst_node = sim.nodes.get(dst_id)

        if src_node and dst_node:
            src_leaf = f"Leaf-{src_node.rack_id}"
            dst_leaf = f"Leaf-{dst_node.rack_id}"

            stylesheet.append({
                'selector': f'edge[source = "{src_id}"][target = "{src_leaf}"]',
                'style': {'line-color': '#64B5F6', 'width': 4}
            })

            if src_node.rack_id == dst_node.rack_id:
                stylesheet.append({
                    'selector': f'edge[source = "{src_leaf}"][target = "{dst_id}"]',
                    'style': {'line-color': '#64B5F6', 'width': 4}
                })
            else:
                stylesheet.append({
                    'selector': f'edge[source = "{src_leaf}"][target = "Spine-Switch"]',
                    'style': {'line-color': '#FFB74D', 'width': 4}
                })
                stylesheet.append({
                    'selector': f'edge[source = "Spine-Switch"][target = "{dst_leaf}"]',
                    'style': {'line-color': '#FFB74D', 'width': 4}
                })
                stylesheet.append({
                    'selector': f'edge[source = "{dst_leaf}"][target = "{dst_id}"]',
                    'style': {'line-color': '#64B5F6', 'width': 4}
                })

    # Highlight congested switches
    for switch_id, switch in net.switches.items():
        if switch.is_congested:
            stylesheet.append({
                'selector': f'node[id = "{switch_id}"]',
                'style': {'background-color': '#FF5722'}
            })

    # Network Graph Elements (Update only if topology changes)
    current_node_ids = set([e['data']['id']
                           for e in current_elements if 'source' not in e['data']])
    sim_node_ids = set(sim.nodes.keys())

    if current_node_ids != sim_node_ids:
        new_elements = []
        for nid in sim.nodes:
            new_elements.append(
                {'data': {'id': nid, 'label': nid, 'type': 'server'}})

        for switch_id, switch in net.switches.items():
            if "Leaf" in switch_id:
                label = switch_id.replace("Leaf-", "Leaf ")
            else:
                label = "Spine"
            new_elements.append(
                {'data': {'id': switch_id, 'label': label, 'type': 'switch'}})

        for nid, node in sim.nodes.items():
            leaf_id = f"Leaf-{node.rack_id}"
            edge_id = f"{nid}_{leaf_id}"
            new_elements.append(
                {'data': {'id': edge_id, 'source': nid, 'target': leaf_id}})

        for rack_id in ["Rack1", "Rack2"]:
            leaf_id = f"Leaf-{rack_id}"
            edge_id = f"{leaf_id}_Spine-Switch"
            new_elements.append(
                {'data': {'id': edge_id, 'source': leaf_id, 'target': "Spine-Switch"}})
    else:
        new_elements = dash.no_update

    # Server details panel
    if selected_server:
        node = sim.nodes.get(selected_server)
        if node:
            details = html.Div([
                html.H5(f"{node.node_id}", style={'textAlign': 'center',
                        'color': '#1976D2', 'marginBottom': '8px'}),
                html.Hr(style={'margin': '8px 0'}),
                html.Div(f"IP: {node.ip_address}",
                         style={'marginBottom': '4px'}),
                html.Div(f"Specs: {node.cores}C / {node.ram_gb}GB",
                         style={'marginBottom': '8px'}),

                # Algorithm State Display
                html.Div([
                    html.Div("Algorithm State:", style={
                             'fontWeight': 'bold', 'fontSize': '11px', 'marginTop': '5px'}),
                    html.Pre(str(node.store) if node.store else "No state", style={
                        'fontSize': '10px', 'backgroundColor': '#f0f0f0', 'padding': '5px', 'borderRadius': '3px', 'overflowX': 'auto'
                    })
                ]) if node.store else html.Div(),

                html.Hr(style={'margin': '8px 0'}),
                html.Div(f"Status: {node.state}", style={
                         'fontWeight': 'bold', 'marginBottom': '8px'}),
                html.Div(f"CPU: {node.cpu_usage:.1f}%",
                         style={'marginBottom': '3px'}),
                html.Div(f"Memory: {node.memory_usage:.1f}%",
                         style={'marginBottom': '3px'}),
                html.Div(f"Disk: {node.disk_usage:.1f}%",
                         style={'marginBottom': '3px'}),
                html.Div(f"Power: {node.power_watts:.0f}W", style={
                         'marginTop': '6px', 'fontWeight': 'bold'}),
                html.Hr(style={'margin': '8px 0'}),
                html.Div("Critical: " + ("⚠️ YES" if node.is_critical else "✓ NO"),
                         style={'fontWeight': 'bold', 'marginBottom': '6px',
                                'color': 'red' if node.is_critical else 'green'}),
                html.Div("Faults:", style={
                         'fontWeight': 'bold', 'marginTop': '6px', 'marginBottom': '4px'}),
                html.Div([html.Div(f"• {fault}", style={'fontSize': '11px', 'color': 'red', 'marginBottom': '2px'})
                         for fault in node.faults] if node.faults else
                         [html.Div("None", style={'fontSize': '11px', 'color': 'green'})]),
                html.Hr(style={'margin': '10px 0'}),
                html.Div([
                    html.Button('Shutdown' if not node.is_shutdown else 'Restart', id={'type': 'power-btn', 'index': node.node_id}, n_clicks=0,
                                style={'backgroundColor': '#E57373' if not node.is_shutdown else '#81C784', 'color': 'white',
                                       'border': 'none', 'borderRadius': '4px', 'padding': '5px 10px', 'marginRight': '5px', 'cursor': 'pointer', 'fontSize': '11px'}),
                    html.Button('Remove', id={'type': 'remove-btn', 'index': node.node_id}, n_clicks=0,
                                style={'backgroundColor': '#B0BEC5', 'color': 'white',
                                       'border': 'none', 'borderRadius': '4px', 'padding': '5px 10px', 'cursor': 'pointer', 'fontSize': '11px'})
                ], style={'textAlign': 'center', 'marginTop': '10px'})
            ])
        else:
            details = html.Div("Server not found", style={
                               'textAlign': 'center', 'padding': '40px'})
    else:
        details = html.Div("Click a server to view details", style={
                           'textAlign': 'center', 'padding': '40px', 'color': '#999'})

    # Logs
    log_items = [html.Div(f"[{t:.1f}s] {nid}: {msg}")
                 for t, nid, msg in reversed(sim.logs[-8:])]

    return rack1_servers, rack2_servers, stylesheet, new_elements, details, log_items


@app.callback(
    Output('algorithm-error', 'children'),
    Input('algorithm-dropdown', 'value')
)
def update_algorithm(selected_algo):
    if not selected_algo:
        return ""

    if selected_algo in sim.algorithm_controller.validation_errors:
        error_msg = sim.algorithm_controller.validation_errors[selected_algo]
        sim.algorithm_controller.is_paused = True

        if config.reset_on_error:
            sim.reset()
            return f"⚠️ ERROR: {error_msg} (Simulation Reset)"

        return f"⚠️ ERROR: {error_msg} (Simulation Paused)"

    sim.algorithm_controller.set_active(selected_algo)
    return f"✓ {selected_algo} active"


@app.callback(
    Output('config-store', 'data'),
    [Input('slider-fault-prob', 'value'),
     Input('slider-power-fail', 'value'),
     Input('slider-critical', 'value')]
)
def update_config(fault_prob, power_fail_prob, critical_thresh):
    import sim_engine
    sim_engine.config.hw_fault_prob = fault_prob
    sim_engine.config.power_failure_prob = power_fail_prob
    sim_engine.config.critical_threshold = critical_thresh

    print(
        f"CONFIG: HW_Fault={fault_prob:.3f}, Power_Fail={power_fail_prob:.2f}, Critical={critical_thresh}")

    return {'updated': True}


@app.callback(
    Output('interval-component', 'interval'),
    Input('slider-speed', 'value')
)
def update_speed(speed_ms):
    return speed_ms


@app.callback(
    Output('edge-details', 'children'),
    Input('network-graph', 'tapEdgeData')
)
def display_edge_info(edge_data):
    if not edge_data or not isinstance(edge_data, dict):
        return "Click an edge in the graph to view message history"

    edge_id = edge_data.get('id', '')
    source = edge_data.get('source', '')
    target = edge_data.get('target', '')

    if not source or not target:
        return f"Edge data incomplete: {edge_data}"

    messages = []
    edge_description = ""

    if 'Leaf' in source or 'Leaf' in target or 'Spine' in source or 'Spine' in target:
        if 'Spine' in source or 'Spine' in target:
            messages = [
                msg for msg in sim.message_history[-50:]
                if sim.nodes.get(msg['src']) and sim.nodes.get(msg['dst']) and
                sim.nodes[msg['src']].rack_id != sim.nodes[msg['dst']].rack_id
            ]
            edge_description = f"Spine Switch Traffic (Inter-rack messages)"
        elif 'Leaf' in source or 'Leaf' in target:
            switch_id = source if 'Leaf' in source else target
            server_id = target if 'Leaf' in source else source

            if server_id in sim.nodes:
                messages = [
                    msg for msg in sim.message_history[-50:]
                    if msg['src'] == server_id or msg['dst'] == server_id
                ]
                edge_description = f"Leaf Switch Traffic for {server_id}"

    if not messages:
        total_msgs = len(sim.message_history)
        return html.Div([
            html.Div(edge_description or f"Connection: {source} ↔ {target}",
                     style={'fontWeight': 'bold'}),
            html.Div(f"No messages routed through this connection",
                     style={'color': '#999', 'marginTop': '5px'}),
            html.Div(f"(Total messages in system: {total_msgs})",
                     style={'fontSize': '9px', 'color': '#666'})
        ])

    msg_items = []
    msg_items.append(html.Div(edge_description or f"Connection: {source} ↔ {target}",
                              style={'fontWeight': 'bold', 'marginBottom': '5px'}))
    msg_items.append(html.Div(f"Messages routed: {len(messages)}",
                              style={'marginBottom': '5px', 'color': '#666'}))

    for msg in reversed(messages[-10:]):
        msg_items.append(
            html.Div(f"[{msg['time']:.1f}s] {msg['src']} → {msg['dst']}: {msg['msg'][:30]}",
                     style={'fontSize': '9px', 'marginBottom': '2px'})
        )

    return msg_items


if __name__ == '__main__':
    app.run(debug=True)
