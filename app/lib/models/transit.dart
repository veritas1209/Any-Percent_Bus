import 'dart:convert';

typedef Json = Map<String, dynamic>;
double numValue(dynamic x) => (x as num).toDouble();
String clock(num minutes) {
  final n = minutes.round();
  return '${(n ~/ 60).toString().padLeft(2, '0')}:${(n % 60).toString().padLeft(2, '0')}';
}

String clockSeconds(num minutes) {
  final n = (minutes * 60).floor();
  return '${(n ~/ 3600).toString().padLeft(2, '0')}:${((n ~/ 60) % 60).toString().padLeft(2, '0')}:${(n % 60).toString().padLeft(2, '0')}';
}

class Network {
  final Json data;
  bool get observed => data['source'] == 'replay_observed';
  bool get official => data['source'] == 'official_timetable';
  bool get realRoutes => observed || official;
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
      .where((r) => official || r['scheduleSource'] == 'catalog_topology')
      .toList();
  List<String> get routeNumbers =>
      routes.values.map((r) => '${r['number']}').toSet().toList()..sort(
        (a, b) => (int.tryParse(a) ?? 0).compareTo(int.tryParse(b) ?? 0),
      );
  String routeLabel(String id) => routes[id]!['numberKnown'] == false
      ? '노선 ID ${routes[id]!['familyId']}'
      : realRoutes
      ? '${routes[id]!['number']}번${routes[id]!['routeSource'] == 'gps_proximity_inferred' ? ' · GPS추정' : ''}'
      : '${routes[id]!['number']} · ${routes[id]!['name']}';
  bool hasInferredRoute(List<dynamic> legs) => legs.any(
    (l) =>
        l['kind'] == 'ride' &&
        routes[l['routeId']]?['routeSource'] == 'gps_proximity_inferred',
  );
  List<Json> relatedRoutes(Json route) => route['numberKnown'] == false
      ? []
      : catalogRoutes
            .where(
              (r) =>
                  r['familyId'] != route['familyId'] &&
                  r['number'] == route['number'] &&
                  (r['stops'] as List).length >= 2,
            )
            .toList();
  Network(this.data);
  final Map<String, Network> _days = {};
  Network forServiceDay(String day) {
    if (!official || day == (data['serviceDay'] ?? 'weekday')) return this;
    return _days.putIfAbsent(
      day,
      () => Network({
        ...data,
        'serviceDay': day,
        'routes': [
          for (final r in data['routes'])
            {
              ...Json.from(r),
              'departures': r['departuresByDay'][day] ?? <num>[],
            },
        ],
      }),
    );
  }

  late final Json routingData = {
    for (final entry in data.entries)
      if (entry.key != 'shapes') entry.key: entry.value,
    'routes': [
      for (final r in data['routes'])
        {
          for (final entry in Json.from(r).entries)
            if (!const {
              'shapeSegments',
              'traceChunks',
              'pathPoints',
            }.contains(entry.key))
              entry.key: entry.value,
        },
    ],
  };
  Network withPlaces(List<dynamic> places) => Network({
    ...data,
    'stops': [
      for (final s in data['stops'])
        if (!(s['id'] as String).startsWith('@')) s,
      ...places,
    ],
  });
  factory Network.decode(String s) => Network(jsonDecode(s));
}

class SearchQuery {
  final String serviceDay;
  final String dataset;
  final String origin, destination;
  final double departure, walkingSpeed, maxWalk, delay;
  final int maxTransfers, samples, seed;
  final Json? originPoint, destinationPoint;
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
    this.originPoint,
    this.destinationPoint,
    this.serviceDay = 'weekday',
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
    originPoint: originPoint,
    destinationPoint: destinationPoint,
    serviceDay: serviceDay,
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
    'service_day': serviceDay,
    if (originPoint != null) 'origin_point': originPoint,
    if (destinationPoint != null) 'destination_point': destinationPoint,
  };
}
