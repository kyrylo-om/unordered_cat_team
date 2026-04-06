import argparse
import json
import random
import math
import re
from faker import Faker

def generate_network(num_warehouses, num_shops, width, height, node_spacing, min_dist, max_dist, min_cost, max_cost):
    fake = Faker('en_US')
    nodes_positions = []
    
    while len(nodes_positions) < (num_warehouses + num_shops):
        x = random.randint(50, width - 50)
        y = random.randint(50, height - 50)
        
        if all(math.hypot(x - p['x'], y - p['y']) >= node_spacing for p in nodes_positions):
            nodes_positions.append({'x': x, 'y': y})

    warehouses = []
    shops = []
    all_nodes = []

    for i, pos in enumerate(nodes_positions):
        city_name = fake.unique.city()
        
        if i < num_warehouses:
            full_name = f"City {city_name}"
            node_id = re.sub(r'[^a-z0-9]', '_', full_name.lower())
            node_id = re.sub(r'_+', '_', node_id).strip('_')
            
            node_data = {
                "id": node_id,
                "name": full_name,
                "position": pos
            }
            warehouses.append(node_data)
        else:
            full_name = f"Village {city_name}"
            node_id = re.sub(r'[^a-z0-9]', '_', full_name.lower())
            node_id = re.sub(r'_+', '_', node_id).strip('_')
            
            node_data = {
                "id": node_id,
                "name": full_name,
                "inventory": random.randint(50, 150),
                "position": pos
            }
            shops.append(node_data)
            
        all_nodes.append(node_data)

    routes = []
    created_edges = set()

    for i, n1 in enumerate(all_nodes):
        distances = []
        for j, n2 in enumerate(all_nodes):
            if i != j:
                spatial_dist = math.hypot(n1['position']['x'] - n2['position']['x'], 
                                  n1['position']['y'] - n2['position']['y'])
                distances.append((spatial_dist, n2))
                
        distances.sort(key=lambda item: item[0])
        
        for dist, n2 in distances[:2]:
            edge = tuple(sorted([n1['id'], n2['id']]))
            
            if edge not in created_edges:
                created_edges.add(edge)
                
                final_distance = round(random.uniform(min_dist, max_dist), 1)
                route_time = random.randint(1, 5)
                route_cost = round(random.uniform(min_cost, max_cost), 1)
                
                routes.append({
                    "from": n1['id'],
                    "to": n2['id'],
                    "time": route_time,
                    "cost": route_cost,
                    "distance": final_distance
                })

    network = {
        "name": "Distribution Network",
        "warehouses": warehouses,
        "shops": shops,
        "routes": routes
    }
    
    return network

if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    
    parser.add_argument("-w", "--warehouses", type=int, default=3)
    parser.add_argument("-s", "--shops", type=int, default=15)
    parser.add_argument("-W", "--width", type=int, default=1000)
    parser.add_argument("-H", "--height", type=int, default=800)
    parser.add_argument("-o", "--output", type=str, default="generated_network.json")
    
    parser.add_argument("--min-dist", type=float, default=1.0)
    parser.add_argument("--max-dist", type=float, default=5.0)
    parser.add_argument("--min-cost", type=float, default=1.0)
    parser.add_argument("--max-cost", type=float, default=5.0)

    args = parser.parse_args()

    generated_data = generate_network(
        num_warehouses=args.warehouses, 
        num_shops=args.shops,
        width=args.width,
        height=args.height,
        node_spacing=100,
        min_dist=args.min_dist,
        max_dist=args.max_dist,
        min_cost=args.min_cost,
        max_cost=args.max_cost
    )
    
    with open(args.output, 'w', encoding='utf-8') as f:
        json.dump(generated_data, f, ensure_ascii=False, indent=2)
        
    print(f"Success! Data saved to {args.output}")