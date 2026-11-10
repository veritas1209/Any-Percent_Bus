import 'dart:math';
import 'package:flutter/material.dart';
import '../models/transit.dart';
import '../theme.dart';

class TransitMap extends StatelessWidget {
  final Network network;
  final List<Json> legs;
  final double minute;
  const TransitMap({
    super.key,
    required this.network,
    required this.legs,
    this.minute = 540,
  });
  @override
  Widget build(BuildContext context) => Semantics(
    label: '위경도 기준 노선 개략도. 실제 도로 지도 아님.',
    child: Container(
      height: 260,
      clipBehavior: Clip.antiAlias,
      decoration: BoxDecoration(
        color: ink,
        borderRadius: BorderRadius.circular(20),
      ),
      child: Stack(
        children: [
          Positioned.fill(
            child: CustomPaint(painter: _MapPainter(network, legs, minute)),
          ),
          const Positioned(
            left: 16,
            top: 14,
            child: Eyebrow('ULSAN / ROUTE DIAGRAM', color: Colors.white70),
          ),
          Positioned(
            left: 16,
            bottom: 12,
            child: Text(
              network.observed
                  ? 'GPS 관측 구간 · 지점 사이 보간 위치'
                  : '위경도 기반 개략도 · 가상 버스 운행',
              style: const TextStyle(color: Colors.white60, fontSize: 10),
            ),
          ),
        ],
      ),
    ),
  );
}

class _MapPainter extends CustomPainter {
  final Network network;
  final List<Json> legs;
  final double minute;
  _MapPainter(this.network, this.legs, this.minute);
  @override
  void paint(Canvas canvas, Size size) {
    final ids = <String>{};
    for (final l in legs) {
      ids.add(l['from']);
      ids.add(l['to']);
      if (l['kind'] == 'ride') {
        final r = network.routes[l['routeId']]!;
        ids.addAll(
          List<String>.from(
            r['stops'],
          ).sublist(l['boardIndex'], l['alightIndex'] + 1),
        );
      }
    }
    if (ids.isEmpty) ids.addAll(network.stops.keys.where((s) => s != 'remote'));
    final stops = ids.map((id) => network.stops[id]!).toList();
    final minLat = stops.map((s) => numValue(s['lat'])).reduce(min),
        maxLat = stops.map((s) => numValue(s['lat'])).reduce(max);
    final minLon = stops.map((s) => numValue(s['lon'])).reduce(min),
        maxLon = stops.map((s) => numValue(s['lon'])).reduce(max);
    Offset point(String id) {
      final s = network.stops[id]!;
      return Offset(
        45 +
            (numValue(s['lon']) - minLon) /
                max(.006, maxLon - minLon) *
                (size.width - 100),
        size.height -
            55 -
            (numValue(s['lat']) - minLat) /
                max(.006, maxLat - minLat) *
                (size.height - 110),
      );
    }

    final grid = Paint()
      ..color = Colors.white.withValues(alpha: .04)
      ..strokeWidth = 1;
    for (var x = 0.0; x < size.width; x += 26) {
      canvas.drawLine(Offset(x, 0), Offset(x, size.height), grid);
    }
    for (var y = 0.0; y < size.height; y += 26) {
      canvas.drawLine(Offset(0, y), Offset(size.width, y), grid);
    }
    for (final r in network.routes.values) {
      final s = List<String>.from(r['stops']);
      for (var i = 0; i < s.length - 1; i++) {
        if (ids.contains(s[i]) && ids.contains(s[i + 1])) {
          canvas.drawLine(
            point(s[i]),
            point(s[i + 1]),
            Paint()
              ..color = Colors.white12
              ..strokeWidth = 2,
          );
        }
      }
    }
    for (final l in legs) {
      final color = l['kind'] == 'walk'
          ? Colors.white54
          : Color(
              int.parse(
                (network.routes[l['routeId']]!['color'] as String).replaceFirst(
                  '#',
                  'FF',
                ),
                radix: 16,
              ),
            );
      final s = l['kind'] == 'walk'
          ? <String>[l['from'], l['to']]
          : List<String>.from(
              network.routes[l['routeId']]!['stops'],
            ).sublist(l['boardIndex'], l['alightIndex'] + 1);
      for (var i = 0; i < s.length - 1; i++) {
        canvas.drawLine(
          point(s[i]),
          point(s[i + 1]),
          Paint()
            ..color = color
            ..strokeWidth = l['kind'] == 'walk' ? 2 : 4
            ..strokeCap = StrokeCap.round,
        );
      }
    }
    final labels = <String>{
      if (legs.isNotEmpty) legs.first['from'],
      if (legs.isNotEmpty) legs.last['to'],
      for (final leg in legs) ...[leg['from'] as String, leg['to'] as String],
    };
    for (final id in ids) {
      final pos = point(id);
      canvas.drawCircle(
        pos,
        labels.contains(id) ? 5 : 3,
        Paint()..color = lime,
      );
      canvas.drawCircle(pos, 2, Paint()..color = ink);
    }
    // Reserve labels for journey endpoints and transfer stops. Greedy placement
    // with leader lines keeps nearby platforms readable on a narrow phone.
    final occupied = <Rect>[];
    for (final id in labels) {
      final pos = point(id);
      final label = TextPainter(
        text: TextSpan(
          text: network.stops[id]!['name'],
          style: const TextStyle(
            fontFamily: 'Pretendard',
            fontSize: 10,
            color: Colors.white,
            fontWeight: FontWeight.w600,
          ),
        ),
        textDirection: TextDirection.ltr,
        maxLines: 2,
        ellipsis: '…',
      )..layout(maxWidth: 100);
      Rect? chosen;
      for (final offset in [
        Offset(12, 10),
        Offset(-label.width - 12, 10),
        Offset(12, -label.height - 10),
        Offset(-label.width - 12, -label.height - 10),
        Offset(-label.width / 2, 30),
        Offset(-label.width / 2, -label.height - 30),
      ]) {
        final topLeft = Offset(
          (pos.dx + offset.dx).clamp(8, size.width - label.width - 8),
          (pos.dy + offset.dy).clamp(42, size.height - label.height - 36),
        );
        final rect = topLeft & label.size;
        if (occupied.every((other) => !other.overlaps(rect.inflate(4)))) {
          chosen = rect;
          break;
        }
      }
      if (chosen != null) {
        occupied.add(chosen.inflate(4));
        canvas.drawLine(
          pos,
          chosen.center,
          Paint()
            ..color = Colors.white30
            ..strokeWidth = 1,
        );
        canvas.drawRRect(
          RRect.fromRectAndRadius(chosen.inflate(3), const Radius.circular(3)),
          Paint()..color = ink.withValues(alpha: .9),
        );
        label.paint(canvas, chosen.topLeft);
      }
    }
    // Vehicles are interpolated along the same trip offsets as the backend.
    for (final r in network.routes.values) {
      final s = List<String>.from(r['stops']);
      for (final num trip in r['departures']) {
        for (var i = 0; i < s.length - 1; i++) {
          final a = trip + numValue(r['offsets'][i]),
              b = trip + numValue(r['offsets'][i + 1]);
          if (a <= minute &&
              minute < b &&
              ids.contains(s[i]) &&
              ids.contains(s[i + 1])) {
            final p = Offset.lerp(
              point(s[i]),
              point(s[i + 1]),
              (minute - a) / (b - a),
            )!;
            canvas.drawCircle(p, 8, Paint()..color = Colors.white);
            canvas.drawCircle(p, 4, Paint()..color = blue);
          }
        }
      }
    }
  }

  @override
  bool shouldRepaint(_MapPainter old) =>
      old.minute != minute || old.legs != legs || old.network != network;
}
