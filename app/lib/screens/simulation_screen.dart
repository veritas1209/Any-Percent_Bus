import 'dart:async';
import 'package:flutter/material.dart';
import '../main.dart';
import '../models/transit.dart';
import '../services/journey_engine.dart';
import '../theme.dart';
import '../widgets/transit_map.dart';
import 'journey_screen.dart';

class SimulationScreen extends StatefulWidget {
  final AppSession session;
  final SearchQuery query;
  final Json journey;
  const SimulationScreen({
    super.key,
    required this.session,
    required this.query,
    required this.journey,
  });
  @override
  State<SimulationScreen> createState() => _SimulationScreenState();
}

class _SimulationScreenState extends State<SimulationScreen> {
  double delay = 0, elapsed = 10;
  Timer? ticker;
  @override
  void dispose() {
    ticker?.cancel();
    super.dispose();
  }

  void play() {
    if (ticker != null) {
      ticker!.cancel();
      setState(() => ticker = null);
      return;
    }
    ticker = Timer.periodic(const Duration(milliseconds: 500), (_) {
      if (mounted) setState(() => elapsed = (elapsed + 1) % 65);
    });
    setState(() {});
  }

  @override
  Widget build(BuildContext context) {
    final engine = JourneyEngine(widget.session.network!),
        scenario = engine.replay(widget.journey, widget.query.withDelay(delay));
    final lost = (scenario['missed'] as List).isNotEmpty,
        arrival = scenario['arrival'];
    return AppPage(
      title: '지연 시뮬레이션',
      child: ListView(
        padding: const EdgeInsets.all(24),
        children: [
          const Eyebrow('WHAT IF YOUR BUS IS LATE?'),
          const SizedBox(height: 12),
          Text(
            '3분이 바꾸는\n나의 도착시간.',
            style: Theme.of(context).textTheme.headlineLarge,
          ),
          const SizedBox(height: 24),
          Row(
            children: [
              const Expanded(
                child: Text(
                  '첫 번째 버스 지연',
                  style: TextStyle(fontWeight: FontWeight.w700),
                ),
              ),
              Text(
                '+${delay.toInt()}분',
                style: const TextStyle(
                  fontSize: 26,
                  fontWeight: FontWeight.w800,
                ),
              ),
            ],
          ),
          Slider(
            key: const Key('delay-slider'),
            value: delay,
            min: 0,
            max: 15,
            divisions: 15,
            label: '+${delay.toInt()}분',
            semanticFormatterCallback: (v) => '+${v.toInt()}분',
            onChanged: (v) => setState(() => delay = v),
          ),
          Row(
            children: [
              TextButton(
                onPressed: () => setState(() => delay = 0),
                child: const Text('초기화'),
              ),
              const Spacer(),
              const Text(
                '첫 탑승 차량 이후의 지연을 재현',
                style: TextStyle(fontSize: 10, color: muted),
              ),
            ],
          ),
          const SizedBox(height: 12),
          Container(
            padding: const EdgeInsets.all(22),
            decoration: BoxDecoration(
              color: lost ? const Color(0xFFFFE2D6) : lime,
              borderRadius: BorderRadius.circular(18),
            ),
            child: Column(
              crossAxisAlignment: CrossAxisAlignment.start,
              children: [
                Text(
                  arrival == null
                      ? (widget.session.network!.observed
                            ? '후속 운행 미확인'
                            : '후속 차량 없음')
                      : lost
                      ? '환승을 놓쳤어요'
                      : '환승할 수 있어요',
                  style: const TextStyle(
                    fontSize: 20,
                    fontWeight: FontWeight.w800,
                  ),
                ),
                const SizedBox(height: 12),
                Text(
                  arrival == null
                      ? (widget.session.network!.observed
                            ? '관측 범위 밖입니다.'
                            : '오늘 운행이 종료되었습니다.')
                      : clock(arrival),
                  style: TextStyle(
                    fontSize: arrival == null ? 24 : 42,
                    fontWeight: FontWeight.w900,
                    letterSpacing: -2,
                  ),
                ),
                if (arrival != null)
                  Text(
                    '계획 대비 +${(numValue(arrival) - numValue(widget.journey['arrival'])).round()}분 · 다음 탑승 가능 차량까지 반영',
                    style: const TextStyle(fontSize: 11),
                  ),
              ],
            ),
          ),
          const SizedBox(height: 24),
          Row(
            children: [
              const Expanded(child: Eyebrow('VIRTUAL CLOCK')),
              TextButton.icon(
                onPressed: play,
                icon: Icon(ticker == null ? Icons.play_arrow : Icons.pause),
                label: Text(ticker == null ? '버스 재생' : '일시정지'),
              ),
            ],
          ),
          TransitMap(
            network: widget.session.network!,
            legs: List<Json>.from(scenario['legs']),
            minute: widget.query.departure + elapsed,
          ),
          const SizedBox(height: 8),
          Text(
            '가상시각 ${clock(widget.query.departure + elapsed)} · 파란 점은 기준 운행 궤적',
            style: const TextStyle(fontSize: 10, color: muted),
          ),
          const SizedBox(height: 24),
          ...timeline(widget.session, scenario['legs']),
          const SizedBox(height: 12),
          const Text(
            '이 화면은 선택한 경로를 유지하며 후속 차량을 다시 선택합니다. 다른 경로를 비교하려면 결과 화면으로 돌아가 조건을 변경하세요.',
            style: TextStyle(fontSize: 11, color: muted, height: 1.7),
          ),
        ],
      ),
    );
  }
}
