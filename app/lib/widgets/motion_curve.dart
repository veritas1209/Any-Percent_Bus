import 'dart:math';
import 'package:latlong2/latlong.dart';
import '../models/transit.dart';

double roadDistance(LatLng a, LatLng b) {
  final x = (a.longitude - b.longitude) * 91000,
      y = (a.latitude - b.latitude) * 111000;
  return sqrt(x * x + y * y);
}

int lowerSpan(List<double> values, double value) {
  var lo = 0, hi = values.length - 1;
  while (lo < hi) {
    final mid = (lo + hi + 1) ~/ 2;
    if (values[mid] <= value) {
      lo = mid;
    } else {
      hi = mid - 1;
    }
  }
  return lo;
}

class RoadCurve {
  final List<LatLng> points;
  late final List<double> distances = () {
    final d = <double>[0];
    for (var i = 1; i < points.length; i++) {
      d.add(d.last + roadDistance(points[i - 1], points[i]));
    }
    return d;
  }();
  RoadCurve(this.points);
  double get length => distances.isEmpty ? 0 : distances.last;
  LatLng? at(double meters) {
    if (points.isEmpty) return null;
    if (points.length == 1 || length == 0) return points.first;
    final value = meters.clamp(0.0, length), i = lowerSpan(distances, value);
    if (i >= points.length - 1) return points.last;
    final span = distances[i + 1] - distances[i],
        f = span == 0 ? 0.0 : (value - distances[i]) / span;
    return LatLng(
      points[i].latitude + (points[i + 1].latitude - points[i].latitude) * f,
      points[i].longitude + (points[i + 1].longitude - points[i].longitude) * f,
    );
  }

  List<LatLng> clip(double start, double end) {
    if (points.isEmpty) return [];
    return [
      at(start)!,
      for (var i = 0; i < points.length; i++)
        if (distances[i] > start && distances[i] < end) points[i],
      at(end)!,
    ];
  }
}

class MotionCurve {
  final RoadCurve curve;
  final List<double> times, progress;
  MotionCurve(Network n, Json chunk)
    : curve = RoadCurve([
        for (final p in n.shape(chunk['shape'])?['points'] ?? [])
          LatLng(numValue(p[0]), numValue(p[1])),
      ]),
      times = [for (final s in chunk['samples']) numValue(s[0])],
      progress = [for (final s in chunk['samples']) numValue(s[1])];
  double get start => times.first;
  double get end => times.last;
  double metersAt(double time) {
    final i = lowerSpan(times, time);
    if (i >= times.length - 1) return progress.last;
    final f = ((time - times[i]) / (times[i + 1] - times[i])).clamp(0.0, 1.0);
    return progress[i] + f * (progress[i + 1] - progress[i]);
  }

  LatLng? at(double time) => curve.at(metersAt(time));
}

String geometryKey(List<Json> legs) => legs
    .map(
      (l) =>
          '${l['kind']}:${l['routeId']}:${l['from']}:${l['to']}:${l['trip']}:${l['boardIndex']}:${l['alightIndex']}:${l['depart']}:${l['arrive']}',
    )
    .join('|');
