import 'dart:convert';
import 'package:flutter/services.dart';
import 'package:flutter/foundation.dart';
import 'package:http/http.dart' as http;
import '../models/transit.dart';
import '../services/journey_engine.dart';
import '../services/walking_graph.dart';

List<Json> runLocal(Json payload) {
  var network = Network(Json.from(payload['network']));
  final q = SearchQuery(
    dataset: payload['dataset'] ?? 'observed',
    origin: payload['origin'],
    destination: payload['destination'],
    departure: numValue(payload['departure']),
    walkingSpeed: numValue(payload['walking_speed']),
    maxWalk: payload['max_walk'] == null ? null : numValue(payload['max_walk']),
    walkingPenalty: payload['walking_penalty'] == null
        ? null
        : numValue(payload['walking_penalty']),
    maxTransfers: payload['max_transfers'],
    delay: numValue(payload['delay']),
    samples: payload['samples'],
    seed: payload['seed'],
    originPoint: payload['origin_point'] == null
        ? null
        : Json.from(payload['origin_point']),
    destinationPoint: payload['destination_point'] == null
        ? null
        : Json.from(payload['destination_point']),
    serviceDay: payload['service_day'] ?? 'weekday',
  );
  network = network.forServiceDay(q.serviceDay);
  final graph = payload['walkGraph'] == null
      ? null
      : WalkingGraph(payload['walkGraph'] as Uint8List);
  List<Json> search(SearchQuery query, {Json? stats}) {
    var prepared = network;
    var places = <Json>[];
    if (query.originPoint != null || query.destinationPoint != null) {
      (prepared, places) = prepareLocations(
        network,
        query,
        graph!,
        stats: stats,
      );
    } else if (stats != null) {
      stats['exhausted'] = true;
    }
    final rows = JourneyEngine(prepared).search(
      SearchQuery(
        origin: query.originPoint == null ? query.origin : '@origin',
        destination: query.destinationPoint == null
            ? query.destination
            : '@destination',
        dataset: q.dataset,
        departure: q.departure,
        walkingSpeed: q.walkingSpeed,
        maxWalk: query.maxWalk,
        walkingPenalty: query.walkingPenalty,
        maxTransfers: q.maxTransfers,
        delay: q.delay,
        samples: q.samples,
        seed: q.seed,
        serviceDay: q.serviceDay,
      ),
    );
    for (final j in rows) {
      if (places.isNotEmpty) j['places'] = places;
    }
    return rows;
  }

  if (q.maxWalk != null) return search(q);
  final origin = q.originPoint ?? network.stops[q.origin],
      destination = q.destinationPoint ?? network.stops[q.destination];
  if (origin == null || destination == null) {
    throw ArgumentError('존재하지 않는 정류장입니다.');
  }
  final penalty = q.walkingPenalty ?? 1.0;
  if (origin['lat'] == null || destination['lat'] == null) {
    return search(
      q.copyWith(maxWalk: double.infinity, walkingPenalty: penalty),
    );
  }
  var radius = 2000.0;
  var fallback = <Json>[];
  while (true) {
    final stats = <String, dynamic>{};
    final limited = SearchQuery(
      origin: q.origin,
      destination: q.destination,
      dataset: q.dataset,
      departure: q.departure,
      walkingSpeed: q.walkingSpeed,
      maxWalk: radius,
      walkingPenalty: penalty,
      maxTransfers: q.maxTransfers,
      delay: q.delay,
      samples: q.samples,
      seed: q.seed,
      serviceDay: q.serviceDay,
      originPoint: origin,
      destinationPoint: destination,
    );
    final rows = search(limited, stats: stats),
        timed = rows.where((row) => row['arrival'] != null).toList();
    double nextRadius;
    if (timed.isNotEmpty) {
      final fastest =
          timed
              .map((row) => numValue(row['arrival']))
              .reduce((a, b) => a < b ? a : b) -
          q.departure;
      final recommended = timed
          .map((row) => numValue(row['recommendationScore']))
          .reduce((a, b) => a < b ? a : b);
      final sufficient =
          (fastest > recommended / (1 + penalty)
              ? fastest
              : recommended / (1 + penalty)) *
          q.walkingSpeed *
          60;
      if (radius + .01 >= sufficient) return timed;
      nextRadius = sufficient + .1;
    } else {
      if (rows.isNotEmpty) fallback = rows;
      nextRadius = radius * 2;
    }
    if (stats['exhausted'] == true) return timed.isNotEmpty ? timed : fallback;
    radius = nextRadius;
  }
}

abstract class TransitRepository {
  Future<Network> loadNetwork();
  Future<List<Json>> search(SearchQuery query);
  String get label;
  String? get placesSearchUrl => null;
}

class AssetTransitRepository extends TransitRepository {
  final String dataset;
  AssetTransitRepository({this.dataset = 'service'});
  Network? _network;
  Future<Uint8List>? _walk;
  @override
  String get label => dataset == 'service'
      ? '울산 공식 시간표 · 오프라인'
      : dataset == 'observed'
      ? 'BusTracker 운행 기록'
      : '로컬 데모';
  @override
  Future<Network> loadNetwork() async => _network ??= Network.decode(
    await rootBundle.loadString(
      dataset == 'service'
          ? 'assets/data/service_network.json'
          : dataset == 'observed'
          ? 'assets/data/observed_network.json'
          : 'assets/data/network.json',
    ),
  );
  @override
  Future<List<Json>> search(SearchQuery query) async {
    final network = await loadNetwork();
    return compute(runLocal, <String, dynamic>{
      ...query.toJson(),
      'network': network.routingData,
      if (query.maxWalk == null ||
          query.originPoint != null ||
          query.destinationPoint != null)
        'walkGraph': await (_walk ??= rootBundle
            .load('assets/data/walk_graph.bin')
            .then(
              (b) => b.buffer.asUint8List(b.offsetInBytes, b.lengthInBytes),
            )),
    });
  }
}

class ApiTransitRepository extends TransitRepository {
  Network? _network;
  final String baseUrl;
  final String dataset;
  ApiTransitRepository(String baseUrl, {this.dataset = 'service'})
    : baseUrl = baseUrl.replaceAll(RegExp(r'/+$'), '');
  @override
  String get label => dataset == 'service'
      ? '울산 공식 시간표 · 서버 연결'
      : dataset == 'observed'
      ? 'BusTracker · 백엔드 연결'
      : '백엔드 연결';
  @override
  String get placesSearchUrl => '$baseUrl/v1/places/search';
  @override
  Future<Network> loadNetwork() async {
    if (_network != null) return _network!;
    final response = await http
        .get(
          Uri.parse(
            '$baseUrl/v1/network?dataset=$dataset${dataset == 'service' ? '&compact=true' : ''}',
          ),
        )
        .timeout(const Duration(seconds: 20));
    if (response.statusCode != 200) {
      throw Exception('노선망을 불러올 수 없습니다 (${response.statusCode})');
    }
    return _network = Network.decode(utf8.decode(response.bodyBytes));
  }

  @override
  Future<List<Json>> search(SearchQuery query) async {
    final response = await http
        .post(
          Uri.parse('$baseUrl/v1/journeys/search'),
          headers: {'Content-Type': 'application/json'},
          body: jsonEncode({
            ...query.toJson(),
            if (dataset == 'service') 'include_geometry': true,
          }),
        )
        .timeout(const Duration(seconds: 20));
    if (response.statusCode != 200) {
      throw Exception('경로 검색에 실패했습니다 (${response.statusCode})');
    }
    final data = jsonDecode(response.body);
    if (data['geometry'] != null) {
      _network = (await loadNetwork()).withGeometry(
        Json.from(data['geometry']),
      );
    }
    return List<Json>.from((data['journeys'] as List).map((e) => Json.from(e)));
  }
}
