import 'package:latlong2/latlong.dart';
import '../models/transit.dart';

class RouteMapSegment {
  final Json leg;
  final List<String> stopIds;
  final List<LatLng> points;
  RouteMapSegment(this.leg, this.stopIds, this.points);
  bool get walking => leg['kind'] == 'walk';
}

/// Only the selected boarding/alighting portion belongs to the highlighted route.
class RouteMapGeometry {
  final Network network;
  final List<Json> legs;
  late final segments = <RouteMapSegment>[
    for (final leg in legs)
      if (_ids(leg).length >= 2)
        RouteMapSegment(leg, _ids(leg), _ids(leg).map(point).toList()),
  ];
  late final stopIds = <String>{for (final s in segments) ...s.stopIds};
  late final importantStops = <String>{
    for (final l in legs) ...[l['from'] as String, l['to'] as String],
  };
  RouteMapGeometry(this.network, this.legs);

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

  /// Baseline position of each selected vehicle, interpolated between stop points.
  List<LatLng> vehicles(double minute) {
    final points = <LatLng>[];
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
          final from = point(ids[i]),
              to = point(ids[i + 1]),
              f = (minute - a) / (b - a);
          points.add(
            LatLng(
              from.latitude + (to.latitude - from.latitude) * f,
              from.longitude + (to.longitude - from.longitude) * f,
            ),
          );
          break;
        }
      }
    }
    return points;
  }
}
