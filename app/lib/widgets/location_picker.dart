import 'dart:convert';
import 'package:flutter/foundation.dart';
import 'package:flutter/material.dart';
import 'package:flutter/services.dart';
import 'package:flutter_map/flutter_map.dart';
import 'package:latlong2/latlong.dart';
import 'package:url_launcher/url_launcher.dart';
import '../models/transit.dart';
import '../theme.dart';
import 'transit_map.dart';

typedef AdvancedLocationBuilder =
    Widget Function(
      bool routesFirst,
      ValueChanged<String> picked,
      VoidCallback back,
    );

class LocalPlaces {
  static Future<List<Json>>? _cached;
  static List<Json>? ready;
  static Future<List<Json>> load() => _cached ??= rootBundle
      .loadString('assets/data/places.json')
      .then(
        (text) => ready = [
          for (final p in jsonDecode(text)['places'])
            Json.from(p)
              ..['queryKey'] = normalize(
                '${p['name']} ${p['address']} ${p['searchText']}',
              ),
        ],
      );
  static String normalize(String text) =>
      text.toLowerCase().replaceAll(RegExp(r'\s+'), '');
  static List<Json> search(List<Json> places, String query, Json center) {
    final key = normalize(query);
    double d(Json p) {
      final y = numValue(p['lat']) - numValue(center['lat']),
          x = numValue(p['lon']) - numValue(center['lon']);
      return y * y + x * x;
    }

    final rows = places
        .where(
          (p) => key.isEmpty
              ? d(p) < .0009
              : (p['queryKey'] as String).contains(key),
        )
        .toList();
    int rank(Json p) => normalize(p['name']) == key
        ? 0
        : normalize(p['name']).startsWith(key)
        ? 1
        : 2;
    rows.sort((a, b) {
      final r = rank(a).compareTo(rank(b));
      return r != 0 ? r : d(a).compareTo(d(b));
    });
    return rows.take(35).toList();
  }
}

class LocationPicker extends StatefulWidget {
  final Network network;
  final String title;
  final Json initial;
  final AdvancedLocationBuilder advancedBuilder;
  final MapTileProviderFactory? tileProviderFactory;
  const LocationPicker({
    super.key,
    required this.network,
    required this.title,
    required this.initial,
    required this.advancedBuilder,
    this.tileProviderFactory,
  });
  @override
  State<LocationPicker> createState() => _LocationPickerState();
}

class _LocationPickerState extends State<LocationPicker> {
  final controller = TextEditingController();
  String query = '', mode = 'place';
  List<Json>? places;
  bool loadFailed = false;
  @override
  void initState() {
    super.initState();
    places = LocalPlaces.ready;
    if (places != null) {
      return;
    }
    LocalPlaces.load().then(
      (v) {
        if (mounted) setState(() => places = v);
      },
      onError: (Object _) {
        if (mounted) {
          setState(() {
            places = [];
            loadFailed = true;
          });
        }
      },
    );
  }

  @override
  void dispose() {
    controller.dispose();
    super.dispose();
  }

  void pick(Json value) => Navigator.pop(context, <String, dynamic>{
    ...value,
    'direction': value['address'] ?? value['direction'] ?? '선택한 지점',
    'isLocation': true,
  });
  @override
  Widget build(BuildContext context) {
    if (mode == 'stop' || mode == 'route') {
      return widget.advancedBuilder(
        mode == 'route',
        (id) => pick(widget.network.stops[id]!),
        () => setState(() => mode = 'place'),
      );
    }
    if (mode == 'map') {
      return _LocationMap(
        title: widget.title,
        initial: widget.initial,
        tileProviderFactory: widget.tileProviderFactory,
        back: () => setState(() => mode = 'place'),
        picked: pick,
      );
    }
    final matches = LocalPlaces.search(places ?? [], query, widget.initial);
    final stops = query.trim().isEmpty
        ? <Json>[]
        : widget.network.searchStops(query).take(15).toList();
    final rows = <Json>[
      ...matches,
      ...stops.map(
        (s) => <String, dynamic>{
          ...s,
          'kind': '정류장',
          'address': s['direction'],
        },
      ),
    ];
    return SafeArea(
      child: SizedBox(
        height: MediaQuery.sizeOf(context).height * .86,
        child: Padding(
          padding: const EdgeInsets.all(24),
          child: Column(
            crossAxisAlignment: CrossAxisAlignment.start,
            children: [
              Text(
                widget.title,
                style: Theme.of(context).textTheme.headlineMedium,
              ),
              const SizedBox(height: 16),
              TextField(
                controller: controller,
                autofocus: true,
                onChanged: (s) => setState(() => query = s),
                decoration: const InputDecoration(
                  hintText: '장소 이름 또는 도로명주소 검색',
                  prefixIcon: Icon(Icons.search),
                ),
              ),
              const SizedBox(height: 10),
              Wrap(
                spacing: 8,
                children: [
                  TextButton.icon(
                    onPressed: () => setState(() => mode = 'map'),
                    icon: const Icon(Icons.map_outlined),
                    label: const Text('지도에서 고르기'),
                  ),
                  TextButton(
                    onPressed: () => setState(() => mode = 'stop'),
                    child: const Text('정류장'),
                  ),
                  TextButton(
                    onPressed: () => setState(() => mode = 'route'),
                    child: const Text('노선'),
                  ),
                ],
              ),
              Text(
                loadFailed
                    ? '장소 목록을 불러오지 못했습니다. 지도나 정류장에서 선택해주세요.'
                    : '검색되지 않는 장소는 지도에서 지점을 골라주세요.',
                style: const TextStyle(fontSize: 11, color: muted),
              ),
              const SizedBox(height: 10),
              Expanded(
                child: places == null
                    ? const Center(child: CircularProgressIndicator())
                    : rows.isEmpty
                    ? const Center(
                        child: Text('검색 결과가 없습니다. 지도에서 지점을 선택할 수 있어요.'),
                      )
                    : ListView.separated(
                        itemCount: rows.length,
                        separatorBuilder: (_, _) => const Divider(height: 1),
                        itemBuilder: (context, i) {
                          final p = rows[i];
                          return ListTile(
                            contentPadding: EdgeInsets.zero,
                            leading: Icon(
                              p['kind'] == '정류장'
                                  ? Icons.directions_bus_outlined
                                  : Icons.place_outlined,
                              color: muted,
                            ),
                            title: Text(p['name']),
                            subtitle: Text(
                              '${p['kind'] ?? '장소'}${(p['address'] ?? '').toString().isEmpty ? '' : ' · ${p['address']}'}',
                              maxLines: 2,
                              overflow: TextOverflow.ellipsis,
                            ),
                            onTap: () => pick(p),
                          );
                        },
                      ),
              ),
              const SizedBox(height: 8),
              const Text(
                '장소·주소: © OpenStreetMap contributors',
                style: TextStyle(fontSize: 10, color: muted),
              ),
            ],
          ),
        ),
      ),
    );
  }
}

class _LocationMap extends StatefulWidget {
  final String title;
  final Json initial;
  final MapTileProviderFactory? tileProviderFactory;
  final VoidCallback back;
  final ValueChanged<Json> picked;
  const _LocationMap({
    required this.title,
    required this.initial,
    required this.back,
    required this.picked,
    this.tileProviderFactory,
  });
  @override
  State<_LocationMap> createState() => _LocationMapState();
}

class _LocationMapState extends State<_LocationMap> {
  late LatLng point = LatLng(
    numValue(widget.initial['lat']),
    numValue(widget.initial['lon']),
  );
  final name = TextEditingController(text: '지도에서 선택한 지점');
  late final tiles =
      widget.tileProviderFactory?.call() ??
      NetworkTileProvider(
        cachingProvider: kIsWeb
            ? null
            : BuiltInMapCachingProvider.getOrCreateInstance(
                maxCacheSize: 50000000,
              ),
      );
  bool failed = false;
  @override
  void dispose() {
    name.dispose();
    super.dispose();
  }

  @override
  Widget build(BuildContext context) => SafeArea(
    child: SizedBox(
      height: MediaQuery.sizeOf(context).height * .88,
      child: Padding(
        padding: const EdgeInsets.all(20),
        child: Column(
          crossAxisAlignment: CrossAxisAlignment.start,
          children: [
            Row(
              children: [
                IconButton(
                  onPressed: widget.back,
                  icon: const Icon(Icons.arrow_back),
                  tooltip: '장소 검색으로 돌아가기',
                ),
                Expanded(
                  child: Text(
                    '${widget.title} 선택',
                    style: const TextStyle(
                      fontSize: 22,
                      fontWeight: FontWeight.w800,
                    ),
                  ),
                ),
              ],
            ),
            const Text(
              '지도를 눌러 출입구나 도로 가까이에 핀을 놓아주세요.',
              style: TextStyle(fontSize: 12, color: muted),
            ),
            const SizedBox(height: 12),
            Expanded(
              child: ClipRRect(
                borderRadius: BorderRadius.circular(18),
                child: Stack(
                  children: [
                    FlutterMap(
                      key: const Key('location-picker-map'),
                      options: MapOptions(
                        initialCenter: point,
                        initialZoom: 16,
                        minZoom: 8,
                        maxZoom: 19,
                        cameraConstraint: CameraConstraint.containCenter(
                          bounds: LatLngBounds(
                            const LatLng(35.20, 128.85),
                            const LatLng(35.85, 129.60),
                          ),
                        ),
                        interactionOptions: const InteractionOptions(
                          flags: InteractiveFlag.all & ~InteractiveFlag.rotate,
                        ),
                        onTap: (_, p) {
                          if (p.latitude < 35.20 ||
                              p.latitude > 35.85 ||
                              p.longitude < 128.85 ||
                              p.longitude > 129.60) {
                            return;
                          }
                          setState(() => point = p);
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
                          panBuffer: 0,
                          keepBuffer: 1,
                          maxNativeZoom: 19,
                          errorTileCallback: (_, _, _) {
                            if (!failed) {
                              WidgetsBinding.instance.addPostFrameCallback((_) {
                                if (mounted) setState(() => failed = true);
                              });
                            }
                          },
                        ),
                        MarkerLayer(
                          markers: [
                            Marker(
                              point: point,
                              width: 44,
                              height: 50,
                              child: const Icon(
                                Icons.location_pin,
                                color: blue,
                                size: 44,
                              ),
                            ),
                          ],
                        ),
                      ],
                    ),
                    Positioned(
                      right: 2,
                      bottom: 2,
                      child: Material(
                        color: Colors.white,
                        child: InkWell(
                          onTap: () => launchUrl(
                            Uri.parse(
                              'https://www.openstreetmap.org/copyright',
                            ),
                            mode: LaunchMode.externalApplication,
                          ),
                          child: const Padding(
                            padding: EdgeInsets.all(4),
                            child: Text(
                              '© OpenStreetMap contributors',
                              style: TextStyle(fontSize: 10, color: ink),
                            ),
                          ),
                        ),
                      ),
                    ),
                    if (failed)
                      Positioned(
                        top: 10,
                        left: 10,
                        right: 10,
                        child: Material(
                          borderRadius: BorderRadius.circular(12),
                          child: Padding(
                            padding: const EdgeInsets.all(12),
                            child: TextButton(
                              onPressed: widget.back,
                              child: const Text('지도를 불러오지 못했습니다. 장소 검색으로 돌아가기'),
                            ),
                          ),
                        ),
                      ),
                  ],
                ),
              ),
            ),
            const SizedBox(height: 12),
            TextField(
              controller: name,
              decoration: const InputDecoration(labelText: '지점 이름'),
            ),
            const SizedBox(height: 12),
            PrimaryAction(
              '이 지점으로 정하기',
              onPressed: failed
                  ? null
                  : () => widget.picked({
                      'id': 'picked-map',
                      'name': name.text.trim().isEmpty
                          ? '지도에서 선택한 지점'
                          : name.text.trim(),
                      'lat': point.latitude,
                      'lon': point.longitude,
                      'address': '지도에서 선택',
                      'kind': '지도 지점',
                    }),
            ),
          ],
        ),
      ),
    ),
  );
}
