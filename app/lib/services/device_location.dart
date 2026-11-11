import 'dart:async';
import 'package:flutter/foundation.dart';
import 'package:geolocator/geolocator.dart';
import '../models/transit.dart';

const secureWebUrl = String.fromEnvironment(
  'SECURE_WEB_URL',
  defaultValue: 'https://hajin-desktop.tailfb939b.ts.net:10000',
);

String get defaultApiUrl => kIsWeb && Uri.base.scheme == 'https'
    ? Uri.base.origin
    : const String.fromEnvironment('API_URL', defaultValue: secureWebUrl);

enum LocationIssue {
  denied,
  deniedForever,
  disabled,
  timeout,
  unavailable,
  outsideArea,
  insecure,
}

class LocationFailure implements Exception {
  final LocationIssue issue;
  final String message;
  const LocationFailure(this.issue, this.message);
}

abstract class DeviceLocation {
  Future<Json> current();
  Future<bool> openSettings({bool service = false});
}

class GeolocatorLocation implements DeviceLocation {
  final GeolocatorPlatform? platform;
  final bool web, secure;
  Position? _recent;
  Future<Json>? _pending;
  GeolocatorLocation({this.platform, bool? web, bool? secure})
    : web = web ?? kIsWeb,
      secure =
          secure ??
          (!kIsWeb ||
              Uri.base.scheme == 'https' ||
              const ['localhost', '127.0.0.1', '::1'].contains(Uri.base.host));
  GeolocatorPlatform get api => platform ?? GeolocatorPlatform.instance;

  @override
  Future<Json> current() =>
      _pending ??= _current().whenComplete(() => _pending = null);

  Future<Json> _current() async {
    try {
      return await _read().timeout(const Duration(seconds: 35));
    } on LocationFailure {
      rethrow;
    } on PermissionDeniedException {
      throw const LocationFailure(
        LocationIssue.denied,
        '위치 권한이 필요합니다. 브라우저나 앱의 위치 권한을 허용한 뒤 다시 눌러주세요.',
      );
    } on LocationServiceDisabledException {
      throw const LocationFailure(
        LocationIssue.disabled,
        '기기의 위치 기능이 꺼져 있습니다. 위치 기능을 켠 뒤 다시 눌러주세요.',
      );
    } on TimeoutException {
      throw const LocationFailure(
        LocationIssue.timeout,
        '현재 위치 확인에 시간이 걸리고 있습니다. 창가나 야외에서 다시 시도하거나 지도에서 지점을 골라주세요.',
      );
    } catch (_) {
      throw const LocationFailure(
        LocationIssue.unavailable,
        '현재 위치를 확인하지 못했습니다. 위치 권한과 기기 설정을 확인하거나 지도에서 지점을 골라주세요.',
      );
    }
  }

  Future<Json> _read() async {
    if (web && !secure) {
      throw const LocationFailure(
        LocationIssue.insecure,
        '웹에서 현재 위치를 사용하려면 HTTPS 앱을 열어주세요. Android 앱에서도 사용할 수 있습니다.',
      );
    }
    if (!web) {
      if (!await api.isLocationServiceEnabled()) {
        throw const LocationFailure(
          LocationIssue.disabled,
          '기기의 위치 기능이 꺼져 있습니다. 위치 기능을 켠 뒤 다시 눌러주세요.',
        );
      }
      var permission = await api.checkPermission();
      if (permission == LocationPermission.denied ||
          permission == LocationPermission.unableToDetermine) {
        permission = await api.requestPermission();
      }
      if (permission == LocationPermission.deniedForever) {
        throw const LocationFailure(
          LocationIssue.deniedForever,
          '위치 권한이 차단되어 있습니다. 앱 설정에서 위치 권한을 허용해주세요.',
        );
      }
      if (permission != LocationPermission.whileInUse &&
          permission != LocationPermission.always) {
        throw const LocationFailure(
          LocationIssue.denied,
          '위치 권한을 허용하면 현재 위치를 출발지로 사용할 수 있습니다.',
        );
      }
    }
    // A browser prompts from getCurrentPosition itself. Calling its permission
    // request first would read GPS twice and lose the original timeout/error.
    final recent = _recent;
    final age = recent == null
        ? null
        : DateTime.now().difference(recent.timestamp);
    final p =
        recent != null &&
            age! >= Duration.zero &&
            age <= const Duration(seconds: 30) &&
            recent.accuracy <= 100
        ? recent
        : await api.getCurrentPosition(
            locationSettings: web
                ? WebSettings(
                    accuracy: LocationAccuracy.medium,
                    maximumAge: const Duration(seconds: 30),
                    timeLimit: const Duration(seconds: 8),
                  )
                : const LocationSettings(
                    accuracy: LocationAccuracy.medium,
                    timeLimit: Duration(seconds: 8),
                  ),
          );
    if (!p.latitude.isFinite || !p.longitude.isFinite || !p.accuracy.isFinite) {
      throw const LocationFailure(
        LocationIssue.unavailable,
        '현재 위치의 좌표를 확인하지 못했습니다. 다시 시도해주세요.',
      );
    }
    if (p.latitude < 35.20 ||
        p.latitude > 35.85 ||
        p.longitude < 128.85 ||
        p.longitude > 129.60) {
      throw const LocationFailure(
        LocationIssue.outsideArea,
        '현재 위치가 울산 시연 데이터 범위 밖입니다. 울산 안의 출발 지점을 검색하거나 지도에서 골라주세요.',
      );
    }
    final accuracy = p.accuracy.clamp(0.0, double.infinity);
    _recent = p;
    return {
      'id': 'device-location',
      'name': '현재 위치',
      'lat': p.latitude,
      'lon': p.longitude,
      'accuracy': accuracy,
      'address': '위치 정확도 약 ${accuracy.ceil()}m',
      'direction': '기기에서 확인한 위치',
      'kind': '현재 위치',
      'isLocation': true,
      'isDeviceLocation': true,
      'locatedAt': p.timestamp.toUtc().toIso8601String(),
    };
  }

  @override
  Future<bool> openSettings({bool service = false}) async {
    if (web) return false;
    try {
      return await (service
          ? api.openLocationSettings()
          : api.openAppSettings());
    } catch (_) {
      return false;
    }
  }
}
