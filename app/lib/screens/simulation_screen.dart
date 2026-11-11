import 'dart:async';
import 'dart:math';
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
  double delay = 0, elapsed = 0, rate = 20, _anchor = 0, _limit = 1;
  Timer? ticker;
  final stopwatch = Stopwatch();
  @override
  void dispose() {
    ticker?.cancel();
    stopwatch.stop();
    super.dispose();
  }

  void play() {
    if (ticker != null) {
      ticker!.cancel();
      stopwatch.stop();
      setState(() => ticker = null);
      return;
    }
    if (elapsed >= _limit) elapsed = 0;
    _anchor = elapsed;
    stopwatch.reset();
    stopwatch.start();
    ticker = Timer.periodic(const Duration(milliseconds: 33), (_) {
      if (!mounted) return;
      final value =
          _anchor + stopwatch.elapsedMicroseconds / 1000000 * rate / 60;
      if (value >= _limit) {
        ticker?.cancel();
        stopwatch.stop();
        ticker = null;
      }
      setState(() => elapsed = min(value, _limit));
    });
    setState(() {});
  }

  @override
  Widget build(BuildContext context) {
    final engine = JourneyEngine(widget.session.displayNetwork),
        scenario = engine.replay(widget.journey, widget.query.withDelay(delay));
    final lost = (scenario['missed'] as List).isNotEmpty,
        arrival = scenario['arrival'];
    final recordedLegs = scenario['legs'] as List;
    _limit = max(
      1,
      numValue(
            arrival ??
                (recordedLegs.isEmpty
                    ? widget.query.departure + 1
                    : recordedLegs.last['arrive']),
          ) -
          widget.query.departure,
    );
    final displayed = elapsed.clamp(0.0, _limit);
    return AppPage(
      title: '지연 시뮬레이션',
      child: ListView(
        padding: const EdgeInsets.all(24),
        children: [
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
              const Expanded(
                child: Text(
                  '버스 재생',
                  style: TextStyle(fontWeight: FontWeight.w700),
                ),
              ),
              DropdownButton<double>(
                value: rate,
                items: [
                  for (final value in [1.0, 10.0, 20.0, 60.0])
                    DropdownMenuItem(
                      value: value,
                      child: Text('${value.toInt()}×'),
                    ),
                ],
                onChanged: (value) {
                  if (ticker != null) play();
                  setState(() => rate = value ?? 20);
                },
              ),
              TextButton.icon(
                onPressed: play,
                icon: Icon(ticker == null ? Icons.play_arrow : Icons.pause),
                label: Text(ticker == null ? '재생' : '일시정지'),
              ),
            ],
          ),
          Slider(
            key: const Key('playback-clock'),
            value: displayed,
            min: 0,
            max: _limit,
            label: clockSeconds(widget.query.departure + displayed),
            onChanged: (value) {
              if (ticker != null) play();
              setState(() => elapsed = value);
            },
          ),
          TransitMap(
            network: widget.session.displayNetwork,
            legs: List<Json>.from(scenario['legs']),
            minute: widget.query.departure + displayed,
            tileProviderFactory: widget.session.mapTileProviderFactory,
            locationService: widget.session.locationService,
            devicePosition: widget.session.devicePosition,
            onDeviceLocated: (p) => widget.session.devicePosition = p,
          ),
          const SizedBox(height: 8),
          Text(
            '${clockSeconds(widget.query.departure + displayed)} · ${rate.toInt()}배속',
            style: const TextStyle(fontSize: 10, color: muted),
          ),
          const SizedBox(height: 24),
          ...timeline(widget.session, scenario['legs']),
          const SizedBox(height: 12),
        ],
      ),
    );
  }
}
