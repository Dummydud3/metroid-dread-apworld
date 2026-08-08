from logic_parser import RandovaniaLogicParser
from pathlib import Path

p = RandovaniaLogicParser(Path("logic_database"))
p.load_database()

# Check First Tutorial area
area = p.regions['Artaria']['areas']['First Tutorial']
print("=== First Tutorial Nodes ===")
for node_name, node_data in list(area['nodes'].items())[:5]:
    print(f"\n{node_name}:")
    print(f"  Type: {node_data['node_type']}")
    connections = node_data.get('connections', {})
    print(f"  Connections ({len(connections)}): {list(connections.keys())}")
    if node_data['node_type'] == 'dock':
        print(f"  Default connection: {node_data.get('default_connection')}")

# Check a pickup node
print("\n=== Looking for pickup nodes ===")
charge_tutorial = p.regions['Artaria']['areas']['Charge Tutorial']
for node_name, node_data in charge_tutorial['nodes'].items():
    if node_data['node_type'] == 'pickup':
        print(f"\n{node_name}:")
        print(f"  Pickup index: {node_data.get('extra', {}).get('pickup_index')}")
        connections = node_data.get('connections', {})
        print(f"  Connections: {list(connections.keys())}")
        break
