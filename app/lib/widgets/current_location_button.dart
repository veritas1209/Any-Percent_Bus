import 'package:flutter/foundation.dart';
import 'package:flutter/material.dart';
import 'package:url_launcher/url_launcher.dart';
import '../models/transit.dart';
import '../services/device_location.dart';
import '../theme.dart';

class CurrentLocationButton extends StatefulWidget {
  final DeviceLocation service;
  final ValueChanged<Json> onLocated;
  final Color color;
  final bool iconOnly;
  final String label;
  const CurrentLocationButton({
    super.key,
    required this.service,
    required this.onLocated,
    this.color = blue,
    this.iconOnly = false,
    this.label = '현재 위치',
  });
  @override
  State<CurrentLocationButton> createState() => _CurrentLocationButtonState();
}

class _CurrentLocationButtonState extends State<CurrentLocationButton> {
  bool busy = false;
  Future<void> locate() async {
    if (busy) return;
    setState(() => busy = true);
    try {
      final point = await widget.service.current();
      if (mounted) widget.onLocated(point);
    } on LocationFailure catch (failure) {
      if (mounted) {
        setState(() => busy = false);
        await explain(failure);
      }
    } catch (_) {
      if (mounted) {
        setState(() => busy = false);
        await explain(
          const LocationFailure(
            LocationIssue.unavailable,
            '현재 위치를 확인하지 못했습니다. 잠시 후 다시 시도해주세요.',
          ),
        );
      }
    } finally {
      if (mounted) setState(() => busy = false);
    }
  }

  Future<void> explain(LocationFailure failure) => showDialog<void>(
    context: context,
    builder: (dialog) => AlertDialog(
      title: const Text('현재 위치를 확인해주세요'),
      content: Text(failure.message),
      actions: [
        if (failure.issue == LocationIssue.insecure)
          TextButton(
            onPressed: () async {
              final opened = await launchUrl(
                Uri.parse(secureWebUrl),
                webOnlyWindowName: '_self',
              );
              if (dialog.mounted && opened) Navigator.pop(dialog);
            },
            child: const Text('HTTPS 앱 열기'),
          ),
        if (!kIsWeb &&
            (failure.issue == LocationIssue.deniedForever ||
                failure.issue == LocationIssue.disabled))
          TextButton(
            onPressed: () async {
              final opened = await widget.service.openSettings(
                service: failure.issue == LocationIssue.disabled,
              );
              if (!dialog.mounted || !mounted) return;
              if (opened) {
                Navigator.pop(dialog);
              } else {
                ScaffoldMessenger.of(context).showSnackBar(
                  const SnackBar(content: Text('기기의 설정에서 위치 권한을 확인해주세요.')),
                );
              }
            },
            child: Text(
              failure.issue == LocationIssue.disabled ? '위치 설정 열기' : '앱 설정 열기',
            ),
          ),
        TextButton(
          onPressed: () => Navigator.pop(dialog),
          child: const Text('확인'),
        ),
      ],
    ),
  );

  @override
  Widget build(BuildContext context) {
    final icon = busy
        ? SizedBox(
            width: 18,
            height: 18,
            child: CircularProgressIndicator(
              strokeWidth: 2,
              color: widget.color,
            ),
          )
        : Icon(Icons.my_location_rounded, size: 19, color: widget.color);
    if (widget.iconOnly) {
      return IconButton(
        onPressed: busy ? null : locate,
        tooltip: busy ? '위치 확인 중' : '현재 위치로 이동',
        icon: icon,
      );
    }
    return TextButton.icon(
      onPressed: busy ? null : locate,
      style: TextButton.styleFrom(foregroundColor: widget.color),
      icon: icon,
      label: Text(
        busy ? '위치 확인 중…' : widget.label,
        style: const TextStyle(fontWeight: FontWeight.w700),
      ),
    );
  }
}

class DeviceLocationDot extends StatelessWidget {
  const DeviceLocationDot({super.key});
  @override
  Widget build(BuildContext context) => Semantics(
    label: '현재 위치',
    child: Center(
      child: Container(
        width: 18,
        height: 18,
        decoration: BoxDecoration(
          color: blue,
          shape: BoxShape.circle,
          border: Border.all(color: Colors.white, width: 3),
          boxShadow: const [
            BoxShadow(
              color: Color(0x554276C7),
              blurRadius: 10,
              spreadRadius: 4,
            ),
          ],
        ),
      ),
    ),
  );
}
