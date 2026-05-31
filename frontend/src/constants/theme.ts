import { Platform } from "react-native";

import { Colors as colors } from "./colors";
import { spacing as spacing, layout, radius, size } from "./spacing";
import { typography } from "./typography";

export const theme = {
  colors,
  spacing,
  layout,
  radius,
  size,
  typography,
} as const;

export { colors, spacing, layout, radius, size, typography };

// Expo template compatibility for existing themed helper components.
export const Colors = {
  light: {
    text: colors.text,
    background: colors.background,
    tint: colors.primary,
    icon: colors.subText,
    tabIconDefault: colors.subText,
    tabIconSelected: colors.primary,
  },
  dark: {
    text: colors.background,
    background: colors.text,
    tint: colors.primary,
    icon: colors.cardLine,
    tabIconDefault: colors.cardLine,
    tabIconSelected: colors.primary,
  },
} as const;

export const Fonts = Platform.select({
  ios: {
    sans: "system-ui",
    serif: "ui-serif",
    rounded: "ui-rounded",
    mono: "ui-monospace",
  },
  default: {
    sans: "normal",
    serif: "serif",
    rounded: "normal",
    mono: "monospace",
  },
  web: {
    sans: "system-ui, -apple-system, BlinkMacSystemFont, 'Segoe UI', Roboto, Helvetica, Arial, sans-serif",
    serif: "Georgia, 'Times New Roman', serif",
    rounded:
      "'SF Pro Rounded', 'Hiragino Maru Gothic ProN', Meiryo, 'MS PGothic', sans-serif",
    mono: "SFMono-Regular, Menlo, Monaco, Consolas, 'Liberation Mono', 'Courier New', monospace",
  },
});
