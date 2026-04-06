import json
import tempfile
from types import SimpleNamespace
from unittest.mock import patch

from django.contrib.auth.models import User
from django.core.files.base import ContentFile
from django.test import Client, SimpleTestCase, TestCase, override_settings

from .json_parser import parse_network_json
from algo import StorageInventoryEngine
from .models import NetworkDefinition, Route, Shop, Warehouse
from .consumers import _snapshot_payload
from .simulation import SimulationRuntime
from .store_account_service import StoreAccountService
from .user_roles import ROLE_MANAGER, ROLE_SHOP_WORKER, set_user_role
from .views import _build_generated_edges


class ParseNetworkJsonTests(SimpleTestCase):
    def test_parse_network_json_preserves_routes_and_positions(self):
        payload = {
            "warehouses": [
                {
                    "id": "warehouse_a",
                    "name": "Warehouse A",
                    "position": {"x": 120, "y": 0},
                },
            ],
            "shops": [
                {
                    "id": "shop_a",
                    "name": "Shop A",
                    "inventory": 25,
                    "position": {"x": 120, "y": 220},
                },
            ],
            "routes": [
                {"from": "warehouse_a", "to": "shop_a", "time": 1, "cost": 4.5},
            ],
        }

        with tempfile.NamedTemporaryFile("w+", suffix=".json", encoding="utf-8") as handle:
            json.dump(payload, handle)
            handle.flush()

            parsed = parse_network_json(handle.name)

        self.assertEqual(parsed["routes"][0]["from"], "warehouse_a")
        self.assertEqual(parsed["routes"][0]["to"], "shop_a")
        self.assertEqual(parsed["routes"][0]["time"], 1.0)
        self.assertEqual(parsed["routes"][0]["cost"], 4.5)
        self.assertEqual(parsed["warehouses"][0]["position"], {"x": 120.0, "y": 0.0})
        self.assertEqual(parsed["shops"][0]["position"], {"x": 120.0, "y": 220.0})
        self.assertEqual(parsed["warehouses"][0]["inventory"], 500)
        self.assertEqual(parsed["shops"][0]["target"], 0)
        self.assertEqual(parsed["shops"][0]["demand_rate"], 0)


class GeneratedEdgesTests(SimpleTestCase):
    def test_build_generated_edges_connects_warehouses_and_shops(self):
        warehouses = [
            SimpleNamespace(node_id="warehouse_a", name="Warehouse A"),
            SimpleNamespace(node_id="warehouse_b", name="Warehouse B"),
        ]
        shops = [
            SimpleNamespace(node_id="shop_a", name="Shop A"),
            SimpleNamespace(node_id="shop_b", name="Shop B"),
            SimpleNamespace(node_id="shop_c", name="Shop C"),
        ]

        edges = _build_generated_edges(warehouses, shops)

        self.assertEqual(len(edges), 4)
        self.assertEqual(edges[0]["source"], "warehouse_a")
        self.assertEqual(edges[0]["target"], "warehouse_b")
        self.assertTrue(all(edge["data"]["generated"] for edge in edges))


class StoreDemandApiTests(TestCase):
    def setUp(self):
        self.client = Client()
        self.user = User.objects.create_user(username="shop_user", password="test-pass-123")
        set_user_role(self.user.id, ROLE_SHOP_WORKER)
        self.shop = Shop.objects.create(
            name="Shop One",
            node_id="shop_1",
            user=self.user,
            inventory=40,
            target=120,
            demand_rate=5,
        )

    def test_store_demand_updates_target_and_demand_rate(self):
        self.client.force_login(self.user)

        response = self.client.post(
            "/api/store/demand",
            data=json.dumps({"target": 170, "demandRate": 12}),
            content_type="application/json",
        )

        self.assertEqual(response.status_code, 200)
        self.shop.refresh_from_db()
        self.assertEqual(self.shop.target, 170)
        self.assertEqual(self.shop.demand_rate, 12)


class StorageInventoryEngineForecastTests(SimpleTestCase):
    def test_step_uses_horizon_forecast_for_shop_gap(self):
        engine = StorageInventoryEngine(vehicle_cap=100, horizon=5)
        engine.initialize(
            {
                "nodes": ["warehouse_a", "shop_a"],
                "routes": [
                    {"from": "warehouse_a", "to": "shop_a", "time": 1, "cost": 1.0},
                ],
                "initial_stocks": {"warehouse_a": 200, "shop_a": 50},
                "demand_rates": {"warehouse_a": 0, "shop_a": 10},
            }
        )

        result = engine.step(0, {"shop_a": 50})
        created_shipments = result["created_shipments"]

        self.assertEqual(len(created_shipments), 1)
        self.assertEqual(created_shipments[0].from_loc, "warehouse_a")
        self.assertEqual(created_shipments[0].to_loc, "shop_a")
        self.assertEqual(created_shipments[0].amount, 60)

    def test_step_splits_large_flow_into_multiple_trucks_per_tick(self):
        engine = StorageInventoryEngine(
            vehicle_cap=100,
            horizon=5,
            max_trucks_per_route_tick=4,
        )
        engine.initialize(
            {
                "nodes": ["warehouse_a", "shop_a"],
                "routes": [
                    {"from": "warehouse_a", "to": "shop_a", "time": 1, "cost": 1.0},
                ],
                "initial_stocks": {"warehouse_a": 400, "shop_a": 0},
                "demand_rates": {"warehouse_a": 0, "shop_a": 0},
            }
        )

        result = engine.step(0, {"shop_a": 250})
        created_shipments = result["created_shipments"]

        self.assertEqual(len(created_shipments), 3)
        self.assertEqual(
            [shipment.amount for shipment in created_shipments],
            [100, 100, 50],
        )
        self.assertTrue(all(shipment.from_loc == "warehouse_a" for shipment in created_shipments))
        self.assertTrue(all(shipment.to_loc == "shop_a" for shipment in created_shipments))

    def test_step_dispatches_to_multiple_shops_in_same_tick(self):
        engine = StorageInventoryEngine(
            vehicle_cap=100,
            horizon=5,
            max_trucks_per_route_tick=3,
        )
        engine.initialize(
            {
                "nodes": ["warehouse_a", "shop_a", "shop_b"],
                "routes": [
                    {"from": "warehouse_a", "to": "shop_a", "time": 1, "cost": 1.0},
                    {"from": "warehouse_a", "to": "shop_b", "time": 1, "cost": 1.0},
                ],
                "initial_stocks": {"warehouse_a": 300, "shop_a": 0, "shop_b": 0},
                "demand_rates": {"warehouse_a": 0, "shop_a": 0, "shop_b": 0},
            }
        )

        result = engine.step(0, {"shop_a": 80, "shop_b": 120})
        created_shipments = result["created_shipments"]

        shipped_totals = {}
        for shipment in created_shipments:
            key = (shipment.from_loc, shipment.to_loc)
            shipped_totals[key] = shipped_totals.get(key, 0) + shipment.amount

        self.assertEqual(shipped_totals.get(("warehouse_a", "shop_a"), 0), 80)
        self.assertEqual(shipped_totals.get(("warehouse_a", "shop_b"), 0), 120)


class SimulationRuntimeEventTests(TestCase):
    def setUp(self):
        self.network = NetworkDefinition.objects.create(
            name="Simulation Test Network",
            json_file=ContentFile(b"{}", name="simulation_test_network.json"),
            is_active=False,
        )

        self.warehouse = Warehouse.objects.create(
            name="Warehouse A",
            node_id="warehouse_a",
            network_definition=self.network,
            inventory=100,
        )

        self.shop = Shop.objects.create(
            name="Shop A",
            node_id="shop_a",
            network_definition=self.network,
            inventory=0,
            target=50,
            demand_rate=0,
        )

        self.route = Route.objects.create(
            network_definition=self.network,
            edge_id="edge-warehouse_a-shop_a-1",
            source_node_id=self.warehouse.node_id,
            target_node_id=self.shop.node_id,
            travel_time=1,
            transport_cost=1.0,
            is_active=True,
        )

    @patch("api.simulation.broadcast_node_update")
    @patch("api.simulation.broadcast_edge_update")
    @patch("api.simulation.broadcast_event_log")
    @patch("api.simulation.broadcast_tick")
    def test_tick_broadcasts_shipment_start_and_arrival(
        self,
        mock_tick,
        mock_event_log,
        mock_edge_update,
        mock_node_update,
    ):
        runtime = SimulationRuntime(vehicle_cap=100, horizon=5)

        first_tick_result = runtime.tick_once()
        self.assertTrue(first_tick_result)

        moving_payload = None
        for call in mock_edge_update.call_args_list:
            edge_id, payload = call.args
            if edge_id == self.route.edge_id and payload.get("status") == "moving":
                moving_payload = payload
                break
        self.assertIsNotNone(moving_payload)
        self.assertEqual(moving_payload["activeShipments"], 1)
        self.assertEqual(moving_payload["departureCount"], 1)
        self.assertEqual(moving_payload["arrivalCount"], 0)

        mock_node_update.assert_any_call(
            self.warehouse.node_id,
            {
                "label": self.warehouse.name,
                "type": "warehouse",
                "inventory": 50,
            },
        )

        self.assertGreaterEqual(mock_event_log.call_count, 1)
        first_event = mock_event_log.call_args_list[0].args[0]
        self.assertEqual(first_event["event"], "truck_departure")
        self.assertEqual(first_event["shipment"]["fromNodeId"], self.warehouse.node_id)
        self.assertEqual(first_event["shipment"]["toNodeId"], self.shop.node_id)

        mock_edge_update.reset_mock()
        mock_node_update.reset_mock()

        second_tick_result = runtime.tick_once()
        self.assertTrue(second_tick_result)

        self.assertEqual(mock_tick.call_count, 2)
        self.assertEqual(mock_tick.call_args_list[0].args[0], 0)
        self.assertEqual(mock_tick.call_args_list[1].args[0], 1)

        idle_payload = None
        for call in mock_edge_update.call_args_list:
            edge_id, payload = call.args
            if edge_id == self.route.edge_id and payload.get("status") == "idle":
                idle_payload = payload
                break
        self.assertIsNotNone(idle_payload)
        self.assertEqual(idle_payload["activeShipments"], 0)
        self.assertEqual(idle_payload["departureCount"], 0)
        self.assertEqual(idle_payload["arrivalCount"], 1)

        mock_node_update.assert_any_call(
            self.shop.node_id,
            {
                "label": self.shop.name,
                "type": "shop",
                "inventory": 50,
                "target": 50,
                "demandRate": 0,
            },
        )


class SnapshotPayloadFallbackTests(TestCase):
    @override_settings(SIMULATION_TICK_SECONDS=1)
    def test_snapshot_uses_definition_routes_when_route_rows_missing(self):
        network = NetworkDefinition.objects.create(
            name="Snapshot Fallback Network",
            json_file=ContentFile(b"{}", name="snapshot_network.json"),
            definition={
                "routes": [
                    {
                        "from": "warehouse_a",
                        "to": "shop_a",
                        "time": 1,
                        "distance": 2.2,
                        "cost": 3.5,
                    }
                ]
            },
            is_active=True,
        )

        Warehouse.objects.create(
            name="Warehouse A",
            node_id="warehouse_a",
            network_definition=network,
            inventory=80,
        )
        Shop.objects.create(
            name="Shop A",
            node_id="shop_a",
            network_definition=network,
            inventory=10,
            target=100,
            demand_rate=6,
        )

        payload = _snapshot_payload()

        self.assertEqual(payload["layoutName"], network.name)
        pairs = {(edge["source"], edge["target"]) for edge in payload["edges"]}
        self.assertIn(("warehouse_a", "shop_a"), pairs)
        self.assertIn(("shop_a", "warehouse_a"), pairs)

        forward_edge = next(
            edge for edge in payload["edges"]
            if edge["source"] == "warehouse_a" and edge["target"] == "shop_a"
        )
        reverse_edge = next(
            edge for edge in payload["edges"]
            if edge["source"] == "shop_a" and edge["target"] == "warehouse_a"
        )

        self.assertEqual(forward_edge["data"]["targetType"], "shop")
        self.assertEqual(reverse_edge["data"]["targetType"], "warehouse")

    @override_settings(SIMULATION_TICK_SECONDS=1)
    def test_snapshot_route_row_uses_distance_for_time_and_duration(self):
        network = NetworkDefinition.objects.create(
            name="Snapshot Distance Route Row Network",
            json_file=ContentFile(b"{}", name="snapshot_distance_network.json"),
            definition={},
            is_active=True,
        )

        Warehouse.objects.create(
            name="Warehouse A",
            node_id="warehouse_a",
            network_definition=network,
            inventory=80,
        )
        Shop.objects.create(
            name="Shop A",
            node_id="shop_a",
            network_definition=network,
            inventory=10,
            target=100,
            demand_rate=6,
        )
        Route.objects.create(
            network_definition=network,
            edge_id="edge-warehouse_a-shop_a-distance",
            source_node_id="warehouse_a",
            target_node_id="shop_a",
            travel_time=1,
            transport_cost=3.5,
            metadata={"distance": 2.2},
            is_active=True,
        )

        payload = _snapshot_payload()
        forward_edge = next(
            edge
            for edge in payload["edges"]
            if edge["source"] == "warehouse_a" and edge["target"] == "shop_a"
        )

        self.assertEqual(forward_edge["data"]["time"], 3)
        self.assertEqual(forward_edge["data"]["duration"], "3.00s")


class SimulationRuntimeDbSyncTests(TestCase):
    def setUp(self):
        self.network = NetworkDefinition.objects.create(
            name="Runtime DB Sync Network",
            json_file=ContentFile(b"{}", name="runtime_db_sync_network.json"),
            is_active=True,
        )

        self.warehouse = Warehouse.objects.create(
            name="Warehouse A",
            node_id="warehouse_a",
            network_definition=self.network,
            inventory=100,
        )

        self.shop = Shop.objects.create(
            name="Shop A",
            node_id="shop_a",
            network_definition=self.network,
            inventory=0,
            target=0,
            demand_rate=0,
        )

        Route.objects.create(
            network_definition=self.network,
            edge_id="edge-warehouse_a-shop_a-sync",
            source_node_id="warehouse_a",
            target_node_id="shop_a",
            travel_time=1,
            transport_cost=1.0,
            is_active=True,
        )

    def test_manual_warehouse_inventory_change_is_not_reverted_by_tick(self):
        runtime = SimulationRuntime(vehicle_cap=100, horizon=5)

        self.assertTrue(runtime.tick_once())
        self.assertEqual(runtime.engine.stocks[self.warehouse.node_id], 100)

        self.warehouse.inventory = 345
        self.warehouse.save(update_fields=["inventory", "updated_at"])

        self.assertTrue(runtime.tick_once())

        self.warehouse.refresh_from_db()
        self.assertEqual(self.warehouse.inventory, 345)
        self.assertEqual(runtime.engine.stocks[self.warehouse.node_id], 345)


class SimulationRuntimeBidirectionalRouteTests(TestCase):
    def setUp(self):
        self.network = NetworkDefinition.objects.create(
            name="Runtime Bidirectional Route Network",
            json_file=ContentFile(b"{}", name="runtime_bidirectional_network.json"),
            is_active=True,
        )

        self.shop_demand = Shop.objects.create(
            name="Shop Demand",
            node_id="shop_demand",
            network_definition=self.network,
            inventory=0,
            target=120,
            demand_rate=0,
        )

        self.shop_supply = Shop.objects.create(
            name="Shop Supply",
            node_id="shop_supply",
            network_definition=self.network,
            inventory=200,
            target=0,
            demand_rate=0,
        )

        # Intentionally create only demand->supply direction in DB.
        # Runtime should synthesize reverse direction and ship supply->demand.
        Route.objects.create(
            network_definition=self.network,
            edge_id="edge-demand-to-supply",
            source_node_id=self.shop_demand.node_id,
            target_node_id=self.shop_supply.node_id,
            travel_time=1,
            transport_cost=1.0,
            metadata={"distance": 2.2},
            is_active=True,
        )

    def test_tick_dispatches_over_synthetic_reverse_direction(self):
        runtime = SimulationRuntime(vehicle_cap=100, horizon=5)

        self.assertTrue(runtime.tick_once())

        in_transit_pairs = {
            (shipment.from_loc, shipment.to_loc)
            for shipment in runtime.engine.in_transit
        }
        self.assertIn((self.shop_supply.node_id, self.shop_demand.node_id), in_transit_pairs)

        supply_to_demand_shipments = [
            shipment
            for shipment in runtime.engine.in_transit
            if shipment.from_loc == self.shop_supply.node_id
            and shipment.to_loc == self.shop_demand.node_id
        ]
        self.assertTrue(supply_to_demand_shipments)
        self.assertTrue(
            all(int(shipment.arrival_t) == 3 for shipment in supply_to_demand_shipments)
        )


class StoreAccountInitializationTests(TestCase):
    def test_shops_start_with_zero_target_and_demand_rate(self):
        network = NetworkDefinition.objects.create(
            name="Account Init Network",
            json_file=ContentFile(b"{}", name="account_init_network.json"),
            is_active=False,
        )

        parsed_definition = {
            "warehouses": [
                {"id": "warehouse_a", "name": "Warehouse A", "inventory": 150}
            ],
            "shops": [
                {
                    "id": "shop_a",
                    "name": "Shop A",
                    "inventory": 40,
                    "target": 500,
                    "demand_rate": 25,
                }
            ],
            "routes": [
                {
                    "from": "warehouse_a",
                    "to": "shop_a",
                    "time": 1,
                    "distance": 2.2,
                    "cost": 2.0,
                }
            ],
        }

        StoreAccountService.create_accounts_from_json(network, parsed_definition)

        shop = Shop.objects.get(network_definition=network, node_id="shop_a")
        self.assertEqual(shop.inventory, 40)
        self.assertEqual(shop.target, 0)
        self.assertEqual(shop.demand_rate, 0)

        route = Route.objects.get(
            network_definition=network,
            source_node_id="warehouse_a",
            target_node_id="shop_a",
        )
        self.assertEqual(route.travel_time, 3)


class SimulationNodeMetricsApiTests(TestCase):
    def setUp(self):
        self.client = Client()
        self.user = User.objects.create_user(username="manager_user", password="test-pass-123")
        set_user_role(self.user.id, ROLE_MANAGER)

        self.network = NetworkDefinition.objects.create(
            name="Node Metrics API Network",
            json_file=ContentFile(b"{}", name="node_metrics_network.json"),
            is_active=True,
        )

        self.shop = Shop.objects.create(
            name="Shop A",
            node_id="shop_a",
            network_definition=self.network,
            inventory=10,
            target=0,
            demand_rate=0,
        )

        self.warehouse = Warehouse.objects.create(
            name="Warehouse A",
            node_id="warehouse_a",
            network_definition=self.network,
            inventory=120,
        )

    def test_simulation_node_metrics_updates_shop_metrics(self):
        self.client.force_login(self.user)

        response = self.client.post(
            "/api/simulation/node-metrics",
            data=json.dumps(
                {
                    "nodeId": self.shop.node_id,
                    "inventory": 55,
                    "target": 140,
                    "demandRate": 12,
                }
            ),
            content_type="application/json",
        )

        self.assertEqual(response.status_code, 200)
        self.shop.refresh_from_db()
        self.assertEqual(self.shop.inventory, 55)
        self.assertEqual(self.shop.target, 140)
        self.assertEqual(self.shop.demand_rate, 12)

    def test_simulation_node_metrics_updates_warehouse_inventory(self):
        self.client.force_login(self.user)

        response = self.client.post(
            "/api/simulation/node-metrics",
            data=json.dumps(
                {
                    "nodeId": self.warehouse.node_id,
                    "inventory": 310,
                }
            ),
            content_type="application/json",
        )

        self.assertEqual(response.status_code, 200)
        self.warehouse.refresh_from_db()
        self.assertEqual(self.warehouse.inventory, 310)
