import networkx as nx
from dataclasses import dataclass
from typing import Dict, List, Optional
import logging


logger = logging.getLogger(__name__)

@dataclass
class Shipment:
    from_loc: str; to_loc: str; amount: int
    departure_t: int; arrival_t: int; edge_cost: int = 0
    @property
    def total_cost(self) -> int: return self.edge_cost * self.amount

class StorageInventoryEngine:
    def __init__(self, vehicle_cap: int = 100, horizon: int = 5, max_trucks_per_route_tick: int = 3):
        self.vehicle_cap = max(1, int(vehicle_cap))
        self.horizon = horizon
        self.max_trucks_per_route_tick = max(1, int(max_trucks_per_route_tick))
        self.nodes, self.edges = [], []
        self.stocks, self.demand_rates = {}, {}
        self.in_transit: List[Shipment] = []
        self.total_cost = 0
        self.history = []

    def initialize(self, package: dict):
        self.nodes = package["nodes"]
        self.edges = package["routes"]
        self.stocks = {n: int(package["initial_stocks"].get(n, 0)) for n in self.nodes}
        self.demand_rates = {n: int(package.get("demand_rates", {}).get(n, 0)) for n in self.nodes}

    def _consume(self):
        for loc, rate in self.demand_rates.items():
            actual = min(rate, self.stocks.get(loc, 0))
            self.stocks[loc] -= actual

    def _build_graph(self, current_t: int, targets: Dict[str, int]) -> Optional[nx.DiGraph]:
        G = nx.DiGraph()
        T = self.horizon

        forecast_targets: Dict[str, int] = {}
        for loc, target in targets.items():
            demand_rate = max(0, int(self.demand_rates.get(loc, 0)))
            forecast_targets[loc] = max(0, int(target)) + (demand_rate * T)

        for t in range(T + 1):
            for loc in self.nodes:
                G.add_node((loc, t))
                if t < T:
                    G.add_edge((loc, t), (loc, t + 1), capacity=10**6, weight=1)

        for e in self.edges:
            for t in range(T + 1 - e["time"]):
                route_capacity = self.vehicle_cap * self.max_trucks_per_route_tick
                G.add_edge((e["from"], t), (e["to"], t + e["time"]), 
                           capacity=route_capacity, weight=int(e["cost"] * 10))

        G.add_node("source"); G.add_node("sink")

        inbound_by_loc: Dict[str, List[tuple[int, int]]] = {}
        for s in self.in_transit:
            dt = s.arrival_t - current_t
            if 0 < dt <= T:
                inbound_by_loc.setdefault(s.to_loc, []).append((dt, int(s.amount)))

        supply_sum = 0
        for loc in self.nodes:
            reserve = forecast_targets.get(loc, 0)

            stock = max(0, int(self.stocks.get(loc, 0)))
            reserved_from_stock = min(stock, reserve)
            reserve -= reserved_from_stock
            available_stock = stock - reserved_from_stock
            if available_stock > 0:
                G.add_edge("source", (loc, 0), capacity=available_stock, weight=0)
                supply_sum += available_stock

            inbound_items = sorted(inbound_by_loc.get(loc, []), key=lambda item: item[0])
            for dt, amount in inbound_items:
                reserved_from_inbound = min(amount, reserve)
                reserve -= reserved_from_inbound
                available_inbound = amount - reserved_from_inbound
                if available_inbound > 0:
                    G.add_edge("source", (loc, dt), capacity=available_inbound, weight=0)
                    supply_sum += available_inbound

        needed_sum = 0
        for loc, forecast_target in forecast_targets.items():
            on_way = sum(
                int(s.amount)
                for s in self.in_transit
                if s.to_loc == loc and 0 < (s.arrival_t - current_t) <= T
            )
            gap = max(0, forecast_target - self.stocks[loc] - on_way)
            if gap > 0:
                needed_sum += gap
                d_node = f"sink_{loc}"
                G.add_edge(d_node, "sink", capacity=gap, weight=0)
                for t in range(1, T + 1):
                    # Пріоритет часу: чим раніше, тим вигідніше
                    G.add_edge((loc, t), d_node, capacity=gap, weight=-10000 + (t * 10))

        try:
            max_reachable_flow = int(
                nx.maximum_flow_value(G, "source", "sink", capacity="capacity")
            )
        except Exception:
            max_reachable_flow = 0

        flow_val = min(supply_sum, needed_sum, max_reachable_flow)
        if flow_val <= 0: return None
        G.nodes["source"]["demand"], G.nodes["sink"]["demand"] = -flow_val, flow_val
        return G

    def step(self, t: int, targets: Dict[str, int]):
        self._consume()
        created_shipments: List[Shipment] = []
        arrived = [s for s in self.in_transit if s.arrival_t <= t]
        for s in arrived:
            self.stocks[s.to_loc] += s.amount
            self.in_transit.remove(s)

        G = self._build_graph(t, targets)
        if G:
            try:
                flow = nx.min_cost_flow(G)
                routes_map = {(e["from"], e["to"]): e for e in self.edges}

                for loc in self.nodes:
                    u = (loc, 0)
                    if u in flow:
                        for v_node, qty in flow[u].items():
                            qty = int(round(qty))

                            if qty > 0 and isinstance(v_node, tuple) and v_node[0] != loc:
                                dest_loc = v_node[0]
                                e_info = routes_map.get((loc, dest_loc))
                                if e_info:
                                    amt = min(qty, self.stocks[loc])
                                    if amt <= 0:
                                        continue
                                    while amt > 0:
                                        shipment_amount = min(amt, self.vehicle_cap)
                                        ship = Shipment(
                                            loc,
                                            dest_loc,
                                            shipment_amount,
                                            t,
                                            t + e_info["time"],
                                            e_info["cost"],
                                        )
                                        self.in_transit.append(ship)
                                        created_shipments.append(ship)
                                        self.stocks[loc] -= shipment_amount
                                        self.total_cost += ship.total_cost
                                        amt -= shipment_amount
            except Exception as exc:
                logger.warning("min_cost_flow failed at tick %s: %s", t, exc)
        self.history.append({"t": t, "stocks": dict(self.stocks), "transit": sum(s.amount for s in self.in_transit)})
        return {
            "created_shipments": created_shipments,
            "arrived_shipments": arrived,
        }
