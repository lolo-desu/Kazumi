import 'package:flutter/foundation.dart';
import 'package:flutter/material.dart';

/// GNOME presentation over the existing widgets. Routes, focus, semantics,
/// gestures and application state continue to belong to the upstream app.
abstract final class GnomeTheme {
  static bool get enabled =>
      !kIsWeb && defaultTargetPlatform == TargetPlatform.linux;

  static ThemeData apply(ThemeData base) {
    if (!enabled) return base;
    final dark = base.brightness == Brightness.dark;
    final oled = dark && base.scaffoldBackgroundColor == Colors.black;
    final window = oled ? Colors.black : Color(dark ? 0xff242424 : 0xfffafafb);
    final header = oled ? Colors.black : Color(dark ? 0xff303030 : 0xffebebed);
    final card = Color(dark ? 0xff383838 : 0xffffffff);
    final foreground = Color(dark ? 0xfff6f5f4 : 0xff2e3436);
    final secondary = Color(dark ? 0xffc0bfbc : 0xff5e5c64);
    final border = Color(dark ? 0xff505050 : 0xffd6d6da);
    // Keep the user's chosen/dynamic accent and semantic error colours.
    final accent = base.colorScheme.primary;
    final selected = Color.alphaBlend(accent.withValues(alpha: .16), window);
    final scheme = base.colorScheme.copyWith(
      surface: window,
      onSurface: foreground,
      onSurfaceVariant: secondary,
      surfaceDim: header,
      surfaceBright: card,
      surfaceContainerLowest: window,
      surfaceContainerLow: card,
      surfaceContainer: header,
      surfaceContainerHigh: card,
      surfaceContainerHighest: header,
      surfaceTint: Colors.transparent,
      primaryContainer: selected,
      onPrimaryContainer: foreground,
      secondaryContainer: header,
      onSecondaryContainer: foreground,
      tertiaryContainer: header,
      onTertiaryContainer: foreground,
      outline: secondary,
      outlineVariant: border,
    );
    const controlShape = RoundedRectangleBorder(
      borderRadius: BorderRadius.all(Radius.circular(6)),
    );
    final controlStyle = ButtonStyle(
      shape: const WidgetStatePropertyAll(controlShape),
      elevation: const WidgetStatePropertyAll(0),
      padding: const WidgetStatePropertyAll(
        EdgeInsets.symmetric(horizontal: 16, vertical: 10),
      ),
      // Retain the original hit targets and density for touch and keyboard use.
      textStyle: WidgetStatePropertyAll(
        base.textTheme.labelLarge?.copyWith(fontWeight: FontWeight.w600),
      ),
    );
    final flatStyle = controlStyle.copyWith(
      foregroundColor: WidgetStateProperty.resolveWith(
        (states) => states.contains(WidgetState.disabled)
            ? foreground.withValues(alpha: .38)
            : foreground,
      ),
    );
    final heading = base.textTheme.titleMedium?.copyWith(
      color: foreground,
      fontWeight: FontWeight.w700,
    );
    return base.copyWith(
      colorScheme: scheme,
      scaffoldBackgroundColor: window,
      canvasColor: window,
      dividerColor: border,
      splashFactory: NoSplash.splashFactory,
      hoverColor: foreground.withValues(alpha: .07),
      highlightColor: foreground.withValues(alpha: .10),
      focusColor: accent.withValues(alpha: .20),
      appBarTheme: base.appBarTheme.copyWith(
        backgroundColor: header,
        foregroundColor: foreground,
        surfaceTintColor: Colors.transparent,
        elevation: 0,
        scrolledUnderElevation: 0,
        centerTitle: true,
        titleTextStyle: heading,
        shape: Border(bottom: BorderSide(color: border, width: .5)),
      ),
      cardTheme: base.cardTheme.copyWith(
        color: card,
        surfaceTintColor: Colors.transparent,
        elevation: 0,
        shape: RoundedRectangleBorder(
          borderRadius: BorderRadius.circular(12),
          side: BorderSide(color: border, width: .5),
        ),
      ),
      elevatedButtonTheme: ElevatedButtonThemeData(
        style: flatStyle.copyWith(
          backgroundColor: WidgetStateProperty.resolveWith(
            (states) => states.contains(WidgetState.disabled)
                ? header.withValues(alpha: .5)
                : header,
          ),
        ),
      ),
      filledButtonTheme: FilledButtonThemeData(style: controlStyle),
      outlinedButtonTheme: OutlinedButtonThemeData(
        style: flatStyle.copyWith(
          side: WidgetStatePropertyAll(BorderSide(color: border)),
        ),
      ),
      textButtonTheme: TextButtonThemeData(style: controlStyle),
      iconButtonTheme: const IconButtonThemeData(
        style: ButtonStyle(shape: WidgetStatePropertyAll(controlShape)),
      ),
      floatingActionButtonTheme: base.floatingActionButtonTheme.copyWith(
        elevation: 0,
        focusElevation: 0,
        hoverElevation: 0,
        highlightElevation: 0,
        shape: RoundedRectangleBorder(borderRadius: BorderRadius.circular(12)),
      ),
      navigationRailTheme: base.navigationRailTheme.copyWith(
        backgroundColor: header,
        indicatorColor: selected,
        indicatorShape: controlShape,
        elevation: 0,
        selectedIconTheme: IconThemeData(color: accent),
        unselectedIconTheme: IconThemeData(color: secondary),
        selectedLabelTextStyle: base.textTheme.labelMedium?.copyWith(
          color: foreground,
          fontWeight: FontWeight.w700,
        ),
        unselectedLabelTextStyle: base.textTheme.labelMedium?.copyWith(
          color: secondary,
        ),
      ),
      navigationDrawerTheme: base.navigationDrawerTheme.copyWith(
        backgroundColor: header,
        surfaceTintColor: Colors.transparent,
        indicatorColor: selected,
        indicatorShape: controlShape,
        elevation: 0,
      ),
      navigationBarTheme: base.navigationBarTheme.copyWith(
        backgroundColor: header,
        surfaceTintColor: Colors.transparent,
        indicatorColor: selected,
        indicatorShape: controlShape,
        elevation: 0,
      ),
      bottomNavigationBarTheme: base.bottomNavigationBarTheme.copyWith(
        backgroundColor: header,
        selectedItemColor: accent,
        unselectedItemColor: secondary,
        elevation: 0,
      ),
      dialogTheme: base.dialogTheme.copyWith(
        backgroundColor: card,
        surfaceTintColor: Colors.transparent,
        shape: RoundedRectangleBorder(borderRadius: BorderRadius.circular(12)),
        titleTextStyle: heading,
      ),
      bottomSheetTheme: base.bottomSheetTheme.copyWith(
        backgroundColor: card,
        surfaceTintColor: Colors.transparent,
        shape: const RoundedRectangleBorder(
          borderRadius: BorderRadius.vertical(top: Radius.circular(12)),
        ),
      ),
      popupMenuTheme: base.popupMenuTheme.copyWith(
        color: card,
        surfaceTintColor: Colors.transparent,
        shape: RoundedRectangleBorder(
          borderRadius: BorderRadius.circular(8),
          side: BorderSide(color: border, width: .5),
        ),
      ),
      menuTheme: MenuThemeData(
        style: MenuStyle(
          backgroundColor: WidgetStatePropertyAll(card),
          surfaceTintColor: const WidgetStatePropertyAll(Colors.transparent),
          shape: const WidgetStatePropertyAll(controlShape),
        ),
      ),
      inputDecorationTheme: base.inputDecorationTheme.copyWith(
        filled: true,
        fillColor: card,
        border: OutlineInputBorder(
          borderRadius: BorderRadius.circular(6),
          borderSide: BorderSide(color: border),
        ),
        enabledBorder: OutlineInputBorder(
          borderRadius: BorderRadius.circular(6),
          borderSide: BorderSide(color: border),
        ),
        focusedBorder: OutlineInputBorder(
          borderRadius: BorderRadius.circular(6),
          borderSide: BorderSide(color: accent, width: 2),
        ),
      ),
      searchBarTheme: base.searchBarTheme.copyWith(
        backgroundColor: WidgetStatePropertyAll(card),
        surfaceTintColor: const WidgetStatePropertyAll(Colors.transparent),
        elevation: const WidgetStatePropertyAll(0),
        shape: const WidgetStatePropertyAll(controlShape),
        side: WidgetStatePropertyAll(BorderSide(color: border)),
      ),
      segmentedButtonTheme: SegmentedButtonThemeData(style: controlStyle),
      datePickerTheme: base.datePickerTheme.copyWith(
        backgroundColor: card,
        surfaceTintColor: Colors.transparent,
        shape: RoundedRectangleBorder(borderRadius: BorderRadius.circular(12)),
      ),
      timePickerTheme: base.timePickerTheme.copyWith(
        backgroundColor: card,
        shape: RoundedRectangleBorder(borderRadius: BorderRadius.circular(12)),
      ),
      chipTheme: base.chipTheme.copyWith(
        shape: controlShape,
        backgroundColor: header,
        selectedColor: selected,
        side: BorderSide.none,
      ),
      switchTheme: base.switchTheme.copyWith(
        thumbIcon: const WidgetStatePropertyAll(null),
        thumbColor: WidgetStateProperty.resolveWith(
          (states) => states.contains(WidgetState.disabled)
              ? card.withValues(alpha: .5)
              : Colors.white,
        ),
        trackColor: WidgetStateProperty.resolveWith(
          (states) => states.contains(WidgetState.selected)
              ? accent.withValues(
                  alpha: states.contains(WidgetState.disabled) ? .4 : 1,
                )
              : border,
        ),
        trackOutlineColor: const WidgetStatePropertyAll(Colors.transparent),
      ),
      checkboxTheme: base.checkboxTheme.copyWith(shape: controlShape),
      listTileTheme: base.listTileTheme.copyWith(
        shape: controlShape,
        selectedTileColor: selected,
        iconColor: secondary,
        textColor: foreground,
      ),
      tabBarTheme: base.tabBarTheme.copyWith(
        labelColor: accent,
        unselectedLabelColor: secondary,
        dividerColor: border,
        indicatorColor: accent,
      ),
      snackBarTheme: base.snackBarTheme.copyWith(
        backgroundColor: foreground,
        contentTextStyle: base.textTheme.bodyMedium?.copyWith(color: window),
        actionTextColor:
            dark ? base.colorScheme.onPrimary : base.colorScheme.inversePrimary,
        shape: RoundedRectangleBorder(borderRadius: BorderRadius.circular(8)),
        elevation: 2,
      ),
    );
  }
}
