import 'dart:convert';
import 'package:flutter/services.dart';
import 'package:flutter/foundation.dart';
import 'package:http/http.dart' as http;
import '../models/transit.dart';
import '../services/journey_engine.dart';

List<Json> runLocal(Json payload) =>
    JourneyEngine(Network(Json.from(payload['network']))).search(
      SearchQuery(
        origin: payload['origin'],
        destination: payload['destination'],
        departure: numValue(payload['departure']),
        walkingSpeed: numValue(payload['walking_speed']),
        maxWalk: numValue(payload['max_walk']),
        maxTransfers: payload['max_transfers'],
        delay: numValue(payload['delay']),
        samples: payload['samples'],
        seed: payload['seed'],
      ),
    );

abstract class TransitRepository {
  Future<Network> loadNetwork();
  Future<List<Json>> search(SearchQuery query);
  String get label;
}

class AssetTransitRepository implements TransitRepository {
  final String dataset;
  AssetTransitRepository({this.dataset = 'observed'});
  Network? _network;
  @override
  String get label => dataset == 'observed' ? 'BusTracker 운행 기록' : '로컬 데모';
  @override
  Future<Network> loadNetwork() async => _network ??= Network.decode(
    await rootBundle.loadString(
      dataset == 'observed'
          ? 'assets/data/observed_network.json'
          : 'assets/data/network.json',
    ),
  );
  @override
  Future<List<Json>> search(SearchQuery query) async {
    final network = await loadNetwork();
    return compute(runLocal, <String, dynamic>{
      ...query.toJson(),
      'network': network.data,
    });
  }
}

class ApiTransitRepository implements TransitRepository {
  final String baseUrl;
  final String dataset;
  ApiTransitRepository(String baseUrl, {this.dataset = 'observed'})
    : baseUrl = baseUrl.replaceAll(RegExp(r'/+$'), '');
  @override
  String get label => dataset == 'observed' ? 'BusTracker · 백엔드 연결' : '백엔드 연결';
  @override
  Future<Network> loadNetwork() async {
    final response = await http
        .get(Uri.parse('$baseUrl/v1/network?dataset=$dataset'))
        .timeout(const Duration(seconds: 20));
    if (response.statusCode != 200) {
      throw Exception('노선망을 불러올 수 없습니다 (${response.statusCode})');
    }
    return Network.decode(utf8.decode(response.bodyBytes));
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
