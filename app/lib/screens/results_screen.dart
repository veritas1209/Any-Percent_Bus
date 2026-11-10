import 'package:flutter/material.dart';
import '../main.dart';
import '../models/transit.dart';
import '../theme.dart';
import 'journey_screen.dart';

class ResultsScreen extends StatefulWidget {
  final AppSession session;
  final SearchQuery query;
  const ResultsScreen({super.key, required this.session, required this.query});
  @override
  State<ResultsScreen> createState() => _ResultsScreenState();
}

class _ResultsScreenState extends State<ResultsScreen> {
  List<Json>? rows;
  String? error;
  bool safeFirst = false;
  @override
  void initState() {
    super.initState();
    load();
  }

  Future<void> load() async {
    setState(() {
      rows = null;
      error = null;
    });
    try {
      final r = await widget.session.repository.search(widget.query);
      if (mounted) setState(() => rows = r);
    } catch (e) {
      if (mounted) {
        setState(() => error = '서버 연결에 실패했습니다. 다시 시도하거나 로컬 데모로 검색하세요.');
      }
    }
  }

  @override
  Widget build(BuildContext context) => AppPage(
    title: '경로 비교',
    child: ListView(
      padding: const EdgeInsets.all(24),
      children: [
        const Eyebrow('A BETTER WAY TO ARRIVE.'),
        const SizedBox(height: 10),
        Text(
          '빠름과 여유,\n당신의 선택은?',
          style: Theme.of(context).textTheme.headlineLarge,
        ),
        const SizedBox(height: 16),
        Text(
          '${clock(widget.query.departure)} 출발 · 보행 ${widget.query.walkingSpeed}m/s · ${widget.query.maxTransfers}회 이내 환승',
          style: const TextStyle(color: muted, fontSize: 12),
        ),
        const SizedBox(height: 22),
        Row(
          children: [
            const Expanded(
              child: Text(
                '도착 예측 비교',
                style: TextStyle(fontWeight: FontWeight.w700),
              ),
            ),
            FilterChip(
              label: const Text('안정성 우선'),
              selected: safeFirst,
              onSelected: (v) => setState(() => safeFirst = v),
            ),
          ],
        ),
        const SizedBox(height: 12),
        if (error != null) ...[
          Text(error!),
          const SizedBox(height: 12),
          PrimaryAction('다시 시도', onPressed: load),
          TextButton(
            onPressed: () async {
              await widget.session.useDemo(dataset: widget.query.dataset);
              if (mounted) load();
            },
            child: const Text('로컬 데모로 검색'),
          ),
        ] else if (rows == null)
          const Padding(
            padding: EdgeInsets.all(50),
            child: Center(child: CircularProgressIndicator()),
          )
        else if (rows!.isEmpty) ...[
          const SizedBox(height: 30),
          const Icon(Icons.route_outlined, size: 44, color: muted),
          const SizedBox(height: 16),
          const Text('연결할 수 있는 경로가 없습니다.', textAlign: TextAlign.center),
          const SizedBox(height: 10),
          const Text(
            '출발시각, 허용 보행거리 또는 최대 환승 횟수를 바꿔보세요.',
            textAlign: TextAlign.center,
            style: TextStyle(color: muted),
          ),
        ] else
          ...displayRows().map(
            (j) => Padding(
              padding: const EdgeInsets.only(bottom: 16),
              child: JourneyCard(
                journey: j,
                session: widget.session,
                onTap: () => Navigator.push(
                  context,
                  MaterialPageRoute(
                    builder: (_) => JourneyScreen(
                      session: widget.session,
                      query: widget.query,
                      journey: j,
                    ),
                  ),
                ),
              ),
            ),
          ),
        const SizedBox(height: 12),
        Text(
          widget.session.network!.observed
              ? '관측 운행에 가상 지연을 적용했습니다. 자료 밖 후속 차량은 추정하지 않으며, 운행 구간별로 탐색합니다. 실측 환승 성공률이 아닙니다.'
              : '성공률은 입력한 지연 표본으로 계산한 시뮬레이션 추정입니다. 90백분위 도착시각은 실제 도착 보장이 아닙니다.',
          style: const TextStyle(fontSize: 11, color: muted, height: 1.7),
        ),
      ],
    ),
  );
  List<Json> displayRows() {
    final list = [...rows!];
    if (safeFirst) {
      list.sort((a, b) => (a['p90Arrival'] as num).compareTo(b['p90Arrival']));
    }
    return list;
  }
}

class JourneyCard extends StatelessWidget {
  final Json journey;
  final AppSession session;
  final VoidCallback onTap;
  const JourneyCard({
    super.key,
    required this.journey,
    required this.session,
    required this.onTap,
  });
  @override
  Widget build(BuildContext context) {
    final tags = List<String>.from(journey['tags']),
        isAny = tags.contains('ANY%');
    return Semantics(
      button: true,
      label: '${tags.join(' ')} 경로 상세 보기',
      child: Material(
        color: isAny ? ink : Colors.white,
        borderRadius: BorderRadius.circular(20),
        child: InkWell(
          onTap: onTap,
          borderRadius: BorderRadius.circular(20),
          child: Padding(
            padding: const EdgeInsets.all(22),
            child: DefaultTextStyle(
              style: TextStyle(
                color: isAny ? Colors.white : ink,
                fontFamily: 'Pretendard',
              ),
              child: Column(
                crossAxisAlignment: CrossAxisAlignment.start,
                children: [
                  Row(
                    children: [
                      Text(
                        tags.isEmpty ? 'ALTERNATIVE' : tags.join(' / '),
                        style: TextStyle(
                          color: isAny ? lime : blue,
                          fontSize: 12,
                          fontWeight: FontWeight.w900,
                          letterSpacing: 1.5,
                        ),
                      ),
                      const Spacer(),
                      Icon(
                        Icons.north_east,
                        size: 19,
                        color: isAny ? Colors.white : ink,
                      ),
                    ],
                  ),
                  const SizedBox(height: 16),
                  Row(
                    crossAxisAlignment: CrossAxisAlignment.end,
                    children: [
                      Text(
                        clock(journey['arrival']),
                        style: const TextStyle(
                          fontSize: 40,
                          fontWeight: FontWeight.w800,
                          letterSpacing: -2,
                        ),
                      ),
                      const Padding(
                        padding: EdgeInsets.only(bottom: 7, left: 7),
                        child: Text('도착 예정', style: TextStyle(fontSize: 11)),
                      ),
                    ],
                  ),
                  const SizedBox(height: 8),
                  Text(
                    '${journey['transfers']}회 환승 · 도보 ${(journey['walkingMeters'] as num).round()}m',
                    style: TextStyle(
                      fontSize: 12,
                      color: isAny ? Colors.white60 : muted,
                    ),
                  ),
                  const SizedBox(height: 18),
                  Row(
                    mainAxisAlignment: MainAxisAlignment.spaceBetween,
                    children: [
                      _metric(
                        journey['transfers'] == 0 ? '환승' : '환승 성공 추정',
                        journey['transfers'] == 0
                            ? '없음'
                            : '${((journey['successProbability'] as num) * 100).round()}%',
                      ),
                      _metric(
                        '평균 도착',
                        (journey['noServiceProbability'] as num) > 0
                            ? '추정 불가'
                            : clock(journey['expectedArrival']),
                      ),
                      _metric(
                        '90백분위',
                        (journey['noServiceProbability'] as num) > .1
                            ? '추정 불가'
                            : clock(journey['p90Arrival']),
                      ),
                    ],
                  ),
                  const SizedBox(height: 20),
                  if ((journey['noServiceProbability'] as num) > 0)
                    Padding(
                      padding: const EdgeInsets.only(bottom: 12),
                      child: Text(
                        '후속 운행 확인 불가 ${((journey['noServiceProbability'] as num) * 100).round()}% · ${session.network!.observed ? '관측 범위 초과' : '종료'} 표본 포함',
                        style: const TextStyle(fontSize: 10),
                      ),
                    ),
                  Wrap(
                    spacing: 6,
                    runSpacing: 6,
                    children: [
                      for (final l in journey['legs'])
                        Container(
                          padding: const EdgeInsets.symmetric(
                            vertical: 5,
                            horizontal: 8,
                          ),
                          decoration: BoxDecoration(
                            borderRadius: BorderRadius.circular(5),
                            color: isAny ? Colors.white12 : paper,
                          ),
                          child: Text(
                            l['kind'] == 'walk'
                                ? '도보 ${l['meters']}m'
                                : '${session.network!.routes[l['routeId']]!['number']} · ${session.network!.routes[l['routeId']]!['name']}',
                            style: const TextStyle(fontSize: 10),
                          ),
                        ),
                    ],
                  ),
                ],
              ),
            ),
          ),
        ),
      ),
    );
  }

  Widget _metric(String label, String value) => Column(
    crossAxisAlignment: CrossAxisAlignment.start,
    children: [
      Text(label, style: const TextStyle(fontSize: 10)),
      const SizedBox(height: 6),
      Text(
        value,
        style: const TextStyle(fontSize: 19, fontWeight: FontWeight.w700),
      ),
    ],
  );
}
