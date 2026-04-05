from pathlib import Path
import math

import networkx as nx


def _clean(value):
    if not isinstance(value, str):
        return value

    cleaned = value.strip()
    if len(cleaned) >= 2 and (
        (cleaned[0] == '"' and cleaned[-1] == '"')
        or (cleaned[0] == "'" and cleaned[-1] == "'")
    ):
        cleaned = cleaned[1:-1]

    return cleaned


def _is_valid_node_id(node_id):
    value = str(node_id).strip()
    return value not in {"", "\\n"}


def _node_data(node_id, attrs):
    label = _clean(attrs.get("label")) if attrs.get("label") else str(node_id)
    data = {"label": label}

    for key, value in attrs.items():
        if key in {"label", "pos"}:
            continue
        data[key] = _clean(value)

    return data


def _edge_data(attrs):
    data = {}
    for key, value in attrs.items():
        if key == "id":
            continue
        data[key] = _clean(value)

    if "status" not in data:
        data["status"] = "idle"

    return data


def _layout_graph(graph, node_id_set):
    layout_graph = nx.Graph()
    layout_graph.add_nodes_from(node_id_set)

    if graph.is_multigraph():
        edge_rows = graph.edges(keys=True)
        for source, target, _key in edge_rows:
            source_id = str(source)
            target_id = str(target)
            if source_id not in node_id_set or target_id not in node_id_set:
                continue
            if source_id == target_id:
                continue
            layout_graph.add_edge(source_id, target_id)
    else:
        edge_rows = graph.edges()
        for source, target in edge_rows:
            source_id = str(source)
            target_id = str(target)
            if source_id not in node_id_set or target_id not in node_id_set:
                continue
            if source_id == target_id:
                continue
            layout_graph.add_edge(source_id, target_id)

    return layout_graph


def _normalize_layout_positions(raw_positions, node_ids):
    if not node_ids:
        return {}

    if not raw_positions:
        return {node_id: {"x": 0.0, "y": 0.0} for node_id in node_ids}

    points = {}
    for node_id in node_ids:
        point = raw_positions.get(node_id)
        if point is None:
            continue
        points[node_id] = (float(point[0]), float(point[1]))

    if not points:
        return {node_id: {"x": 0.0, "y": 0.0} for node_id in node_ids}

    xs = [value[0] for value in points.values()]
    ys = [value[1] for value in points.values()]

    min_x = min(xs)
    max_x = max(xs)
    min_y = min(ys)
    max_y = max(ys)

    span_x = max(max_x - min_x, 1e-9)
    span_y = max(max_y - min_y, 1e-9)

    total_nodes = len(node_ids)
    columns = max(1, int(math.ceil(total_nodes ** 0.5)))
    rows = max(1, int(math.ceil(total_nodes / columns)))
    width = max(220.0, float((columns - 1) * 220))
    height = max(160.0, float((rows - 1) * 160))

    fallback_index = 0
    positions = {}
    for node_id in node_ids:
        if node_id in points:
            x, y = points[node_id]
            normalized_x = ((x - min_x) / span_x) * width
            normalized_y = ((y - min_y) / span_y) * height
            positions[node_id] = {"x": normalized_x, "y": normalized_y}
            continue

        row = fallback_index // columns
        col = fallback_index % columns
        positions[node_id] = {"x": float(col * 220), "y": float(row * 160)}
        fallback_index += 1

    return positions


def _generate_layout_positions(graph, node_ids):
    if not node_ids:
        return {}

    if len(node_ids) == 1:
        return {node_ids[0]: {"x": 0.0, "y": 0.0}}

    node_id_set = set(node_ids)
    layout_graph = _layout_graph(graph, node_id_set)

    use_planar = True
    try:
        is_planar, _ = nx.check_planarity(layout_graph)
        use_planar = is_planar and layout_graph.number_of_edges() > 0
    except Exception:
        use_planar = False

    if use_planar:
        raw_positions = nx.planar_layout(layout_graph, scale=1.0)
    else:
        raw_positions = nx.spring_layout(layout_graph, seed=42)

    return _normalize_layout_positions(raw_positions, node_ids)


def parse_dot_to_react_flow(dot_file_path):
    path = Path(dot_file_path)
    if not path.exists():
        raise ValueError("DOT file does not exist")

    graph = nx.nx_pydot.read_dot(path)

    nodes = []
    node_ids = []
    for node_id, attrs in graph.nodes(data=True):
        if not _is_valid_node_id(node_id):
            continue
        node_ids.append(str(node_id))
        nodes.append((str(node_id), attrs))

    node_id_set = set(node_ids)
    layout_positions = _generate_layout_positions(graph, node_ids)
    react_flow_nodes = []
    for node_id, attrs in nodes:
        parsed_position = layout_positions.get(node_id)
        if not parsed_position:
            parsed_position = {"x": 0.0, "y": 0.0}

        react_flow_nodes.append(
            {
                "id": node_id,
                "position": parsed_position,
                "data": _node_data(node_id, attrs),
            }
        )

    react_flow_edges = []
    if graph.is_multigraph():
        edge_rows = list(graph.edges(keys=True, data=True))
        for index, (source, target, _key, attrs) in enumerate(edge_rows):
            source_id = str(source)
            target_id = str(target)
            if source_id not in node_id_set or target_id not in node_id_set:
                continue

            edge_id = _clean(attrs.get("id")) or f"e-{source_id}-{target_id}-{index}"
            react_flow_edges.append(
                {
                    "id": str(edge_id),
                    "source": source_id,
                    "target": target_id,
                    "type": "moving",
                    "data": _edge_data(attrs),
                }
            )
    else:
        edge_rows = list(graph.edges(data=True))
        for index, (source, target, attrs) in enumerate(edge_rows):
            source_id = str(source)
            target_id = str(target)
            if source_id not in node_id_set or target_id not in node_id_set:
                continue

            edge_id = _clean(attrs.get("id")) or f"e-{source_id}-{target_id}-{index}"
            react_flow_edges.append(
                {
                    "id": str(edge_id),
                    "source": source_id,
                    "target": target_id,
                    "type": "moving",
                    "data": _edge_data(attrs),
                }
            )

    return {
        "nodes": react_flow_nodes,
        "edges": react_flow_edges,
    }
