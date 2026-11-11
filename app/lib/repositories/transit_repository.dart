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
    maxWalk: numValue(payload['max_walk']),
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
  var places = <Json>[];
  if (q.originPoint != null || q.destinationPoint != null) {
    (network, places) = prepareLocations(
      network,
      q,
      WalkingGraph(payload['walkGraph'] as Uint8List),
    );
  }
  final rows = JourneyEngine(network).search(
    SearchQuery(
      origin: q.originPoint == null ? q.origin : '@origin',
      destination: q.destinationPoint == null ? q.destination : '@destination',
      dataset: q.dataset,
      departure: q.departure,
      walkingSpeed: q.walkingSpeed,
      maxWalk: q.maxWalk,
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

abstract class TransitRepository {
  Future<Network> loadNetwork();
  Future<List<Json>> search(SearchQuery query);
  String get label;
}

class AssetTransitRepository implements TransitRepository {
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
      if (query.originPoint != null || query.destinationPoint != null)
        'walkGraph': await (_walk ??= rootBundle
            .load('assets/data/walk_graph.bin')
            .then(
              (b) => b.buffer.asUint8List(b.offsetInBytes, b.lengthInBytes),
            )),
    });
  }
}

class ApiTransitRepository implements TransitRepository {
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
  Future<Network> loadNetwork() async {
    if (_network != null) return _network!;
    final response = await http
        .get(Uri.parse('$baseUrl/v1/network?dataset=$dataset'))
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
          body: jsonEncode(query.toJson()),
        )
        .timeout(const Duration(seconds: 20));
    if (response.statusCode != 200) {
      throw Exception('경로 검색에 실패했습니다 (${response.statusCode})');
    }
    final data = jsonDecode(response.body);
    return List<Json>.from((data['journeys'] as List).map((e) => Json.from(e)));
  }
}
