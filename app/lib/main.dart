import 'package:flutter/material.dart';
import 'package:flutter_localizations/flutter_localizations.dart';
import 'models/transit.dart';
import 'repositories/transit_repository.dart';
import 'screens/search_screen.dart';
import 'theme.dart';
import 'widgets/transit_map.dart';

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
  MapTileProviderFactory? mapTileProviderFactory;
  TransitRepository repository = AssetTransitRepository();
  Network? network;
  Future<void> initialize() async {
    network = await repository.loadNetwork();
  }

  Future<void> connect(
    String url, {
    String dataset = 'observed',
    bool Function()? accept,
  }) async {
    final candidate = ApiTransitRepository(url, dataset: dataset);
    final next = await candidate.loadNetwork();
    if (accept != null && !accept()) return;
    repository = candidate;
    network = next;
  }

  Future<void> useOffline({
    String dataset = 'observed',
    bool Function()? accept,
  }) async {
    final candidate = AssetTransitRepository(dataset: dataset);
    final next = await candidate.loadNetwork();
    if (accept != null && !accept()) return;
    repository = candidate;
    network = next;
  }
}
