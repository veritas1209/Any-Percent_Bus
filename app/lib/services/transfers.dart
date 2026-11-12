import 'dart:convert';
import 'dart:typed_data';
import '../models/transit.dart';
import 'walking_graph.dart';
import 'topology.dart';

class TransferGraph {
  late final Uint32List offsets, neighbors;
  late final Float64List weights;
  final stops = <String, (int, double)>{};
  final aliases = <String, List<String>>{};
  TransferGraph(Uint8List input) {
    final bytes = input.offsetInBytes % 8 == 0
        ? input
        : Uint8List.fromList(input);
    final h = ByteData.sublistView(bytes);
    if (ascii.decode(bytes.sublist(0, 4)) != 'APX1') {
      throw const FormatException('Invalid transfer graph');
    }
    final n = h.getUint32(4, Endian.little),
        m = h.getUint32(8, Endian.little),
        s = h.getUint32(12, Endian.little),
        size = h.getUint32(16, Endian.little);
    final meta = jsonDecode(utf8.decode(bytes.sublist(24, 24 + size))) as Map;
    for (final entry in ((meta['coincidentStops'] as Map?) ?? {}).entries) {
      aliases[entry.key as String] = List<String>.from(entry.value);
    }
    var offset = 24 + size;
    Uint32List unsigned(int count) {
      final result = Uint32List.view(
        bytes.buffer,
        bytes.offsetInBytes + offset,
        count,
      );
      offset += count * 4;
      return result;
    }

    offsets = unsigned(n + 1);
    neighbors = unsigned(m);
    final nodes = Int32List.view(bytes.buffer, bytes.offsetInBytes + offset, s);
    offset += s * 4;
    offset += (-offset) % 8;
    weights = Float64List.view(bytes.buffer, bytes.offsetInBytes + offset, m);
    offset += m * 8;
    final errors = Float64List.view(
      bytes.buffer,
      bytes.offsetInBytes + offset,
      s,
    );
    offset += s * 8;
    if (offset != bytes.length) {
      throw const FormatException('Unexpected transfer graph length');
    }
    for (var i = 0; i < s; i++) {
      if (nodes[i] >= 0) stops[meta['stopIds'][i]] = (nodes[i], errors[i]);
    }
  }

  Map<String, double> latest(
    Map<String, double> values,
    double walkingSpeed,
    double earliest,
  ) {
    final scale = walkingSpeed * 60,
        costs = <int, double>{},
        queue = DistanceHeap();
    final seeds = Map<String, double>.from(values);
    for (final entry in aliases.entries) {
      for (final other in entry.value) {
        final value = values[other] ?? double.negativeInfinity;
        if (value > (seeds[entry.key] ?? double.negativeInfinity)) {
          seeds[entry.key] = value;
        }
      }
    }
    for (final entry in seeds.entries) {
      final snap = stops[entry.key];
      if (snap == null) continue;
      final value = entry.value - snap.$2 / scale;
      if (value < earliest - 1e-6) continue;
      if (value > (costs[snap.$1] ?? double.negativeInfinity)) {
        costs[snap.$1] = value;
        queue.add(-value, snap.$1);
      }
    }
    while (queue.isNotEmpty) {
      final (negative, node) = queue.pop();
      final value = -negative;
      if (value != costs[node]) continue;
      for (var i = offsets[node]; i < offsets[node + 1]; i++) {
        final other = neighbors[i], candidate = value - weights[i] / scale;
        if (candidate >= earliest - 1e-6 &&
            candidate > (costs[other] ?? double.negativeInfinity)) {
          costs[other] = candidate;
          queue.add(-candidate, other);
        }
      }
    }
    final result = Map<String, double>.from(seeds);
    for (final entry in stops.entries) {
      final value =
          (costs[entry.value.$1] ?? double.negativeInfinity) -
          entry.value.$2 / scale;
      if (value > (result[entry.key] ?? double.negativeInfinity)) {
        result[entry.key] = value;
      }
    }
    result.removeWhere((_, value) => value < earliest - 1e-6);
    return result;
  }

  List<Json> spread(
    List<Json> roots,
    double speed,
    double budget,
    double deadline, {
    bool respectUsed = false,
    Set<String>? boardable,
  }) {
    final kept = <int, List<int>>{}, queue = DistanceHeap();
    final values = <(int, double, double, int)>[];
    final scale = speed * 60;
    bool subset(int a, int b) =>
        !respectUsed ||
        (roots[b]['used'] as Set<String>).containsAll(
          roots[a]['used'] as Set<String>,
        );
    void put(int node, double now, double walked, int root) {
      if (walked > budget + .001 || now > deadline + 1e-6) return;
      final labels = kept.putIfAbsent(node, () => []);
      if (labels.any(
        (i) =>
            values[i].$2 <= now + 1e-9 &&
            values[i].$3 <= walked + 1e-7 &&
            subset(values[i].$4, root),
      )) {
        return;
      }
      labels.removeWhere(
        (i) =>
            now <= values[i].$2 + 1e-9 &&
            walked <= values[i].$3 + 1e-7 &&
            subset(root, values[i].$4),
      );
      final id = values.length;
      values.add((node, now, walked, root));
      labels.add(id);
      queue.add(now, id);
    }

    for (var root = 0; root < roots.length; root++) {
      final snap = stops[roots[root]['stop']];
      if (snap == null) continue;
      put(
        snap.$1,
        numValue(roots[root]['now']) + snap.$2 / scale,
        numValue(roots[root]['walked']) + snap.$2,
        root,
      );
    }
    while (queue.isNotEmpty) {
      final (_, id) = queue.pop();
      final (node, now, walked, root) = values[id];
      if (!kept[node]!.contains(id)) continue;
      for (var i = offsets[node]; i < offsets[node + 1]; i++) {
        put(neighbors[i], now + weights[i] / scale, walked + weights[i], root);
      }
    }
    final result = List<Json>.from(roots);
    for (final source in roots) {
      for (final sid in aliases[source['stop']] ?? <String>[]) {
        if (boardable != null && !boardable.contains(sid)) continue;
        result.add({
          'stop': sid,
          'now': source['now'],
          'walked': source['walked'],
          'used': source['used'],
          'legs': <Json>[
            ...List<Json>.from(source['legs']),
            {
              'kind': 'walk',
              'from': source['stop'],
              'to': sid,
              'depart': source['now'],
              'arrive': source['now'],
              'meters': 0.0,
              '_transferWalk': true,
            },
          ],
        });
      }
    }
    for (final entry in stops.entries) {
      final sid = entry.key;
      final (node, error) = entry.value;
      if (boardable != null && !boardable.contains(sid)) continue;
      for (final id in kept[node] ?? <int>[]) {
        final (_, _, walked, root) = values[id];
        final source = roots[root];
        if (sid == source['stop']) continue;
        final meters =
            ((walked - numValue(source['walked']) + error) * 10).round() / 10;
        final total = numValue(source['walked']) + meters,
            end = numValue(source['now']) + meters / scale;
        if (total > budget + .001 || end > deadline + 1e-6) continue;
        result.add({
          'stop': sid,
          'now': end,
          'walked': total,
          'used': source['used'],
          'legs': <Json>[
            ...List<Json>.from(source['legs']),
            {
              'kind': 'walk',
              'from': source['stop'],
              'to': sid,
              'depart': source['now'],
              'arrive': end,
              'meters': meters,
              '_transferWalk': true,
            },
          ],
        });
      }
    }
    return paretoLabels(result, respectUsed: respectUsed);
  }
}
