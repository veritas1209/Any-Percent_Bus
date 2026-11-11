import 'package:flutter_test/flutter_test.dart';
import 'package:anypercent_app/models/transit.dart';
import 'package:anypercent_app/services/journey_engine.dart';

Network network(List<String> stops, List<Json> routes) => Network({
  'stops': [
    for (final s in stops) {'id': s},
  ],
  'routes': routes,
  'footpaths': <Json>[],
});
Json route(
  String id,
  List<String> stops,
  List<num> offsets,
  List<num> trips,
  List<num> delays,
) => {
  'id': id,
  'stops': stops,
  'offsets': offsets,
  'departures': trips,
  'delaySamples': delays,
};

void main() {
  test('express transfer can reboard an earlier trip of the first route', () {
    final data = network(
      ['o', 'u', 'v', 'd'],
      [
        route('A', ['o', 'u', 'v', 'd'], [0, 10, 40, 60], [20, 40], [0]),
        route('B', ['u', 'v'], [0, 1], [51], [0]),
      ],
    );
    final rows = JourneyEngine(data).search(
      const SearchQuery(
        origin: 'o',
        destination: 'd',
        departure: 25,
        maxWalk: 0,
        walkingPenalty: 1,
        maxTransfers: 2,
      ),
    );
    final fastest = rows.firstWhere(
      (j) => (j['tags'] as List).contains('ANY%'),
    );
    expect(fastest['arrival'], 80);
    expect(
      (fastest['legs'] as List).map((l) => '${l['routeId']}:${l['trip']}'),
      ['A:40', 'B:51', 'A:20'],
    );
  });
  test('protected candidates preserve a safer later prefix', () {
    final data = network(
      ['o', 'x', 'y', 'h', 'd'],
      [
        route('A', ['o', 'x'], [0, 5], [5], [0, 4]),
        route('B', ['x', 'h'], [0, 5], [10.5, 70.5], [0]),
        route('C', ['o', 'y'], [0, 2], [5], [0]),
        route('D', ['y', 'h'], [0, 6], [13.5], [0]),
        route('E', ['h', 'd'], [0, 5], [26, 86], [0]),
      ],
    );
    final rows = JourneyEngine(data).search(
      const SearchQuery(
        origin: 'o',
        destination: 'd',
        departure: 0,
        maxWalk: 0,
        walkingPenalty: 1,
        maxTransfers: 2,
      ),
    );
    final safer = rows.firstWhere((j) => (j['tags'] as List).contains('SAFE'));
    expect((safer['legs'] as List).map((l) => l['routeId']), ['C', 'D', 'E']);
    expect(safer['p90Arrival'], 31);
    final risky = rows.firstWhere(
      (j) => (j['legs'] as List).map((l) => l['routeId']).join(',') == 'A,B,E',
    );
    expect(risky['p90Arrival'], 91);
  });
}
