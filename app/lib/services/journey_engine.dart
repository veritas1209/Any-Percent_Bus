import 'dart:math';
import '../models/transit.dart';
import 'topology.dart';

int firstDeparture(List<num> departures, double minimum) {
  var low = 0, high = departures.length;
  while (low < high) {
    final middle = (low + high) ~/ 2;
    if (departures[middle] < minimum - 1e-9) {
      low = middle + 1;
    } else {
      high = middle;
    }
  }
  return low;
}

class JourneyEngine {
  final Network network;
  JourneyEngine(this.network);
  late final timedRoutes = network.routes.values
      .where((r) => (r['departures'] as List).isNotEmpty)
      .toList();
  late final boards = <String, List<(Json, int)>>{}
    ..addEntries(_boardEntries());
  Iterable<MapEntry<String, List<(Json, int)>>> _boardEntries() {
    final index = <String, List<(Json, int)>>{};
    for (final r in timedRoutes) {
      for (var i = 0; i < (r['stops'] as List).length - 1; i++) {
        index.putIfAbsent(r['stops'][i], () => []).add((r, i));
      }
    }
    return index.entries;
  }

  late final walks = <String, List<Json>>{}..addEntries(_walkEntries());
  Iterable<MapEntry<String, List<Json>>> _walkEntries() {
    final index = <String, List<Json>>{};
    for (final raw in network.data['footpaths']) {
      final f = Json.from(raw);
      index.putIfAbsent(f['from'], () => []).add(f);
    }
    return index.entries;
  }

  List<Json> search(SearchQuery q) {
    final selected = network.forServiceDay(q.serviceDay);
    if (!identical(selected, network)) return JourneyEngine(selected).search(q);
    if (q.origin == q.destination) return [];
    final layers = reachableStops(
      timedRoutes,
      network.data['footpaths'],
      q.destination,
      q.maxTransfers + 1,
      q.maxWalk,
    );
    final bounds = walkingBounds(
      timedRoutes,
      network.data['footpaths'],
      q.destination,
      q.maxTransfers + 1,
    );
    List<Json> frontier = [
      {
        'stop': q.origin,
        'now': q.departure,
        'legs': <Json>[],
        'used': <String>{},
        'walked': 0.0,
      },
    ];
    final found = <String, Json>{};
    var cutoff = double.infinity;
    void add(List<Json> legs, double walked) {
      final key = legs
          .map((l) => '${l['routeId'] ?? 'walk'}:${l['from']}:${l['to']}')
          .join('|');
      found.putIfAbsent(
        key,
        () => {
          'id': key,
          'legs': legs,
          'arrival': legs.last['arrive'],
          'walkingMeters': walked,
        },
      );
      if (found.length > 20) {
        final keys = found.keys.toList()
          ..sort(
            (a, b) => numValue(
              found[a]!['arrival'],
            ).compareTo(numValue(found[b]!['arrival'])),
          );
        for (final key in keys.skip(20)) {
          found.remove(key);
        }
      }
      if (found.length == 20) {
        cutoff = found.values.map((j) => numValue(j['arrival'])).reduce(max);
      }
    }

    for (final f in walks[q.origin] ?? <Json>[]) {
      if (f['from'] == q.origin &&
          f['to'] == q.destination &&
          f['meters'] <= q.maxWalk) {
        add([
          {
            'kind': 'walk',
            'from': q.origin,
            'to': q.destination,
            'depart': q.departure,
            'arrive': q.departure + f['meters'] / q.walkingSpeed / 60,
            'meters': f['meters'],
            'shape': f['shape'],
          },
        ], numValue(f['meters']));
      }
    }
    for (var round = 0; round <= q.maxTransfers; round++) {
      final next = <Json>[];
      for (final state in frontier) {
        if (numValue(state['now']) > cutoff) continue;
        if (numValue(state['walked']) +
                (bounds[q.maxTransfers - round + 1][state['stop']] ??
                    double.infinity) >
            q.maxWalk + .001) {
          continue;
        }
        final accesses = <Json>[
          {
            'stop': state['stop'],
            'now': state['now'],
            'legs': <Json>[],
            'walked': state['walked'],
          },
        ];
        for (final f in walks[state['stop']] ?? <Json>[]) {
          if (f['from'] == state['stop'] &&
              state['walked'] + f['meters'] <= q.maxWalk) {
            final end =
                numValue(state['now']) + f['meters'] / q.walkingSpeed / 60;
            accesses.add({
              'stop': f['to'],
              'now': end,
              'walked': state['walked'] + f['meters'],
              'legs': <Json>[
                {
                  'kind': 'walk',
                  'from': f['from'],
                  'to': f['to'],
                  'depart': state['now'],
                  'arrive': end,
                  'meters': f['meters'],
                  'shape': f['shape'],
                },
              ],
            });
          }
        }
        for (final access in accesses) {
          for (final (route, bi) in boards[access['stop']] ?? <(Json, int)>[]) {
            final used = state['used'] as Set<String>;
            final stops = (route['stops'] as List).cast<String>();
            if (used.contains(route['id']) || !stops.contains(access['stop'])) {
              continue;
            }
            final departures = (route['departures'] as List).cast<num>();
            final offsets = (route['offsets'] as List).cast<num>();
            final buffer = used.isEmpty ? 0.0 : 0.5;
            final index = firstDeparture(
              departures,
              numValue(access['now']) + buffer - offsets[bi],
            );
            if (index == departures.length) continue;
            final trip = departures[index];
            for (var ai = bi + 1; ai < stops.length; ai++) {
              if (trip + offsets[ai] > cutoff) continue;
              if (!layers[q.maxTransfers - round].contains(stops[ai])) continue;
              if (numValue(access['walked']) +
                      (bounds[q.maxTransfers - round][stops[ai]] ??
                          double.infinity) >
                  q.maxWalk + .001) {
                continue;
              }
              final leg = <String, dynamic>{
                'kind': 'ride',
                'routeId': route['id'],
                'from': stops[bi],
                'to': stops[ai],
                'boardIndex': bi,
                'alightIndex': ai,
                'trip': trip,
                'depart': trip + offsets[bi],
                'arrive': trip + offsets[ai],
              };
              final legs = <Json>[
                ...List<Json>.from(state['legs']),
                ...List<Json>.from(access['legs']),
                leg,
              ];
              if (stops[ai] == q.destination) {
                add(legs, numValue(access['walked']));
              } else {
                for (final f in walks[stops[ai]] ?? <Json>[]) {
                  if (f['from'] == stops[ai] &&
                      f['to'] == q.destination &&
                      numValue(access['walked']) + f['meters'] <= q.maxWalk) {
                    final last = <String, dynamic>{
                      'kind': 'walk',
                      'from': stops[ai],
                      'to': q.destination,
                      'depart': leg['arrive'],
                      'arrive':
                          numValue(leg['arrive']) +
                          f['meters'] / q.walkingSpeed / 60,
                      'meters': f['meters'],
                      'shape': f['shape'],
                    };
                    add([
                      ...legs,
                      last,
                    ], numValue(access['walked']) + numValue(f['meters']));
                  }
                }
                if (round < q.maxTransfers) {
                  next.add({
                    'stop': stops[ai],
                    'now': leg['arrive'],
                    'legs': legs,
                    'used': <String>{...used, route['id']},
                    'walked': access['walked'],
                  });
                }
              }
            }
          }
        }
      }
      frontier = round < q.maxTransfers
          ? paretoLabels(
              next.where((s) => numValue(s['now']) <= cutoff).toList(),
            )
          : [];
    }
    final candidates = found.values.toList()
      ..sort((a, b) => (a['arrival'] as num).compareTo(b['arrival']));
    final evaluated = candidates.take(20).map((j) => evaluate(j, q)).toList();
    if (evaluated.isEmpty) {
      return network.data['catalogFallback'] == true
          ? topologyConnections(network, q)
          : [];
    }
    final earliest = evaluated.reduce(
      (a, b) => a['arrival'] <= b['arrival'] ? a : b,
    );
    final safest = evaluated.reduce(
      (a, b) =>
          a['p90Arrival'] < b['p90Arrival'] ||
              a['p90Arrival'] == b['p90Arrival'] &&
                  a['expectedArrival'] < b['expectedArrival']
          ? a
          : b,
    );
    for (final j in evaluated) {
      j['tags'] = <String>[
        if (j['id'] == earliest['id']) 'ANY%',
        if (j['id'] == safest['id']) 'SAFE',
      ];
    }
    evaluated.sort((a, b) {
      final priority = (a['tags'] as List).isEmpty ? 1 : 0;
      final other = (b['tags'] as List).isEmpty ? 1 : 0;
      return priority == other
          ? (a['arrival'] as num).compareTo(b['arrival'])
          : priority.compareTo(other);
    });
    return evaluated;
  }

  Json replay(
    Json journey,
    SearchQuery q, [
    Map<String, double>? draws,
    double Function(Json, num)? sampleDelay,
  ]) {
    final selected = network.forServiceDay(q.serviceDay);
    if (!identical(selected, network)) {
      return JourneyEngine(selected).replay(journey, q, draws, sampleDelay);
    }
    double now = q.departure;
    var first = true;
    double? margin;
    final missed = <String>[], result = <Json>[];
    for (final source in journey['legs']) {
      final leg = Json.from(source);
      leg['depart'] = now;
      if (leg['kind'] == 'walk') {
        now += leg['meters'] / q.walkingSpeed / 60;
      } else {
        final r = network.routes[leg['routeId']]!;
        final bi = leg['boardIndex'] as int, ai = leg['alightIndex'] as int;
        num? chosen;
        double depart = 0, arrive = 0;
        final departures = (r['departures'] as List).cast<num>();
        final maximumDelay = draws != null || sampleDelay != null
            ? (r['delaySamples'] as List).cast<num>().reduce(max).toDouble()
            : 0.0;
        final start = firstDeparture(
          departures,
          now +
              (first ? 0 : .5) -
              numValue(r['offsets'][bi]) -
              maximumDelay -
              (first ? q.delay : 0),
        );
        for (var index = start; index < departures.length; index++) {
          final trip = departures[index];
          if (first && trip < (leg['trip'] as num)) continue;
          final d =
              sampleDelay?.call(r, trip) ?? draws?['${r['id']}:$trip'] ?? 0;
          final extra = first && trip == leg['trip'] ? q.delay : 0.0;
          final test = trip + numValue(r['offsets'][bi]) + d + extra;
          if (test >= now + (first ? 0 : 0.5)) {
            chosen = trip;
            depart = test;
            arrive = trip + numValue(r['offsets'][ai]) + d + extra;
            break;
          }
        }
        if (chosen == null) {
          return {
            'arrival': null,
            'missed': [...missed, leg['routeId']],
            'legs': result,
            'margin': margin,
          };
        }
        if (!first) {
          final slack = depart - now - 0.5;
          margin = margin == null ? slack : min(margin, slack);
          if (chosen > (leg['trip'] as num)) missed.add(leg['routeId']);
        }
        leg['trip'] = chosen;
        leg['depart'] = depart;
        now = arrive;
        first = false;
      }
      leg['arrive'] = now;
      result.add(leg);
    }
    return {'arrival': now, 'missed': missed, 'legs': result, 'margin': margin};
  }

  Json evaluate(Json journey, SearchQuery q) {
    final j = Json.from(journey), rng = Random(q.seed);
    final times = <double>[];
    var success = 0, noService = 0;
    final relevant = <String>{
      for (final l in j['legs'])
        if (l['kind'] == 'ride') l['routeId'] as String,
    }.toList()..sort();
    for (var i = 0; i < q.samples; i++) {
      final draws = <String, double>{};
      for (final id in network.official ? <String>[] : relevant) {
        final r = network.routes[id]!;
        final ds = List<num>.from(r['delaySamples']);
        for (final trip in r['departures']) {
          draws['${r['id']}:$trip'] = ds[rng.nextInt(ds.length)].toDouble();
        }
      }
      final sample = network.official
          ? replay(
              j,
              q,
              null,
              (route, trip) => draws.putIfAbsent('${route['id']}:$trip', () {
                final delays = route['delaySamples'] as List;
                return numValue(delays[rng.nextInt(delays.length)]);
              }),
            )
          : replay(j, q, draws);
      if (sample['arrival'] == null) {
        noService++;
        times.add(max(q.departure + 240, 1440));
      } else {
        times.add(numValue(sample['arrival']));
        if ((sample['missed'] as List).isEmpty) success++;
      }
    }
    times.sort();
    final scenario = replay(j, q);
    j.addAll({
      'expectedArrival': times.reduce((a, b) => a + b) / times.length,
      'p90Arrival': times[(times.length * .9).ceil() - 1],
      'successProbability': success / q.samples,
      'sampleCount': q.samples,
      'noServiceProbability': noService / q.samples,
      'statisticsIncludeFailurePenalty': noService > 0,
      'failurePenaltyArrival': noService > 0
          ? max(q.departure + 240, 1440)
          : null,
      'source': network.data['source'] ?? 'simulated',
      'delaySource': 'simulated',
      'scheduleAvailable': true,
      'scenario': scenario,
      'transfers': max(
        0,
        (j['legs'] as List).where((l) => l['kind'] == 'ride').length - 1,
      ),
      'missPenalty': scenario['arrival'] == null
          ? null
          : max(0, numValue(scenario['arrival']) - numValue(j['arrival'])),
    });
    return j;
  }
}
