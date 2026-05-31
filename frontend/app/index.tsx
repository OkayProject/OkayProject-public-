import { Pressable, StyleSheet, Text, View } from "react-native";
import { useRouter } from "expo-router";

import { colors, typography } from "../src/constants/theme";

export default function SplashScreen() {
  const router = useRouter();

  return (
    <Pressable
      style={styles.container}
      onPress={() => router.push("/onboarding")}
    >
      <View style={styles.center}>
        <Text style={styles.logo}>내곁안전</Text>
        <Text style={styles.subtitle}>
          개인 맞춤형 재난·실종 안전 알림 서비스
        </Text>
      </View>
    </Pressable>
  );
}

const styles = StyleSheet.create({
  container: {
    flex: 1,
    backgroundColor: colors.primary,
    justifyContent: "center",
  },
  center: {
    alignItems: "center",
  },
  logo: {
    ...typography.splashTitle,
    color: colors.background,
    marginBottom: 26,
  },
  subtitle: {
    ...typography.titleMedium,
    color: colors.background,
  },
});
