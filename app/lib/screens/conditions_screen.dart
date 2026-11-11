import 'package:flutter/material.dart';
import '../main.dart';
import '../models/transit.dart';
import '../theme.dart';
import 'results_screen.dart';

class ConditionsScreen extends StatefulWidget {
  final AppSession session;
  final String origin, destination;
  final Json? originPoint, destinationPoint;
  const ConditionsScreen({
    super.key,
    required this.session,
    required this.origin,
    required this.destination,
    this.originPoint,
    this.destinationPoint,
  });
  @override
  State<ConditionsScreen> createState() => _ConditionsScreenState();
}

class _ConditionsScreenState extends State<ConditionsScreen> {
  double departure = 540, speed = 1.2, walk = 500;
  int transfers = 2;
  String serviceDay = 'weekday';
  @override
  void initState() {
    super.initState();
    final now = DateTime.now();
    departure = widget.session.network!.official
        ? (now.hour * 60 + now.minute).toDouble()
        : widget.session.network!.defaultDeparture;
    serviceDay = now.weekday == 6
        ? 'saturday'
        : now.weekday == 7
        ? 'holiday'
        : 'weekday';
  }

  @override
  Widget build(BuildContext context) => AppPage(
    title: '이동 조건',
    bottom: PrimaryAction(
      '경로 비교하기',
      onPressed: () => Navigator.push(
        context,
        MaterialPageRoute(
          builder: (_) => ResultsScreen(
            session: widget.session,
            query: SearchQuery(
              origin: widget.origin,
              originPoint: widget.originPoint,
              destinationPoint: widget.destinationPoint,
              destination: widget.destination,
              dataset: widget.session.network!.dataset,
              departure: departure,
              walkingSpeed: speed,
              maxWalk: walk,
              maxTransfers: transfers,
              serviceDay: serviceDay,
            ),
          ),
        ),
      ),
    ),
    child: ListView(
      padding: const EdgeInsets.all(24),
      children: [
        if (widget.session.network!.official) ...[
          SegmentedButton<String>(
            segments: const [
              ButtonSegment(value: 'weekday', label: Text('평일')),
              ButtonSegment(value: 'saturday', label: Text('토요일')),
              ButtonSegment(value: 'holiday', label: Text('일·공휴일')),
            ],
            selected: {serviceDay},
            onSelectionChanged: (v) => setState(() => serviceDay = v.first),
          ),
          const SizedBox(height: 24),
        ],
        _label('출발 시각'),
        ListTile(
          contentPadding: EdgeInsets.zero,
          title: Text(
            clock(departure),
            style: const TextStyle(fontSize: 38, fontWeight: FontWeight.w800),
          ),
          trailing: const Icon(Icons.schedule),
          onTap: () async {
            final t = await showTimePicker(
              context: context,
              initialTime: TimeOfDay(
                hour: departure ~/ 60,
                minute: departure.toInt() % 60,
              ),
            );
            if (t != null) {
              setState(() => departure = (t.hour * 60 + t.minute).toDouble());
            }
          },
        ),
        if (!widget.session.network!.official)
          Text(
            widget.session.network!.observed
                ? '관측 범위 07:00~07:59 · 기본 07:10. 범위 밖 운행은 알 수 없습니다.'
                : '시연 추천 시간 09:00 · 운영 종료 이후에는 경로가 없을 수 있어요.',
            style: const TextStyle(fontSize: 11, color: muted),
          ),
        const SizedBox(height: 28),
        _label('보행 속도'),
        const SizedBox(height: 12),
        Wrap(
          spacing: 8,
          children: [
            for (final item in [(0.8, '느리게'), (1.2, '보통'), (1.6, '빠르게')])
              ChoiceChip(
                label: Text('${item.$2} ${item.$1}m/s'),
                selected: speed == item.$1,
                onSelected: (_) => setState(() => speed = item.$1),
                selectedColor: lime,
              ),
          ],
        ),
        const SizedBox(height: 28),
        _label('허용 보행거리  ${walk.toInt()}m'),
        Slider(
          value: walk,
          min: 0,
          max: 2000,
          divisions: 20,
          label: '${walk.toInt()}m',
          onChanged: (v) => setState(() => walk = v),
        ),
        const SizedBox(height: 20),
        _label('최대 환승'),
        const SizedBox(height: 12),
        SegmentedButton<int>(
          segments: const [
            ButtonSegment(value: 0, label: Text('직행만')),
            ButtonSegment(value: 1, label: Text('1회')),
            ButtonSegment(value: 2, label: Text('2회')),
          ],
          selected: {transfers},
          onSelectionChanged: (v) => setState(() => transfers = v.first),
        ),
      ],
    ),
  );
  Widget _label(String t) => Text(
    t,
    style: const TextStyle(fontSize: 14, fontWeight: FontWeight.w700),
  );
}
