import 'dart:io';
import 'package:flutter/material.dart';
import 'package:flutter_map/flutter_map.dart';
import 'package:flutter_test/flutter_test.dart';
import 'package:anypercent_app/models/transit.dart';
import 'package:anypercent_app/services/journey_engine.dart';
import 'package:anypercent_app/widgets/route_map_geometry.dart';
import 'package:anypercent_app/widgets/transit_map.dart';
import 'package:anypercent_app/widgets/transit_diagram.dart';
import 'support/map_tiles.dart';

void main() {
  final network = Network.decode(
    File('assets/data/network.json').readAsStringSync(),
  );
  final journey = JourneyEngine(network)
      .search(
        const SearchQuery(origin: 'uc', destination: 'tower', samples: 20),
      )
      .firstWhere((j) => (j['tags'] as List).contains('ANY%'));
  final legs = List<Json>.from(journey['legs']);

  testWidgets(
    'tile failures offer an offline diagram without breaking the journey',
    (tester) async {
      await tester.pumpWidget(
        MaterialApp(
          home: Scaffold(
            body: TransitMap(
              network: network,
              legs: legs,
              tileProviderFactory: FailedMapTiles.new,
            ),
          ),
        ),
      );
      await tester.pumpAndSettle();
      expect(find.text('지도 연결을 확인해주세요.'), findsOneWidget);
      await tester.tap(find.text('개략도로 보기'));
      await tester.pumpAndSettle();
      expect(find.byType(TransitDiagram), findsOneWidget);
      expect(tester.takeException(), isNull);
    },
  );

  test('map follows selected stop sequence and selected vehicle only', () {
    final geometry = RouteMapGeometry(network, legs);
    expect(geometry.segments.map((s) => s.walking), [false, true, false]);
    expect(geometry.segments.first.stopIds, ['uc', 'hwajung', 'station']);
    expect(
      geometry.stopIds,
      containsAll(['uc', 'hwajung', 'station', 'station-b', 'samsan', 'tower']),
    );
    expect(geometry.stopIds, isNot(contains('seongnam')));
    expect(geometry.vehicles(550), hasLength(1));
    expect(geometry.vehicles(550).single.latitude, greaterThan(35.501));
    expect(geometry.vehicles(550).single.latitude, lessThan(35.5394));
  });

  testWidgets(
    'map supports zoom, stop details, fullscreen and diagram fallback',
    (tester) async {
      tester.view.physicalSize = const Size(390, 844);
      tester.view.devicePixelRatio = 1;
      addTearDown(tester.view.resetPhysicalSize);
      addTearDown(tester.view.resetDevicePixelRatio);
      await tester.pumpWidget(
        MaterialApp(
          home: Scaffold(
            body: SafeArea(
              child: Padding(
                padding: const EdgeInsets.all(24),
                child: TransitMap(
                  network: network,
                  legs: legs,
                  minute: 550,
                  tileProviderFactory: MemoryMapTiles.new,
                ),
              ),
            ),
          ),
        ),
      );
      await tester.pumpAndSettle();
      expect(find.text('© OpenStreetMap contributors'), findsOneWidget);
      final map = tester.widget<FlutterMap>(
        find.byKey(const Key('journey-street-map')),
      );
      final before = map.mapController!.camera.zoom;
      await tester.tap(find.byTooltip('지도 확대'));
      await tester.pumpAndSettle();
      expect(map.mapController!.camera.zoom, closeTo(before + 1, .001));
      await tester.tap(find.byTooltip('전체 경로 맞추기'));
      await tester.pumpAndSettle();
      expect(map.mapController!.camera.zoom, closeTo(before, .001));
      await tester.tap(find.text('A'));
      await tester.pumpAndSettle();
      expect(find.text('울산과학대학앞'), findsOneWidget);
      expect(find.textContaining('탑승 09:00'), findsOneWidget);
      Navigator.of(tester.element(find.text('울산과학대학앞'))).pop();
      await tester.pumpAndSettle();
      await tester.tap(find.byTooltip('전체 화면 지도'));
      await tester.pumpAndSettle();
      expect(find.text('전체 경로 지도'), findsOneWidget);
      await tester.pageBack();
      await tester.pumpAndSettle();
      await tester.tap(find.text('개략도 보기'));
      await tester.pumpAndSettle();
      expect(find.byType(TransitDiagram), findsOneWidget);
      expect(find.byType(FlutterMap), findsNothing);
      await tester.tap(find.text('지도 보기'));
      await tester.pumpAndSettle();
      expect(find.byType(FlutterMap), findsOneWidget);
      expect(tester.takeException(), isNull);
    },
  );
}
