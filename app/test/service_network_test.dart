import 'dart:convert';
import 'dart:io';
import 'package:flutter_test/flutter_test.dart';
import 'package:anypercent_app/models/transit.dart';
import 'package:anypercent_app/repositories/transit_repository.dart';
import 'package:anypercent_app/services/journey_engine.dart';

void main() {
  TestWidgetsFlutterBinding.ensureInitialized();
  test(
    'walking preferences change the recommendation without a hard distance limit',
    () {
      final network = Network({
        'stops': [
          for (final s in ['o', 'near', 'far', 'd']) {'id': s},
        ],
        'routes': <Json>[
          {
            'id': 'fast',
            'stops': ['far', 'd'],
            'offsets': [0, 10],
            'departures': [15],
            'delaySamples': [0],
          },
          {
            'id': 'shortwalk',
            'stops': ['near', 'd'],
            'offsets': [0, 10],
            'departures': [20],
            'delaySamples': [0],
          },
        ],
        'footpaths': <Json>[
          {'from': 'o', 'to': 'far', 'meters': 800},
          {'from': 'o', 'to': 'near', 'meters': 50},
        ],
      });
      List<Json> search(double penalty) => JourneyEngine(network).search(
        SearchQuery(
          origin: 'o',
          destination: 'd',
          departure: 0,
          maxWalk: null,
          walkingPenalty: penalty,
          maxTransfers: 0,
          samples: 20,
        ),
      );
      final less = search(2), willing = search(.25);
      String ride(Json row) => (row['legs'] as List).firstWhere(
        (leg) => leg['kind'] == 'ride',
      )['routeId'];
      expect(ride(less.first), 'shortwalk');
      expect(ride(willing.first), 'fast');
      expect(less.first['tags'], contains('추천'));
      expect(
        less.firstWhere(
          (row) => (row['tags'] as List).contains('ANY%'),
        )['arrival'],
        25,
      );
      network.data['routes'] = <Json>[
        {
          'id': 'fast',
          'stops': ['far', 'd'],
          'offsets': [0, 10],
          'departures': [100],
          'delaySamples': [0],
        },
      ];
      network.data['footpaths'] = <Json>[
        {'from': 'o', 'to': 'far', 'meters': 6000},
      ];
      final long = JourneyEngine(Network(network.data)).search(
        const SearchQuery(
          origin: 'o',
          destination: 'd',
          departure: 0,
          maxWalk: null,
          samples: 20,
        ),
      );
      expect(long.first['walkingMeters'], 6000);
    },
  );
  test(
    '14:15 campus search chooses the near stop and retains the middle road line',
    () {
      final network = Network.decode(
        File('assets/data/service_network.json').readAsStringSync(),
      );
      final rows = runLocal({
        ...const SearchQuery(
          origin: 'campus',
          destination: 'upsquare',
          dataset: 'service',
          departure: 855,
          maxWalk: null,
          walkingPenalty: 1,
          maxTransfers: 1,
          samples: 20,
          originPoint: {
            'name': 'campus',
            'lat': 35.4972505,
            'lon': 129.4158209,
          },
          destinationPoint: {
            'name': 'upsquare',
            'lat': 35.5412587,
            'lon': 129.3388543,
          },
        ).toJson(),
        'network': network.routingData,
        'walkGraph': File('assets/data/walk_graph.bin').readAsBytesSync(),
        'transferGraph': File(
          'assets/data/transfer_graph.bin',
        ).readAsBytesSync(),
      });
      final fastest = rows.firstWhere(
        (row) => (row['tags'] as List).contains('ANY%'),
      );
      final ride = (fastest['legs'] as List).firstWhere(
        (leg) => leg['kind'] == 'ride',
      );
      expect(network.stops[ride['from']]!['publicId'], '27121');
      expect(fastest['walkingMeters'], lessThan(700));
      final route = network.routes['its:194000091']!;
      expect(
        (route['shapeSegments'] as List).every(
          (key) => (network.shape(key)['points'] as List).isNotEmpty,
        ),
        isTrue,
      );
    },
  );
  test(
    'wide walking and two transfers retain the faster one-transfer option',
    () {
      final n = Network.decode(
        File('assets/data/service_network.json').readAsStringSync(),
      );
      final walk = File('assets/data/walk_graph.bin').readAsBytesSync();
      List<Json> search(int transfers) => runLocal({
        ...SearchQuery(
          origin: 'campus',
          destination: 'upsquare',
          dataset: 'service',
          departure: 765,
          maxWalk: 5000,
          maxTransfers: transfers,
          samples: 20,
          originPoint: const {
            'name': 'campus',
            'lat': 35.5426092,
            'lon': 129.2540322,
          },
          destinationPoint: const {
            'name': 'upsquare',
            'lat': 35.5412587,
            'lon': 129.3388543,
          },
        ).toJson(),
        'network': n.routingData,
        'walkGraph': walk,
        'transferGraph': File(
          'assets/data/transfer_graph.bin',
        ).readAsBytesSync(),
      });
      final one = search(1), two = search(2);
      expect(two.length, 20);
      expect(
        two.first['arrival'],
        lessThanOrEqualTo(one.first['arrival'] as num),
      );
      expect(
        two.every(
          (row) => row['walkingMeters'] <= 5000 && row['transfers'] <= 2,
        ),
        isTrue,
      );
    },
  );
  test(
    'both campuses connect to Upsquare at 12:45 within one kilometre of walking',
    () {
      final n = Network.decode(
        File('assets/data/service_network.json').readAsStringSync(),
      );
      final walk = File('assets/data/walk_graph.bin').readAsBytesSync();
      for (final (lat, lon) in [
        (35.4972505, 129.4158209),
        (35.5426092, 129.2540322),
      ]) {
        final rows = runLocal({
          ...SearchQuery(
            origin: 'campus',
            destination: 'upsquare',
            dataset: 'service',
            departure: 765,
            originPoint: {'name': 'campus', 'lat': lat, 'lon': lon},
            destinationPoint: const {
              'name': 'upsquare',
              'lat': 35.5412587,
              'lon': 129.3388543,
            },
            maxWalk: 1000,
            maxTransfers: 1,
            samples: 20,
          ).toJson(),
          'network': n.routingData,
          'walkGraph': walk,
          'transferGraph': File(
            'assets/data/transfer_graph.bin',
          ).readAsBytesSync(),
        });
        expect(rows, isNotEmpty);
        expect(
          rows.every(
            (row) => row['walkingMeters'] <= 1000 && row['transfers'] <= 1,
          ),
          isTrue,
        );
      }
      final route = n.routes.values.first;
      final ids = List<String>.from(route['shapeSegments']);
      final merged = Network(n.routingData).withGeometry({
        'routes': {
          route['id']: {'shapeSegments': ids},
        },
        'shapes': {for (final id in ids) id: n.data['shapes'][id]},
      });
      expect(merged.routes[route['id']]!['shapeSegments'], ids);
      expect(merged.shape(ids.first), n.shape(ids.first));
    },
  );
  test('service days select the matching trip in search and replay', () {
    final network = Network({
      'source': 'official_timetable',
      'dataset': 'service',
      'stops': <Json>[
        {'id': 'o'},
        {'id': 'd'},
      ],
      'footpaths': <Json>[],
      'routes': <Json>[
        {
          'id': 'bus',
          'stops': ['o', 'd'],
          'offsets': [0, 10],
          'departures': [600, 620],
          'delaySamples': [0],
          'departuresByDay': {
            'weekday': [600, 620],
            'saturday': [650],
            'holiday': <num>[],
          },
        },
      ],
    });
    final engine = JourneyEngine(network);
    const q = SearchQuery(
      origin: 'o',
      destination: 'd',
      departure: 610,
      serviceDay: 'saturday',
      samples: 20,
    );
    final saturday = engine.search(q).first;
    expect(saturday['arrival'], 660);
    expect(engine.replay(saturday, q)['arrival'], 660);
    expect(
      engine
          .search(
            const SearchQuery(
              origin: 'o',
              destination: 'd',
              departure: 610,
              samples: 20,
            ),
          )
          .first['arrival'],
      630,
    );
    expect(
      engine.search(
        const SearchQuery(
          origin: 'o',
          destination: 'd',
          departure: 610,
          serviceDay: 'holiday',
          samples: 20,
        ),
      ),
      isEmpty,
    );
  });
  test(
    'offline official point search works at 10:07 with geometry-free routing data',
    () {
      final n = Network.decode(
        File('assets/data/service_network.json').readAsStringSync(),
      );
      expect(n.routingData.containsKey('shapes'), isFalse);
      expect(
        (n.routingData['routes'] as List).every(
          (r) => r['shapeSegments'] == null,
        ),
        isTrue,
      );
      final rows = runLocal({
        ...SearchQuery(
          origin: n.defaultOrigin,
          destination: 'upsquare',
          dataset: 'service',
          departure: 607,
          originPoint: n.stops[n.defaultOrigin],
          destinationPoint: const {
            'name': '업스퀘어',
            'lat': 35.5412587,
            'lon': 129.3388543,
          },
          maxTransfers: 1,
          samples: 20,
        ).toJson(),
        'network': n.routingData,
        'walkGraph': File('assets/data/walk_graph.bin').readAsBytesSync(),
        'transferGraph': File(
          'assets/data/transfer_graph.bin',
        ).readAsBytesSync(),
      });
      expect(rows, isNotEmpty);
      expect(rows.any((r) => (r['tags'] as List).contains('ANY%')), isTrue);
      expect(
        rows.every(
          (r) =>
              r['arrival'] >= 607 &&
              r['walkingMeters'] <= 500 &&
              r['transfers'] <= 1,
        ),
        isTrue,
      );
      expect(
        jsonEncode(n.routingData).length,
        lessThan(jsonEncode(n.data).length ~/ 3),
      );
    },
  );
}
