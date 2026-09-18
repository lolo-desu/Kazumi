import 'package:flutter/material.dart';

/// A scrollable GNOME sidebar using the app's original destinations/callbacks.
/// Each row remains a keyboard-focusable, labelled control with a 48px target.
class GnomeSidebar extends StatelessWidget {
  const GnomeSidebar({
    super.key,
    required this.selectedIndex,
    required this.labels,
    required this.icons,
    required this.onSelected,
    this.header,
  }) : assert(labels.length == icons.length);

  final int selectedIndex;
  final List<String> labels;
  final List<Widget> icons;
  final ValueChanged<int> onSelected;
  final Widget? header;

  @override
  Widget build(BuildContext context) {
    final theme = Theme.of(context);
    final colors = theme.colorScheme;
    return Container(
      width: 180,
      decoration: BoxDecoration(
        color: colors.surfaceContainer,
        border: Border(
          right: BorderSide(color: colors.outlineVariant, width: .5),
        ),
      ),
      child: SafeArea(
        right: false,
        child: ListView(
          padding: const EdgeInsets.all(8),
          children: [
            if (header != null) ...[header!, const SizedBox(height: 12)],
            for (var index = 0; index < labels.length; index++)
              Padding(
                padding: const EdgeInsets.only(bottom: 4),
                child: Semantics(
                  selected: index == selectedIndex,
                  child: Tooltip(
                    message: labels[index],
                    child: TextButton(
                      onPressed: () => onSelected(index),
                      style: TextButton.styleFrom(
                        alignment: AlignmentDirectional.centerStart,
                        minimumSize: const Size.fromHeight(48),
                        foregroundColor: colors.onSurface,
                        backgroundColor: index == selectedIndex
                            ? colors.primary.withValues(alpha: .14)
                            : Colors.transparent,
                        padding: const EdgeInsets.symmetric(
                          horizontal: 12,
                          vertical: 10,
                        ),
                      ),
                      child: Row(
                        children: [
                          IconTheme(
                            data: IconThemeData(
                              size: 20,
                              color: index == selectedIndex
                                  ? colors.primary
                                  : colors.onSurfaceVariant,
                            ),
                            child: icons[index],
                          ),
                          const SizedBox(width: 12),
                          Expanded(
                            child: Text(
                              labels[index],
                              style: TextStyle(
                                fontWeight: index == selectedIndex
                                    ? FontWeight.w700
                                    : FontWeight.w500,
                              ),
                            ),
                          ),
                        ],
                      ),
                    ),
                  ),
                ),
              ),
          ],
        ),
      ),
    );
  }
}
