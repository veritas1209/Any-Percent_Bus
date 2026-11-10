import 'package:flutter/material.dart';

const ink = Color(0xFF101A2C),
    paper = Color(0xFFF4F5EF),
    lime = Color(0xFFCEF75F),
    muted = Color(0xFF687387),
    blue = Color(0xFF4276C7);
ThemeData appTheme() => ThemeData(
  useMaterial3: true,
  scaffoldBackgroundColor: paper,
  colorScheme: ColorScheme.fromSeed(
    seedColor: ink,
    primary: ink,
    secondary: lime,
    surface: paper,
  ),
  fontFamily: 'Pretendard',
  appBarTheme: const AppBarTheme(
    backgroundColor: paper,
    foregroundColor: ink,
    centerTitle: false,
    elevation: 0,
  ),
  textTheme: const TextTheme(
    headlineLarge: TextStyle(
      fontSize: 38,
      fontWeight: FontWeight.w800,
      color: ink,
      letterSpacing: -1.8,
    ),
    headlineMedium: TextStyle(
      fontSize: 28,
      fontWeight: FontWeight.w800,
      color: ink,
      letterSpacing: -1,
    ),
    titleLarge: TextStyle(
      fontSize: 21,
      fontWeight: FontWeight.w700,
      color: ink,
    ),
    bodyMedium: TextStyle(fontSize: 14, color: ink, height: 1.6),
  ),
  filledButtonTheme: FilledButtonThemeData(
    style: FilledButton.styleFrom(
      backgroundColor: ink,
      foregroundColor: Colors.white,
      padding: const EdgeInsets.symmetric(horizontal: 24, vertical: 19),
      shape: RoundedRectangleBorder(borderRadius: BorderRadius.circular(14)),
    ),
  ),
  inputDecorationTheme: InputDecorationTheme(
    filled: true,
    fillColor: Colors.white,
    border: OutlineInputBorder(
      borderRadius: BorderRadius.circular(12),
      borderSide: BorderSide.none,
    ),
  ),
  sliderTheme: const SliderThemeData(
    activeTrackColor: ink,
    thumbColor: ink,
    inactiveTrackColor: Color(0xFFD3D7CC),
  ),
);

class PrimaryAction extends StatelessWidget {
  final String label;
  final VoidCallback? onPressed;
  final IconData icon;
  const PrimaryAction(
    this.label, {
    super.key,
    required this.onPressed,
    this.icon = Icons.arrow_forward_rounded,
  });
  @override
  Widget build(BuildContext context) => SizedBox(
    width: double.infinity,
    child: FilledButton(
      onPressed: onPressed,
      child: Row(
        mainAxisAlignment: MainAxisAlignment.spaceBetween,
        children: [Text(label), Icon(icon, size: 20)],
      ),
    ),
  );
}

class Eyebrow extends StatelessWidget {
  final String text;
  final Color color;
  const Eyebrow(this.text, {super.key, this.color = muted});
  @override
  Widget build(BuildContext context) => Text(
    text,
    style: TextStyle(
      fontSize: 11,
      fontWeight: FontWeight.w800,
      letterSpacing: 1.6,
      color: color,
    ),
  );
}

class AppPage extends StatelessWidget {
  final String title;
  final Widget child;
  final Widget? bottom;
  const AppPage({
    super.key,
    required this.title,
    required this.child,
    this.bottom,
  });
  @override
  Widget build(BuildContext context) => Scaffold(
    appBar: AppBar(
      title: Text(
        title,
        style: const TextStyle(fontSize: 15, fontWeight: FontWeight.w700),
      ),
    ),
    body: Center(
      child: ConstrainedBox(
        constraints: const BoxConstraints(maxWidth: 680),
        child: child,
      ),
    ),
    bottomNavigationBar: bottom == null
        ? null
        : SafeArea(
            top: false,
            child: Center(
              heightFactor: 1,
              child: ConstrainedBox(
                constraints: const BoxConstraints(maxWidth: 680),
                child: Padding(
                  padding: const EdgeInsets.fromLTRB(24, 8, 24, 12),
                  child: bottom,
                ),
              ),
            ),
          ),
  );
}
