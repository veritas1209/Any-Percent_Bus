import 'dart:math';
import 'package:latlong2/latlong.dart';
import '../models/transit.dart';

class RouteMapSegment {
  final Json leg;
  final List<String> stopIds;
  final List<List<LatLng>> paths;
  final String source;
  List<LatLng> get points => paths.expand((p) => p).toList();
  RouteMapSegment(this.leg, this.stopIds, this.paths, this.source);
  bool get walking => leg['kind'] == 'walk';
}

/// Only the selected boarding/alighting portion belongs to the highlighted route.
class RouteMapGeometry {
  final Network network;
  final List<Json> legs;
  late final segments = <RouteMapSegment>[
    for (final leg in legs)
      if (_ids(leg).length >= 2) _segment(leg),
  ];
  late final stopIds = <String>{for (final s in segments) ...s.stopIds};
  late final importantStops = <String>{
    for (final l in legs) ...[l['from'] as String, l['to'] as String],
  };
  RouteMapGeometry(this.network, this.legs);
  List<LatLng> get boundsPoints => [
    for (final id in stopIds) point(id),
    for (final segment in segments) ...segment.points,
  ];
  String get description => network.data['geometryVersion'] == null
      ? '정류장 연결선 · 차량은 시연시각 기준 보간'
      : segments.any((s) => s.source == 'unavailable')
      ? '일부 구간 도로 형상 없음 · 확인된 도로 구간만 표시'
      : '운행 GPS 기반 도로 보정 · 일부 구간 도로망 추정 · 시연 차량';

  List<LatLng> _points(dynamic shape) => shape is Map && shape['points'] is List
      ? [
          for (final p in shape['points'])
            LatLng(numValue(p[0]), numValue(p[1])),
        ]
      : [];

  RouteMapSegment _segment(Json leg) {
    final ids = _ids(leg);
    if (network.data['geometryVersion'] == null) {
      return RouteMapSegment(leg, ids, [ids.map(point).toList()], 'stop_links');
    }
    final shapes = <dynamic>[];
    if (leg['kind'] == 'walk') {
      for (final f in network.data['footpaths']) {
        if (f['from'] == leg['from'] && f['to'] == leg['to']) {
          shapes.add(f['shape']);
          break;
        }
      }
    } else {
      final route = network.routes[leg['routeId']]!;
      final raw = route['shapeSegments'] as List?;
      if (raw != null) {
        shapes.addAll(raw.sublist(leg['boardIndex'], leg['alightIndex']));
      }
    }
    final paths = <List<LatLng>>[];
    for (final shape in shapes) {
      final points = _points(shape);
      if (points.length < 2) continue;
      if (paths.isNotEmpty && mapDistance(paths.last.last, points.first) < 3) {
        paths.last.addAll(points);
      } else {
        paths.add(points);
      }
    }
    final source =
        shapes.isEmpty ||
            shapes.any((s) => s == null || s['source'] == 'unavailable')
        ? 'unavailable'
        : shapes.any((s) => s['source'] == 'road_estimate')
        ? 'road_estimate'
        : 'gps_road_matched';
    return RouteMapSegment(leg, ids, paths, source);
  }

  LatLng point(String id) => LatLng(
    numValue(network.stops[id]!['lat']),
    numValue(network.stops[id]!['lon']),
  );

  List<String> _ids(Json leg) {
    final ids = leg['kind'] == 'walk'
        ? <String>[leg['from'], leg['to']]
        : List<String>.from(
            network.routes[leg['routeId']]!['stops'],
          ).sublist(leg['boardIndex'], leg['alightIndex'] + 1);
    return ids.where((id) {
      final stop = network.stops[id];
      if (stop == null) return false;
      final lat = numValue(stop['lat']), lon = numValue(stop['lon']);
      return lat.isFinite &&
          lon.isFinite &&
          lat.abs() <= 85 &&
          lon.abs() <= 180;
    }).toList();
  }

  /// Baseline position of each selected vehicle along its road shape.
  List<LatLng> vehicles(double minute) {
    final positions = <LatLng>[];
    final seen = <String>{};
    for (final s in segments.where((s) => !s.walking)) {
      final leg = s.leg;
      if (!seen.add('${leg['routeId']}:${leg['trip']}')) continue;
      final route = network.routes[leg['routeId']]!;
      final ids = List<String>.from(route['stops']);
      final trip = numValue(leg['trip']);
      for (var i = leg['boardIndex'] as int; i < leg['alightIndex']; i++) {
        final a = trip + numValue(route['offsets'][i]);
        final b = trip + numValue(route['offsets'][i + 1]);
        if (b > a && a <= minute && minute < b) {
          if (network.data['geometryVersion'] != null) {
            final raw = route['shapeSegments'] as List?;
            final road = raw == null ? <LatLng>[] : _points(raw[i]);
            final position = pointAlongRoad(road, (minute - a) / (b - a));
            if (position != null) positions.add(position);
            break;
          }
          final from = point(ids[i]),
              to = point(ids[i + 1]),
              f = (minute - a) / (b - a);
          positions.add(
            LatLng(
              from.latitude + (to.latitude - from.latitude) * f,
              from.longitude + (to.longitude - from.longitude) * f,
            ),
          );
          break;
        }
      }
    }
    return positions;
  }
}

double mapDistance(LatLng a, LatLng b) => sqrt(
  pow((a.latitude - b.latitude) * 111000, 2) +
      pow((a.longitude - b.longitude) * 91000, 2),
);

LatLng? pointAlongRoad(List<LatLng> points, double fraction) {
  if (points.length < 2) return null;
  final distances = [
    for (var i = 1; i < points.length; i++)
      mapDistance(points[i - 1], points[i]),
  ];
  var remaining =
      distances.fold<double>(0, (a, b) => a + b) * fraction.clamp(0, 1);
  for (var i = 0; i < distances.length; i++) {
    if (remaining <= distances[i] || i == distances.length - 1) {
      final f = distances[i] == 0
          ? 0.0
          : (remaining / distances[i]).clamp(0.0, 1.0);
      return LatLng(
        points[i].latitude + (points[i + 1].latitude - points[i].latitude) * f,
        points[i].longitude +
            (points[i + 1].longitude - points[i].longitude) * f,
      );
    }
    remaining -= distances[i];
  }
  return points.last;
}
