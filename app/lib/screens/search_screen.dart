import 'package:flutter/material.dart';
import '../main.dart';
import '../models/transit.dart';
import '../theme.dart';
import 'conditions_screen.dart';
import '../widgets/location_picker.dart';
import '../widgets/current_location_button.dart';
import '../services/device_location.dart';

class SearchScreen extends StatefulWidget {
  final AppSession? session;
  const SearchScreen({super.key, this.session});
  @override
  State<SearchScreen> createState() => _SearchScreenState();
}

class _SearchScreenState extends State<SearchScreen> {
  late final session = widget.session ?? AppSession();
  String origin = 'uc', destination = 'tower';
  Json? originPoint, destinationPoint;
  bool get samePoint => originPoint != null && destinationPoint != null
      ? (numValue(originPoint!['lat']) - numValue(destinationPoint!['lat']))
                    .abs() <
                .000001 &&
            (numValue(originPoint!['lon']) - numValue(destinationPoint!['lon']))
                    .abs() <
                .000001
      : origin == destination;
  String? error;
  bool loading = true;
  @override
  void initState() {
    super.initState();
    load();
  }

  Future<void> load() async {
    try {
      await session.initialize();
      if (mounted) {
        setState(() {
          alignStops();
          error = null;
          loading = false;
        });
      }
    } catch (e) {
      if (mounted) {
        setState(() {
          error = '$e';
          loading = false;
        });
      }
    }
  }

  void alignStops({bool preserve = false}) {
    if (preserve && originPoint != null && destinationPoint != null) return;
    origin = session.network!.defaultOrigin;
    destination = session.network!.defaultDestination;
    originPoint = {
      ...session.network!.stops[origin]!,
      'direction': '장소·주소 또는 지도에서 선택',
      'isLocation': true,
    };
    destinationPoint = {
      ...session.network!.stops[destination]!,
      'direction': '장소·주소 또는 지도에서 선택',
      'isLocation': true,
    };
  }

  Future<void> select(bool from, {bool routesFirst = false}) async {
    if (!routesFirst) {
      final point = await showModalBottomSheet<Json>(
        context: context,
        isScrollControlled: true,
        backgroundColor: paper,
        builder: (context) => LocationPicker(
          network: session.network!,
          title: from ? '출발 지점' : '도착 지점',
          initial: (from ? originPoint : destinationPoint)!,
          tileProviderFactory: session.mapTileProviderFactory,
          locationService: session.locationService,
          devicePosition: session.devicePosition,
          onDeviceLocated: (point) => session.devicePosition = point,
          placesSearchUrl: session.repository.placesSearchUrl,
          advancedBuilder: (routes, picked, back) => _StopPicker(
            session.network!,
            from ? '출발 정류장' : '도착 정류장',
            routesFirst: routes,
            onPicked: picked,
            onPlaces: back,
          ),
        ),
      );
      if (point != null && mounted) {
        setState(() {
          if (from) {
            originPoint = point;
            origin = point['id'] ?? '@origin';
          } else {
            destinationPoint = point;
            destination = point['id'] ?? '@destination';
          }
        });
      }
      return;
    }
    final picked = await showModalBottomSheet<String>(
      context: context,
      isScrollControlled: true,
      backgroundColor: paper,
      builder: (context) => _StopPicker(
        session.network!,
        from ? '출발 정류장' : '도착 정류장',
        routesFirst: routesFirst,
      ),
    );
    if (picked != null && mounted) {
      setState(() {
        if (from) {
          origin = picked;
          originPoint = {
            ...session.network!.stops[picked]!,
            'isLocation': true,
          };
        } else {
          destination = picked;
          destinationPoint = {
            ...session.network!.stops[picked]!,
            'isLocation': true,
          };
        }
      });
    }
  }

  Future<void> settings() async {
    final controller = TextEditingController(text: defaultApiUrl);
    String? problem;
    String dataset = session.network!.official
        ? 'service'
        : session.network!.dataset;
    bool connecting = false;
    await showModalBottomSheet(
      context: context,
      isScrollControlled: true,
      builder: (context) => StatefulBuilder(
        builder: (context, local) => Padding(
          padding: EdgeInsets.fromLTRB(
            24,
            28,
            24,
            MediaQuery.viewInsetsOf(context).bottom + 28,
          ),
          child: SingleChildScrollView(
            child: Column(
              mainAxisSize: MainAxisSize.min,
              crossAxisAlignment: CrossAxisAlignment.start,
              children: [
                const Text(
                  '데이터 연결',
                  style: TextStyle(fontSize: 24, fontWeight: FontWeight.w800),
                ),
                const SizedBox(height: 12),
                SegmentedButton<String>(
                  segments: const [
                    ButtonSegment(value: 'service', label: Text('공식 시간표')),
                    ButtonSegment(value: 'observed', label: Text('GPS 기록')),
                  ],
                  selected: {dataset == 'demo' ? 'observed' : dataset},
                  onSelectionChanged: connecting
                      ? null
                      : (v) => local(() => dataset = v.first),
                ),
                const SizedBox(height: 16),
                TextField(
                  controller: controller,
                  keyboardType: TextInputType.url,
                  decoration: const InputDecoration(labelText: 'Any% 백엔드 주소'),
                ),
                if (problem != null)
                  Padding(
                    padding: const EdgeInsets.all(8),
                    child: Text(
                      problem!,
                      style: const TextStyle(color: Colors.red),
                    ),
                  ),
                const SizedBox(height: 16),
                PrimaryAction(
                  connecting ? '연결 중…' : '백엔드에 연결',
                  onPressed: connecting
                      ? null
                      : () async {
                          local(() {
                            connecting = true;
                            problem = null;
                          });
                          try {
                            await session.connect(
                              controller.text.trim(),
                              dataset: dataset,
                              accept: () => context.mounted,
                            );
                            if (context.mounted) {
                              Navigator.pop(context);
                              if (mounted) {
                                setState(() => alignStops(preserve: true));
                              }
                            }
                          } catch (e) {
                            if (context.mounted) {
                              local(() {
                                connecting = false;
                                problem = '연결할 수 없습니다. 서버 주소와 실행 상태를 확인해주세요.';
                              });
                            }
                          }
                        },
                ),
                TextButton(
                  onPressed: connecting
                      ? null
                      : () async {
                          await session.useOffline(
                            dataset: dataset,
                            accept: () => context.mounted,
                          );
                          if (context.mounted) {
                            Navigator.pop(context);
                            if (mounted) {
                              setState(() => alignStops(preserve: true));
                            }
                          }
                        },
                  child: const Text('오프라인으로 사용'),
                ),
              ],
            ),
          ),
        ),
      ),
    );
    controller.dispose();
  }

  @override
  Widget build(BuildContext context) {
    if (loading) {
      return const Scaffold(body: Center(child: CircularProgressIndicator()));
    }
    if (error != null) {
      return Scaffold(
        body: Center(
          child: Column(
            mainAxisSize: MainAxisSize.min,
            children: [
              const Text('데이터를 불러오지 못했습니다.'),
              TextButton(onPressed: load, child: const Text('다시 시도')),
            ],
          ),
        ),
      );
    }
    final n = session.network!;
    return Scaffold(
      body: SafeArea(
        child: Center(
          child: ConstrainedBox(
            constraints: const BoxConstraints(maxWidth: 680),
            child: ListView(
              padding: const EdgeInsets.all(24),
              children: [
                Row(
                  mainAxisAlignment: MainAxisAlignment.spaceBetween,
                  children: [
                    const Text(
                      'Any%',
                      style: TextStyle(
                        fontSize: 30,
                        fontWeight: FontWeight.w900,
                        letterSpacing: -2,
                      ),
                    ),
                    IconButton(
                      onPressed: settings,
                      tooltip: '데이터 연결 설정',
                      icon: const Icon(Icons.tune_rounded),
                    ),
                  ],
                ),
                const SizedBox(height: 24),
                Container(
                  decoration: BoxDecoration(
                    color: ink,
                    borderRadius: BorderRadius.circular(22),
                  ),
                  padding: const EdgeInsets.all(22),
                  child: Column(
                    children: [
                      _stopTile(
                        '출발 지점',
                        originPoint!,
                        () => select(true),
                        lime,
                      ),
                      Align(
                        alignment: Alignment.centerRight,
                        child: CurrentLocationButton(
                          key: const Key('use-current-origin'),
                          service: session.locationService,
                          color: lime,
                          label: '현재 위치를 출발지로',
                          onLocated: (point) => setState(() {
                            session.devicePosition = point;
                            originPoint = point;
                            origin = point['id'];
                          }),
                        ),
                      ),
                      Row(
                        children: [
                          const Expanded(child: Divider(color: Colors.white24)),
                          IconButton(
                            onPressed: () => setState(() {
                              final t = origin;
                              origin = destination;
                              destination = t;
                              final p = originPoint;
                              originPoint = destinationPoint;
                              destinationPoint = p;
                            }),
                            tooltip: '출발·도착 교환',
                            icon: const Icon(
                              Icons.swap_vert,
                              color: Colors.white70,
                            ),
                          ),
                          const Expanded(child: Divider(color: Colors.white24)),
                        ],
                      ),
                      _stopTile(
                        '도착 지점',
                        destinationPoint!,
                        () => select(false),
                        const Color(0xFF7CB8FF),
                      ),
                    ],
                  ),
                ),
                const SizedBox(height: 20),
                PrimaryAction(
                  '나의 경로 만들기',
                  onPressed: samePoint
                      ? null
                      : () => Navigator.push(
                          context,
                          MaterialPageRoute(
                            builder: (_) => ConditionsScreen(
                              session: session,
                              origin: origin,
                              destination: destination,
                              originPoint: originPoint,
                              destinationPoint: destinationPoint,
                            ),
                          ),
                        ),
                ),
                if (samePoint)
                  const Padding(
                    padding: EdgeInsets.only(top: 8),
                    child: Text(
                      '출발지와 도착지를 다르게 선택해주세요.',
                      style: TextStyle(color: Colors.red),
                    ),
                  ),
                const SizedBox(height: 30),
                Row(
                  children: [
                    Container(
                      width: 7,
                      height: 7,
                      decoration: const BoxDecoration(
                        shape: BoxShape.circle,
                        color: blue,
                      ),
                    ),
                    const SizedBox(width: 7),
                    Text(
                      '${session.repository.label} · ${n.data['routeFamilies'] ?? n.routes.length}개 노선',
                      style: const TextStyle(fontSize: 11, color: muted),
                    ),
                  ],
                ),
                const SizedBox(height: 8),
                if (n.realRoutes) ...[
                  Wrap(
                    spacing: 6,
                    runSpacing: 6,
                    children: [
                      for (final number in n.routeNumbers.take(8))
                        Chip(
                          label: Text('$number번'),
                          visualDensity: VisualDensity.compact,
                        ),
                    ],
                  ),
                  TextButton(
                    onPressed: () => select(true, routesFirst: true),
                    child: Text(
                      '전체 ${n.data['routeFamilies']}개 노선 · ${n.stops.length}개 정류장 검색',
                    ),
                  ),
                  const SizedBox(height: 8),
                ],
                Text(
                  n.official
                      ? '울산교통관리센터 · ${n.data['retrievedDate']}'
                      : n.observed
                      ? '2025.12.31 07:00~07:59 · ${n.data['observedRuns'] ?? n.routes.length}개 기록 구간\n전체 노선·정류장을 검색합니다. 시각 자료가 없으면 노선 연결 후보로 안내합니다.\n통과시각은 근사치, 지연은 가상, 보행은 도로망 추정입니다.'
                      : '운행시각과 지연은 시뮬레이션 데이터입니다.\n실제 버스 이용 안내로 사용할 수 없습니다.',
                  style: const TextStyle(
                    fontSize: 11,
                    color: muted,
                    height: 1.6,
                  ),
                ),
              ],
            ),
          ),
        ),
      ),
    );
  }

  Widget _stopTile(
    String label,
    Json stop,
    VoidCallback tap,
    Color accent,
  ) => Semantics(
    button: true,
    label: '$label 선택',
    child: InkWell(
      onTap: tap,
      borderRadius: BorderRadius.circular(12),
      child: Padding(
        padding: const EdgeInsets.symmetric(vertical: 8),
        child: Row(
          children: [
            Container(
              width: 8,
              height: 8,
              decoration: BoxDecoration(shape: BoxShape.circle, color: accent),
            ),
            const SizedBox(width: 14),
            Expanded(
              child: Column(
                crossAxisAlignment: CrossAxisAlignment.start,
                children: [
                  Text(
                    label,
                    style: const TextStyle(color: Colors.white60, fontSize: 11),
                  ),
                  const SizedBox(height: 6),
                  Text(
                    stop['name'],
                    style: const TextStyle(
                      color: Colors.white,
                      fontSize: 21,
                      fontWeight: FontWeight.w700,
                    ),
                  ),
                  const SizedBox(height: 3),
                  Text(
                    stop['address'] ?? stop['direction'] ?? '선택한 지점',
                    style: const TextStyle(color: Colors.white54, fontSize: 10),
                  ),
                ],
              ),
            ),
            const Icon(Icons.search, color: Colors.white70),
          ],
        ),
      ),
    ),
  );
}

class _StopPicker extends StatefulWidget {
  final Network network;
  final String title;
  final bool routesFirst;
  final ValueChanged<String>? onPicked;
  final VoidCallback? onPlaces;
  const _StopPicker(
    this.network,
    this.title, {
    this.routesFirst = false,
    this.onPicked,
    this.onPlaces,
  });
  @override
  State<_StopPicker> createState() => _StopPickerState();
}

class _StopPickerState extends State<_StopPicker> {
  String query = '';
  late bool routeMode = widget.routesFirst;
  Json? selectedRoute;
  final controller = TextEditingController();
  @override
  void dispose() {
    controller.dispose();
    super.dispose();
  }

  @override
  Widget build(BuildContext context) {
    final n = widget.network;
    final matching = routeMode ? <Json>[] : n.searchStops(query);
    final matchingIds = matching.map((s) => s['id']).toSet();
    final rows = routeMode
        ? n.catalogRoutes
              .where(
                (r) => '${r['number']} ${r['familyId']} ${r['name']}'
                    .toLowerCase()
                    .contains(
                      query.trim().toLowerCase().replaceFirst(
                        RegExp(r'번$'),
                        '',
                      ),
                    ),
              )
              .toList()
        : selectedRoute == null
        ? matching
        : [
            for (final sid in selectedRoute!['stops'])
              if (matchingIds.contains(sid)) n.stops[sid]!,
          ];
    return SafeArea(
      child: SizedBox(
        height: MediaQuery.sizeOf(context).height * .78,
        child: Padding(
          padding: const EdgeInsets.all(24),
          child: Column(
            crossAxisAlignment: CrossAxisAlignment.start,
            children: [
              Text(
                widget.title,
                style: Theme.of(context).textTheme.headlineMedium,
              ),
              const SizedBox(height: 20),
              if (widget.onPlaces != null)
                TextButton.icon(
                  onPressed: widget.onPlaces,
                  icon: const Icon(Icons.arrow_back, size: 16),
                  label: const Text('장소·지도 선택'),
                ),
              SegmentedButton<bool>(
                segments: const [
                  ButtonSegment(value: false, label: Text('정류장')),
                  ButtonSegment(value: true, label: Text('노선')),
                ],
                selected: {routeMode},
                onSelectionChanged: (s) => setState(() {
                  routeMode = s.first;
                  selectedRoute = null;
                  query = '';
                  controller.clear();
                }),
              ),
              const SizedBox(height: 12),
              if (selectedRoute != null)
                InputChip(
                  label: Text('${n.routeLabel(selectedRoute!['id'])} 정류장'),
                  onDeleted: () => setState(() => selectedRoute = null),
                ),
              if (selectedRoute != null &&
                  (selectedRoute!['stops'] as List).length < 2)
                const Text(
                  '원본에 연결할 정류장 자료가 부족합니다. 이 노선은 목록만 확인할 수 있습니다.',
                  style: TextStyle(fontSize: 12, color: muted),
                ),
              if (selectedRoute != null &&
                  (selectedRoute!['stops'] as List).length < 2)
                for (final related in n.relatedRoutes(selectedRoute!))
                  TextButton.icon(
                    onPressed: () => setState(() {
                      selectedRoute = related;
                      query = '';
                      controller.clear();
                    }),
                    icon: const Icon(Icons.alt_route, size: 16),
                    label: Text('${n.routeLabel(related['id'])} · 다른 구간 보기'),
                  ),
              if (selectedRoute?['routeSource'] == 'gps_proximity_inferred')
                const Text(
                  'GPS 근접으로 복구한 일부 구간입니다. 정차·탑승 가능 여부와 전체 노선은 미확인입니다.',
                  style: TextStyle(fontSize: 12, color: muted, height: 1.5),
                ),
              TextField(
                controller: controller,
                autofocus: true,
                onChanged: (v) => setState(() => query = v),
                decoration: const InputDecoration(
                  hintText: '정류장 이름·ID 또는 버스 번호 검색',
                  prefixIcon: Icon(Icons.search),
                ),
              ),
              const SizedBox(height: 16),
              Expanded(
                child: rows.isEmpty
                    ? const Center(child: Text('검색 결과가 없습니다. 다른 이름으로 검색해주세요.'))
                    : ListView.separated(
                        itemCount: rows.length,
                        separatorBuilder: (_, _) => const Divider(height: 1),
                        itemBuilder: (context, i) => ListTile(
                          leading: selectedRoute == null
                              ? null
                              : Text('${i + 1}'),
                          contentPadding: EdgeInsets.zero,
                          title: Text(
                            routeMode
                                ? n.routeLabel(rows[i]['id'])
                                : rows[i]['name'],
                          ),
                          subtitle: Text(
                            routeMode && n.official
                                ? '${rows[i]['name']} · ${(rows[i]['stops'] as List).length}개 정류장'
                                : routeMode
                                ? (rows[i]['routeSource'] ==
                                          'gps_proximity_inferred'
                                      ? '${(rows[i]['stops'] as List).length}개 정류장 · GPS 근접 추정 · 부분 구간'
                                      : '${(rows[i]['stops'] as List).length}개 정류장 지점 · 시각 자료는 GPS 관측 범위만 제공')
                                : rows[i]['direction'],
                          ),
                          trailing: const Icon(Icons.north_east, size: 18),
                          onTap: () {
                            if (routeMode) {
                              setState(() {
                                selectedRoute = rows[i];
                                routeMode = false;
                                query = '';
                                controller.clear();
                              });
                            } else {
                              if (widget.onPicked != null) {
                                widget.onPicked!(rows[i]['id']);
                              } else {
                                Navigator.pop(context, rows[i]['id']);
                              }
                            }
                          },
                        ),
                      ),
              ),
            ],
          ),
        ),
      ),
    );
  }
}
