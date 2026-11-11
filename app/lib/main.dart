import 'package:flutter/material.dart';
import 'package:flutter/foundation.dart';
import 'package:flutter_localizations/flutter_localizations.dart';
import 'models/transit.dart';
import 'repositories/transit_repository.dart';
import 'screens/search_screen.dart';
import 'theme.dart';
import 'widgets/transit_map.dart';
import 'services/device_location.dart';

void main() => runApp(const AnyPercentApp());

class AnyPercentApp extends StatelessWidget {
  final AppSession? session;
  const AnyPercentApp({super.key, this.session});
  @override
  Widget build(BuildContext context) => MaterialApp(
    title: 'Any% · 환승의 다음까지',
    debugShowCheckedModeBanner: false,
    theme: appTheme(),
    locale: const Locale('ko'),
    supportedLocales: const [Locale('ko'), Locale('en')],
    localizationsDelegates: GlobalMaterialLocalizations.delegates,
    home: SearchScreen(session: session),
  );
}

class AppSession {
  DeviceLocation locationService = GeolocatorLocation();
  Json? devicePosition;
  MapTileProviderFactory? mapTileProviderFactory;
  TransitRepository repository = kIsWeb && Uri.base.scheme == 'https'
      ? ApiTransitRepository(defaultApiUrl)
      : AssetTransitRepository();
  Network? network;
  Network? journeyNetwork;
  Network get displayNetwork => journeyNetwork ?? network!;
  Future<void> initialize() async {
    try {
      network = await repository.loadNetwork();
    } catch (_) {
      if (repository is! ApiTransitRepository) rethrow;
      repository = AssetTransitRepository();
      network = await repository.loadNetwork();
    }
  }

  Future<void> connect(
    String url, {
    String dataset = 'service',
    bool Function()? accept,
  }) async {
    final candidate = ApiTransitRepository(url, dataset: dataset);
    final next = await candidate.loadNetwork();
    if (accept != null && !accept()) return;
    repository = candidate;
    network = next;
    journeyNetwork = null;
  }

  Future<void> useOffline({
    String dataset = 'service',
    bool Function()? accept,
  }) async {
    final candidate = AssetTransitRepository(dataset: dataset);
    final next = await candidate.loadNetwork();
    if (accept != null && !accept()) return;
    repository = candidate;
    network = next;
    journeyNetwork = null;
  }
}
