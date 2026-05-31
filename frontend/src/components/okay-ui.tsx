import { ReactNode, useEffect, useRef, useState } from "react";
import {
  Animated,
  LayoutChangeEvent,
  Pressable,
  ScrollView,
  StyleProp,
  StyleSheet,
  Text,
  TextStyle,
  View,
  ViewStyle,
} from "react-native";
import { Ionicons, MaterialCommunityIcons } from "@expo/vector-icons";
import { useRouter } from "expo-router";
import { SafeAreaView } from "react-native-safe-area-context";

import {
  colors,
  layout,
  radius,
  spacing,
  typography,
} from "../constants/theme";

type IconName = React.ComponentProps<typeof Ionicons>["name"];
type MaterialIconName = React.ComponentProps<
  typeof MaterialCommunityIcons
>["name"];
type BottomTabKey = "disaster" | "missing";

let previousBottomTab: BottomTabKey = "disaster";
let lastTabDirection: -1 | 0 | 1 = 0;

type ScreenProps = {
  children: ReactNode;
  scroll?: boolean;
  centered?: boolean;
  style?: StyleProp<ViewStyle>;
  contentStyle?: StyleProp<ViewStyle>;
};

export function AppScreen({
  children,
  scroll = false,
  centered = false,
  style,
  contentStyle,
}: ScreenProps) {
  const content = (
    <View style={[styles.content, centered && styles.centered, contentStyle]}>
      {children}
    </View>
  );

  return (
    <SafeAreaView style={[styles.safeArea, style]} edges={["top", "bottom"]}>
      {scroll ? (
        <ScrollView
          bounces={false}
          showsVerticalScrollIndicator={false}
          contentContainerStyle={[styles.scrollContent, contentStyle]}
        >
          {children}
        </ScrollView>
      ) : (
        content
      )}
    </SafeAreaView>
  );
}

type HeaderProps = {
  title: string;
  backLabel?: string;
  showBack?: boolean;
  left?: ReactNode;
  right?: ReactNode;
};

export function AppHeader({
  title,
  backLabel,
  showBack = false,
  left,
  right,
}: HeaderProps) {
  const router = useRouter();

  return (
    <View style={styles.header}>
      <View style={styles.headerSide}>
        {showBack ? (
          <Pressable
            accessibilityRole="button"
            onPress={() => router.back()}
            style={styles.headerBack}
          >
            {backLabel ? (
              <Text style={styles.backLabel}>
                {"< "}
                {backLabel}
              </Text>
            ) : (
              <Ionicons name="arrow-back" size={31} color={colors.text} />
            )}
          </Pressable>
        ) : (
          left
        )}
      </View>
      <Text style={styles.headerTitle}>{title}</Text>
      <View style={[styles.headerSide, styles.headerRight]}>{right}</View>
    </View>
  );
}

export function HeaderActions() {
  const router = useRouter();

  return (
    <View style={styles.headerActions}>
      <Pressable
        accessibilityRole="button"
        accessibilityLabel="지난 알람 보기"
        onPress={() => router.push("/alert-history" as never)}
        style={styles.headerIconButton}
      >
        <Ionicons name="notifications-outline" size={31} color={colors.text} />
      </Pressable>
      <Pressable
        accessibilityRole="button"
        accessibilityLabel="정보 수정 보기"
        onPress={() => router.push("/profile-edit1" as never)}
        style={styles.headerIconButton}
      >
        <Ionicons name="person-circle-outline" size={34} color={colors.text} />
      </Pressable>
    </View>
  );
}

export function PrimaryButton({
  children,
  onPress,
  style,
  textStyle,
}: {
  children: ReactNode;
  onPress?: () => void;
  style?: StyleProp<ViewStyle>;
  textStyle?: StyleProp<TextStyle>;
}) {
  return (
    <Pressable
      accessibilityRole="button"
      onPress={onPress}
      style={({ pressed }) => [
        styles.primaryButton,
        pressed && styles.pressed,
        style,
      ]}
    >
      {typeof children === "string" ? (
        <Text style={[styles.primaryButtonText, textStyle]}>{children}</Text>
      ) : (
        children
      )}
    </Pressable>
  );
}

export function SecondaryButton({
  children,
  onPress,
  style,
}: {
  children: ReactNode;
  onPress?: () => void;
  style?: StyleProp<ViewStyle>;
}) {
  return (
    <Pressable
      accessibilityRole="button"
      onPress={onPress}
      style={({ pressed }) => [
        styles.secondaryButton,
        pressed && styles.pressed,
        style,
      ]}
    >
      {typeof children === "string" ? (
        <Text style={styles.secondaryButtonText}>{children}</Text>
      ) : (
        children
      )}
    </Pressable>
  );
}

export function FieldLabel({
  icon,
  children,
}: {
  icon?: IconName;
  children: ReactNode;
}) {
  return (
    <View style={styles.fieldLabel}>
      {icon ? <Ionicons name={icon} size={19} color={colors.primary} /> : null}
      <Text style={styles.fieldLabelText}>{children}</Text>
    </View>
  );
}

export function MaterialFieldLabel({
  icon,
  children,
}: {
  icon: MaterialIconName;
  children: ReactNode;
}) {
  return (
    <View style={styles.fieldLabel}>
      <MaterialCommunityIcons name={icon} size={21} color={colors.primary} />
      <Text style={styles.fieldLabelText}>{children}</Text>
    </View>
  );
}

export function InputBox({
  placeholder,
  value,
  muted = false,
  onPress,
  rightAccessory,
}: {
  placeholder?: string;
  value?: string;
  muted?: boolean;
  onPress?: () => void;
  rightAccessory?: ReactNode;
}) {
  const content = (
    <>
      <Text
        numberOfLines={1}
        style={[styles.inputText, value && styles.inputValue]}
      >
        {value ?? placeholder}
      </Text>
      {rightAccessory}
    </>
  );

  if (onPress) {
    return (
      <Pressable
        accessibilityRole="button"
        onPress={onPress}
        style={({ pressed }) => [
          styles.inputBox,
          muted && styles.mutedInput,
          pressed && styles.pressed,
        ]}
      >
        {content}
      </Pressable>
    );
  }

  return (
    <View style={[styles.inputBox, muted && styles.mutedInput]}>{content}</View>
  );
}

export function OptionPill({
  children,
  selected,
  onPress,
  style,
}: {
  children: ReactNode;
  selected?: boolean;
  onPress?: () => void;
  style?: StyleProp<ViewStyle>;
}) {
  return (
    <Pressable
      accessibilityRole="button"
      onPress={onPress}
      disabled={!onPress}
      style={({ pressed }) => [
        styles.optionPill,
        selected && styles.optionPillSelected,
        pressed && styles.pressed,
        style,
      ]}
    >
      <Text style={[styles.optionText, selected && styles.optionTextSelected]}>
        {children}
      </Text>
    </Pressable>
  );
}

export function ScreenTitle({ children }: { children: ReactNode }) {
  return <Text style={styles.screenTitle}>{children}</Text>;
}

export function Card({
  children,
  style,
}: {
  children: ReactNode;
  style?: StyleProp<ViewStyle>;
}) {
  return <View style={[styles.card, style]}>{children}</View>;
}

export function BottomTabs({ active }: { active: BottomTabKey }) {
  const router = useRouter();
  const [width, setWidth] = useState(0);
  const activeIndex = active === "disaster" ? 0 : 1;
  const previousIndex = previousBottomTab === "disaster" ? 0 : 1;
  const slide = useRef(new Animated.Value(previousIndex)).current;
  const horizontalPadding = spacing.md;
  const tabGap = spacing.md;
  const pillWidth =
    width > 0 ? (width - horizontalPadding * 2 - tabGap) / 2 : 0;
  const pillLeft = Animated.add(
    new Animated.Value(horizontalPadding),
    Animated.multiply(slide, pillWidth + tabGap),
  );

  useEffect(() => {
    Animated.timing(slide, {
      toValue: activeIndex,
      duration: 180,
      useNativeDriver: false,
    }).start();
    previousBottomTab = active;
  }, [active, activeIndex, slide]);

  const handleLayout = (event: LayoutChangeEvent) => {
    setWidth(event.nativeEvent.layout.width);
  };

  const goDisaster = () => {
    if (active !== "disaster") {
      lastTabDirection = -1;
      router.replace("/disaster-caution" as never);
    }
  };
  const goMissing = () => {
    if (active !== "missing") {
      lastTabDirection = 1;
      router.replace("/missing" as never);
    }
  };

  return (
    <View style={styles.bottomTabs} onLayout={handleLayout}>
      {pillWidth > 0 ? (
        <Animated.View
          pointerEvents="none"
          style={[
            styles.tabActiveIndicator,
            {
              width: pillWidth,
              left: pillLeft,
            },
          ]}
        />
      ) : null}
      <Pressable
        accessibilityRole="button"
        onPress={goDisaster}
        style={styles.tabButton}
      >
        <MaterialCommunityIcons
          name="home-flood"
          size={31}
          color={active === "disaster" ? colors.background : colors.text}
        />
        <Text
          style={[
            styles.tabText,
            active === "disaster" && styles.tabTextActive,
          ]}
        >
          재난
        </Text>
      </Pressable>
      <Pressable
        accessibilityRole="button"
        onPress={goMissing}
        style={styles.tabButton}
      >
        <MaterialCommunityIcons
          name="account-search-outline"
          size={31}
          color={active === "missing" ? colors.background : colors.text}
        />
        <Text
          style={[styles.tabText, active === "missing" && styles.tabTextActive]}
        >
          실종
        </Text>
      </Pressable>
    </View>
  );
}

export function TabSceneTransition({
  active,
  children,
}: {
  active: BottomTabKey;
  children: ReactNode;
}) {
  const direction = lastTabDirection;
  const translateX = useRef(new Animated.Value(direction * 46)).current;
  const opacity = useRef(
    new Animated.Value(direction === 0 ? 1 : 0.92),
  ).current;

  useEffect(() => {
    translateX.setValue(direction * 46);
    opacity.setValue(direction === 0 ? 1 : 0.92);
    Animated.parallel([
      Animated.timing(translateX, {
        toValue: 0,
        duration: 210,
        useNativeDriver: true,
      }),
      Animated.timing(opacity, {
        toValue: 1,
        duration: 210,
        useNativeDriver: true,
      }),
    ]).start(() => {
      lastTabDirection = 0;
    });
  }, [active, direction, opacity, translateX]);

  return (
    <Animated.View
      style={[
        styles.tabScene,
        {
          opacity,
          transform: [{ translateX }],
        },
      ]}
    >
      {children}
    </Animated.View>
  );
}

export function StatusBadge({ children }: { children: ReactNode }) {
  return (
    <View style={styles.statusBadge}>
      <Text style={styles.statusBadgeText}>{children}</Text>
    </View>
  );
}

export function Divider({ color = colors.cardLine }: { color?: string }) {
  return <View style={[styles.divider, { backgroundColor: color }]} />;
}

const shadow: ViewStyle = {
  shadowColor: "#000",
  shadowOpacity: 0.18,
  shadowRadius: 4,
  shadowOffset: { width: 0, height: 2 },
  elevation: 3,
};

const styles = StyleSheet.create({
  safeArea: {
    flex: 1,
    backgroundColor: colors.background,
  },
  content: {
    flex: 1,
    paddingHorizontal: layout.screenHorizontal,
    paddingTop: 8,
    paddingBottom: layout.screeBottom,
  },
  scrollContent: {
    flexGrow: 1,
    paddingHorizontal: layout.screenHorizontal,
    paddingTop: 8,
    paddingBottom: layout.screeBottom,
  },
  centered: {
    justifyContent: "center",
  },
  header: {
    height: 46,
    alignItems: "center",
    flexDirection: "row",
    justifyContent: "space-between",
    marginBottom: 14,
  },
  headerSide: {
    width: 116,
    minHeight: 42,
    justifyContent: "center",
  },
  headerRight: {
    alignItems: "flex-end",
  },
  headerBack: {
    alignSelf: "flex-start",
    minHeight: 42,
    justifyContent: "center",
  },
  backLabel: {
    ...typography.titleMedium,
    color: colors.PreviousStep,
  },
  headerTitle: {
    ...typography.titleMedium,
    color: colors.text,
    textAlign: "center",
  },
  headerActions: {
    flexDirection: "row",
    alignItems: "center",
    gap: 12,
  },
  headerIconButton: {
    width: 40,
    height: 40,
    alignItems: "center",
    justifyContent: "center",
  },
  primaryButton: {
    minHeight: 53,
    borderRadius: radius.borderRadiusSm,
    backgroundColor: colors.primary,
    alignItems: "center",
    justifyContent: "center",
    paddingHorizontal: spacing.lg,
  },
  primaryButtonText: {
    ...typography.titleMedium,
    color: colors.background,
  },
  secondaryButton: {
    minHeight: 51,
    borderRadius: radius.borderRadiusSm,
    borderWidth: 1,
    borderColor: colors.cardLine,
    backgroundColor: colors.background,
    alignItems: "center",
    justifyContent: "center",
    paddingHorizontal: spacing.lg,
  },
  secondaryButtonText: {
    ...typography.titleMedium,
    color: colors.text,
  },
  pressed: {
    opacity: 0.78,
  },
  fieldLabel: {
    flexDirection: "row",
    alignItems: "center",
    gap: 3,
    marginBottom: spacing.md,
  },
  fieldLabelText: {
    ...typography.titleMedium,
    color: colors.text,
  },
  inputBox: {
    minHeight: 44,
    borderWidth: 1,
    borderColor: colors.cardLine,
    borderRadius: radius.borderRadiusSm,
    backgroundColor: colors.card,
    paddingHorizontal: spacing.lg,
    flexDirection: "row",
    alignItems: "center",
    justifyContent: "center",
  },
  mutedInput: {
    backgroundColor: "#F4F4F4",
  },
  inputText: {
    flex: 1,
    ...typography.titleMedium,
    color: colors.subText,
  },
  inputValue: {
    color: colors.subText,
  },
  optionPill: {
    minHeight: 44,
    flex: 1,
    borderWidth: 1,
    borderColor: colors.cardLine,
    borderRadius: radius.borderRadiusSm,
    backgroundColor: colors.card,
    alignItems: "center",
    justifyContent: "center",
    paddingHorizontal: spacing.md,
  },
  optionPillSelected: {
    borderColor: colors.primary,
    backgroundColor: colors.checkCard,
  },
  optionText: {
    ...typography.titleMedium,
    color: colors.actionText,
  },
  optionTextSelected: {
    color: colors.primary,
    fontWeight: "700",
  },
  screenTitle: {
    fontSize: 28,
    lineHeight: 34,
    fontWeight: "700",
    color: colors.text,
  },
  card: {
    borderRadius: radius.borderRadiusSm,
    borderWidth: 1,
    borderColor: colors.cardLine,
    backgroundColor: colors.background,
    ...shadow,
  },
  bottomTabs: {
    height: 69,
    borderRadius: radius.borderRadiusLg,
    backgroundColor: colors.menu,
    flexDirection: "row",
    padding: spacing.md,
    gap: spacing.md,
  },
  tabScene: {
    flex: 1,
  },
  tabButton: {
    flex: 1,
    borderRadius: radius.borderRadiusLg,
    alignItems: "center",
    justifyContent: "center",
    zIndex: 1,
  },
  tabActiveIndicator: {
    position: "absolute",
    top: spacing.md,
    bottom: spacing.md,
    borderRadius: radius.borderRadiusLg,
    backgroundColor: colors.actionText,
  },
  tabText: {
    ...typography.menuTiny,
    color: colors.text,
    marginTop: -2,
  },
  tabTextActive: {
    color: colors.background,
  },
  statusBadge: {
    borderRadius: 7,
    backgroundColor: colors.primary,
    paddingHorizontal: 12,
    paddingVertical: 6,
    alignSelf: "flex-start",
  },
  statusBadgeText: {
    ...typography.titleMedium,
    color: colors.background,
  },
  divider: {
    height: 1,
    opacity: 0.85,
  },
});
