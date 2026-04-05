import json
import tempfile
from types import SimpleNamespace

from django.test import SimpleTestCase

from .json_parser import parse_network_json
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
