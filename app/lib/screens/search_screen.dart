import 'package:flutter/material.dart';
import '../main.dart';
import '../models/transit.dart';
import '../theme.dart';
import 'conditions_screen.dart';

class SearchScreen extends StatefulWidget {
  final AppSession? session;
  const SearchScreen({super.key, this.session});
  @override
  State<SearchScreen> createState() => _SearchScreenState();
}

class _SearchScreenState extends State<SearchScreen> {
  late final session = widget.session ?? AppSession();
  String origin = 'uc', destination = 'tower';
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

  void alignStops() {
    origin = session.network!.defaultOrigin;
    destination = session.network!.defaultDestination;
  }

  Future<void> select(bool from) async {
    final picked = await showModalBottomSheet<String>(
      context: context,
      isScrollControlled: true,
      backgroundColor: paper,
      builder: (context) =>
          _StopPicker(session.network!, from ? '출발 정류장' : '도착 정류장'),
    );
    if (picked != null && mounted) {
      setState(() {
        if (from) {
          origin = picked;
        } else {
          destination = picked;
        }
      });
    }
  }

  Future<void> settings() async {
    final controller = TextEditingController(
      text: const String.fromEnvironment(
        'API_URL',
        defaultValue: 'http://100.119.23.4:8001',
      ),
    );
    String? problem;
    String dataset = session.network!.dataset;
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
                const Text(
                  '경로 계산은 오프라인으로 가능합니다. 실제 지도는 인터넷 연결이 필요하며, 백엔드 주소는 아래에서 설정합니다.',
                ),
                const SizedBox(height: 16),
                SegmentedButton<String>(
                  segments: const [
                    ButtonSegment(value: 'demo', label: Text('가상 시연')),
                    ButtonSegment(value: 'observed', label: Text('관측 리플레이')),
                  ],
                  selected: {dataset},
                  onSelectionChanged: connecting
                      ? null
                      : (value) => local(() => dataset = value.first),
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
                              if (mounted) setState(alignStops);
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
                          await session.useDemo(
                            dataset: dataset,
                            accept: () => context.mounted,
                          );
                          if (context.mounted) {
                            Navigator.pop(context);
                            if (mounted) setState(alignStops);
                          }
                        },
                  child: const Text('선택한 데이터를 오프라인으로 사용'),
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
                const SizedBox(height: 32),
                const Eyebrow('TRANSIT, BEYOND THE TRANSFER.'),
                const SizedBox(height: 12),
                const Text(
                  '가장 빠르게.\n놓쳐도, 괜찮게.',
                  style: TextStyle(
                    fontSize: 38,
                    height: 1.23,
                    fontWeight: FontWeight.w900,
                    letterSpacing: -1.8,
                  ),
                ),
                const SizedBox(height: 18),
                const Text(
                  '버스가 3분 늦으면 어떻게 될까요?\n환승의 다음까지 계산하는 나의 이동 플랜.',
                  style: TextStyle(color: muted, height: 1.7),
                ),
                const SizedBox(height: 30),
                Container(
                  decoration: BoxDecoration(
                    color: ink,
                    borderRadius: BorderRadius.circular(22),
                  ),
                  padding: const EdgeInsets.all(22),
                  child: Column(
                    children: [
                      _stopTile(
                        '출발',
                        n.stops[origin]!,
                        () => select(true),
                        lime,
                      ),
                      Row(
                        children: [
                          const Expanded(child: Divider(color: Colors.white24)),
                          IconButton(
                            onPressed: () => setState(() {
                              final t = origin;
                              origin = destination;
                              destination = t;
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
                        '도착',
                        n.stops[destination]!,
                        () => select(false),
                        const Color(0xFF7CB8FF),
                      ),
                    ],
                  ),
                ),
                const SizedBox(height: 20),
                PrimaryAction(
                  '나의 경로 만들기',
                  onPressed: origin == destination
                      ? null
                      : () => Navigator.push(
                          context,
                          MaterialPageRoute(
                            builder: (_) => ConditionsScreen(
                              session: session,
                              origin: origin,
                              destination: destination,
                            ),
                          ),
                        ),
                ),
                if (origin == destination)
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
                Text(
                  n.observed
                      ? '2025.12.31 07시대 GPS 통과기록 · 83개 운행 구간\n정차시각은 근사치, 지연과 보행거리는 가상·추정입니다.'
                      : '운행시각과 지연은 시뮬레이션 데이터입니다.\n실제 버스 이용 안내로 사용할 수 없습니다.',
                  style: const TextStyle(
                    fontSize: 11,
                    color: muted,
                    height: 1.6,
                  ),
                ),
                const SizedBox(height: 24),
                const Divider(),
                const SizedBox(height: 8),
                const Eyebrow('01 / SEARCH  →  02 / PLAN  →  03 / GO'),
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
    label: '$label 정류장 선택',
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
                    stop['direction'],
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
  const _StopPicker(this.network, this.title);
  @override
  State<_StopPicker> createState() => _StopPickerState();
}

class _StopPickerState extends State<_StopPicker> {
  String query = '';
  @override
  Widget build(BuildContext context) {
    final rows = widget.network.stops.values
        .where((s) => (s['name'] + s['direction']).toString().contains(query))
        .toList();
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
              TextField(
                autofocus: true,
                onChanged: (v) => setState(() => query = v),
                decoration: const InputDecoration(
                  hintText: '정류장 이름 또는 방면 검색',
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
                          contentPadding: EdgeInsets.zero,
                          title: Text(rows[i]['name']),
                          subtitle: Text(rows[i]['direction']),
                          trailing: const Icon(Icons.north_east, size: 18),
                          onTap: () => Navigator.pop(context, rows[i]['id']),
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
