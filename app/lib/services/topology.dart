import '../models/transit.dart';

List<Set<String>> reachableStops(
  Iterable<Json> routes,
  List<dynamic> paths,
  String destination,
  int rides,
  double maxWalk,
) {
  final incoming = <String, List<String>>{};
  for (final f in paths) {
    if (f['meters'] <= maxWalk) {
      incoming.putIfAbsent(f['to'], () => []).add(f['from']);
    }
  }
  var layer = <String>{destination, ...?incoming[destination]};
  final layers = [layer];
  for (var i = 0; i < rides; i++) {
    final boardable = {...layer};
    for (final r in routes) {
      var downstream = false;
      for (final sid in (r['stops'] as List).reversed) {
        if (downstream) boardable.add(sid);
        if (layer.contains(sid)) downstream = true;
      }
    }
    layer = {...boardable, for (final b in boardable) ...?incoming[b]};
    layers.add(layer);
  }
  return layers;
}

List<Json> paretoLabels(List<Json> states) {
  states.sort((a, b) {
    final time = (a['now'] as num).compareTo(b['now']);
    return time != 0 ? time : (a['walked'] as num).compareTo(b['walked']);
  });
  final kept = <String, List<Json>>{};
  final result = <Json>[];
  for (final state in states) {
    final group = kept.putIfAbsent(state['stop'], () => []);
    if (group.any(
      (prior) =>
          prior['now'] <= state['now'] &&
          prior['walked'] <= state['walked'] &&
          (state['used'] as Set<String>).containsAll(
            prior['used'] as Set<String>,
          ),
    )) {
      continue;
    }
    group.add(state);
    result.add(state);
  }
  return result;
}

List<Json> topologyConnections(Network network, SearchQuery q) {
  final routes = network.routes.values
      .where((r) => r['scheduleSource'] == 'catalog_topology')
      .toList();
  final walks = <String, List<Json>>{}, boards = <String, List<(Json, int)>>{};
  for (final raw in network.data['footpaths']) {
    final f = Json.from(raw);
    walks.putIfAbsent(f['from'], () => []).add(f);
  }
  for (final r in routes) {
    final ids = r['stops'] as List;
    for (var i = 0; i < ids.length - 1; i++) {
      boards.putIfAbsent(ids[i], () => []).add((r, i));
    }
  }
  final layers = reachableStops(
    routes,
    network.data['footpaths'],
    q.destination,
    q.maxTransfers + 1,
    q.maxWalk,
  );
  var frontier = <Json>[
    {
      'stop': q.origin,
      'now': 0.0,
      'legs': <Json>[],
      'used': <String>{},
      'walked': 0.0,
    },
  ];
  for (var round = 0; round <= q.maxTransfers; round++) {
    final next = <Json>[], found = <String, Json>{};
    final remaining = q.maxTransfers - round;
    for (final state in frontier) {
      final used = state['used'] as Set<String>;
      final accesses = <Json>[
        {
          'stop': state['stop'],
          'now': state['now'],
          'legs': <Json>[],
          'walked': state['walked'],
        },
      ];
      for (final f in walks[state['stop']] ?? <Json>[]) {
        if (state['walked'] + f['meters'] <= q.maxWalk) {
          accesses.add({
            'stop': f['to'],
            'now': state['now'] + f['meters'] * 2,
            'walked': state['walked'] + f['meters'],
            'legs': <Json>[
              {
                'kind': 'walk',
                'from': state['stop'],
                'to': f['to'],
                'meters': f['meters'],
              },
            ],
          });
        }
      }
      for (final access in accesses) {
        for (final (r, bi) in boards[access['stop']] ?? <(Json, int)>[]) {
          if (used.contains(r['id'])) continue;
          final ids = r['stops'] as List;
          final offsets =
              r['distanceOffsets'] as List? ??
              List.generate(ids.length, (i) => i);
          for (var ai = bi + 1; ai < ids.length; ai++) {
            final end = ids[ai] as String;
            if (!layers[remaining].contains(end)) continue;
            final cost = access['now'] + offsets[ai] - offsets[bi];
            final legs = <Json>[
              ...List<Json>.from(state['legs']),
              ...List<Json>.from(access['legs']),
              {
                'kind': 'ride',
                'routeId': r['id'],
                'from': access['stop'],
                'to': end,
                'boardIndex': bi,
                'alightIndex': ai,
              },
            ];
            final tails = <Json>[
              if (end == q.destination)
                {'legs': <Json>[], 'walked': access['walked'], 'cost': cost},
              if (end != q.destination)
                for (final f in walks[end] ?? <Json>[])
                  if (f['to'] == q.destination &&
                      access['walked'] + f['meters'] <= q.maxWalk)
                    {
                      'legs': <Json>[
                        {
                          'kind': 'walk',
                          'from': end,
                          'to': q.destination,
                          'meters': f['meters'],
                        },
                      ],
                      'walked': access['walked'] + f['meters'],
                      'cost': cost + f['meters'] * 2,
                    },
            ];
            for (final tail in tails) {
              final full = <Json>[...legs, ...List<Json>.from(tail['legs'])];
              final key = full
                  .map(
                    (l) => '${l['routeId'] ?? 'walk'}:${l['from']}:${l['to']}',
                  )
                  .join('|');
              found.putIfAbsent(
                key,
                () => {
                  'id': key,
                  'legs': full,
                  'arrival': null,
                  'walkingMeters': tail['walked'],
                  'transfers': round,
                  'tags': ['ROUTE'],
                  'source': 'catalog_topology',
                  'scheduleAvailable': false,
                  'topologyCost': tail['cost'],
                  'expectedArrival': null,
                  'p90Arrival': null,
                  'successProbability': null,
                  'noServiceProbability': null,
                  'sampleCount': 0,
                  'delaySource': 'unavailable',
                },
              );
            }
            if (remaining > 0) {
              next.add({
                'stop': end,
                'now': cost,
                'legs': legs,
                'used': <String>{...used, r['id']},
                'walked': access['walked'],
              });
            }
          }
        }
      }
    }
    if (found.isNotEmpty) {
      final result = found.values.toList()
        ..sort((a, b) {
          final cost = (a['topologyCost'] as num).compareTo(b['topologyCost']);
          return cost != 0
              ? cost
              : (a['walkingMeters'] as num).compareTo(b['walkingMeters']);
        });
      return result.take(5).toList();
    }
    frontier = paretoLabels(next);
  }
  return [];
}
