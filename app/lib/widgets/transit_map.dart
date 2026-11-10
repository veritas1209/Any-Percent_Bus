import 'dart:convert';
import 'dart:math';
import 'package:flutter/foundation.dart';
import 'package:flutter/material.dart';
import 'package:flutter_map/flutter_map.dart';
import 'package:latlong2/latlong.dart';
import 'package:url_launcher/url_launcher.dart';
import '../models/transit.dart';
import '../theme.dart';
import 'route_map_geometry.dart';
import 'transit_diagram.dart';

typedef MapTileProviderFactory = TileProvider Function();

class TransitMap extends StatefulWidget {
  final Network network;
  final List<Json> legs;
  final double minute;
  final MapTileProviderFactory? tileProviderFactory;
  const TransitMap({
    super.key,
    required this.network,
    required this.legs,
    this.minute = 540,
    this.tileProviderFactory,
  });
  @override
  State<TransitMap> createState() => _TransitMapState();
}

class _TransitMapState extends State<TransitMap> {
  bool diagram = false;
  int retry = 0;
  @override
  Widget build(BuildContext context) => Column(
    crossAxisAlignment: CrossAxisAlignment.start,
    children: [
      Row(
        children: [
          const Expanded(child: Eyebrow('ULSAN / JOURNEY MAP')),
          TextButton(
            onPressed: () => setState(() => diagram = !diagram),
            child: Text(diagram ? '지도 보기' : '개략도 보기'),
          ),
          IconButton(
            tooltip: '전체 화면 지도',
            onPressed: () => Navigator.push(
              context,
              MaterialPageRoute(
                builder: (_) => Scaffold(
                  appBar: AppBar(
                    title: const Text('전체 경로 지도'),
                    bottom: PreferredSize(
                      preferredSize: const Size.fromHeight(24),
                      child: Padding(
                        padding: const EdgeInsets.only(bottom: 8),
                        child: Text(
                          '정류장 연결선 · 시연시각 ${clock(widget.minute)}',
                          style: const TextStyle(fontSize: 11, color: muted),
                        ),
                      ),
                    ),
                  ),
                  body: SafeArea(
                    child: _RouteMap(
                      network: widget.network,
                      legs: widget.legs,
                      minute: widget.minute,
                      tileProviderFactory: widget.tileProviderFactory,
                      onDiagram: () {
                        setState(() => diagram = true);
                        Navigator.pop(context);
                      },
                    ),
                  ),
                ),
              ),
            ),
            icon: const Icon(Icons.open_in_full, size: 19),
          ),
        ],
      ),
      ClipRRect(
        borderRadius: BorderRadius.circular(20),
        child: diagram
            ? TransitDiagram(
                network: widget.network,
                legs: widget.legs,
                minute: widget.minute,
              )
            : SizedBox(
                height: 330,
                child: _RouteMap(
                  key: ValueKey(retry),
                  network: widget.network,
                  legs: widget.legs,
                  minute: widget.minute,
                  tileProviderFactory: widget.tileProviderFactory,
                  onDiagram: () => setState(() => diagram = true),
                  onRetry: () => setState(() => retry++),
                ),
              ),
      ),
      const SizedBox(height: 8),
      const Text(
        '실제 지도 · 선은 정류장 연결 기준 · 차량은 시연시각 기준 보간',
        style: TextStyle(fontSize: 10, color: muted, height: 1.5),
      ),
    ],
  );
}

class _RouteMap extends StatefulWidget {
  final Network network;
  final List<Json> legs;
  final double minute;
  final MapTileProviderFactory? tileProviderFactory;
  final VoidCallback onDiagram;
  final VoidCallback? onRetry;
  const _RouteMap({
    super.key,
    required this.network,
    required this.legs,
    required this.minute,
    required this.onDiagram,
    this.onRetry,
    this.tileProviderFactory,
  });
  @override
  State<_RouteMap> createState() => _RouteMapState();
}

class _RouteMapState extends State<_RouteMap> {
  final controller = MapController();
  late final TileProvider tiles =
      widget.tileProviderFactory?.call() ??
      NetworkTileProvider(
        cachingProvider: kIsWeb
            ? null
            : BuiltInMapCachingProvider.getOrCreateInstance(
                maxCacheSize: 50_000_000,
              ),
      );
  bool failed = false, failureQueued = false, ready = false;
  @override
  void dispose() {
    controller.dispose();
    super.dispose();
  }

  CameraFit fit(RouteMapGeometry geometry) {
    final points = geometry.stopIds.map(geometry.point).toList();
    final south = points.map((p) => p.latitude).reduce(min),
        north = points.map((p) => p.latitude).reduce(max);
    final west = points.map((p) => p.longitude).reduce(min),
        east = points.map((p) => p.longitude).reduce(max);
    return CameraFit.bounds(
      bounds: LatLngBounds(
        LatLng(south - .0005, west - .0005),
        LatLng(north + .0005, east + .0005),
      ),
      padding: const EdgeInsets.fromLTRB(38, 54, 80, 46),
      maxZoom: 16,
    );
  }

  void showStop(String id) {
    final stop = widget.network.stops[id]!;
    final times = <String>[];
    for (final l in widget.legs) {
      if (l['from'] == id) {
        times.add(
          '${l['kind'] == 'walk' ? '도보 출발' : '탑승'} ${clock(l['depart'])}',
        );
      }
      if (l['to'] == id) {
        times.add(
          '${l['kind'] == 'walk' ? '도보 도착' : '하차'} ${clock(l['arrive'])}',
        );
      }
    }
    showModalBottomSheet(
      context: context,
      showDragHandle: true,
      builder: (_) => SafeArea(
        child: Padding(
          padding: const EdgeInsets.fromLTRB(24, 0, 24, 28),
          child: Column(
            mainAxisSize: MainAxisSize.min,
            crossAxisAlignment: CrossAxisAlignment.start,
            children: [
              Text(
                stop['name'],
                style: const TextStyle(
                  fontSize: 24,
                  fontWeight: FontWeight.w800,
                ),
              ),
              const SizedBox(height: 8),
              Text(
                stop['direction'] ?? '정류장 $id',
                style: const TextStyle(color: muted),
              ),
              if (times.isNotEmpty) ...[
                const SizedBox(height: 18),
                Text(
                  times.join(' · '),
                  style: const TextStyle(fontWeight: FontWeight.w700),
                ),
              ],
              const SizedBox(height: 10),
              Text(
                '정류장 ID $id',
                style: const TextStyle(fontSize: 11, color: muted),
              ),
            ],
          ),
        ),
      ),
    );
  }

  @override
  Widget build(BuildContext context) {
    final geometry = RouteMapGeometry(widget.network, widget.legs);
    if (geometry.stopIds.isEmpty) {
      return const ColoredBox(
        color: paper,
        child: Center(child: Text('표시할 경로가 없습니다.')),
      );
    }
    final start = widget.legs.first['from'], end = widget.legs.last['to'];
    int priority(String id) => id == start || id == end
        ? 2
        : geometry.importantStops.contains(id)
        ? 1
        : 0;
    final markerIds = geometry.stopIds.toList()
      ..sort((a, b) => priority(a).compareTo(priority(b)));
    return Semantics(
      label: '실제 지도 위 이동 경로. 확대·축소와 정류장 선택 가능.',
      child: Stack(
        children: [
          FlutterMap(
            key: const Key('journey-street-map'),
            mapController: controller,
            options: MapOptions(
              initialCenter: geometry.point(geometry.stopIds.first),
              initialZoom: 12,
              initialCameraFit: fit(geometry),
              minZoom: 7,
              maxZoom: 19,
              backgroundColor: paper,
              interactionOptions: const InteractionOptions(
                flags: InteractiveFlag.all & ~InteractiveFlag.rotate,
              ),
              onMapReady: () {
                if (mounted) setState(() => ready = true);
              },
            ),
            children: [
              TileLayer(
                urlTemplate: const String.fromEnvironment(
                  'MAP_TILE_URL',
                  defaultValue:
                      'https://tile.openstreetmap.org/{z}/{x}/{y}.png',
                ),
                userAgentPackageName: 'kr.ac.uc.anypercent_app',
                tileProvider: tiles,
                maxNativeZoom: 19,
                panBuffer: 0,
                keepBuffer: 1,
                retinaMode: false,
                tileDisplay: const TileDisplay.instantaneous(),
                errorImage: MemoryImage(
                  base64Decode(
                    'iVBORw0KGgoAAAANSUhEUgAAAAEAAAABCAYAAAAfFcSJAAAAC0lEQVR4nGNgAAIAAAUAAXpeqz8AAAAASUVORK5CYII=',
                  ),
                ),
                errorTileCallback: (_, _, _) {
                  if (!mounted || failed || failureQueued) return;
                  failureQueued = true;
                  WidgetsBinding.instance.addPostFrameCallback((_) {
                    if (mounted) {
                      setState(() {
                        failed = true;
                        failureQueued = false;
                      });
                    }
                  });
                },
              ),
              PolylineLayer(
                polylines: [
                  for (final s in geometry.segments)
                    Polyline(
                      points: s.points,
                      strokeWidth: s.walking ? 4 : 5,
                      color: s.walking
                          ? blue
                          : Color(
                              int.parse(
                                (widget.network.routes[s
                                                .leg['routeId']]!['color']
                                            as String? ??
                                        '#CEF75F')
                                    .replaceFirst('#', 'FF'),
                                radix: 16,
                              ),
                            ),
                      borderStrokeWidth: s.walking ? 1.5 : 2,
                      borderColor: s.walking
                          ? Colors.white
                          : ink.withValues(alpha: .8),
                      pattern: s.walking
                          ? StrokePattern.dashed(segments: [6, 5])
                          : const StrokePattern.solid(),
                    ),
                ],
              ),
              MarkerLayer(
                markers: [
                  for (final id in markerIds)
                    Marker(
                      point: geometry.point(id),
                      width: geometry.importantStops.contains(id) ? 38 : 18,
                      height: geometry.importantStops.contains(id) ? 38 : 18,
                      child: Tooltip(
                        message: widget.network.stops[id]!['name'],
                        child: Semantics(
                          button: true,
                          label: '정류장 정보: ${widget.network.stops[id]!['name']}',
                          child: GestureDetector(
                            onTap: () => showStop(id),
                            child: Container(
                              decoration: BoxDecoration(
                                shape: BoxShape.circle,
                                color: id == end
                                    ? blue
                                    : (geometry.importantStops.contains(id)
                                          ? ink
                                          : Colors.white),
                                border: Border.all(
                                  color: Colors.white,
                                  width: 2,
                                ),
                                boxShadow: const [
                                  BoxShadow(
                                    color: Color(0x33000000),
                                    blurRadius: 5,
                                  ),
                                ],
                              ),
                              child: Center(
                                child: id == start || id == end
                                    ? Text(
                                        id == start ? 'A' : 'B',
                                        style: const TextStyle(
                                          color: Colors.white,
                                          fontWeight: FontWeight.w900,
                                          fontSize: 15,
                                        ),
                                      )
                                    : geometry.importantStops.contains(id)
                                    ? const Icon(
                                        Icons.sync_alt,
                                        size: 16,
                                        color: lime,
                                      )
                                    : const Icon(
                                        Icons.circle,
                                        size: 7,
                                        color: ink,
                                      ),
                              ),
                            ),
                          ),
                        ),
                      ),
                    ),
                  for (final point in geometry.vehicles(widget.minute))
                    Marker(
                      point: point,
                      width: 28,
                      height: 28,
                      child: Semantics(
                        label: '시연 버스 위치',
                        child: Container(
                          decoration: BoxDecoration(
                            color: blue,
                            shape: BoxShape.circle,
                            border: Border.all(color: Colors.white, width: 3),
                          ),
                          child: const Icon(
                            Icons.directions_bus,
                            color: Colors.white,
                            size: 14,
                          ),
                        ),
                      ),
                    ),
                ],
              ),
            ],
          ),
          Positioned(
            right: 10,
            top: 10,
            child: Material(
              color: Colors.white,
              elevation: 2,
              borderRadius: BorderRadius.circular(12),
              child: Column(
                mainAxisSize: MainAxisSize.min,
                children: [
                  IconButton(
                    tooltip: '전체 경로 맞추기',
                    onPressed: ready
                        ? () => controller.fitCamera(fit(geometry))
                        : null,
                    icon: const Icon(Icons.center_focus_strong, size: 20),
                  ),
                  IconButton(
                    tooltip: '지도 확대',
                    onPressed: ready
                        ? () => controller.move(
                            controller.camera.center,
                            min(19, controller.camera.zoom + 1),
                          )
                        : null,
                    icon: const Icon(Icons.add, size: 20),
                  ),
                  IconButton(
                    tooltip: '지도 축소',
                    onPressed: ready
                        ? () => controller.move(
                            controller.camera.center,
                            max(7, controller.camera.zoom - 1),
                          )
                        : null,
                    icon: const Icon(Icons.remove, size: 20),
                  ),
                ],
              ),
            ),
          ),
          if (failed)
            Positioned(
              left: 10,
              top: 10,
              right: 66,
              child: Material(
                color: Colors.white,
                elevation: 2,
                borderRadius: BorderRadius.circular(10),
                child: Padding(
                  padding: const EdgeInsets.all(10),
                  child: Column(
                    crossAxisAlignment: CrossAxisAlignment.start,
                    mainAxisSize: MainAxisSize.min,
                    children: [
                      const Text(
                        '지도 연결을 확인해주세요.',
                        style: TextStyle(
                          fontSize: 12,
                          fontWeight: FontWeight.w700,
                        ),
                      ),
                      Wrap(
                        children: [
                          TextButton(
                            onPressed: widget.onDiagram,
                            child: const Text('개략도로 보기'),
                          ),
                          if (widget.onRetry != null)
                            TextButton(
                              onPressed: widget.onRetry,
                              child: const Text('재시도'),
                            ),
                        ],
                      ),
                    ],
                  ),
                ),
              ),
            ),
          Positioned(
            right: 0,
            bottom: 0,
            child: Material(
              color: Colors.white.withValues(alpha: .94),
              child: InkWell(
                onTap: () => launchUrl(
                  Uri.parse('https://www.openstreetmap.org/copyright'),
                  mode: LaunchMode.externalApplication,
                ),
                child: const Padding(
                  padding: EdgeInsets.symmetric(horizontal: 6, vertical: 4),
                  child: Text(
                    '© OpenStreetMap contributors',
                    style: TextStyle(fontSize: 10, color: ink),
                  ),
                ),
              ),
            ),
          ),
        ],
      ),
    );
  }
}
