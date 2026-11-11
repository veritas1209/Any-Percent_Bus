import 'dart:math';
import 'dart:typed_data';
import '../models/transit.dart';

class _Snap {
  final int a, b, edge;
  final double fraction, lat, lon, error, length;
  _Snap(
    this.a,
    this.b,
    this.edge,
    this.fraction,
    this.lat,
    this.lon,
    this.error,
    this.length,
  );
}

class _Heap {
  final values = <(double, int)>[];
  bool get isNotEmpty => values.isNotEmpty;
  void add(double cost, int node) {
    var i = values.length;
    values.add((cost, node));
    while (i > 0) {
      final p = (i - 1) ~/ 2;
      if (_compare(values[p], values[i]) <= 0) break;
      final t = values[p];
      values[p] = values[i];
      values[i] = t;
      i = p;
    }
  }

  int _compare((double, int) a, (double, int) b) {
    final c = a.$1.compareTo(b.$1);
    return c != 0 ? c : a.$2.compareTo(b.$2);
  }

  (double, int) pop() {
    final first = values.first, last = values.removeLast();
    if (values.isEmpty) return first;
    values[0] = last;
    var i = 0;
    while (true) {
      var c = i * 2 + 1;
      if (c >= values.length) break;
      if (c + 1 < values.length && _compare(values[c + 1], values[c]) < 0) c++;
      if (_compare(values[i], values[c]) <= 0) break;
      final t = values[i];
      values[i] = values[c];
      values[c] = t;
      i = c;
    }
    return first;
  }
}

class WalkingGraph {
  late final Int32List coords, cells;
  late final Uint32List offsets, neighbors, edges, entries;
  final grid = <int, int>{};
  WalkingGraph(Uint8List input) {
    final bytes = input.offsetInBytes % 4 == 0
        ? input
        : Uint8List.fromList(input);
    final h = ByteData.sublistView(bytes);
    if (String.fromCharCodes(bytes.take(4)) != 'APW1') {
      throw const FormatException('Invalid pedestrian graph');
    }
    final n = h.getUint32(4, Endian.little),
        m = h.getUint32(8, Endian.little),
        e = h.getUint32(12, Endian.little),
        c = h.getUint32(16, Endian.little),
        g = h.getUint32(20, Endian.little);
    var offset = 24;
    Int32List signed(int count) {
      final result = Int32List.view(
        bytes.buffer,
        bytes.offsetInBytes + offset,
        count,
      );
      offset += count * 4;
      return result;
    }

    Uint32List unsigned(int count) {
      final result = Uint32List.view(
        bytes.buffer,
        bytes.offsetInBytes + offset,
        count,
      );
      offset += count * 4;
      return result;
    }

    coords = signed(n * 2);
    offsets = unsigned(n + 1);
    neighbors = unsigned(m);
    edges = unsigned(e * 2);
    cells = signed(c * 4);
    entries = unsigned(g);
    if (offset != bytes.length) {
      throw const FormatException('Unexpected pedestrian graph length');
    }
    for (var i = 0; i < cells.length; i += 4) {
      grid[cells[i] * 1000000 + cells[i + 1]] = i;
    }
  }
  double _weight(int a, int b) {
    final y = (coords[a * 2] - coords[b * 2]) * .111,
        x = (coords[a * 2 + 1] - coords[b * 2 + 1]) * .091;
    return sqrt(x * x + y * y);
  }

  List<double> _point(int node) => [
    coords[node * 2] / 1e6,
    coords[node * 2 + 1] / 1e6,
  ];
  static double distance(double lat, double lon, double lat2, double lon2) {
    final y = (lat - lat2) * 111000, x = (lon - lon2) * 91000;
    return sqrt(x * x + y * y);
  }

  _Snap? _snap(double lat, double lon) {
    final x = (lon * 910).floor(),
        y = (lat * 1110).floor(),
        candidates = <int>{};
    for (var dx = -1; dx <= 1; dx++) {
      for (var dy = -1; dy <= 1; dy++) {
        final i = grid[(x + dx) * 1000000 + y + dy];
        if (i != null) {
          for (var j = cells[i + 2]; j < cells[i + 2] + cells[i + 3]; j++) {
            candidates.add(entries[j]);
          }
        }
      }
    }
    _Snap? best;
    for (final edge in candidates) {
      final a = edges[edge * 2],
          b = edges[edge * 2 + 1],
          pa = _point(a),
          pb = _point(b);
      final dx = (pb[1] - pa[1]) * 91000,
          dy = (pb[0] - pa[0]) * 111000,
          den = dx * dx + dy * dy;
      if (den == 0) continue;
      final f =
          (((lon - pa[1]) * 91000 * dx + (lat - pa[0]) * 111000 * dy) / den)
              .clamp(0.0, 1.0);
      final py = pa[0] + f * (pb[0] - pa[0]),
          px = pa[1] + f * (pb[1] - pa[1]),
          error = distance(lat, lon, py, px);
      if (best == null ||
          error < best.error ||
          error == best.error && edge < best.edge) {
        best = _Snap(a, b, edge, f, py, px, error, sqrt(den));
      }
    }
    return best != null && best.error <= 80 ? best : null;
  }

  List<Json> connections(
    Json point,
    Iterable<Json> stops,
    double budget, {
    bool reverse = false,
    Json? stats,
  }) {
    final lat = numValue(point['lat']), lon = numValue(point['lon']);
    final candidates = stops
        .where(
          (s) =>
              distance(lat, lon, numValue(s['lat']), numValue(s['lon'])) <=
              budget + .01,
        )
        .toList();
    final snap = _snap(lat, lon),
        costs = <int, double>{},
        parent = <int, int>{},
        queue = _Heap();
    final boundary = <int>{};
    if (snap != null) {
      for (final (node, cost) in [
        (snap.a, snap.error + snap.length * snap.fraction),
        (snap.b, snap.error + snap.length * (1 - snap.fraction)),
      ]) {
        if (cost <= budget && cost < (costs[node] ?? double.infinity)) {
          costs[node] = cost;
          parent[node] = -1;
          queue.add(cost, node);
        }
      }
    }
    while (queue.isNotEmpty) {
      final (cost, node) = queue.pop();
      if (cost != costs[node]) continue;
      for (var i = offsets[node]; i < offsets[node + 1]; i++) {
        final other = neighbors[i], next = cost + _weight(node, other);
        if (next <= budget && next < (costs[other] ?? double.infinity)) {
          costs[other] = next;
          parent[other] = node;
          queue.add(next, other);
        } else if (stats != null && next > budget) {
          boundary.add(other);
        }
      }
    }
    if (stats != null) {
      stats['exhausted'] =
          boundary.every(costs.containsKey) &&
          (costs.isEmpty || budget >= costs.values.reduce(max) + 80);
    }
    final results = <Json>[];
    for (final stop in candidates) {
      final endLat = numValue(stop['lat']), endLon = numValue(stop['lon']);
      if (distance(lat, lon, endLat, endLon) < .1) {
        results.add({
          'stop': stop['id'],
          'meters': 0.0,
          'points': [
            [lat, lon],
            [endLat, endLon],
          ],
        });
        continue;
      }
      final target = _snap(endLat, endLon);
      if (snap == null || target == null) continue;
      final options = <(double, int)>[];
      if (snap.edge == target.edge) {
        options.add((
          snap.error +
              (snap.fraction - target.fraction).abs() * snap.length +
              target.error,
          -1,
        ));
      }
      for (final (node, extra) in [
        (target.a, target.length * target.fraction),
        (target.b, target.length * (1 - target.fraction)),
      ]) {
        if (costs.containsKey(node)) {
          options.add((costs[node]! + extra + target.error, node));
        }
      }
      if (options.isEmpty) continue;
      options.sort((a, b) => a.$1.compareTo(b.$1));
      final (cost, last) = options.first;
      if (cost > budget + .01) continue;
      final middle = <List<double>>[];
      var node = last;
      while (node != -1) {
        middle.add(_point(node));
        node = parent[node]!;
      }
      final raw = <List<double>>[
        [lat, lon],
        [snap.lat, snap.lon],
        ...middle.reversed,
        [target.lat, target.lon],
        [endLat, endLon],
      ];
      final points = <List<double>>[];
      for (final p in raw) {
        final rounded = [
          (p[0] * 1e6).round() / 1e6,
          (p[1] * 1e6).round() / 1e6,
        ];
        if (points.isEmpty ||
            points.last[0] != rounded[0] ||
            points.last[1] != rounded[1]) {
          points.add(rounded);
        }
      }
      results.add({
        'stop': stop['id'],
        'meters': (cost * 10).round() / 10,
        'points': reverse ? points.reversed.toList() : points,
      });
    }
    return results;
  }
}

(Network, List<Json>) prepareLocations(
  Network network,
  SearchQuery q,
  WalkingGraph graph, {
  Json? stats,
}) {
  final points = <Json>[], links = <Json>[];
  final progress = <bool>[];
  final stops = network.stops.values
      .where((s) => !(s['id'] as String).startsWith('@'))
      .toList();
  for (final (kind, value) in [
    ('origin', q.originPoint),
    ('destination', q.destinationPoint),
  ]) {
    if (value == null) continue;
    final id = '@$kind';
    points.add({...value, 'id': id, 'direction': '선택한 지점', 'isLocation': true});
    final targets = <Json>[
      ...stops,
      if (kind == 'origin' && q.destinationPoint != null)
        {...q.destinationPoint!, 'id': '@destination'},
    ];
    final part = stats == null ? null : <String, dynamic>{};
    for (final link in graph.connections(
      value,
      targets,
      q.maxWalk ?? double.infinity,
      reverse: kind == 'destination',
      stats: part,
    )) {
      links.add({
        'from': kind == 'origin' ? id : link['stop'],
        'to': kind == 'origin' ? link['stop'] : id,
        'meters': link['meters'],
        'shape': {
          'points': link['points'],
          'meters': link['meters'],
          'source': 'osm_pedestrian_access',
        },
        'access': true,
      });
    }
    if (part != null) progress.add(part['exhausted'] as bool);
  }
  if (stats != null) stats['exhausted'] = progress.every((value) => value);
  return (
    Network({
      ...network.data,
      'stops': [...stops, ...points],
      'footpaths': [...network.data['footpaths'], ...links],
    }),
    points,
  );
}
