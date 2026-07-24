import 'package:flutter/material.dart';

/// Fuzzy draft/development upside grade shown across scouting surfaces.
///
/// Values come straight from the backend's `assign_ceiling_label`:
/// 'High Upside', 'Some Upside', 'Near Ceiling'. The number behind the grade is
/// deliberately never exposed — you never really know a guy's ceiling until you
/// coach him up (see training_and_potential.md, decision #9).
Color upsideColor(String label) {
  switch (label) {
    case 'High Upside':
      return const Color(0xFFF0A020); // amber — raw project, big room to grow
    case 'Some Upside':
      return const Color(0xFF3AA6A0); // teal — a little room left
    default:
      return Colors.blueGrey;         // Near Ceiling — finished product
  }
}

IconData _upsideIcon(String label) {
  switch (label) {
    case 'High Upside':
      return Icons.trending_up;
    case 'Some Upside':
      return Icons.north_east;
    default:
      return Icons.trending_flat;
  }
}

/// Compact pill rendering an upside grade. [compact] tightens it for dense list
/// rows; the default sizing suits detail sheets.
class UpsideChip extends StatelessWidget {
  final String label;
  final bool compact;

  const UpsideChip(this.label, {super.key, this.compact = false});

  @override
  Widget build(BuildContext context) {
    final color = upsideColor(label);
    return Container(
      padding: EdgeInsets.symmetric(horizontal: compact ? 6 : 8, vertical: 2),
      decoration: BoxDecoration(
        color: color.withValues(alpha: 0.15),
        borderRadius: BorderRadius.circular(8),
        border: Border.all(color: color.withValues(alpha: 0.45)),
      ),
      child: Row(
        mainAxisSize: MainAxisSize.min,
        children: [
          Icon(_upsideIcon(label), size: compact ? 11 : 13, color: color),
          const SizedBox(width: 3),
          Text(
            label,
            style: TextStyle(
              fontSize: compact ? 10 : 11,
              fontWeight: FontWeight.w600,
              color: color,
            ),
          ),
        ],
      ),
    );
  }
}
