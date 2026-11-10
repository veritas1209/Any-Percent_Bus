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
    this.dataset = 'demo',
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
