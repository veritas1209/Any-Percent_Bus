import 'dart:io';
import 'package:flutter/material.dart';
import 'package:flutter_test/flutter_test.dart';
import 'package:anypercent_app/main.dart';
import 'package:anypercent_app/models/transit.dart';
import 'package:anypercent_app/services/journey_engine.dart';
import 'package:anypercent_app/screens/results_screen.dart';
import 'package:anypercent_app/screens/journey_screen.dart';
import 'package:anypercent_app/screens/conditions_screen.dart';
import 'package:anypercent_app/repositories/transit_repository.dart';
import 'support/map_tiles.dart';

class MemoryRepository implements TransitRepository {
  final Network network;
  MemoryRepository(this.network);
  @override
  String get label => '테스트';
  @override
  Future<Network> loadNetwork() async => network;
  @override
  Future<List<Json>> search(SearchQuery q) async =>
      JourneyEngine(network).search(q);
}

void main() {
  final network = Network.decode(
    File('assets/data/network.json').readAsStringSync(),
  );
  final engine = JourneyEngine(network);
  test(
    'simulation agrees with the analytically known 50 percent connection',
    () {
      final probability = JourneyEngine(
        Network.decode(
          File('../shared/test_probability_network.json').readAsStringSync(),
        ),
      );
      final j = probability
          .search(
            const SearchQuery(
              origin: 'o',
              destination: 'd',
              departure: 0,
              samples: 1000,
            ),
          )
          .first;
      expect((numValue(j['successProbability']) - .5).abs(), lessThan(.04));
      expect((numValue(j['expectedArrival']) - 24.5).abs(), lessThan(.8));
      expect(j['p90Arrival'], 34);
      expect(j['noServiceProbability'], 0);
    },
  );
  test('final walking leg and walk-only route respect the distance budget', () {
    final walking = JourneyEngine(
      Network.decode(
        File('../shared/test_walk_network.json').readAsStringSync(),
      ),
    );
    final rows = walking.search(
      const SearchQuery(
        origin: 'a',
        destination: 'c',
        walkingSpeed: 1,
        maxWalk: 120,
        maxTransfers: 0,
        samples: 20,
      ),
    );
    expect(rows.first['arrival'], 547);
    expect(rows.first['walkingMeters'], 120);
    expect(rows.first['transfers'], 0);
    expect(
      walking.search(
        const SearchQuery(
          origin: 'a',
          destination: 'c',
          walkingSpeed: 1,
          maxWalk: 119,
          samples: 20,
        ),
      ),
      isEmpty,
    );
    final walk = walking
        .search(
          const SearchQuery(
            origin: 'b',
            destination: 'c',
            walkingSpeed: 1,
            maxWalk: 120,
            samples: 20,
          ),
        )
        .first;
    expect(walk['arrival'], 542);
    expect(walk['transfers'], 0);
  });
  test('observed replay preserves provenance and its one-hour boundary', () {
    final observed = Network.decode(
      File('assets/data/observed_network.json').readAsStringSync(),
    );
    final replay = JourneyEngine(observed);
    final rows = replay.search(
      SearchQuery(
        origin: observed.defaultOrigin,
        destination: observed.defaultDestination,
        departure: 430,
        dataset: 'observed',
        samples: 20,
      ),
    );
    expect(rows, isNotEmpty);
    expect(
      rows.every(
        (j) =>
            j['source'] == 'replay_observed' && j['delaySource'] == 'simulated',
      ),
      isTrue,
    );
    expect(
      replay.search(
        SearchQuery(
          origin: observed.defaultOrigin,
          destination: observed.defaultDestination,
          departure: 480,
          samples: 20,
        ),
      ),
      everyElement(containsPair('scheduleAvailable', false)),
    );
  });
  test('Any% and Safe differ under delay risk', () {
    final rows = engine.search(
      const SearchQuery(origin: 'uc', destination: 'tower', samples: 100),
    );
    final fast = rows.firstWhere((j) => (j['tags'] as List).contains('ANY%'));
    final safe = rows.firstWhere((j) => (j['tags'] as List).contains('SAFE'));
    expect(fast['arrival'], lessThan(safe['arrival']));
    expect(safe['p90Arrival'], lessThan(fast['p90Arrival']));
    expect(safe['successProbability'], greaterThan(fast['successProbability']));
    final late = engine.replay(
      fast,
      const SearchQuery(origin: 'uc', destination: 'tower', delay: 3),
    );
    expect(late['missed'], ['demo-b']);
    expect(late['arrival'], 596);
  });
  test(
    'walking limits, zero transfers, last service and disconnected stop',
    () {
      final noWalk = engine.search(
        const SearchQuery(
          origin: 'uc',
          destination: 'tower',
          maxWalk: 0,
          samples: 20,
        ),
      );
      expect(noWalk.every((j) => j['walkingMeters'] == 0), isTrue);
      final direct = engine.search(
        const SearchQuery(
          origin: 'uc',
          destination: 'tower',
          maxTransfers: 0,
          samples: 20,
        ),
      );
      expect(direct.every((j) => j['transfers'] == 0), isTrue);
      expect(
        engine.search(
          const SearchQuery(origin: 'uc', destination: 'remote', samples: 20),
        ),
        isEmpty,
      );
      expect(
        engine.search(
          const SearchQuery(
            origin: 'uc',
            destination: 'tower',
            departure: 1430,
            samples: 20,
          ),
        ),
        isEmpty,
      );
    },
  );
  testWidgets(
    'search, station selection and input conditions on narrow mobile',
    (tester) async {
      tester.view.physicalSize = const Size(390, 844);
      tester.view.devicePixelRatio = 1;
      addTearDown(tester.view.resetPhysicalSize);
      addTearDown(tester.view.resetDevicePixelRatio);
      final session = AppSession();
      await tester.runAsync(session.initialize);
      expect(session.network!.observed, isTrue);
      session.repository = MemoryRepository(session.network!);
      await tester.pumpWidget(AnyPercentApp(session: session));
      await tester.pumpAndSettle();
      expect(find.text('가장 빠르게.\n놓쳐도, 괜찮게.'), findsOneWidget);
      expect(find.text('성남동'), findsOneWidget);
      expect(session.network!.routeNumbers, contains('722'));
      expect(find.text('가상 시연'), findsNothing);
      await tester.tap(find.text('울산과학대학앞'));
      await tester.pumpAndSettle();
      await tester.enterText(find.byType(TextField), '없는이름');
      await tester.pumpAndSettle();
      expect(find.textContaining('검색 결과가 없습니다'), findsOneWidget);
      await tester.enterText(find.byType(TextField), '울산과학');
      await tester.pumpAndSettle();
      await tester.tap(find.text('울산과학대학앞').last);
      await tester.pumpAndSettle();
      await tester.ensureVisible(find.text('나의 경로 만들기'));
      await tester.tap(find.text('나의 경로 만들기'));
      await tester.pumpAndSettle();
      expect(find.text('어떤 속도로\n이동할까요?'), findsOneWidget);
      expect(find.text('07:10'), findsOneWidget);
      await tester.tap(find.text('느리게 0.8m/s'));
      await tester.pumpAndSettle();
      expect(tester.takeException(), isNull);
    },
  );
  testWidgets('default search and offline recovery keep actual bus routes', (
    tester,
  ) async {
    tester.view.physicalSize = const Size(390, 844);
    tester.view.devicePixelRatio = 1;
    addTearDown(tester.view.resetPhysicalSize);
    addTearDown(tester.view.resetDevicePixelRatio);
    final session = AppSession()..mapTileProviderFactory = MemoryMapTiles.new;
    await tester.runAsync(session.initialize);
    session.repository = MemoryRepository(session.network!);
    await tester.pumpWidget(AnyPercentApp(session: session));
    await tester.pumpAndSettle();
    expect(session.network!.dataset, 'observed');
    expect(session.network!.data['routeFamilies'], 256);
    expect(session.network!.stops.length, 4953);
    expect(
      session.network!.routeNumbers,
      containsAll(['114', '124', '134', '224', '741', '722', '772']),
    );
    await tester.ensureVisible(find.text('나의 경로 만들기'));
    await tester.tap(find.text('나의 경로 만들기'));
    await tester.pumpAndSettle();
    await tester.tap(find.text('경로 비교하기'));
    await tester.pumpAndSettle();
    expect(find.text('124번'), findsWidgets);
    expect(find.text('722번'), findsWidgets);
    expect(find.text('772번'), findsWidgets);
    expect(find.text('A · 동구 연결'), findsNothing);
    await tester.runAsync(() => session.useOffline());
    expect(session.network!.observed, isTrue);
    expect(
      session.network!.routeLabel(session.network!.routes.keys.first),
      endsWith('번'),
    );
    expect(tester.takeException(), isNull);
  });
  testWidgets('details and delay simulator update actual arrival', (
    tester,
  ) async {
    final session = AppSession()
      ..mapTileProviderFactory = MemoryMapTiles.new
      ..network = network
      ..repository = MemoryRepository(network);
    const q = SearchQuery(origin: 'uc', destination: 'tower', samples: 20);
    final rows = engine.search(q);
    final j = rows.firstWhere((r) => (r['tags'] as List).contains('ANY%'));
    await tester.pumpWidget(
      MaterialApp(
        home: JourneyScreen(session: session, query: q, journey: j),
      ),
    );
    await tester.pumpAndSettle();
    expect(find.text('09:36 도착'), findsOneWidget);
    await tester.tap(find.text('버스가 늦는다면?'));
    await tester.pumpAndSettle();
    expect(find.text('환승할 수 있어요'), findsOneWidget);
    final slider = find.byKey(const Key('delay-slider'));
    tester.widget<Slider>(slider).onChanged!(3);
    await tester.pumpAndSettle();
    expect(find.text('환승을 놓쳤어요'), findsOneWidget);
    expect(find.text('09:56'), findsOneWidget);
    expect(tester.takeException(), isNull);
  });
  testWidgets('empty results render without frozen spinner', (tester) async {
    final session = AppSession()
      ..network = network
      ..repository = MemoryRepository(network);
    await tester.pumpWidget(
      MaterialApp(
        home: ResultsScreen(
          session: session,
          query: const SearchQuery(
            origin: 'uc',
            destination: 'remote',
            samples: 20,
          ),
        ),
      ),
    );
    await tester.pumpAndSettle();
    expect(find.text('연결할 수 있는 경로가 없습니다.'), findsOneWidget);
  });
  testWidgets('observed conditions use the recorded time window', (
    tester,
  ) async {
    tester.view.physicalSize = const Size(390, 844);
    tester.view.devicePixelRatio = 1;
    addTearDown(tester.view.resetPhysicalSize);
    addTearDown(tester.view.resetDevicePixelRatio);
    final observed = Network.decode(
      File('assets/data/observed_network.json').readAsStringSync(),
    );
    final session = AppSession()
      ..network = observed
      ..repository = MemoryRepository(observed);
    await tester.pumpWidget(
      MaterialApp(
        home: ConditionsScreen(
          session: session,
          origin: observed.defaultOrigin,
          destination: observed.defaultDestination,
        ),
      ),
    );
    await tester.pumpAndSettle();
    expect(find.text('07:10'), findsOneWidget);
    expect(tester.takeException(), isNull);
  });
  testWidgets('catalog-only route shows no invented arrival or delay action', (
    tester,
  ) async {
    final full = Network.decode(
      File('assets/data/observed_network.json').readAsStringSync(),
    );
    final q = SearchQuery(
      origin: full.defaultOrigin,
      destination: full.defaultDestination,
      departure: 480,
      samples: 20,
    );
    final rows = JourneyEngine(full).search(q);
    expect(rows, isNotEmpty);
    expect(rows, everyElement(containsPair('scheduleAvailable', false)));
    final session = AppSession()
      ..network = full
      ..repository = MemoryRepository(full)
      ..mapTileProviderFactory = MemoryMapTiles.new;
    await tester.pumpWidget(
      MaterialApp(
        home: JourneyScreen(session: session, query: q, journey: rows.first),
      ),
    );
    await tester.pumpAndSettle();
    expect(find.text('노선 연결 후보'), findsOneWidget);
    expect(find.text('버스가 늦는다면?'), findsNothing);
    expect(find.textContaining('시뮬레이션'), findsNothing);
    expect(tester.takeException(), isNull);
  });
  testWidgets('all-route picker finds 722 and opens its stop list', (
    tester,
  ) async {
    tester.view.physicalSize = const Size(390, 844);
    tester.view.devicePixelRatio = 1;
    addTearDown(tester.view.resetPhysicalSize);
    addTearDown(tester.view.resetDevicePixelRatio);
    final full = Network.decode(
      File('assets/data/observed_network.json').readAsStringSync(),
    );
    final session = AppSession()..repository = MemoryRepository(full);
    await tester.pumpWidget(AnyPercentApp(session: session));
    await tester.pumpAndSettle();
    final button = find.textContaining('전체 256개 노선');
    await tester.scrollUntilVisible(
      button,
      300,
      scrollable: find.byType(Scrollable).first,
    );
    await tester.tap(button);
    await tester.pumpAndSettle();
    await tester.enterText(find.byType(TextField), '722');
    await tester.pumpAndSettle();
    expect(find.text('722번'), findsWidgets);
    await tester.tap(find.text('722번').first);
    await tester.pumpAndSettle();
    expect(find.text('722번 정류장'), findsOneWidget);
    expect(full.searchStops('722번'), isNotEmpty);
    expect(
      full.searchStops('194027121').any((s) => s['id'] == '194027121'),
      isTrue,
    );
    expect(tester.takeException(), isNull);
  });
  testWidgets(
    'recovered 81 shows its partial GPS source and no arrival promise',
    (tester) async {
      tester.view.physicalSize = const Size(390, 844);
      tester.view.devicePixelRatio = 1;
      addTearDown(tester.view.resetPhysicalSize);
      addTearDown(tester.view.resetDevicePixelRatio);
      final full = Network.decode(
        File('assets/data/observed_network.json').readAsStringSync(),
      );
      const q = SearchQuery(
        origin: 'ref:31531',
        destination: 'ref:31532',
        departure: 430,
        maxWalk: 0,
        maxTransfers: 0,
        samples: 20,
      );
      final rows = JourneyEngine(full).search(q);
      expect(rows, isNotEmpty);
      expect(rows.first['arrival'], isNull);
      final session = AppSession()
        ..network = full
        ..repository = MemoryRepository(full)
        ..mapTileProviderFactory = MemoryMapTiles.new;
      await tester.pumpWidget(
        MaterialApp(
          home: JourneyScreen(session: session, query: q, journey: rows.first),
        ),
      );
      await tester.pumpAndSettle();
      expect(find.textContaining('GPS 근접 추정 구간'), findsOneWidget);
      expect(find.text('울주81번 · GPS추정'), findsWidgets);
      expect(find.text('운행시각이 없는 경로입니다'), findsOneWidget);
      expect(find.text('버스가 늦는다면?'), findsNothing);
      expect(tester.takeException(), isNull);
    },
  );
  testWidgets('sparse variant links to the existing same-number section', (
    tester,
  ) async {
    tester.view.physicalSize = const Size(390, 844);
    tester.view.devicePixelRatio = 1;
    addTearDown(tester.view.resetPhysicalSize);
    addTearDown(tester.view.resetDevicePixelRatio);
    final full = Network.decode(
      File('assets/data/observed_network.json').readAsStringSync(),
    );
    final session = AppSession()..repository = MemoryRepository(full);
    await tester.pumpWidget(AnyPercentApp(session: session));
    await tester.pumpAndSettle();
    await tester.tap(find.text('울산과학대학앞'));
    await tester.pumpAndSettle();
    await tester.tap(find.text('노선'));
    await tester.pumpAndSettle();
    await tester.enterText(find.byType(TextField), '북구13');
    await tester.pumpAndSettle();
    await tester.tap(find.text('북구13번').first);
    await tester.pumpAndSettle();
    await tester.tap(find.text('북구13번 · 다른 구간 보기'));
    await tester.pumpAndSettle();
    final related = full.routes['cat:195000135']!;
    expect(find.text(full.stops[related['stops'][0]]!['name']), findsWidgets);
    expect(tester.takeException(), isNull);
  });
}
