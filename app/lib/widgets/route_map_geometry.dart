import 'dart:math';
import 'package:latlong2/latlong.dart';
import '../models/transit.dart';
import 'motion_curve.dart';

class RouteMapSegment {
  final Json leg;
  final List<String> stopIds;
  final List<List<LatLng>> paths;
  final String source;
  List<LatLng> get points => paths.expand((p) => p).toList();
  RouteMapSegment(this.leg, this.stopIds, this.paths, this.source);
  bool get walking => leg['kind'] == 'walk';
}

class RouteMapVehicle {
  final LatLng point;
  final Json route;
  RouteMapVehicle(this.point, this.route);
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
  late final Map<String, List<MotionCurve>> motions = {
    for (final leg in legs)
      if (leg['kind'] == 'ride')
        leg['routeId'] as String: [
          for (final chunk
              in network.routes[leg['routeId']]!['traceChunks'] ?? [])
            MotionCurve(network, Json.from(chunk)),
        ],
  };
  late final Map<String, LatLng> markerPoints = () {
    final points = <String, LatLng>{};
    for (final id in stopIds) {
      points[id] = point(id);
    }
    for (final leg in legs.where((l) => l['kind'] == 'ride')) {
      final route = network.routes[leg['routeId']]!;
      if ((route['departures'] as List).isEmpty ||
          (motions[route['id']] ?? []).isEmpty) {
        continue;
      }
      for (var i = leg['boardIndex'] as int; i <= leg['alightIndex']; i++) {
        final id = route['stops'][i] as String;
        if (importantStops.contains(id)) continue;
        final time =
            numValue(route['departures'][0]) + numValue(route['offsets'][i]);
        for (final chunk in motions[route['id']] ?? <MotionCurve>[]) {
          if (chunk.start <= time && time <= chunk.end) {
            final p = chunk.at(time);
            if (p != null) points[id] = p;
            break;
          }
        }
      }
    }
    return points;
  }();
  List<LatLng> get boundsPoints => [
    for (final id in stopIds) markerPoints[id]!,
    for (final segment in segments) ...segment.points,
  ];
  String get description =>
      legs.any((l) => l['kind'] == 'ride') &&
          legs.where((l) => l['kind'] == 'ride').every((l) => l['trip'] == null)
      ? 'BusTracker 노선 연결 · 도로망 보정·추정 · 운행시각 미확인'
      : network.data['geometryVersion'] == null
      ? '정류장 연결선 · 차량은 시연시각 기준 보간'
      : segments.any((s) => s.source == 'unavailable')
      ? '일부 구간 도로 형상 없음 · 확인된 도로 구간만 표시'
      : network.observed
      ? 'BusTracker 기록 GPS · 도로 보정·추정 · 기록시각 기준 차량 보간'
      : '운행 GPS 기반 도로 보정 · 일부 구간 도로망 추정 · 시연 차량';

  List<LatLng> _points(dynamic value) {
    final shape = network.shape(value);
    return shape is Map && shape['points'] is List
        ? [
            for (final p in shape['points'])
              LatLng(numValue(p[0]), numValue(p[1])),
          ]
        : [];
  }

  RouteMapSegment _segment(Json leg) {
    final ids = _ids(leg);
    if (network.data['geometryVersion'] == null) {
      return RouteMapSegment(leg, ids, [ids.map(point).toList()], 'stop_links');
    }
    final shapes = <dynamic>[];
    if (leg['kind'] == 'walk') {
      if (leg['shape'] != null) shapes.add(network.shape(leg['shape']));
      for (final f in network.data['footpaths']) {
        if (shapes.isNotEmpty) break;
        if (f['from'] == leg['from'] && f['to'] == leg['to']) {
          shapes.add(network.shape(f['shape']));
          break;
        }
      }
    } else {
      final route = network.routes[leg['routeId']]!;
      if (network.data['motionVersion'] != null &&
          route['scheduleSource'] == 'replay_observed') {
        final start =
            numValue(route['departures'][0]) +
            numValue(route['offsets'][leg['boardIndex']]);
        final end =
            numValue(route['departures'][0]) +
            numValue(route['offsets'][leg['alightIndex']]);
        final paths = <List<LatLng>>[];
        var covered = 0.0;
        for (final chunk in motions[route['id']] ?? <MotionCurve>[]) {
          final a = max(start, chunk.start), b = min(end, chunk.end);
          if (b < a) continue;
          paths.add(chunk.curve.clip(chunk.metersAt(a), chunk.metersAt(b)));
          covered += b - a;
        }
        return RouteMapSegment(
          leg,
          ids,
          paths,
          covered >= end - start - .001 ? 'gps_trace_matched' : 'unavailable',
        );
      }
      final raw = route['shapeSegments'] as List?;
      if (raw != null) {
        shapes.addAll(
          raw.sublist(leg['boardIndex'], leg['alightIndex']).map(network.shape),
        );
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
  List<LatLng> vehicles(double minute) =>
      vehicleMarkers(minute).map((v) => v.point).toList();

  List<RouteMapVehicle> vehicleMarkers(double minute) {
    final positions = <RouteMapVehicle>[];
    final seen = <String>{};
    for (final s in segments.where((s) => !s.walking)) {
      final leg = s.leg;
      if (leg['trip'] == null) continue;
      if (!seen.add('${leg['routeId']}:${leg['trip']}')) continue;
      final route = network.routes[leg['routeId']]!;
      final ids = List<String>.from(route['stops']);
      final trip = numValue(leg['trip']);
      final shift = leg['depart'] == null
          ? 0.0
          : numValue(leg['depart']) -
                (trip + numValue(route['offsets'][leg['boardIndex']]));
      if (network.data['motionVersion'] != null &&
          route['scheduleSource'] == 'replay_observed') {
        final recorded =
            minute - shift - (trip - numValue(route['departures'][0]));
        final start =
            numValue(route['departures'][0]) +
            numValue(route['offsets'][leg['boardIndex']]);
        final end =
            numValue(route['departures'][0]) +
            numValue(route['offsets'][leg['alightIndex']]);
        if (recorded < start || recorded >= end) continue;
        for (final chunk in motions[route['id']] ?? <MotionCurve>[]) {
          if (chunk.start <= recorded && recorded <= chunk.end) {
            final p = chunk.at(recorded);
            if (p != null) positions.add(RouteMapVehicle(p, route));
            break;
          }
        }
        continue;
      }
      for (var i = leg['boardIndex'] as int; i < leg['alightIndex']; i++) {
        final a = trip + numValue(route['offsets'][i]) + shift;
        final b = trip + numValue(route['offsets'][i + 1]) + shift;
        if (b > a && a <= minute && minute < b) {
          if (network.data['geometryVersion'] != null) {
            final raw = route['shapeSegments'] as List?;
            final road = raw == null ? <LatLng>[] : _points(raw[i]);
            final position = pointAlongRoad(road, (minute - a) / (b - a));
            if (position != null) {
              positions.add(RouteMapVehicle(position, route));
            }
            break;
          }
          final from = point(ids[i]),
              to = point(ids[i + 1]),
              f = (minute - a) / (b - a);
          positions.add(
            RouteMapVehicle(
              LatLng(
                from.latitude + (to.latitude - from.latitude) * f,
                from.longitude + (to.longitude - from.longitude) * f,
              ),
              route,
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
