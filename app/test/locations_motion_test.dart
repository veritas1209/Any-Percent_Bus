import 'dart:convert';
import 'dart:io';
import 'package:flutter/material.dart';
import 'package:flutter_map/flutter_map.dart';
import 'package:flutter_test/flutter_test.dart';
import 'package:latlong2/latlong.dart';
import 'package:anypercent_app/models/transit.dart';
import 'package:anypercent_app/repositories/transit_repository.dart';
import 'package:anypercent_app/services/walking_graph.dart';
import 'package:anypercent_app/widgets/location_picker.dart';
import 'package:anypercent_app/widgets/route_map_geometry.dart';
import 'support/map_tiles.dart';

void main() {
  test(
    'walking graph follows the bridge and rejects a disconnected nearby edge',
    () {
      final g = WalkingGraph(
        File('../shared/test_walk_graph.bin').readAsBytesSync(),
      );
      final stops = <Json>[
        {'id': 'bank', 'lat': 35.501, 'lon': 129.3},
        {'id': 'island', 'lat': 35.5005, 'lon': 129.3},
      ];
      expect(g.connections({'lat': 35.5, 'lon': 129.3}, stops, 150), isEmpty);
      final result = g.connections({'lat': 35.5, 'lon': 129.3}, stops, 350);
      expect(result.single['stop'], 'bank');
      expect(result.single['meters'], closeTo(293, .2));
      final n = Json.from(
        jsonDecode(
          File('../shared/test_point_network.json').readAsStringSync(),
        ),
      );
      final rows = runLocal({
        ...const SearchQuery(
          origin: 'point',
          destination: 'target',
          originPoint: {'name': '출발', 'lat': 35.5, 'lon': 129.3},
          walkingSpeed: 1,
          maxWalk: 350,
          samples: 20,
        ).toJson(),
        'network': n,
        'walkGraph': File('../shared/test_walk_graph.bin').readAsBytesSync(),
      });
      expect(rows.first['arrival'], 548);
      expect(rows.first['legs'][0]['to'], 'far');
    },
  );
  test(
    'GPS pauses and scenario delay move along the recorded curve without stop-centroid detours',
    () {
      final n = Network({
        'motionVersion': 'test',
        'geometryVersion': 'test',
        'source': 'replay_observed',
        'footpaths': [],
        'stops': [
          {'id': 'a', 'lat': 35.51, 'lon': 129.29},
          {'id': 'b', 'lat': 35.51, 'lon': 129.32},
        ],
        'shapes': {
          'trace': {
            'points': [
              [35.5, 129.3],
              [35.5, 129.301],
              [35.501, 129.301],
            ],
          },
        },
        'routes': [
          {
            'id': 'r',
            'number': '124',
            'scheduleSource': 'replay_observed',
            'stops': ['a', 'b'],
            'offsets': [0, 3],
            'departures': [420],
            'traceChunks': [
              {
                'shape': 'trace',
                'samples': [
                  [420, 0],
                  [421, 0],
                  [422, 91],
                  [423, 202],
                ],
              },
            ],
          },
        ],
      });
      final legs = <Json>[
        {
          'kind': 'ride',
          'routeId': 'r',
          'from': 'a',
          'to': 'b',
          'boardIndex': 0,
          'alightIndex': 1,
          'trip': 420,
          'depart': 423,
          'arrive': 426,
        },
      ];
      final g = RouteMapGeometry(n, legs);
      expect(g.vehicles(423.5).single, const LatLng(35.5, 129.3));
      expect(g.vehicles(424.5).single.longitude, closeTo(129.3005, .00001));
      expect(g.vehicles(422), isEmpty);
      expect(
        g.segments.single.points.every((p) => p.latitude < 35.502),
        isTrue,
      );
    },
  );
  testWidgets(
    'map picker accepts an arbitrary point rather than requiring a transit stop',
    (tester) async {
      tester.view.physicalSize = const Size(390, 844);
      tester.view.devicePixelRatio = 1;
      addTearDown(tester.view.resetPhysicalSize);
      addTearDown(tester.view.resetDevicePixelRatio);
      await tester.runAsync(LocalPlaces.load);
      Json? result;
      final n = Network({'stops': [], 'routes': [], 'footpaths': []});
      await tester.pumpWidget(
        MaterialApp(
          home: Builder(
            builder: (context) => Scaffold(
              body: TextButton(
                onPressed: () async {
                  result = await showModalBottomSheet<Json>(
                    context: context,
                    isScrollControlled: true,
                    builder: (_) => LocationPicker(
                      network: n,
                      title: '출발 지점',
                      initial: const {'lat': 35.5, 'lon': 129.3},
                      tileProviderFactory: MemoryMapTiles.new,
                      advancedBuilder: (_, _, _) => const SizedBox(),
                    ),
                  );
                },
                child: const Text('지점 선택'),
              ),
            ),
          ),
        ),
      );
      await tester.tap(find.text('지점 선택'));
      await tester.pumpAndSettle();
      await tester.tap(find.text('지도에서 고르기'));
      await tester.pumpAndSettle();
      final map = tester.widget<FlutterMap>(
        find.byKey(const Key('location-picker-map')),
      );
      map.options.onTap!(
        const TapPosition(Offset.zero, Offset.zero),
        const LatLng(35.50123, 129.30234),
      );
      await tester.pump();
      await tester.tap(find.text('이 지점으로 정하기'));
      await tester.pumpAndSettle();
      expect(result!['lat'], 35.50123);
      expect(result!['lon'], 129.30234);
      expect(result!['isLocation'], isTrue);
      expect(tester.takeException(), isNull);
    },
  );
}
