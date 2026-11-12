import 'dart:convert';
import 'dart:typed_data';
import 'package:flutter_test/flutter_test.dart';
import 'package:anypercent_app/models/transit.dart';
import 'package:anypercent_app/services/transfers.dart';
import 'package:anypercent_app/services/walking_graph.dart';
import 'package:anypercent_app/services/journey_engine.dart';

TransferGraph lineGraph(double meters) {
  final text = utf8.encode(
    jsonEncode({
      'stopIds': ['p', 'q'],
    }),
  );
  final size = (text.length + 7) ~/ 8 * 8;
  final offset = (24 + size + 7 * 4 + 7) ~/ 8 * 8;
  final bytes = Uint8List(offset + 32), h = ByteData.sublistView(bytes);
  bytes.setRange(0, 4, ascii.encode('APX1'));
  h.setUint32(4, 2, Endian.little);
  h.setUint32(8, 2, Endian.little);
  h.setUint32(12, 2, Endian.little);
  h.setUint32(16, size, Endian.little);
  bytes.fillRange(24, 24 + size, 32);
  bytes.setRange(24, 24 + text.length, text);
  var i = 24 + size;
  for (final value in [0, 1, 2, 1, 0, 0, 1]) {
    h.setUint32(i, value, Endian.little);
    i += 4;
  }
  h.setFloat64(offset, meters, Endian.little);
  h.setFloat64(offset + 8, meters, Endian.little);
  return TransferGraph(bytes);
}

class FakeWalks extends WalkingGraph {
  FakeWalks() : super(empty());
  static Uint8List empty() {
    final b = Uint8List(28);
    b.setRange(0, 4, ascii.encode('APW1'));
    return b;
  }

  @override
  List<Json> connections(
    Json point,
    Iterable<Json> stops,
    double budget, {
    bool reverse = false,
    Json? stats,
  }) => [
    {
      'stop': stops.first['id'],
      'meters': 6000.0,
      'points': [
        [35.0, 129.0],
        [35.05, 129.0],
      ],
    },
  ];
}

void main() {
  test(
    'a transfer longer than five kilometers is scored instead of excluded',
    () {
      final network = Network({
        'stops': [
          for (final s in ['o', 'p', 'q', 'd'])
            {
              'id': s,
              if (s == 'p' || s == 'q') ...{'lat': 35.0, 'lon': 129.0},
            },
        ],
        'routes': [
          {
            'id': 'A',
            'stops': ['o', 'p'],
            'departures': [5],
            'offsets': [0, 5],
            'delaySamples': [0],
          },
          {
            'id': 'B',
            'stops': ['q', 'd'],
            'departures': [110],
            'offsets': [0, 5],
            'delaySamples': [0],
          },
          {
            'id': 'direct',
            'stops': ['o', 'd'],
            'departures': [5],
            'offsets': [0, 195],
            'delaySamples': [0],
          },
        ],
        'footpaths': <Json>[],
      });
      final engine = JourneyEngine(
        network,
        walkingGraph: FakeWalks(),
        transferGraph: lineGraph(6000),
      );
      List<Json> search(double penalty) => engine.search(
        SearchQuery(
          origin: 'o',
          destination: 'd',
          departure: 0,
          maxWalk: null,
          walkingPenalty: penalty,
          maxTransfers: 1,
          samples: 20,
        ),
      );
      final less = search(2), willing = search(.25);
      expect(less.first['walkingMeters'], 0);
      expect(willing.first['walkingMeters'], 6000);
      expect(
        less.firstWhere((j) => (j['tags'] as List).contains('ANY%'))['arrival'],
        115,
      );
      expect(
        (willing.first['legs'] as List).any(
          (l) => l['shape']?['source'] == 'pedestrian_transfer',
        ),
        isTrue,
      );
    },
  );
  test('multisource walking retains both arrival and walking alternatives', () {
    final rows = lineGraph(600).spread(
      [
        {
          'stop': 'p',
          'now': 0.0,
          'walked': 0.0,
          'legs': <Json>[],
          'used': <String>{},
        },
        {
          'stop': 'q',
          'now': 5.0,
          'walked': 1000.0,
          'legs': <Json>[],
          'used': <String>{},
        },
      ],
      1.2,
      10000,
      double.infinity,
      boardable: {'q'},
    );
    final targets = rows.where((r) => r['stop'] == 'q').toList();
    expect(targets.length, 2);
    expect(targets.map((r) => r['walked']).toSet(), {600.0, 1000.0});
  });
}
