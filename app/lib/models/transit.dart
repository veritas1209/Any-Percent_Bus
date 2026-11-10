import 'dart:convert';

typedef Json = Map<String, dynamic>;
double numValue(dynamic x) => (x as num).toDouble();
String clock(num minutes) {
  final n = minutes.round();
  return '${(n ~/ 60).toString().padLeft(2, '0')}:${(n % 60).toString().padLeft(2, '0')}';
}

class Network {
  final Json data;
  bool get observed => data['source'] == 'replay_observed';
  String get dataset => data['dataset'] as String? ?? 'demo';
  String get defaultOrigin => data['defaultOrigin'] as String? ?? 'uc';
  String get defaultDestination =>
      data['defaultDestination'] as String? ?? 'tower';
  double get defaultDeparture =>
      (data['defaultDeparture'] as num? ?? 540).toDouble();
  late final Map<String, Json> stops = {
    for (final s in data['stops']) s['id'] as String: Json.from(s),
  };
  late final Map<String, Json> routes = {
    for (final r in data['routes']) r['id'] as String: Json.from(r),
  };
  dynamic shape(dynamic value) =>
      value is String ? ((data['shapes'] as Map?) ?? const {})[value] : value;
  late final Map<String, Set<String>> stopRouteNumbers = () {
    final index = <String, Set<String>>{};
    for (final r in routes.values) {
      for (final sid in r['stops']) {
        index.putIfAbsent(sid, () => {}).add('${r['number']}');
      }
    }
    return index;
  }();
  List<Json> searchStops(String query) {
    final q = query.trim().toLowerCase().replaceAll(' ', '');
    return stops.values
        .where(
          (s) =>
              '${s['name']}${s['direction']}${s['id']}'
                  .toLowerCase()
                  .replaceAll(' ', '')
                  .contains(q) ||
              (stopRouteNumbers[s['id']] ?? {}).any(
                (n) => '$n번'.toLowerCase().contains(q),
              ),
        )
        .toList();
  }

  List<Json> get catalogRoutes => routes.values
      .where((r) => r['scheduleSource'] == 'catalog_topology')
      .toList();
  List<String> get routeNumbers =>
      routes.values.map((r) => '${r['number']}').toSet().toList()..sort(
        (a, b) => (int.tryParse(a) ?? 0).compareTo(int.tryParse(b) ?? 0),
      );
  String routeLabel(String id) => routes[id]!['numberKnown'] == false
      ? '노선 ID ${routes[id]!['familyId']}'
      : observed
      ? '${routes[id]!['number']}번'
      : '${routes[id]!['number']} · ${routes[id]!['name']}';
  Network(this.data);
  factory Network.decode(String s) => Network(jsonDecode(s));
}

class SearchQuery {
  final String dataset;
  final String origin, destination;
  final double departure, walkingSpeed, maxWalk, delay;
  final int maxTransfers, samples, seed;
  const SearchQuery({
    required this.origin,
    required this.destination,
    this.dataset = 'observed',
    this.departure = 540,
    this.walkingSpeed = 1.2,
    this.maxWalk = 500,
    this.delay = 0,
    this.maxTransfers = 2,
    this.samples = 300,
    this.seed = 42,
  });
  SearchQuery withDelay(double value) => SearchQuery(
    origin: origin,
    destination: destination,
    dataset: dataset,
    departure: departure,
    walkingSpeed: walkingSpeed,
    maxWalk: maxWalk,
    delay: value,
    maxTransfers: maxTransfers,
    samples: samples,
    seed: seed,
  );
  Json toJson() => {
    'dataset': dataset,
    'origin': origin,
    'destination': destination,
    'departure': departure,
    'walking_speed': walkingSpeed,
    'max_walk': maxWalk,
    'delay': delay,
    'max_transfers': maxTransfers,
    'samples': samples,
    'seed': seed,
  };
}
