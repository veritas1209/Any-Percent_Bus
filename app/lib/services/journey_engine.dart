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
  final _routingCache =
      <(String, int, double), (List<Set<String>>, List<Map<String, double>>)>{};
  late final timedRoutes = network.routes.values
      .where((r) => (r['departures'] as List).isNotEmpty)
      .toList();
  late final boards = <String, List<(Json, int)>>{}
    ..addEntries(_boardEntries());
  Iterable<MapEntry<String, List<(Json, int)>>> _boardEntries() {
    final index = <String, List<(Json, int)>>{};
    for (final r in timedRoutes) {
      for (var i = 0; i < (r['stops'] as List).length - 1; i++) {
        if (r['passengerStops'] != null &&
            !(r['passengerStops'] as List).contains(r['stops'][i])) {
          continue;
        }
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

  static int rank(Json a, Json b) {
    final arrival = numValue(a['arrival']).compareTo(numValue(b['arrival']));
    if (arrival != 0) return arrival;
    final walk = numValue(
      a['walkingMeters'],
    ).compareTo(numValue(b['walkingMeters']));
    if (walk != 0) return walk;
    return (a['legs'] as List)
        .where((leg) => leg['kind'] == 'ride')
        .length
        .compareTo(
          (b['legs'] as List).where((leg) => leg['kind'] == 'ride').length,
        );
  }

  List<Json> search(SearchQuery q, {bool evaluateCandidates = true}) {
    final selected = network.forServiceDay(q.serviceDay, date: q.serviceDate);
    if (!identical(selected, network)) {
      return JourneyEngine(
        selected,
      ).search(q, evaluateCandidates: evaluateCandidates);
    }
    if (q.origin == q.destination) return [];
    final walkLimit = q.maxWalk ?? double.infinity,
        scored = q.walkingPenalty != null || q.maxWalk == null,
        penalty = q.walkingPenalty ?? 1.0;
    final cacheKey = (q.destination, q.maxTransfers, walkLimit);
    if (!_routingCache.containsKey(cacheKey)) {
      if (_routingCache.length >= 8) _routingCache.clear();
      _routingCache[cacheKey] = (
        reachableStops(
          timedRoutes,
          network.data['footpaths'],
          q.destination,
          q.maxTransfers + 1,
          walkLimit,
        ),
        walkingBounds(
          timedRoutes,
          network.data['footpaths'],
          q.destination,
          q.maxTransfers + 1,
        ),
      );
    }
    final (layers, bounds) = _routingCache[cacheKey]!;
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
    var arrivalCutoff = double.infinity, scoreCutoff = double.infinity;
    List<Map<String, double>>? latest;

    bool competitive(
      double now,
      double walked,
      int rides,
      int remaining,
      String stop,
    ) {
      if (now <= arrivalCutoff + 1e-6) return true;
      final leastWalk = walked + (bounds[remaining][stop] ?? double.infinity);
      final optimistic =
          now -
          q.departure +
          leastWalk / q.walkingSpeed / 60 * penalty +
          max(0, rides - 1) * 3;
      return now <= arrivalCutoff + 1e-6 || optimistic <= scoreCutoff + 1e-6;
    }

    void add(List<Json> legs, double walked) {
      final key = legs
          .map((l) => '${l['routeId'] ?? 'walk'}:${l['from']}:${l['to']}')
          .join('|');
      final candidate = <String, dynamic>{
        'id': key,
        'legs': legs,
        'arrival': legs.last['arrive'],
        'walkingMeters': walked,
        if (scored)
          'recommendationScore':
              numValue(legs.last['arrive']) -
              q.departure +
              walked / q.walkingSpeed / 60 * penalty +
              max(0, legs.where((leg) => leg['kind'] == 'ride').length - 1) * 3,
      };
      if (found.containsKey(key) && rank(found[key]!, candidate) <= 0) return;
      found[key] = candidate;
      if (found.length > 20) {
        final keys = found.keys.toList()
          ..sort((a, b) => rank(found[a]!, found[b]!));
        final keep = keys.take(20).toSet();
        if (scored) {
          keys.sort((a, b) {
            final score = numValue(
              found[a]!['recommendationScore'],
            ).compareTo(numValue(found[b]!['recommendationScore']));
            return score != 0 ? score : rank(found[a]!, found[b]!);
          });
          keep.add(keys.first);
        }
        found.removeWhere((key, _) => !keep.contains(key));
      }
      if (found.length >= 20) {
        final arrivals = found.values.toList()..sort(rank);
        arrivalCutoff = numValue(arrivals[19]['arrival']);
        if (scored) {
          final scores =
              found.values
                  .map((row) => numValue(row['recommendationScore']))
                  .toList()
                ..sort();
          scoreCutoff = scores.first;
        }
        cutoff = scored
            ? max(arrivalCutoff, q.departure + scoreCutoff)
            : arrivalCutoff;
      }
    }

    for (final f in walks[q.origin] ?? <Json>[]) {
      if (f['from'] == q.origin &&
          f['to'] == q.destination &&
          f['meters'] <= walkLimit) {
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
      final tripBoardings = <(String, num), List<(int, double)>>{};
      for (final state in frontier) {
        if (numValue(state['now']) > cutoff) continue;
        if (scored &&
            !competitive(
              numValue(state['now']),
              numValue(state['walked']),
              round,
              q.maxTransfers - round + 1,
              state['stop'],
            )) {
          continue;
        }
        if (latest != null &&
            numValue(state['now']) >
                (latest[q.maxTransfers - round + 1][state['stop']] ??
                        double.negativeInfinity) +
                    1e-6) {
          continue;
        }
        if (numValue(state['walked']) +
                (bounds[q.maxTransfers - round + 1][state['stop']] ??
                    double.infinity) >
            walkLimit + .001) {
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
              state['walked'] + f['meters'] <= walkLimit) {
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
          if (scored &&
              !competitive(
                numValue(access['now']),
                numValue(access['walked']),
                round,
                q.maxTransfers - round + 1,
                access['stop'],
              )) {
            continue;
          }
          if (latest != null &&
              numValue(access['now']) >
                  (latest[q.maxTransfers - round + 1][access['stop']] ??
                          double.negativeInfinity) +
                      1e-6) {
            continue;
          }
          for (final (route, bi) in boards[access['stop']] ?? <(Json, int)>[]) {
            final used = state['used'] as Set<String>;
            final stops = (route['stops'] as List).cast<String>();
            if ((!scored && used.contains(route['id'])) ||
                !stops.contains(access['stop'])) {
              continue;
            }
            final departures = (route['departures'] as List).cast<num>();
            final offsets = (route['offsets'] as List).cast<num>();
            final buffer = round == 0 ? 0.0 : 0.5 + q.transferMargin;
            final index = firstDeparture(
              departures,
              numValue(access['now']) + buffer - offsets[bi],
            );
            if (index == departures.length) continue;
            final trip = departures[index];
            if (scored) {
              final priorLegs = (state['legs'] as List).cast<Json>();
              if (priorLegs.isNotEmpty &&
                  priorLegs.last['kind'] == 'ride' &&
                  priorLegs.last['routeId'] == route['id'] &&
                  priorLegs.last['trip'] == trip) {
                continue;
              }
              final key = (route['id'] as String, trip);
              final boarded = tripBoardings.putIfAbsent(key, () => []);
              final walked = numValue(access['walked']);
              if (boarded.any(
                (old) => old.$1 <= bi && old.$2 <= walked + .001,
              )) {
                continue;
              }
              boarded.removeWhere(
                (old) => bi <= old.$1 && walked <= old.$2 + .001,
              );
              boarded.add((bi, walked));
            }
            for (var ai = bi + 1; ai < stops.length; ai++) {
              if (route['passengerStops'] != null &&
                  !(route['passengerStops'] as List).contains(stops[ai])) {
                continue;
              }
              if (trip + offsets[ai] > cutoff) break;
              if (scored &&
                  !competitive(
                    (trip + offsets[ai]).toDouble(),
                    numValue(access['walked']),
                    round + 1,
                    q.maxTransfers - round,
                    stops[ai],
                  )) {
                continue;
              }
              if (latest != null &&
                  trip + offsets[ai] >
                      (latest[q.maxTransfers - round][stops[ai]] ??
                              double.negativeInfinity) +
                          1e-6) {
                continue;
              }
              if (!layers[q.maxTransfers - round].contains(stops[ai])) continue;
              if (numValue(access['walked']) +
                      (bounds[q.maxTransfers - round][stops[ai]] ??
                          double.infinity) >
                  walkLimit + .001) {
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
                      numValue(access['walked']) + f['meters'] <= walkLimit) {
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
      if (round < q.maxTransfers) {
        final remaining = q.maxTransfers - round;
        latest = cutoff.isFinite
            ? latestDepartures(
                timedRoutes,
                network.data['footpaths'],
                q.destination,
                remaining,
                cutoff,
                q.walkingSpeed,
              )
            : null;
        final limits = latest;
        frontier = paretoLabels(
          next
              .where(
                (s) =>
                    numValue(s['now']) <= cutoff &&
                    (limits == null ||
                        numValue(s['now']) <=
                            (limits[remaining][s['stop']] ??
                                    double.negativeInfinity) +
                                1e-6),
              )
              .toList(),
          respectUsed: !scored,
        );
      }
    }
    final candidates = found.values.toList()..sort(rank);
    if (candidates.isEmpty) {
      return network.data['catalogFallback'] == true
          ? topologyConnections(network, q)
          : [];
    }
    return evaluateCandidates ? finishCandidates(candidates, q) : candidates;
  }

  List<Json> finishCandidates(List<Json> rows, SearchQuery q) {
    if (rows.isEmpty) return [];
    var candidates = List<Json>.from(rows);
    final scored = q.walkingPenalty != null || q.maxWalk == null;
    if (scored && q.maxTransfers > 0 && q.transferMargin == 0) {
      final protected =
          search(
            q.copyWith(transferMargin: 5),
            evaluateCandidates: false,
          ).where((j) => j['arrival'] != null).toList()..sort((a, b) {
            final score = numValue(
              a['recommendationScore'],
            ).compareTo(numValue(b['recommendationScore']));
            return score != 0 ? score : rank(a, b);
          });
      final known = candidates.map((j) => j['id']).toSet(),
          strategies = <String>{};
      final places = candidates.first['places'];
      for (final j in protected) {
        final strategy = (j['legs'] as List)
            .where((l) => l['kind'] == 'ride')
            .map((l) => l['routeId'])
            .join('|');
        if (known.contains(j['id']) || strategies.contains(strategy)) continue;
        if (places != null) j['places'] = places;
        candidates.add(j);
        known.add(j['id']);
        strategies.add(strategy);
        if (strategies.length >= 5) break;
      }
    }
    if (scored) {
      final singleRides = <String, Json>{}, alternatives = <Json>[];
      for (final journey in candidates) {
        final rides = (journey['legs'] as List)
            .where((leg) => leg['kind'] == 'ride')
            .toList();
        if (rides.length != 1) {
          alternatives.add(journey);
          continue;
        }
        final ride = rides.single,
            key = '${ride['routeId']}:${ride['trip']}:${ride['alightIndex']}';
        if (!singleRides.containsKey(key) ||
            rank(journey, singleRides[key]!) < 0) {
          singleRides[key] = journey;
        }
      }
      candidates = [...alternatives, ...singleRides.values];
    }
    final evaluated = candidates.map((j) => evaluate(j, q)).toList();
    final earliest = evaluated.reduce((a, b) => rank(a, b) <= 0 ? a : b);
    final safest = evaluated.reduce(
      (a, b) =>
          (a['safeScore'] ?? a['p90Arrival']) <
                  (b['safeScore'] ?? b['p90Arrival']) ||
              (a['safeScore'] ?? a['p90Arrival']) ==
                      (b['safeScore'] ?? b['p90Arrival']) &&
                  a['expectedArrival'] < b['expectedArrival']
          ? a
          : b,
    );
    final recommended = scored
        ? evaluated.reduce(
            (a, b) =>
                a['recommendationScore'] < b['recommendationScore'] ||
                    a['recommendationScore'] == b['recommendationScore'] &&
                        rank(a, b) <= 0
                ? a
                : b,
          )
        : null;
    for (final j in evaluated) {
      j['tags'] = <String>[
        if (j['id'] == recommended?['id']) '추천',
        if (j['id'] == earliest['id']) 'ANY%',
        if (j['id'] == safest['id']) 'SAFE',
      ];
    }
    evaluated.sort((a, b) {
      if (scored) {
        final score = numValue(
          a['recommendationScore'],
        ).compareTo(numValue(b['recommendationScore']));
        return score != 0 ? score : rank(a, b);
      }
      final priority = (a['tags'] as List).isEmpty ? 1 : 0;
      final other = (b['tags'] as List).isEmpty ? 1 : 0;
      return priority == other ? rank(a, b) : priority.compareTo(other);
    });
    return evaluated;
  }

  Json replay(
    Json journey,
    SearchQuery q, [
    Map<String, double>? draws,
    double Function(Json, num)? sampleDelay,
  ]) {
    final selected = network.forServiceDay(q.serviceDay, date: q.serviceDate);
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
    if (q.walkingPenalty != null || q.maxWalk == null) {
      final extra =
          numValue(j['walkingMeters']) /
              q.walkingSpeed /
              60 *
              (q.walkingPenalty ?? 1) +
          numValue(j['transfers']) * 3;
      j['recommendationScore'] = numValue(j['arrival']) - q.departure + extra;
      j['safeScore'] = numValue(j['p90Arrival']) - q.departure + extra;
    }
    return j;
  }
}
