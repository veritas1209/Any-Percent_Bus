import 'package:flutter/material.dart';
import '../main.dart';
import '../models/transit.dart';
import '../theme.dart';
import '../widgets/transit_map.dart';
import 'simulation_screen.dart';

class JourneyScreen extends StatelessWidget {
  final AppSession session;
  final SearchQuery query;
  final Json journey;
  const JourneyScreen({
    super.key,
    required this.session,
    required this.query,
    required this.journey,
  });
  @override
  Widget build(BuildContext context) => AppPage(
    title: '경로와 환승',
    bottom: PrimaryAction(
      journey['scheduleAvailable'] == false
          ? '운행시각이 없는 경로입니다'
          : (journey['legs'] as List).any((l) => l['kind'] == 'ride')
          ? '버스가 늦는다면?'
          : '도보 경로입니다',
      onPressed:
          journey['scheduleAvailable'] == false ||
              !(journey['legs'] as List).any((l) => l['kind'] == 'ride')
          ? null
          : () => Navigator.push(
              context,
              MaterialPageRoute(
                builder: (_) => SimulationScreen(
                  session: session,
                  query: query,
                  journey: journey,
                ),
              ),
            ),
    ),
    child: ListView(
      padding: const EdgeInsets.all(24),
      children: [
        Eyebrow(List<String>.from(journey['tags']).join(' / ')),
        const SizedBox(height: 8),
        Text(
          journey['scheduleAvailable'] == false
              ? '노선 연결 후보'
              : '${clock(journey['arrival'])} 도착',
          style: Theme.of(context).textTheme.headlineLarge,
        ),
        const SizedBox(height: 16),
        if (session.displayNetwork.hasInferredRoute(journey['legs'])) ...[
          const Text(
            'GPS 근접 추정 구간입니다. 실제 정차·탑승 가능 여부와 전체 노선은 확인되지 않았습니다.',
            style: TextStyle(fontSize: 12, color: muted, height: 1.6),
          ),
          const SizedBox(height: 12),
        ],
        TransitMap(
          network: session.displayNetwork,
          legs: List<Json>.from(journey['legs']),
          minute:
              (journey['legs'] as List)
                  .where((l) => l['kind'] == 'ride' && l['depart'] != null)
                  .isEmpty
              ? query.departure
              : numValue(
                  (journey['legs'] as List).firstWhere(
                    (l) => l['kind'] == 'ride' && l['depart'] != null,
                  )['depart'],
                ),
          tileProviderFactory: session.mapTileProviderFactory,
          locationService: session.locationService,
          devicePosition: session.devicePosition,
          onDeviceLocated: (p) => session.devicePosition = p,
        ),
        const SizedBox(height: 28),
        const Eyebrow('TRANSFER TIMELINE'),
        const SizedBox(height: 18),
        ...timeline(session, journey['legs']),
        const SizedBox(height: 20),
        if (journey['scheduleAvailable'] != false)
          Container(
            padding: const EdgeInsets.all(18),
            decoration: BoxDecoration(
              color: lime,
              borderRadius: BorderRadius.circular(14),
            ),
            child: Text(
              '같은 여정 ${journey['sampleCount']}회 시뮬레이션\n계획한 환승 성공 추정 ${((journey['successProbability'] as num) * 100).round()}%\n출발시각과 보행속도를 바꾸면 결과도 달라집니다.',
              style: const TextStyle(fontSize: 12, height: 1.8),
            ),
          ),
        const SizedBox(height: 14),
        Text(
          journey['scheduleAvailable'] == false
              ? '기록된 시각으로 연결되지 않아 원본 노선의 정류장 순서로 찾은 후보입니다. 운행 방향·시간표 확인이 필요합니다.'
              : '${session.network!.observed ? 'GPS 통과시각 근사 · 지연 가상' : '시뮬레이션 운행'} · 30초 탑승 여유 포함 · 운행 GPS와 도로망 기반 경로입니다.',
          style: const TextStyle(fontSize: 10, color: muted),
        ),
      ],
    ),
  );
}

List<Widget> timeline(AppSession session, List<dynamic> raw) {
  final legs = List<Json>.from(raw), widgets = <Widget>[];
  double? lastArrival;
  for (final l in legs) {
    final isWalk = l['kind'] == 'walk';
    if (isWalk && numValue(l['meters']) < .5) continue;
    if (!isWalk && lastArrival != null && l['depart'] != null) {
      final margin = numValue(l['depart']) - lastArrival - .5;
      widgets.add(
        Padding(
          padding: const EdgeInsets.only(left: 45, bottom: 16),
          child: Text(
            '환승 여유 ${margin.toStringAsFixed(1)}분 · 탑승 여유 30초 제외',
            style: TextStyle(
              color: margin < 2 ? Colors.deepOrange : blue,
              fontSize: 11,
              fontWeight: FontWeight.w700,
            ),
          ),
        ),
      );
    }
    widgets.add(
      Padding(
        padding: const EdgeInsets.only(bottom: 18),
        child: Row(
          crossAxisAlignment: CrossAxisAlignment.start,
          children: [
            Container(
              width: 32,
              height: 32,
              decoration: BoxDecoration(
                color: isWalk ? Colors.white : ink,
                borderRadius: BorderRadius.circular(8),
              ),
              child: Icon(
                isWalk ? Icons.directions_walk : Icons.directions_bus,
                color: isWalk ? ink : lime,
                size: 17,
              ),
            ),
            const SizedBox(width: 13),
            Expanded(
              child: Column(
                crossAxisAlignment: CrossAxisAlignment.start,
                children: [
                  Text(
                    isWalk
                        ? '도보 ${l['meters']}m'
                        : session.displayNetwork.routeLabel(l['routeId']),
                    style: const TextStyle(fontWeight: FontWeight.w800),
                  ),
                  const SizedBox(height: 5),
                  Text(
                    '${session.displayNetwork.stops[l['from']]!['name']} → ${session.displayNetwork.stops[l['to']]!['name']}',
                    style: const TextStyle(fontSize: 12),
                  ),
                  if (l['depart'] != null)
                    Text(
                      '${clock(l['depart'])} - ${clock(l['arrive'])}',
                      style: const TextStyle(fontSize: 12, color: muted),
                    ),
                ],
              ),
            ),
          ],
        ),
      ),
    );
    lastArrival = l['arrive'] == null ? null : numValue(l['arrive']);
  }
  return widgets;
}
