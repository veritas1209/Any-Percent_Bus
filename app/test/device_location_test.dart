import 'dart:async';
import 'dart:io';
import 'package:flutter/material.dart';
import 'package:flutter_map/flutter_map.dart';
import 'package:flutter_test/flutter_test.dart';
import 'package:geolocator/geolocator.dart';
import 'package:anypercent_app/main.dart';
import 'package:anypercent_app/models/transit.dart';
import 'package:anypercent_app/repositories/transit_repository.dart';
import 'package:anypercent_app/screens/conditions_screen.dart';
import 'package:anypercent_app/services/device_location.dart';
import 'package:anypercent_app/widgets/current_location_button.dart';
import 'package:anypercent_app/widgets/location_picker.dart';
import 'support/map_tiles.dart';

Position position({double lat = 35.49971, double lon = 129.41719}) => Position(
  latitude: lat,
  longitude: lon,
  timestamp: DateTime.utc(2026, 11, 10),
  accuracy: 15,
  altitude: 0,
  altitudeAccuracy: 0,
  heading: 0,
  headingAccuracy: 0,
  speed: 0,
  speedAccuracy: 0,
);

class FakePlatform extends GeolocatorPlatform {
  bool enabled = true;
  LocationPermission permission = LocationPermission.denied,
      requested = LocationPermission.whileInUse;
  int requests = 0, reads = 0;
  Object? error;
  Position value = position();
  @override
  Future<bool> isLocationServiceEnabled() async => enabled;
  @override
  Future<LocationPermission> checkPermission() async => permission;
  @override
  Future<LocationPermission> requestPermission() async {
    requests++;
    return requested;
  }

  @override
  Future<Position> getCurrentPosition({
    LocationSettings? locationSettings,
  }) async {
    reads++;
    if (error != null) throw error!;
    return value;
  }
}

class FakeLocation implements DeviceLocation {
  int calls = 0;
  Future<Json> Function() resolve = () async => {
    'id': 'device-location',
    'name': '현재 위치',
    'lat': 35.49971,
    'lon': 129.41719,
    'accuracy': 15.0,
    'address': '위치 정확도 약 15m',
    'isLocation': true,
    'isDeviceLocation': true,
  };
  @override
  Future<Json> current() {
    calls++;
    return resolve();
  }

  @override
  Future<bool> openSettings({bool service = false}) async => true;
}

class MemoryRepo implements TransitRepository {
  final Network n;
  MemoryRepo(this.n);
  @override
  String get label => '테스트 운행 기록';
  @override
  Future<Network> loadNetwork() async => n;
  @override
  Future<List<Json>> search(SearchQuery q) async => [];
}

void main() {
  TestWidgetsFlutterBinding.ensureInitialized();
  setUpAll(() async {
    await LocalPlaces.load();
  });
  test(
    'Android permission grant preserves the actual coordinate and accuracy',
    () async {
      final fake = FakePlatform();
      final p = await GeolocatorLocation(
        platform: fake,
        web: false,
        secure: true,
      ).current();
      expect(fake.requests, 1);
      expect(fake.reads, 1);
      expect(p['lat'], 35.49971);
      expect(p['lon'], 129.41719);
      expect(p['accuracy'], 15);
      expect(p['name'], '현재 위치');
    },
  );
  test('permanently denied and disabled GPS do not read position', () async {
    final fake = FakePlatform()..permission = LocationPermission.deniedForever;
    final service = GeolocatorLocation(
      platform: fake,
      web: false,
      secure: true,
    );
    await expectLater(
      service.current(),
      throwsA(
        isA<LocationFailure>().having(
          (e) => e.issue,
          'issue',
          LocationIssue.deniedForever,
        ),
      ),
    );
    fake.enabled = false;
    await expectLater(
      service.current(),
      throwsA(
        isA<LocationFailure>().having(
          (e) => e.issue,
          'issue',
          LocationIssue.disabled,
        ),
      ),
    );
    expect(fake.reads, 0);
    expect(fake.requests, 0);
  });
  test(
    'browser reads only once and classifies denial, timeout and out-of-area',
    () async {
      final fake = FakePlatform();
      final service = GeolocatorLocation(
        platform: fake,
        web: true,
        secure: true,
      );
      await service.current();
      expect(fake.requests, 0);
      expect(fake.reads, 1);
      for (final (error, issue) in [
        (PermissionDeniedException('denied'), LocationIssue.denied),
        (TimeoutException('timeout'), LocationIssue.timeout),
      ]) {
        fake.error = error;
        await expectLater(
          service.current(),
          throwsA(
            isA<LocationFailure>().having((e) => e.issue, 'issue', issue),
          ),
        );
      }
      fake.error = null;
      fake.value = position(lat: 37.5, lon: 127.0);
      await expectLater(
        service.current(),
        throwsA(
          isA<LocationFailure>().having(
            (e) => e.issue,
            'issue',
            LocationIssue.outsideArea,
          ),
        ),
      );
    },
  );
  test(
    'HTTP browser points to HTTPS without accessing device location',
    () async {
      final fake = FakePlatform();
      await expectLater(
        GeolocatorLocation(platform: fake, web: true, secure: false).current(),
        throwsA(
          isA<LocationFailure>().having(
            (e) => e.issue,
            'issue',
            LocationIssue.insecure,
          ),
        ),
      );
      expect(fake.reads, 0);
      expect(fake.requests, 0);
    },
  );

  AppSession session(FakeLocation gps) => AppSession()
    ..repository = MemoryRepo(
      Network.decode(File('assets/data/network.json').readAsStringSync()),
    )
    ..locationService = gps
    ..mapTileProviderFactory = MemoryMapTiles.new;
  void phone(WidgetTester tester) {
    tester.view.physicalSize = const Size(390, 844);
    tester.view.devicePixelRatio = 1;
    addTearDown(tester.view.resetPhysicalSize);
    addTearDown(tester.view.resetDevicePixelRatio);
  }

  testWidgets(
    'current origin is opt-in, keeps destination, and reaches the route query',
    (tester) async {
      phone(tester);
      final gps = FakeLocation(), s = session(FakeLocation());
      s.locationService = gps;
      await tester.pumpWidget(AnyPercentApp(session: s));
      await tester.pumpAndSettle();
      expect(gps.calls, 0);
      await tester.tap(find.text('현재 위치를 출발지로'));
      await tester.pumpAndSettle();
      expect(gps.calls, 1);
      expect(find.text('현재 위치'), findsOneWidget);
      expect(find.text('위치 정확도 약 15m'), findsOneWidget);
      await tester.tap(find.text('나의 경로 만들기'));
      await tester.pumpAndSettle();
      final q = tester.widget<ConditionsScreen>(find.byType(ConditionsScreen));
      expect(q.originPoint!['lat'], 35.49971);
      expect(q.originPoint!['lon'], 129.41719);
      expect(q.destination, s.network!.defaultDestination);
      expect(tester.takeException(), isNull);
    },
  );
  testWidgets(
    'pending GPS prevents duplicate requests and denial keeps the origin',
    (tester) async {
      phone(tester);
      final gps = FakeLocation();
      final pending = Completer<Json>();
      gps.resolve = () => pending.future;
      final s = session(gps);
      await tester.pumpWidget(AnyPercentApp(session: s));
      await tester.pumpAndSettle();
      final before = s.network!.stops[s.network!.defaultOrigin]!['name'];
      await tester.tap(find.byKey(const Key('use-current-origin')));
      await tester.pump();
      await tester.tap(find.byKey(const Key('use-current-origin')));
      await tester.pump();
      expect(gps.calls, 1);
      expect(find.text('위치 확인 중…'), findsOneWidget);
      pending.completeError(
        const LocationFailure(LocationIssue.denied, '위치 권한을 허용해주세요.'),
      );
      await tester.pumpAndSettle();
      expect(find.text('위치 권한을 허용해주세요.'), findsOneWidget);
      await tester.tap(find.text('확인'));
      await tester.pumpAndSettle();
      expect(find.text(before), findsOneWidget);
      expect(s.devicePosition, isNull);
      expect(tester.takeException(), isNull);
    },
  );
  testWidgets(
    'map current-location button recenters and shows a blue location dot',
    (tester) async {
      phone(tester);
      final gps = FakeLocation(), s = session(FakeLocation());
      s.locationService = gps;
      await tester.pumpWidget(AnyPercentApp(session: s));
      await tester.pumpAndSettle();
      await tester.tap(find.text('출발 지점'));
      await tester.pumpAndSettle();
      await tester.tap(find.text('지도에서 고르기'));
      await tester.pumpAndSettle();
      await tester.tap(find.byTooltip('현재 위치로 이동'));
      await tester.pumpAndSettle();
      final map = tester.widget<FlutterMap>(
        find.byKey(const Key('location-picker-map')),
      );
      expect(map.mapController!.camera.center.latitude, 35.49971);
      expect(map.mapController!.camera.center.longitude, 129.41719);
      expect(find.byType(DeviceLocationDot), findsOneWidget);
      await tester.tap(find.text('이 지점으로 정하기'));
      await tester.pumpAndSettle();
      expect(find.text('현재 위치'), findsOneWidget);
      expect(s.devicePosition!['lat'], 35.49971);
      expect(tester.takeException(), isNull);
    },
  );
}
